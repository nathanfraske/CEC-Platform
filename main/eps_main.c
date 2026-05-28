#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "cec_state.h"
#include "cec_config.h"
#include "cec_adc.h"
#include "acs758.h"
#include "ntc.h"
#include "cec_filters.h"
#include "cec_detection.h"
#include "cec_capture.h"
#include "cec_can.h"
#include "cec_teleplot.h"

static const char *TAG = "eps_main";

// ---- Global state ----
static cec_state_t   g_state;
static cec_config_t  g_config;
static acs758_ctx_t  g_acs;
// NTC on GPIO 7 -> ADC1_CH6. 10K @ 25C, B=3950, 10K series pull-up to
// 3V3 - matches the EPS daughterboard schematic.
static ntc_t g_ntc = {
    .channel              = ADC_CHANNEL_6,
    .samples              = 8,
    .beta                 = 3950.0f,
    .nominal_resistance   = 10000.0f,
    .nominal_temperature_k = 298.15f,
    .pull_up_resistance   = 10000.0f,
    .vcc                  = 3.3f,
};
// Two-stage filter per cable: median to reject impulse spikes, then EMA
// to smooth. Median window size is per-module tunable; 5 is the EPS
// starting point for the Hall sensor's ~50-100 mA RMS raw noise.
#define EPS_MEDIAN_WINDOW   5
static median_t g_median[CEC_NUM_CABLES];
static ema_t    g_ema[CEC_NUM_CABLES];
static float    g_median_buf[CEC_NUM_CABLES][EPS_MEDIAN_WINDOW];
static cec_detection_ctx_t g_detect;
static capture_ctx_t g_capture;

// ---- Timing ----
#define SAMPLE_RATE_HZ   50
#define SAMPLE_PERIOD_MS  (1000 / SAMPLE_RATE_HZ)
#define OUTPUT_RATE_HZ   10
#define OUTPUT_PERIOD_MS  (1000 / OUTPUT_RATE_HZ)
#define COMMS_RATE_HZ    20
#define COMMS_PERIOD_MS   (1000 / COMMS_RATE_HZ)

#define CAPTURE_SECONDS   5.0f

// ---- Sample task: read, convert, filter, detect, store ----
static void sample_task(void *arg)
{
    ESP_LOGI(TAG, "sample task started on core %d", xPortGetCoreID());
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        int64_t now_us = esp_timer_get_time();

        float raw[CEC_NUM_CABLES];
        float filt[CEC_NUM_CABLES];
        for (int i = 0; i < CEC_NUM_CABLES; i++) {
            raw[i] = acs758_read_current(&g_acs, i);
            filt[i] = ema_update(&g_ema[i], median_update(&g_median[i], raw[i]));
        }

        // Push raw stream to ring buffer for transient capture
        capture_push(&g_capture, now_us, raw);

        // Run detection layers
        uint8_t flags = 0;
        cec_load_state_t load_state = CEC_LOAD_IDLE;
        bool anomaly = cec_detection_run(&g_detect, raw, filt, now_us, &flags, &load_state);

        float temp = 0.0f;
        (void)ntc_read_celsius(&g_ntc, &temp);   // leaves temp at 0 on open/short

        // Update shared state
        if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            for (int i = 0; i < CEC_NUM_CABLES; i++) {
                g_state.current_a[i] = filt[i];
                g_state.current_raw_a[i] = raw[i];
            }
            g_state.board_temp_c = temp;
            g_state.load_state = load_state;
            g_state.status_flags = flags;
            g_state.timestamp_us = now_us;
            xSemaphoreGive(g_state.mutex);
        }

        if (anomaly) {
            // In a full build: signal burst_task to dump the capture window.
            // For now, log it.
            ESP_LOGW(TAG, "anomaly flags=0x%02x", flags);
        }

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

// ---- Output task: Teleplot telemetry ----
static void output_task(void *arg)
{
    ESP_LOGI(TAG, "output task started on core %d", xPortGetCoreID());
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        cec_state_t snap;
        if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            snap = g_state;
            xSemaphoreGive(g_state.mutex);
            teleplot_emit_state(&snap, g_config.output_raw);
        }
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(OUTPUT_PERIOD_MS));
    }
}

// ---- Comms task: CAN telemetry to Hub ----
static void comms_task(void *arg)
{
    ESP_LOGI(TAG, "comms task started on core %d", xPortGetCoreID());
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        cec_state_t snap;
        if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            snap = g_state;
            xSemaphoreGive(g_state.mutex);

            can_send_telemetry(CEC_MODULE_TYPE_EPS, g_config.module_id,
                               snap.current_a, snap.status_flags, snap.board_temp_c);
            if (snap.status_flags != 0) {
                can_send_anomaly(CEC_MODULE_TYPE_EPS, g_config.module_id,
                                 snap.status_flags);
            }
        }
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(COMMS_PERIOD_MS));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "CEC EPS module firmware starting");

    // NVS + config
    ESP_ERROR_CHECK(cec_config_init_nvs());
    cec_config_load(&g_config);

    // Shared state
    memset(&g_state, 0, sizeof(g_state));
    g_state.mutex = xSemaphoreCreateMutex();
    if (g_state.mutex == NULL) {
        ESP_LOGE(TAG, "mutex create failed");
        abort();
    }

    // ADC1 + curve-fit calibration, shared by every sensor driver.
    ESP_ERROR_CHECK(cec_adc_init());

    // Sensors
    ESP_ERROR_CHECK(acs758_init(&g_acs));
    // Apply the measured supply voltage for ratiometric correction.
    acs758_set_supply(&g_acs, g_config.supply_voltage);
    // Load any stored zero offsets
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        float off;
        if (cec_config_load_zero_offset(i, &off)) {
            acs758_set_zero_offset(&g_acs, i, off);
            ESP_LOGI(TAG, "loaded zero offset[%d] = %.4fV", i, off);
        }
    }

    ESP_ERROR_CHECK(ntc_setup(&g_ntc));

    // Filters: median (impulse rejection) then EMA (smoothing).
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        median_init(&g_median[i], g_median_buf[i], EPS_MEDIAN_WINDOW);
        ema_init(&g_ema[i], g_config.ema_alpha);
    }

    // Detection
    cec_detection_init(&g_detect, g_config.oc_threshold_a);

    // Capture ring buffer (PSRAM)
    capture_init(&g_capture, CAPTURE_SECONDS, SAMPLE_RATE_HZ);

#if CEC_CAN_ENABLED
    // CAN in loopback for bench bring-up (no Hub connected yet).
    // Switch to can_init(false) once the daughterboard + Hub are present.
    can_init(true);
#else
    ESP_LOGW(TAG, "CAN disabled (CEC_CAN_ENABLED=0); skipping TWAI init and comms task");
#endif

    // Tasks: sample on core 0 (isolated), output/comms on core 1
    xTaskCreatePinnedToCore(sample_task, "sample", 4096, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(output_task, "output", 4096, NULL, 3, NULL, 1);
#if CEC_CAN_ENABLED
    xTaskCreatePinnedToCore(comms_task,  "comms",  4096, NULL, 4, NULL, 1);
#else
    (void)comms_task;
#endif

    ESP_LOGI(TAG, "init complete, tasks running");
}
