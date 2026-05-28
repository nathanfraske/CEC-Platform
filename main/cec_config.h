#pragma once

#include "cec_state.h"
#include "esp_err.h"
#include <stdio.h>

void      cec_config_defaults(cec_config_t *cfg);
esp_err_t cec_config_init_nvs(void);
void      cec_config_load(cec_config_t *cfg);
void      cec_config_save(const cec_config_t *cfg);
void      cec_config_save_zero_offset(int sensor, float offset_v);
bool      cec_config_load_zero_offset(int sensor, float *offset_v);
