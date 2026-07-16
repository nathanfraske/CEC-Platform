/*
 * Layer 2 fast-transient detector — dual-mode merge. The ADAPTIVE path
 * is the 24-pin source, the RATE path the eps source, verbatim.
 */
#include <math.h>
#include "cec_layer2.h"

/* ADAPTIVE mode: tiny variance floor so the initial std is never
 * exactly zero and the EMA-update can't get stuck. */
#define VARIANCE_FLOOR 0.0001f

/* ADAPTIVE mode: variance estimator update weights (from v0.5.9). */
#define VAR_RETAIN     0.98f
#define VAR_NEW        0.02f

void cec_layer2_init_adaptive(cec_layer2_detector_t *d,
                              float min_threshold,
                              float k_sigma,
                              int   required_consecutive)
{
    d->mode = CEC_L2_MODE_ADAPTIVE;
    d->min_threshold = min_threshold;
    d->k_sigma = k_sigma;
    d->required_consecutive = (required_consecutive >= 1) ? required_consecutive : 1;
    d->consecutive_count = 0;
    d->variance_est = VARIANCE_FLOOR;
    d->initialized = false;
    d->last_value = 0.0f;
    d->last_time_us = 0;
    d->threshold_a_per_ms = 0.0f;
    d->primed = false;
}

void cec_layer2_init_rate(cec_layer2_detector_t *d, float threshold_a_per_ms)
{
    d->mode = CEC_L2_MODE_RATE;
    d->min_threshold = 0.0f;
    d->k_sigma = 0.0f;
    d->required_consecutive = 1;
    d->consecutive_count = 0;
    d->variance_est = 0.0f;
    d->initialized = false;
    d->last_value         = 0.0f;
    d->last_time_us       = 0;
    d->threshold_a_per_ms = threshold_a_per_ms;
    d->primed             = false;
}

void cec_layer2_reset(cec_layer2_detector_t *d)
{
    d->consecutive_count = 0;
    d->primed = false;
}

bool cec_layer2_update_adaptive(cec_layer2_detector_t *d, float instant, float ema)
{
    float dev = instant - ema;
    float abs_dev = fabsf(dev);

    if (!d->initialized) {
        d->variance_est = dev * dev + VARIANCE_FLOOR;
        d->initialized = true;
    }

    float std = sqrtf(d->variance_est);
    float adaptive = d->k_sigma * std;
    float threshold = (adaptive > d->min_threshold) ? adaptive : d->min_threshold;

    if (abs_dev > threshold) {
        d->consecutive_count++;
        if (d->consecutive_count >= d->required_consecutive) {
            d->consecutive_count = 0;
            return true;
        }
    } else {
        d->consecutive_count = 0;
        d->variance_est = VAR_RETAIN * d->variance_est + VAR_NEW * dev * dev;
    }
    return false;
}

bool cec_layer2_update_rate(cec_layer2_detector_t *d, float value, int64_t now_us)
{
    if (!d->primed) {
        d->last_value   = value;
        d->last_time_us = now_us;
        d->primed       = true;
        return false;
    }

    float dt_ms = (now_us - d->last_time_us) / 1000.0f;
    bool fired = false;
    if (dt_ms > 0.0f) {
        float rate = (value - d->last_value) / dt_ms;
        if (rate >  d->threshold_a_per_ms) fired = true;
        if (rate < -d->threshold_a_per_ms) fired = true;
    }
    d->last_value   = value;
    d->last_time_us = now_us;
    return fired;
}

float cec_layer2_current_threshold(const cec_layer2_detector_t *d)
{
    float std = sqrtf(d->variance_est);
    float adaptive = d->k_sigma * std;
    return (adaptive > d->min_threshold) ? adaptive : d->min_threshold;
}
