/*
 * Layer 1 static threshold detector.
 */

#include "cec_layer1.h"

void cec_layer1_init(cec_layer1_detector_t *d,
                     float warn_a,
                     float crit_a,
                     float dropout_a,
                     int   crit_required)
{
    d->warn_threshold_a = warn_a;
    d->crit_threshold_a = crit_a;
    d->dropout_floor_a  = dropout_a;
    d->dropout_enabled  = false;
    d->crit_required    = (crit_required < 1) ? 1 : crit_required;
    d->crit_consecutive = 0;
}

cec_severity_t cec_layer1_update(cec_layer1_detector_t *d, float current_a)
{
    if (current_a >= d->crit_threshold_a) {
        if (d->crit_consecutive < d->crit_required) {
            d->crit_consecutive++;
        }
        if (d->crit_consecutive >= d->crit_required) {
            return CEC_SEV_CRITICAL;
        }
        // Hasn't sustained yet - report as WARNING in the meantime so
        // the operator sees the brewing condition.
        return CEC_SEV_WARNING;
    }

    // Below crit; reset the debounce counter.
    d->crit_consecutive = 0;

    if (current_a >= d->warn_threshold_a) {
        return CEC_SEV_WARNING;
    }
    return CEC_SEV_NONE;
}

bool cec_layer1_check_dropout(const cec_layer1_detector_t *d, float current_a)
{
    if (!d->dropout_enabled) return false;
    return current_a < d->dropout_floor_a;
}

void cec_layer1_reset(cec_layer1_detector_t *d)
{
    d->crit_consecutive = 0;
}
