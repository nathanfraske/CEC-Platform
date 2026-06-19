/*
 * CAN-OTA — application-level firmware update over classical CAN.
 *
 * The ESP32-S3 ROM bootloader speaks UART/USB, NOT CAN, so there is no
 * "CAN bootloader". This is an APPLICATION OTA: the running module app
 * receives its next image as a stream of CAN frames, writes it to the
 * inactive OTA partition with esp_ota_*, validates it, switches the boot
 * partition, and reboots. One source of truth for the frame format, shared
 * by the module (receiver) and the Hub (sender):
 *
 *   CTRL (Hub->module, 0x340): byte[0]=opcode
 *       BEGIN: byte[1..4] = image size, uint32 LE
 *       END:   byte[1..4] = CRC32 (zlib/IEEE) of the image, uint32 LE
 *       ABORT
 *   DATA (Hub->module, 0x341): byte[0]=seq (rolling u8), byte[1..7]=7 bytes
 *   STAT (module->Hub, 0x342): byte[0]=status (+ byte[1] = seq or errcode)
 *
 * Transport is STOP-AND-WAIT: the Hub sends one DATA frame and waits for
 * STAT ACK(seq) before the next, re-sending on timeout. Robust and simple;
 * ~2.5 kB/s at 125 kbps (a ~280 kB app is ~2 min), fine for the bench. The
 * receiver tracks the running offset itself (in-order by construction) so
 * the last frame's 1..7 valid bytes are inferred from the BEGIN size.
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Frame IDs (classical 11-bit). Below the 0x200 telemetry burst in priority
 * (the module pauses telemetry during an update via the active callback). */
#define CEC_OTA_ID_CTRL   0x340   /* Hub -> module: BEGIN / END / ABORT */
#define CEC_OTA_ID_DATA   0x341   /* Hub -> module: 7 payload bytes/frame */
#define CEC_OTA_ID_STAT   0x342   /* module -> Hub: READY/ACK/NAK/DONE/ERR */

/* CTRL opcodes (byte[0]) */
enum {
    CEC_OTA_OP_BEGIN = 0x01,  /* byte[1..4] = image size, uint32 LE */
    CEC_OTA_OP_END   = 0x02,  /* byte[1..4] = CRC32 of the image, LE */
    CEC_OTA_OP_ABORT = 0x03,
};

/* STAT status (byte[0]) */
enum {
    CEC_OTA_ST_READY = 0x01,  /* BEGIN accepted, OTA slot open */
    CEC_OTA_ST_ACK   = 0x02,  /* byte[1] = acked seq; send next */
    CEC_OTA_ST_NAK   = 0x03,  /* byte[1] = expected seq; resend */
    CEC_OTA_ST_DONE  = 0x04,  /* image valid + boot set; module rebooting */
    CEC_OTA_ST_ERR   = 0x05,  /* byte[1] = errcode below */
};
enum {
    CEC_OTA_ERR_BEGIN = 0x01, /* esp_ota_begin failed / no OTA slot */
    CEC_OTA_ERR_WRITE = 0x02, /* esp_ota_write failed */
    CEC_OTA_ERR_SIZE  = 0x03, /* more data than BEGIN announced */
    CEC_OTA_ERR_CRC   = 0x04, /* CRC32 / image validation mismatch */
    CEC_OTA_ERR_STATE = 0x05, /* DATA before BEGIN, etc. */
};

#define CEC_OTA_DATA_BYTES 7  /* payload bytes per DATA frame */

/* ---------- module (receiver) side ---------- */

/* Optional callback: true at BEGIN, false at ABORT/ERR/DONE-fail, so the
 * app can pause its telemetry TX while an update is in flight. */
typedef void (*cec_canota_active_cb)(bool active);

/* Spawn the receiver task. It drains can_receive(), drives the OTA state
 * machine (writes the streamed image to the inactive OTA slot, sets it
 * bootable, reboots on a valid END), and ignores non-OTA frames. Requires
 * CAN to be up (can_init) and OTA partitions in the table. */
esp_err_t cec_canota_receiver_start(cec_canota_active_cb on_active);

/* Confirm the running image so the bootloader won't roll it back. Call once
 * early in app_main on an OTA-partitioned board; harmless (logs) otherwise. */
void cec_canota_mark_valid(void);

/* ---------- Hub (sender) side ---------- */

typedef void (*cec_canota_progress_cb)(size_t sent, size_t total);

/* Stream image/len to the module over CAN (stop-and-wait + retries). The
 * caller MUST own can_receive() for the duration (suspend any other RX
 * drain). Returns ESP_OK once the module ACKs DONE, else an error. */
esp_err_t cec_canota_send(const uint8_t *image, size_t len,
                          cec_canota_progress_cb progress);

/* Standard CRC32 (zlib/IEEE, poly 0xEDB88320). Chainable: passing a
 * previous result as `crc` continues it, so it matches Python zlib.crc32
 * across chunked input. Seed the first call with 0. */
uint32_t cec_canota_crc32_update(uint32_t crc, const uint8_t *data, size_t len);
static inline uint32_t cec_canota_crc32(const uint8_t *data, size_t len)
{
    return cec_canota_crc32_update(0, data, len);
}

#ifdef __cplusplus
}
#endif
