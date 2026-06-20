/*
 * CEC Hub Standard prototype — CAN receiver + CAN-OTA bridge.
 *
 * Runs on the Lonely Binary ESP32-S3-WROOM-1 N16R8 with a SN65HVD230 CAN
 * transceiver on IO5 (TX) / IO4 (RX). Two jobs:
 *
 *  1. RECEIVE telemetry: bring TWAI up in NORMAL mode so it ACKs the bus
 *     (which lets the 24-pin's transmits complete), drain can_receive(),
 *     decode the 3-frame rail-telemetry burst (cec_telem.h), and emit the
 *     decoded rails to TelePlot + a 1 Hz summary over the USB console. This
 *     runs in display_task.
 *
 *  2. BRIDGE a firmware update over CAN: the `ota` console command receives
 *     a new image from the host over USB (hex lines), buffers it in the
 *     N16R8's 8 MB PSRAM, verifies its CRC32, then streams it to the 24-pin
 *     over CAN (cec_canota). The 24-pin writes it to its inactive OTA slot
 *     and reboots. ESP32 has no ROM CAN bootloader, so this is the only way
 *     to "flash over CAN": an application OTA bridged through the Hub.
 *     Host side: firmware/tools/can_ota_push.py.
 *
 * Bitrate + pins come from sdkconfig.defaults (Kconfig); 125 kbps to match
 * the 24-pin (the SN65HVD230 breakout bus-offs at 500k unless Rs->GND).
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"

#include "cec_can.h"
#include "cec_telem.h"
#include "cec_canota.h"
#include "cec_pokeack.h"
#include "cec_cli.h"
#include "cec_teleplot.h"
#include "cec_config.h"

static const char *TAG = "hub_main";

/* The aggregator loop runs here; the `ota`/`detect` commands suspend it for
 * the duration so they own can_receive(). */
static TaskHandle_t s_display_task = NULL;

/* ---------------- multi-module aggregator ----------------
 *
 * One decoded telemetry record per port (instance), demuxed by the CAN ID
 * block (cec_telem_id_instance). On each module's STATUS frame (burst
 * complete) the Hub emits the consolidated USB output; a 1 Hz summary lists
 * every active port; a port that goes quiet past CEC_HUB_MODULE_TIMEOUT_MS is
 * marked dropped. */
static cec_telem_t s_mod[CEC_MAX_MODULES];
static int64_t     s_last_us[CEC_MAX_MODULES];
static bool        s_seen[CEC_MAX_MODULES];
static uint32_t    s_bursts[CEC_MAX_MODULES];

/* Per-burst consolidated output for one port: namespaced TelePlot series +
 * one parseable CSV record line (legend printed once at boot). */
static void emit_module(uint8_t inst)
{
    cec_telem_t *m = &s_mod[inst];
    char name[28];
    for (int c = 0; c < CEC_TELEM_NUM_RAILS; c++) {
        const char *lbl = cec_telem_chan_label(m->module_type, c);
        snprintf(name, sizeof(name), "m%u_%s_v", inst, lbl); teleplot_emit(name, m->v[c]);
        snprintf(name, sizeof(name), "m%u_%s_i", inst, lbl); teleplot_emit(name, m->i[c]);
    }
    snprintf(name, sizeof(name), "m%u_temp_c", inst); teleplot_emit(name, m->temp_c);
    snprintf(name, sizeof(name), "m%u_p",      inst); teleplot_emit(name, m->p_total_w);

    printf("CECTLM,%lld,%u,0x%02x,%u,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.1f,%.2f,0x%02x\n",
           (long long)(esp_timer_get_time() / 1000), inst, m->module_type, m->seq,
           m->v[0], m->i[0], m->v[1], m->i[1], m->v[2], m->i[2], m->v[3], m->i[3],
           m->temp_c, m->p_total_w, m->flags);
    fflush(stdout);
}

/* 1 Hz human-readable roll-up of every active port. */
static void print_summary(void)
{
    int n = 0; float ptot = 0.0f;
    for (int i = 0; i < CEC_MAX_MODULES; i++) if (s_seen[i]) { n++; ptot += s_mod[i].p_total_w; }

    if (n == 0) {
        ESP_LOGW(TAG, "no modules seen (rx=%u bus_off=%u). Check wiring / termination / bitrate.",
                 (unsigned)can_get_rx_count(), (unsigned)can_get_bus_off_count());
        return;
    }
    ESP_LOGI(TAG, "=== %d module(s) | total P=%.1fW | bus rx=%u boff=%u ===",
             n, ptot, (unsigned)can_get_rx_count(), (unsigned)can_get_bus_off_count());
    for (int i = 0; i < CEC_MAX_MODULES; i++) {
        if (!s_seen[i]) continue;
        cec_telem_t *m = &s_mod[i];
        ESP_LOGI(TAG, "  port%d %-6s seq=%3u  %s=%.2f/%.2fA %s=%.2f/%.2fA %s=%.2f/%.2fA "
                      "%s=%.2f/%.2fA  P=%.1fW T=%.0fC fl=0x%02x b=%u",
                 i, cec_telem_type_name(m->module_type), m->seq,
                 cec_telem_chan_label(m->module_type, 0), m->v[0], m->i[0],
                 cec_telem_chan_label(m->module_type, 1), m->v[1], m->i[1],
                 cec_telem_chan_label(m->module_type, 2), m->v[2], m->i[2],
                 cec_telem_chan_label(m->module_type, 3), m->v[3], m->i[3],
                 m->p_total_w, m->temp_c, m->flags, (unsigned)s_bursts[i]);
    }
}

