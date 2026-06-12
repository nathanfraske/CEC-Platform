/*
 * Layer 2 fast-transient detector — dual-mode merge (firmware
 * consolidation, Phase E). Same architectural role in both apps (catch
 * fast anomalies the static Layer 1 misses); two algorithms because the
 * underlying signals differ. Board-specific thresholds live in each
 * app's cec_config (never in this component).
 *
 *   ADAPTIVE mode (24-pin lineage): watches the deviation between an
 *   instantaneous (or lightly-filtered) reading and its slow EMA. The
 *   detection threshold is adaptive: it scales with a running variance
 *   estimate of the deviation, so a rail that's normally noisy gets a
 *   wide threshold and a quiet rail gets a tight one; a configurable
 *   floor keeps a perfectly quiet rail detectable. The variance
 *   estimator only updates on samples that are NOT firing, so a
 *   transient doesn't widen its own threshold. Fires when
 *   |instant - ema| > max(min_threshold, k_sigma * std) for
 *   required_consecutive samples in a row. Voltage rails have a stable
 *   expected mean, so deviation-from-mean is the right primitive.
 *
 *   RATE mode (eps lineage): rate-of-change (dI/dt) on the raw current
 *   stream. Cable current legitimately swings as the CPU load steps,
 *   so a rate threshold (not a magnitude threshold) is the right
 *   primitive there. Fires when |current - last| / dt_ms exceeds
 *   threshold_a_per_ms; one sample is enough (no debounce), the dt_ms
 *   gating already filters trivial sample-to-sample jitter.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CEC_L2_MODE_ADAPTIVE = 0,   /* |instant - ema| vs adaptive sigma threshold */
    CEC_L2_MODE_RATE,           /* |d(value)/dt| vs fixed rate threshold */
} cec_layer2_mode_t;

typedef struct {
    cec_layer2_mode_t mode;

    /* ADAPTIVE mode */
    float min_threshold;        /* Floor for the adaptive threshold */
    float k_sigma;              /* Multiplier on running std (typ 5.0) */
    int   required_consecutive; /* Debounce, typ 3 */
    int   consecutive_count;    /* Internal: running fire counter */
    float variance_est;         /* Internal: running variance estimate */
    bool  initialized;          /* Internal: first-sample flag */

    /* RATE mode */
    float    last_value;
    int64_t  last_time_us;
    float    threshold_a_per_ms;
    bool     primed;
} cec_layer2_detector_t;

/*
 * Configure an ADAPTIVE-mode detector (24-pin lineage).
 * `required_consecutive` is clamped to >= 1.
 */
void cec_layer2_init_adaptive(cec_layer2_detector_t *d,
                              float min_threshold,
                              float k_sigma,
                              int   required_consecutive);

/*
 * Configure a RATE-mode detector (eps lineage) with the maximum
 * allowable rate of change in A/ms. v0.5.9 default is 1.0
 * (= 10 A in 10 ms).
 */
void cec_layer2_init_rate(cec_layer2_detector_t *d, float threshold_a_per_ms);

/*
 * ADAPTIVE mode: feed the instantaneous reading and its slow EMA.
 * Returns true when the detector fires. On a failed sensor read, feed
 * the EMA value as the instant too (or skip the update) — a raw 0.0
 * against a held EMA reads as a huge spurious deviation.
 */
bool cec_layer2_update_adaptive(cec_layer2_detector_t *d,
                                float instant, float ema);

/*
 * RATE mode: feed the raw value and its esp_timer timestamp. Returns
 * true when |d(value)/dt| exceeds the configured rate.
 */
bool cec_layer2_update_rate(cec_layer2_detector_t *d,
                            float value, int64_t now_us);

/*
 * Reset transient state (mode-aware): the consecutive counter in
 * ADAPTIVE mode, the primed flag in RATE mode. Config is preserved.
 */
void cec_layer2_reset(cec_layer2_detector_t *d);

/*
 * ADAPTIVE mode: the currently effective threshold,
 * max(min_threshold, k_sigma * std). Diagnostic.
 */
float cec_layer2_current_threshold(const cec_layer2_detector_t *d);

#ifdef __cplusplus
}
#endif
