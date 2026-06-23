#include "cec_can.h"

#if CEC_CAN_ENABLED

/*
 * Migrated to the IDF 6.x esp_twai_onchip / esp_twai node-handle API.
 * Legacy driver/twai.h is no longer touched here.
 *
 * UNTESTED on hardware: this block does not compile while
 * CEC_CAN_ENABLED is 0. Verify on the bench when the daughterboard /
 * transceiver is attached and the flag is flipped on.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_twai.h"
#include "esp_twai_onchip.h"
#include "esp_log.h"

/* Bus bitrate, TX/RX pins: Kconfig (CEC_CAN_BITRATE_BPS,
 * CEC_CAN_{TX,RX}_GPIO). The bench-vs-production bitrate story (125 k
 * on the slope-controlled Waveshare breakout vs the 500 k platform
 * target) lives in the Kconfig help text. */
#define CAN_BITRATE_BPS        CONFIG_CEC_CAN_BITRATE_BPS
#define CAN_TX_QUEUE_DEPTH     8
#define CAN_TX_TIMEOUT_MS      10

static const char *TAG = "can";
static twai_node_handle_t s_node = NULL;
static bool s_enabled = false;
static volatile uint32_t s_rx_count = 0;
static volatile uint32_t s_bus_off_count = 0;
static volatile bool s_rx_log = true;   /* per-frame RX ISR log (gated for bursts) */
static can_isr_event_cb_t s_isr_event_cb = NULL;   /* cec_freeze ISR hook */

/* Received frames are posted here by the RX ISR for an app to drain via
 * can_receive(). 8 data bytes + id + dlc per slot. */
typedef struct { uint32_t id; uint8_t len; uint8_t data[8]; } can_rx_slot_t;
#define CAN_RX_QUEUE_DEPTH 16
static QueueHandle_t s_rx_queue = NULL;

/*
 * State-change callback (ISR context). Auto-recovers from BUS_OFF by
 * kicking twai_node_recover. Without this the controller stays parked
 * and every subsequent twai_node_transmit logs "node is bus off",
 * which we saw spam at 20 Hz when TX'ing into an unterminated bus.
 * Counts events for diagnostics.
 */
static IRAM_ATTR bool can_on_state_change(twai_node_handle_t handle,
                                          const twai_state_change_event_data_t *edata,
                                          void *user_ctx)
{
    (void)user_ctx;
    if (edata->new_sta == TWAI_ERROR_BUS_OFF) {
        s_bus_off_count++;
        ESP_EARLY_LOGW(TAG, "bus-off entered (#%u), kicking recovery",
                       (unsigned)s_bus_off_count);
        twai_node_recover(handle);
    }
    return false;
}

/*
 * RX callback (ISR context). Logs the id + payload via ESP_EARLY_LOG
 * (ISR-safe) so the user can confirm received frames from idf.py
 * monitor stream. NOTE: on ESP32-S3, no hardware loopback - this only
 * fires for frames from other nodes (Hub, USB-CAN dongle, etc.), not
 * the MCU's own TX in self-test mode.
 */
