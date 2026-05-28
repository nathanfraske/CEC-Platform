/*
 * Generic ADC oneshot wrapper for the CEC EPS module.
 *
 * Wraps the ESP-IDF 6.x adc_oneshot + adc_cali drivers so the sensor
 * drivers (acs758, ntc) and any future ADC consumer share one
 * curve-fit-calibrated, oversampled read path. All channels live on
 * ADC1 with the same attenuation (ADC_ATTEN_DB_12, ~0-3.1 V usable).
 *
 * Parity with the 24-pin module's cec_adc.h.
 */

#pragma once

#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Per-channel "rail" descriptor for callers that just want a scaled
 * voltage at a hardware divider. acs758 / ntc do their own
 * post-processing on the raw millivolt result and don't use this.
 */
typedef struct {
    adc_channel_t channel;   /* ADC1 channel (CH0..CH9 on ESP32-S3) */
    int   samples;           /* Averaging count per read, >= 1 */
    float scale;             /* Hardware divider, V_rail = V_pin * scale */
    float trim;              /* Per-rail calibration trim (1.0 = no trim) */
} cec_adc_rail_t;

/*
 * One-time ADC1 + curve-fit calibration setup. Idempotent; safe to
 * call before any channel is configured.
 */
esp_err_t cec_adc_init(void);

/*
 * Configure a single ADC1 channel. Must be called once per channel
 * before cec_adc_read_mv / cec_adc_read.
 */
esp_err_t cec_adc_setup_channel(adc_channel_t channel);

/*
 * Read the calibrated pin voltage in millivolts, averaged over
 * `samples` raw conversions. Used by sensor drivers whose
 * post-processing isn't a simple linear divider scale (acs758, ntc).
 */
esp_err_t cec_adc_read_mv(adc_channel_t channel, int samples, int *out_mv);

/*
 * Read a rail. Averages `rail->samples` raw conversions, applies the
 * curve-fit calibration, then the hardware scale and per-rail trim.
 * Returns the final voltage in volts.
 */
esp_err_t cec_adc_read(const cec_adc_rail_t *rail, float *out_volts);

#ifdef __cplusplus
}
#endif
