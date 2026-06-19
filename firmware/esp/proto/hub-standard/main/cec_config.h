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
#define CEC_HUB_LOG_PERIOD_US   1000000   /* 1 Hz summary */

#ifdef __cplusplus
}
#endif
