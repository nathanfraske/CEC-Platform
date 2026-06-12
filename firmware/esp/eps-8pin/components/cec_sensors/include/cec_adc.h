/*
 * Generic ADC oneshot wrapper for the CEC EPS module.
 *
 * Wraps the ESP-IDF 6.x adc_oneshot + adc_cali drivers so the sensor
 * drivers (acs758, ntc) and any future ADC consumer share one
 * curve-fit-calibrated, oversampled read path. All channels live on
 * ADC1 with the same attenuation (ADC_ATTEN_DB_12, ~0-3.1 V usable).
 *
 * Parity with the 24-pin module's cec_adc.h, plus an EPS-only
 * pause/resume hand-off so cec_capture can briefly take the ADC1 unit
 * for adc_continuous DMA capture and return it (continuous and oneshot
 * cannot coexist on the same unit per IDF). Tracked channels are
 * re-applied on resume so callers don't have to re-configure them.
 */

#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum number of channels cec_adc remembers across pause/resume. */
#define CEC_ADC_MAX_CHANNELS 8

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
 * before cec_adc_read_mv / cec_adc_read. The channel is remembered
 * across cec_adc_pause/resume.
 */
esp_err_t cec_adc_setup_channel(adc_channel_t channel);

/*
 * Read the calibrated pin voltage in millivolts, averaged over
 * `samples` raw conversions. Used by sensor drivers whose
 * post-processing isn't a simple linear divider scale (acs758, ntc).
 *
 * Returns ESP_ERR_INVALID_STATE while cec_adc is paused (a continuous-
 * mode consumer holds ADC1).
 */
esp_err_t cec_adc_read_mv(adc_channel_t channel, int samples, int *out_mv);

/*
 * Read a rail. Averages `rail->samples` raw conversions, applies the
 * curve-fit calibration, then the hardware scale and per-rail trim.
 * Returns the final voltage in volts.
 */
esp_err_t cec_adc_read(const cec_adc_rail_t *rail, float *out_volts);

/*
 * Release ADC1 from the oneshot driver so another driver (typically
 * adc_continuous) can take it. cec_adc_read_mv returns
 * ESP_ERR_INVALID_STATE until cec_adc_resume.
 */
esp_err_t cec_adc_pause(void);

/*
 * Re-acquire ADC1 for oneshot use and re-apply every channel that was
 * previously registered with cec_adc_setup_channel. After resume the
 * oneshot read path is usable again.
 */
esp_err_t cec_adc_resume(void);

/*
 * Returns true if cec_adc is currently paused (oneshot path unusable).
 */
bool cec_adc_is_paused(void);

/*
 * Hand out the curve-fit calibration handle that cec_adc owns. The
 * cec_capture HS path needs it to translate raw DMA samples to mV.
 * Returns NULL if calibration is unavailable.
 */
adc_cali_handle_t cec_adc_get_cali_handle(void);

#ifdef __cplusplus
}
#endif
