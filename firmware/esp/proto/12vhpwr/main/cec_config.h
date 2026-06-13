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

#include <stdbool.h>
#include <stdint.h>
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
#define PROTO_LINK_CLOCK_HZ  (10 * 1000 * 1000) /* 10 MHz: the oversampled-slave
                                                 * ceiling (fabric 50 MHz / 5).
                                                 * Needed to read an 18-byte
                                                 * frame (~14.4 us) inside the
                                                 * 50 kHz period (20 us). If the
                                                 * monitor shows bad headers at
                                                 * 10 MHz, back off to 8 MHz. */

/* AD7606 +/-5 V range: 152.59 uV per LSB. */
#define PROTO_LSB_VOLTS      (5.0 / 32768.0)

/* 12V-rail voltage divider: 47k top / 10k bottom -> rail = adc * (47+10)/10. */
#define PROTO_RAIL_DIVIDER   (57.0f / 10.0f)

/* Per-pin current sense (PROVISIONAL -- confirm against the perfboard):
 *   amps = (adc_volts - PROTO_ISENSE_BIAS_V) / PROTO_ISENSE_V_PER_A
 * BIAS  = sense-amp output at 0 A (the capture's steady channels sit ~2.40 V).
 * V_PER_A = Rshunt * gain. The spec 12VHPWR-Std front-end is 1 mOhm * INA240A3
 * (gain 100) = 0.1 V/A; set this to the board's ACTUAL shunt*gain. Only the
 * magnitude scales with V_PER_A -- the sign and zero are right regardless. */
#define PROTO_ISENSE_BIAS_V    2.40f
#define PROTO_ISENSE_V_PER_A   0.10f

/*
 * Per-channel physical calibration. The TelePlot loop turns each raw AD7606
 * channel (ADC volts, ±5 V full-scale) into a physical quantity:
 *
 *     physical = (adc_volts - offset_v) * scale
 *
 *   VOLTAGE via a divider:  scale = (Rtop + Rbot) / Rbot,  offset_v = 0
 *   CURRENT via shunt+amp:  scale = 1 / (Rshunt * Again),  offset_v = Vbias
 *
 * `label` is the TelePlot series name; `median` runs the channel through a
 * small rolling median to reject the per-channel glitch -- use it on steady
 * VOLTAGE channels, NOT on current channels whose real transients you keep.
 *
 * TODO(bench): the current channels are RAW (ADC volts) until the perfboard
 * front-end is pinned. Per per-pin current channel set kind=PROTO_KIND_AMP,
 * scale=1/(Rshunt*gain), offset_v=Vbias, label="i<pin>" and it streams amps.
 * v6 (index 5) is the confirmed 12V-rail divider and is already calibrated.
 */
typedef enum { PROTO_KIND_RAW, PROTO_KIND_VOLT, PROTO_KIND_AMP } proto_kind_t;

typedef struct {
    const char  *label;     /* TelePlot series name                        */
    proto_kind_t kind;      /* RAW=adc volts, VOLT=volts, AMP=amps         */
    float        scale;     /* multiplies (adc_volts - offset_v)           */
    float        offset_v;  /* bias subtracted before scaling              */
    bool         median;    /* rolling-median de-glitch (steady channels)  */
} proto_ch_cal_t;

extern const proto_ch_cal_t PROTO_CH_CAL[CEC_FPGA_FRAME_CHANNELS];

/* Apply PROTO_CH_CAL[ch] to a raw ADC code -> physical value (no filtering). */
float       proto_channel_phys(int ch, int16_t code);
/* Unit suffix for a calibration kind ("V" / "A" / "Vadc"). */
const char *proto_kind_unit(proto_kind_t kind);

/*
 * Fill a link config from the constants above.
 */
void cec_config_fpga_link(cec_fpga_link_config_t *out);

#ifdef __cplusplus
}
#endif
