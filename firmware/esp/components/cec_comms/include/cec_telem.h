#pragma once

/*
 * CEC rail-telemetry CAN frame layout — the ONE source of truth shared by
 * the transmitter (a 4-rail module like the 24-pin ATX) and the Hub
 * receiver. Keeping pack + unpack in one place stops the two ends from
 * silently disagreeing on byte order.
 *
 * The module's telemetry is sent as a 3-frame burst on classical CAN
 * (8 data bytes/frame), all little-endian:
 *
 *   RAILS_V (0x200): u16 mV  [12V][5V][3V3][5VSB]
 *   RAILS_I (0x201): i16 mA  [12V][5V][3V3][5VSB]
 *   STATUS  (0x202): [module_type u8][state u8][flags u8][temp i8 degC]
 *                    [p_total u16 deciwatts LE][seq u8][reserved u8]
 *
 * flags bits: bit0 = PS_ON (mobo commanding PSU on), bit1 = PWR_OK,
 *             bit2 = shutting_down.
 *
 * This is distinct from the EPS per-cable can_send_telemetry() frame.
 */

#include <stdint.h>
#include <stdbool.h>
#include "cec_can.h"   /* CAN_ID_TELEMETRY_BASE */

#ifdef __cplusplus
extern "C" {
#endif

/* Rail index order used across the 3 frames. */
enum { CEC_TELEM_RAIL_12V = 0, CEC_TELEM_RAIL_5V, CEC_TELEM_RAIL_3V3,
       CEC_TELEM_RAIL_5VSB, CEC_TELEM_NUM_RAILS };

#define CEC_TELEM_ID_RAILS_V   (CAN_ID_TELEMETRY_BASE + 0x00)   /* 0x200 */
#define CEC_TELEM_ID_RAILS_I   (CAN_ID_TELEMETRY_BASE + 0x01)   /* 0x201 */
#define CEC_TELEM_ID_STATUS    (CAN_ID_TELEMETRY_BASE + 0x02)   /* 0x202 */

#define CEC_TELEM_FLAG_PS_ON          (1u << 0)
#define CEC_TELEM_FLAG_PWR_OK         (1u << 1)
#define CEC_TELEM_FLAG_SHUTTING_DOWN  (1u << 2)

/* Decoded telemetry. The TX side fills it from its readings and packs;
 * the RX side starts zeroed and each unpack updates the matching fields. */
typedef struct {
    float   v[CEC_TELEM_NUM_RAILS];   /* volts */
    float   i[CEC_TELEM_NUM_RAILS];   /* amps */
    float   temp_c;
    float   p_total_w;
    uint8_t module_type;
    uint8_t state;
    bool    ps_on, pwr_ok, shutting_down;
    uint8_t seq;
} cec_telem_t;

/*
 * Pack subframe `sub` (0=RAILS_V, 1=RAILS_I, 2=STATUS) of `t` into the
 * 8-byte `out`. Returns the CAN ID to send it on, or 0 if `sub` is out
 * of range. Pair with can_send_frame():
 *     uint8_t d[8]; uint32_t id = cec_telem_pack(&t, sub, d);
 *     can_send_frame(id, d, 8);
 */
uint32_t cec_telem_pack(const cec_telem_t *t, uint8_t sub, uint8_t out[8]);

/*
 * Decode a received frame into `t`, updating only the fields that frame
 * carries. Returns true if `id` was one of the three telemetry IDs (and
 * `t` was updated), false otherwise (so the caller can ignore non-telemetry
 * traffic). `len` is the received DLC; short frames are tolerated.
 */
bool cec_telem_unpack(uint32_t id, const uint8_t *data, uint8_t len, cec_telem_t *t);

#ifdef __cplusplus
}
#endif
