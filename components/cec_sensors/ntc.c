#include "ntc.h"
#include "esp_log.h"
#include <math.h>

static const char *TAG = "ntc";

#define NTC_CHANNEL  ADC_CHANNEL_6   // GPIO 7
#define NTC_OVERSAMPLE 8

esp_err_t ntc_init(ntc_ctx_t *ctx, adc_oneshot_unit_handle_t adc,
                   adc_cali_handle_t cali, bool cali_enabled)
{
    ctx->adc = adc;
    ctx->cali = cali;
    ctx->cali_enabled = cali_enabled;
    ctx->channel = NTC_CHANNEL;

    // Typical 10K NTC defaults; adjust to match the daughterboard parts.
    ctx->beta        = 3950.0f;
    ctx->r_nominal   = 10000.0f;
    ctx->t_nominal_k = 298.15f;   // 25 C
    ctx->r_series    = 10000.0f;  // series resistor in the divider
    ctx->vref        = 3.3f;

    adc_oneshot_chan_cfg_t ch_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    esp_err_t ret = adc_oneshot_config_channel(ctx->adc, ctx->channel, &ch_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "channel config failed: %s", esp_err_to_name(ret));
    }
    return ret;
}

float ntc_read_celsius(ntc_ctx_t *ctx)
{
    int64_t sum = 0;
    for (int i = 0; i < NTC_OVERSAMPLE; i++) {
        int raw = 0;
        adc_oneshot_read(ctx->adc, ctx->channel, &raw);
        sum += raw;
    }
    int raw_avg = (int)(sum / NTC_OVERSAMPLE);

    float v_adc;
    if (ctx->cali_enabled) {
        int mv = 0;
        adc_cali_raw_to_voltage(ctx->cali, raw_avg, &mv);
        v_adc = mv / 1000.0f;
    } else {
        v_adc = raw_avg * (3.1f / 4095.0f);
    }

    // Divider: Vref -- R_series -- node(ADC) -- NTC -- GND
    // (adjust if your NTC divider is wired the other way)
    if (v_adc <= 0.001f || v_adc >= ctx->vref) {
        return -273.15f;  // sentinel: open or shorted
    }
    float r_ntc = ctx->r_series * (v_adc / (ctx->vref - v_adc));

    // Beta equation
    float steinhart = logf(r_ntc / ctx->r_nominal) / ctx->beta;
    steinhart += 1.0f / ctx->t_nominal_k;
    float temp_k = 1.0f / steinhart;
    return temp_k - 273.15f;
}
