/*
 * TelePlot output helpers.
 *
 * Emits lines in the TelePlot serial format. Each emitted line starts
 * with '>' and is ignored by any consumer that isn't TelePlot, so it
 * coexists cleanly with ESP_LOG output on the same stream.
 *
 * Two transports are supported:
 *   - Default: writes go through printf/stdio - whichever stream the
 *     IDF console is bound to (USB Serial-JTAG on this project).
 *   - After cec_telemetry_init_uart() succeeds: writes go directly via
 *     uart_write_bytes() on the configured UART. ESP_LOG and CLI stay
 *     on the IDF console; only TelePlot output diverts. Use this when
 *     a dedicated higher-rate transport (e.g. the CH340K UART USB-C on
 *     this board) is wired up for burst dumps + telemetry.
 *
 * Format reference: https://github.com/nesnes/teleplot
 *   >name:value\n                emits a sample with host-side timestamp
 *   >name:time_ms:value\n        emits a sample with explicit timestamp
 *
 * Parity with the 24-pin module's cec_teleplot.h.
 */

#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "cec_state.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Install the UART driver and reroute every subsequent TelePlot emit
 * through it (TX only - RX_PIN may be UART_PIN_NO_CHANGE). Idempotent.
 * If this is not called, TelePlot output continues to go via printf.
 *
 * tx_buffer_size: TX ring depth in bytes. Sized so burst dumps queue
 * meaningful chunks before uart_write_bytes blocks; 16 KB is a good
 * starting point at 2 Mbps.
 */
esp_err_t cec_telemetry_init_uart(int uart_port,
                                  int tx_pin, int rx_pin,
                                  int baud_rate,
                                  size_t tx_buffer_size);

/*
 * Write a pre-formatted byte buffer into the telemetry stream. Used
 * by cec_capture's burst dump where building one printf per row is
 * too slow. Blocks when the UART TX ring is full (or via stdio when
 * UART isn't initialized).
 */
void teleplot_write_raw(const char *buf, size_t n);

/*
 * Emit a TelePlot sample. TelePlot timestamps it on receipt.
 */
void teleplot_emit(const char *name, float value);

/*
 * Emit a TelePlot sample with an explicit timestamp in milliseconds.
 * Use when sample timing must be precise (e.g. burst capture replay).
 */
void teleplot_emit_t(const char *name, int64_t time_ms, float value);

/*
 * EPS-specific helper: emit a full state snapshot (both currents,
 * optional raw values, temp, load state, status flags). Uses
 * teleplot_emit_t with the state->timestamp_us.
 */
void teleplot_emit_state(const cec_shared_state_t *state, bool include_raw);

#ifdef __cplusplus
}
#endif
