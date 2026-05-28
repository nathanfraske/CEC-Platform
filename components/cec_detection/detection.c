#include "detection.h"
#include <math.h>

// ---- Swing detector (Layer 2) ----

void swing_init(swing_detector_t *d, float threshold_a_per_ms)
{
    d->last_value = 0.0f;
    d->last_time_us = 0;
    d->threshold_a_per_ms = threshold_a_per_ms;
    d->primed = false;
}

bool swing_check(swing_detector_t *d, float current, int64_t now_us)
{
    if (!d->primed) {
        d->last_value = current;
        d->last_time_us = now_us;
        d->primed = true;
        return false;
    }
    float dt_ms = (now_us - d->last_time_us) / 1000.0f;
    bool fired = false;
    if (dt_ms > 0.0f) {
        float rate = (current - d->last_value) / dt_ms;
        if (rate > d->threshold_a_per_ms || rate < -d->threshold_a_per_ms) {
            fired = true;
        }
    }
    d->last_value = current;
    d->last_time_us = now_us;
    return fired;
}

// ---- Threshold detector (Layer 1) ----

void threshold_init(threshold_detector_t *t, float oc_a, float dropout_a)
{
    t->oc_threshold_a = oc_a;
    t->dropout_floor_a = dropout_a;
    t->dropout_enabled = false;   // enable once "system active" is known
}

uint8_t threshold_check(threshold_detector_t *t, float current)
{
    uint8_t flags = 0;
    if (current > t->oc_threshold_a) {
        flags |= CEC_FLAG_OVERCURRENT;
    }
    if (t->dropout_enabled && current < t->dropout_floor_a) {
        flags |= CEC_FLAG_DROPOUT;
    }
    return flags;
}

// ---- State classifier (Layer 3 support) ----

cec_op_state_t classify_state(float current_a, float variance)
{
    // High variance -> transient regardless of magnitude
    if (variance > 4.0f) {
        return CEC_STATE_TRANSIENT;
    }
    if (current_a < 5.0f)  return CEC_STATE_IDLE;
    if (current_a < 12.0f) return CEC_STATE_LIGHT;
    if (current_a < 22.0f) return CEC_STATE_MODERATE;
    return CEC_STATE_HEAVY;
}

// ---- Top-level detection ----

#define SWING_THRESHOLD_A_PER_MS  1.0f   // 1 A/ms = 10 A in 10 ms
#define DROPOUT_FLOOR_A           0.5f
#define VARIANCE_ALPHA            0.1f

void detection_init(detection_ctx_t *ctx, float oc_threshold_a)
{
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        swing_init(&ctx->swing[i], SWING_THRESHOLD_A_PER_MS);
        threshold_init(&ctx->threshold[i], oc_threshold_a, DROPOUT_FLOOR_A);
        ctx->baseline_a[i] = 0.0f;
        ctx->variance_a[i] = 0.0f;
    }
}

bool detection_run(detection_ctx_t *ctx, const float current_raw[CEC_NUM_CABLES],
                   const float current_filt[CEC_NUM_CABLES], int64_t now_us,
                   uint8_t *out_flags, cec_op_state_t *out_state)
{
    uint8_t flags = 0;
    float max_variance = 0.0f;
    float max_current = 0.0f;

    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        // Layer 1: threshold on filtered value
        flags |= threshold_check(&ctx->threshold[i], current_filt[i]);

        // Layer 2: swing on raw value (catches fast transients)
        if (swing_check(&ctx->swing[i], current_raw[i], now_us)) {
            flags |= CEC_FLAG_SWING;
        }

        // Layer 3 (partial): running variance estimate for the classifier.
        // EMA of squared deviation from the filtered baseline.
        float dev = current_raw[i] - current_filt[i];
        ctx->variance_a[i] = (1.0f - VARIANCE_ALPHA) * ctx->variance_a[i]
                             + VARIANCE_ALPHA * (dev * dev);

        if (ctx->variance_a[i] > max_variance) max_variance = ctx->variance_a[i];
        if (current_filt[i] > max_current)    max_current = current_filt[i];
    }

    *out_state = classify_state(max_current, max_variance);
    *out_flags = flags;
    return (flags != 0);
}
