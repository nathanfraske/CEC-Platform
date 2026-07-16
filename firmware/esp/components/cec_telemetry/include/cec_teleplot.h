/*
 * TelePlot output helpers — shared superset (firmware consolidation,
 * Phase G1).
 *
 * Emits lines in the TelePlot serial format. Each emitted line starts
 * with '>' and is ignored by any consumer that isn't TelePlot, so it
 * coexists cleanly with ESP_LOG output on the same stream.
 *
 * Two transports:
 *   - Default: writes go through stdio — whichever stream the IDF
 *     console is bound to (USB Serial-JTAG on the current boards).
 *   - After cec_telemetry_init_uart() succeeds: writes go directly via
 *     uart_write_bytes() on the configured UART. ESP_LOG and CLI stay
 *     on the IDF console; only TelePlot output diverts. Both boards use
 *     this for the CH340K UART USB-C dual-stream setup (steady-state
 *     telemetry + burst dumps at 921600 baud, keeping the heavy traffic
 *     off the CLI wire).
 *
 * The UART transport is compiled behind CONFIG_CEC_TELEMETRY_UART0
 * (both s3 apps enable it in sdkconfig.defaults); with it disabled,
 * cec_telemetry_init_uart returns ESP_ERR_NOT_SUPPORTED and every
 * helper stays on stdio.
 *
 * USB-CDC output bytes are a compatibility contract: existing TelePlot
 * tooling consumes them. The emit formats below are byte-identical to
 * both pre-merge trees.
 *
 * Format reference: https://github.com/nesnes/teleplot
 *   >name:value\n                 — sample with host-side timestamp
 *   >name:time_ms:value\n         — sample with explicit timestamp
 *   any other '>'-prefixed line   — envelope / annotation
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Install the UART driver and reroute every subsequent TelePlot emit
 * through it (TX only — rx_pin may be UART_PIN_NO_CHANGE). Idempotent.
 * If this is not called (or fails, or the transport is compiled out),
 * TelePlot output continues to go via stdio.
 *
 * tx_buffer_size: TX ring depth in bytes. Sized so burst dumps queue
 * meaningful chunks before uart_write_bytes blocks.
 */
esp_err_t cec_telemetry_init_uart(int uart_port,
                                  int tx_pin, int rx_pin,
                                  int baud_rate,
                                  size_t tx_buffer_size);

/*
 * Write a pre-formatted byte buffer into the telemetry stream. Used by
 * cec_capture's burst dump where building one printf per row is too
 * slow. Blocks when the UART TX ring is full (or via stdio when UART
 * isn't initialized).
 */
void teleplot_write_raw(const char *buf, size_t n);

/*
 * Emit a TelePlot sample with no embedded timestamp (TelePlot stamps
 * it on receipt). Prefer the _t variant if a device-side timestamp
 * is meaningful.
 */
void teleplot_emit(const char *name, float value);

/*
 * Emit a TelePlot sample with an explicit timestamp in milliseconds.
 * Use when sample timing must be precise (e.g. burst capture replay
 * alignment against the slow loop).
 */
void teleplot_emit_t(const char *name, int64_t time_ms, float value);

/*
 * Generic printf-style line emit, for non-sample TelePlot output:
 *   teleplot_writef(">BURST_BEGIN:%s:%d_normal+%d_hs:%d\n", ...);
 * Caller provides the leading '>' and trailing newline. Routed to
 * the same backend as the typed helpers above.
 */
void teleplot_writef(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#ifdef __cplusplus
}
#endif
