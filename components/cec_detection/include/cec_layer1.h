/*
 * Layer 1 static threshold detector.
 *
 * 24-pin parity: same sustained-severity shape as the 24-pin's
 * cec_layer1, with WARNING reported immediately on a single bad sample
 * and CRITICAL only after crit_required consecutive samples breach the
 * crit band.
 *
 * EPS-specific: the watched quantity is per-cable current (not rail
 * voltage), so the bands are absolute amps. The dropout floor reports
 * an undercurrent if the system should be loaded; the OC ceiling
 * reports overcurrent.
 */

#pragma once

#include <stdbool.h>
#include "cec_state.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float warn_threshold_a;   /* current at which WARNING fires */
    float crit_threshold_a;   /* current at which CRITICAL fires after debounce */
    float dropout_floor_a;    /* current below which DROPOUT fires (when armed) */
    bool  dropout_enabled;    /* gate dropout reporting (typically off during boot) */
    int   crit_required;      /* consecutive bad samples before CRITICAL */
    int   crit_consecutive;   /* internal counter */
} cec_layer1_detector_t;

/*
 * Configure the detector. crit_required is clamped to >= 1.
 * Pass warn_a == crit_a to disable the WARNING tier.
 */
void cec_layer1_init(cec_layer1_detector_t *d,
                     float warn_a,
                     float crit_a,
                     float dropout_a,
                     int   crit_required);

/*
 * Feed a current sample. Returns the sustained severity.
 */
cec_severity_t cec_layer1_update(cec_layer1_detector_t *d, float current_a);

/*
 * Returns true if this sample is below the (armed) dropout floor.
 * Separate from severity because dropout is a different anomaly class.
 */
bool cec_layer1_check_dropout(const cec_layer1_detector_t *d, float current_a);

/*
 * Clear the consecutive counter. Use during state-up transitions so a
 * brief startup transient can't immediately trip CRITICAL.
 */
void cec_layer1_reset(cec_layer1_detector_t *d);

#ifdef __cplusplus
}
#endif
