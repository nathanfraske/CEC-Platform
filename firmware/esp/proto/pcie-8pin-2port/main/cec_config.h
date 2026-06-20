/*
 * PCIe 8-pin 2-port board/application configuration (the board-variation
 * point). ESP32-S3-MINI-1 interposer; one INA238 per cable over I2C
 * (per-cable granularity), 2 cables populated; 0.5 mOhm shunts; plus the
 * §6.13 per-cable transient-DETECTION front end (INA181 CSA + comparator ->
 * firmware threshold -> FREEZE). Spec §6.1/§6.4/§6.13.
 *
 * Pin/address values are the spec's design intent -- VERIFY each against the
 * as-built pcie-8pin-2port schematic before bring-up.
 */

#pragma once

#include "cec_state.h"
#include "cec_pokeack.h"   /* CEC_POKEACK_TAP_NONE */

#ifdef __cplusplus
extern "C" {
#endif

/* Identity. module_id = the Hub port (0..3); default 2 (24-pin=0, EPS=1,
 * PCIe=2, 12VHPWR=3 for a clean 4-module bench). Poke-and-ack can rebind it. */
#define CEC_CFG_MODULE_TYPE     CEC_MODULE_TYPE_PCIE
#define CEC_CFG_MODULE_ID       2
#define CEC_CAN_TX_PERIOD_MS    200          /* 5 Hz telemetry */

/* Per-cable sensing: INA238 over I2C (SDA/SCL VERIFY against schematic). */
#define PCIE_NUM_CABLES         2
#define PCIE_I2C_SDA_GPIO       8
#define PCIE_I2C_SCL_GPIO       9
#define PCIE_INA238_ADDR        { 0x40, 0x41 }   /* one per cable */
#define PCIE_SHUNT_OHMS         0.0005f          /* 0.5 mOhm per cable (§6.4) */

/* §6.13 per-cable transient detection: INA181 CSA -> TLV7011 comparator vs a
 * firmware threshold (MCU PWM) -> per-cable DET latch GPIO -> ORs into FREEZE.
 * VERIFY pins; stubbed in main.c until bring-up. */
#define PCIE_DET_GPIO           { 15, 16 }        /* per-cable DET latch in */
#define PCIE_THRESH_PWM_GPIO    14                /* firmware threshold out */

/* Poke-and-ack DETECT tap (pin 8 -> ~100k -> GPIO; the generated PCIe boards
 * tap IO10). Set CEC_POKEACK_TAP_NONE if absent. */
#define CEC_CFG_DETECT_TAP_GPIO 10

#ifdef __cplusplus
}
#endif