static void display_task(void *arg)
{
    (void)arg;
    int64_t last_log_us = esp_timer_get_time() - CEC_HUB_LOG_PERIOD_US;

    while (1) {
        uint32_t id = 0; uint8_t len = 0, data[8];
        esp_err_t r = can_receive(&id, data, &len, CEC_HUB_RX_TIMEOUT_MS);
        int64_t now = esp_timer_get_time();

        if (r == ESP_OK && cec_telem_id_is(id)) {
            uint8_t inst = cec_telem_id_instance(id);
            if (inst < CEC_MAX_MODULES) {
                if (!s_seen[inst]) { s_seen[inst] = true; ESP_LOGI(TAG, "module joined on port %u", inst); }
                cec_telem_unpack(id, data, len, &s_mod[inst]);
                s_last_us[inst] = now;
                if (cec_telem_id_sub(id) == CEC_TELEM_SUB_STATUS) { s_bursts[inst]++; emit_module(inst); }
            }
        }

        /* Stale-port dropout (can_receive caps the wait at RX_TIMEOUT_MS, so we
         * re-check at least once a second even with no traffic). */
        for (int i = 0; i < CEC_MAX_MODULES; i++) {
            if (s_seen[i] && (now - s_last_us[i]) > (int64_t)CEC_HUB_MODULE_TIMEOUT_MS * 1000) {
                s_seen[i] = false;
                ESP_LOGW(TAG, "module on port %d dropped (no telemetry for %d ms)",
                         i, CEC_HUB_MODULE_TIMEOUT_MS);
            }
        }
        if (now - last_log_us >= CEC_HUB_LOG_PERIOD_US) { last_log_us = now; print_summary(); }
    }
}

/* ---------------- CAN-OTA bridge (`ota` command) ---------------- */

