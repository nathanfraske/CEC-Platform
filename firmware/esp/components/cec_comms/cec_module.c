#include "cec_module.h"
#include "cec_can.h"
#include "cec_canota.h"
#include "cec_pokeack.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "cec_module";

static cec_module_cfg_t s_cfg;
static volatile bool    s_ota_active = false;

static void ota_active_cb(bool active) { s_ota_active = active; }

static void telemetry_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "%s telemetry on port %u every %u ms",
             cec_telem_type_name(s_cfg.module_type), s_cfg.module_id,
             (unsigned)s_cfg.period_ms);
    uint8_t seq = 0;
    while (1) {
        if (s_ota_active) {                 /* hold off telemetry during a CAN-OTA */
            vTaskDelay(pdMS_TO_TICKS(s_cfg.period_ms));
            continue;
        }
        cec_telem_t t;
        memset(&t, 0, sizeof(t));
        if (s_cfg.read) s_cfg.read(&t, s_cfg.ctx);   /* board fills channels/temp/flags */
        t.instance    = s_cfg.module_id;
        t.module_type = s_cfg.module_type;
        t.seq         = seq++;

        uint8_t f[8];
        for (uint8_t sub = 0; sub < CEC_TELEM_NUM_SUB; sub++) {
            uint32_t id = cec_telem_pack(&t, sub, f);
            can_send_frame(id, f, sizeof(f));
        }
        vTaskDelay(pdMS_TO_TICKS(s_cfg.period_ms));
    }
}

esp_err_t cec_module_start(const cec_module_cfg_t *cfg)
{
    if (!cfg || !cfg->read || cfg->period_ms == 0) return ESP_ERR_INVALID_ARG;
    s_cfg = *cfg;

    /* Confirm a freshly CAN-flashed image so the bootloader keeps it. */
    cec_canota_mark_valid();

    /* Normal mode: the Hub ACKs our frames. Without a Hub the controller
     * bus-offs and auto-recovers (cec_can on_state_change). */
    esp_err_t e = can_init(false);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "can_init failed: %s -- no telemetry / CAN-OTA", esp_err_to_name(e));
        return e;
    }

    /* CAN-OTA receiver: the Hub can re-flash this board over CAN. */
    if (cec_canota_receiver_start(ota_active_cb) != ESP_OK)
        ESP_LOGW(TAG, "CAN-OTA receiver failed to start");

    /* Poke-and-ack DETECT responder (inert if detect_tap_gpio < 0). */
    cec_pokeack_responder_start(s_cfg.detect_tap_gpio, s_cfg.module_type, s_cfg.module_id);

    if (xTaskCreatePinnedToCore(telemetry_task, "cec_telem", 4096, NULL, 4, NULL, 1) != pdPASS) {
        ESP_LOGE(TAG, "telemetry task create failed");
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "module runtime up: CAN normal, OTA receiver, poke-ack, telemetry");
    return ESP_OK;
}
