#include "cec_config.h"
#include "cec_nvs.h"
#include "esp_log.h"

static const char *TAG = "cec_config";

/* Schema magics. Bump the low byte (e.g. 0xCEC50001 -> 0xCEC50002) any
 * time the on-flash layout of the corresponding payload changes; the
 * cec_nvs wrapper will reject an old blob cleanly instead of loading
 * garbage into the new struct. */
#define KEY_CONFIG           "config"
#define MAGIC_CONFIG         0xCEC50001U

#define KEY_ZERO_OFF_FMT     "zero_off%d"
#define MAGIC_ZERO_OFF       0xCEC50101U

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
    return cec_nvs_init();
}

void cec_config_load(cec_config_t *cfg)
{
    cec_config_defaults(cfg);

    esp_err_t ret = cec_nvs_load_blob(KEY_CONFIG, MAGIC_CONFIG, cfg, sizeof(*cfg));
    switch (ret) {
    case ESP_OK:
        ESP_LOGI(TAG, "config loaded: id=%d supply=%.2fV oc=%.1fA alpha=%.2f raw=%d",
                 cfg->module_id, cfg->supply_voltage, cfg->oc_threshold_a,
                 cfg->ema_alpha, cfg->output_raw);
        return;
    case ESP_ERR_NOT_FOUND:
        ESP_LOGW(TAG, "no stored config, using defaults");
        break;
    case ESP_ERR_INVALID_VERSION:
        ESP_LOGW(TAG, "stored config has stale schema (magic mismatch), using defaults");
        break;
    case ESP_ERR_INVALID_SIZE:
        ESP_LOGW(TAG, "stored config size mismatch, using defaults");
        break;
    default:
        ESP_LOGE(TAG, "load failed: %s, using defaults", esp_err_to_name(ret));
        break;
    }
    // Reset to defaults if anything went sideways. cec_config_defaults
    // already ran above; nothing else to do.
}

void cec_config_save(const cec_config_t *cfg)
{
    esp_err_t ret = cec_nvs_save_blob(KEY_CONFIG, MAGIC_CONFIG, cfg, sizeof(*cfg));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "save failed: %s", esp_err_to_name(ret));
        return;
    }
    ESP_LOGI(TAG, "config saved");
}

void cec_config_save_zero_offset(int sensor, float offset_v)
{
    char key[16];
    snprintf(key, sizeof(key), KEY_ZERO_OFF_FMT, sensor);
    esp_err_t ret = cec_nvs_save_blob(key, MAGIC_ZERO_OFF, &offset_v, sizeof(offset_v));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "zero offset[%d] save failed: %s", sensor, esp_err_to_name(ret));
        return;
    }
    ESP_LOGI(TAG, "zero offset[%d] saved = %.4fV", sensor, offset_v);
}

bool cec_config_load_zero_offset(int sensor, float *offset_v)
{
    if (offset_v == NULL) return false;
    char key[16];
    snprintf(key, sizeof(key), KEY_ZERO_OFF_FMT, sensor);
    return cec_nvs_load_blob(key, MAGIC_ZERO_OFF, offset_v, sizeof(*offset_v)) == ESP_OK;
}
