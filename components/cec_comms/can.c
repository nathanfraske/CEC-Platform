#include "can.h"
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

    msg.data[0] = module_type;
    msg.data[1] = module_id;
    msg.data[2] = (uint8_t)(i0 & 0xFF);
    msg.data[3] = (uint8_t)((i0 >> 8) & 0xFF);
    msg.data[4] = (uint8_t)(i1 & 0xFF);
    msg.data[5] = (uint8_t)((i1 >> 8) & 0xFF);
    msg.data[6] = status_flags;
    msg.data[7] = (int8_t)board_temp_c;

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
