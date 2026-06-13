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
#include "cec_filters.h"

static const char *TAG = "12vhpwr_proto";

/* DRDY idle-poll delay. Must be >= 1 tick so the idle task gets to run
 * (the task watchdog watches it): pdMS_TO_TICKS(1) rounds to 0 at the
 * default 100 Hz tick rate, and vTaskDelay(0) never yields -> a low DRDY
 * (FPGA not pacing yet) spins the loop at 100% and starves IDLE -> TWDT.
 * One tick (10 ms @ 100 Hz) is far below the ~200 ms frame period. */
#define PROTO_DRDY_POLL_TICKS  1

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
        const proto_ch_cal_t *c = &PROTO_CH_CAL[ch];
        printf("  %-5s %+9.4f %-4s (raw %+6d, %+7.4f Vadc)\n",
               c->label, proto_channel_phys(ch, f.code[ch]), proto_kind_unit(c->kind),
               f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
    }
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "frame", "pull + dump one FPGA frame (header, seq, V1..V8)", cli_cmd_frame },
};

#if !CONFIG_CEC_PROTO_RAW_CONSOLE
/* Rolling-median de-glitch for the median-flagged (steady) channels. */
#define PROTO_MEDIAN_WIN 5
static float    s_med_buf[CEC_FPGA_FRAME_CHANNELS][PROTO_MEDIAN_WIN];
static median_t s_med[CEC_FPGA_FRAME_CHANNELS];

/* TelePlot streaming loop: calibrated channels (volts/amps per PROTO_CH_CAL)
 * plus seq. The rail is median-filtered to reject its per-channel glitch. */
static void teleplot_loop(void)
{
    ESP_LOGI(TAG, "TelePlot loop: waiting on DRDY");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        median_init(&s_med[ch], s_med_buf[ch], PROTO_MEDIAN_WIN);
    while (1) {
        if (!cec_fpga_link_poll()) {
            vTaskDelay(PROTO_DRDY_POLL_TICKS);
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
            float v = proto_channel_phys(ch, f.code[ch]);
            if (PROTO_CH_CAL[ch].median) v = median_update(&s_med[ch], v);
            teleplot_emit_t(PROTO_CH_CAL[ch].label, now_ms, v);
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
            vTaskDelay(PROTO_DRDY_POLL_TICKS);
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
    ESP_LOGI(TAG, "app_main: start (proto bring-up)");

    cec_fpga_link_config_t link_cfg;
    cec_config_fpga_link(&link_cfg);
    /* Non-fatal: a stuck/failed FPGA link must not boot-loop the board
     * via ESP_ERROR_CHECK -- log and continue so the console stays up
     * and the failing step is visible. */
    esp_err_t link_err = cec_fpga_link_init(&link_cfg);
    if (link_err != ESP_OK) {
        ESP_LOGE(TAG, "cec_fpga_link_init failed: %s", esp_err_to_name(link_err));
    } else {
        ESP_LOGI(TAG, "app_main: fpga link up");
    }

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
