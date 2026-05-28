/*
 * Layer 3 statistical baseline (variance EMA).
 */

#include "cec_layer3.h"

void cec_layer3_init(cec_layer3_detector_t *d, float alpha)
{
    d->variance_est = 0.0f;
    d->alpha = alpha;
}

float cec_layer3_update(cec_layer3_detector_t *d, float instant, float smoothed)
{
    float dev = instant - smoothed;
    d->variance_est = (1.0f - d->alpha) * d->variance_est + d->alpha * (dev * dev);
    return d->variance_est;
}

float cec_layer3_variance(const cec_layer3_detector_t *d)
{
    return d->variance_est;
}

void cec_layer3_reset(cec_layer3_detector_t *d)
{
    d->variance_est = 0.0f;
}
