/*
 * Top-level detection orchestrator.
 *
 * Owns one cec_layer1/2/3 detector per cable and runs them on every
 * sample. Layers fire independently; the result is folded into the
 * CEC_FLAG_* status_flags bitfield and a cec_load_state_t load
 * classification.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "cec_state.h"
#include "cec_layer1.h"
#include "cec_layer2.h"
#include "cec_layer3.h"
#include "cec_classifier.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Detector tuning. Board/application values live in the app's
 * cec_config (the board-variation point), never in this component. */
typedef struct {
    float oc_threshold_a;         /* L1 ceiling; warn tier == crit initially */
    float dropout_floor_a;        /* L1 dropout floor (armed separately) */
    int   crit_required;          /* L1 debounce (consecutive samples) */
    float l2_threshold_a_per_ms;  /* L2 rate-of-change threshold */
    float l3_adapt_rate;          /* L3 steady-state adapt rate */
} cec_detection_config_t;

typedef struct {
    cec_layer1_detector_t l1[CEC_NUM_CABLES];   /* current threshold */
    cec_layer2_detector_t l2[CEC_NUM_CABLES];   /* fast transient (dI/dt) */
    cec_rail_profile_t    l3[CEC_NUM_CABLES];   /* mean+std rail profile */
    cec_detection_config_t cfg;
} cec_detection_ctx_t;

/*
 * Initialize all detectors from the app-supplied tuning. The OC ceiling
 * doubles as the warn tier initially (single-tier) and can be lowered
 * later for a sub-critical warning.
 */
void cec_detection_init(cec_detection_ctx_t *ctx,
                        const cec_detection_config_t *cfg);

/*
 * Run all layers on one sample set. Folds Layer 1 severities and
 * Layer 2 transient hits into out_flags; classifies the load level
 * using max-current + max-variance into out_state.
 *
 * Returns true if any layer fired (callers may trigger burst capture).
 */
bool cec_detection_run(cec_detection_ctx_t *ctx,
                       const float current_raw[CEC_NUM_CABLES],
                       const float current_filt[CEC_NUM_CABLES],
                       int64_t now_us,
                       uint8_t *out_flags,
                       cec_load_state_t *out_state);

#ifdef __cplusplus
}
#endif
