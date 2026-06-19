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

/* TelePlot UART transport pins -- VESTIGIAL on the production board, which has
 * only the MCU's native USB Serial/JTAG. main.c does NOT call
 * cec_telemetry_init_uart (see the comment there), so TelePlot always rides
 * stdio with the logs regardless of CONFIG_CEC_TELEMETRY_UART0. These were the
 * dev board's CH340K UART bridge (GPIO43/44, 921600); kept only so the shared
 * cec_telemetry init signature still resolves. A board that actually has the
 * bridge would call cec_telemetry_init_uart with CONFIG_CEC_TELEMETRY_UART0=y. */
#define TELEMETRY_UART_NUM       0
#define TELEMETRY_UART_TXD       43
#define TELEMETRY_UART_RXD       44
#define TELEMETRY_UART_BAUD      921600
#define TELEMETRY_UART_TX_BUF    4096   /* Burst dumps need headroom */

/*
 * Production 24-pin sensing — 4x INA228 (one per rail), traced from the
 * board netlist (24pin-module.kicad_sch). Each INA228 gives bus voltage +
 * current; the ACS712/divider front end is retired. I2C SDA=IO8 / SCL=IO9.
 *
 *   Rail  U     I2C   shunt    ALERT
 *   12V   U10   0x40  2 mOhm   IO10
 *   5V    U11   0x41  2 mOhm   IO11
 *   3V3   U12   0x44  2 mOhm   IO12
 *   5VSB  U13   0x45  25 mOhm  IO13
 *
 * Status LED: D2 on IO21 (active-high, IO21 -> R7 -> LED -> GND).
 */
#define INA228_ADDR_12V      0x40
#define INA228_ADDR_5V       0x41
#define INA228_ADDR_3V3      0x44
#define INA228_ADDR_5VSB     0x45
#define INA228_SHUNT_MAIN    0.002f   /* 12V/5V/3V3 = 2 mOhm */
#define INA228_SHUNT_5VSB    0.025f   /* 5VSB = 25 mOhm */
#define INA228_ALERT_12V     10
#define INA228_ALERT_5V      11
#define INA228_ALERT_3V3     12
#define INA228_ALERT_5VSB    13
#define STATUS_LED_GPIO      21       /* D2, active-high */

/* PSU control/status, buffered to 3.3V by U4/U5 (74LVC1G17, non-inverting),
 * tapped off the ATX pass-through. Read-only: the module monitors these, it
 * does not drive PS_ON#. */
#define PWROK_BUF_GPIO       38       /* U4 out: ATX PWR_OK (1 = power good) */
#define PSON_BUF_GPIO        39       /* U5 out: ATX PS_ON# (0 = PSU on, active-low) */

#ifdef __cplusplus
}
#endif
