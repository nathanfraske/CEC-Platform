/*
 * TelePlot output helpers.
 */

#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "esp_check.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "cec_teleplot.h"

static const char *TAG = "cec_teleplot";

/* -1 = transport unconfigured, fall back to stdio (printf). >= 0 = UART
 * port that telemetry writes go to. */
static int s_uart_port = -1;

esp_err_t cec_telemetry_init_uart(int uart_port,
                                  int tx_pin, int rx_pin,
                                  int baud_rate,
                                  size_t tx_buffer_size)
{
    if (s_uart_port == uart_port) {
        return ESP_OK;
    }
    /* Minimum RX buffer per IDF is UART_HW_FIFO_LEN_DEFAULT. 256 is safe
     * on every chip and we don't actually use RX here.
     *
     * source_clk is pinned to APB explicitly. UART_SCLK_DEFAULT resolves
     * differently across IDF revisions/targets and on ESP32-S3 can
     * still be the REF_TICK / XTAL the bootloader leaves configured,
     * in which case the baud divider lands far off the requested rate
     * and the host sees garbage no matter what baud you ask for. APB
     * (80 MHz at default CPU freq) gives a stable, predictable divisor
     * across the standard baud range. */
    const uart_config_t cfg = {
        .baud_rate  = baud_rate,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_APB,
    };
    ESP_RETURN_ON_ERROR(uart_driver_install((uart_port_t)uart_port,
                                            256, tx_buffer_size,
                                            0, NULL, 0),
                        TAG, "uart_driver_install");
    ESP_RETURN_ON_ERROR(uart_param_config((uart_port_t)uart_port, &cfg),
                        TAG, "uart_param_config");
    ESP_RETURN_ON_ERROR(uart_set_pin((uart_port_t)uart_port, tx_pin, rx_pin,
                                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE),
                        TAG, "uart_set_pin");
    s_uart_port = uart_port;
    ESP_LOGI(TAG, "UART%d up @ %d bps, TX=%d RX=%d, tx_buf=%u",
             uart_port, baud_rate, tx_pin, rx_pin, (unsigned)tx_buffer_size);
    return ESP_OK;
}

void teleplot_write_raw(const char *buf, size_t n)
{
    if (n == 0) return;
    if (s_uart_port >= 0) {
        uart_write_bytes((uart_port_t)s_uart_port, buf, n);
    } else {
        fwrite(buf, 1, n, stdout);
    }
}

void teleplot_emit(const char *name, float value)
{
    char buf[80];
    int n = snprintf(buf, sizeof(buf), ">%s:%.6f\n", name, value);
    if (n > 0) teleplot_write_raw(buf, (size_t)n);
}

void teleplot_emit_t(const char *name, int64_t time_ms, float value)
{
    char buf[96];
    int n = snprintf(buf, sizeof(buf), ">%s:%" PRId64 ":%.6f\n",
                     name, time_ms, value);
    if (n > 0) teleplot_write_raw(buf, (size_t)n);
}

void teleplot_emit_state(const cec_state_t *state, bool include_raw)
{
    int64_t t_ms = state->timestamp_us / 1000;

    teleplot_emit_t("eps1_current", t_ms, state->current_a[0]);
    teleplot_emit_t("eps2_current", t_ms, state->current_a[1]);

    if (include_raw) {
        teleplot_emit_t("eps1_raw", t_ms, state->current_raw_a[0]);
        teleplot_emit_t("eps2_raw", t_ms, state->current_raw_a[1]);
    }

    teleplot_emit_t("board_temp", t_ms, state->board_temp_c);
    teleplot_emit_t("load_state", t_ms, (float)state->load_state);
    teleplot_emit_t("flags",      t_ms, (float)state->status_flags);
}
