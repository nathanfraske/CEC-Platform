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
#include "cec_cli.h"
#include "cec_classifier.h"

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

// Burst capture engine config. 10 kHz HS rate (per channel) for 1 s, with
// 20 s of 50 Hz pre-trigger context. cooldown_ms=10000 matches the 24-pin.
#define EPS_BURST_HS_RATE_HZ   10000
#define EPS_BURST_HS_DURATION  1000
#define EPS_PRE_TRIGGER_SECONDS  20
#define EPS_BURST_COOLDOWN_MS   10000

// ---- Timing ----
#define SAMPLE_RATE_HZ   50
#define SAMPLE_PERIOD_MS  (1000 / SAMPLE_RATE_HZ)
#define OUTPUT_RATE_HZ   10
#define OUTPUT_PERIOD_MS  (1000 / OUTPUT_RATE_HZ)
#define COMMS_RATE_HZ    20
#define COMMS_PERIOD_MS   (1000 / COMMS_RATE_HZ)

// ---- Sample task: read, convert, filter, detect, store ----
static void sample_task(void *arg)
{
    ESP_LOGI(TAG, "sample task started on core %d", xPortGetCoreID());
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        int64_t now_us = esp_timer_get_time();

        // While the burst engine has ADC1, skip every read this iteration
        // (cec_adc_read_mv would return ESP_ERR_INVALID_STATE anyway).
        // The shared-state snapshot from the last good iteration stays
        // valid for downstream consumers during the burst window.
        if (cec_capture_is_busy()) {
            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
            continue;
        }

        float raw[CEC_NUM_CABLES];
        float filt[CEC_NUM_CABLES];
        for (int i = 0; i < CEC_NUM_CABLES; i++) {
            raw[i] = acs758_read_current(&g_acs, i);
            filt[i] = ema_update(&g_ema[i], median_update(&g_median[i], raw[i]));
        }

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

        // Push the full per-iteration snapshot into the pre-trigger ring.
        cec_capture_sample_t cap_sample = {
            .ts_ms      = (uint32_t)(now_us / 1000),
            .eps1_a     = filt[0],
            .eps2_a     = filt[1],
            .eps1_raw_a = raw[0],
            .eps2_raw_a = raw[1],
            .temp_c     = temp,
            .load_state = (uint8_t)load_state,
            .flags      = flags,
        };
        cec_capture_push(&cap_sample);

        if (anomaly) {
            // Fire a burst capture on anomaly. cec_capture's busy/cooldown
            // gates absorb back-to-back triggers; we don't gate again here.
            esp_err_t tr = cec_capture_trigger(CEC_TRIG_ANOMALY);
            if (tr == ESP_OK) {
                ESP_LOGW(TAG, "anomaly flags=0x%02x - burst triggered", flags);
            } else if (tr == ESP_ERR_NOT_FINISHED || tr == ESP_ERR_INVALID_STATE) {
                ESP_LOGD(TAG, "anomaly flags=0x%02x - burst skipped (%s)",
                         flags, esp_err_to_name(tr));
            } else {
                ESP_LOGW(TAG, "anomaly flags=0x%02x - trigger failed: %s",
                         flags, esp_err_to_name(tr));
            }
        }

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

// ---- Output task: Teleplot telemetry ----
static void output_task(void *arg)
{
    ESP_LOGI(TAG, "output task started on core %d", xPortGetCoreID());
    (void)arg;

    while (1) {
        cec_state_t snap;
        if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            snap = g_state;
            xSemaphoreGive(g_state.mutex);
            teleplot_emit_state(&snap, g_config.output_raw);
        }
        // vTaskDelay (not DelayUntil) so a long burst dump can't leave
        // this task in "catch up" mode where DelayUntil returns instantly
        // and the task spins iteration-on-iteration, starving IDLE1.
        vTaskDelay(pdMS_TO_TICKS(OUTPUT_PERIOD_MS));
    }
}

// ---- CLI command handlers ----

