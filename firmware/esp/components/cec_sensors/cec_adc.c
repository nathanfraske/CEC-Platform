/*
 * cec_adc — one component, one API, two backends (firmware
 * consolidation, Phase F2). The backend is selected per app via
 * Kconfig (CEC_ADC_BACKEND_*); both arms below are the respective
 * source trees verbatim, plus stubs filling out the union API:
 *
 *   CONTINUOUS (24-pin lineage): ADC1 runs in continuous (DMA) mode at
 *   a fixed per-channel cadence; a reader task maintains a per-channel
 *   latest-calibrated-mV table and reads are constant-time, lock-free
 *   lookups. `samples` is ignored. cec_adc_start() applies the pattern.
 *   No pause/resume hand-off (HS capture on this backend reads the same
 *   table via the callback source).
 *
 *   ONESHOT (eps lineage): adc_oneshot + curve-fit calibration with
 *   per-read averaging (`samples` honored), plus the pause/resume
 *   hand-off so cec_capture's adc_continuous HS path can borrow the
 *   unit and give it back (tracked channels re-applied on resume).
 */

#include "sdkconfig.h"
#include "esp_adc/adc_cali_scheme.h"

/* Both backends use the curve-fitting calibration scheme, which every
 * CEC target has (esp32s3, esp32p4, esp32c6). If this fires, the build
 * is targeting a line-fitting-only chip (plain esp32 / esp32s2) --
 * almost certainly a wrong set-target: run
 *   idf.py set-target <esp32s3|esp32p4>
 * (each app's sdkconfig.defaults names its chip; the VSCode extension's
 * "Set Espressif Device Target" overrides it and defaults to esp32). */
#ifndef ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
#error "cec_adc: IDF_TARGET has no curve-fitting ADC cali (plain esp32/esp32s2?). Wrong set-target -- CEC apps build for esp32s3 or esp32p4; see the app's sdkconfig.defaults."
#endif

#if CONFIG_CEC_ADC_BACKEND_CONTINUOUS
/* ======================================================================
 * CONTINUOUS backend (24-pin lineage)
 * ====================================================================== */
#include <stdbool.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_check.h"
#include "esp_adc/adc_continuous.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "cec_adc.h"

static const char *TAG = "cec_adc";

/* Per-channel sample rate. Total ADC sample rate is this times the
 * number of channels in the pattern. 1 kHz per channel matches the
 * HS capture cadence so each HS read sees a fresh sample. */
#define ADC_PER_CHAN_HZ        1000U

/* ESP32-S3 ADC1 has 10 channels (CH0..CH9). */
#define MAX_CHANNELS           10

/* DMA buffer sizing. Reader task drains the buffer aggressively so
 * overflow is the only failure mode worth worrying about: at 7 channels
 * × 1 kHz × 4 bytes/sample = 28 KB/s, a 4 KB buffer fills every ~140 ms.
 * The reader runs much faster than that. */
#define DMA_FRAME_BYTES        256
#define DMA_BUF_BYTES          4096

#define READER_TASK_STACK      4096
#define READER_TASK_PRIORITY   (configMAX_PRIORITIES - 3)
#define READ_TIMEOUT_MS        100

static adc_continuous_handle_t s_handle = NULL;
static adc_cali_handle_t       s_cali = NULL;

/* Per-channel latest calibrated mV. int writes are word-sized and
 * atomic on ESP32-S3, so readers can sample without locking. */
static volatile int  s_latest_mv[MAX_CHANNELS];
static volatile bool s_channel_seen[MAX_CHANNELS];

/* Channel list accumulated via cec_adc_setup_channel and applied as a
 * pattern when cec_adc_start runs. */
static adc_channel_t s_pattern_channels[MAX_CHANNELS];
static size_t        s_pattern_count = 0;

static bool s_inited  = false;
static bool s_started = false;

