/*
 * 12vhpwr-proto board/application configuration — definitions.
 */

#include "cec_config.h"

/*
 * Per-channel calibration. v6 (index 5) is the 12V-rail divider -> volts.
 * The seven others stream RAW ADC volts until the perfboard current
 * front-end (shunt / amp gain / bias) is pinned -- see cec_config.h. Flip a
 * channel to AMP by setting kind/scale/offset_v/label here; nothing else
 * changes.
 */
const proto_ch_cal_t PROTO_CH_CAL[CEC_FPGA_FRAME_CHANNELS] = {
    /* idx 0  v1 */ { "v1",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 1  v2 */ { "v2",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 2  v3 */ { "v3",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 3  v4 */ { "v4",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 4  v5 */ { "v5",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 5  v6 */ { "vrail", PROTO_KIND_VOLT, PROTO_RAIL_DIVIDER, 0.0f, true  },
    /* idx 6  v7 */ { "v7",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
    /* idx 7  v8 */ { "v8",    PROTO_KIND_RAW,  1.0f,               0.0f, false },
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
