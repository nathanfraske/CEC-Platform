/*
 * 24-pin module board/application configuration — definitions.
 */

#include "cec_config.h"

const cec_rail_spec_t CEC_CFG_L1_SPEC_12V  = { 12.0f, 0.05f, 0.10f };
const cec_rail_spec_t CEC_CFG_L1_SPEC_5V   = {  5.0f, 0.05f, 0.10f };
const cec_rail_spec_t CEC_CFG_L1_SPEC_3V3  = {  3.3f, 0.05f, 0.10f };
const cec_rail_spec_t CEC_CFG_L1_SPEC_5VSB = {  5.0f, 0.10f, 0.20f };
