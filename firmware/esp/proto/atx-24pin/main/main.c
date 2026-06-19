/*
 * CEC 24-pin Module Firmware - ESP-IDF port
 *
 * Brings up the I2C bus + INA226 (5VSB), the ADC1 voltage-rail divider
 * reads (12V/5V/3V3), the ACS712 current sensors on the same three rails,
 * and the NTC thermistor, all matching the v0.5.9 hardware configuration.
 * Samples everything at 50 Hz, runs each channel through a fast EMA, and
 * emits TelePlot series at 10 Hz with a 1 Hz INFO summary line.
 *
 * Compare against v0.5.9 captures on the same hardware. Numbers should
 * match within measurement noise once per-unit trim is dialed in.
 */

#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_check.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "driver/i2c_master.h"

#include "ina228.h"
#include "driver/gpio.h"
#include "cec_filters.h"
#include "cec_state.h"
#include "cec_config.h"
#include "cec_layer1.h"
#include "cec_layer2.h"
#include "cec_layer3.h"
#include "cec_swing.h"
#include "cec_nvs.h"
#include "cec_capture.h"
#include "cec_cli.h"
#include "cec_teleplot.h"
#include "cec_can.h"
#include "cec_telem.h"
#include "cec_canota.h"

static const char *TAG = "cec_main";

/* Set while a CAN-OTA update is in flight (cec_canota active callback).
 * can_comms_task pauses telemetry TX so it doesn't contend with the OTA
 * stream, and the app stays quiet right before it reboots into the new
 * image. */
static volatile bool s_ota_active = false;
static void ota_active_cb(bool active) { s_ota_active = active; }

/* CAN telemetry to the Hub. The live loop publishes the latest readings
 * into s_telem_pub (under a brief critical section); can_comms_task
 * snapshots it and sends the 3-frame rail-telemetry burst (cec_telem.h)
 * at CEC_CAN_TX_PERIOD_MS. */
static portMUX_TYPE s_telem_mux = portMUX_INITIALIZER_UNLOCKED;
static cec_telem_t  s_telem_pub;

static void can_comms_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "CAN comms task on core %d, telemetry every %d ms",
             xPortGetCoreID(), CEC_CAN_TX_PERIOD_MS);
    uint8_t seq = 0;
    while (1) {
        if (s_ota_active) {                 /* hold off telemetry during a CAN-OTA */
            vTaskDelay(pdMS_TO_TICKS(CEC_CAN_TX_PERIOD_MS));
            continue;
        }
        cec_telem_t t;
        portENTER_CRITICAL(&s_telem_mux);
        t = s_telem_pub;
        portEXIT_CRITICAL(&s_telem_mux);
        t.module_type = CEC_CFG_MODULE_TYPE;
        t.seq = seq++;
        uint8_t f[8];
        for (uint8_t sub = 0; sub < 3; sub++) {
            uint32_t id = cec_telem_pack(&t, sub, f);
            can_send_frame(id, f, sizeof(f));
        }
        vTaskDelay(pdMS_TO_TICKS(CEC_CAN_TX_PERIOD_MS));
    }
}

/* I2C bus pins, matching v0.5.9 wiring on the Lonely Binary ESP32-S3 N16R8 */
#define I2C_PIN_SDA       8
#define I2C_PIN_SCL       9
#define I2C_PORT_NUM      I2C_NUM_0

/* ADC1 channels (GPIO1..7 = ADC1_CH0..6), pin map from v0.5.9 */
#define ADC_CH_V_12V      ADC_CHANNEL_0   /* GPIO1 */
#define ADC_CH_V_5V       ADC_CHANNEL_1   /* GPIO2 */
#define ADC_CH_V_3V3      ADC_CHANNEL_2   /* GPIO3 */
#define ADC_CH_I_12V      ADC_CHANNEL_3   /* GPIO4 */
#define ADC_CH_I_5V       ADC_CHANNEL_4   /* GPIO5 */
#define ADC_CH_I_3V3      ADC_CHANNEL_5   /* GPIO6 */
#define ADC_CH_NTC        ADC_CHANNEL_6   /* GPIO7 */

/* Per-rail trim factors carried forward from v0.5.9 (hardware-specific) */
#define TRIM_12V          1.0000f
#define TRIM_5V           0.9962f
#define TRIM_3V3          0.9915f
#define TRIM_5VSB         0.9901f

/* Hardware voltage dividers (top + bottom of resistor stack), v0.5.9 */
#define SCALE_12V         ((47000.0f + 10000.0f) / 10000.0f)
#define SCALE_5V          ((15000.0f + 10000.0f) / 10000.0f)
#define SCALE_3V3         (( 4700.0f + 10000.0f) / 10000.0f)

/* ACS712 divider (between sensor output and ADC pin) and per-part
 * sensitivities, from v0.5.9. The 30A part sits on the 12V rail; both
 * 20A parts sit on the 5V/3V3 rails. */
#define ACS712_DIVIDER       ((20000.0f + 30000.0f) / 30000.0f)
#define ACS712_30A_SENS      0.066f
#define ACS712_20A_SENS      0.100f
/* Per-rail no-load output (post-divider voltage). Nominal Vcc/2 = 2.20 V
 * but the part-to-part variation is several tens of mV (hundreds of mA
 * at these sensitivities), so each rail gets its own constant for hand-
 * tuning. The boot-time diagnostic logs the measured no-load output —
 * with the PSU disconnected at first boot, copy those values here. Full
 * runtime calibration lands with the serial-command + NVS path.
 *
 * Values below are the per-unit no-load measurements captured against
 * this board with the PSU disconnected. */
#define ACS712_ZERO_12V      2.4483f
#define ACS712_ZERO_5V       2.1967f
#define ACS712_ZERO_3V3      2.2117f

/* Loop cadence. Sample at 50 Hz to match v0.5.9; emit TelePlot at 10 Hz
 * (every 5th iteration); log an INFO summary at 1 Hz (every 50th). */
#define SAMPLE_PERIOD_MS  20
#define TELEPLOT_DIVIDER  5
#define LOG_DIVIDER       50

/* EMA smoothing. At 50 Hz, alpha=0.02 gives a ~1 s time constant, matching
 * the v0.5.9 EMA_ALPHA_FAST. */
#define EMA_ALPHA_FAST    0.02f

/* I2C bus handle (shared across components later) */
static i2c_master_bus_handle_t s_i2c_bus = NULL;

/* PRODUCTION sensing: one INA228 per rail (12V/5V/3V3/5VSB). Each gives bus
 * voltage + current, replacing the divider/ACS712/INA226 front end. */
static ina228_handle_t s_ina228_12v  = NULL;
static ina228_handle_t s_ina228_5v   = NULL;
static ina228_handle_t s_ina228_3v3  = NULL;
static ina228_handle_t s_ina228_5vsb = NULL;

/* Read one rail's bus voltage + current. True only if both reads succeed. */
static bool ina228_read_rail(ina228_handle_t h, float *v, float *i)
{
    if (h == NULL) return false;
    return ina228_read_bus_voltage(h, v) == ESP_OK &&
           ina228_read_current(h, i) == ESP_OK;
}

/* (LS divider rail configs removed -- rails now read via INA228.) */

/* (NTC + ACS712 + LS/HS divider configs removed -- the INA228s supply
 * per-rail V/I and the 12V die sensor supplies temperature.) */

/* Filter state */
static ema_t s_v_5vsb_ema, s_i_5vsb_ema;
static ema_t s_v_12v_ema, s_v_5v_ema, s_v_3v3_ema;
static ema_t s_i_12v_ema, s_i_5v_ema, s_i_3v3_ema;
static ema_t s_temp_ema;

/* State machine */
static cec_state_t s_state = CEC_STATE_OFF;
static int64_t s_state_entered_us = 0;

/* Layer 1 static-threshold detectors per rail. Bands + debounce live
 * in cec_config.{c,h} (the board-variation point).
 *
 * Mask Layer 1 for this long after every state transition. Covers the
 * PSU inrush (most visibly on 5VSB OFF -> STANDBY ramp, where the rail
 * passes through 1..5 V on its way up and would otherwise sustain
 * CRITICAL for the consecutive-sample window). 500 ms is loose enough
 * for typical PSU ramp times and tight enough not to miss real faults. */
#define LAYER1_SETTLE_US  (500LL * 1000)

static cec_layer1_detector_t s_l1_12v, s_l1_5v, s_l1_3v3, s_l1_5vsb;
static cec_severity_t s_last_sev_12v  = CEC_SEV_NONE;
static cec_severity_t s_last_sev_5v   = CEC_SEV_NONE;
static cec_severity_t s_last_sev_3v3  = CEC_SEV_NONE;
static cec_severity_t s_last_sev_5vsb = CEC_SEV_NONE;

/* Layer 2 adaptive transient detectors. Per-rail min-thresholds and
 * k_sigma live in cec_config.h (the board-variation point). */
static cec_layer2_detector_t s_l2_v_12v, s_l2_v_5v, s_l2_v_3v3, s_l2_v_5vsb;
static cec_layer2_detector_t s_l2_i_12v, s_l2_i_5v, s_l2_i_3v3;

/* Layer 3 per-(state, rail) running profile. Z-score threshold 4.0
 * (v0.5.9 default). Adapt rate 0.0005 gives an effective window of
 * roughly 2000 samples (40 s at 50 Hz) once the profile is warm. */
#define LAYER3_Z_THRESHOLD   4.0f
#define PROFILE_ADAPT_RATE   0.0005f
typedef enum {
    PROF_V_12V = 0, PROF_V_5V,  PROF_V_3V3,  PROF_V_5VSB,
    PROF_I_12V,     PROF_I_5V,  PROF_I_3V3,  PROF_I_5VSB,
    PROF_TEMP,      PROF_COUNT
} prof_idx_t;
static cec_rail_profile_t s_profiles[CEC_STATE_COUNT][PROF_COUNT];
static bool s_z_above_last = false;

/* Power swing: 250-sample rolling window (~5 s at 50 Hz). Adaptive
 * threshold = max(8 W, 25% * window_mean), 2 consecutive bad samples
 * (~40 ms) before firing. From v0.5.9. */
#define POWER_SWING_WINDOW_SIZE        250
#define POWER_SWING_CONSECUTIVE        2
#define POWER_SWING_MIN_THRESHOLD_W    8.0f
#define POWER_SWING_FRACTION           0.25f
static cec_swing_detector_t s_power_swing;
static float s_power_swing_buf[POWER_SWING_WINDOW_SIZE];

