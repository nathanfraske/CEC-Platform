#include "cec_pokeack.h"
#include "cec_can.h"

#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_check.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

static const char *TAG = "pokeack";

const char *cec_detect_class_name(cec_detect_class_t c)
{
    switch (c) {
    case CEC_DETECT_FAULT:        return "FAULT(short)";
    case CEC_DETECT_CAN_ONLY:     return "CAN-only(2.2k)";
    case CEC_DETECT_CAN_RS485:    return "CAN+RS485(4.7k)";
    case CEC_DETECT_CAN_100BT1:   return "CAN+100BT1(10k)";
    case CEC_DETECT_RESERVED_22K: return "reserved(22k)";
    case CEC_DETECT_RESERVED_47K: return "reserved(47k)";
    case CEC_DETECT_ABSENT:       return "absent(open)";
    default:                      return "?";
    }
}

/* Bin measured millivolts to a class. Windows are the midpoints between the
 * nominal code voltages (10k pull-up / 3.3V): short .60 1.06 1.65 2.27 2.72 open. */
static cec_detect_class_t classify_mv(int mv)
{
    if (mv < 300)  return CEC_DETECT_FAULT;
    if (mv < 820)  return CEC_DETECT_CAN_ONLY;
    if (mv < 1350) return CEC_DETECT_CAN_RS485;
    if (mv < 1950) return CEC_DETECT_CAN_100BT1;
    if (mv < 2500) return CEC_DETECT_RESERVED_22K;
    if (mv < 2950) return CEC_DETECT_RESERVED_47K;
    return CEC_DETECT_ABSENT;
}

/* =================== module (responder) side =================== */

struct responder_ctx {
    int     tap_gpio;
    uint8_t module_type;
    uint8_t instance;
};

static void responder_task(void *arg)
{
    struct responder_ctx *c = (struct responder_ctx *)arg;
    ESP_LOGI(TAG, "responder watching DETECT tap on IO%d (type 0x%02x, inst %u)",
             c->tap_gpio, c->module_type, c->instance);

    int prev = gpio_get_level(c->tap_gpio);
    bool counting = false;
    int  edges = 0;
    int64_t window_start = 0;
    int64_t cooldown_until = 0;

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1));
        int64_t now = esp_timer_get_time();
        if (now < cooldown_until) { prev = gpio_get_level(c->tap_gpio); continue; }

        int lvl = gpio_get_level(c->tap_gpio);
        bool rising = (prev == 0 && lvl == 1);
        prev = lvl;

        if (rising) {
            if (!counting) { counting = true; edges = 1; window_start = now; }
            else edges++;
        }
        if (counting && (now - window_start) >= (int64_t)CEC_POKEACK_WINDOW_MS * 1000) {
            if (edges >= CEC_POKEACK_MIN_EDGES) {
                uint8_t d[8] = { c->module_type, c->instance, (uint8_t)edges, 0, 0, 0, 0, 0 };
                can_send_frame(CEC_POKEACK_ID_MOVED, d, sizeof(d));
                ESP_LOGI(TAG, "poke detected (%d edges) -> MOVED ack sent", edges);
                cooldown_until = now + 1000 * 1000;   /* 1 s, ignore the rest of this poke */
            }
            counting = false; edges = 0;
        }
    }
}

