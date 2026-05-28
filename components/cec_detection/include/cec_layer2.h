/*
 * Layer 2 fast-transient detector.
 *
 * 24-pin parity: same architectural role as the 24-pin's cec_layer2
 * (catch fast anomalies that the static-threshold Layer 1 misses).
 *
 * EPS-specific algorithm: rate-of-change (dI/dt) on the raw current
 * stream. The 24-pin uses an adaptive |instant - ema| > k_sigma*std
 * detector instead, because voltage rails have a stable expected mean
 * and the interesting anomaly is a deviation from that mean. EPS-side
 * the cable current legitimately swings as the CPU load steps, so a
 * rate threshold (not a magnitude threshold) is the right primitive.
 *
 * Fires when |current - last_value| / dt_ms > threshold_a_per_ms.
 * One sample is enough to fire (no debounce yet); the dt_ms gating
 * already filters out trivial sample-to-sample jitter.
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float    last_value;
    int64_t  last_time_us;
    float    threshold_a_per_ms;
    bool     primed;
} cec_layer2_detector_t;

/*
 * Configure with the maximum allowable rate of change in A/ms.
 * v0.5.9 default is 1.0 (= 10 A in 10 ms).
 */
void cec_layer2_init(cec_layer2_detector_t *d, float threshold_a_per_ms);

/*
 * Feed an instantaneous current sample with its timestamp. Returns true
 * the iteration the rate-of-change exceeds the threshold.
 */
bool cec_layer2_update(cec_layer2_detector_t *d, float current_a, int64_t now_us);

/*
 * Clear the primed flag so the next update establishes a fresh baseline.
 * Use during state-up transitions where the first samples may be from a
 * different operating point.
 */
void cec_layer2_reset(cec_layer2_detector_t *d);

#ifdef __cplusplus
}
#endif
