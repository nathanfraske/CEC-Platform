#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "cec_state.h"
#include "esp_err.h"

// Pre-trigger ring buffer in PSRAM for burst capture of transients.
// Continuously records samples; on a trigger, the recent history plus
// post-trigger samples form a capture window for analysis.

typedef struct {
    int64_t timestamp_us;
    float current[CEC_NUM_CABLES];
} capture_sample_t;

typedef struct {
    capture_sample_t *buffer;   // allocated in PSRAM
    size_t capacity;            // number of samples
    size_t write_idx;
    size_t count;
    bool armed;
} capture_ctx_t;

// Allocate the ring buffer in PSRAM. seconds * sample_rate = capacity.
esp_err_t capture_init(capture_ctx_t *ctx, float seconds, int sample_rate_hz);

// Push one sample into the ring buffer (called from the sample task).
void capture_push(capture_ctx_t *ctx, int64_t now_us, const float current[CEC_NUM_CABLES]);

// Dump the buffer contents (e.g., over serial) after a trigger.
// Stub for now; full implementation streams the window out.
void capture_dump(capture_ctx_t *ctx);

void capture_free(capture_ctx_t *ctx);
