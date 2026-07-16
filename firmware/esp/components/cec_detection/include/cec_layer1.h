/*
 * Layer 1 static threshold detector — dual-mode merge (firmware
 * consolidation, Phase E). One detector type, two watch modes; each app
 * instantiates the mode matching its signal. Board-specific bands and
 * thresholds live in each app's cec_config (never in this component).
 *
 *   BAND mode (24-pin lineage): watches one rail's VOLTAGE against a
 *   nominal +- warn / crit fractional-deviation band. Below 0.1 V the
 *   rail is considered off and reports NONE (counter reset). Severity
 *   bands carry forward from v0.5.9: 5%/10% deviation for the main
 *   rails (12V/5V/3V3) and 10%/20% for the loose-spec 5VSB.
 *
 *   CEILING mode (eps lineage): watches per-cable CURRENT against
 *   absolute warn/crit ceilings in amps, plus an armable dropout floor
 *   (undercurrent while the system should be loaded).
 *
 * Shared sustained-severity shape in both modes:
 *   - NONE and WARNING are reported immediately on a single sample.
 *   - CRITICAL is reported only after `crit_required` consecutive
 *     samples breach the crit band/ceiling; while debouncing, WARNING
 *     is reported so the caller can see the brewing condition.
 *
 * The detector is stateful (holds the consecutive counter) but cheap to
 * reset, so callers can gate updates by system state (e.g. ignore while
 * the PSU is OFF/STANDBY) without losing config.
 */

#pragma once

#include <stdbool.h>
#include "cec_state.h"  /* for cec_severity_t */

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CEC_L1_MODE_BAND = 0,     /* fractional deviation around a nominal */
    CEC_L1_MODE_CEILING,      /* absolute ceiling + dropout floor */
} cec_layer1_mode_t;

typedef struct {
    float nominal;     /* Nominal rail voltage (e.g. 12.0) */
    float warn_band;   /* Fractional deviation triggering WARNING (e.g. 0.05) */
    float crit_band;   /* Fractional deviation triggering CRITICAL (e.g. 0.10) */
} cec_rail_spec_t;

typedef struct {
    cec_layer1_mode_t mode;

    /* BAND mode */
    cec_rail_spec_t spec;

    /* CEILING mode */
    float warn_threshold_a;   /* value at which WARNING fires */
    float crit_threshold_a;   /* value at which CRITICAL fires after debounce */
    float dropout_floor_a;    /* value below which DROPOUT fires (when armed) */
    bool  dropout_enabled;    /* gate dropout reporting (typically off at boot) */

    /* common */
    int crit_required;        /* Consecutive bad samples before CRITICAL */
    int crit_consecutive;     /* Running counter, internal */
} cec_layer1_detector_t;

/*
 * Configure a BAND-mode detector (24-pin lineage). `crit_required`
 * >= 1; 3 is the v0.5.9 default.
 */
void cec_layer1_init_band(cec_layer1_detector_t *d,
                          const cec_rail_spec_t *spec,
                          int crit_required);

/*
 * Configure a CEILING-mode detector (eps lineage). crit_required is
 * clamped to >= 1. Pass warn_a == crit_a to disable the WARNING tier.
 * Dropout starts disarmed (dropout_enabled = false).
 */
void cec_layer1_init_ceiling(cec_layer1_detector_t *d,
                             float warn_a,
                             float crit_a,
                             float dropout_a,
                             int   crit_required);

/*
 * Feed a sample (volts in BAND mode, amps in CEILING mode) and return
 * the sustained severity. In BAND mode a value below 0.1 V is
 * considered "rail off" and returns NONE (counter reset).
 */
cec_severity_t cec_layer1_update(cec_layer1_detector_t *d, float value);

/*
 * CEILING mode: returns true if this sample is below the (armed)
 * dropout floor. Separate from severity because dropout is a different
 * anomaly class. Always false in BAND mode.
 */
bool cec_layer1_check_dropout(const cec_layer1_detector_t *d, float value);

/*
 * Clear the consecutive counter. Use when entering a state where the
 * watched signal isn't expected at nominal (e.g. STANDBY) so a
 * transient during a later state change can't immediately trip
 * CRITICAL.
 */
void cec_layer1_reset(cec_layer1_detector_t *d);

#ifdef __cplusplus
}
#endif
