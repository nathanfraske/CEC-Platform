/*
 * Layer 1 static threshold detector — dual-mode merge. The BAND path is
 * the 24-pin source, the CEILING path the eps source; the consecutive
 * counter is clamped at crit_required in both (identical observable
 * behavior, no overflow on a sustained fault).
 */
#include <math.h>
#include "cec_layer1.h"

/* BAND mode: rails below this are treated as "off, not abnormal". */
#define RAIL_OFF_VOLTS 0.1f

static const char *NAMES[] = {
    [CEC_SEV_NONE]     = "NONE",
    [CEC_SEV_WARNING]  = "WARNING",
    [CEC_SEV_CRITICAL] = "CRITICAL",
};

const char *cec_severity_name(cec_severity_t s)
{
    if ((int)s < 0 || (int)s > CEC_SEV_CRITICAL) return "?";
    return NAMES[s];
}

void cec_layer1_init_band(cec_layer1_detector_t *d,
                          const cec_rail_spec_t *spec,
                          int crit_required)
{
    d->mode = CEC_L1_MODE_BAND;
    d->spec = *spec;
    d->warn_threshold_a = 0.0f;
    d->crit_threshold_a = 0.0f;
    d->dropout_floor_a  = 0.0f;
    d->dropout_enabled  = false;
    d->crit_required = (crit_required >= 1) ? crit_required : 1;
    d->crit_consecutive = 0;
}

void cec_layer1_init_ceiling(cec_layer1_detector_t *d,
                             float warn_a,
                             float crit_a,
                             float dropout_a,
                             int   crit_required)
{
    d->mode = CEC_L1_MODE_CEILING;
    d->spec = (cec_rail_spec_t){ 0 };
    d->warn_threshold_a = warn_a;
    d->crit_threshold_a = crit_a;
    d->dropout_floor_a  = dropout_a;
    d->dropout_enabled  = false;
    d->crit_required    = (crit_required < 1) ? 1 : crit_required;
    d->crit_consecutive = 0;
}

void cec_layer1_reset(cec_layer1_detector_t *d)
{
    d->crit_consecutive = 0;
}

cec_severity_t cec_layer1_update(cec_layer1_detector_t *d, float value)
{
    if (d->mode == CEC_L1_MODE_BAND) {
        if (value < RAIL_OFF_VOLTS) {
            d->crit_consecutive = 0;
            return CEC_SEV_NONE;
        }

        float dev = fabsf((value - d->spec.nominal) / d->spec.nominal);

        if (dev > d->spec.crit_band) {
            if (d->crit_consecutive < d->crit_required) {
                d->crit_consecutive++;
            }
            if (d->crit_consecutive >= d->crit_required) {
                return CEC_SEV_CRITICAL;
            }
            /* Below the consecutive threshold the rail is still anomalous;
             * report WARNING so the caller can see the transient. */
            return CEC_SEV_WARNING;
        }
        d->crit_consecutive = 0;
        if (dev > d->spec.warn_band) {
            return CEC_SEV_WARNING;
        }
        return CEC_SEV_NONE;
    }

    /* CEC_L1_MODE_CEILING */
    if (value >= d->crit_threshold_a) {
        if (d->crit_consecutive < d->crit_required) {
            d->crit_consecutive++;
        }
        if (d->crit_consecutive >= d->crit_required) {
            return CEC_SEV_CRITICAL;
        }
        /* Hasn't sustained yet - report as WARNING in the meantime so
         * the operator sees the brewing condition. */
        return CEC_SEV_WARNING;
    }
    /* Below crit; reset the debounce counter. */
    d->crit_consecutive = 0;

    if (value >= d->warn_threshold_a) {
        return CEC_SEV_WARNING;
    }
    return CEC_SEV_NONE;
}

bool cec_layer1_check_dropout(const cec_layer1_detector_t *d, float value)
{
    if (d->mode != CEC_L1_MODE_CEILING) return false;
    if (!d->dropout_enabled) return false;
    return value < d->dropout_floor_a;
}
