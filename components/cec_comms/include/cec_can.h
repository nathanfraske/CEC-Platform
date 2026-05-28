#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "cec_state.h"

#define CAN_TX_GPIO  4
#define CAN_RX_GPIO  15

// Frame ID scheme (see EPS-FIRMWARE-SPEC.md)
#define CAN_ID_ANOMALY_BASE    0x100
#define CAN_ID_TELEMETRY_BASE  0x200
#define CAN_ID_COMMAND_BASE    0x300
#define CAN_ID_RESPONSE_BASE   0x400

// Telemetry payload layout (8 bytes):
//  [0] module type
//  [1] module instance
//  [2..3] cable 0 current, int16 milliamps (little-endian)
//  [4..5] cable 1 current, int16 milliamps
//  [6] status flags
//  [7] board temp, int8 deg C

// Install and start the TWAI driver.
//   loopback = true  -> self-test mode (NO_ACK). TX goes on the wire
//                       but doesn't require another node to ACK.
//                       Bench-safe when no Hub is on the bus yet.
//                       NOTE: ESP32-S3's TWAI controller has no
//                       hardware loopback, so on_rx_done does NOT
//                       fire on our own TX in this mode. Verify with
//                       a scope, USB-CAN dongle, or once the Hub is
//                       on the bus.
//   loopback = false -> normal mode: TX on the wire, ACK required
//                       from another node. Production / once Hub is
//                       up.
// In either mode an on_state_change callback auto-recovers from
// bus-off so the controller doesn't park permanently after a fault.
esp_err_t can_init(bool loopback);

// Send a telemetry frame from the current shared state snapshot.
esp_err_t can_send_telemetry(uint8_t module_type, uint8_t module_id,
                             const float current_a[CEC_NUM_CABLES],
                             uint8_t status_flags, float board_temp_c);

// Send a high-priority anomaly frame.
esp_err_t can_send_anomaly(uint8_t module_type, uint8_t module_id,
                           uint8_t status_flags);

// Cumulative count of frames received since can_init. In loopback mode
// each successful TX increments this; in normal mode it only ticks on
// frames from other nodes.
uint32_t can_get_rx_count(void);

void can_stop(void);