static IRAM_ATTR bool can_on_rx_done(twai_node_handle_t handle,
                                     const twai_rx_done_event_data_t *edata,
                                     void *user_ctx)
{
    (void)edata; (void)user_ctx;
    uint8_t rx_data[8];
    twai_frame_t rx_frame = {
        .buffer     = rx_data,
        .buffer_len = sizeof(rx_data),
    };
    BaseType_t hpw = pdFALSE;
    if (twai_node_receive_from_isr(handle, &rx_frame) == ESP_OK) {
        s_rx_count++;
        /* ISR-fast event hook (cec_freeze): timestamp a FREEZE the instant it
         * lands, before the slower queue/task path. */
        if (s_isr_event_cb)
            s_isr_event_cb(rx_frame.header.id, rx_data, rx_frame.header.dlc);
        if (s_rx_log) ESP_EARLY_LOGI(TAG,
            "RX id=0x%03x dlc=%u [%02x %02x %02x %02x %02x %02x %02x %02x]",
            (unsigned)rx_frame.header.id,
            (unsigned)rx_frame.header.dlc,
            rx_data[0], rx_data[1], rx_data[2], rx_data[3],
            rx_data[4], rx_data[5], rx_data[6], rx_data[7]);
        /* Hand the frame to any waiting task (can_receive). Best-effort:
         * if the queue is full the oldest backlog is dropped rather than
         * blocking the ISR. */
        if (s_rx_queue) {
            can_rx_slot_t slot = { .id = rx_frame.header.id, .len = rx_frame.header.dlc };
            memcpy(slot.data, rx_data, sizeof(slot.data));
            if (xQueueSendFromISR(s_rx_queue, &slot, &hpw) != pdTRUE) {
                can_rx_slot_t drop;
                xQueueReceiveFromISR(s_rx_queue, &drop, NULL);
                xQueueSendFromISR(s_rx_queue, &slot, &hpw);
            }
        }
    }
    return hpw == pdTRUE;
}

/* Listen-only diagnostic: Kconfig CEC_CAN_DIAG_LISTEN_ONLY (the
 * bus-off triage procedure is its help text). */

esp_err_t can_init(bool loopback)
{
    if (s_node != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_rx_queue == NULL) {
        s_rx_queue = xQueueCreate(CAN_RX_QUEUE_DEPTH, sizeof(can_rx_slot_t));
        if (s_rx_queue == NULL) {
            ESP_LOGE(TAG, "RX queue alloc failed");
            return ESP_ERR_NO_MEM;
        }
    }

    twai_onchip_node_config_t cfg = {
        .io_cfg = {
            .tx                = CONFIG_CEC_CAN_TX_GPIO,
            .rx                = CONFIG_CEC_CAN_RX_GPIO,
            .quanta_clk_out    = GPIO_NUM_NC,
            .bus_off_indicator = GPIO_NUM_NC,
        },
        .bit_timing      = { .bitrate = CAN_BITRATE_BPS },
        .fail_retry_cnt  = 3,
        .tx_queue_depth  = CAN_TX_QUEUE_DEPTH,
    };
    if (loopback) {
        /* Bench self-test (NO_ACK). ESP32-S3's TWAI controller has no
         * hardware loopback bit - twai_ll_set_mode on S3 only writes
         * the LOM (listen-only) and STM (self-test/no-ack) bits, and
         * silently ignores the loopback flag. So on_rx_done will NOT
         * fire on the MCU's own transmitted frames; to actually see
         * TX, you need either the Hub on the bus, a USB-CAN dongle,
         * or a scope. Self-test mode at least lets TX complete
         * without requiring an external ACK so the controller stays
         * happy until the Hub arrives. */
        cfg.flags.enable_self_test = 1;
    }
#if CONFIG_CEC_CAN_DIAG_LISTEN_ONLY
    cfg.flags.enable_listen_only = 1;
    cfg.flags.enable_self_test = 0;  /* listen-only overrides */
#endif

    esp_err_t ret = twai_new_node_onchip(&cfg, &s_node);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "twai_new_node_onchip failed: %s", esp_err_to_name(ret));
        s_node = NULL;
        return ret;
    }
    /* Register callbacks before enable. on_state_change auto-recovers
     * from bus-off; on_rx_done logs inbound frames (Hub, dongle - not
     * the MCU's own TX, ESP32-S3 has no hardware loopback). */
    const twai_event_callbacks_t cbs = {
        .on_rx_done       = can_on_rx_done,
        .on_state_change  = can_on_state_change,
    };
    ret = twai_node_register_event_callbacks(s_node, &cbs, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "twai_node_register_event_callbacks failed: %s",
                 esp_err_to_name(ret));
        twai_node_delete(s_node);
        s_node = NULL;
        return ret;
    }
    ret = twai_node_enable(s_node);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "twai_node_enable failed: %s", esp_err_to_name(ret));
        twai_node_delete(s_node);
        s_node = NULL;
        return ret;
    }
    s_enabled = true;
    ESP_LOGI(TAG, "TWAI node up @ %d bps (%s%s)", CAN_BITRATE_BPS,
             loopback ? "self-test" : "normal",
#if CONFIG_CEC_CAN_DIAG_LISTEN_ONLY
             " + listen-only DIAG"
#else
             ""
#endif
             );
    return ESP_OK;
}

