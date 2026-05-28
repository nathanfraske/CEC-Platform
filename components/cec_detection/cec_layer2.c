/*
 * Layer 2 fast-transient detector (rate-of-change).
 */

#include "cec_layer2.h"

void cec_layer2_init(cec_layer2_detector_t *d, float threshold_a_per_ms)
{
    d->last_value         = 0.0f;
    d->last_time_us       = 0;
    d->threshold_a_per_ms = threshold_a_per_ms;
    d->primed             = false;
}

bool cec_layer2_update(cec_layer2_detector_t *d, float current_a, int64_t now_us)
{
    if (!d->primed) {
        d->last_value   = current_a;
        d->last_time_us = now_us;
        d->primed       = true;
        return false;
    }
    float dt_ms = (now_us - d->last_time_us) / 1000.0f;
    bool fired = false;
    if (dt_ms > 0.0f) {
        float rate = (current_a - d->last_value) / dt_ms;
        if (rate >  d->threshold_a_per_ms) fired = true;
        if (rate < -d->threshold_a_per_ms) fired = true;
    }
    d->last_value   = current_a;
    d->last_time_us = now_us;
    return fired;
}

void cec_layer2_reset(cec_layer2_detector_t *d)
{
    d->primed = false;
}