// Snapshot the live ACS758 cal for one channel into a
// cec_capture_channel_t for cec_capture_update_channel.
static void capture_channel_snapshot(int idx, cec_capture_channel_t *out)
{
    *out = (cec_capture_channel_t){
        .channel         = g_acs.channels[idx],
        .divider_gain    = ACS758_DIVIDER_GAIN,
        .quiescent_v     = g_acs.cal[idx].quiescent_v,
        .sensitivity_v_a = g_acs.cal[idx].sensitivity_v_a,
        .zero_offset_v   = g_acs.cal[idx].zero_offset_v,
    };
}

static int cmd_show(int argc, char **argv)
{
    (void)argc; (void)argv;
    cec_state_t snap;
    if (xSemaphoreTake(g_state.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        printf("error: state mutex timeout\n");
        return 1;
    }
    snap = g_state;
    xSemaphoreGive(g_state.mutex);

    printf("eps1   raw=%7.3f A   filt=%7.3f A   zero_off=%.4f V\n",
           snap.current_raw_a[0], snap.current_a[0], g_acs.cal[0].zero_offset_v);
    printf("eps2   raw=%7.3f A   filt=%7.3f A   zero_off=%.4f V\n",
           snap.current_raw_a[1], snap.current_a[1], g_acs.cal[1].zero_offset_v);
    printf("temp   %.2f C   load=%s   flags=0x%02x\n",
           snap.board_temp_c, cec_load_state_name(snap.load_state), snap.status_flags);
    printf("config id=%u supply=%.2f V oc=%.1f A alpha=%.2f raw_telem=%d\n",
           g_config.module_id, g_config.supply_voltage, g_config.oc_threshold_a,
           g_config.ema_alpha, g_config.output_raw);
    return 0;
}

static int cmd_cal(int argc, char **argv)
{
    // 'cal'              -> zero-offset cal on both sensors
    // 'cal span <amps>'  -> span calibration with known current
    if (argc >= 2 && strcmp(argv[1], "span") == 0) {
        if (argc < 3) {
            printf("usage: cal span <known_amps>\n");
            return 1;
        }
        float known = strtof(argv[2], NULL);
        if (known == 0.0f) {
            printf("error: known current must be nonzero\n");
            return 1;
        }
        for (int i = 0; i < CEC_NUM_CABLES; i++) {
            acs758_calibrate_span(&g_acs, i, known);
            cec_capture_channel_t ch;
            capture_channel_snapshot(i, &ch);
            cec_capture_update_channel(i, &ch);
        }
        printf("span cal done at %.2f A\n", known);
        return 0;
    }

    printf("zero-cal: ensure NO current flows in either cable...\n");
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        float off = acs758_calibrate_zero(&g_acs, i);
        cec_config_save_zero_offset(i, off);
        cec_capture_channel_t ch;
        capture_channel_snapshot(i, &ch);
        cec_capture_update_channel(i, &ch);
        printf("sensor %d zero offset = %.4f V (saved)\n", i, off);
    }
    return 0;
}

static int cmd_save(int argc, char **argv)
{
    (void)argc; (void)argv;
    cec_config_save(&g_config);
    return 0;
}

static int cmd_set(int argc, char **argv)
{
    if (argc < 3) {
        printf("usage: set <alpha|oc|supply> <value>\n");
        return 1;
    }
    float v = strtof(argv[2], NULL);
    if (strcmp(argv[1], "alpha") == 0) {
        g_config.ema_alpha = v;
        for (int i = 0; i < CEC_NUM_CABLES; i++) g_ema[i].alpha = v;
        printf("alpha=%.3f\n", v);
    } else if (strcmp(argv[1], "oc") == 0) {
        g_config.oc_threshold_a = v;
        cec_detection_init(&g_detect, v);   // re-init layer 1 with new threshold
        printf("oc=%.2f A\n", v);
    } else if (strcmp(argv[1], "supply") == 0) {
        g_config.supply_voltage = v;
        acs758_set_supply(&g_acs, v);
        for (int i = 0; i < CEC_NUM_CABLES; i++) {
            cec_capture_channel_t ch;
            capture_channel_snapshot(i, &ch);
            cec_capture_update_channel(i, &ch);
        }
        printf("supply=%.3f V\n", v);
    } else {
        printf("error: unknown key '%s'\n", argv[1]);
        return 1;
    }
    printf("(use 'save' to persist)\n");
    return 0;
}