esp_err_t cec_adc_init(void)
{
    if (s_inited) return ESP_OK;

    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id  = ADC_UNIT_1,
        .atten    = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    ESP_RETURN_ON_ERROR(adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_cali),
                        TAG, "adc_cali_create_scheme_curve_fitting");

    memset((void *)s_latest_mv, 0, sizeof(s_latest_mv));
    memset((void *)s_channel_seen, 0, sizeof(s_channel_seen));
    s_pattern_count = 0;
    s_inited = true;
    ESP_LOGI(TAG, "ADC1 + curve-fit calibration ready (atten=DB_12)");
    return ESP_OK;
}

esp_err_t cec_adc_setup_channel(adc_channel_t channel)
{
    if (!s_inited)  return ESP_ERR_INVALID_STATE;
    if (s_started)  return ESP_ERR_INVALID_STATE;   /* pattern locked once started */
    if ((int)channel < 0 || (int)channel >= MAX_CHANNELS) return ESP_ERR_INVALID_ARG;

    /* Idempotent: re-registering an already-known channel is a no-op. */
    for (size_t i = 0; i < s_pattern_count; i++) {
        if (s_pattern_channels[i] == channel) return ESP_OK;
    }
    if (s_pattern_count >= MAX_CHANNELS) return ESP_ERR_NO_MEM;
    s_pattern_channels[s_pattern_count++] = channel;
    return ESP_OK;
}

static void reader_task(void *arg)
{
    (void)arg;
    static uint8_t buf[DMA_FRAME_BYTES];

    while (1) {
        uint32_t bytes_read = 0;
        esp_err_t err = adc_continuous_read(s_handle, buf, sizeof(buf),
                                            &bytes_read, READ_TIMEOUT_MS);
        if (err == ESP_ERR_TIMEOUT) {
            /* No data this window — usually means the reader is keeping
             * up perfectly. Loop and try again. */
            continue;
        }
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "adc_continuous_read: %s", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= bytes_read;
             i += SOC_ADC_DIGI_RESULT_BYTES) {
            adc_digi_output_data_t *p = (adc_digi_output_data_t *)&buf[i];
            uint32_t ch  = p->type2.channel;
            uint32_t raw = p->type2.data;
            if (ch >= MAX_CHANNELS) continue;
            int mv = 0;
            if (adc_cali_raw_to_voltage(s_cali, (int)raw, &mv) == ESP_OK) {
                s_latest_mv[ch] = mv;
                s_channel_seen[ch] = true;
            }
        }
    }
}

esp_err_t cec_adc_start(void)
{
    if (!s_inited)           return ESP_ERR_INVALID_STATE;
    if (s_started)           return ESP_OK;
    if (s_pattern_count == 0) return ESP_ERR_INVALID_STATE;

    adc_continuous_handle_cfg_t handle_cfg = {
        .max_store_buf_size = DMA_BUF_BYTES,
        .conv_frame_size    = DMA_FRAME_BYTES,
    };
    ESP_RETURN_ON_ERROR(adc_continuous_new_handle(&handle_cfg, &s_handle),
                        TAG, "adc_continuous_new_handle");

    adc_digi_pattern_config_t pattern[MAX_CHANNELS];
    for (size_t i = 0; i < s_pattern_count; i++) {
        pattern[i].atten     = ADC_ATTEN_DB_12;
        pattern[i].channel   = s_pattern_channels[i];
        pattern[i].unit      = ADC_UNIT_1;
        pattern[i].bit_width = ADC_BITWIDTH_12;
    }

    adc_continuous_config_t dig_cfg = {
        .pattern_num    = s_pattern_count,
        .adc_pattern    = pattern,
        .sample_freq_hz = ADC_PER_CHAN_HZ * (uint32_t)s_pattern_count,
        .conv_mode      = ADC_CONV_SINGLE_UNIT_1,
        .format         = ADC_DIGI_OUTPUT_FORMAT_TYPE2,
    };
    ESP_RETURN_ON_ERROR(adc_continuous_config(s_handle, &dig_cfg),
                        TAG, "adc_continuous_config");
    ESP_RETURN_ON_ERROR(adc_continuous_start(s_handle),
                        TAG, "adc_continuous_start");

    if (xTaskCreate(reader_task, "cec_adc_rd", READER_TASK_STACK, NULL,
                    READER_TASK_PRIORITY, NULL) != pdPASS) {
        return ESP_FAIL;
    }

    s_started = true;
    ESP_LOGI(TAG, "continuous mode running: %u channels @ %u Hz each (%u Hz total)",
             (unsigned)s_pattern_count, (unsigned)ADC_PER_CHAN_HZ,
             (unsigned)(ADC_PER_CHAN_HZ * s_pattern_count));
    return ESP_OK;
}

