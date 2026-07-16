/*
 * PCIe 8-pin 3-port board/application configuration (the board-variation
 * point). ESP32-S3-MINI-1 interposer; one INA238 per cable over I2C, 3 cables
 * populated (the spec upper bound); 0.5 mOhm shunts; plus the §6.13 per-cable
 * transient-DETECTION front end. Spec §6.1/§6.4/§6.13.
 *
 * Identical to the 2-port SKU but for the third cable. VERIFY each pin/address
 * against the as-built pcie-8pin-3port schematic before bring-up.
 */

#pragma once

#include "cec_state.h"
#include "cec_pokeack.h"   /* CEC_POKEACK_TAP_NONE */

#ifdef __cplusplus
extern "C" {
#endif

/* Identity. module_id = the Hub port (0..3); default 2 (shares the "PCIe port"
 * role with the 2-port SKU -- a hub carries one PCIe SKU). Poke-and-ack can
 * rebind it. */
#define CEC_CFG_MODULE_TYPE     CEC_MODULE_TYPE_PCIE
#define CEC_CFG_MODULE_ID       2
#define CEC_CAN_TX_PERIOD_MS    200          /* 5 Hz telemetry */

/* Per-cable sensing: INA238 over I2C (SDA/SCL VERIFY against schematic). */
#define PCIE_NUM_CABLES         3
#define PCIE_I2C_SDA_GPIO       8
#define PCIE_I2C_SCL_GPIO       9
#define PCIE_INA238_ADDR        { 0x40, 0x41, 0x44 }   /* one per cable */
#define PCIE_SHUNT_OHMS         0.0005f                /* 0.5 mOhm per cable (§6.4) */

/* §6.13 per-cable transient detection (INA181 -> comparator -> DET latch). */
#define PCIE_DET_GPIO           { 15, 16, 7 }          /* per-cable DET latch in */
#define PCIE_THRESH_PWM_GPIO    14                     /* firmware threshold out */

/* Poke-and-ack DETECT tap (the generated PCIe boards tap IO10). Set
 * CEC_POKEACK_TAP_NONE if absent. */
#define CEC_CFG_DETECT_TAP_GPIO 10

#ifdef __cplusplus
}
#endif