/* Current swing: per-rail 250-sample rolling window with fixed
 * thresholds. 3 consecutive bad samples (~60 ms) before firing. From
 * v0.5.9. Only one rail fires per iteration (priority 12V > 5V > 3V3). */
#define CURRENT_SWING_WINDOW_SIZE      250
#define CURRENT_SWING_CONSECUTIVE      3
#define CURRENT_SWING_THRESH_I_12V     0.30f
#define CURRENT_SWING_THRESH_I_5V      0.50f
#define CURRENT_SWING_THRESH_I_3V3     0.30f
static cec_swing_detector_t s_i_swing_12v, s_i_swing_5v, s_i_swing_3v3;
static float s_i_swing_12v_buf[CURRENT_SWING_WINDOW_SIZE];
static float s_i_swing_5v_buf [CURRENT_SWING_WINDOW_SIZE];
static float s_i_swing_3v3_buf[CURRENT_SWING_WINDOW_SIZE];

/* NVS persistence for Layer 3 profiles. The magic prefix lets a future
 * firmware revision reject an old blob cleanly if the layout changes. */
#define NVS_PROFILES_KEY     "profiles"
#define NVS_PROFILES_MAGIC   0xCEC30001U
#define NVS_SETTINGS_KEY     "settings"
#define NVS_SETTINGS_MAGIC   0xCEC50001U
#define NVS_SAVE_INTERVAL_US (5LL * 60 * 1000 * 1000)   /* 5 minutes */
static bool    s_profiles_dirty = false;
static int64_t s_last_nvs_save_us = 0;

/* Per-rail INA228 calibration, persisted so a bench cal survives reboots.
 * Index 0..3 = 12V/5V/3V3/5VSB (CAL_RAIL_NAME). The shunt sets accuracy
 * (~±1% tolerance uncalibrated); a one-point load cal sets the current gain
 * (removing the tolerance), a second point adds the offset, and a DMM point
 * sets the voltage gain. See cli_cmd_cal. */
#define NVS_CAL_KEY    "ina_cal"
#define NVS_CAL_MAGIC  0xCEC60001U
#define CAL_N_RAILS    4
typedef struct {
    float v_trim;     /* bus-voltage gain (1.0 = raw) */
    float i_trim;     /* current gain (1.0 = raw) */
    float i_offset;   /* current offset, amps (0.0 = none) */
} cec_rail_cal_t;
static cec_rail_cal_t s_cal[CAL_N_RAILS];   /* identity until load_cal_from_nvs() */
/* Pending current cal points per rail: 1 point -> gain only, 2 -> gain+offset. */
static struct { int n; float raw[2], tru[2]; } s_cal_pts[CAL_N_RAILS];

/* Shutdown detection: 1-second rate-of-change window on v_12v_ema.
 * Triggers when 12V is dropping faster than 0.5 V/s from a nominal-ish
 * starting point (> 5 V) — i.e. the PSU is in the middle of going down.
 * Fires CEC_TRIG_SHUTDOWN (bypasses cooldown so a real shutdown still
 * captures even if a recent burst is in cooldown) and asserts a 30 s
 * mute window during which all detector layers go quiet so we don't
 * spam triggers on collapsing rails. The mute clears either by timeout
 * or by the state classifier landing on OFF or STANDBY, whichever
 * comes first.
 *
 * The 5VSB-defined STANDBY in cec_state_classify is what makes this
 * clean: STANDBY now explicitly means "main rails off, 5VSB up",
 * which is the canonical post-shutdown stable state, so reaching it
 * is a positive signal that the shutdown has completed. */
#define V_12V_RATE_HISTORY_SIZE        50           /* 1 s at 50 Hz */
#define V_12V_SHUTDOWN_RATE_THRESHOLD  (-0.5f)      /* V/s, negative */
#define V_12V_SHUTDOWN_MIN_ARMED_V     5.0f         /* don't trigger if 12V was already low */
#define SHUTDOWN_MUTE_DURATION_US      (30LL * 1000 * 1000)
static float   s_v_12v_history[V_12V_RATE_HISTORY_SIZE];
static size_t  s_v_12v_hist_idx = 0;
static size_t  s_v_12v_hist_count = 0;
static bool    s_shutting_down = false;
static int64_t s_shutdown_start_us = 0;

/* Runtime-toggleable layer enables, persisted to NVS so they survive
 * reboots. Defaults are all-on. Toggle via the serial CLI. */
typedef struct {
    bool layer1;
    bool layer2;
    bool layer3;
    bool swing_power;
    bool swing_current;
} cec_settings_t;
static cec_settings_t s_settings = {
    .layer1 = true, .layer2 = true, .layer3 = true,
    .swing_power = true, .swing_current = true,
};
static bool s_settings_dirty = false;

static void init_i2c_bus(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = I2C_PORT_NUM,
        .scl_io_num = I2C_PIN_SCL,
        .sda_io_num = I2C_PIN_SDA,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_i2c_bus));
    ESP_LOGI(TAG, "I2C bus: SDA=GPIO%d, SCL=GPIO%d", I2C_PIN_SDA, I2C_PIN_SCL);
}

/* Production: create the four per-rail INA228s (addresses/shunts from
 * cec_config.h, traced from the board netlist). 2 mOhm main rails use the
 * +/-40.96 mV range (finer); 25 mOhm 5VSB uses +/-163.84 mV. */
static esp_err_t init_ina228_rails(void)
{
    const struct {
        ina228_handle_t *h; uint8_t addr; float shunt; float max_a; uint8_t range; const char *name;
    } rails[] = {
        { &s_ina228_12v,  INA228_ADDR_12V,  INA228_SHUNT_MAIN, 20.0f, 1, "12V"  },
        { &s_ina228_5v,   INA228_ADDR_5V,   INA228_SHUNT_MAIN, 20.0f, 1, "5V"   },
        { &s_ina228_3v3,  INA228_ADDR_3V3,  INA228_SHUNT_MAIN, 20.0f, 1, "3V3"  },
        { &s_ina228_5vsb, INA228_ADDR_5VSB, INA228_SHUNT_5VSB,  6.0f, 0, "5VSB" },
    };
    esp_err_t first_err = ESP_OK;
    for (size_t k = 0; k < sizeof(rails) / sizeof(rails[0]); k++) {
        ina228_config_t cfg = INA228_CONFIG_DEFAULT();
        cfg.bus_handle    = s_i2c_bus;
        cfg.i2c_addr      = rails[k].addr;
        cfg.shunt_ohms    = rails[k].shunt;
        cfg.max_current_a = rails[k].max_a;
        cfg.adc_range     = rails[k].range;
        esp_err_t e = ina228_create(&cfg, rails[k].h);
        if (e != ESP_OK) {
            ESP_LOGE(TAG, "INA228 %s @ 0x%02X init failed: %s",
                     rails[k].name, rails[k].addr, esp_err_to_name(e));
            if (first_err == ESP_OK) first_err = e;
        }
    }
    return first_err;
}

/* Status indicator LED: D2 on STATUS_LED_GPIO, active-high. */
static void init_status_led(void)
{
    gpio_config_t out = {
        .pin_bit_mask = 1ULL << STATUS_LED_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&out);
    gpio_set_level(STATUS_LED_GPIO, 0);

    /* PSU control/status inputs, buffered by U4/U5 (read-only monitoring). */
    gpio_config_t in = {
        .pin_bit_mask = (1ULL << PWROK_BUF_GPIO) | (1ULL << PSON_BUF_GPIO),
        .mode = GPIO_MODE_INPUT,
    };
    gpio_config(&in);
}

static void init_layer1(void)
{
    cec_layer1_init_band(&s_l1_12v,  &CEC_CFG_L1_SPEC_12V,  L1_CRIT_CONSECUTIVE);
    cec_layer1_init_band(&s_l1_5v,   &CEC_CFG_L1_SPEC_5V,   L1_CRIT_CONSECUTIVE);
    cec_layer1_init_band(&s_l1_3v3,  &CEC_CFG_L1_SPEC_3V3,  L1_CRIT_CONSECUTIVE);
    cec_layer1_init_band(&s_l1_5vsb, &CEC_CFG_L1_SPEC_5VSB, L1_CRIT_CONSECUTIVE);
}

static void init_layer2(void)
{
    cec_layer2_init_adaptive(&s_l2_v_12v,  L2_MIN_V_12V,  LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_v_5v,   L2_MIN_V_5V,   LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_v_3v3,  L2_MIN_V_3V3,  LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_v_5vsb, L2_MIN_V_5VSB, LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_i_12v,  L2_MIN_I_12V,  LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_i_5v,   L2_MIN_I_5V,   LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
    cec_layer2_init_adaptive(&s_l2_i_3v3,  L2_MIN_I_3V3,  LAYER2_K_SIGMA, LAYER2_CONSECUTIVE);
}

static void init_layer3_profiles(void)
{
    for (int s = 0; s < CEC_STATE_COUNT; s++) {
        for (int r = 0; r < PROF_COUNT; r++) {
            cec_rail_profile_init(&s_profiles[s][r]);
        }
    }
}

/* Clear Layer 2 consecutive-fire counters on a "state up" transition so
 * a pending fire from STANDBY ramp values doesn't survive into IDLE. */
static void reset_layer2_counters(void)
{
    cec_layer2_reset(&s_l2_v_12v);
    cec_layer2_reset(&s_l2_v_5v);
    cec_layer2_reset(&s_l2_v_3v3);
    cec_layer2_reset(&s_l2_v_5vsb);
    cec_layer2_reset(&s_l2_i_12v);
    cec_layer2_reset(&s_l2_i_5v);
    cec_layer2_reset(&s_l2_i_3v3);
}

static void init_swing_detectors(void)
{
    cec_swing_detector_init(&s_power_swing, s_power_swing_buf,
                            POWER_SWING_WINDOW_SIZE, POWER_SWING_CONSECUTIVE);
    cec_swing_detector_init(&s_i_swing_12v, s_i_swing_12v_buf,
                            CURRENT_SWING_WINDOW_SIZE, CURRENT_SWING_CONSECUTIVE);
    cec_swing_detector_init(&s_i_swing_5v,  s_i_swing_5v_buf,
                            CURRENT_SWING_WINDOW_SIZE, CURRENT_SWING_CONSECUTIVE);
    cec_swing_detector_init(&s_i_swing_3v3, s_i_swing_3v3_buf,
                            CURRENT_SWING_WINDOW_SIZE, CURRENT_SWING_CONSECUTIVE);
}

/* On state-up the rails go from ~0 V to nominal in milliseconds; the
 * swing windows had been collecting near-zero samples and the new
 * "huge swing" would otherwise fire on the very first IDLE sample.
 * Empty the windows so they re-fill cleanly from in-state values. */
static void reset_swing_windows(void)
{
    cec_swing_detector_reset_empty(&s_power_swing);
    cec_swing_detector_reset_empty(&s_i_swing_12v);
    cec_swing_detector_reset_empty(&s_i_swing_5v);
    cec_swing_detector_reset_empty(&s_i_swing_3v3);
}

/* Same idea for the v_12v rate-of-change history that drives shutdown
 * detection: clear it on state-up so the first 1 s of in-state
 * sampling refills it cleanly instead of being polluted by 0 V values
 * from STANDBY/OFF. */
static void reset_v_12v_history(void)
{
    memset(s_v_12v_history, 0, sizeof(s_v_12v_history));
    s_v_12v_hist_idx = 0;
    s_v_12v_hist_count = 0;
}

/* Load profiles from NVS if the stored blob is valid; otherwise leave
 * the (already-zeroed) profile array alone. Logs the outcome so it's
 * obvious from the boot log whether we picked up warm state. */
static void load_profiles_from_nvs(void)
{
    esp_err_t err = cec_nvs_load_blob(NVS_PROFILES_KEY, NVS_PROFILES_MAGIC,
                                      s_profiles, sizeof(s_profiles));
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "NVS: loaded profiles (%u bytes)",
                 (unsigned)sizeof(s_profiles));
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGI(TAG, "NVS: no saved profiles, starting cold");
    } else if (err == ESP_ERR_INVALID_VERSION || err == ESP_ERR_INVALID_SIZE) {
        ESP_LOGW(TAG, "NVS: stored profiles unusable (%s), clearing and starting cold",
                 esp_err_to_name(err));
        cec_nvs_clear_blob(NVS_PROFILES_KEY);
    } else {
        ESP_LOGW(TAG, "NVS: load failed (%s), profiles will warm from cold",
                 esp_err_to_name(err));
    }
}

