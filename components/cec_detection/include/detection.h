#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "cec_state.h"

// Swing (rate-of-change) detector. Operates on the raw current stream.
typedef struct {
    float last_value;
    int64_t last_time_us;
    float threshold_a_per_ms;   // flag if |dI/dt| exceeds this
    bool primed;
} swing_detector_t;

void swing_init(swing_detector_t *d, float threshold_a_per_ms);
bool swing_check(swing_detector_t *d, float current, int64_t now_us);

// Threshold detector (Layer 1).
typedef struct {
    float oc_threshold_a;       // overcurrent ceiling
    float dropout_floor_a;      // undercurrent floor (when system should be active)
    bool dropout_enabled;
} threshold_detector_t;

void threshold_init(threshold_detector_t *t, float oc_a, float dropout_a);
uint8_t threshold_check(threshold_detector_t *t, float current);  // returns CEC_FLAG_* bits

// State classifier (Layer 3 support).
cec_op_state_t classify_state(float current_a, float variance);

// Top-level detection: runs all layers on one sample set, updates flags,
// returns true if any anomaly fired (caller may trigger burst capture).
typedef struct {
    swing_detector_t swing[CEC_NUM_CABLES];
    threshold_detector_t threshold[CEC_NUM_CABLES];
    // running stats for variance / baseline (Layer 3) - to be expanded
    float baseline_a[CEC_NUM_CABLES];
    float variance_a[CEC_NUM_CABLES];
} detection_ctx_t;

void detection_init(detection_ctx_t *ctx, float oc_threshold_a);
bool detection_run(detection_ctx_t *ctx, const float current_raw[CEC_NUM_CABLES],
                   const float current_filt[CEC_NUM_CABLES], int64_t now_us,
                   uint8_t *out_flags, cec_op_state_t *out_state);