uint32_t can_get_rx_count(void)
{
    return s_rx_count;
}

void can_set_rx_log(bool enable)
{
    s_rx_log = enable;
}

void can_set_isr_event_cb(can_isr_event_cb_t cb)
{
    s_isr_event_cb = cb;
}

uint32_t can_get_bus_off_count(void)
{
    return s_bus_off_count;
}

esp_err_t can_get_info(int *out_state,
                       uint16_t *out_tx_err,
                       uint16_t *out_rx_err,
                       uint32_t *out_tx_queue_remaining,
                       uint32_t *out_bus_err_num)
{
    if (s_node == NULL) return ESP_ERR_INVALID_STATE;
    twai_node_status_t status = {0};
    twai_node_record_t record = {0};
    esp_err_t ret = twai_node_get_info(s_node, &status, &record);
    if (ret != ESP_OK) return ret;
    if (out_state)               *out_state = (int)status.state;
    if (out_tx_err)              *out_tx_err = status.tx_error_count;
    if (out_rx_err)              *out_rx_err = status.rx_error_count;
    if (out_tx_queue_remaining)  *out_tx_queue_remaining = status.tx_queue_remaining;
    if (out_bus_err_num)         *out_bus_err_num = record.bus_err_num;
    return ESP_OK;
}

static int16_t amps_to_ma_i16(float amps)
{
    float ma = amps * 1000.0f;
    if (ma > 32767.0f)  ma = 32767.0f;
    if (ma < -32768.0f) ma = -32768.0f;
    return (int16_t)ma;
}

esp_err_t can_send_telemetry(uint8_t module_type, uint8_t module_id,
                             const float current_a[CEC_NUM_CABLES],
                             uint8_t status_flags, float board_temp_c)
{
    if (!s_enabled) return ESP_ERR_INVALID_STATE;

    int16_t i0 = amps_to_ma_i16(current_a[0]);
    int16_t i1 = amps_to_ma_i16(current_a[1]);

    // Clamp temperature into int8 range before casting (the NTC returns
    // -273.15 as an open/short sentinel, which would otherwise be UB here).
    float t = board_temp_c;
    if (t > 127.0f)  t = 127.0f;
    if (t < -128.0f) t = -128.0f;

    uint8_t data[8] = {
        module_type,
        module_id,
        (uint8_t)(i0 & 0xFF),
        (uint8_t)((i0 >> 8) & 0xFF),
        (uint8_t)(i1 & 0xFF),
        (uint8_t)((i1 >> 8) & 0xFF),
        status_flags,
        (uint8_t)(int8_t)t,
    };
    twai_frame_t frame = {
        .header.id  = CAN_ID_TELEMETRY_BASE + module_id,
        .buffer     = data,
        .buffer_len = sizeof(data),
    };

    esp_err_t ret = twai_node_transmit(s_node, &frame, CAN_TX_TIMEOUT_MS);
    if (ret != ESP_OK) return ret;
    // Block until the queued frame is actually on the wire so the
    // stack-allocated `data` buffer can safely go out of scope.
    return twai_node_transmit_wait_all_done(s_node, CAN_TX_TIMEOUT_MS);
}

esp_err_t can_send_anomaly(uint8_t module_type, uint8_t module_id,
                           uint8_t status_flags)
{
    if (!s_enabled) return ESP_ERR_INVALID_STATE;

    uint8_t data[3] = { module_type, module_id, status_flags };
    twai_frame_t frame = {
        .header.id  = CAN_ID_ANOMALY_BASE + module_id,  // lower ID = higher priority
        .buffer     = data,
        .buffer_len = sizeof(data),
    };

    esp_err_t ret = twai_node_transmit(s_node, &frame, CAN_TX_TIMEOUT_MS);
    if (ret != ESP_OK) return ret;
    return twai_node_transmit_wait_all_done(s_node, CAN_TX_TIMEOUT_MS);
}