static void load_settings_from_nvs(void)
{
    cec_settings_t loaded;
    esp_err_t err = cec_nvs_load_blob(NVS_SETTINGS_KEY, NVS_SETTINGS_MAGIC,
                                      &loaded, sizeof(loaded));
    if (err == ESP_OK) {
        s_settings = loaded;
        ESP_LOGI(TAG, "NVS: loaded settings (L1=%d L2=%d L3=%d sp=%d sc=%d)",
                 s_settings.layer1, s_settings.layer2, s_settings.layer3,
                 s_settings.swing_power, s_settings.swing_current);
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGI(TAG, "NVS: no saved settings, using defaults (all-on)");
    } else if (err == ESP_ERR_INVALID_VERSION || err == ESP_ERR_INVALID_SIZE) {
        ESP_LOGW(TAG, "NVS: stored settings unusable (%s), clearing",
                 esp_err_to_name(err));
        cec_nvs_clear_blob(NVS_SETTINGS_KEY);
    }
}

static void save_settings_to_nvs(void)
{
    esp_err_t err = cec_nvs_save_blob(NVS_SETTINGS_KEY, NVS_SETTINGS_MAGIC,
                                      &s_settings, sizeof(s_settings));
    if (err == ESP_OK) {
        s_settings_dirty = false;
        ESP_LOGI(TAG, "NVS: saved settings");
    } else {
        ESP_LOGW(TAG, "NVS: settings save failed: %s", esp_err_to_name(err));
    }
}

/* ------------------------- INA228 calibration ------------------------- */

static const char *CAL_RAIL_NAME[CAL_N_RAILS] = { "12v", "5v", "3v3", "5vsb" };

static ina228_handle_t cal_handle(int idx)
{
    switch (idx) {
        case 0: return s_ina228_12v;
        case 1: return s_ina228_5v;
        case 2: return s_ina228_3v3;
        case 3: return s_ina228_5vsb;
        default: return NULL;
    }
}

static int cal_rail_index(const char *name)
{
    if (!strcmp(name, "12v") || !strcmp(name, "12"))                       return 0;
    if (!strcmp(name, "5v")  || !strcmp(name, "5"))                        return 1;
    if (!strcmp(name, "3v3") || !strcmp(name, "3.3") || !strcmp(name, "3")) return 2;
    if (!strcmp(name, "5vsb")|| !strcmp(name, "5sb") || !strcmp(name, "sb")) return 3;
    return -1;
}

/* Push the stored cal for a rail onto its live INA228 handle. */
static void cal_apply(int idx)
{
    ina228_handle_t h = cal_handle(idx);
    if (h == NULL) return;
    ina228_set_voltage_trim(h, s_cal[idx].v_trim);
    ina228_set_current_cal(h, s_cal[idx].i_trim, s_cal[idx].i_offset);
}

/* Average N back-to-back reads to settle ADC noise for a clean cal point. */
static esp_err_t cal_read_current_uncal_avg(ina228_handle_t h, float *out)
{
    float acc = 0.0f; int got = 0;
    for (int i = 0; i < 16; i++) {
        float v;
        if (ina228_read_current_uncal(h, &v) == ESP_OK) { acc += v; got++; }
    }
    if (got == 0) return ESP_FAIL;
    *out = acc / got;
    return ESP_OK;
}

static esp_err_t cal_read_voltage_avg(ina228_handle_t h, float *out)
{
    float acc = 0.0f; int got = 0;
    for (int i = 0; i < 16; i++) {
        float v;
        if (ina228_read_bus_voltage(h, &v) == ESP_OK) { acc += v; got++; }
    }
    if (got == 0) return ESP_FAIL;
    *out = acc / got;
    return ESP_OK;
}

static void load_cal_from_nvs(void)
{
    for (int i = 0; i < CAL_N_RAILS; i++) {
        s_cal[i] = (cec_rail_cal_t){ 1.0f, 1.0f, 0.0f };
        s_cal_pts[i].n = 0;
    }
    cec_rail_cal_t loaded[CAL_N_RAILS];
    esp_err_t err = cec_nvs_load_blob(NVS_CAL_KEY, NVS_CAL_MAGIC, loaded, sizeof(loaded));
    if (err == ESP_OK) {
        memcpy(s_cal, loaded, sizeof(s_cal));
        ESP_LOGI(TAG, "NVS: loaded INA228 cal (e.g. 12V gain i=%.4f v=%.4f off=%.4fA)",
                 s_cal[0].i_trim, s_cal[0].v_trim, s_cal[0].i_offset);
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGI(TAG, "NVS: no saved cal, using raw (identity) -- run `cal` to calibrate");
    } else if (err == ESP_ERR_INVALID_VERSION || err == ESP_ERR_INVALID_SIZE) {
        ESP_LOGW(TAG, "NVS: stored cal unusable (%s), clearing", esp_err_to_name(err));
        cec_nvs_clear_blob(NVS_CAL_KEY);
    }
    for (int i = 0; i < CAL_N_RAILS; i++) cal_apply(i);
}

static void save_cal_to_nvs(void)
{
    esp_err_t err = cec_nvs_save_blob(NVS_CAL_KEY, NVS_CAL_MAGIC, s_cal, sizeof(s_cal));
    if (err == ESP_OK)
        ESP_LOGI(TAG, "NVS: saved INA228 cal");
    else
        ESP_LOGW(TAG, "NVS: cal save failed: %s", esp_err_to_name(err));
}

/* Re-prime EMAs to the next sample on transitions UP into the
 * main-rails-on regime. Without this, the EMAs would carry their
 * pre-transition (near-zero) values into the new state and produce
 * misleading instant-vs-EMA deviations until they catch up. v0.5.9
 * does the same in reset_filters_on_state_up(). */
static void reset_emas_on_state_up(void)
{
    ema_reset(&s_v_5vsb_ema); ema_reset(&s_i_5vsb_ema);
    ema_reset(&s_v_12v_ema);  ema_reset(&s_v_5v_ema);  ema_reset(&s_v_3v3_ema);
    ema_reset(&s_i_12v_ema);  ema_reset(&s_i_5v_ema);  ema_reset(&s_i_3v3_ema);
    ema_reset(&s_temp_ema);
}

typedef struct {
    cec_severity_t sev;
    bool entered_critical;   /* true on the iteration where sev steps to CRITICAL */
} layer1_step_result_t;

/* Update one rail's Layer 1 detector, log on severity transitions, and
 * report whether this is the iteration on which the rail just stepped
 * into CRITICAL — the caller uses that to fire a burst trigger exactly
 * once per fault entry. */
static layer1_step_result_t layer1_step(const char *rail_name,
                                        cec_layer1_detector_t *d,
                                        cec_severity_t *last_sev,
                                        float v_rail)
{
    cec_severity_t prev = *last_sev;
    cec_severity_t sev = cec_layer1_update(d, v_rail);
    if (sev != prev) {
        if (sev != CEC_SEV_NONE) {
            ESP_LOGW(TAG, "L1: %s %s (v=%.3f, nominal=%.2f)",
                     rail_name, cec_severity_name(sev), v_rail, d->spec.nominal);
        } else {
            ESP_LOGI(TAG, "L1: %s recovered (v=%.3f)", rail_name, v_rail);
        }
        *last_sev = sev;
    }
    return (layer1_step_result_t){
        .sev = sev,
        .entered_critical = (prev != CEC_SEV_CRITICAL && sev == CEC_SEV_CRITICAL),
    };
}

/* Sample each ACS712's no-load output and log what it reads, along with
 * the equivalent offset current vs. the constants currently compiled in.
 * Run once at boot before the main loop starts feeding the sensors.
 * Lets you copy the measured no-load voltages directly into
 * ACS712_ZERO_{12V,5V,3V3} for a per-unit-tuned offset until the proper
 * serial-command / NVS calibration path lands. */
/* (ACS712 no-load diagnostic removed -- the INA228 needs no per-rail zero.) */

/* ---- Burst-capture shapes + hooks (app-side) ----
 * The shared cec_capture engine treats rows as opaque bytes and calls
 * back here for HS acquisition + dump rendering. Shapes and dump
 * formats match v0.5.9 so existing capture-analysis tooling works
 * unchanged. */

/* Pre-trigger sample (50 Hz, full sensor set). */
typedef struct {
    uint32_t ts_ms;
    uint8_t  state;     /* cec_state_t cast to byte */
    float    v_12v,  i_12v;
    float    v_5v,   i_5v;
    float    v_3v3,  i_3v3;
    float    v_5vsb, i_5vsb;
    float    temp_c;
    uint8_t  ps_on, pwr_ok;   /* buffered PS_ON# (1=on) + PWR_OK (1=good) */
} cec_capture_sample_t;

