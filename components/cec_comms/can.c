#include "can.h"

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
        // Bench self-test: transmit without requiring another node's ACK.
        // Equivalent to the legacy TWAI_MODE_NO_ACK.
        cfg.flags.enable_self_test = 1;
    }

    esp_err_t ret = twai_new_node_onchip(&cfg, &s_node);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "twai_new_node_onchip failed: %s", esp_err_to_name(ret));
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
             loopback ? "self-test" : "normal");
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

#endif /* CEC_CAN_ENABLED */
