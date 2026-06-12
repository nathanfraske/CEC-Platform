#pragma once

#include "cec_state.h"
#include "esp_err.h"
#include <stdio.h>

/* Detector tuning for the shared cec_detection component (the
 * board-variation point; hoisted from the component in Phase E). The
 * OC ceiling itself is runtime config (cec_config_t.oc_threshold_a). */
#define EPS_DETECT_CRIT_REQUIRED        3
#define EPS_DETECT_DROPOUT_FLOOR_A      0.5f
#define EPS_DETECT_L2_RATE_A_PER_MS     1.0f
/* Layer 3 adapt rate. 0.0005 at 50 Hz gives a ~2000-sample (40 s)
 * effective averaging window once warm, matching the 24-pin's value. */
#define EPS_DETECT_L3_ADAPT_RATE        0.0005f

void      cec_config_defaults(cec_config_t *cfg);
esp_err_t cec_config_init_nvs(void);
void      cec_config_load(cec_config_t *cfg);
void      cec_config_save(const cec_config_t *cfg);
void      cec_config_save_zero_offset(int sensor, float offset_v);
bool      cec_config_load_zero_offset(int sensor, float *offset_v);