/* HS sample (1 kHz): the main rails plus the PS_ON#/PWR_OK sense-pin
 * buffer outputs (U4/U5). The sense pins are GPIO reads, so they add no
 * I2C to the 1 kHz fill; the slow 5VSB rail and die-temp stay in the
 * 50 Hz pre-roll (an extra INA228 read per HS row would crowd the
 * sub-1 ms budget for little value -- those signals don't move fast). */
typedef struct {
    uint32_t ts_us_offset;   /* microseconds since HS capture start */
    float    v_12v, i_12v;
    float    v_5v,  i_5v;
    float    v_3v3, i_3v3;
    uint8_t  ps_on, pwr_ok;  /* buffered PS_ON# (1=on) + PWR_OK (1=good) */
} cec_capture_hs_sample_t;

/* Sizes from v0.5.9 (preserved exactly): pre-trigger covers 20 s at
 * 50 Hz, HS covers 4 s at 1 kHz, 10 s cooldown between bursts. */
#define PRE_TRIGGER_BUF_SIZE   1000
#define HS_BURST_BUF_SIZE      4000
#define HS_SAMPLE_RATE_HZ      1000
#define BURST_COOLDOWN_MS      10000

/* Newest state byte pushed into the pre-trigger ring; rendered into the
 * BURST_BEGIN line's state token (the engine snapshots it at dispatch,
 * matching the old state_at_trigger semantics). */
static volatile uint8_t s_last_capture_state = 0;

static void capture_state_token(char *buf, size_t cap)
{
    snprintf(buf, cap, "%d", (int)s_last_capture_state);
}

/* HS fill callback. Paced at 1 kHz on the dispatcher task (Core 1) —
 * must stay well under 1 ms. Six reads off the cec_adc continuous-mode
 * latest-mV table + scaling comfortably fit. */
static void capture_hs_fill(void *row_v, const void *prev_v, uint32_t ts_us_offset)
{
    cec_capture_hs_sample_t *s = row_v;
    s->ts_us_offset = ts_us_offset;
    /* INA228 reads (V+I per rail). NOTE: the INA228 update rate (~315 Hz) is
     * below this 1 kHz HS cadence, so bursts oversample -- real but stepped.
     * The proper fast path (INA228 ALERT-triggered, spec 6.10) is a follow-up. */
    ina228_read_rail(s_ina228_12v, &s->v_12v, &s->i_12v);
    ina228_read_rail(s_ina228_5v,  &s->v_5v,  &s->i_5v);
    ina228_read_rail(s_ina228_3v3, &s->v_3v3, &s->i_3v3);

    /* All-zero-rails carry-forward (v0.5.9 lineage). With cec_adc in
     * continuous/DMA mode the latest-mV table holds the last value, so
     * a true all-zero row is rare now (it meant a SAR glitch in the
     * oneshot era); kept as cheap insurance. Only bites if a burst runs
     * across a real full-rail collapse, which then shows as a flat-line
     * in the carried-forward window. */
    if (prev_v != NULL && s->v_12v == 0.0f && s->v_5v == 0.0f && s->v_3v3 == 0.0f) {
        const cec_capture_hs_sample_t *prev = prev_v;
        s->v_12v = prev->v_12v; s->i_12v = prev->i_12v;
        s->v_5v  = prev->v_5v;  s->i_5v  = prev->i_5v;
        s->v_3v3 = prev->v_3v3; s->i_3v3 = prev->i_3v3;
    }

    /* Sense-pin buffer outputs (U4 PWR_OK / U5 PS_ON#). GPIO reads -- no
     * I2C, so they fit the 1 kHz HS path, and 1 kHz is where they matter:
     * PWR_OK deasserts within a few ms of a fault, and the HS window times
     * that edge against the 12V collapse far better than the 50 Hz pre-roll.
     * Same polarity as the live loop: PWR_OK active-high (good),
     * PS_ON# active-low (level 0 = PSU commanded on). Read fresh every row
     * (digital + instantaneous), so they are never carried forward. */
    s->pwr_ok = (gpio_get_level(PWROK_BUF_GPIO) != 0) ? 1 : 0;
    s->ps_on  = (gpio_get_level(PSON_BUF_GPIO)  == 0) ? 1 : 0;
}

/* Dump renderers: byte-identical to the pre-merge (v0.5.9-format) dump. */
static int capture_render_pre(const void *sample, char *buf, size_t cap)
{
    const cec_capture_sample_t *p = sample;
    unsigned ts = (unsigned)p->ts_ms;
    return snprintf(buf, cap,
                    ">b_v_12v:%u:%.3f\n"
                    ">b_i_12v:%u:%.3f\n"
                    ">b_v_5v:%u:%.3f\n"
                    ">b_i_5v:%u:%.3f\n"
                    ">b_v_3v3:%u:%.3f\n"
                    ">b_i_3v3:%u:%.3f\n"
                    ">b_v_5vsb:%u:%.3f\n"
                    ">b_i_5vsb:%u:%.4f\n"
                    ">b_temp:%u:%.2f\n"
                    ">b_ps_on:%u:%d\n"
                    ">b_pwr_ok:%u:%d\n"
                    ">b_state:%u:%d\n",
                    ts, p->v_12v,  ts, p->i_12v,
                    ts, p->v_5v,   ts, p->i_5v,
                    ts, p->v_3v3,  ts, p->i_3v3,
                    ts, p->v_5vsb, ts, p->i_5vsb,
                    ts, p->temp_c,
                    ts, (int)p->ps_on, ts, (int)p->pwr_ok,
                    ts, (int)p->state);
}

static int capture_render_hs(const void *row_v, int64_t hs_start_us,
                             char *buf, size_t cap)
{
    const cec_capture_hs_sample_t *s = row_v;
    unsigned ts = (unsigned)((uint32_t)(hs_start_us / 1000)
                             + (s->ts_us_offset / 1000));
    return snprintf(buf, cap,
                    ">hs_v_12v:%u:%.3f\n"
                    ">hs_i_12v:%u:%.3f\n"
                    ">hs_v_5v:%u:%.3f\n"
                    ">hs_i_5v:%u:%.3f\n"
                    ">hs_v_3v3:%u:%.3f\n"
                    ">hs_i_3v3:%u:%.3f\n"
                    ">hs_ps_on:%u:%d\n"
                    ">hs_pwr_ok:%u:%d\n",
                    ts, s->v_12v, ts, s->i_12v,
                    ts, s->v_5v,  ts, s->i_5v,
                    ts, s->v_3v3, ts, s->i_3v3,
                    ts, (int)s->ps_on, ts, (int)s->pwr_ok);
}

/* ---------------------------- CLI handlers ---------------------------- */

/* Trigger a manual burst with optional caller-supplied annotation text.
 * Tokens argv[1..argc-1] are space-joined into a single annotation. If
 * no text is supplied the burst still fires with reason=MANUAL but
 * without an annotation line. */
static int cli_cmd_burst(int argc, char **argv)
{
    char text[96];
    text[0] = '\0';
    if (argc >= 2) {
        size_t pos = 0;
        for (int i = 1; i < argc; i++) {
            size_t avail = sizeof(text) - pos - 1;
            if (avail == 0) break;
            if (i > 1) { text[pos++] = ' '; if (pos >= sizeof(text) - 1) break; avail--; }
            size_t n = strlen(argv[i]);
            if (n > avail) n = avail;
            memcpy(text + pos, argv[i], n);
            pos += n;
            text[pos] = '\0';
        }
    }
    esp_err_t err = cec_capture_trigger_with_text(CEC_TRIG_MANUAL,
                                                   text[0] ? text : NULL);
    if (err == ESP_OK) {
        printf("burst triggered (manual%s%s)\n",
               text[0] ? ", annotation: " : "",
               text[0] ? text : "");
        return 0;
    }
    if (err == ESP_ERR_NOT_FINISHED) {
        printf("error: capture already running\n");
    } else if (err == ESP_ERR_INVALID_STATE) {
        printf("error: within cooldown window\n");
    } else {
        printf("error: %s\n", esp_err_to_name(err));
    }
    return 1;
}

static bool *settings_flag_for(const char *name)
{
    if (strcmp(name, "layer1") == 0 || strcmp(name, "l1") == 0)
        return &s_settings.layer1;
    if (strcmp(name, "layer2") == 0 || strcmp(name, "l2") == 0)
        return &s_settings.layer2;
    if (strcmp(name, "layer3") == 0 || strcmp(name, "l3") == 0)
        return &s_settings.layer3;
    if (strcmp(name, "swing_power") == 0 || strcmp(name, "sp") == 0)
        return &s_settings.swing_power;
    if (strcmp(name, "swing_current") == 0 || strcmp(name, "sc") == 0)
        return &s_settings.swing_current;
    return NULL;
}

static int cli_cmd_set(int argc, char **argv)
{
    if (argc != 3) {
        printf("usage: set <layer1|layer2|layer3|swing_power|swing_current> <on|off>\n");
        return 1;
    }
    bool *flag = settings_flag_for(argv[1]);
    if (flag == NULL) {
        printf("error: unknown setting '%s'\n", argv[1]);
        return 1;
    }
    bool new_value;
    if (strcmp(argv[2], "on") == 0 || strcmp(argv[2], "1") == 0)        new_value = true;
    else if (strcmp(argv[2], "off") == 0 || strcmp(argv[2], "0") == 0)  new_value = false;
    else {
        printf("error: value must be 'on' or 'off'\n");
        return 1;
    }
    *flag = new_value;
    s_settings_dirty = true;
    save_settings_to_nvs();
    printf("%s = %s\n", argv[1], new_value ? "on" : "off");
    return 0;
}

