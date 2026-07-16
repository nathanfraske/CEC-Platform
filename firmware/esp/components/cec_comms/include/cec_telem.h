#pragma once

/*
 * CEC rail-telemetry CAN frame layout — the ONE source of truth shared by the
 * transmitters (the 4-rail 24-pin ATX, the EPS, any module) and the Hub
 * aggregator. Keeping pack + unpack in one place stops the two ends from
 * silently disagreeing on byte order.
 *
 * MODULE-SCOPED IDs (so a Hub can aggregate up to CEC_MAX_MODULES modules on
 * one bus without collision): each module instance owns a block of
 * CEC_TELEM_STRIDE IDs, and sends a 3-frame burst within its block, all
 * little-endian:
 *
 *   id = CAN_ID_TELEMETRY_BASE + instance*CEC_TELEM_STRIDE + sub
 *     sub 0 RAILS_V : u16 mV  per channel [0..3]
 *     sub 1 RAILS_I : i16 mA  per channel [0..3]
 *     sub 2 STATUS  : [module_type u8][state u8][flags u8][temp i8 degC]
 *                     [p_total u16 deciwatts LE][seq u8][reserved u8]
 *
 * So instance 0 = 0x200..0x202, instance 1 = 0x210..0x212, etc. The Hub
 * demuxes by instance (cec_telem_id_instance) and decodes by sub.
 *
 * CHANNELS are module-type-defined: for the 24-pin (ATX24) the four channels
 * are 12V/5V/3V3/5VSB; for the EPS they are the two cable currents; others map
 * onto ch0..3. cec_telem_chan_label() gives the per-type label.
 *
 * The STATUS `flags` byte is module-type-defined too: ATX24 uses the
 * CEC_TELEM_FLAG_* bits (PS_ON/PWR_OK/SHUTTING_DOWN); the EPS carries its
 * CEC_FLAG_* bits (overcurrent/swing/fault/dropout). The Hub keeps the raw
 * byte and decodes it per module_type.
 */

#include <stdint.h>
#include <stdbool.h>
#include "cec_can.h"   /* CAN_ID_TELEMETRY_BASE */

#ifdef __cplusplus
extern "C" {
#endif

/* Channel index order within a burst (4 channels = 8 bytes of u16/i16). */
enum { CEC_TELEM_RAIL_12V = 0, CEC_TELEM_RAIL_5V, CEC_TELEM_RAIL_3V3,
       CEC_TELEM_RAIL_5VSB, CEC_TELEM_NUM_RAILS };

/* Per-module ID block. Instances 0..CEC_MAX_MODULES-1 (the Hub's ports). */
#define CEC_TELEM_STRIDE        0x10
#define CEC_MAX_MODULES         4

/* Subframe selectors. */
#define CEC_TELEM_SUB_RAILS_V   0
#define CEC_TELEM_SUB_RAILS_I   1
#define CEC_TELEM_SUB_STATUS    2
#define CEC_TELEM_NUM_SUB       3

#define CEC_TELEM_ID(inst, sub) \
    (CAN_ID_TELEMETRY_BASE + (uint32_t)(inst) * CEC_TELEM_STRIDE + (uint32_t)(sub))

/* Instance-0 convenience aliases (back-compat). */
#define CEC_TELEM_ID_RAILS_V    CEC_TELEM_ID(0, CEC_TELEM_SUB_RAILS_V)   /* 0x200 */
#define CEC_TELEM_ID_RAILS_I    CEC_TELEM_ID(0, CEC_TELEM_SUB_RAILS_I)   /* 0x201 */
#define CEC_TELEM_ID_STATUS     CEC_TELEM_ID(0, CEC_TELEM_SUB_STATUS)    /* 0x202 */

/* ATX24 status-byte bits (module_type-defined; EPS reuses the byte for its
 * own CEC_FLAG_* bits). */
#define CEC_TELEM_FLAG_PS_ON          (1u << 0)
#define CEC_TELEM_FLAG_PWR_OK         (1u << 1)
#define CEC_TELEM_FLAG_SHUTTING_DOWN  (1u << 2)

/* Decoded telemetry for one module. The TX side fills it from its readings,
 * sets `instance`, and packs; the RX side keeps one per port and each unpack
 * updates the matching fields. */
typedef struct {
    float   v[CEC_TELEM_NUM_RAILS];   /* per-channel volts (module-type-defined) */
    float   i[CEC_TELEM_NUM_RAILS];   /* per-channel amps */
    float   temp_c;
    float   p_total_w;
    uint8_t instance;                 /* port / module id (0..CEC_MAX_MODULES-1) */
    uint8_t module_type;
    uint8_t state;
    uint8_t flags;                    /* module-type-defined status bits */
    uint8_t seq;
} cec_telem_t;

/* ATX24 flag accessors (only meaningful when module_type == ATX24). */
#define cec_telem_ps_on(t)         (((t)->flags & CEC_TELEM_FLAG_PS_ON) != 0)
#define cec_telem_pwr_ok(t)        (((t)->flags & CEC_TELEM_FLAG_PWR_OK) != 0)
#define cec_telem_shutting_down(t) (((t)->flags & CEC_TELEM_FLAG_SHUTTING_DOWN) != 0)

/*
 * Pack subframe `sub` (0=RAILS_V, 1=RAILS_I, 2=STATUS) of `t` into the 8-byte
 * `out`. Returns the CAN ID to send it on (within t->instance's block), or 0
 * if `sub` is out of range. Pair with can_send_frame():
 *     uint8_t d[8]; uint32_t id = cec_telem_pack(&t, sub, d);
 *     can_send_frame(id, d, 8);
 */
uint32_t cec_telem_pack(const cec_telem_t *t, uint8_t sub, uint8_t out[8]);

/*
 * Decode a received frame into `t`, updating only the fields that frame
 * carries (and t->instance from the ID). Returns true if `id` is a telemetry
 * frame (and `t` was updated), false otherwise. `len` is the received DLC.
 */
bool cec_telem_unpack(uint32_t id, const uint8_t *data, uint8_t len, cec_telem_t *t);

/* ID helpers for the Hub demux. */
bool    cec_telem_id_is(uint32_t id);        /* is this a telemetry frame? */
uint8_t cec_telem_id_instance(uint32_t id);  /* port/module id from the ID */
uint8_t cec_telem_id_sub(uint32_t id);       /* subframe (0/1/2) from the ID */

/* Human labels. chan_label is the per-(type,channel) name ("12v"/"cbl0"/"ch2"). */
const char *cec_telem_type_name(uint8_t module_type);
const char *cec_telem_chan_label(uint8_t module_type, int chan);

#ifdef __cplusplus
}
#endif
