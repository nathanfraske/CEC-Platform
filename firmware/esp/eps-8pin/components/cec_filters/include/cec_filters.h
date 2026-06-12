/*
 * EMA and rolling-median filter primitives.
 *
 * Pure software, no hardware deps. Caller owns all storage so no heap
 * allocation happens here.
 *
 * EMA: standard first-order IIR. Primes on the first sample so there is
 * no warm-up bias.
 *
 * Median: rolling window of the last N samples, sized at init time with
 * a caller-provided buffer. Returns the median on every update. The
 * implementation sorts a scratch copy on each call, which is fine for
 * the small N (<= CEC_MEDIAN_MAX_CAP) used by the detector layers.
 *
 * Parity with the 24-pin module's cec_filters.h. EPS-specific tuning
 * (window size, alpha) lives at the call site in eps_main.c.
 */

#pragma once

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CEC_MEDIAN_MAX_CAP 32

/* ------------------------- EMA ------------------------- */

typedef struct {
    float alpha;    /* Smoothing factor, 0 < alpha <= 1. Higher = faster. */
    float value;    /* Current filter output. Undefined until primed. */
    bool  primed;   /* true once at least one sample has been fed in. */
} ema_t;

void  ema_init(ema_t *e, float alpha);
float ema_update(ema_t *e, float sample);
float ema_value(const ema_t *e);
void  ema_reset(ema_t *e);

/* ----------------------- Median ----------------------- */

typedef struct {
    float *buf;     /* Caller-owned ring of size `cap`. */
    size_t cap;     /* Window size. 1 <= cap <= CEC_MEDIAN_MAX_CAP. */
    size_t count;   /* Valid samples in buf, capped at cap. */
    size_t head;    /* Next write index. */
} median_t;

void   median_init(median_t *m, float *buf, size_t cap);
float  median_update(median_t *m, float sample);
size_t median_count(const median_t *m);
void   median_reset(median_t *m);

#ifdef __cplusplus
}
#endif
