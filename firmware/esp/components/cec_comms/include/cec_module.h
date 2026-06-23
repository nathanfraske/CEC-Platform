/*
 * cec_module — the standard module->Hub runtime.
 *
 * One call from a module's app_main wires up everything a Standard-tier module
 * needs to (a) aggregate cleanly to the Hub and (b) be re-flashable over CAN:
 *
 *   - confirms a freshly CAN-flashed image (rollback safety),
 *   - opens CAN in normal mode (the Hub ACKs),
 *   - starts the CAN-OTA receiver, so the Hub can re-flash this board over CAN
 *     (after the one-time initial USB flash),
 *   - starts the poke-and-ack DETECT responder (or inert if no tap),
 *   - runs a telemetry task that calls the board's read() each period and
 *     sends the module-scoped cec_telem burst (paused while an OTA is running).
 *
 * The ONLY per-board code a bring-up needs to add is the read() callback that
 * fills the cec_telem_t from that board's sensors. Everything else is shared.
 */

#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "cec_telem.h"
#include "cec_freeze.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Fill `t`'s channels + temp_c + p_total_w + flags + state from the board's
 * sensors. instance/module_type/seq are set by the runtime — don't touch them.
 * Called from the telemetry task at cfg.period_ms. */
typedef void (*cec_module_read_fn)(cec_telem_t *t, void *ctx);

typedef struct {
    uint8_t  module_type;        /* CEC_MODULE_TYPE_* */
    uint8_t  module_id;          /* Hub port / instance (0..CEC_MAX_MODULES-1) */
    int      detect_tap_gpio;    /* poke-ack high-Z tap GPIO, or CEC_POKEACK_TAP_NONE */
    uint32_t period_ms;          /* telemetry cadence (e.g. 200 = 5 Hz) */
    cec_module_read_fn read;     /* per-board sensor read (required) */
    void    *ctx;                /* passed to read() and the freeze callbacks */
    /* Cross-module FREEZE co-capture (§6.10). on_freeze is called when another
     * node broadcasts FREEZE -- freeze/dump this board's ring here (NULL =
     * participate with a log only, e.g. a scaffold with no buffer yet). */
    cec_freeze_on_freeze_fn on_freeze;
    cec_freeze_on_rearm_fn  on_rearm;
} cec_module_cfg_t;

/* Start the runtime. Returns ESP_OK once CAN + OTA + responder + telemetry are
 * up. Logs and continues if CAN can't open (no telemetry, but the app lives). */
esp_err_t cec_module_start(const cec_module_cfg_t *cfg);

#ifdef __cplusplus
}
#endif
