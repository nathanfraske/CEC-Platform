#include "cec_capture.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "cec_capture";

esp_err_t capture_init(capture_ctx_t *ctx, float seconds, int sample_rate_hz)
{
    ctx->capacity = (size_t)(seconds * sample_rate_hz);
    if (ctx->capacity == 0) ctx->capacity = 1;

    size_t bytes = ctx->capacity * sizeof(capture_sample_t);
    // Allocate in PSRAM (SPIRAM). Falls back to internal if PSRAM missing.
    ctx->buffer = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM);
    if (!ctx->buffer) {
        ESP_LOGW(TAG, "PSRAM alloc failed, trying internal");
        ctx->buffer = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
    }
    if (!ctx->buffer) {
        ESP_LOGE(TAG, "ring buffer alloc failed (%u bytes)", (unsigned)bytes);
        return ESP_ERR_NO_MEM;
    }

    memset(ctx->buffer, 0, bytes);
    ctx->write_idx = 0;
    ctx->count = 0;
    ctx->armed = true;

    ESP_LOGI(TAG, "ring buffer: %u samples, %u bytes (%.1f s @ %d Hz)",
             (unsigned)ctx->capacity, (unsigned)bytes, seconds, sample_rate_hz);
    return ESP_OK;
}

void capture_push(capture_ctx_t *ctx, int64_t now_us, const float current[CEC_NUM_CABLES])
{
    if (!ctx->buffer || !ctx->armed) return;
    capture_sample_t *s = &ctx->buffer[ctx->write_idx];
    s->timestamp_us = now_us;
    for (int i = 0; i < CEC_NUM_CABLES; i++) s->current[i] = current[i];

    ctx->write_idx = (ctx->write_idx + 1) % ctx->capacity;
    if (ctx->count < ctx->capacity) ctx->count++;
}

void capture_dump(capture_ctx_t *ctx)
{
    if (!ctx->buffer || ctx->count == 0) return;

    // Walk from oldest to newest. Stub: prints CSV to the console.
    // A full implementation would stream over CAN or a dedicated channel.
    size_t start = (ctx->count == ctx->capacity) ? ctx->write_idx : 0;
    printf("# capture dump: %u samples\n", (unsigned)ctx->count);
    printf("t_us,i0,i1\n");
    for (size_t n = 0; n < ctx->count; n++) {
        size_t idx = (start + n) % ctx->capacity;
        capture_sample_t *s = &ctx->buffer[idx];
        printf("%lld,%.3f,%.3f\n", s->timestamp_us, s->current[0], s->current[1]);
    }
}

void capture_free(capture_ctx_t *ctx)
{
    if (ctx->buffer) {
        heap_caps_free(ctx->buffer);
        ctx->buffer = NULL;
    }
}
