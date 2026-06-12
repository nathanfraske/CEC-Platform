/*
 * NTC thermistor driver using the Beta-coefficient equation.
 *
 * Wiring assumption: VCC --- pull-up resistor --- ADC pin --- NTC --- GND.
 * As the NTC heats, its resistance drops and the pin voltage drops with it.
 *
 * Reads go through cec_adc_read_mv so the calibration and oversampling
 * path is shared with the rest of the sensor stack.
 *
 * API parity with the 24-pin module's thermistor.h: same caller-owned
 * config struct, same esp_err_t / out-param contract, same
 * ESP_ERR_INVALID_RESPONSE sentinel for open/short. Name kept as "ntc"
 * because the part is specifically an NTC (the 24-pin's broader
 * "thermistor" naming was for hardware-style consistency that's not
 * needed here).
 */

#pragma once

#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    adc_channel_t channel;        /* ADC1 channel the divider sits on */
    int   samples;                /* Averaging count per read, >= 1 */
    float beta;                   /* NTC B coefficient (Kelvin) */
    float nominal_resistance;     /* R at nominal_temperature_k (ohms) */
    float nominal_temperature_k;  /* Reference temperature (kelvin), 298.15 = 25C */
    float pull_up_resistance;     /* Series pull-up resistor (ohms) */
    float vcc;                    /* Supply voltage at top of the divider (V) */
} ntc_t;

/*
 * Configure the ADC channel the thermistor lives on. Must be called once
 * before ntc_read_celsius. cec_adc_init() must have run first.
 */
esp_err_t ntc_setup(const ntc_t *t);

/*
 * Read the thermistor temperature in degrees Celsius.
 *
 * Returns ESP_ERR_INVALID_RESPONSE if the pin voltage is at one of the
 * divider rails (NTC open-circuited or shorted), in which case *out_c
 * is not written.
 */
esp_err_t ntc_read_celsius(const ntc_t *t, float *out_c);

#ifdef __cplusplus
}
#endif
