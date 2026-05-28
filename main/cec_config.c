#include "cec_config.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"

static const char *TAG = "cec_config";
static const char *NVS_NAMESPACE = "cec_eps";

void cec_config_defaults(cec_config_t *cfg)
{
    cfg->module_id      = CEC_DEFAULT_MODULE_ID;
    cfg->supply_voltage = CEC_DEFAULT_SUPPLY_V;
    cfg->oc_threshold_a = CEC_DEFAULT_OC_A;
    cfg->ema_alpha      = CEC_DEFAULT_EMA_ALPHA;
    cfg->output_raw     = false;
}

esp_err_t cec_config_init_nvs(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    return ret;
}

void cec_config_load(cec_config_t *cfg)
{
    cec_config_defaults(cfg);

    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &h) != ESP_OK) {
        ESP_LOGW(TAG, "no stored config, using defaults");
        return;
    }

    size_t sz;
    nvs_get_u8(h, "module_id", &cfg->module_id);

    sz = sizeof(float);
    nvs_get_blob(h, "supply_v", &cfg->supply_voltage, &sz);
    sz = sizeof(float);
    nvs_get_blob(h, "oc_a", &cfg->oc_threshold_a, &sz);
    sz = sizeof(float);
    nvs_get_blob(h, "ema_alpha", &cfg->ema_alpha, &sz);

    uint8_t raw = 0;
    if (nvs_get_u8(h, "output_raw", &raw) == ESP_OK) {
        cfg->output_raw = (raw != 0);
    }

    nvs_close(h);
    ESP_LOGI(TAG, "config loaded: id=%d supply=%.2fV oc=%.1fA alpha=%.2f",
             cfg->module_id, cfg->supply_voltage, cfg->oc_threshold_a, cfg->ema_alpha);
}

void cec_config_save(const cec_config_t *cfg)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) {
        ESP_LOGE(TAG, "failed to open NVS for write");
        return;
    }

    nvs_set_u8(h, "module_id", cfg->module_id);
    nvs_set_blob(h, "supply_v", &cfg->supply_voltage, sizeof(float));
    nvs_set_blob(h, "oc_a", &cfg->oc_threshold_a, sizeof(float));
    nvs_set_blob(h, "ema_alpha", &cfg->ema_alpha, sizeof(float));
    nvs_set_u8(h, "output_raw", cfg->output_raw ? 1 : 0);

    nvs_commit(h);
    nvs_close(h);
    ESP_LOGI(TAG, "config saved");
}

// Per-sensor zero offset persistence (called by the calibration routine)
void cec_config_save_zero_offset(int sensor, float offset_v)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) return;
    char key[16];
    snprintf(key, sizeof(key), "zero_off%d", sensor);
    nvs_set_blob(h, key, &offset_v, sizeof(float));
    nvs_commit(h);
    nvs_close(h);
}

bool cec_config_load_zero_offset(int sensor, float *offset_v)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &h) != ESP_OK) return false;
    char key[16];
    snprintf(key, sizeof(key), "zero_off%d", sensor);
    size_t sz = sizeof(float);
    esp_err_t ret = nvs_get_blob(h, key, offset_v, &sz);
    nvs_close(h);
    return (ret == ESP_OK);
}