esp_err_t cec_pokeack_responder_start(int tap_gpio, uint8_t module_type, uint8_t instance)
{
    if (tap_gpio < 0) {
        /* No pin-8 sense tap on this board -> safe fallback / legacy mode. The
         * Hub will still read comm class from the static divider; it just
         * won't get a poke ack, and treats this port as known-but-unbound. */
        ESP_LOGW(TAG, "no DETECT sense tap (type 0x%02x) -> poke-and-ack disabled "
                      "(legacy/unbound; Hub reads comm-class from the divider)",
                 module_type);
        return ESP_OK;
    }

    gpio_config_t io = {
        .pin_bit_mask = 1ULL << tap_gpio,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,   /* high-Z tap: don't load the line */
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    esp_err_t e = gpio_config(&io);
    if (e != ESP_OK) return e;

    struct responder_ctx *c = malloc(sizeof(*c));
    if (!c) return ESP_ERR_NO_MEM;
    c->tap_gpio = tap_gpio; c->module_type = module_type; c->instance = instance;

    if (xTaskCreatePinnedToCore(responder_task, "pokeack_rx", 3072, c, 5, NULL, 0) != pdPASS) {
        free(c);
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

/* =================== Hub side =================== */

/* Each port is ONE pin: ADC input to read the divider, momentary push-pull
 * output to poke. Mode-switched per poke; the ADC channel config is restored
 * afterward so the next read is clean. */
typedef struct {
    int               gpio;
    adc_channel_t     chan;
    adc_cali_handle_t cali;
    bool              valid;
} pokeack_port_t;

static adc_oneshot_unit_handle_t s_adc = NULL;
static pokeack_port_t            s_port[CEC_POKEACK_MAX_PORTS];
static int                       s_n_ports = 0;

static const adc_oneshot_chan_cfg_t s_chan_cfg = {
    .bitwidth = ADC_BITWIDTH_DEFAULT, .atten = ADC_ATTEN_DB_12,
};

esp_err_t cec_pokeack_hub_init_ports(const int *port_gpios, int n_ports)
{
    if (!port_gpios || n_ports <= 0) return ESP_ERR_INVALID_ARG;
    if (n_ports > CEC_POKEACK_MAX_PORTS) n_ports = CEC_POKEACK_MAX_PORTS;

    adc_oneshot_unit_init_cfg_t ucfg = { .unit_id = ADC_UNIT_1 };
    ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&ucfg, &s_adc), TAG, "adc_oneshot_new_unit");

    s_n_ports = 0;
    for (int p = 0; p < n_ports; p++) {
        int g = port_gpios[p];
        if (g < 1 || g > 10) {     /* ESP32-S3 ADC1 = IO1..IO10 = CH0..CH9 */
            ESP_LOGE(TAG, "port %d: IO%d is not an ADC1 pin (IO1..IO10) -- skipped", p, g);
            s_port[p].valid = false;
            continue;
        }
        s_port[p].gpio  = g;
        s_port[p].chan  = (adc_channel_t)(g - 1);
        s_port[p].valid = true;
        if (adc_oneshot_config_channel(s_adc, s_port[p].chan, &s_chan_cfg) != ESP_OK) {
            ESP_LOGE(TAG, "port %d IO%d: config_channel failed", p, g);
            s_port[p].valid = false;
            continue;
        }
        adc_cali_curve_fitting_config_t cal = {
            .unit_id = ADC_UNIT_1, .chan = s_port[p].chan,
            .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT,
        };
        if (adc_cali_create_scheme_curve_fitting(&cal, &s_port[p].cali) != ESP_OK)
            s_port[p].cali = NULL;     /* mV approximate */
        s_n_ports = p + 1;
        ESP_LOGI(TAG, "port %d: DETECT on IO%d (ADC1_CH%d, read+poke; external 10k pull-up)",
                 p, g, (int)s_port[p].chan);
    }
    return s_n_ports > 0 ? ESP_OK : ESP_FAIL;
}

int cec_pokeack_num_ports(void) { return s_n_ports; }

cec_detect_class_t cec_pokeack_read_class_port(int port, int *out_mv)
{
    if (out_mv) *out_mv = -1;
    if (!s_adc || port < 0 || port >= s_n_ports || !s_port[port].valid) return CEC_DETECT_ABSENT;

    int acc = 0, n = 0;
    for (int i = 0; i < 8; i++) {
        int raw = 0;
        if (adc_oneshot_read(s_adc, s_port[port].chan, &raw) == ESP_OK) { acc += raw; n++; }
    }
    int raw = n ? acc / n : 0;
    int mv = 0;
    if (s_port[port].cali) adc_cali_raw_to_voltage(s_port[port].cali, raw, &mv);
    else                   mv = raw * 3300 / 4095;
    if (out_mv) *out_mv = mv;
    return classify_mv(mv);
}

bool cec_pokeack_poke_and_bind_port(int port, uint32_t timeout_ms,
                                    uint8_t *module_type, uint8_t *instance)
{
    if (port < 0 || port >= s_n_ports || !s_port[port].valid) return false;
    int g = s_port[port].gpio;

    /* Poke: drive PULSES clean rising edges on this port's pin, then return it
     * to hi-Z input and restore the ADC channel config so the next read works. */
    gpio_set_direction(g, GPIO_MODE_OUTPUT);
    for (int i = 0; i < CEC_POKEACK_PULSES; i++) {
        gpio_set_level(g, 1); vTaskDelay(pdMS_TO_TICKS(CEC_POKEACK_PULSE_MS));
        gpio_set_level(g, 0); vTaskDelay(pdMS_TO_TICKS(CEC_POKEACK_PULSE_MS));
    }
    gpio_set_direction(g, GPIO_MODE_INPUT);
    adc_oneshot_config_channel(s_adc, s_port[port].chan, &s_chan_cfg);   /* re-arm ADC pad */

    /* Wait for a MOVED ack (caller owns can_receive). One port at a time, so
     * any MOVED in this window is from the module on `port`. */
    TickType_t start = xTaskGetTickCount();
    while ((xTaskGetTickCount() - start) < pdMS_TO_TICKS(timeout_ms)) {
        uint32_t id = 0; uint8_t len = 0, d[8];
        uint32_t left = timeout_ms - (xTaskGetTickCount() - start) * portTICK_PERIOD_MS;
        if (can_receive(&id, d, &len, left ? left : 1) != ESP_OK) break;
        if (id == CEC_POKEACK_ID_MOVED) {
            if (module_type) *module_type = d[0];
            if (instance)    *instance    = d[1];
            return true;
        }
    }
    return false;   /* no ack -> safe fallback (legacy/unbound) */
}
