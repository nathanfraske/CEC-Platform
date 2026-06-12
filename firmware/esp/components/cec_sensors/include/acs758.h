/*
 * ACS758 Hall-effect current sensor driver.
 *
 * Outputs an analog voltage centered on Vcc/2 at no load, deviating
 * linearly with current. On this board the output passes through a
 * 2:3 divider (R1=10K top, R2=20K bottom) before reaching the ADC pin,
 * so the read path is:
 *
 *   v_pin  = v_chip * (2/3)
 *   v_chip = v_pin  * 1.5          // recover sensor output
 *   I      = (v_chip - quiescent - zero_offset) / sensitivity
 *
 * Sensitivity is ratiometric (40 mV/A at 5.0 V nominal); both the
 * sensitivity and the Vcc/2 quiescent scale with the actual supply
 * voltage, which is set at startup via acs758_set_supply().
 *
 * Zero offset needs per-unit calibration (typical part-to-part
 * quiescent variation is several tens of mV, which is hundreds of mA
 * at this sensitivity). acs758_calibrate_zero() runs the cal with no
 * current flowing; the resulting offset is loaded from / saved to NVS
 * at the cec_config layer.
 *
 * Reads go through cec_adc_read_mv so the ADC calibration and
 * oversampling are shared with the rest of the sensor stack.
 */

#pragma once

#include "esp_err.h"
#include "hal/adc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ACS758_NUM_SENSORS    2

// Voltage divider: 2:3 ratio (R1=10K top, R2=20K bottom).
// ADC sees VIOUT * 2/3, so multiply by 1.5 to recover the chip output.
#define ACS758_DIVIDER_GAIN   1.5f

// Nominal sensor constants (datasheet, at 5.0V supply).
// These scale ratiometrically with actual supply voltage.
#define ACS758_NOMINAL_SENS   0.040f   // V/A at 5.0V
#define ACS758_NOMINAL_VCC    5.0f

// Per-sensor calibration values. Mutable - calibration routines and the
// NVS-load path update these in place.
typedef struct {
    float quiescent_v;       // zero-current chip output (= Vcc/2)
    float sensitivity_v_a;   // V per A (ratiometric: scales with Vcc)
    float zero_offset_v;     // fine trim from zero calibration
} acs758_cal_t;

typedef struct {
    adc_channel_t channels[ACS758_NUM_SENSORS];
    acs758_cal_t  cal[ACS758_NUM_SENSORS];
    int           samples;   // averaging count per cec_adc_read_mv call
} acs758_ctx_t;

/*
 * Configure both sensor channels on cec_adc and initialize the
 * calibration state. cec_adc_init() must have been called first.
 */
esp_err_t acs758_init(acs758_ctx_t *ctx);

/*
 * Set the supply voltage; recomputes quiescent and sensitivity
 * ratiometrically for both sensors. Call with the measured Vcc (e.g.
 * 4.4 V from the dev board's USB-Vbus rail).
 */
void acs758_set_supply(acs758_ctx_t *ctx, float vcc);

/*
 * Set a per-sensor zero offset (volts at the chip output). Typically
 * loaded from NVS at boot, or written by acs758_calibrate_zero.
 */
void acs758_set_zero_offset(acs758_ctx_t *ctx, int sensor, float offset_v);

/*
 * Voltage at the ADC pin in volts.
 */
esp_err_t acs758_read_adc_voltage(acs758_ctx_t *ctx, int sensor, float *out_v);

/*
 * Recovered chip output voltage in volts (= adc_voltage * divider gain).
 */
esp_err_t acs758_read_chip_voltage(acs758_ctx_t *ctx, int sensor, float *out_v);

/*
 * Calibrated current in amps. Returns 0.0 on bad sensor index or read
 * failure; check the return separately if exact error handling matters.
 */
float acs758_read_current(acs758_ctx_t *ctx, int sensor);

/*
 * Run zero-offset calibration for one sensor. Ensure NO current flows
 * (PSU off, or PSU on with motherboard off so EPS cables carry no load).
 * Averages many samples and stores the offset in ctx->cal[sensor].
 * Returns the computed offset (volts).
 */
float acs758_calibrate_zero(acs758_ctx_t *ctx, int sensor);

/*
 * Span calibration: with a known current flowing, compute and store the
 * actual sensitivity for one sensor. Improves accuracy beyond the
 * ratiometric estimate.
 */
void acs758_calibrate_span(acs758_ctx_t *ctx, int sensor, float known_current_a);

#ifdef __cplusplus
}
#endif
