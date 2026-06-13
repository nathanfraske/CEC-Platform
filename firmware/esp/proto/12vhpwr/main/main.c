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
#include <stdlib.h>
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

/* Set while a `burst` capture is running so the TelePlot loop yields the
 * FPGA link to the tight capture loop. */
static volatile bool s_capturing = false;

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
        if (c->label == NULL) {
            printf("  ch%-2d  (unconnected)         (raw %+6d, %+7.4f Vadc)\n",
                   ch + 1, f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
            continue;
        }
        printf("  %-5s %+9.4f %-4s (raw %+6d, %+7.4f Vadc)\n",
               c->label, proto_channel_phys(ch, f.code[ch]), proto_kind_unit(c->kind),
               f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
    }
    return 0;
}

/* Capture N frames at the FPGA rate (~50 kHz) into RAM, then dump a CSV
 * block (us offset, seq, calibrated channels) for host plotting. The 50 kHz
 * stream is too fast to send live over USB-CDC (text ~6 MB/s vs ~1 MB/s),
 * so this grabs a finite window and dumps it afterward. The us/seq columns
 * reveal the true captured rate and any dropped frames. Usage: `burst [N]`
 * (default 2048; ~41 ms window). */
static int cli_cmd_burst(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : 2048;
    if (n < 1)    n = 1;
    if (n > 8192) n = 8192;

    struct cap { int64_t us; cec_fpga_frame_t f; };
    struct cap *buf = malloc((size_t)n * sizeof(*buf));
    if (buf == NULL) { printf("burst: out of memory for %d frames\n", n); return 1; }

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));              /* let the TelePlot loop pause */
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2); /* min preemption jitter while capturing */
    int  got  = 0;
    bool dead = false;
    int64_t t0 = esp_timer_get_time();
    for (; got < n && !dead; got++) {
        uint32_t spin = 0;
        while (!cec_fpga_link_poll()) {
            if (++spin > 2000000u) { dead = true; break; }   /* no DRDY -> bail */
        }
        if (dead || cec_fpga_link_read(&buf[got].f) != ESP_OK) break;
        buf[got].us = esp_timer_get_time() - t0;
    }
    vTaskPrioritySet(NULL, old_prio);          /* restore before the slow dump */

    /* Dump with the link still owned (TelePlot stays paused) so the CSV block
     * prints clean -- no live ">..." lines interleaved into it. Markers
     * (===) bracket the block so it is trivial to extract from a serial log. */
    int64_t span = got ? buf[got - 1].us : 0;
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# burst: %d frames in %lld us (~%.1f kHz)\n",
           got, span, span ? 1000.0 * (got - 1) / span : 0.0);
    printf("us,seq");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    for (int i = 0; i < got; i++) {
        printf("%lld,%u", buf[i].us, buf[i].f.seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].f.code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    s_capturing = false;
    free(buf);
    return 0;
}

/* Pull the FPGA's native-rate capture ring in one shot: hold MOSI high
 * (buffered reads), discard the ARM read, then read N frames straight out of
 * BRAM and dump a CSV. Unlike `burst` (ESP-paced, ~12 kHz), this is the FPGA's
 * full native rate -- uniform and gap-free (the seq column is consecutive).
 * N <= PROTO_RING_DEPTH. Usage: `fastburst [N]` (default = full ring). */
static int cli_cmd_fastburst(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : PROTO_RING_DEPTH;
    if (n < 1)                n = 1;
    if (n > PROTO_RING_DEPTH) n = PROTO_RING_DEPTH;

    cec_fpga_frame_t *buf = malloc((size_t)n * sizeof(*buf));
    if (buf == NULL) { printf("fastburst: out of memory for %d frames\n", n); return 1; }

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2);
    cec_fpga_frame_t armf;
    cec_fpga_link_read_buffered(&armf);       /* ARM: freeze ring at oldest (discard) */
    int got = 0;
    for (; got < n; got++)
        if (cec_fpga_link_read_buffered(&buf[got]) != ESP_OK) break;
    vTaskPrioritySet(NULL, old_prio);
    s_capturing = false;

    int gaps = 0, badhdr = 0;
    for (int i = 0; i < got; i++) {
        if (!buf[i].header_ok) badhdr++;
        if (i && buf[i].seq != (uint8_t)(buf[i - 1].seq + 1)) gaps++;
    }
    const double us_per = 1.0e6 / (double)PROTO_NATIVE_HZ;
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# fastburst: %d frames @ ~%d kHz native, %d seq-gaps, %d bad-hdr; "
           "us = idx x %.2f us (nominal 1/%d kHz)\n",
           got, PROTO_NATIVE_HZ / 1000, gaps, badhdr, us_per, PROTO_NATIVE_HZ / 1000);
    printf("us,seq");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    for (int i = 0; i < got; i++) {
        printf("%.1f,%u", i * us_per, buf[i].seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    free(buf);
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "frame",     "pull + dump one FPGA frame (header, seq, V1..V8)", cli_cmd_frame },
    { "burst",     "ESP-paced capture [N] frames to RAM, dump CSV (~12 kHz)", cli_cmd_burst },
    { "fastburst", "FPGA ring readout [N] at the full native rate (uniform)", cli_cmd_fastburst },
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
        if (s_capturing) {                 /* a `burst` owns the link */
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
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
            if (PROTO_CH_CAL[ch].label == NULL) continue;   /* unconnected channel */
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
