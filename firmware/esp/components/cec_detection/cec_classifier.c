/*
 * Per-cable load classifier.
 */

#include "cec_classifier.h"

static const char *NAMES[CEC_LOAD_COUNT] = {
    [CEC_LOAD_IDLE]      = "IDLE",
    [CEC_LOAD_LIGHT]     = "LIGHT",
    [CEC_LOAD_MODERATE]  = "MODERATE",
    [CEC_LOAD_HEAVY]     = "HEAVY",
    [CEC_LOAD_TRANSIENT] = "TRANSIENT",
};

const char *cec_load_state_name(cec_load_state_t s)
{
    if ((int)s < 0 || (int)s >= CEC_LOAD_COUNT) return "?";
    return NAMES[s];
}

cec_load_state_t cec_classify_load(float current_a, float noise_std_a)
{
    // High std deviation -> transient regardless of magnitude.
    // 0.5 A is well above the filtered noise floor (~10-30 mA RMS)
    // so only sustained large swings trip TRANSIENT.
    if (noise_std_a > 0.5f) return CEC_LOAD_TRANSIENT;

    if (current_a < 5.0f)  return CEC_LOAD_IDLE;
    if (current_a < 12.0f) return CEC_LOAD_LIGHT;
    if (current_a < 22.0f) return CEC_LOAD_MODERATE;
    return CEC_LOAD_HEAVY;
}