static int cli_cmd_status(int argc, char **argv)
{
    bool json = (argc >= 2 && strcmp(argv[1], "json") == 0);
    int64_t now_us = esp_timer_get_time();
    int64_t dwell_ms = (now_us - s_state_entered_us) / 1000;

    if (json) {
        printf("{\"state\":\"%s\",\"dwell_ms\":%lld,",
               cec_state_name(s_state), (long long)dwell_ms);
        printf("\"v\":{\"12v\":%.3f,\"5v\":%.3f,\"3v3\":%.3f,\"5vsb\":%.3f},",
               ema_value(&s_v_12v_ema), ema_value(&s_v_5v_ema),
               ema_value(&s_v_3v3_ema), ema_value(&s_v_5vsb_ema));
        printf("\"i\":{\"12v\":%.3f,\"5v\":%.3f,\"3v3\":%.3f,\"5vsb\":%.4f},",
               ema_value(&s_i_12v_ema), ema_value(&s_i_5v_ema),
               ema_value(&s_i_3v3_ema), ema_value(&s_i_5vsb_ema));
        printf("\"temp_c\":%.2f,", ema_value(&s_temp_ema));
        printf("\"layers\":{\"l1\":%s,\"l2\":%s,\"l3\":%s,\"swing_power\":%s,\"swing_current\":%s},",
               s_settings.layer1 ? "true" : "false",
               s_settings.layer2 ? "true" : "false",
               s_settings.layer3 ? "true" : "false",
               s_settings.swing_power ? "true" : "false",
               s_settings.swing_current ? "true" : "false");
        printf("\"profile_warm\":{");
        for (int s = 0; s < CEC_STATE_COUNT; s++) {
            printf("%s\"%s\":%s",
                   s > 0 ? "," : "",
                   cec_state_name((cec_state_t)s),
                   cec_rail_profile_is_warm(&s_profiles[s][PROF_V_12V]) ? "true" : "false");
        }
        printf("},\"shutting_down\":%s,\"nvs\":{\"profiles_dirty\":%s}}\n",
               s_shutting_down ? "true" : "false",
               s_profiles_dirty ? "true" : "false");
        return 0;
    }

    printf("state:    %s  (dwell %lld ms)%s\n",
           cec_state_name(s_state), (long long)dwell_ms,
           s_shutting_down ? "  [shutdown muted]" : "");
    printf("V:        12=%.3f  5=%.3f  3V3=%.3f  5SB=%.3f\n",
           ema_value(&s_v_12v_ema), ema_value(&s_v_5v_ema),
           ema_value(&s_v_3v3_ema), ema_value(&s_v_5vsb_ema));
    printf("I:        12=%.3f  5=%.3f  3V3=%.3f  5SB=%.4f\n",
           ema_value(&s_i_12v_ema), ema_value(&s_i_5v_ema),
           ema_value(&s_i_3v3_ema), ema_value(&s_i_5vsb_ema));
    printf("temp:     %.2f C\n", ema_value(&s_temp_ema));
    printf("layers:   L1=%s L2=%s L3=%s  swing/power=%s  swing/current=%s\n",
           s_settings.layer1 ? "on" : "off",
           s_settings.layer2 ? "on" : "off",
           s_settings.layer3 ? "on" : "off",
           s_settings.swing_power ? "on" : "off",
           s_settings.swing_current ? "on" : "off");
    printf("profiles: ");
    for (int s = 0; s < CEC_STATE_COUNT; s++) {
        printf("%s=%s  ", cec_state_name((cec_state_t)s),
               cec_rail_profile_is_warm(&s_profiles[s][PROF_V_12V]) ? "warm" : "cold");
    }
    printf("\n");
    printf("nvs:      profiles_dirty=%s\n", s_profiles_dirty ? "yes" : "no");
    return 0;
}

/* Per-rail INA228 calibration against a known bench load + reference meter.
 *   cal                       show the current gains/offsets
 *   cal i <rail> <known_A>    apply a known load, set current gain (2nd point = +offset)
 *   cal v <rail> <known_V>    set the voltage gain from a DMM reading
 *   cal save                  persist to NVS (survives reboot)
 *   cal clear [rail|all]      reset to identity (raw) + save
 * rail = 12v|5v|3v3|5vsb. The shunt tolerance (~±1%) is the uncalibrated
 * error; one current point removes it, a second adds the offset term. */
static int cli_cmd_cal(int argc, char **argv)
{
    if (argc < 2 || !strcmp(argv[1], "show")) {
        printf("INA228 cal (reading = gain*raw + offset; 1.0/0 = raw):\n");
        printf("  rail   v_gain   i_gain   i_off(A)  pts\n");
        for (int i = 0; i < CAL_N_RAILS; i++)
            printf("  %-5s  %.4f   %.4f   %+.4f   %d\n",
                   CAL_RAIL_NAME[i], s_cal[i].v_trim, s_cal[i].i_trim,
                   s_cal[i].i_offset, s_cal_pts[i].n);
        printf("usage: cal i <rail> <known_A> | cal v <rail> <known_V> | "
               "cal save | cal clear [rail|all]\n");
        return 0;
    }
    if (!strcmp(argv[1], "save")) {
        save_cal_to_nvs();
        printf("cal saved to NVS\n");
        return 0;
    }
    if (!strcmp(argv[1], "clear")) {
        const char *who = (argc >= 3) ? argv[2] : "all";
        int only = strcmp(who, "all") ? cal_rail_index(who) : -2;
        if (only == -1) { printf("error: unknown rail '%s'\n", who); return 1; }
        for (int i = 0; i < CAL_N_RAILS; i++) {
            if (only != -2 && i != only) continue;
            s_cal[i] = (cec_rail_cal_t){ 1.0f, 1.0f, 0.0f };
            s_cal_pts[i].n = 0;
            cal_apply(i);
        }
        save_cal_to_nvs();
        printf("cal reset to identity (%s) + saved\n", who);
        return 0;
    }
    if ((!strcmp(argv[1], "i") || !strcmp(argv[1], "v")) && argc == 4) {
        int idx = cal_rail_index(argv[2]);
        if (idx < 0) { printf("error: unknown rail '%s' (12v|5v|3v3|5vsb)\n", argv[2]); return 1; }
        ina228_handle_t h = cal_handle(idx);
        if (h == NULL) { printf("error: %s sensor not initialized\n", CAL_RAIL_NAME[idx]); return 1; }
        float known = strtof(argv[3], NULL);

        if (!strcmp(argv[1], "v")) {
            if (known < 0.5f) { printf("error: reference V too small (%.3f)\n", known); return 1; }
            float reading = 0.0f;
            if (cal_read_voltage_avg(h, &reading) != ESP_OK || reading < 0.2f) {
                printf("error: %s bus-voltage read failed/too low (%.3f) -- rail present?\n",
                       CAL_RAIL_NAME[idx], reading);
                return 1;
            }
            float g = s_cal[idx].v_trim * (known / reading);   /* compose onto the live gain */
            if (g < 0.5f || g > 2.0f) {
                printf("error: implausible v_gain %.4f (read %.3f vs %.3f) -- check reference\n",
                       g, reading, known);
                return 1;
            }
            s_cal[idx].v_trim = g;
            cal_apply(idx);
            printf("%s v_gain = %.4f  (%.3f V -> %.3f V); `cal save` to persist\n",
                   CAL_RAIL_NAME[idx], g, reading, known);
            return 0;
        }

        /* current: capture an UNcalibrated reading against the known load */
        float raw;
        if (cal_read_current_uncal_avg(h, &raw) != ESP_OK) {
            printf("error: %s current read failed\n", CAL_RAIL_NAME[idx]);
            return 1;
        }
        if (fabsf(raw) < 0.05f || fabsf(known) < 0.05f) {
            printf("error: load too small (raw %.4f A, known %.4f A) -- apply >=~0.1 A\n", raw, known);
            return 1;
        }
        /* solve against the newest existing point (gain+offset), or gain-only for the first */
        int n = s_cal_pts[idx].n;
        float gain, off;
        if (n == 0) {
            gain = known / raw; off = 0.0f;
        } else {
            float r0 = s_cal_pts[idx].raw[n - 1], t0 = s_cal_pts[idx].tru[n - 1];
            float dr = raw - r0;
            if (fabsf(dr) < 0.05f) { gain = known / raw; off = 0.0f; }   /* too close -> gain only */
            else { gain = (known - t0) / dr; off = t0 - gain * r0; }
        }
        if (gain < 0.5f || gain > 2.0f) {
            printf("error: implausible i_gain %.4f -- check load/reference (point rejected)\n", gain);
            return 1;
        }
        /* commit: record the point (keep last two), set + apply the cal */
        if (s_cal_pts[idx].n < 2) {
            s_cal_pts[idx].raw[s_cal_pts[idx].n] = raw;
            s_cal_pts[idx].tru[s_cal_pts[idx].n] = known;
            s_cal_pts[idx].n++;
        } else {
            s_cal_pts[idx].raw[0] = s_cal_pts[idx].raw[1];
            s_cal_pts[idx].tru[0] = s_cal_pts[idx].tru[1];
            s_cal_pts[idx].raw[1] = raw;
            s_cal_pts[idx].tru[1] = known;
        }
        s_cal[idx].i_trim = gain;
        s_cal[idx].i_offset = off;
        cal_apply(idx);
        printf("%s i_gain = %.4f  i_off = %+.4f A  (pt %d: raw %.4f A -> %.4f A); `cal save` to persist\n",
               CAL_RAIL_NAME[idx], gain, off, s_cal_pts[idx].n, raw, known);
        return 0;
    }
    printf("usage: cal [show] | cal i <rail> <known_A> | cal v <rail> <known_V> | "
           "cal save | cal clear [rail|all]\n");
    return 1;
}

static const cec_cli_command_t s_cli_commands[] = {
    { "burst",  "burst now [reason text...] — fire a manual burst capture",  cli_cmd_burst  },
    { "set",    "set <layer1|layer2|layer3|swing_power|swing_current> <on|off>", cli_cmd_set },
    { "status", "status [json] — current state, EMA readings, layer enables, profile warmth", cli_cmd_status },
    { "cal",    "cal [show|i <rail> <A>|v <rail> <V>|save|clear [rail]] — per-rail INA228 cal", cli_cmd_cal },
};

