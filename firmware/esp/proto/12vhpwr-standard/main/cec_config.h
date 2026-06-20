/*
 * 12VHPWR Standard board/application configuration (the board-variation
 * point). ESP32-S3-MINI-1; six INA240 per-pin current-sense amps into the S3
 * ADC + a 47k/10k rail-voltage divider + two NTCs. NO FPGA, no external ADC --
 * that fast path (GW5A/AD7606) is the Pro tier. Spec §6.1, §6.4, §6.13.
 *
 * Most of the per-connector signal lives at ~10 kHz; the S3 SAR is ~83 kSps
 * shared, so 6 pins + rail round-robin to ~12 kSps/ch (~6 kHz Nyquist). The
 * continuous CAN telemetry is therefore a LOW-RATE SUMMARY; the 10 kHz per-pin
 * detail is captured in a local burst (cec_capture / §6.10) on a trigger, not
 * streamed. See main.c.
 *
 * Pin/threshold values below are from the spec's design intent -- VERIFY every
 * one against the as-built 12vhpwr-standard schematic before bring-up.
 */

#pragma once

#include "cec_state.h"
#include "cec_pokeack.h"   /* CEC_POKEACK_TAP_NONE */

#ifdef __cplusplus
extern "C" {
#endif

/* This module's identity on the bus. module_id = the Hub port it plugs into
 * (0..3); poke-and-ack can rebind it. Default 3 gives a clean 4-module bench
 * (24-pin=0, EPS=1, PCIe=2, 12VHPWR=3); set distinct per your hub. */
#define CEC_CFG_MODULE_TYPE     CEC_MODULE_TYPE_12VHPWR
#define CEC_CFG_MODULE_ID       3
#define CEC_CAN_TX_PERIOD_MS    200          /* 5 Hz telemetry summary */

/* Sensing — 6 INA240 (gain A3 = 100 V/V) on 1 mOhm per-pin shunts into ADC1,
 * plus a 47k/10k rail divider, plus NTCs (spec §6.1/§6.4). ADC channels per
 * the v0.x pin map; VERIFY against the schematic. */
#define HPWR_NUM_PINS           6
#define HPWR_SHUNT_OHMS         0.001f        /* 1 mOhm per-pin (§6.4) */
#define HPWR_INA240_GAIN        100.0f        /* INA240A3 */
#define HPWR_ADC_PIN_GPIO       { 1, 2, 3, 4, 5, 6 }   /* INA240 OUT -> ADC1_CH0..5 */
#define HPWR_RAIL_DIV_GPIO      7             /* 47k/10k rail divider -> ADC1_CH6 */
#define HPWR_RAIL_DIV_NUM       47000.0f
#define HPWR_RAIL_DIV_DEN       10000.0f
#define HPWR_NTC_BOARD_GPIO     13            /* TH1 by the shunt row (ADC2) */
#define HPWR_NTC_AMBIENT_GPIO   14            /* TH2 ambient (ADC2) */

/* Poke-and-ack DETECT tap (pin 8 -> ~100k -> GPIO). VERIFY the pin; set to
 * CEC_POKEACK_TAP_NONE if this board has no tap. */
#define CEC_CFG_DETECT_TAP_GPIO 10

/* Imbalance alarm: a sustained per-pin hog is the §6.13 detection thesis. A
 * pin this far above the per-pin mean flags an imbalance (electrical outlier
 * leads the thermal one). Tune at bring-up. */
#define HPWR_IMBALANCE_FRAC     0.40f         /* 40% over mean -> flag */
#define HPWR_FLAG_IMBALANCE     (1u << 0)

#ifdef __cplusplus
}
#endif
