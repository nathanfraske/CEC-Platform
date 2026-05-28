#pragma once

#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include <stdbool.h>

#define ACS758_NUM_SENSORS 2

// Voltage divider: 2:3 ratio (R1=10K top, R2=20K bottom).
// ADC sees VIOUT * 2/3, so multiply by 1.5 to recover the chip output.
#define ACS758_DIVIDER_GAIN   1.5f

// Nominal sensor constants (datasheet, at 5.0V supply).
// These scale ratiometrically with actual supply voltage.
#define ACS758_NOMINAL_SENS   0.040f   // V/A at 5.0V
#define ACS758_NOMINAL_VCC    5.0f

// Per-sensor calibration
typedef struct {
    float quiescent_v;       // zero-current chip output (= Vcc/2)
    float sensitivity_v_a;   // V per A (ratiometric: scales with Vcc)
    float zero_offset_v;     // fine trim from zero calibration
} acs758_cal_t;

typedef struct {
    adc_oneshot_unit_handle_t adc;
    adc_cali_handle_t cali;
    bool cali_enabled;
    adc_channel_t channels[ACS758_NUM_SENSORS];
    acs758_cal_t cal[ACS758_NUM_SENSORS];
    int oversample;          // samples averaged per read (default 16)
} acs758_ctx_t;

// Initialize ADC1 and configure the sensor channels.
esp_err_t acs758_init(acs758_ctx_t *ctx);

// Set the supply voltage; recomputes quiescent and sensitivity ratiometrically
// for all sensors. Call with the measured Vcc (e.g. 4.4V from the dev board).
void acs758_set_supply(acs758_ctx_t *ctx, float vcc);

// Set a per-sensor zero offset (volts at the chip output). Applied on top of
// the ratiometric quiescent. Typically loaded from NVS or set by calibration.
void acs758_set_zero_offset(acs758_ctx_t *ctx, int sensor, float offset_v);

// Raw ADC count (oversampled).
int acs758_read_raw(acs758_ctx_t *ctx, int sensor);

// Voltage at the ADC pin (volts), using ESP-IDF calibration if available.
float acs758_read_adc_voltage(acs758_ctx_t *ctx, int sensor);

// Recovered chip output voltage (volts), = adc_voltage * divider gain.
float acs758_read_chip_voltage(acs758_ctx_t *ctx, int sensor);

// Calibrated current (amps).
float acs758_read_current(acs758_ctx_t *ctx, int sensor);

// Run zero-offset calibration for one sensor. Ensure NO current flows.
// Averages many samples and stores the offset in ctx->cal[sensor].zero_offset_v.
// Returns the computed offset (volts).
float acs758_calibrate_zero(acs758_ctx_t *ctx, int sensor);

// Span calibration: with a known current flowing, compute and store the actual
// sensitivity for one sensor. Improves accuracy beyond the ratiometric estimate.
void acs758_calibrate_span(acs758_ctx_t *ctx, int sensor, float known_current_a);