esp_err_t cec_adc_read_mv(adc_channel_t channel, int samples, int *out_mv)
{
    (void)samples;  /* see file header */
    if (!s_started)                                        return ESP_ERR_INVALID_STATE;
    if (out_mv == NULL)                                    return ESP_ERR_INVALID_ARG;
    if ((int)channel < 0 || (int)channel >= MAX_CHANNELS)  return ESP_ERR_INVALID_ARG;
    if (!s_channel_seen[channel])                          return ESP_ERR_NOT_FOUND;

    *out_mv = s_latest_mv[channel];
    return ESP_OK;
}

esp_err_t cec_adc_read(const cec_adc_rail_t *rail, float *out_volts)
{
    if (rail == NULL || out_volts == NULL) return ESP_ERR_INVALID_ARG;
    int mv = 0;
    ESP_RETURN_ON_ERROR(cec_adc_read_mv(rail->channel, rail->samples, &mv),
                        TAG, "cec_adc_read_mv");
    *out_volts = (mv / 1000.0f) * rail->scale * rail->trim;
    return ESP_OK;
}

/* ---- eps-lineage API surface, continuous-backend semantics ---- */

esp_err_t cec_adc_pause(void)
{
    /* The continuous backend never hands the unit off; HS capture on
     * this backend reads the same latest-mV table (callback source). */
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t cec_adc_resume(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

bool cec_adc_is_paused(void)
{
    return false;
}

adc_cali_handle_t cec_adc_get_cali_handle(void)
{
    return s_cali;
}

#else /* CONFIG_CEC_ADC_BACKEND_ONESHOT (default) */
/* ======================================================================
 * ONESHOT backend (eps lineage)
 * ====================================================================== */
#include <stdbool.h>
#include "esp_log.h"
#include "esp_check.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "cec_adc.h"

static const char *TAG = "cec_adc";

static adc_oneshot_unit_handle_t s_unit = NULL;
static adc_cali_handle_t s_cali = NULL;
static bool s_inited = false;
static bool s_cali_enabled = false;
static bool s_paused = false;

/* Track every channel ever configured so cec_adc_resume can re-apply
 * the per-channel config after a pause/resume cycle. */
static adc_channel_t s_channels[CEC_ADC_MAX_CHANNELS];
static int           s_channel_count = 0;

static esp_err_t apply_channel(adc_channel_t channel)
{
    adc_oneshot_chan_cfg_t cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    return adc_oneshot_config_channel(s_unit, channel, &cfg);
}

esp_err_t cec_adc_init(void)
{
    if (s_inited) {
        return ESP_OK;
    }

    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&init_cfg, &s_unit),
                        TAG, "adc_oneshot_new_unit");

    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_cali) == ESP_OK) {
        s_cali_enabled = true;
    } else {
        ESP_LOGW(TAG, "ADC calibration unavailable, falling back to nominal scaling");
    }

    s_inited = true;
    s_paused = false;
    ESP_LOGI(TAG, "ADC1 ready (atten=DB_12, cali=%s)",
             s_cali_enabled ? "curve-fit" : "nominal");
    return ESP_OK;
}

