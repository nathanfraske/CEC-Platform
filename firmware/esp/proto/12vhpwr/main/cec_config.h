/*
 * 12vhpwr-proto board/application configuration — the official
 * board-variation point (eps main/cec_config pattern, firmware
 * consolidation Phase H3). Pins, LSB scaling, and the link clock live
 * here, never inside firmware/esp/components.
 *
 * Pin map per doc section 6.3 / 10 (ESP32-P4-Module-DEV-KIT GPIO header
 * to the Tang Primer 25K dock 2x20 GPIO field).
 *
 * Re-pinned off GPIO 20-24 (bench bring-up): on the ESP32-P4 those pads
 * are the flash/PSRAM MSPI bus (IO_MUX DBG_PSRAM_*), so gpio_config on
 * them hangs the CPU. GPIO 1-5 are plain-GPIO-only, exposed on the
 * DEV-KIT header, with no flash/PSRAM/Ethernet/console/strap function.
 * Dock field positions and FPGA balls are UNCHANGED — only the ESP GPIO
 * (and thus which header pin the jumper lands on) moved.
 */

#pragma once

#include "cec_fpga_link.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PROTO_PIN_SCLK  1    /* -> dock field T13 (FPGA F2)  */
#define PROTO_PIN_MOSI  2    /* -> dock field T14 (FPGA B2)  */
#define PROTO_PIN_MISO  3    /* <- dock field B14 (FPGA C2)  */
#define PROTO_PIN_CS    4    /* -> dock field B13 (FPGA F1)  */
#define PROTO_PIN_DRDY  5    /* <- dock field B12 (FPGA A1)  */

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
