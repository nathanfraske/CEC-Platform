#pragma once

#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"

// NTC on GPIO 7 -> ADC1_CH6 (via daughterboard).
// Shares the ADC unit handle with the ACS758 driver.

typedef struct {
    adc_oneshot_unit_handle_t adc;   // shared with acs758
    adc_cali_handle_t cali;
    bool cali_enabled;
    adc_channel_t channel;
    // NTC + divider parameters
    float beta;          // NTC beta coefficient
    float r_nominal;     // NTC resistance at nominal temp (ohms)
    float t_nominal_k;   // nominal temp (kelvin), usually 298.15 (25C)
    float r_series;      // series resistor in the divider (ohms)
    float vref;          // top of divider (3.3V)
} ntc_ctx_t;

// Initialize using an already-created ADC unit + calibration handle
// (pass the handles from acs758_ctx_t to share the ADC1 unit).
esp_err_t ntc_init(ntc_ctx_t *ctx, adc_oneshot_unit_handle_t adc,
                   adc_cali_handle_t cali, bool cali_enabled);

// Read board temperature in degrees Celsius.
float ntc_read_celsius(ntc_ctx_t *ctx);
