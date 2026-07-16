/*
 * cec_adc — shared ADC1 wrapper, one API over two Kconfig-selected
 * backends (firmware consolidation, Phase F2):
 *
 *   CONFIG_CEC_ADC_BACKEND_CONTINUOUS (24-pin lineage)
 *     ADC1 in continuous (DMA) mode at a fixed per-channel rate
 *     (1 kHz); a background reader task keeps a per-channel "latest
 *     calibrated millivolts" table and reads are constant-time,
 *     lock-free lookups — no oneshot conversions, no cross-core ADC
 *     lock contention. `samples` is IGNORED (caller-side EMA/median
 *     does the smoothing). Setup flow: cec_adc_init(); one
 *     cec_adc_setup_channel() per channel; cec_adc_start() — after
 *     which the pattern is locked. cec_adc_pause/resume are
 *     ESP_ERR_NOT_SUPPORTED (the unit is never handed off; HS capture
 *     reads the same table via the callback source).
 *
 *   CONFIG_CEC_ADC_BACKEND_ONESHOT (eps lineage, the default)
 *     adc_oneshot + curve-fit calibration, `samples`-fold averaging
 *     per read, plus the pause/resume hand-off so cec_capture's
 *     adc_continuous HS path can borrow ADC1 and return it (tracked
 *     channels are re-applied on resume; reads return
 *     ESP_ERR_INVALID_STATE while paused). cec_adc_start() is a no-op
 *     (reads work as soon as a channel is set up).
 *
 * All channels live on ADC1 with the same attenuation (ADC_ATTEN_DB_12,
 * ~0-3.1 V usable at the pin).
 */

#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "hal/adc_types.h"
#include "esp_adc/adc_cali.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum number of channels cec_adc tracks (pattern slots on the
 * continuous backend; pause/resume memory on the oneshot backend). */
#define CEC_ADC_MAX_CHANNELS 8

/*
 * Per-channel "rail" descriptor for callers that just want a scaled
 * voltage at a hardware divider. Chip drivers (acs712/acs758,
 * thermistor) do their own post-processing on the raw millivolt result
 * and don't use this.
 */
typedef struct {
    adc_channel_t channel;
    int   samples;            /* Averaging count per read, >= 1 (oneshot
                                 backend); IGNORED on continuous */
    float scale;              /* Hardware divider, V_rail = V_pin * scale */
    float trim;               /* Per-rail calibration trim factor */
} cec_adc_rail_t;

/*
 * One-time ADC1 + curve-fit calibration setup. Idempotent; safe to
 * call before any channel is configured.
 */
esp_err_t cec_adc_init(void);

/*
 * Register/configure a channel. Idempotent. Continuous backend: must
 * precede cec_adc_start (ESP_ERR_INVALID_STATE after). Oneshot
 * backend: configures immediately; remembered across pause/resume.
 */
esp_err_t cec_adc_setup_channel(adc_channel_t channel);

/*
 * Continuous backend: apply the accumulated pattern, start sampling,
 * spawn the reader task (call once after all setup_channel calls).
 * Oneshot backend: no-op, ESP_OK.
 */
esp_err_t cec_adc_start(void);

/*
 * Read the calibrated pin voltage in millivolts. Oneshot backend:
 * averaged over `samples` conversions; ESP_ERR_INVALID_STATE while
 * paused. Continuous backend: latest-table lookup (`samples` ignored);
 * ESP_ERR_NOT_FOUND during the brief startup window before the reader
 * has seen the channel.
 */
esp_err_t cec_adc_read_mv(adc_channel_t channel, int samples, int *out_mv);

/*
 * Read a rail: calibrated mV -> volts via the hardware scale and
 * per-rail trim.
 */
esp_err_t cec_adc_read(const cec_adc_rail_t *rail, float *out_volts);

/*
 * Oneshot backend: release ADC1 so another driver (typically
 * adc_continuous) can take it; reads fail until cec_adc_resume, which
 * re-acquires and re-applies every registered channel. Continuous
 * backend: ESP_ERR_NOT_SUPPORTED.
 */
esp_err_t cec_adc_pause(void);
esp_err_t cec_adc_resume(void);

/* True while paused (oneshot backend); always false on continuous. */
bool cec_adc_is_paused(void);

/*
 * Hand out the curve-fit calibration handle cec_adc owns (NULL if
 * calibration is unavailable). cec_capture's DMA HS path uses it to
 * translate raw DMA samples to mV.
 */
adc_cali_handle_t cec_adc_get_cali_handle(void);

#ifdef __cplusplus
}
#endif