esp_err_t can_send_frame(uint32_t id, const uint8_t *data, uint8_t len)
{
    if (!s_enabled) return ESP_ERR_INVALID_STATE;
    if (len > 8) len = 8;
    uint8_t buf[8] = {0};
    if (data && len) memcpy(buf, data, len);
    twai_frame_t frame = {
        .header.id  = id,
        .buffer     = buf,
        .buffer_len = len,
    };
    esp_err_t ret = twai_node_transmit(s_node, &frame, CAN_TX_TIMEOUT_MS);
    if (ret != ESP_OK) return ret;
    return twai_node_transmit_wait_all_done(s_node, CAN_TX_TIMEOUT_MS);
}

esp_err_t can_receive(uint32_t *out_id, uint8_t *out_data, uint8_t *out_len,
                      uint32_t timeout_ms)
{
    if (s_rx_queue == NULL) return ESP_ERR_INVALID_STATE;
    can_rx_slot_t slot;
    if (xQueueReceive(s_rx_queue, &slot, pdMS_TO_TICKS(timeout_ms)) != pdTRUE)
        return ESP_ERR_TIMEOUT;
    if (out_id)   *out_id = slot.id;
    if (out_len)  *out_len = slot.len;
    if (out_data) memcpy(out_data, slot.data, sizeof(slot.data));
    return ESP_OK;
}

void can_stop(void)
{
    if (s_node != NULL) {
        if (s_enabled) {
            twai_node_disable(s_node);
            s_enabled = false;
        }
        twai_node_delete(s_node);
        s_node = NULL;
    }
    if (s_rx_queue) {
        vQueueDelete(s_rx_queue);
        s_rx_queue = NULL;
    }
}

#else  /* CEC_CAN_ENABLED */

/*
 * Link-time stubs while the TWAI driver is not built. comms_task is
 * never created in this configuration (eps_main.c also #if-guards the
 * xTaskCreatePinnedToCore call), but its compiled body still references
 * these symbols, so they have to resolve.
 */

esp_err_t can_init(bool loopback)
{
    (void)loopback;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t can_send_telemetry(uint8_t module_type, uint8_t module_id,
                             const float current_a[CEC_NUM_CABLES],
                             uint8_t status_flags, float board_temp_c)
{
    (void)module_type; (void)module_id; (void)current_a;
    (void)status_flags; (void)board_temp_c;
    return ESP_ERR_INVALID_STATE;
}

esp_err_t can_send_anomaly(uint8_t module_type, uint8_t module_id,
                           uint8_t status_flags)
{
    (void)module_type; (void)module_id; (void)status_flags;
    return ESP_ERR_INVALID_STATE;
}

esp_err_t can_send_frame(uint32_t id, const uint8_t *data, uint8_t len)
{
    (void)id; (void)data; (void)len;
    return ESP_ERR_INVALID_STATE;
}

esp_err_t can_receive(uint32_t *out_id, uint8_t *out_data, uint8_t *out_len,
                      uint32_t timeout_ms)
{
    (void)out_id; (void)out_data; (void)out_len; (void)timeout_ms;
    return ESP_ERR_INVALID_STATE;
}

void can_stop(void) { }
void can_set_rx_log(bool enable) { (void)enable; }
void can_set_isr_event_cb(can_isr_event_cb_t cb) { (void)cb; }

uint32_t can_get_rx_count(void) { return 0; }
uint32_t can_get_bus_off_count(void) { return 0; }
esp_err_t can_get_info(int *a, uint16_t *b, uint16_t *c, uint32_t *d, uint32_t *e)
{
    (void)a; (void)b; (void)c; (void)d; (void)e;
    return ESP_ERR_INVALID_STATE;
}

#endif /* CEC_CAN_ENABLED */
