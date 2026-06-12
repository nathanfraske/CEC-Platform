/* 12vhpwr-proto ESP32-P4 bring-up.
 * SPI master to the GW5A via the shared cec_fpga_link component: poll
 * DRDY, pull an 18-byte frame (0xA5, seq, V1..V8 big-endian).
 *
 * Two output paths (Kconfig CEC_PROTO_RAW_CONSOLE):
 *   - RAW (default until bench step 3 passes): the v0 printf loop,
 *     byte-for-byte — the path verified in simulation.
 *   - TelePlot: eight channels (volts) plus seq through the shared
 *     cec_teleplot engine, ~5 Hz.
 * Either way the cec_cli 'frame' command dumps one frame on demand.
 *
 * Pins per main/cec_config.h (doc section 6.3 / 10).
 * License: Apache-2.0 (CEC-Platform). */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cec_fpga_link.h"
#include "cec_config.h"
#include "cec_teleplot.h"
#include "cec_cli.h"

static const char *TAG = "12vhpwr_proto";

/* ---------------------------- CLI handlers ---------------------------- */

/* Dump one frame on demand (any mode). Reads whatever the fabric has
 * latched; DRDY state is reported rather than awaited so the command
 * never blocks the console. */
static int cli_cmd_frame(int argc, char **argv)
{
    (void)argc; (void)argv;
    bool drdy = cec_fpga_link_poll();
    cec_fpga_frame_t f;
    esp_err_t err = cec_fpga_link_read(&f);
    if (err != ESP_OK) {
        printf("error: %s\n", esp_err_to_name(err));
        return 1;
    }
    printf("drdy=%d header=0x%02x (%s) seq=%u\n",
           drdy ? 1 : 0, f.header, f.header_ok ? "ok" : "BAD", f.seq);
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
        printf("  V%d %+6d (%+8.4f V)\n",
               ch + 1, f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
    }
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "frame", "pull + dump one FPGA frame (header, seq, V1..V8)", cli_cmd_frame },
};

#if !CONFIG_CEC_PROTO_RAW_CONSOLE
/* TelePlot streaming loop: eight channels (volts) plus seq. */
static void teleplot_loop(void)
{
    ESP_LOGI(TAG, "TelePlot loop: waiting on DRDY");
    char name[8];
    while (1) {
        if (!cec_fpga_link_poll()) {
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }
        cec_fpga_frame_t f;
        if (cec_fpga_link_read(&f) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (!f.header_ok) {
            ESP_LOGW(TAG, "bad header 0x%02x (alignment?)", f.header);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        int64_t now_ms = esp_timer_get_time() / 1000;
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
            snprintf(name, sizeof(name), "v%d", ch + 1);
            teleplot_emit_t(name, now_ms, (float)(f.code[ch] * PROTO_LSB_VOLTS));
        }
        teleplot_emit_t("seq", now_ms, (float)f.seq);
        vTaskDelay(pdMS_TO_TICKS(200));   /* ~5 Hz; FPGA keeps pacing */
    }
}
#else
/* v0 raw console loop, byte-for-byte (the simulation-verified path). */
static void raw_console_loop(void)
{
    printf("12vhpwr-proto v0: waiting on DRDY\n");
    while (1) {
        if (!cec_fpga_link_poll()) {
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }
        cec_fpga_frame_t f;
        if (cec_fpga_link_read(&f) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (!f.header_ok) {
            printf("bad header 0x%02x (alignment?)\n", f.header);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        printf("seq %3u |", f.seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
            printf(" V%d %+6d (%+8.4f V)", ch + 1, f.code[ch],
                   f.code[ch] * PROTO_LSB_VOLTS);
        }
        printf("\n");
        vTaskDelay(pdMS_TO_TICKS(200));   /* ~5 Hz console; FPGA keeps pacing */
    }
}
#endif

void app_main(void)
{
    cec_fpga_link_config_t link_cfg;
    cec_config_fpga_link(&link_cfg);
    ESP_ERROR_CHECK(cec_fpga_link_init(&link_cfg));

    esp_err_t cli_err = cec_cli_init(CLI_COMMANDS,
                                     sizeof(CLI_COMMANDS) / sizeof(CLI_COMMANDS[0]));
    if (cli_err != ESP_OK) {
        ESP_LOGW(TAG, "cec_cli_init failed: %s — serial commands unavailable",
                 esp_err_to_name(cli_err));
    }

#if CONFIG_CEC_PROTO_RAW_CONSOLE
    raw_console_loop();
#else
    teleplot_loop();
#endif
}
