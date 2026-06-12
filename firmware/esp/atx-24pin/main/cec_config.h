/*
 * 24-pin module board/application configuration — the official
 * board-variation point (eps main/cec_config pattern, firmware
 * consolidation Phase E3). Constants that tune the SHARED detection
 * components live here, never inside firmware/esp/components.
 *
 * Currently carries the Layer 1 / Layer 2 detector tuning hoisted from
 * main.c when the detectors moved to the shared cec_detection. Future
 * hoists (pins, dividers, trims, swing/L3 tuning) belong here too.
 */

#pragma once

#include "cec_layer1.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Layer 1 static-threshold bands per rail (BAND mode). Carried forward
 * from v0.5.9: 5%/10% deviation on the main rails, 10%/20% on the
 * loose-spec 5VSB. Definitions in cec_config.c. */
extern const cec_rail_spec_t CEC_CFG_L1_SPEC_12V;
extern const cec_rail_spec_t CEC_CFG_L1_SPEC_5V;
extern const cec_rail_spec_t CEC_CFG_L1_SPEC_3V3;
extern const cec_rail_spec_t CEC_CFG_L1_SPEC_5VSB;

/* Consecutive out-of-band samples before Layer 1 reports CRITICAL
 * (v0.5.9 default). */
#define L1_CRIT_CONSECUTIVE 3

/* Layer 2 adaptive transient detectors. Per-rail min-thresholds and
 * k_sigma carry forward from v0.5.9. The fire condition is
 * |instant - ema| > max(min, k*std) for 3 consecutive samples. */
#define LAYER2_K_SIGMA       5.0f
#define LAYER2_CONSECUTIVE   3
#define L2_MIN_V_12V         0.50f
#define L2_MIN_V_5V          0.20f
#define L2_MIN_V_3V3         0.15f
#define L2_MIN_V_5VSB        0.30f
#define L2_MIN_I_12V         1.00f
#define L2_MIN_I_5V          0.50f
#define L2_MIN_I_3V3         0.30f

/* Dedicated TelePlot UART transport (CH340K USB-C bridge on UART0,
 * GPIO 43 TX / 44 RX, 921600 baud — see the Serial topology section of
 * the app README). Hoisted from the old component-baked values when
 * cec_telemetry went shared. */
#define TELEMETRY_UART_NUM       0
#define TELEMETRY_UART_TXD       43
#define TELEMETRY_UART_RXD       44
#define TELEMETRY_UART_BAUD      921600
#define TELEMETRY_UART_TX_BUF    4096   /* Burst dumps need headroom */

#ifdef __cplusplus
}
#endif
