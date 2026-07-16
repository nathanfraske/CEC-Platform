#include "cec_freeze.h"
#include "cec_can.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_attr.h"
#include "esp_timer.h"

static const char *TAG = "freeze";

static cec_freeze_cfg_t s_cfg;
static TaskHandle_t     s_task = NULL;

/* Shared with the ISR hook (single ISR writer for the freeze fields; the task
 * reads). volatile is adequate for this bench use. */
static volatile bool    s_frozen        = false;
static volatile uint8_t s_origin        = 0;
static volatile uint8_t s_cause         = 0;
static volatile uint8_t s_last_seq      = 0xFF;
static volatile uint8_t s_last_origin   = 0xFF;
static volatile int64_t s_instant_us    = 0;
static volatile bool    s_freeze_pending = false;
static volatile bool    s_rearm_pending  = false;

const char *cec_freeze_cause_name(uint8_t cause)
{
    switch (cause) {
    case CEC_FREEZE_CAUSE_MANUAL:      return "manual";
    case CEC_FREEZE_CAUSE_ANOMALY:     return "anomaly";
    case CEC_FREEZE_CAUSE_TRANSIENT:   return "transient";
    case CEC_FREEZE_CAUSE_OVERCURRENT: return "overcurrent";
    case CEC_FREEZE_CAUSE_SHUTDOWN:    return "shutdown";
    default:                           return "other";
    }
}

/* ISR context (called from cec_can's on_rx_done for every frame). Timestamp a
 * FREEZE the instant it lands; defer the heavier work to the task. */
static IRAM_ATTR void freeze_isr_cb(uint32_t id, const uint8_t *data, uint8_t len)
{
    if (id == CEC_FREEZE_ID && len >= 3) {
        uint8_t origin = data[0], cause = data[1], seq = data[2];
        if (origin == s_cfg.self_instance) return;        /* our own echo */
        if (origin == s_last_origin && seq == s_last_seq) return;  /* dup */
        s_last_origin = origin; s_last_seq = seq;
        s_instant_us  = esp_timer_get_time();
        s_origin = origin; s_cause = cause; s_frozen = true;
        s_freeze_pending = true;
        if (s_task) { BaseType_t hpw = pdFALSE; vTaskNotifyGiveFromISR(s_task, &hpw); if (hpw) portYIELD_FROM_ISR(); }
    } else if (id == CEC_REARM_ID && len >= 1) {
        if (data[0] == s_cfg.self_instance) return;
        s_frozen = false; s_rearm_pending = true;
        if (s_task) { BaseType_t hpw = pdFALSE; vTaskNotifyGiveFromISR(s_task, &hpw); if (hpw) portYIELD_FROM_ISR(); }
    }
}

static void freeze_task(void *arg)
{
    (void)arg;
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (s_freeze_pending) {
            s_freeze_pending = false;
            ESP_LOGW(TAG, "FROZEN by port %u (%s) @ %lld us",
                     s_origin, cec_freeze_cause_name(s_cause), (long long)s_instant_us);
            if (s_cfg.on_freeze) s_cfg.on_freeze(s_origin, s_cause, s_instant_us, s_cfg.ctx);
        }
        if (s_rearm_pending) {
            s_rearm_pending = false;
            ESP_LOGI(TAG, "RE-ARM");
            if (s_cfg.on_rearm) s_cfg.on_rearm(s_cfg.ctx);
        }
    }
}

esp_err_t cec_freeze_init(const cec_freeze_cfg_t *cfg)
{
    if (!cfg) return ESP_ERR_INVALID_ARG;
    s_cfg = *cfg;
    if (xTaskCreatePinnedToCore(freeze_task, "cec_freeze", 4096, NULL, 9, &s_task, 0) != pdPASS)
        return ESP_ERR_NO_MEM;
    can_set_isr_event_cb(freeze_isr_cb);
    ESP_LOGI(TAG, "co-capture ready (self port %u)", s_cfg.self_instance);
    return ESP_OK;
}

esp_err_t cec_freeze_trigger(uint8_t cause)
{
    /* The caller has already frozen its own ring; broadcast so everyone else
     * freezes too. Don't re-fire on_freeze locally. */
    s_instant_us = esp_timer_get_time();
    s_origin = s_cfg.self_instance; s_cause = cause; s_frozen = true;
    uint8_t seq = (uint8_t)(s_last_seq + 1); s_last_seq = seq; s_last_origin = s_cfg.self_instance;
    uint8_t d[8] = { s_cfg.self_instance, cause, seq, 0, 0, 0, 0, 0 };
    ESP_LOGW(TAG, "broadcast FREEZE (cause %s)", cec_freeze_cause_name(cause));
    return can_send_frame(CEC_FREEZE_ID, d, sizeof(d));
}

esp_err_t cec_freeze_rearm(void)
{
    s_frozen = false;
    uint8_t seq = (uint8_t)(s_last_seq + 1); s_last_seq = seq;
    uint8_t d[8] = { s_cfg.self_instance, seq, 0, 0, 0, 0, 0, 0 };
    /* Re-arm locally too. */
    s_rearm_pending = true;
    if (s_task) xTaskNotifyGive(s_task);
    ESP_LOGI(TAG, "broadcast RE-ARM");
    return can_send_frame(CEC_REARM_ID, d, sizeof(d));
}

bool    cec_freeze_is_frozen(void)  { return s_frozen; }
uint8_t cec_freeze_origin(void)     { return s_origin; }
uint8_t cec_freeze_cause(void)      { return s_cause; }
int64_t cec_freeze_instant_us(void) { return s_instant_us; }
