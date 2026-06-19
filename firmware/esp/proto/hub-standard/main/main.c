/*
 * CEC Hub Standard prototype — CAN receiver bring-up.
 *
 * Runs on the Lonely Binary ESP32-S3-WROOM-1 N16R8 with a SN65HVD230 CAN
 * transceiver on IO5 (TX) / IO4 (RX) and nothing else attached. Its only
 * job is to prove module->Hub CAN telemetry end to end:
 *
 *   - Bring TWAI up in NORMAL mode (not self-test). In normal mode this node
 *     ACKs every frame on the bus, which is exactly what the 24-pin module
 *     needs so its transmits complete (a lone transmitter with no ACKer
 *     bus-offs). So just powering this Hub on lets the 24-pin's CAN succeed.
 *   - Drain received frames, decode the 3-frame rail-telemetry burst
 *     (cec_telem.h: RAILS_V 0x200, RAILS_I 0x201, STATUS 0x202), and on each
 *     completed burst (STATUS frame) emit the decoded rails to TelePlot +
 *     a 1 Hz human-readable summary, both over the USB console.
 *   - If the bus goes silent, warn once a second with the rx / bus-off
 *     counts so a wiring / termination / bitrate mismatch is obvious.
 *
 * The shared cec_comms RX ISR already logs every raw frame via ESP_EARLY_LOG
 * and posts it to the can_receive() queue; this app is the task-side drain +
 * decode. Bitrate + pins come from sdkconfig.defaults (Kconfig).
 */

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "cec_can.h"
#include "cec_telem.h"
#include "cec_teleplot.h"
#include "cec_config.h"

static const char *TAG = "hub_main";

/* Friendly name for a module-type byte (cec_state.h IDs). */
static const char *module_name(uint8_t t)
{
    switch (t) {
    case CEC_MODULE_TYPE_ATX24: return "ATX24";
    case CEC_MODULE_TYPE_EPS:   return "EPS";
    default:                    return "?";
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "CEC Hub Standard prototype - CAN receiver");
    ESP_LOGI(TAG, "Transceiver SN65HVD230; CAN TX=IO%d RX=IO%d @ %d bps",
             CONFIG_CEC_CAN_TX_GPIO, CONFIG_CEC_CAN_RX_GPIO,
             CONFIG_CEC_CAN_BITRATE_BPS);
    ESP_LOGI(TAG, "TelePlot of received telemetry on the native USB console");
    ESP_LOGI(TAG, "===========================================");

    /* NORMAL mode (loopback=false): this node ACKs the bus so a module's
     * transmit completes. Do NOT use self-test here -- the whole point of
     * the Hub is to be the other end that ACKs. */
    esp_err_t err = can_init(false);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "can_init failed: %s -- no RX loop", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "CAN up (normal mode, ACKing). Waiting for module telemetry...");
    ESP_LOGW(TAG, "Bench reminder: 120 ohm termination at BOTH bus ends; "
                  "both nodes at %d bps; SN65HVD230 Rs->GND for 500k.",
             CONFIG_CEC_CAN_BITRATE_BPS);

    /* Accumulates the 3 subframes of one module's burst. RAILS_V / RAILS_I
     * each fill half of t; the STATUS frame completes it and triggers the
     * emit. */
    cec_telem_t t;
    memset(&t, 0, sizeof(t));

    uint32_t bursts = 0;
    int64_t  last_log_us = esp_timer_get_time() - CEC_HUB_LOG_PERIOD_US;

    while (1) {
        uint32_t id = 0;
        uint8_t  len = 0;
        uint8_t  data[8];

        esp_err_t r = can_receive(&id, data, &len, CEC_HUB_RX_TIMEOUT_MS);
        if (r == ESP_ERR_TIMEOUT) {
            /* Silence: make a wiring / bitrate / termination problem loud. */
            ESP_LOGW(TAG,
                "no CAN frames in %d ms (rx=%u bus_off=%u). Check wiring / "
                "termination / matching bitrate.",
                CEC_HUB_RX_TIMEOUT_MS,
                (unsigned)can_get_rx_count(),
                (unsigned)can_get_bus_off_count());
            continue;
        }
        if (r != ESP_OK) {
            continue;  /* INVALID_STATE etc.; ISR already logged anything real */
        }

        /* Decode into t. Non-telemetry IDs (anomaly/command) return false and
         * are ignored here -- the ISR still logged them raw. */
        if (!cec_telem_unpack(id, data, len, &t)) {
            continue;
        }

        /* The STATUS frame is the last of the 3-frame burst -> snapshot. */
        if (id != CEC_TELEM_ID_STATUS) {
            continue;
        }
        bursts++;

        /* TelePlot the decoded rails (rx_* names so a combined capture can
         * tell Hub-received series from a module's own local series). */
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

        /* 1 Hz human-readable line so the console is readable without a
         * TelePlot client attached. */
        int64_t now = esp_timer_get_time();
        if (now - last_log_us >= CEC_HUB_LOG_PERIOD_US) {
            last_log_us = now;
            ESP_LOGI(TAG,
                "[%s/0x%02x seq=%u] 12V %.2fV/%.2fA  5V %.2fV/%.2fA  "
                "3V3 %.2fV/%.2fA  5VSB %.2fV/%.2fA  P=%.1fW T=%.0fC "
                "PS_ON=%d PWR_OK=%d  bursts=%u rx=%u boff=%u",
                module_name(t.module_type), t.module_type, t.seq,
                t.v[CEC_TELEM_RAIL_12V],  t.i[CEC_TELEM_RAIL_12V],
                t.v[CEC_TELEM_RAIL_5V],   t.i[CEC_TELEM_RAIL_5V],
                t.v[CEC_TELEM_RAIL_3V3],  t.i[CEC_TELEM_RAIL_3V3],
                t.v[CEC_TELEM_RAIL_5VSB], t.i[CEC_TELEM_RAIL_5VSB],
                t.p_total_w, t.temp_c, t.ps_on, t.pwr_ok,
                (unsigned)bursts,
                (unsigned)can_get_rx_count(),
                (unsigned)can_get_bus_off_count());
        }
    }
}