static int hexnib(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Decode a line of hex (whitespace ignored) into out[], up to outcap bytes.
 * Returns bytes decoded, or -1 on a bad/odd nibble. */
static int decode_hex_line(const char *s, uint8_t *out, size_t outcap)
{
    size_t n = 0;
    while (*s) {
        if (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n') { s++; continue; }
        int hi = hexnib(*s++);
        int lo = hexnib(*s++);
        if (hi < 0 || lo < 0) return -1;
        if (n >= outcap) return -1;
        out[n++] = (uint8_t)((hi << 4) | lo);
    }
    return (int)n;
}

static void ota_progress(size_t sent, size_t total)
{
    static int last_pct = -1;
    int pct = (int)(100ULL * sent / (total ? total : 1));
    if (pct != last_pct && (pct % 5) == 0) {
        printf("OTA: %d%% (%u/%u)\n", pct, (unsigned)sent, (unsigned)total);
        fflush(stdout);
        last_pct = pct;
    }
}

static int cmd_ota(int argc, char **argv)
{
    if (argc < 3) { printf("usage: ota <size_bytes> <crc32_hex>  then send the image as hex lines\n"); return 1; }
    size_t   size = (size_t)strtoul(argv[1], NULL, 0);
    uint32_t want = (uint32_t)strtoul(argv[2], NULL, 16);
    if (size == 0) { printf("OTA ERR: zero size\n"); return 1; }

    uint8_t *img = heap_caps_malloc(size, MALLOC_CAP_SPIRAM);
    if (!img) img = malloc(size);   /* fall back to internal RAM for a small image */
    if (!img) { printf("OTA ERR: alloc %u failed\n", (unsigned)size); return 1; }

    printf("OTA: ready, send %u bytes as hex lines (target crc %08x)\n", (unsigned)size, (unsigned)want);
    fflush(stdout);

    size_t off = 0;
    static char line[600];   /* up to ~256 payload bytes/line */
    while (off < size) {
        if (fgets(line, sizeof(line), stdin) == NULL) { printf("OTA ERR: input EOF @%u\n", (unsigned)off); free(img); return 1; }
        int n = decode_hex_line(line, img + off, size - off);
        if (n < 0) { printf("OTA ERR: bad hex @%u\n", (unsigned)off); free(img); return 1; }
        off += (size_t)n;
    }

    uint32_t got = cec_canota_crc32(img, size);
    if (got != want) { printf("OTA ERR: buffer crc %08x != %08x\n", (unsigned)got, (unsigned)want); free(img); return 1; }
    printf("OTA: buffered + CRC ok; streaming to module over CAN...\n");
    fflush(stdout);

    if (s_display_task) vTaskSuspend(s_display_task);   /* sender owns can_receive() */
    esp_err_t r = cec_canota_send(img, size, ota_progress);
    if (s_display_task) vTaskResume(s_display_task);
    free(img);

    printf("OTA: %s\n", (r == ESP_OK) ? "DONE (module rebooting into new image)" : esp_err_to_name(r));
    return (r == ESP_OK) ? 0 : 1;
}

static int cmd_caninfo(int argc, char **argv)
{
    (void)argc; (void)argv;
    int state = 0; uint16_t txe = 0, rxe = 0; uint32_t txq = 0, berr = 0;
    can_get_info(&state, &txe, &rxe, &txq, &berr);
    printf("CAN state=%d tx_err=%u rx_err=%u bus_err=%u rx=%u bus_off=%u\n",
           state, txe, rxe, (unsigned)berr,
           (unsigned)can_get_rx_count(), (unsigned)can_get_bus_off_count());
    return 0;
}

/* DETECT poke-and-ack: read the comm class off the static divider (the analog
 * sense pin), then poke and try to bind a module to this port. A module with a
 * pin-8 tap acks over CAN; the 24-pin has no tap, so this falls back safely to
 * legacy/known-but-unbound. */
static int cmd_detect(int argc, char **argv)
{
    (void)argc; (void)argv;
    int mv = -1;
    cec_detect_class_t cls = cec_pokeack_read_class(&mv);
    printf("DETECT: %d mV -> %s\n", mv, cec_detect_class_name(cls));
    if (cls == CEC_DETECT_ABSENT) { printf("DETECT: no module on the line (open)\n"); return 0; }
    if (cls == CEC_DETECT_FAULT)  { printf("DETECT: line shorted (fault)\n"); return 1; }

    uint8_t mtype = 0, inst = 0;
    if (s_display_task) vTaskSuspend(s_display_task);   /* binder owns can_receive() */
    bool acked = cec_pokeack_poke_and_bind(200, &mtype, &inst);
    if (s_display_task) vTaskResume(s_display_task);

    if (acked)
        printf("DETECT: poke ACK -> bound module type 0x%02x inst %u to this port\n", mtype, inst);
    else
        printf("DETECT: no poke ack -> legacy module (known-but-unbound; comm class above)\n");
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "ota",     "flash the module over CAN: ota <size> <crc32hex>, then stream hex lines", cmd_ota },
    { "caninfo", "print TWAI controller state + counters",                                   cmd_caninfo },
    { "detect",  "read DETECT comm-class + poke-and-ack bind (falls back to legacy)",        cmd_detect },
};

/* ---------------- app_main ---------------- */

void app_main(void)
{
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "CEC Hub Standard prototype - CAN rx + OTA bridge");
    ESP_LOGI(TAG, "Transceiver SN65HVD230; CAN TX=IO%d RX=IO%d @ %d bps",
             CONFIG_CEC_CAN_TX_GPIO, CONFIG_CEC_CAN_RX_GPIO, CONFIG_CEC_CAN_BITRATE_BPS);
    ESP_LOGI(TAG, "===========================================");

    esp_err_t err = can_init(false);    /* normal mode: ACK the bus for the module */
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "can_init failed: %s -- halting", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "CAN up (normal mode, ACKing). Aggregating up to %d modules; `ota`/`detect` ready.",
             CEC_MAX_MODULES);
    ESP_LOGW(TAG, "Bench: 120 ohm at BOTH bus ends; both nodes at %d bps; Rs->GND for 500k.",
             CONFIG_CEC_CAN_BITRATE_BPS);

    /* Consolidated per-module record legend for a host parser (one line each
     * STATUS frame; greppable by the CECTLM prefix). */
    printf("# CECTLM,ts_ms,port,type,seq,v0,i0,v1,i1,v2,i2,v3,i3,temp_c,p_w,flags\n");
    fflush(stdout);

    xTaskCreatePinnedToCore(display_task, "hub_agg", 4096, NULL, 4, &s_display_task, 1);

    /* DETECT poke-and-ack rig (spec §2.3): ADC read of the divider (comm
     * class) + a poke driver. The 10k pull-up to 3V3 is external; see
     * cec_config.h for the bench wiring. */
    if (cec_pokeack_hub_init(CEC_HUB_DETECT_ADC_GPIO, CEC_HUB_DETECT_POKE_GPIO) == ESP_OK) {
        int mv = -1;
        cec_detect_class_t cls = cec_pokeack_read_class(&mv);
        ESP_LOGI(TAG, "DETECT at boot: %d mV -> %s (use `detect` to poke-and-bind)",
                 mv, cec_detect_class_name(cls));
    }

    /* CLI on the USB console (blocking stdin): `ota` flash bridge + `detect`. */
    cec_cli_init(CLI_COMMANDS, sizeof(CLI_COMMANDS) / sizeof(CLI_COMMANDS[0]));
}
