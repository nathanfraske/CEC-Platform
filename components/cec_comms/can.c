#include "can.h"

#if CEC_CAN_ENABLED

/*
 * NOTE: this still uses the legacy "driver/twai.h" driver. IDF 6.x has
 * deprecated it in favor of "esp_twai.h" / "esp_twai_onchip.h" and emits
 * a #warning that -Werror turns into a build error. Migrate the body of
 * this block to the new node-handle API (twai_new_node_onchip, twai_node_*)
 * the next time CEC_CAN_ENABLED is flipped on. Until then this whole block
 * is excluded from compilation so the deprecation warning never fires.
 */
#include "driver/twai.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "can";
static bool s_installed = false;

esp_err_t can_init(bool loopback)
{
    twai_mode_t mode = loopback ? TWAI_MODE_NO_ACK : TWAI_MODE_NORMAL;
    twai_general_config_t g_cfg =
        TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX_GPIO, CAN_RX_GPIO, mode);
    twai_timing_config_t t_cfg = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f_cfg = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    esp_err_t ret = twai_driver_install(&g_cfg, &t_cfg, &f_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "driver install failed: %s", esp_err_to_name(ret));
        return ret;
    }
    ret = twai_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "start failed: %s", esp_err_to_name(ret));
        twai_driver_uninstall();
        return ret;
    }
    s_installed = true;
    ESP_LOGI(TAG, "TWAI started @ 500kbps (%s)", loopback ? "loopback" : "normal");
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
    if (!s_installed) return ESP_ERR_INVALID_STATE;

    twai_message_t msg = {0};
    msg.identifier = CAN_ID_TELEMETRY_BASE + module_id;
    msg.data_length_code = 8;

    int16_t i0 = amps_to_ma_i16(current_a[0]);
    int16_t i1 = amps_to_ma_i16(current_a[1]);

    // Clamp temperature into int8 range before casting (the NTC returns
    // -273.15 as an open/short sentinel, which would otherwise be UB here).
    float t = board_temp_c;
    if (t > 127.0f)  t = 127.0f;
    if (t < -128.0f) t = -128.0f;

    msg.data[0] = module_type;
    msg.data[1] = module_id;
    msg.data[2] = (uint8_t)(i0 & 0xFF);
    msg.data[3] = (uint8_t)((i0 >> 8) & 0xFF);
    msg.data[4] = (uint8_t)(i1 & 0xFF);
    msg.data[5] = (uint8_t)((i1 >> 8) & 0xFF);
    msg.data[6] = status_flags;
    msg.data[7] = (int8_t)t;

    return twai_transmit(&msg, pdMS_TO_TICKS(10));
}

esp_err_t can_send_anomaly(uint8_t module_type, uint8_t module_id,
                           uint8_t status_flags)
{
    if (!s_installed) return ESP_ERR_INVALID_STATE;

    twai_message_t msg = {0};
    msg.identifier = CAN_ID_ANOMALY_BASE + module_id;   // lower ID = higher priority
    msg.data_length_code = 3;
    msg.data[0] = module_type;
    msg.data[1] = module_id;
    msg.data[2] = status_flags;

    return twai_transmit(&msg, pdMS_TO_TICKS(10));
}

void can_stop(void)
{
    if (s_installed) {
        twai_stop();
        twai_driver_uninstall();
        s_installed = false;
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

void can_stop(void) { }

#endif /* CEC_CAN_ENABLED */
