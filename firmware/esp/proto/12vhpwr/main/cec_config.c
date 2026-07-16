/*
 * 12vhpwr-proto board/application configuration — definitions.
 */

#include "cec_config.h"

#include <stdbool.h>

/*
 * Per-channel calibration. v6 (index 5) is the 12V-rail divider -> volts; v7
 * (index 6) is a VCC tap through a 10k/10k divider (/2) + 100nF -> volts (scale
 * 2.0). The SIX per-pin current senses split by front-end TYPE -- a deliberate
 * A/B: v3-v5,v8 are the INA240 SHUNT path (ISCALE/IBIAS), v1/v2 are ACS712-20A
 * HALL modules (HSCALE/HBIAS -- lower precision, see cec_config.h). All read amps.
 */
/* Negated: the shunt sense is wired so load current pulls the ADC BELOW bias, so
 * a GPU draw read as negative -- flip it so a draw is positive amps
 * (bench-confirmed 2026-06-13). Drop the '-' if a board reads inverted. */
#define ISCALE  (-1.0f / PROTO_ISENSE_V_PER_A)
#define IBIAS   PROTO_ISENSE_BIAS_V
/* ACS712 sign (provisional): per the datasheet a rising IP+ -> IP- current raises
 * the output above Vcc/2, so a forward draw reads POSITIVE with +scale -- the
 * OPPOSITE polarity from the shunt wiring above. CONFIRM at the bench and flip the
 * sign if a draw reads negative (it depends which way the module sits in the line). */
#define HSCALE  (1.0f / PROTO_HALL_V_PER_A)
#define HBIAS   PROTO_HALL_BIAS_V
const proto_ch_cal_t PROTO_CH_CAL[CEC_FPGA_FRAME_CHANNELS] = {
    /* idx 0  v1 */ { "i1",    PROTO_KIND_AMP,  HSCALE,             HBIAS, false }, /* ACS712-20A Hall */
    /* idx 1  v2 */ { "i2",    PROTO_KIND_AMP,  HSCALE,             HBIAS, false }, /* ACS712-20A Hall */
    /* idx 2  v3 */ { "i3",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false }, /* INA240 shunt */
    /* idx 3  v4 */ { "i4",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false }, /* INA240 shunt */
    /* idx 4  v5 */ { "i5",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false }, /* INA240 shunt */
    /* idx 5  v6 */ { "vrail", PROTO_KIND_VOLT, PROTO_RAIL_DIVIDER, 0.0f,  true  },
    /* idx 6  v7 */ { "vcc",   PROTO_KIND_VOLT, 2.0f,               0.0f,  true  }, /* VCC tap: 10k/10k /2 + 100nF */
    /* idx 7  v8 */ { "i8",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false }, /* INA240 shunt */
};

/* Runtime per-channel offset (subtracted ADC volts). Starts at the config
 * offset_v; the `cal` command overwrites the AMP channels with their measured
 * no-load bias. Auto-seeds on first use so call order never matters. */
static bool  s_cal_inited = false;
static float s_cal_offset_v[CEC_FPGA_FRAME_CHANNELS];

static void cal_ensure(void)
{
    if (!s_cal_inited) {
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            s_cal_offset_v[ch] = PROTO_CH_CAL[ch].offset_v;
        s_cal_inited = true;
    }
}

void proto_cal_init(void) { cal_ensure(); }

void proto_cal_set_offset_v(int ch, float offset_v)
{
    cal_ensure();
    if (ch >= 0 && ch < CEC_FPGA_FRAME_CHANNELS) s_cal_offset_v[ch] = offset_v;
}

float proto_cal_get_offset_v(int ch)
{
    cal_ensure();
    return (ch >= 0 && ch < CEC_FPGA_FRAME_CHANNELS) ? s_cal_offset_v[ch] : 0.0f;
}

float proto_channel_phys(int ch, int16_t code)
{
    cal_ensure();
    const proto_ch_cal_t *c = &PROTO_CH_CAL[ch];
    return (float)((code * PROTO_LSB_VOLTS - s_cal_offset_v[ch]) * c->scale);
}

/* Measured native sample rate (Hz). 0 = not yet measured -> fall back to the
 * nominal PROTO_NATIVE_HZ. The `rate` command sets it; the burst/autoburst time
 * axes use it so the FFT frequency scale is honest, not the nominal label. */
static float s_measured_native_hz = 0.0f;

void  proto_set_measured_native_hz(float hz) { if (hz > 1.0f) s_measured_native_hz = hz; }
bool  proto_native_hz_measured(void)         { return s_measured_native_hz > 1.0f; }
float proto_measured_native_hz(void)
{
    return (s_measured_native_hz > 1.0f) ? s_measured_native_hz : (float)PROTO_NATIVE_HZ;
}

const char *proto_kind_unit(proto_kind_t kind)
{
    switch (kind) {
        case PROTO_KIND_VOLT: return "V";
        case PROTO_KIND_AMP:  return "A";
        default:              return "Vadc";
    }
}

void cec_config_fpga_link(cec_fpga_link_config_t *out)
{
    *out = (cec_fpga_link_config_t){
        .pin_sclk       = PROTO_PIN_SCLK,
        .pin_mosi       = PROTO_PIN_MOSI,
        .pin_miso       = PROTO_PIN_MISO,
        .pin_cs         = PROTO_PIN_CS,
        .pin_drdy       = PROTO_PIN_DRDY,
        .host           = PROTO_LINK_HOST,
        .clock_speed_hz = PROTO_LINK_CLOCK_HZ,
    };
}
