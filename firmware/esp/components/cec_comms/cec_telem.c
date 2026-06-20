#include "cec_telem.h"
#include "cec_state.h"   /* CEC_MODULE_TYPE_* */
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
    case CEC_TELEM_SUB_RAILS_V: /* u16 mV per channel */
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            put_u16(&out[r * 2], clamp_u16(t->v[r] * 1000.0f));
        return CEC_TELEM_ID(t->instance, CEC_TELEM_SUB_RAILS_V);
    case CEC_TELEM_SUB_RAILS_I: /* i16 mA per channel */
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            put_i16(&out[r * 2], clamp_i16(t->i[r] * 1000.0f));
        return CEC_TELEM_ID(t->instance, CEC_TELEM_SUB_RAILS_I);
    case CEC_TELEM_SUB_STATUS:
        out[0] = t->module_type;
        out[1] = t->state;
        out[2] = t->flags;                                   /* module-type-defined */
        out[3] = (uint8_t)clamp_i8(t->temp_c);
        put_u16(&out[4], clamp_u16(t->p_total_w * 10.0f));   /* deciwatts */
        out[6] = t->seq;
        return CEC_TELEM_ID(t->instance, CEC_TELEM_SUB_STATUS);
    default:
        return 0;
    }
}

bool cec_telem_id_is(uint32_t id)
{
    if (id < CAN_ID_TELEMETRY_BASE) return false;
    uint32_t off = id - CAN_ID_TELEMETRY_BASE;
    uint32_t inst = off / CEC_TELEM_STRIDE;
    uint32_t sub  = off % CEC_TELEM_STRIDE;
    return inst < CEC_MAX_MODULES && sub < CEC_TELEM_NUM_SUB;
}

uint8_t cec_telem_id_instance(uint32_t id)
{
    return (uint8_t)((id - CAN_ID_TELEMETRY_BASE) / CEC_TELEM_STRIDE);
}

uint8_t cec_telem_id_sub(uint32_t id)
{
    return (uint8_t)((id - CAN_ID_TELEMETRY_BASE) % CEC_TELEM_STRIDE);
}

bool cec_telem_unpack(uint32_t id, const uint8_t *data, uint8_t len, cec_telem_t *t)
{
    if (data == NULL || t == NULL || len < 8) return false;   /* all frames are 8 bytes */
    if (!cec_telem_id_is(id)) return false;

    t->instance = cec_telem_id_instance(id);
    switch (cec_telem_id_sub(id)) {
    case CEC_TELEM_SUB_RAILS_V:
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            t->v[r] = get_u16(&data[r * 2]) / 1000.0f;
        return true;
    case CEC_TELEM_SUB_RAILS_I:
        for (int r = 0; r < CEC_TELEM_NUM_RAILS; r++)
            t->i[r] = get_i16(&data[r * 2]) / 1000.0f;
        return true;
    case CEC_TELEM_SUB_STATUS:
        t->module_type = data[0];
        t->state       = data[1];
        t->flags       = data[2];
        t->temp_c      = (float)(int8_t)data[3];
        t->p_total_w   = get_u16(&data[4]) / 10.0f;
        t->seq         = data[6];
        return true;
    default:
        return false;
    }
}

const char *cec_telem_type_name(uint8_t module_type)
{
    switch (module_type) {
    case CEC_MODULE_TYPE_ATX24:   return "ATX24";
    case CEC_MODULE_TYPE_EPS:     return "EPS";
    case CEC_MODULE_TYPE_PCIE:    return "PCIe";
    case CEC_MODULE_TYPE_12VHPWR: return "12VHPWR";
    default:                      return "?";
    }
}

const char *cec_telem_chan_label(uint8_t module_type, int chan)
{
    static const char *atx[CEC_TELEM_NUM_RAILS] = { "12v", "5v", "3v3", "5vsb" };
    static const char *eps[CEC_TELEM_NUM_RAILS] = { "cbl0", "cbl1", "ch2", "ch3" };
    static const char *pci[CEC_TELEM_NUM_RAILS] = { "cbl0", "cbl1", "cbl2", "ch3" };
    /* 12VHPWR Standard reports a per-pin summary over CAN (the 6 raw per-pin
     * currents stay local): rail current total + hottest/coldest pin + spread. */
    static const char *hpwr[CEC_TELEM_NUM_RAILS] = { "rail", "imax", "imin", "spread" };
    static const char *gen[CEC_TELEM_NUM_RAILS] = { "ch0", "ch1", "ch2", "ch3" };
    if (chan < 0 || chan >= CEC_TELEM_NUM_RAILS) return "ch?";
    switch (module_type) {
    case CEC_MODULE_TYPE_ATX24:   return atx[chan];
    case CEC_MODULE_TYPE_EPS:     return eps[chan];
    case CEC_MODULE_TYPE_PCIE:    return pci[chan];
    case CEC_MODULE_TYPE_12VHPWR: return hpwr[chan];
    default:                      return gen[chan];
    }
}
