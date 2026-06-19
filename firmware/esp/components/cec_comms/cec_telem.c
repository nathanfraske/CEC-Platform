#include "cec_telem.h"
#include <string.h>

/* --- little-endian helpers --- */
static inline void put_u16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF; }
static inline void put_i16(uint8_t *p, int16_t v)  { put_u16(p, (uint16_t)v); }
static inline uint16_t get_u16(const uint8_t *p)    { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static inline int16_t  get_i16(const uint8_t *p)    { return (int16_t)get_u16(p); }

static uint16_t clamp_u16(float x) { if (x < 0.0f) return 0; if (x > 65535.0f) return 65535; return (uint16_t)(x + 0.5f); }
static int16_t  clamp_i16(float x) { if (x < -32768.0f) return -32768; if (x > 32767.0f) return 32767; return (int16_t)(x < 0 ? x - 0.5f : x + 0.5f); }
static int8_t   clamp_i8(float x)  { if (x < -128.0f) return -128; if (x > 127.0f) return 127; return (int8_t)(x < 0 ? x - 0.5f : x + 0.5f); }

uint32_t cec_telem_pack(const cec_telem_t *t, uint8_t sub, uint8_t out[8])
{
    if (t == NULL || out == NULL) return 0;
    memset(out, 0, 8);
    switch (sub) {
    case 0: /* RAILS_V: u16 mV per rail */
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            put_u16(&out[r * 2], clamp_u16(t->v[r] * 1000.0f));
        return CEC_TELEM_ID_RAILS_V;
    case 1: /* RAILS_I: i16 mA per rail */
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            put_i16(&out[r * 2], clamp_i16(t->i[r] * 1000.0f));
        return CEC_TELEM_ID_RAILS_I;
    case 2: /* STATUS */
        out[0] = t->module_type;
        out[1] = t->state;
        out[2] = (uint8_t)((t->ps_on ? CEC_TELEM_FLAG_PS_ON : 0) |
                           (t->pwr_ok ? CEC_TELEM_FLAG_PWR_OK : 0) |
                           (t->shutting_down ? CEC_TELEM_FLAG_SHUTTING_DOWN : 0));
        out[3] = (uint8_t)clamp_i8(t->temp_c);
        put_u16(&out[4], clamp_u16(t->p_total_w * 10.0f));   /* deciwatts */
        out[6] = t->seq;
        return CEC_TELEM_ID_STATUS;
    default:
        return 0;
    }
}

bool cec_telem_unpack(uint32_t id, const uint8_t *data, uint8_t len, cec_telem_t *t)
{
    if (data == NULL || t == NULL || len < 8) {
        /* All three frames are 8 bytes; a short frame is malformed. */
        if (len < 8) return false;
    }
    if (id == CEC_TELEM_ID_RAILS_V) {
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            t->v[r] = get_u16(&data[r * 2]) / 1000.0f;
        return true;
    }
    if (id == CEC_TELEM_ID_RAILS_I) {
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            t->i[r] = get_i16(&data[r * 2]) / 1000.0f;
        return true;
    }
    if (id == CEC_TELEM_ID_STATUS) {
        t->module_type   = data[0];
        t->state         = data[1];
        t->ps_on         = (data[2] & CEC_TELEM_FLAG_PS_ON) != 0;
        t->pwr_ok        = (data[2] & CEC_TELEM_FLAG_PWR_OK) != 0;
        t->shutting_down = (data[2] & CEC_TELEM_FLAG_SHUTTING_DOWN) != 0;
        t->temp_c        = (float)(int8_t)data[3];
        t->p_total_w     = get_u16(&data[4]) / 10.0f;
        t->seq           = data[6];
        return true;
    }
    return false;
}
