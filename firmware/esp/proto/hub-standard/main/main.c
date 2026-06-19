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
#include "cec_cli.h"
#include "cec_teleplot.h"
#include "cec_config.h"

static const char *TAG = "hub_main";

/* The telemetry display loop runs here; the `ota` command suspends it for
 * the duration of a transfer so the OTA sender owns can_receive(). */
static TaskHandle_t s_display_task = NULL;

/* Friendly name for a module-type byte (cec_state.h IDs). */
static const char *module_name(uint8_t t)
{
    switch (t) {
    case CEC_MODULE_TYPE_ATX24: return "ATX24";
    case CEC_MODULE_TYPE_EPS:   return "EPS";
    default:                    return "?";
    }
}

/* ---------------- telemetry receive / display ---------------- */

static void display_task(void *arg)
{
    (void)arg;
    cec_telem_t t;
    memset(&t, 0, sizeof(t));
    uint32_t bursts = 0;
    int64_t  last_log_us = esp_timer_get_time() - CEC_HUB_LOG_PERIOD_US;

    while (1) {
        uint32_t id = 0; uint8_t len = 0, data[8];
        esp_err_t r = can_receive(&id, data, &len, CEC_HUB_RX_TIMEOUT_MS);
        if (r == ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "no CAN frames in %d ms (rx=%u bus_off=%u). Check wiring / "
                          "termination / matching bitrate.",
                     CEC_HUB_RX_TIMEOUT_MS, (unsigned)can_get_rx_count(),
                     (unsigned)can_get_bus_off_count());
            continue;
        }
        if (r != ESP_OK) continue;
        if (!cec_telem_unpack(id, data, len, &t)) continue;   /* non-telemetry: ignore */
        if (id != CEC_TELEM_ID_STATUS) continue;              /* STATUS completes a burst */
        bursts++;

        teleplot_emit("rx_v_12v",   t.v[CEC_TELEM_RAIL_12V]);
        teleplot_emit("rx_v_5v",    t.v[CEC_TELEM_RAIL_5V]);
        teleplot_emit("rx_v_3v3",   t.v[CEC_TELEM_RAIL_3V3]);
        teleplot_emit("rx_v_5vsb",  t.v[CEC_TELEM_RAIL_5VSB]);
        teleplot_emit("rx_i_12v",   t.i[CEC_TELEM_RAIL_12V]);
        teleplot_emit("rx_i_5v",    t.i[CEC_TELEM_RAIL_5V]);
        teleplot_emit("rx_i_3v3",   t.i[CEC_TELEM_RAIL_3V3]);
        teleplot_emit("rx_i_5vsb",  t.i[CEC_TELEM_RAIL_5VSB]);
        teleplot_emit("rx_temp_c",  t.temp_c);
        teleplot_emit("rx_p_total", t.p_total_w);
        teleplot_emit("rx_ps_on",   t.ps_on  ? 1.0f : 0.0f);
        teleplot_emit("rx_pwr_ok",  t.pwr_ok ? 1.0f : 0.0f);
        teleplot_emit("rx_seq",     (float)t.seq);

        int64_t now = esp_timer_get_time();
        if (now - last_log_us >= CEC_HUB_LOG_PERIOD_US) {
            last_log_us = now;
            ESP_LOGI(TAG,
                "[%s/0x%02x seq=%u] 12V %.2fV/%.2fA  5V %.2fV/%.2fA  3V3 %.2fV/%.2fA  "
                "5VSB %.2fV/%.2fA  P=%.1fW T=%.0fC PS_ON=%d PWR_OK=%d  bursts=%u rx=%u boff=%u",
                module_name(t.module_type), t.module_type, t.seq,
                t.v[CEC_TELEM_RAIL_12V],  t.i[CEC_TELEM_RAIL_12V],
                t.v[CEC_TELEM_RAIL_5V],   t.i[CEC_TELEM_RAIL_5V],
                t.v[CEC_TELEM_RAIL_3V3],  t.i[CEC_TELEM_RAIL_3V3],
                t.v[CEC_TELEM_RAIL_5VSB], t.i[CEC_TELEM_RAIL_5VSB],
                t.p_total_w, t.temp_c, t.ps_on, t.pwr_ok,
                (unsigned)bursts, (unsigned)can_get_rx_count(),
                (unsigned)can_get_bus_off_count());
        }
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

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "ota",     "flash the module over CAN: ota <size> <crc32hex>, then stream hex lines", cmd_ota },
    { "caninfo", "print TWAI controller state + counters",                                   cmd_caninfo },
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
    ESP_LOGI(TAG, "CAN up (normal mode, ACKing). Telemetry display + `ota` bridge ready.");
    ESP_LOGW(TAG, "Bench: 120 ohm at BOTH bus ends; both nodes at %d bps; Rs->GND for 500k.",
             CONFIG_CEC_CAN_BITRATE_BPS);

    xTaskCreatePinnedToCore(display_task, "hub_disp", 4096, NULL, 4, &s_display_task, 1);

    /* CLI on the USB console (blocking stdin) for the `ota` flash bridge. */
    cec_cli_init(CLI_COMMANDS, sizeof(CLI_COMMANDS) / sizeof(CLI_COMMANDS[0]));
}