static void log_hardware_info(void)
{
    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);
    ESP_LOGI(TAG, "Chip: %s rev v%d.%d, %d core(s)",
             CONFIG_IDF_TARGET,
             chip_info.revision / 100, chip_info.revision % 100,
             chip_info.cores);

    uint32_t flash_size;
    esp_flash_get_size(NULL, &flash_size);
    ESP_LOGI(TAG, "Flash: %" PRIu32 " MB", flash_size / (1024 * 1024));

    if (esp_psram_is_initialized()) {
        size_t psram_size = esp_psram_get_size();
        ESP_LOGI(TAG, "PSRAM: %u MB", psram_size / (1024 * 1024));
    } else {
        ESP_LOGW(TAG, "PSRAM: not initialized");
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "===========================================");
    ESP_LOGI(TAG, "CEC 24-pin Module Firmware (ESP-IDF port)");
    ESP_LOGI(TAG, "Version: 0.6.0-dev (INA226 bringup)");
    ESP_LOGI(TAG, "===========================================");

    /* If we just booted a CAN-OTA image it is PENDING_VERIFY -- confirm it so
     * the bootloader keeps it instead of rolling back on the next reset. */
    cec_canota_mark_valid();

    log_hardware_info();

    /* TelePlot transport: the production 24-pin board has ONLY the MCU's
     * native USB Serial/JTAG (one USB-C); there is no CH340K UART bridge
     * (that was the dev board). So we deliberately do NOT initialize the
     * dedicated UART transport here -- leaving it unconfigured routes every
     * teleplot_* line to stdio (the USB console), interleaved with the logs
     * and CLI on the one cable.
     *
     * This is independent of CONFIG_CEC_TELEMETRY_UART0 on purpose: a stale
     * sdkconfig left at =y (sdkconfig.defaults changes don't rewrite an
     * existing sdkconfig) must not silently send telemetry out the absent
     * GPIO43/44 again. The shared cec_telemetry component keeps full UART
     * support for a board that actually has the bridge; this app just
     * doesn't call it. */
    ESP_LOGI(TAG, "TelePlot on the native USB console (no CH340K UART on the production board)");

    init_i2c_bus();
    init_status_led();

    /* PRODUCTION sensing: 4x INA228 (one per rail). Replaces the proto's
     * divider/ACS712/INA226 front end -- do NOT also call init_ina226_5vsb(),
     * it grabs 0x40 and writes INA226 registers into the 12V INA228 (U10). */
    esp_err_t err = init_ina228_rails();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "INA228 rail init failed: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "Continuing; un-initialized rails read 0");
    }

    ema_init(&s_v_5vsb_ema, EMA_ALPHA_FAST);
    ema_init(&s_i_5vsb_ema, EMA_ALPHA_FAST);
    ema_init(&s_v_12v_ema,  EMA_ALPHA_FAST);
    ema_init(&s_v_5v_ema,   EMA_ALPHA_FAST);
    ema_init(&s_v_3v3_ema,  EMA_ALPHA_FAST);
    ema_init(&s_i_12v_ema,  EMA_ALPHA_FAST);
    ema_init(&s_i_5v_ema,   EMA_ALPHA_FAST);
    ema_init(&s_i_3v3_ema,  EMA_ALPHA_FAST);
    ema_init(&s_temp_ema,   EMA_ALPHA_FAST);

    init_layer1();
    init_layer2();
    init_layer3_profiles();
    init_swing_detectors();

    if (cec_nvs_init() == ESP_OK) {
        load_profiles_from_nvs();
        load_settings_from_nvs();
        load_cal_from_nvs();   /* after init_ina228_rails: applies the cal to the handles */
    } else {
        ESP_LOGW(TAG, "NVS init failed; profiles will not persist across boots");
    }

    esp_err_t cli_err = cec_cli_init(s_cli_commands,
                                     sizeof(s_cli_commands) / sizeof(s_cli_commands[0]));
    if (cli_err != ESP_OK) {
        ESP_LOGW(TAG, "cec_cli_init failed: %s — serial commands unavailable",
                 esp_err_to_name(cli_err));
    }

    /* CAN telemetry to the Hub. Normal mode (the Hub ACKs our frames); if
     * no Hub is on the bus the controller bus-offs and auto-recovers (the
     * cec_can on_state_change handler), logging until a Hub appears. */
    if (can_init(false) == ESP_OK) {
        xTaskCreatePinnedToCore(can_comms_task, "can_comms", 4096, NULL, 4, NULL, 1);
        /* CAN-OTA receiver: lets the Hub re-flash this module over CAN. It
         * drains can_receive() and writes the streamed image to the inactive
         * OTA slot; ota_active_cb pauses telemetry while an update runs. */
        if (cec_canota_receiver_start(ota_active_cb) != ESP_OK) {
            ESP_LOGW(TAG, "CAN-OTA receiver failed to start");
        }
    } else {
        ESP_LOGW(TAG, "CAN init failed — no telemetry to the Hub");
    }

    /* (ACS712 zero-cal removed; the INA228 needs no per-rail zero) */

    cec_capture_config_t cap_cfg = {
        .pre_trigger_capacity = PRE_TRIGGER_BUF_SIZE,
        .pre_sample_size      = sizeof(cec_capture_sample_t),
        .hs_row_size          = sizeof(cec_capture_hs_sample_t),
        .hs_sample_rate_hz    = HS_SAMPLE_RATE_HZ,
        .hs_duration_ms       = (HS_BURST_BUF_SIZE * 1000) / HS_SAMPLE_RATE_HZ,
        .cooldown_ms          = BURST_COOLDOWN_MS,
        .hs_dump_decimation   = 1,       /* dump every HS row, as v0.5.9 did */
        /* v0.5.9 lineage: pre-ring indices computed at dump time, so
         * pushes during the 4 s HS window are part of the dump. */
        .snapshot_pre_at_trigger = false,
        .dispatch_task_stack  = 8192,    /* legacy HS task margin */
        .write          = teleplot_write_raw,
        .render_pre     = capture_render_pre,
        .render_hs      = capture_render_hs,
        .state_token    = capture_state_token,
        .hs_source      = CEC_CAPTURE_HS_CALLBACK,
        .hs_fill        = capture_hs_fill,
    };
    err = cec_capture_init(&cap_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "cec_capture_init failed: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "Continuing without burst capture");
    }

    /* Sample at 50 Hz, emit TelePlot at 10 Hz, log an INFO summary at 1 Hz.
     * Read failures don't get spammed per-iteration; the divided cadence
     * makes them visible as gaps in TelePlot and bad values in the summary. */
    ESP_LOGI(TAG, "Entering main loop (sample=50 Hz, teleplot=10 Hz, log=1 Hz)");
    TickType_t last_wake = xTaskGetTickCount();
    uint32_t iter = 0;
    while (1) {
        float v_5vsb = 0.0f, i_5vsb = 0.0f;
        float v_12v = 0.0f, v_5v = 0.0f, v_3v3 = 0.0f;
        float i_12v = 0.0f, i_5v = 0.0f, i_3v3 = 0.0f;
        float temp_c = 0.0f;
        bool ok_5vsb = false, ok_temp = false;
        bool ok_v_12v = false, ok_v_5v = false, ok_v_3v3 = false;
        bool ok_i_12v = false, ok_i_5v = false, ok_i_3v3 = false;

        /* PRODUCTION sensing: one INA228 per rail gives bus voltage + current;
         * board temp from the 12V INA228's on-die sensor. */
        ok_v_12v = ok_i_12v = ina228_read_rail(s_ina228_12v,  &v_12v,  &i_12v);
        ok_v_5v  = ok_i_5v  = ina228_read_rail(s_ina228_5v,   &v_5v,   &i_5v);
        ok_v_3v3 = ok_i_3v3 = ina228_read_rail(s_ina228_3v3,  &v_3v3,  &i_3v3);
        ok_5vsb             = ina228_read_rail(s_ina228_5vsb, &v_5vsb, &i_5vsb);
        ok_temp  = (s_ina228_12v != NULL &&
                    ina228_read_die_temp_c(s_ina228_12v, &temp_c) == ESP_OK);

        /* PSU control/status, buffered by U4/U5 (read-only). PS_ON# is
         * active-low, so ps_on=true means the mobo is commanding the PSU on. */
        bool pwr_ok = (gpio_get_level(PWROK_BUF_GPIO) != 0);
        bool ps_on  = (gpio_get_level(PSON_BUF_GPIO)  == 0);

        /* On a failed read, fall back to the last good filtered value so a
         * single bad sample doesn't ripple into the state classifier. Before
         * the first successful read an EMA returns 0.0 (its init value). */
        float v_5vsb_ema = ok_5vsb  ? ema_update(&s_v_5vsb_ema, v_5vsb) : ema_value(&s_v_5vsb_ema);
        float i_5vsb_ema = ok_5vsb  ? ema_update(&s_i_5vsb_ema, i_5vsb) : ema_value(&s_i_5vsb_ema);
        float v_12v_ema  = ok_v_12v ? ema_update(&s_v_12v_ema,  v_12v)  : ema_value(&s_v_12v_ema);
        float v_5v_ema   = ok_v_5v  ? ema_update(&s_v_5v_ema,   v_5v)   : ema_value(&s_v_5v_ema);
        float v_3v3_ema  = ok_v_3v3 ? ema_update(&s_v_3v3_ema,  v_3v3)  : ema_value(&s_v_3v3_ema);
        float i_12v_ema  = ok_i_12v ? ema_update(&s_i_12v_ema,  i_12v)  : ema_value(&s_i_12v_ema);
        float i_5v_ema   = ok_i_5v  ? ema_update(&s_i_5v_ema,   i_5v)   : ema_value(&s_i_5v_ema);
        float i_3v3_ema  = ok_i_3v3 ? ema_update(&s_i_3v3_ema,  i_3v3)  : ema_value(&s_i_3v3_ema);
        float temp_ema   = ok_temp  ? ema_update(&s_temp_ema,   temp_c) : ema_value(&s_temp_ema);

        /* Total main-rail power, EMA-smoothed. 5VSB is standby and not
         * included by design (matches v0.5.9). */
        float p_total = (v_12v_ema * i_12v_ema)
                      + (v_5v_ema  * i_5v_ema)
                      + (v_3v3_ema * i_3v3_ema);

        /* Publish the latest readings for the CAN comms task (brief
         * critical section; the task snapshots and sends at 5 Hz). */
        portENTER_CRITICAL(&s_telem_mux);
        s_telem_pub.v[CEC_TELEM_RAIL_12V]  = v_12v_ema;  s_telem_pub.i[CEC_TELEM_RAIL_12V]  = i_12v_ema;
        s_telem_pub.v[CEC_TELEM_RAIL_5V]   = v_5v_ema;   s_telem_pub.i[CEC_TELEM_RAIL_5V]   = i_5v_ema;
        s_telem_pub.v[CEC_TELEM_RAIL_3V3]  = v_3v3_ema;  s_telem_pub.i[CEC_TELEM_RAIL_3V3]  = i_3v3_ema;
        s_telem_pub.v[CEC_TELEM_RAIL_5VSB] = v_5vsb_ema; s_telem_pub.i[CEC_TELEM_RAIL_5VSB] = i_5vsb_ema;
        s_telem_pub.temp_c   = temp_ema;
        s_telem_pub.p_total_w = p_total;
        s_telem_pub.state    = (uint8_t)s_state;
        s_telem_pub.ps_on    = ps_on;
        s_telem_pub.pwr_ok   = pwr_ok;
        s_telem_pub.shutting_down = s_shutting_down;
        portEXIT_CRITICAL(&s_telem_mux);

        /* Update 12V rate-of-change history (1 s window). The "oldest"
         * sample is whatever sits at the slot we're about to overwrite. */
        float v_12v_oldest = s_v_12v_history[s_v_12v_hist_idx];
        s_v_12v_history[s_v_12v_hist_idx] = v_12v_ema;
        s_v_12v_hist_idx = (s_v_12v_hist_idx + 1) % V_12V_RATE_HISTORY_SIZE;
        if (s_v_12v_hist_count < V_12V_RATE_HISTORY_SIZE) s_v_12v_hist_count++;
        bool rate_valid = (s_v_12v_hist_count >= V_12V_RATE_HISTORY_SIZE);
        float v_12v_rate = rate_valid ? (v_12v_ema - v_12v_oldest) : 0.0f;

        /* Shutdown detection: 12V was nominal-ish and is now falling
         * fast. Fire the burst and assert the mute. The capture path
         * has SHUTDOWN-bypasses-cooldown built in, so this always
         * captures even if a previous burst was recent. */
        if (rate_valid && !s_shutting_down
            && v_12v_ema > V_12V_SHUTDOWN_MIN_ARMED_V
            && v_12v_rate < V_12V_SHUTDOWN_RATE_THRESHOLD) {
            s_shutting_down = true;
            s_shutdown_start_us = esp_timer_get_time();
            ESP_LOGW(TAG, "SHUTDOWN DETECTED (12V dropping %.2f V/s); muting detectors for %ds",
                     v_12v_rate, (int)(SHUTDOWN_MUTE_DURATION_US / 1000000));
            esp_err_t terr = cec_capture_trigger(CEC_TRIG_SHUTDOWN);
            if (terr == ESP_OK) {
                ESP_LOGW(TAG, "burst trigger: SHUTDOWN");
            }
        }
        /* Auto-clear the mute on timeout (e.g. brown-out that recovered
         * without ever transitioning through STANDBY/OFF). The state-
         * change clear is handled in the transition block below. */
        if (s_shutting_down
            && (esp_timer_get_time() - s_shutdown_start_us) > SHUTDOWN_MUTE_DURATION_US) {
            s_shutting_down = false;
            ESP_LOGI(TAG, "shutdown mute window expired");
        }

        cec_state_t next_state = cec_state_classify(v_12v_ema, v_5vsb_ema, p_total, s_state);
        if (next_state != s_state) {
            int64_t now_us = esp_timer_get_time();
            int64_t dwell_ms = (now_us - s_state_entered_us) / 1000;
            ESP_LOGI(TAG, "state: %s -> %s (dwell=%lld ms, p_total=%.1f W)",
                     cec_state_name(s_state), cec_state_name(next_state),
                     (long long)dwell_ms, p_total);
            /* Transition UP from below IDLE: rails were 0 V or ramping,
             * the EMAs / Layer-2 variance estimators carry pre-transition
             * state, and Layer-2 counters might be mid-accumulating from
             * the ramp. Reset them so the new state starts clean. Matches
             * v0.5.9 reset_filters_on_state_up. */
            if (next_state >= CEC_STATE_IDLE && s_state < CEC_STATE_IDLE) {
                reset_emas_on_state_up();
                reset_layer2_counters();
                reset_swing_windows();
                reset_v_12v_history();
                s_z_above_last = false;
            }
            /* Landing in OFF or STANDBY means the shutdown sequence
             * resolved (PSU unplugged → OFF, switched off → STANDBY).
             * Clear the mute so detectors arm again as soon as the
             * settle window passes. */
            if (s_shutting_down
                && (next_state == CEC_STATE_OFF || next_state == CEC_STATE_STANDBY)) {
                s_shutting_down = false;
                ESP_LOGI(TAG, "shutdown mute cleared by transition to %s",
                         cec_state_name(next_state));
            }
            s_state = next_state;
            s_state_entered_us = now_us;
        }

        /* Layer 1 gating:
         *   - Main rails (12V/5V/3V3) only check in IDLE/ACTIVE/PEAK,
         *     since OFF/STANDBY has them at 0 V and the ramp passes
         *     through out-of-band values.
         *   - 5VSB checks any time the rail is supposed to be present
         *     (everything except OFF).
         *   - Both wait LAYER1_SETTLE_US after every state transition
         *     so the PSU's inrush ramp doesn't trip a false CRITICAL.
         *     Detectors are reset during the settle window so the
         *     consecutive-sample counter doesn't accumulate from the
         *     ramp.
         */
        bool l1_settled = (esp_timer_get_time() - s_state_entered_us) > LAYER1_SETTLE_US;
        bool main_rails_armed = l1_settled
            && (s_state == CEC_STATE_IDLE || s_state == CEC_STATE_ACTIVE || s_state == CEC_STATE_PEAK);
        bool sb_rail_armed = l1_settled && (s_state != CEC_STATE_OFF);
        /* "active" = state-armed AND runtime-enabled AND not in the
         * shutdown mute window. The settings flag lets the operator
         * silence a layer at runtime; the shutdown mute keeps every
         * detector quiet while the rails are collapsing so the only
         * trigger that fires during a shutdown is CEC_TRIG_SHUTDOWN. */
        bool armed = !s_shutting_down;
        bool l1_main_active = s_settings.layer1 && main_rails_armed && armed;
        bool l1_sb_active   = s_settings.layer1 && sb_rail_armed   && armed;
        bool l2_active      = s_settings.layer2 && main_rails_armed && armed;
        bool l3_active      = s_settings.layer3 && main_rails_armed && armed;
        bool sp_active      = s_settings.swing_power   && main_rails_armed && armed;
        bool sc_active      = s_settings.swing_current && main_rails_armed && armed;

        cec_severity_t sev_12v = CEC_SEV_NONE;
        cec_severity_t sev_5v  = CEC_SEV_NONE;
        cec_severity_t sev_3v3 = CEC_SEV_NONE;
        cec_severity_t sev_5vsb = CEC_SEV_NONE;
        bool any_entered_crit = false;

        if (l1_main_active) {
            layer1_step_result_t r;
            r = layer1_step("12V", &s_l1_12v, &s_last_sev_12v, v_12v_ema);
            sev_12v = r.sev; any_entered_crit |= r.entered_critical;
            r = layer1_step("5V",  &s_l1_5v,  &s_last_sev_5v,  v_5v_ema);
            sev_5v  = r.sev; any_entered_crit |= r.entered_critical;
            r = layer1_step("3V3", &s_l1_3v3, &s_last_sev_3v3, v_3v3_ema);
            sev_3v3 = r.sev; any_entered_crit |= r.entered_critical;
        } else {
            cec_layer1_reset(&s_l1_12v); s_last_sev_12v = CEC_SEV_NONE;
            cec_layer1_reset(&s_l1_5v);  s_last_sev_5v  = CEC_SEV_NONE;
            cec_layer1_reset(&s_l1_3v3); s_last_sev_3v3 = CEC_SEV_NONE;
        }
        if (l1_sb_active) {
            layer1_step_result_t r5sb = layer1_step("5VSB", &s_l1_5vsb, &s_last_sev_5vsb, v_5vsb_ema);
            sev_5vsb = r5sb.sev;
            any_entered_crit |= r5sb.entered_critical;
        } else {
            cec_layer1_reset(&s_l1_5vsb); s_last_sev_5vsb = CEC_SEV_NONE;
        }

        if (any_entered_crit) {
            esp_err_t terr = cec_capture_trigger(CEC_TRIG_STATIC_CRIT);
            if (terr == ESP_OK) {
                ESP_LOGW(TAG, "burst trigger: STATIC_CRIT");
            } else if (terr == ESP_ERR_NOT_FINISHED) {
                ESP_LOGW(TAG, "burst trigger: STATIC_CRIT skipped (capture busy)");
            } else if (terr == ESP_ERR_INVALID_STATE) {
                ESP_LOGW(TAG, "burst trigger: STATIC_CRIT skipped (cooldown)");
            }
        }

        /* Layers 2 and 3 share the rail-state gating with Layer 1's main
         * rails, then layer with their own enable flag so the operator
         * can silence either layer at runtime. */
        bool l2_fired = false;
        if (l2_active) {
            /* On a failed read the raw local stays 0.0 while the EMA
             * holds last-good — feeding that pair to Layer 2 reads as a
             * huge spurious deviation (FOLLOWUPS L1). Feed the EMA as
             * the instant on a failed read so the deviation is zero for
             * that channel this iteration. */
            l2_fired |= cec_layer2_update_adaptive(&s_l2_v_12v,  ok_v_12v ? v_12v  : v_12v_ema,  v_12v_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_v_5v,   ok_v_5v  ? v_5v   : v_5v_ema,   v_5v_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_v_3v3,  ok_v_3v3 ? v_3v3  : v_3v3_ema,  v_3v3_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_v_5vsb, ok_5vsb  ? v_5vsb : v_5vsb_ema, v_5vsb_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_i_12v,  ok_i_12v ? i_12v  : i_12v_ema,  i_12v_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_i_5v,   ok_i_5v  ? i_5v   : i_5v_ema,   i_5v_ema);
            l2_fired |= cec_layer2_update_adaptive(&s_l2_i_3v3,  ok_i_3v3 ? i_3v3  : i_3v3_ema,  i_3v3_ema);
        } else {
            reset_layer2_counters();
        }
        if (l2_fired) {
            esp_err_t terr = cec_capture_trigger(CEC_TRIG_TRANSIENT);
            if (terr == ESP_OK) {
                ESP_LOGW(TAG, "burst trigger: TRANSIENT");
            }
            /* NOT_FINISHED / cooldown skips are silent for L2/L3 — they
             * fire often enough that logging each skip would be noisy. */
        }

        /* Layer 3: update the current state's profiles, then compute
         * the max |z| across the six main rails. Single-sample trigger
         * gated on transition (z stayed below, now crossed above)
         * so a sustained anomaly doesn't spam the trigger path. */
        float z_max = 0.0f;
        if (l3_active) {
            cec_rail_profile_t *prof = s_profiles[s_state];
            cec_rail_profile_update(&prof[PROF_V_12V],  v_12v_ema,  PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_V_5V],   v_5v_ema,   PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_V_3V3],  v_3v3_ema,  PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_V_5VSB], v_5vsb_ema, PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_I_12V],  i_12v_ema,  PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_I_5V],   i_5v_ema,   PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_I_3V3],  i_3v3_ema,  PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_I_5VSB], i_5vsb_ema, PROFILE_ADAPT_RATE);
            cec_rail_profile_update(&prof[PROF_TEMP],   temp_ema,   PROFILE_ADAPT_RATE);
            s_profiles_dirty = true;

            if (cec_rail_profile_is_warm(&prof[PROF_V_12V])) {
                float z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_V_12V], v_12v_ema)); if (z > z_max) z_max = z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_V_5V],  v_5v_ema));  if (z > z_max) z_max = z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_V_3V3], v_3v3_ema)); if (z > z_max) z_max = z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_I_12V], i_12v_ema)); if (z > z_max) z_max = z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_I_5V],  i_5v_ema));  if (z > z_max) z_max = z;
                z = fabsf(cec_rail_profile_z_score(&prof[PROF_I_3V3], i_3v3_ema)); if (z > z_max) z_max = z;
            }
        }
        bool z_above = (z_max > LAYER3_Z_THRESHOLD);
        if (z_above && !s_z_above_last) {
            esp_err_t terr = cec_capture_trigger(CEC_TRIG_ANOMALY);
            if (terr == ESP_OK) {
                ESP_LOGW(TAG, "burst trigger: ANOMALY (z_max=%.2f)", z_max);
            }
        }
        s_z_above_last = z_above;

        /* Power swing: adaptive threshold against the 5-second window
         * mean. Reset baseline on fire so the post-event behavior gets
         * its own debounce window. */
        float p_window_mean = cec_swing_detector_mean(&s_power_swing);
        float p_swing_thresh = fmaxf(POWER_SWING_MIN_THRESHOLD_W,
                                     POWER_SWING_FRACTION * p_window_mean);
        if (sp_active) {
            if (cec_swing_detector_update(&s_power_swing, p_total, p_swing_thresh)) {
                ESP_LOGW(TAG, "POWER SWING: now=%.1f W, mean=%.1f W, swing=%+.1f W, thr=%.1f W",
                         p_total, p_window_mean, p_total - p_window_mean, p_swing_thresh);
                esp_err_t terr = cec_capture_trigger(CEC_TRIG_POWER_SWING);
                if (terr == ESP_OK) {
                    ESP_LOGW(TAG, "burst trigger: POWER_SWING");
                }
                cec_swing_detector_reset_to(&s_power_swing, p_total);
            }
        } else {
            cec_swing_detector_reset_empty(&s_power_swing);
        }

        /* Per-rail current swing. Fire on the first rail to trip, with
         * 12V > 5V > 3V3 priority so the log message identifies one
         * specific cause. Re-baseline all three windows on fire. */
        if (sc_active) {
            bool f12 = cec_swing_detector_update(&s_i_swing_12v, i_12v_ema, CURRENT_SWING_THRESH_I_12V);
            bool f5  = cec_swing_detector_update(&s_i_swing_5v,  i_5v_ema,  CURRENT_SWING_THRESH_I_5V);
            bool f3v3 = cec_swing_detector_update(&s_i_swing_3v3, i_3v3_ema, CURRENT_SWING_THRESH_I_3V3);
            const char *fired_rail = NULL;
            float fired_val = 0.0f, fired_mean = 0.0f;
            if (f12)       { fired_rail = "12V"; fired_val = i_12v_ema; fired_mean = cec_swing_detector_mean(&s_i_swing_12v); }
            else if (f5)   { fired_rail = "5V";  fired_val = i_5v_ema;  fired_mean = cec_swing_detector_mean(&s_i_swing_5v);  }
            else if (f3v3) { fired_rail = "3V3"; fired_val = i_3v3_ema; fired_mean = cec_swing_detector_mean(&s_i_swing_3v3); }
            if (fired_rail != NULL) {
                ESP_LOGW(TAG, "CURRENT SWING on %s: now=%.3f A, mean=%.3f A, swing=%+.3f A",
                         fired_rail, fired_val, fired_mean, fired_val - fired_mean);
                esp_err_t terr = cec_capture_trigger(CEC_TRIG_CURRENT_SWING);
                if (terr == ESP_OK) {
                    ESP_LOGW(TAG, "burst trigger: CURRENT_SWING");
                }
                cec_swing_detector_reset_to(&s_i_swing_12v, i_12v_ema);
                cec_swing_detector_reset_to(&s_i_swing_5v,  i_5v_ema);
                cec_swing_detector_reset_to(&s_i_swing_3v3, i_3v3_ema);
            }
        } else {
            cec_swing_detector_reset_empty(&s_i_swing_12v);
            cec_swing_detector_reset_empty(&s_i_swing_5v);
            cec_swing_detector_reset_empty(&s_i_swing_3v3);
        }

        /* Periodic NVS save. Only run if profiles got dirty since the
         * last save, and only every NVS_SAVE_INTERVAL_US to limit flash
         * wear. The 50 Hz loop calls this every iteration; the time
         * check is the gate. */
        if (s_profiles_dirty
            && (esp_timer_get_time() - s_last_nvs_save_us) > NVS_SAVE_INTERVAL_US) {
            esp_err_t err = cec_nvs_save_blob(NVS_PROFILES_KEY, NVS_PROFILES_MAGIC,
                                              s_profiles, sizeof(s_profiles));
            if (err == ESP_OK) {
                s_profiles_dirty = false;
                s_last_nvs_save_us = esp_timer_get_time();
                ESP_LOGI(TAG, "NVS: saved profiles (%u bytes)",
                         (unsigned)sizeof(s_profiles));
            } else {
                ESP_LOGW(TAG, "NVS: save failed: %s", esp_err_to_name(err));
                /* Back off until the next interval so we don't spam on
                 * persistent errors. */
                s_last_nvs_save_us = esp_timer_get_time();
            }
        }

        /* Push a pre-trigger sample every iteration so the ring buffer
         * always holds the last ~20 s of filtered telemetry. */
        cec_capture_sample_t pre = {
            .ts_ms  = (uint32_t)(esp_timer_get_time() / 1000),
            .state  = (uint8_t)s_state,
            .v_12v  = v_12v_ema,  .i_12v  = i_12v_ema,
            .v_5v   = v_5v_ema,   .i_5v   = i_5v_ema,
            .v_3v3  = v_3v3_ema,  .i_3v3  = i_3v3_ema,
            .v_5vsb = v_5vsb_ema, .i_5vsb = i_5vsb_ema,
            .temp_c = temp_ema,
            .ps_on  = ps_on ? 1 : 0, .pwr_ok = pwr_ok ? 1 : 0,
        };
        s_last_capture_state = pre.state;
        cec_capture_push(&pre);

        if (iter % TELEPLOT_DIVIDER == 0) {
            /* Live monitor rows are emitted UNTIMESTAMPED so TelePlot
             * auto-stamps each with the host wallclock and they land in
             * the live window. (An explicit device-uptime-ms timestamp
             * is read by TelePlot as Unix-epoch ms -> the points plot
             * decades in the past, off-screen, which looked like "no
             * graphs".) The burst renderers below KEEP device-ms: those
             * blocks are saved + aligned offline by cec_capture_analyze,
             * not viewed in the live TelePlot window. */
            if (ok_5vsb) {
                teleplot_emit("v_5vsb",     v_5vsb);
                teleplot_emit("v_5vsb_ema", v_5vsb_ema);
                teleplot_emit("i_5vsb_raw", i_5vsb);
                teleplot_emit("i_5vsb_ema", i_5vsb_ema);
            }
            if (ok_v_12v) { teleplot_emit("v_12v", v_12v); teleplot_emit("v_12v_ema", v_12v_ema); }
            if (ok_v_5v)  { teleplot_emit("v_5v",  v_5v);  teleplot_emit("v_5v_ema",  v_5v_ema);  }
            if (ok_v_3v3) { teleplot_emit("v_3v3", v_3v3); teleplot_emit("v_3v3_ema", v_3v3_ema); }
            if (ok_i_12v) { teleplot_emit("i_12v", i_12v); teleplot_emit("i_12v_ema", i_12v_ema); }
            if (ok_i_5v)  { teleplot_emit("i_5v",  i_5v);  teleplot_emit("i_5v_ema",  i_5v_ema);  }
            if (ok_i_3v3) { teleplot_emit("i_3v3", i_3v3); teleplot_emit("i_3v3_ema", i_3v3_ema); }
            if (ok_temp)  { teleplot_emit("temp_c", temp_c); teleplot_emit("temp_c_ema", temp_ema); }
            teleplot_emit("p_total", p_total);
            teleplot_emit("state",   (float)s_state);
            teleplot_emit("sev_12v",  (float)sev_12v);
            teleplot_emit("sev_5v",   (float)sev_5v);
            teleplot_emit("sev_3v3",  (float)sev_3v3);
            teleplot_emit("sev_5vsb", (float)sev_5vsb);
            teleplot_emit("z_max",    z_max);
            teleplot_emit("shutting_down", s_shutting_down ? 1.0f : 0.0f);
            teleplot_emit("ps_on",  ps_on  ? 1.0f : 0.0f);
            teleplot_emit("pwr_ok", pwr_ok ? 1.0f : 0.0f);
            if (cec_swing_detector_is_full(&s_power_swing)) {
                teleplot_emit("p_window_mean", p_window_mean);
                teleplot_emit("p_swing_thr",   p_swing_thresh);
            }
        }

        if (iter % LOG_DIVIDER == 0) {
            ESP_LOGI(TAG, "[%s] V: 12=%.3f 5=%.3f 3V3=%.3f 5SB=%.3f | "
                          "I: 12=%.2f 5=%.2f 3V3=%.2f 5SB=%.4f | "
                          "P=%.1fW T=%.1fC | PS_ON=%d PWR_OK=%d",
                     cec_state_name(s_state),
                     v_12v_ema, v_5v_ema, v_3v3_ema, v_5vsb_ema,
                     i_12v_ema, i_5v_ema, i_3v3_ema, i_5vsb_ema,
                     p_total, temp_ema, ps_on, pwr_ok);
        }

        /* Status LED: solid ON when ATX power is good (system running),
         * ~1 Hz heartbeat otherwise (standby/off, firmware alive). */
        gpio_set_level(STATUS_LED_GPIO, pwr_ok ? 1 : ((iter / 25) & 1));

        iter++;
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}
