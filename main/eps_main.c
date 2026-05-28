#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "cec_state.h"
#include "cec_config.h"
#include "acs758.h"
#include "ntc.h"
#include "filter.h"
#include "detection.h"
#include "capture.h"
#include "can.h"
#include "teleplot.h"

static const char *TAG = "eps_main";

// ---- Global state ----
static cec_state_t   g_state;
static cec_config_t  g_config;
static acs758_ctx_t  g_acs;
static ntc_ctx_t     g_ntc;
static cec_filter_t  g_filter[CEC_NUM_CABLES];
static detection_ctx_t g_detect;
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
            filt[i] = cec_filter_update(&g_filter[i], raw[i]);
        }

        // Push raw stream to ring buffer for transient capture
        capture_push(&g_capture, now_us, raw);

        // Run detection layers
        uint8_t flags = 0;
        cec_op_state_t op_state = CEC_STATE_IDLE;
        bool anomaly = detection_run(&g_detect, raw, filt, now_us, &flags, &op_state);

        float temp = g_ntc.adc ? ntc_read_celsius(&g_ntc) : 0.0f;

        // Update shared state
        if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            for (int i = 0; i < CEC_NUM_CABLES; i++) {
                g_state.current_a[i] = filt[i];
                g_state.current_raw_a[i] = raw[i];
            }
            g_state.board_temp_c = temp;
            g_state.op_state = op_state;
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

    // NTC shares the ADC1 unit + calibration from the ACS758 driver
    ntc_init(&g_ntc, g_acs.adc, g_acs.cali, g_acs.cali_enabled);

    // Filters
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        cec_filter_init(&g_filter[i], g_config.ema_alpha);
    }

    // Detection
    detection_init(&g_detect, g_config.oc_threshold_a);

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
