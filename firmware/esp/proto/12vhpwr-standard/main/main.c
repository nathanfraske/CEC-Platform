/*
 * CEC 12VHPWR Standard module — SCAFFOLD (ready for sensor bring-up).
 *
 * ESP32-S3-MINI-1; six INA240 per-pin current-sense amps into the S3 ADC + a
 * rail-voltage divider + NTCs (spec §6.1/§6.4). No FPGA (that's Pro+). The
 * shared cec_module runtime gives clean Hub aggregation + CAN re-flashability;
 * the ONLY per-board code here is read_sensors(), which a bring-up fills in.
 *
 * Over CAN this sends a low-rate SUMMARY of the 6 per-pin currents (total /
 * hottest / coldest / spread + rail V + temp). The 10 kHz per-pin detail stays
 * local in a burst buffer (capture_burst(), a stub here) per §6.10.
 *
 * STATUS: read_sensors() returns PLACEHOLDER data so the module enumerates on
 * the Hub and exercises the aggregator before the analog front end is wired.
 * Replace the marked block with the real ADC reads.
 */

#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "cec_module.h"
#include "cec_telem.h"
#include "cec_config.h"

static const char *TAG = "hpwr_std";

/* §6.10 burst capture of the 6 per-pin currents at the full ADC rate. Wired to
 * the INA240 over-threshold / §6.13 detection trigger at bring-up. A per-pin
 * imbalance also broadcasts a cross-module FREEZE so every module captures the
 * same instant (the §6.13 thesis: the electrical outlier leads the thermal). */
static void capture_burst(void)
{
    /* TODO bring-up: snapshot the per-pin ring buffer (cec_capture) + dump it. */
    if (!cec_freeze_is_frozen())
        cec_freeze_trigger(CEC_FREEZE_CAUSE_OVERCURRENT);   /* freeze the whole system */
}

/* Fold the 6 per-pin currents into the 4-channel telemetry summary. */
static void summarize(const float pin_a[HPWR_NUM_PINS], float rail_v, float temp_c,
                      cec_telem_t *t)
{
    float total = 0.0f, imax = -1e9f, imin = 1e9f;
    for (int p = 0; p < HPWR_NUM_PINS; p++) {
        total += pin_a[p];
        if (pin_a[p] > imax) imax = pin_a[p];
        if (pin_a[p] < imin) imin = pin_a[p];
    }
    float mean = total / HPWR_NUM_PINS;

    t->v[0] = rail_v;  t->i[0] = total;          /* "rail"   */
    t->v[1] = 0;       t->i[1] = imax;           /* "imax"   */
    t->v[2] = 0;       t->i[2] = imin;           /* "imin"   */
    t->v[3] = 0;       t->i[3] = imax - imin;    /* "spread" */
    t->temp_c    = temp_c;
    t->p_total_w = rail_v * total;
    t->flags     = (mean > 0.0f && (imax - mean) > HPWR_IMBALANCE_FRAC * mean)
                       ? HPWR_FLAG_IMBALANCE : 0;
    if (t->flags & HPWR_FLAG_IMBALANCE) capture_burst();   /* freeze on a hog */
}

static void read_sensors(cec_telem_t *t, void *ctx)
{
    (void)ctx;
    /* ===== TODO bring-up: replace this placeholder with the real reads =====
     * for each pin p: raw = adc_oneshot_read(ADC1, HPWR_ADC_PIN_GPIO[p]-1);
     *   v_out = cali(raw);  i = v_out / (HPWR_INA240_GAIN * HPWR_SHUNT_OHMS);
     * rail_v = cali(adc(HPWR_RAIL_DIV_GPIO)) * (DIV_NUM+DIV_DEN)/DIV_DEN;
     * temp = ntc_c(adc(HPWR_NTC_BOARD_GPIO));
     * (REF3030 ratiometric correction per §3.8 if populated.) */
    static bool warned = false;
    if (!warned) { ESP_LOGW(TAG, "STUB sensor data -- wire the INA240 ADC reads"); warned = true; }

    float pin_a[HPWR_NUM_PINS] = { 5.1f, 4.9f, 5.0f, 5.2f, 4.8f, 5.0f };  /* ~30A total */
    summarize(pin_a, 12.0f, 40.0f, t);
    /* ======================================================================= */
}

void app_main(void)
{
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "CEC 12VHPWR Standard module (scaffold)");
    ESP_LOGI(TAG, "ESP32-S3 + 6x INA240 -> ADC; no FPGA (Pro+ only)");
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
