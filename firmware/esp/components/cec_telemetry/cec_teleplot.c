/*
 * TelePlot output helpers — shared superset. The transport core is the
 * eps lineage (parameterized UART init, write_raw backend, the
 * field-debugged UART_SCLK_APB pin — UART_SCLK_DEFAULT can resolve to
 * the REF_TICK/XTAL the bootloader leaves configured on ESP32-S3,
 * putting the baud divider far off and feeding the host garbage); the
 * 24-pin lineage contributes teleplot_writef and the truncation clamp
 * on every formatted emit.
 */

#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>
#include "sdkconfig.h"
#include "esp_check.h"
#include "esp_log.h"
#include "cec_teleplot.h"

#if CONFIG_CEC_TELEMETRY_UART0
#include "driver/uart.h"
#endif

static const char *TAG = "cec_teleplot";

#if CONFIG_CEC_TELEMETRY_UART0
/* -1 = transport unconfigured, fall back to stdio. >= 0 = UART port
 * that telemetry writes go to. */
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
#else  /* !CONFIG_CEC_TELEMETRY_UART0 */
esp_err_t cec_telemetry_init_uart(int uart_port,
                                  int tx_pin, int rx_pin,
                                  int baud_rate,
                                  size_t tx_buffer_size)
{
    (void)uart_port; (void)tx_pin; (void)rx_pin;
    (void)baud_rate; (void)tx_buffer_size;
    ESP_LOGW(TAG, "UART transport compiled out (CONFIG_CEC_TELEMETRY_UART0=n); "
                  "TelePlot stays on stdio");
    return ESP_ERR_NOT_SUPPORTED;
}
#endif /* CONFIG_CEC_TELEMETRY_UART0 */

void teleplot_write_raw(const char *buf, size_t n)
{
    if (n == 0) return;
#if CONFIG_CEC_TELEMETRY_UART0
    if (s_uart_port >= 0) {
        uart_write_bytes((uart_port_t)s_uart_port, buf, n);
        return;
    }
#endif
    fwrite(buf, 1, n, stdout);
    fflush(stdout);   /* USB-CDC console: push each line out now, not on buffer-fill */
}

/* Clamp snprintf's documented "I would have written N bytes" return so
 * we never read past the formatting buffer on truncation. */
static size_t clamp_len(int n, size_t cap)
{
    if (n <= 0) return 0;
    return ((size_t)n < cap) ? (size_t)n : cap - 1;
}

void teleplot_emit(const char *name, float value)
{
    char buf[80];
    int n = snprintf(buf, sizeof(buf), ">%s:%.6f\n", name, value);
    teleplot_write_raw(buf, clamp_len(n, sizeof(buf)));
}

void teleplot_emit_t(const char *name, int64_t time_ms, float value)
{
    char buf[96];
    int n = snprintf(buf, sizeof(buf), ">%s:%" PRId64 ":%.6f\n",
                     name, time_ms, value);
    teleplot_write_raw(buf, clamp_len(n, sizeof(buf)));
}

void teleplot_writef(const char *fmt, ...)
{
    char buf[192];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    teleplot_write_raw(buf, clamp_len(n, sizeof(buf)));
}
