/*
 * Top-level detection orchestrator.
 *
 * Layer split mirrors the 24-pin module:
 *   cec_layer1     - static threshold (overcurrent + dropout)
 *   cec_layer2     - fast transient (dI/dt for EPS)
 *   cec_layer3     - rail profile (mean + std, z-score for anomaly)
 *   cec_classifier - load-state classifier
 *
 * Layer 3 is the 24-pin's cec_rail_profile_t verbatim. The classifier
 * compares the per-cable running std_dev against a threshold to flag
 * CEC_LOAD_TRANSIENT, and the z-score is also available to callers
 * via the ctx for finer-grained anomaly detection (TODO: fold a
 * |z| > 4 check into the flags bitfield once the noise floor is
 * characterized on hardware).
 */

#include "cec_detection.h"

void cec_detection_init(cec_detection_ctx_t *ctx,
                        const cec_detection_config_t *cfg)
{
    ctx->cfg = *cfg;
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        cec_layer1_init_ceiling(&ctx->l1[i],
                                cfg->oc_threshold_a, cfg->oc_threshold_a,
                                cfg->dropout_floor_a,
                                cfg->crit_required);
        cec_layer2_init_rate(&ctx->l2[i], cfg->l2_threshold_a_per_ms);
        cec_rail_profile_init(&ctx->l3[i]);
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
    float   max_std     = 0.0f;
    float   max_current = 0.0f;

    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        /* Layer 1: severity-graded threshold on the filtered value. */
        cec_severity_t sev = cec_layer1_update(&ctx->l1[i], current_filt[i]);
        if (sev == CEC_SEV_CRITICAL) {
            flags |= CEC_FLAG_OVERCURRENT;
        }
        if (cec_layer1_check_dropout(&ctx->l1[i], current_filt[i])) {
            flags |= CEC_FLAG_DROPOUT;
        }

        /* Layer 2: rate-of-change on the raw stream (fast transients). */
        if (cec_layer2_update_rate(&ctx->l2[i], current_raw[i], now_us)) {
            flags |= CEC_FLAG_SWING;
        }

        /* Layer 3: rail profile. Feed the filtered value so brief raw
         * spikes don't widen the std estimate; the classifier picks
         * up the resulting std_dev as a noise/variability gauge. */
        cec_rail_profile_update(&ctx->l3[i], current_filt[i], ctx->cfg.l3_adapt_rate);

        if (ctx->l3[i].std_dev > max_std)  max_std     = ctx->l3[i].std_dev;
        if (current_filt[i]    > max_current) max_current = current_filt[i];
    }

    *out_state = cec_classify_load(max_current, max_std);
    *out_flags = flags;
    return (flags != 0);
}
