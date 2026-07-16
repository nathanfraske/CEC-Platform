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
 * ESP_ERR_INVALID_STATE before init. Drives MOSI low: the fabric returns
 * the LIVE latest frame.
 */
esp_err_t cec_fpga_link_read(cec_fpga_frame_t *out);

/*
 * Same, but drives MOSI HIGH: the fabric streams its native-rate capture
 * ring. The FIRST buffered read after a run of live reads ARMS (freezes
 * the ring at the oldest frame; its returned data is the still-live frame
 * -- discard it), and each subsequent buffered read returns the next ring
 * frame and advances. A normal (live) read resumes the fill. Use this in a
 * tight loop to pull a gap-free, FPGA-paced window in one go.
 */
esp_err_t cec_fpga_link_read_buffered(cec_fpga_frame_t *out);

/*
 * Drives MOSI = 0x55: the fabric returns the CONTINUOUS decimated stream from
 * its free-running FIFO (every native frame boxcar-averaged by DECIM_M, ~25
 * kSPS). Unlike the burst ring this is NOT frozen -- it streams indefinitely.
 * The frame's `seq` byte carries the saturating PER-SESSION dropped-sample
 * count (FIFO overrun = the ESP fell behind); `header` is 0x5A instead of 0xA5
 * on an underrun read (FIFO momentarily empty -- stale codes, skip the frame).
 * Send one read to select the mode (discard it), then drain in a tight block
 * loop with NO per-frame formatting -- the decimation already cut the rate, and
 * keeping the drain free of the console path is what lets it run gap-free.
 */
esp_err_t cec_fpga_link_read_stream(cec_fpga_frame_t *out);

/*
 * Drives MOSI = 0x33: the fabric returns a STATUS frame -- header 0x5C, a
 * free-running native-frame counter packed as count[31:16] in code[0] and
 * count[15:0] in code[1] (the rest zero). Read it twice over a known wall-time
 * and (count2 - count1) / dt is the TRUE native sample rate (the conv+read FSM
 * self-limits below the nominal pacer), so the burst/FFT time axis is measured,
 * not the nominal label. Send one read to select the mode (discard it), then read.
 */
esp_err_t cec_fpga_link_read_status(cec_fpga_frame_t *out);

/*
 * Native-rate detector control. The fabric carries a per-channel transient/
 * imbalance detector (top.v cec_native_detect); these drive its STICKY arm
 * latch via MOSI command bytes -- 0x44 ARMs, 0x46 DISARMs+clears (and resumes
 * the ring). Both are MSB=0 so STATUS polling / BURST reads never disarm it and
 * never trip the 0xFF burst freeze. On a trip the fabric freezes the burst ring
 * CENTERED on the event; poll cec_fpga_link_read_status() and read the STATUS
 * word in code[2] = {tripped[15], frozen[14], 0, trip_ch[7:0]} (V1/V2 stay the
 * rate counter). When tripped, read the centered dump with read_buffered() like
 * fastburst, then call _detect_clear() to disarm. The command byte's returned
 * frame is the prior mode's data -- discard it.
 */
esp_err_t cec_fpga_link_detect_arm(void);
esp_err_t cec_fpga_link_detect_clear(void);

#ifdef __cplusplus
}
#endif
