/*
 * 12vhpwr-proto board/application configuration — definitions.
 */

#include "cec_config.h"

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
