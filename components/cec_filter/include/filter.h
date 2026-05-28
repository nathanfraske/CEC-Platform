#pragma once

#include <stdbool.h>

#define MEDIAN_WINDOW 5

// Median filter to reject impulse noise.
typedef struct {
    float buffer[MEDIAN_WINDOW];
    int idx;
    int count;
} median_filter_t;

void  median_init(median_filter_t *f);
float median_update(median_filter_t *f, float sample);

// Exponential moving average to smooth.
typedef struct {
    float value;
    float alpha;     // 0..1, higher = more responsive
    bool initialized;
} ema_filter_t;

void  ema_init(ema_filter_t *f, float alpha);
float ema_update(ema_filter_t *f, float sample);

// Combined two-stage filter (median then EMA), one per channel.
typedef struct {
    median_filter_t median;
    ema_filter_t ema;
} cec_filter_t;

void  cec_filter_init(cec_filter_t *f, float alpha);
float cec_filter_update(cec_filter_t *f, float sample);
void  cec_filter_set_alpha(cec_filter_t *f, float alpha);
