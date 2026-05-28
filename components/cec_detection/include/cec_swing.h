/*
 * Windowed swing detector.
 *
 * Ring buffer of the last `capacity` samples plus a running sum so
 * the window mean is available in O(1). On each update the caller
 * supplies the latest value and a threshold; the detector computes
 * |value - mean| and fires when that swing exceeds the threshold for
 * `required_consecutive` samples in a row. The window doesn't fire
 * until it's full so the mean is meaningful.
 *
 * Threshold computation lives at the call site (the 24-pin uses
 * max(MIN_W, FRACTION * mean) for power and a fixed value for
 * per-rail current). Buffer is caller-owned - no heap allocation.
 *
 * Parity primitive with the 24-pin module's cec_swing.h. Not yet
 * wired into EPS's cec_detection_run; available for callers that
 * want sustained-shift detection in addition to the rate-of-change
 * cec_layer2.
 */

#pragma once

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float *buf;
    size_t capacity;
    size_t idx;
    size_t count;
    float  sum;
    int    consecutive_count;
    int    required_consecutive;
} cec_swing_detector_t;

void cec_swing_detector_init(cec_swing_detector_t *d, float *buf,
                             size_t capacity, int required_consecutive);

/*
 * Push value, return true the iteration when the consecutive counter
 * reaches its limit. Counter resets on fire so a single sustained
 * swing produces exactly one fire event. Caller typically follows up
 * with cec_swing_detector_reset_to so the post-fire baseline starts
 * from the current operating point.
 *
 * Doesn't fire until the window is full.
 */
bool cec_swing_detector_update(cec_swing_detector_t *d,
                               float value, float threshold);

float  cec_swing_detector_mean(const cec_swing_detector_t *d);
bool   cec_swing_detector_is_full(const cec_swing_detector_t *d);
size_t cec_swing_detector_count(const cec_swing_detector_t *d);

/* Pre-fill the window with `value`. Use after a fire so subsequent
 * checks compare against the new baseline instead of the pre-fire
 * window. */
void cec_swing_detector_reset_to(cec_swing_detector_t *d, float value);

/* Empty the window. Use on state-up transitions so pre-transition
 * (typically near-zero) samples don't pollute the new state's mean. */
void cec_swing_detector_reset_empty(cec_swing_detector_t *d);

#ifdef __cplusplus
}
#endif
