#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "cec_state.h"

/* TX/RX pins come from Kconfig (CEC_CAN_{TX,RX}_GPIO) — board wiring
 * never lives in a shared component. */

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

// Send an arbitrary classical-CAN frame (id, up to 8 data bytes). Blocks
// until the frame is on the wire so the caller's buffer can go out of
// scope. Used by the rail-telemetry path (cec_telem.h) and any raw sender.
esp_err_t can_send_frame(uint32_t id, const uint8_t *data, uint8_t len);

// Block until a frame is received (from another node) or `timeout_ms`
// elapses, then copy it out. `data` must point to at least 8 bytes.
// Returns ESP_OK, ESP_ERR_TIMEOUT, or ESP_ERR_INVALID_STATE if can_init
// hasn't run. The RX ISR also logs every frame via ESP_EARLY_LOG; this is
// the path for an app (e.g. the Hub) that wants to decode them in a task.
esp_err_t can_receive(uint32_t *out_id, uint8_t *out_data, uint8_t *out_len,
                      uint32_t timeout_ms);

// Cumulative count of frames received since can_init. In loopback mode
// each successful TX increments this; in normal mode it only ticks on
// frames from other nodes.
uint32_t can_get_rx_count(void);

// Cumulative count of bus-off events since can_init. Each one was
// auto-recovered by the on_state_change callback.
uint32_t can_get_bus_off_count(void);

// Enable/disable the per-frame RX ISR log (ESP_EARLY_LOG of every received
// frame). On by default for bring-up; turn it OFF around a high-rate burst
// (e.g. a CAN-OTA transfer streams tens of thousands of frames) so the log
// doesn't flood the console and throttle the transfer.
void can_set_rx_log(bool enable);

// Snapshot the TWAI controller's current state + error counters and
// cumulative bus-error count. Returns ESP_ERR_INVALID_STATE if
// can_init hasn't run. Useful from a debug CLI when bus-off is
// suspected and you want to see the actual error counts climbing.
esp_err_t can_get_info(int *out_state,
                       uint16_t *out_tx_err,
                       uint16_t *out_rx_err,
                       uint32_t *out_tx_queue_remaining,
                       uint32_t *out_bus_err_num);

void can_stop(void);
