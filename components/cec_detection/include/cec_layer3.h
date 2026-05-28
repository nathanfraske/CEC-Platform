/*
 * Layer 3 statistical baseline (rail profile).
 *
 * Parity primitive with the 24-pin module's cec_layer3.h
 * cec_rail_profile_t. Tracks a running mean and std-deviation estimate
 * for a single signal with dual adaptation rates: a fast initial ramp
 * for the first ~CEC_PROFILE_FAST_SAMPLES samples so the estimate
 * converges quickly after a state change or boot, then settles into a
 * slow caller-supplied adapt rate so genuine anomalies don't pollute
 * the baseline.
 *
 * A profile is "warm" after CEC_PROFILE_WARM_SAMPLES samples; z_score
 * returns 0 before that so anomaly detection doesn't fire during
 * warm-up.
 *
 * Used on EPS as the per-cable, per-load-state noise/std baseline for
 * the classifier (high std_dev -> CEC_LOAD_TRANSIENT) and for
 * z-score-based anomaly detection on the filtered current stream.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Sample count above which the profile is "warm" and z-scores are
 * trustworthy. At 50 Hz, 1000 samples = 20 seconds before the profile
 * starts emitting anomaly signals. */
#define CEC_PROFILE_WARM_SAMPLES  1000U

/* Sample count below which the fast initial adapt rate (0.01) is used
 * instead of the caller-supplied slow rate, so the profile converges
 * quickly on first entry. */
#define CEC_PROFILE_FAST_SAMPLES  100U

typedef struct {
    float    mean;
    float    std_dev;
    uint32_t sample_count;
} cec_rail_profile_t;

/* Initialize. All fields zeroed; profile is unwarmed. */
void cec_rail_profile_init(cec_rail_profile_t *p);

/* Feed a sample. `adapt_rate` is the steady-state EMA weight used
 * after the fast-ramp window (typ 0.0005 -> ~2000-sample effective
 * window). */
void cec_rail_profile_update(cec_rail_profile_t *p, float x, float adapt_rate);

/* True once enough samples have accumulated to trust the estimate. */
bool cec_rail_profile_is_warm(const cec_rail_profile_t *p);

/* Standard-deviation distance of `x` from the learned mean. Returns 0
 * if the profile isn't warm yet or if std_dev is too small to be
 * numerically meaningful (avoids div-by-zero and huge junk values
 * from a perfectly quiet rail). */
float cec_rail_profile_z_score(const cec_rail_profile_t *p, float x);

#ifdef __cplusplus
}
#endif
