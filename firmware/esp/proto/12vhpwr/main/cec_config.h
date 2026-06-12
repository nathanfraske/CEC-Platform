/*
 * 12vhpwr-proto board/application configuration — the official
 * board-variation point (eps main/cec_config pattern, firmware
 * consolidation Phase H3). Pins, LSB scaling, and the link clock live
 * here, never inside firmware/esp/components.
 *
 * Pin map per doc section 6.3 / 10 (ESP32-P4-NANO header P1 to the
 * Tang Primer 25K dock 2x20 GPIO field).
 */

#pragma once

#include "cec_fpga_link.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PROTO_PIN_SCLK  20   /* P1-13 -> field T13 (F2)  */
#define PROTO_PIN_MOSI  21   /* P1-15 -> field T14 (B2)  */
#define PROTO_PIN_MISO  22   /* P1-16 -> field B14 (C2)  */
#define PROTO_PIN_CS    23   /* P1-7  -> field B13 (F1)  */
#define PROTO_PIN_DRDY  24   /* P1-18 <- field B12 (A1)  */

#define PROTO_LINK_HOST      SPI2_HOST
#define PROTO_LINK_CLOCK_HZ  (4 * 1000 * 1000)  /* 4 MHz: < 5 MHz oversample rec */

/* AD7606 +/-5 V range: 152.59 uV per LSB. */
#define PROTO_LSB_VOLTS      (5.0 / 32768.0)

/*
 * Fill a link config from the constants above.
 */
void cec_config_fpga_link(cec_fpga_link_config_t *out);

#ifdef __cplusplus
}
#endif
