/*
 * ACS758 Hall-effect current sensor driver.
 */

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_check.h"
#include "cec_adc.h"
#include "acs758.h"

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
    if (ctx == NULL) return ESP_ERR_INVALID_ARG;

    ctx->samples = 16;
    for (int i = 0; i < ACS758_NUM_SENSORS; i++) {
        ctx->channels[i]              = SENSOR_CHANNELS[i];
        ctx->cal[i].zero_offset_v     = 0.0f;
        // quiescent_v / sensitivity_v_a are set by acs758_set_supply()
        // below; caller may override with the measured Vcc.
        ESP_RETURN_ON_ERROR(cec_adc_setup_channel(ctx->channels[i]),
                            TAG, "setup channel %d", i);
    }

    // Default to nominal 5 V supply; the caller should override via
    // acs758_set_supply() with the actual measured Vcc.
    acs758_set_supply(ctx, ACS758_NOMINAL_VCC);

    ESP_LOGI(TAG, "initialized %d sensors", ACS758_NUM_SENSORS);
    return ESP_OK;
}

void acs758_set_supply(acs758_ctx_t *ctx, float vcc)
{
    if (ctx == NULL) return;
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
    if (ctx == NULL || sensor < 0 || sensor >= ACS758_NUM_SENSORS) return;
    ctx->cal[sensor].zero_offset_v = offset_v;
}

esp_err_t acs758_read_adc_voltage(acs758_ctx_t *ctx, int sensor, float *out_v)
{
    if (ctx == NULL || out_v == NULL) return ESP_ERR_INVALID_ARG;
    if (sensor < 0 || sensor >= ACS758_NUM_SENSORS) return ESP_ERR_INVALID_ARG;

    int mv = 0;
    ESP_RETURN_ON_ERROR(cec_adc_read_mv(ctx->channels[sensor], ctx->samples, &mv),
                        TAG, "cec_adc_read_mv");
    *out_v = mv / 1000.0f;
    return ESP_OK;
}

esp_err_t acs758_read_chip_voltage(acs758_ctx_t *ctx, int sensor, float *out_v)
{
    if (out_v == NULL) return ESP_ERR_INVALID_ARG;
    float v_adc = 0.0f;
    esp_err_t ret = acs758_read_adc_voltage(ctx, sensor, &v_adc);
    if (ret != ESP_OK) return ret;
    *out_v = v_adc * ACS758_DIVIDER_GAIN;
    return ESP_OK;
}

float acs758_read_current(acs758_ctx_t *ctx, int sensor)
{
    if (ctx == NULL || sensor < 0 || sensor >= ACS758_NUM_SENSORS) return 0.0f;
    float v_chip = 0.0f;
    if (acs758_read_chip_voltage(ctx, sensor, &v_chip) != ESP_OK) return 0.0f;
    const acs758_cal_t *c = &ctx->cal[sensor];
    if (c->sensitivity_v_a == 0.0f) return 0.0f;  // belt-and-suspenders
    float v_signal = v_chip - c->quiescent_v - c->zero_offset_v;
    return v_signal / c->sensitivity_v_a;
}

float acs758_calibrate_zero(acs758_ctx_t *ctx, int sensor)
{
    if (ctx == NULL || sensor < 0 || sensor >= ACS758_NUM_SENSORS) return 0.0f;

    const int N = 256;
    double sum_v = 0.0;
    for (int i = 0; i < N; i++) {
        float v = 0.0f;
        if (acs758_read_chip_voltage(ctx, sensor, &v) != ESP_OK) {
            return 0.0f;
        }
        sum_v += v;
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    float avg_chip_v = (float)(sum_v / N);

    // Offset is the deviation of the measured zero-current output from
    // the expected ratiometric quiescent.
    float offset = avg_chip_v - ctx->cal[sensor].quiescent_v;
    ctx->cal[sensor].zero_offset_v = offset;

    ESP_LOGI(TAG, "sensor %d zero cal: chip=%.4fV quiescent=%.4fV offset=%.4fV",
             sensor, avg_chip_v, ctx->cal[sensor].quiescent_v, offset);
    return offset;
}

void acs758_calibrate_span(acs758_ctx_t *ctx, int sensor, float known_current_a)
{
    if (ctx == NULL || sensor < 0 || sensor >= ACS758_NUM_SENSORS) return;
    if (known_current_a == 0.0f) {
        ESP_LOGW(TAG, "span cal needs nonzero current");
        return;
    }

    const int N = 256;
    double sum_v = 0.0;
    for (int i = 0; i < N; i++) {
        float v = 0.0f;
        if (acs758_read_chip_voltage(ctx, sensor, &v) != ESP_OK) {
            return;
        }
        sum_v += v;
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
