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

// Install and start the TWAI driver. Pass loopback=true to self-test
// without a Hub connected.
esp_err_t can_init(bool loopback);

// Send a telemetry frame from the current shared state snapshot.
esp_err_t can_send_telemetry(uint8_t module_type, uint8_t module_id,
                             const float current_a[CEC_NUM_CABLES],
                             uint8_t status_flags, float board_temp_c);

// Send a high-priority anomaly frame.
esp_err_t can_send_anomaly(uint8_t module_type, uint8_t module_id,
                           uint8_t status_flags);

void can_stop(void);
