/*
 * FPGA acquisition link — SPI master to the CEC RTL's cec_spi_slave
 * (firmware consolidation, Phase H1). The fabric latches an 18-byte
 * frame (0xA5 header, sequence, eight big-endian int16 channel codes)
 * and holds DRDY high while an unread frame waits; a completed read
 * clears it. Keep the SPI clock at or under 5 MHz: the slave is
 * oversampled at 50 MHz fabric clock.
 *
 * Used by the 12vhpwr-proto bring-up app (GW5A on the Tang Primer 25K
 * dock + AD7606); FPGA-Max reuses this component unchanged. Pins,
 * host, and clock are app config (each app's cec_config) — board
 * wiring never lives in a shared component.
 *
 * Reads are serialized with an internal mutex so a CLI 'frame' command
 * and a streaming loop can share the link safely.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/spi_master.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CEC_FPGA_FRAME_CHANNELS 8
#define CEC_FPGA_FRAME_HEADER   0xA5

typedef struct {
    int pin_sclk;
    int pin_mosi;          /* unused by the v0 read-only link; reserved
                              for later command traffic */
    int pin_miso;
    int pin_cs;
    int pin_drdy;
    spi_host_device_t host;
    int clock_speed_hz;    /* <= 5 MHz (oversampled slave) */
} cec_fpga_link_config_t;

typedef struct {
    bool    header_ok;     /* header byte == 0xA5 */
    uint8_t header;        /* raw header byte (alignment diagnosis) */
    uint8_t seq;           /* frame sequence counter */
    int16_t code[CEC_FPGA_FRAME_CHANNELS];   /* V1..V8 raw codes */
} cec_fpga_frame_t;

/*
 * Configure the DRDY input and the SPI bus + device. Call once.
 */
esp_err_t cec_fpga_link_init(const cec_fpga_link_config_t *cfg);

/*
 * DRDY level: true while an unread frame is waiting in the fabric.
 */
bool cec_fpga_link_poll(void);

/*
 * Pull one 18-byte frame and decode it. Returns ESP_OK with the frame
 * filled (check frame->header_ok before trusting the codes), or
 * ESP_ERR_INVALID_STATE before init.
 */
esp_err_t cec_fpga_link_read(cec_fpga_frame_t *out);

#ifdef __cplusplus
}
#endif
