/*
 * Generic ADC oneshot wrapper.
 */

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
