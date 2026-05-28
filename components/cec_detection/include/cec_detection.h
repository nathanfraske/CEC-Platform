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

typedef struct {
    cec_layer1_detector_t l1[CEC_NUM_CABLES];   /* current threshold */
    cec_layer2_detector_t l2[CEC_NUM_CABLES];   /* fast transient (dI/dt) */
    cec_rail_profile_t    l3[CEC_NUM_CABLES];   /* mean+std rail profile */
} cec_detection_ctx_t;

/*
 * Initialize all detectors. The OC ceiling comes from cec_config; the
 * warn band is set to the same value initially (single-tier) and can
 * be lowered later for a sub-critical warning.
 */
void cec_detection_init(cec_detection_ctx_t *ctx, float oc_threshold_a);

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