esp_err_t cec_adc_setup_channel(adc_channel_t channel)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (s_paused)  return ESP_ERR_INVALID_STATE;

    if (s_channel_count >= CEC_ADC_MAX_CHANNELS) {
        ESP_LOGE(TAG, "channel table full (max %d)", CEC_ADC_MAX_CHANNELS);
        return ESP_ERR_NO_MEM;
    }

    /* Skip if already registered. */
    for (int i = 0; i < s_channel_count; i++) {
        if (s_channels[i] == channel) {
            return apply_channel(channel);
        }
    }
    s_channels[s_channel_count++] = channel;
    return apply_channel(channel);
}

esp_err_t cec_adc_read_mv(adc_channel_t channel, int samples, int *out_mv)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (s_paused)  return ESP_ERR_INVALID_STATE;
    if (out_mv == NULL || samples < 1) return ESP_ERR_INVALID_ARG;

    int32_t sum_mv = 0;
    for (int i = 0; i < samples; i++) {
        int raw = 0;
        ESP_RETURN_ON_ERROR(adc_oneshot_read(s_unit, channel, &raw),
                            TAG, "adc_oneshot_read ch=%d", (int)channel);
        int mv = 0;
        if (s_cali_enabled) {
            ESP_RETURN_ON_ERROR(adc_cali_raw_to_voltage(s_cali, raw, &mv),
                                TAG, "adc_cali_raw_to_voltage");
        } else {
            /* Nominal scaling: 3.1 V full scale at 12-bit / 11dB-atten. */
            mv = (int)((raw * 3100) / 4095);
        }
        sum_mv += mv;
    }
    *out_mv = (int)(sum_mv / samples);
    return ESP_OK;
}

esp_err_t cec_adc_read(const cec_adc_rail_t *rail, float *out_volts)
{
    if (rail == NULL || out_volts == NULL) return ESP_ERR_INVALID_ARG;
    int mv = 0;
    ESP_RETURN_ON_ERROR(cec_adc_read_mv(rail->channel, rail->samples, &mv),
                        TAG, "cec_adc_read_mv");
    *out_volts = (mv / 1000.0f) * rail->scale * rail->trim;
    return ESP_OK;
}

esp_err_t cec_adc_pause(void)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (s_paused)  return ESP_OK;

    esp_err_t ret = adc_oneshot_del_unit(s_unit);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "adc_oneshot_del_unit failed: %s", esp_err_to_name(ret));
        return ret;
    }
    s_unit = NULL;
    s_paused = true;
    ESP_LOGI(TAG, "paused (oneshot released, %d channel(s) remembered)", s_channel_count);
    return ESP_OK;
}

esp_err_t cec_adc_resume(void)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (!s_paused) return ESP_OK;

    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&init_cfg, &s_unit),
                        TAG, "adc_oneshot_new_unit");

    /* Re-apply every previously-configured channel. */
    for (int i = 0; i < s_channel_count; i++) {
        esp_err_t ret = apply_channel(s_channels[i]);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "re-apply channel %d failed: %s",
                     (int)s_channels[i], esp_err_to_name(ret));
            return ret;
        }
    }

    s_paused = false;
    ESP_LOGI(TAG, "resumed (oneshot reacquired, %d channel(s) re-applied)", s_channel_count);
    return ESP_OK;
}

bool cec_adc_is_paused(void)
{
    return s_paused;
}

adc_cali_handle_t cec_adc_get_cali_handle(void)
{
    return s_cali_enabled ? s_cali : NULL;
}

/* ---- 24-pin-lineage API surface, oneshot-backend semantics ---- */

esp_err_t cec_adc_start(void)
{
    /* The oneshot backend has no pattern to apply or reader task to
     * spawn; reads work as soon as a channel is set up. */
    return ESP_OK;
}

#endif /* CEC_ADC_BACKEND */
