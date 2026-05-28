/*
 * Per-cable load classifier.
 *
 * Maps (current_a, variance) to a coarse cec_load_state_t. Parity with
 * the 24-pin's cec_state.c shape (a stateless classify function) but
 * with EPS-specific bands (per-cable load level, not whole-PSU
 * operating mode).
 */

#pragma once

#include "cec_state.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Classify the current load level given the latest filtered current
 * (amps) and the per-cable noise std-deviation from the Layer 3 rail
 * profile (amps RMS). High std overrides the magnitude bucketing and
 * returns CEC_LOAD_TRANSIENT.
 */
cec_load_state_t cec_classify_load(float current_a, float noise_std_a);

/*
 * Human-readable load-state name. Always returns a valid pointer.
 */
const char *cec_load_state_name(cec_load_state_t s);

#ifdef __cplusplus
}
#endif
