/*
 * Top-level detection orchestrator.
 *
 * Layer split mirrors the 24-pin module:
 *   cec_layer1 - static threshold (overcurrent + dropout)
 *   cec_layer2 - fast transient (dI/dt for EPS)
 *   cec_layer3 - statistical baseline (variance EMA)
 *   cec_classifier - load-state classifier
 */

#include "cec_detection.h"

/* Detector-tuning defaults. EPS-specific; the 24-pin uses different
 * numbers for its voltage-domain bands. */
#define LAYER1_CRIT_REQUIRED        3      /* matches 24-pin's L1 default */
#define LAYER1_DROPOUT_FLOOR_A      0.5f   /* under-current when system should be loaded */
#define LAYER2_THRESHOLD_A_PER_MS   1.0f   /* 1 A/ms = 10 A in 10 ms */
#define LAYER3_VARIANCE_ALPHA       0.1f

void cec_detection_init(cec_detection_ctx_t *ctx, float oc_threshold_a)
{
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        // Single-tier OC: warn band == crit band until a sub-critical
        // warning level is tuned in. cec_layer1 will then report
        // WARNING vs CRITICAL on those distinct bands.
        cec_layer1_init(&ctx->l1[i],
                        oc_threshold_a, oc_threshold_a,
                        LAYER1_DROPOUT_FLOOR_A,
                        LAYER1_CRIT_REQUIRED);
        cec_layer2_init(&ctx->l2[i], LAYER2_THRESHOLD_A_PER_MS);
        cec_layer3_init(&ctx->l3[i], LAYER3_VARIANCE_ALPHA);
    }
}

bool cec_detection_run(cec_detection_ctx_t *ctx,
                       const float current_raw[CEC_NUM_CABLES],
                       const float current_filt[CEC_NUM_CABLES],
                       int64_t now_us,
                       uint8_t *out_flags,
                       cec_load_state_t *out_state)
{
    uint8_t flags = 0;
    float   max_variance = 0.0f;
    float   max_current  = 0.0f;

    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        // Layer 1: severity-graded threshold on the filtered value.
        cec_severity_t sev = cec_layer1_update(&ctx->l1[i], current_filt[i]);
        if (sev == CEC_SEV_CRITICAL) {
            flags |= CEC_FLAG_OVERCURRENT;
        }
        if (cec_layer1_check_dropout(&ctx->l1[i], current_filt[i])) {
            flags |= CEC_FLAG_DROPOUT;
        }

        // Layer 2: rate-of-change on the raw stream (catches fast transients).
        if (cec_layer2_update(&ctx->l2[i], current_raw[i], now_us)) {
            flags |= CEC_FLAG_SWING;
        }

        // Layer 3: running variance estimate for the classifier.
        float var = cec_layer3_update(&ctx->l3[i], current_raw[i], current_filt[i]);

        if (var > max_variance)            max_variance = var;
        if (current_filt[i] > max_current) max_current  = current_filt[i];
    }

    *out_state = cec_classify_load(max_current, max_variance);
    *out_flags = flags;
    return (flags != 0);
}
