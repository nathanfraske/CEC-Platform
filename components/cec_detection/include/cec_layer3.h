/*
 * Layer 3 statistical baseline.
 *
 * 24-pin parity: same architectural role as the 24-pin's cec_layer3
 * (long-horizon statistical baseline for the load classifier and for
 * detecting drift from learned-normal behavior).
 *
 * EPS-specific implementation: an EMA of (raw - filtered)^2, giving a
 * running variance estimate. This is rudimentary compared to the
 * 24-pin's cec_rail_profile_t with mean + std + warm-sample gating +
 * z-score; the EPS variance is just a noisiness gauge fed into the
 * load classifier (CEC_LOAD_TRANSIENT when variance is high).
 *
 * TODO: upgrade to a full mean+std profile with warm-up and z-score
 * (parity with cec_rail_profile_t) once EPS calibration and dwell
 * times are characterized.
 */

#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float variance_est;   /* EMA of (instant - smoothed)^2 */
    float alpha;          /* EMA weight; 0.1 is the v0.5.9 default */
} cec_layer3_detector_t;

void  cec_layer3_init(cec_layer3_detector_t *d, float alpha);

/*
 * Feed an (instant, smoothed) pair. Returns the updated variance
 * estimate. instant is the raw sample; smoothed is the filtered value
 * (median+EMA). The deviation (instant - smoothed) is the noise content
 * once steady-state is established.
 */
float cec_layer3_update(cec_layer3_detector_t *d, float instant, float smoothed);

float cec_layer3_variance(const cec_layer3_detector_t *d);

void  cec_layer3_reset(cec_layer3_detector_t *d);

#ifdef __cplusplus
}
#endif
