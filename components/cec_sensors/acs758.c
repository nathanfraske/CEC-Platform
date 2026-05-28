#include "acs758.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "acs758";

// Channel assignments for the EPS refboard:
//   ACS758 #1 -> GPIO 6  -> ADC1_CH5
//   ACS758 #2 -> GPIO 10 -> ADC1_CH9
static const adc_channel_t SENSOR_CHANNELS[ACS758_NUM_SENSORS] = {
    ADC_CHANNEL_5,   // GPIO 6
    ADC_CHANNEL_9,   // GPIO 10
};

esp_err_t acs758_init(acs758_ctx_t *ctx)
{
    ctx->oversample = 16;
    ctx->cali_enabled = false;
    for (int i = 0; i < ACS758_NUM_SENSORS; i++) {
        ctx->cal[i].zero_offset_v = 0.0f;
    }

    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t ret = adc_oneshot_new_unit(&init_cfg, &ctx->adc);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "adc unit init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    adc_oneshot_chan_cfg_t ch_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,    // ~0-3.1V input range
    };

    for (int i = 0; i < ACS758_NUM_SENSORS; i++) {
        ctx->channels[i] = SENSOR_CHANNELS[i];
        ret = adc_oneshot_config_channel(ctx->adc, ctx->channels[i], &ch_cfg);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "channel %d config failed: %s", i, esp_err_to_name(ret));
            return ret;
        }
    }

    // Curve-fitting calibration scheme for accurate voltage readings.
    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_curve_fitting(&cali_cfg, &ctx->cali) == ESP_OK) {
        ctx->cali_enabled = true;
        ESP_LOGI(TAG, "ADC calibration scheme enabled");
    } else {
        ESP_LOGW(TAG, "ADC calibration unavailable, using nominal scaling");
    }

    // Default to nominal 5V supply; the caller should override via
    // acs758_set_supply() with the measured Vcc.
    acs758_set_supply(ctx, ACS758_NOMINAL_VCC);

    ESP_LOGI(TAG, "initialized %d sensors", ACS758_NUM_SENSORS);
    return ESP_OK;
}

void acs758_set_supply(acs758_ctx_t *ctx, float vcc)
{
    for (int i = 0; i < ACS758_NUM_SENSORS; i++) {
        ctx->cal[i].quiescent_v     = vcc * 0.5f;
        ctx->cal[i].sensitivity_v_a = ACS758_NOMINAL_SENS * (vcc / ACS758_NOMINAL_VCC);
        // zero_offset_v is preserved (set separately by calibration / NVS)
    }
    ESP_LOGI(TAG, "supply set to %.2fV -> quiescent %.3fV, sensitivity %.4f V/A",
             vcc, vcc * 0.5f, ACS758_NOMINAL_SENS * (vcc / ACS758_NOMINAL_VCC));
}

void acs758_set_zero_offset(acs758_ctx_t *ctx, int sensor, float offset_v)
{
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return;
    ctx->cal[sensor].zero_offset_v = offset_v;
}

int acs758_read_raw(acs758_ctx_t *ctx, int sensor)
{
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return 0;
    int64_t sum = 0;
    for (int i = 0; i < ctx->oversample; i++) {
        int raw = 0;
        adc_oneshot_read(ctx->adc, ctx->channels[sensor], &raw);
        sum += raw;
    }
    return (int)(sum / ctx->oversample);
}

float acs758_read_adc_voltage(acs758_ctx_t *ctx, int sensor)
{
    int raw = acs758_read_raw(ctx, sensor);
    if (ctx->cali_enabled) {
        int mv = 0;
        adc_cali_raw_to_voltage(ctx->cali, raw, &mv);
        return mv / 1000.0f;
    }
    // Fallback: nominal scaling (3.1V full scale at 11dB atten)
    return raw * (3.1f / 4095.0f);
}

float acs758_read_chip_voltage(acs758_ctx_t *ctx, int sensor)
{
    return acs758_read_adc_voltage(ctx, sensor) * ACS758_DIVIDER_GAIN;
}

float acs758_read_current(acs758_ctx_t *ctx, int sensor)
{
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return 0.0f;
    float v_chip = acs758_read_chip_voltage(ctx, sensor);
    acs758_cal_t *c = &ctx->cal[sensor];
    float v_signal = v_chip - c->quiescent_v - c->zero_offset_v;
    return v_signal / c->sensitivity_v_a;
}

float acs758_calibrate_zero(acs758_ctx_t *ctx, int sensor)
{
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return 0.0f;

    const int N = 256;
    double sum_v = 0.0;
    for (int i = 0; i < N; i++) {
        sum_v += acs758_read_chip_voltage(ctx, sensor);
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    float avg_chip_v = (float)(sum_v / N);

    // The offset is the deviation of the measured zero-current output from
    // the expected ratiometric quiescent.
    float offset = avg_chip_v - ctx->cal[sensor].quiescent_v;
    ctx->cal[sensor].zero_offset_v = offset;

    ESP_LOGI(TAG, "sensor %d zero cal: chip=%.4fV quiescent=%.4fV offset=%.4fV",
             sensor, avg_chip_v, ctx->cal[sensor].quiescent_v, offset);
    return offset;
}

void acs758_calibrate_span(acs758_ctx_t *ctx, int sensor, float known_current_a)
{
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return;
    if (known_current_a == 0.0f) {
        ESP_LOGW(TAG, "span cal needs nonzero current");
        return;
    }

    const int N = 256;
    double sum_v = 0.0;
    for (int i = 0; i < N; i++) {
        sum_v += acs758_read_chip_voltage(ctx, sensor);
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    float avg_chip_v = (float)(sum_v / N);

    // sensitivity = (V_measured - quiescent - offset) / I_known
    acs758_cal_t *c = &ctx->cal[sensor];
    float v_signal = avg_chip_v - c->quiescent_v - c->zero_offset_v;
    float new_sens = v_signal / known_current_a;
    c->sensitivity_v_a = new_sens;

    ESP_LOGI(TAG, "sensor %d span cal at %.2fA: sensitivity=%.4f V/A",
             sensor, known_current_a, new_sens);
}
