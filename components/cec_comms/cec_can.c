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
#include "esp_twai.h"
#include "esp_twai_onchip.h"
#include "esp_log.h"

#define CAN_BITRATE_BPS        500000
#define CAN_TX_QUEUE_DEPTH     8
#define CAN_TX_TIMEOUT_MS      10

static const char *TAG = "can";
static twai_node_handle_t s_node = NULL;
static bool s_enabled = false;
static volatile uint32_t s_rx_count = 0;
static volatile uint32_t s_bus_off_count = 0;

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
    if (twai_node_receive_from_isr(handle, &rx_frame) == ESP_OK) {
        s_rx_count++;
        ESP_EARLY_LOGI(TAG,
            "RX id=0x%03x dlc=%u [%02x %02x %02x %02x %02x %02x %02x %02x]",
            (unsigned)rx_frame.header.id,
            (unsigned)rx_frame.header.dlc,
            rx_data[0], rx_data[1], rx_data[2], rx_data[3],
            rx_data[4], rx_data[5], rx_data[6], rx_data[7]);
    }
    return false; /* no higher-prio task to unblock */
}

esp_err_t can_init(bool loopback)
{
    if (s_node != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    twai_onchip_node_config_t cfg = {
        .io_cfg = {
            .tx                = CAN_TX_GPIO,
            .rx                = CAN_RX_GPIO,
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
    ESP_LOGI(TAG, "TWAI node up @ %d bps (%s)", CAN_BITRATE_BPS,
             loopback ? "loopback" : "normal");
    return ESP_OK;
}

uint32_t can_get_rx_count(void)
{
    return s_rx_count;
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

void can_stop(void)
{
    if (s_node == NULL) return;
    if (s_enabled) {
        twai_node_disable(s_node);
        s_enabled = false;
    }
    twai_node_delete(s_node);
    s_node = NULL;
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

void can_stop(void) { }

uint32_t can_get_rx_count(void) { return 0; }

#endif /* CEC_CAN_ENABLED */
