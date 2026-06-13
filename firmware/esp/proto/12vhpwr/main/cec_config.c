/*
 * 12vhpwr-proto board/application configuration — definitions.
 */

#include "cec_config.h"

/*
 * Per-channel calibration. v6 (index 5) is the 12V-rail divider -> volts;
 * v3-v5,v7,v8 are per-pin current senses -> amps via the PROVISIONAL
 * PROTO_ISENSE_* constants (see cec_config.h -- confirm the shunt*gain and
 * the channel->pin map). v1/v2 are NOT wired into the measuring cable yet,
 * so they carry a NULL label = "unconnected": not emitted to TelePlot (the
 * `frame` CLI still shows their raw value). To enable one, give it a label
 * + kind; to mark another unconnected, set its label NULL.
 */
/* Negated: the sense is wired so load current pulls the ADC BELOW bias, so
 * a GPU draw read as negative -- flip it so a draw is positive amps
 * (bench-confirmed 2026-06-13). Drop the '-' if a board reads inverted. */
#define ISCALE  (-1.0f / PROTO_ISENSE_V_PER_A)
#define IBIAS   PROTO_ISENSE_BIAS_V
const proto_ch_cal_t PROTO_CH_CAL[CEC_FPGA_FRAME_CHANNELS] = {
    /* idx 0  v1 */ { NULL,    PROTO_KIND_RAW,  1.0f,               0.0f,  false }, /* unconnected */
    /* idx 1  v2 */ { NULL,    PROTO_KIND_RAW,  1.0f,               0.0f,  false }, /* unconnected */
    /* idx 2  v3 */ { "i3",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false },
    /* idx 3  v4 */ { "i4",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false },
    /* idx 4  v5 */ { "i5",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false },
    /* idx 5  v6 */ { "vrail", PROTO_KIND_VOLT, PROTO_RAIL_DIVIDER, 0.0f,  true  },
    /* idx 6  v7 */ { "i7",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false },
    /* idx 7  v8 */ { "i8",    PROTO_KIND_AMP,  ISCALE,             IBIAS, false },
};

float proto_channel_phys(int ch, int16_t code)
{
    const proto_ch_cal_t *c = &PROTO_CH_CAL[ch];
    return (float)((code * PROTO_LSB_VOLTS - c->offset_v) * c->scale);
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
