/*
 * NTC thermistor driver — compatibility header (firmware consolidation,
 * Phase F3). The eps `ntc` driver and the 24-pin `thermistor` driver
 * were the same Beta-equation divider math under two names; the single
 * source lives in thermistor.{c,h} (the broader name), and this header
 * preserves the eps API verbatim. Selecting either CEC_SENSOR_NTC or
 * CEC_SENSOR_THERMISTOR compiles the one shared source.
 */

#pragma once

#include "thermistor.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef thermistor_t ntc_t;

static inline esp_err_t ntc_setup(const ntc_t *t)
{
    return thermistor_setup(t);
}

static inline esp_err_t ntc_read_celsius(const ntc_t *t, float *out_c)
{
    return thermistor_read_celsius(t, out_c);
}

#ifdef __cplusplus
}
#endif
