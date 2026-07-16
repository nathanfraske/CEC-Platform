/*
 * cec_freeze — cross-module synchronized capture (spec §6.10, v2.1).
 *
 * Any one module's local trip freezes EVERY module's capture ring on a common
 * timeline, so a single rail's event captures the whole system. Mechanism, all
 * tiers, over CAN, no spare-pin hardware:
 *
 *   1. The tripping node freezes its own ring, then broadcasts one
 *      high-priority FREEZE frame (CEC_FREEZE_ID, lowest id = wins arbitration).
 *   2. Every other node sees it in its CAN RX ISR and timestamps the instant
 *      THERE (the alignment point), then freezes its ring in a task.
 *   3. The host reads each frozen window out (here: each module's existing
 *      burst dump over its own USB) and overlays them on the FREEZE instant.
 *   4. A broadcast RE-ARM frame re-arms everyone after read-out.
 *
 * Alignment rides CAN being a simultaneous broadcast medium: every node detects
 * end-of-frame within ~1 bit time (a µs or two at 500k), far inside one 1 ms
 * sample. The task-level freeze latency (a few hundred µs, ~ms worst) is
 * absorbed by the modules' 2 s pre-roll, so it doesn't affect alignment.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Broadcast frame IDs. Far below telemetry (0x200) / anomaly (0x100) so FREEZE
 * wins CAN arbitration and lands first. */
#define CEC_FREEZE_ID   0x010   /* payload: [0]=origin_inst [1]=cause [2]=seq */
#define CEC_REARM_ID    0x011   /* payload: [0]=origin_inst [1]=seq */

enum {
    CEC_FREEZE_CAUSE_MANUAL = 0,   /* host/CLI-initiated (a test freeze) */
    CEC_FREEZE_CAUSE_ANOMALY,
    CEC_FREEZE_CAUSE_TRANSIENT,
    CEC_FREEZE_CAUSE_OVERCURRENT,
    CEC_FREEZE_CAUSE_SHUTDOWN,
    CEC_FREEZE_CAUSE_OTHER,
};
const char *cec_freeze_cause_name(uint8_t cause);

/* Called (TASK context) when this node must freeze its ring because a REMOTE
 * node broadcast FREEZE. instant_us is the ISR-captured arrival time. Freeze /
 * dump your capture buffer here (e.g. cec_capture_trigger). */
typedef void (*cec_freeze_on_freeze_fn)(uint8_t origin_inst, uint8_t cause,
                                        int64_t instant_us, void *ctx);
/* Called (TASK context) on RE-ARM. Re-arm your capture here. */
typedef void (*cec_freeze_on_rearm_fn)(void *ctx);

typedef struct {
    uint8_t                 self_instance;   /* this node's id (origin marking) */
    cec_freeze_on_freeze_fn on_freeze;       /* NULL = freeze state only (no buffer) */
    cec_freeze_on_rearm_fn  on_rearm;        /* NULL ok */
    void                   *ctx;
} cec_freeze_cfg_t;

/* Install FREEZE/RE-ARM handling: an ISR hook (cec_can) timestamps a broadcast
 * the instant it lands; a task invokes the callbacks. Call after can_init. */
esp_err_t cec_freeze_init(const cec_freeze_cfg_t *cfg);

/* This node tripped: broadcast FREEZE so every other node freezes. The caller
 * has already frozen its OWN ring, so on_freeze is NOT invoked locally. */
esp_err_t cec_freeze_trigger(uint8_t cause);

/* Broadcast RE-ARM (every node, and this one, re-arms). */
esp_err_t cec_freeze_rearm(void);

bool    cec_freeze_is_frozen(void);
uint8_t cec_freeze_origin(void);
uint8_t cec_freeze_cause(void);
int64_t cec_freeze_instant_us(void);

#ifdef __cplusplus
}
#endif
