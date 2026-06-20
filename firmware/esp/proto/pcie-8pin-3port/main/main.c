/*
 * CEC PCIe 8-pin module — SCAFFOLD (ready for sensor bring-up).
 *
 * ESP32-S3-MINI-1 interposer; one INA238 per cable over I2C (per-cable
 * granularity) + the §6.13 per-cable transient-detection front end. Cable
 * count is PCIE_NUM_CABLES (this main is shared verbatim by the 2-port and
 * 3-port SKUs; only cec_config.h differs).
 *
 * The shared cec_module runtime gives clean Hub aggregation + CAN
 * re-flashability; the ONLY per-board code here is read_sensors().
 *
 * STATUS: read_sensors() returns PLACEHOLDER data so the module enumerates on
 * the Hub and exercises the aggregator before the sensors are wired. Replace
 * the marked block with the real INA238 reads.
 */

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "cec_module.h"
#include "cec_telem.h"
#include "cec_config.h"

static const char *TAG = "pcie";

static void read_sensors(cec_telem_t *t, void *ctx)
{
    (void)ctx;
    /* ===== TODO bring-up: replace with the real per-cable INA238 reads =====
     * static const uint8_t addr[PCIE_NUM_CABLES] = PCIE_INA238_ADDR;
     * for each cable c:
     *   bus_v = ina238_read_bus_voltage(addr[c]);
     *   i     = ina238_read_current(addr[c]);   // shunt = PCIE_SHUNT_OHMS
     *   t->v[c] = bus_v;  t->i[c] = i;
     * flags |= per-cable §6.13 DET latch (gpio PCIE_DET_GPIO[c]). */
    static bool warned = false;
    if (!warned) { ESP_LOGW(TAG, "STUB sensor data -- wire the INA238 reads"); warned = true; }

    float p = 0.0f;
    for (int c = 0; c < PCIE_NUM_CABLES && c < CEC_TELEM_NUM_RAILS; c++) {
        t->v[c] = 12.0f;                 /* nominal rail (INA238 reads bus V at bring-up) */
        t->i[c] = 10.0f + 0.5f * c;      /* placeholder per-cable current */
        p += t->v[c] * t->i[c];
    }
    t->temp_c    = 35.0f;                /* board NTC at bring-up */
    t->p_total_w = p;
    t->flags     = 0;                    /* §6.13 DET latches at bring-up */
    /* ===================================================================== */
}

void app_main(void)
{
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "CEC PCIe 8-pin module (scaffold) -- %d cable(s)", PCIE_NUM_CABLES);
    ESP_LOGI(TAG, "ESP32-S3 + INA238 per cable + §6.13 detection");
    ESP_LOGI(TAG, "===========================================");

    cec_module_cfg_t cfg = {
        .module_type     = CEC_CFG_MODULE_TYPE,
        .module_id       = CEC_CFG_MODULE_ID,
        .detect_tap_gpio = CEC_CFG_DETECT_TAP_GPIO,
        .period_ms       = CEC_CAN_TX_PERIOD_MS,
        .read            = read_sensors,
        .ctx             = NULL,
    };
    if (cec_module_start(&cfg) != ESP_OK)
        ESP_LOGE(TAG, "module runtime failed to start");
}