static int cmd_burst(int argc, char **argv)
{
    const char *text = (argc >= 2) ? argv[1] : "manual";
    esp_err_t r = cec_capture_trigger_with_text(CEC_TRIG_MANUAL, text);
    if (r == ESP_OK) {
        printf("burst triggered (annotation=%s)\n", text);
        return 0;
    }
    if (r == ESP_ERR_NOT_FINISHED) {
        printf("error: a burst is already running\n");
        return 1;
    }
    if (r == ESP_ERR_INVALID_STATE) {
        printf("error: cooldown active, try again shortly\n");
        return 1;
    }
    printf("error: trigger failed: %s\n", esp_err_to_name(r));
    return 1;
}

static int cmd_mode(int argc, char **argv)
{
    if (argc < 2) {
        printf("usage: mode <raw|filt>\n");
        return 1;
    }
    if (strcmp(argv[1], "raw")  == 0) g_config.output_raw = true;
    else if (strcmp(argv[1], "filt") == 0) g_config.output_raw = false;
    else { printf("error: unknown mode '%s'\n", argv[1]); return 1; }
    printf("output_raw=%d (use 'save' to persist)\n", g_config.output_raw);
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "show",  "print current readings, calibration, and config",       cmd_show  },
    { "cal",   "zero-offset cal on both sensors, or 'cal span <amps>'", cmd_cal   },
    { "set",   "set <alpha|oc|supply> <value> (in-memory; 'save' to NVS)", cmd_set },
    { "save",  "persist current config to NVS",                         cmd_save  },
    { "mode",  "set telemetry mode: 'mode raw' or 'mode filt'",         cmd_mode  },
    { "burst", "trigger a manual burst capture ('burst <annotation>')", cmd_burst },
};
#define CLI_COMMAND_COUNT (sizeof(CLI_COMMANDS) / sizeof(CLI_COMMANDS[0]))

// ---- Comms task: CAN telemetry to Hub ----
static void comms_task(void *arg)
{
    ESP_LOGI(TAG, "comms task started on core %d", xPortGetCoreID());
    (void)arg;

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
        vTaskDelay(pdMS_TO_TICKS(COMMS_PERIOD_MS));
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

    // Burst capture engine: pre-trigger ring at SAMPLE_RATE_HZ, HS path
    // at 10 kHz/channel via adc_continuous. Channel conversion params
    // come from the live ACS758 calibration so HS samples land in amps.
    cec_capture_config_t cap_cfg = {
        .pre_trigger_capacity = EPS_PRE_TRIGGER_SECONDS * SAMPLE_RATE_HZ,
        .hs_sample_rate_hz    = EPS_BURST_HS_RATE_HZ,
        .hs_duration_ms       = EPS_BURST_HS_DURATION,
        .cooldown_ms          = EPS_BURST_COOLDOWN_MS,
        .n_channels           = CEC_NUM_CABLES,
    };
    for (int i = 0; i < CEC_NUM_CABLES; i++) {
        cap_cfg.channels[i] = (cec_capture_channel_t){
            .channel         = g_acs.channels[i],
            .divider_gain    = ACS758_DIVIDER_GAIN,
            .quiescent_v     = g_acs.cal[i].quiescent_v,
            .sensitivity_v_a = g_acs.cal[i].sensitivity_v_a,
            .zero_offset_v   = g_acs.cal[i].zero_offset_v,
        };
    }
    ESP_ERROR_CHECK(cec_capture_init(&cap_cfg));

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

    // Serial command interface (USB Serial-JTAG console).
    ESP_ERROR_CHECK(cec_cli_init(CLI_COMMANDS, CLI_COMMAND_COUNT));

    ESP_LOGI(TAG, "init complete, tasks running");
}
