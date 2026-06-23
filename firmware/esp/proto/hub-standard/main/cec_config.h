/*
 * Hub Standard prototype board/application configuration — the official
 * board-variation point (firmware consolidation convention: constants that
 * tune shared components live here, never inside firmware/esp/components).
 *
 * This is a CAN-bringup prototype on the Lonely Binary ESP32-S3-WROOM-1
 * N16R8 board, with ONLY a SN65HVD230 CAN transceiver attached. It exists
 * to prove module->Hub CAN telemetry works end to end; it does no sensing,
 * no port management, no host USB protocol yet.
 *
 * CAN wiring (set in sdkconfig.defaults, read by the shared cec_comms
 * component via Kconfig):
 *   CAN TX -> ESP IO5 (SN65HVD230 D / TXD)
 *   CAN RX <- ESP IO4 (SN65HVD230 R / RXD)
 *   CONFIG_CEC_CAN_BITRATE_BPS = 125000  (the slope-controlled bench rate;
 *   500k is the platform target once the breakout's Rs is bridged to GND).
 *
 * Bench notes for the SN65HVD230 breakout:
 *   - Bus needs 120 ohm termination at BOTH ends (the breakout usually has
 *     a jumper/footprint for its 120 ohm; the 24-pin's TJA1051 end needs
 *     the Hub-side split or a 120 ohm across CAN_H/CAN_L).
 *   - Rs (slope control) pin: via 10k to GND on most breakouts = limits the
 *     edge rate, fine at 125k. For 500k, bridge Rs straight to GND.
 *   - Both nodes MUST run the SAME bitrate.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* This node's identity on the CAN bus. The Hub is the aggregator/receiver;
 * it is not a sensing module, so it has no module-type telemetry of its own
 * in this prototype. Kept here so a future port-management build has a home
 * for Hub-side constants. */
#define CEC_HUB_INSTANCE        0

/* Cadence (ms) of the "no traffic" heartbeat warning when the bus is silent,
 * and of the 1 Hz human-readable RX summary log. */
#define CEC_HUB_RX_TIMEOUT_MS   1000
#define CEC_HUB_LOG_PERIOD_US   1000000   /* 1 Hz consolidated summary */

/* A port with no telemetry for this long is marked dropped in the aggregator
 * (the module is ~5 Hz, so a few hundred ms of silence is normal). */
#define CEC_HUB_MODULE_TIMEOUT_MS  3000

/*
 * DETECT poke-and-ack — 4 ports, mirroring the real Hub Standard board
 * (hubs/hub-standard: DETECT1..4 on IO4/IO5/IO6/IO7, each its own ADC1 pin +
 * 10 kΩ pull-up + ESD diode). Wire the dev board the same way: per port, the
 * module's RJ-45 pin 8 (DETECT) -> the Hub pin below + a 10 kΩ pull-up to 3V3.
 *
 * Each port pin does BOTH jobs: ADC input to read the static divider (comm
 * class), and a momentary push-pull output to poke. The poke perturbs that one
 * port's line; the module on it acks over CAN (a tapped module), binding it to
 * the port. A module with no pin-8 tap (e.g. the 24-pin) never acks -> safe
 * fallback to legacy/known-but-unbound.
 *
 * CAN moved to IO17/IO18 (sdkconfig) to free IO4/IO5 for DETECT1/DETECT2 -- the
 * real-board pin map. Index = Hub port 0..3 = jacks J2..J5.
 */
#define CEC_HUB_NUM_PORTS         4
#define CEC_HUB_DETECT_PORT_GPIOS { 4, 5, 6, 7 }   /* port 0..3 = IO4/5/6/7 (ADC1 CH3..6) */

#ifdef __cplusplus
}
#endif
