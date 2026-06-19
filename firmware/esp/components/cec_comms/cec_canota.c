#include "cec_canota.h"
#include "cec_can.h"

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"

#if CEC_CAN_ENABLED
#include "esp_ota_ops.h"
#include "esp_partition.h"
#endif

static const char *TAG = "canota";

/* ---- little-endian + CRC32 (standard zlib, chainable) ---- */
static inline uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline void put_le32(uint8_t *p, uint32_t v)
{
    p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF;
    p[2] = (v >> 16) & 0xFF; p[3] = (v >> 24) & 0xFF;
}

uint32_t cec_canota_crc32_update(uint32_t crc, const uint8_t *data, size_t len)
{
    crc = ~crc;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
    }
    return ~crc;
}

#if CEC_CAN_ENABLED

/* =================== module (receiver) side =================== */

static void stat(uint8_t status, uint8_t arg)
{
    uint8_t d[8] = { status, arg, 0, 0, 0, 0, 0, 0 };
    can_send_frame(CEC_OTA_ID_STAT, d, sizeof(d));
}

static void receiver_task(void *arg)
{
    cec_canota_active_cb on_active = (cec_canota_active_cb)arg;

    esp_ota_handle_t ota = 0;
    const esp_partition_t *part = NULL;
    bool     active = false;
    size_t   total = 0, written = 0;
    uint8_t  expected_seq = 0;
    uint32_t crc_running = 0;

    ESP_LOGI(TAG, "OTA receiver up; running from '%s'",
             esp_ota_get_running_partition()->label);

    while (1) {
        uint32_t id = 0; uint8_t len = 0, d[8];
        if (can_receive(&id, d, &len, 60000) != ESP_OK) continue;

        if (id == CEC_OTA_ID_CTRL) {
            uint8_t op = d[0];
            if (op == CEC_OTA_OP_BEGIN) {
                if (active) { esp_ota_abort(ota); active = false; }
                total = le32(&d[1]); written = 0; expected_seq = 0; crc_running = 0;
                part = esp_ota_get_next_update_partition(NULL);
                if (!part) { ESP_LOGE(TAG, "no OTA slot"); stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_BEGIN); continue; }
                /* Silence the per-frame RX ISR log for the ~tens-of-thousands
                 * of DATA frames -- otherwise it floods the console + bus. */
                can_set_rx_log(false);
                if (esp_ota_begin(part, total, &ota) != ESP_OK) {
                    can_set_rx_log(true);
                    ESP_LOGE(TAG, "esp_ota_begin failed"); stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_BEGIN); continue;
                }
                active = true; if (on_active) on_active(true);
                ESP_LOGI(TAG, "OTA begin: %u bytes -> '%s'", (unsigned)total, part->label);
                stat(CEC_OTA_ST_READY, 0);
            } else if (op == CEC_OTA_OP_END) {
                if (!active) { stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_STATE); continue; }
                uint32_t want = le32(&d[1]);
                can_set_rx_log(true);
                if (written != total) {
                    ESP_LOGE(TAG, "size mismatch: got %u want %u", (unsigned)written, (unsigned)total);
                    esp_ota_abort(ota); active = false; if (on_active) on_active(false);
                    stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_SIZE); continue;
                }
                if (crc_running != want) {
                    ESP_LOGE(TAG, "CRC mismatch: got %08x want %08x", (unsigned)crc_running, (unsigned)want);
                    esp_ota_abort(ota); active = false; if (on_active) on_active(false);
                    stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_CRC); continue;
                }
                esp_err_t e = esp_ota_end(ota);     /* also validates the image header/hash */
                if (e != ESP_OK) {
                    ESP_LOGE(TAG, "esp_ota_end: %s", esp_err_to_name(e));
                    active = false; if (on_active) on_active(false);
                    stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_CRC); continue;
                }
                if (esp_ota_set_boot_partition(part) != ESP_OK) {
                    active = false; if (on_active) on_active(false);
                    stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_STATE); continue;
                }
                ESP_LOGW(TAG, "OTA complete (%u bytes, crc %08x) -> booting '%s'",
                         (unsigned)written, (unsigned)crc_running, part->label);
                stat(CEC_OTA_ST_DONE, 0);
                vTaskDelay(pdMS_TO_TICKS(300));     /* let the STAT frame drain */
                esp_restart();
            } else if (op == CEC_OTA_OP_ABORT) {
                if (active) { esp_ota_abort(ota); active = false; can_set_rx_log(true); if (on_active) on_active(false); }
                ESP_LOGW(TAG, "OTA aborted by Hub");
            }
        } else if (id == CEC_OTA_ID_DATA) {
            if (!active) { stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_STATE); continue; }
            uint8_t seq = d[0];
            if (seq == expected_seq) {
                size_t n = CEC_OTA_DATA_BYTES;
                if (written + n > total) n = total - written;   /* partial last frame */
                if (n && esp_ota_write(ota, &d[1], n) != ESP_OK) {
                    esp_ota_abort(ota); active = false; can_set_rx_log(true); if (on_active) on_active(false);
                    stat(CEC_OTA_ST_ERR, CEC_OTA_ERR_WRITE); continue;
                }
                crc_running = cec_canota_crc32_update(crc_running, &d[1], n);
                written += n; expected_seq++;
                stat(CEC_OTA_ST_ACK, seq);
            } else if (seq == (uint8_t)(expected_seq - 1)) {
                stat(CEC_OTA_ST_ACK, seq);          /* duplicate (our ACK was lost) -> re-ACK */
            } else {
                stat(CEC_OTA_ST_NAK, expected_seq);
            }
        }
        /* other IDs ignored -- this task only services OTA */
    }
}

esp_err_t cec_canota_receiver_start(cec_canota_active_cb on_active)
{
    if (xTaskCreatePinnedToCore(receiver_task, "canota_rx", 6144,
                                (void *)on_active, 6, NULL, 0) != pdPASS)
        return ESP_ERR_NO_MEM;
    return ESP_OK;
}

void cec_canota_mark_valid(void)
{
    const esp_partition_t *run = esp_ota_get_running_partition();
    esp_ota_img_states_t st;
    if (esp_ota_get_state_partition(run, &st) != ESP_OK) {
        ESP_LOGI(TAG, "running from '%s' (no OTA state)", run->label);
        return;
    }
    if (st == ESP_OTA_IMG_PENDING_VERIFY) {
        ESP_LOGW(TAG, "image pending verify -> marking valid (rollback cancelled)");
        esp_ota_mark_app_valid_cancel_rollback();
    } else {
        ESP_LOGI(TAG, "running from '%s' (state %d)", run->label, (int)st);
    }
}

/* =================== Hub (sender) side =================== */

#define OTA_STAT_TIMEOUT_MS   1000
#define OTA_END_TIMEOUT_MS    8000   /* module validates + flips boot here */
#define OTA_MAX_RETRY         8

/* Drain can_receive() until a STAT frame arrives or timeout. Returns true on
 * a STAT, filling status and arg. Non-STAT frames are skipped. */
static bool wait_stat(uint8_t *status, uint8_t *arg, uint32_t timeout_ms)
{
    int64_t deadline_ticks = (int64_t)pdMS_TO_TICKS(timeout_ms);
    TickType_t start = xTaskGetTickCount();
    while (1) {
        TickType_t elapsed = xTaskGetTickCount() - start;
        if ((int64_t)elapsed >= deadline_ticks) return false;
        uint32_t left_ms = timeout_ms - (elapsed * portTICK_PERIOD_MS);
        uint32_t id = 0; uint8_t len = 0, d[8];
        if (can_receive(&id, d, &len, left_ms ? left_ms : 1) != ESP_OK) return false;
        if (id == CEC_OTA_ID_STAT) { *status = d[0]; *arg = d[1]; return true; }
    }
}

esp_err_t cec_canota_send(const uint8_t *image, size_t len,
                          cec_canota_progress_cb progress)
{
    if (!image || !len) return ESP_ERR_INVALID_ARG;

    /* BEGIN */
    uint8_t c[8] = { CEC_OTA_OP_BEGIN }; put_le32(&c[1], (uint32_t)len);
    uint8_t status = 0, arg = 0;
    bool ready = false;
    for (int r = 0; r < OTA_MAX_RETRY && !ready; r++) {
        can_send_frame(CEC_OTA_ID_CTRL, c, sizeof(c));
        if (wait_stat(&status, &arg, OTA_STAT_TIMEOUT_MS)) {
            if (status == CEC_OTA_ST_READY) ready = true;
            else if (status == CEC_OTA_ST_ERR) { ESP_LOGE(TAG, "module BEGIN err %u", arg); return ESP_FAIL; }
        }
    }
    if (!ready) { ESP_LOGE(TAG, "no READY from module"); return ESP_ERR_TIMEOUT; }

    /* DATA, stop-and-wait */
    size_t off = 0; uint8_t seq = 0;
    while (off < len) {
        size_t n = (len - off < CEC_OTA_DATA_BYTES) ? (len - off) : CEC_OTA_DATA_BYTES;
        uint8_t f[8] = { seq, 0, 0, 0, 0, 0, 0, 0 };
        memcpy(&f[1], &image[off], n);

        bool acked = false;
        for (int r = 0; r < OTA_MAX_RETRY && !acked; r++) {
            can_send_frame(CEC_OTA_ID_DATA, f, sizeof(f));
            if (wait_stat(&status, &arg, OTA_STAT_TIMEOUT_MS)) {
                if (status == CEC_OTA_ST_ACK && arg == seq) acked = true;
                else if (status == CEC_OTA_ST_ERR) { ESP_LOGE(TAG, "module DATA err %u @%u", arg, (unsigned)off); return ESP_FAIL; }
                /* NAK or stale ACK -> just resend the current frame */
            }
        }
        if (!acked) { ESP_LOGE(TAG, "no ACK @%u; aborting", (unsigned)off);
                      uint8_t a[8] = { CEC_OTA_OP_ABORT }; can_send_frame(CEC_OTA_ID_CTRL, a, sizeof(a));
                      return ESP_ERR_TIMEOUT; }
        off += n; seq++;
        if (progress) progress(off, len);
    }

    /* END (carries the CRC32; module validates, flips boot, reboots) */
    uint8_t e[8] = { CEC_OTA_OP_END }; put_le32(&e[1], cec_canota_crc32(image, len));
    for (int r = 0; r < OTA_MAX_RETRY; r++) {
        can_send_frame(CEC_OTA_ID_CTRL, e, sizeof(e));
        if (wait_stat(&status, &arg, OTA_END_TIMEOUT_MS)) {
            if (status == CEC_OTA_ST_DONE) { ESP_LOGW(TAG, "module reports DONE -> rebooting into new image"); return ESP_OK; }
            if (status == CEC_OTA_ST_ERR)  { ESP_LOGE(TAG, "module END err %u", arg); return ESP_FAIL; }
        }
    }
    ESP_LOGE(TAG, "no DONE from module");
    return ESP_ERR_TIMEOUT;
}

#else  /* !CEC_CAN_ENABLED -- link stubs */

esp_err_t cec_canota_receiver_start(cec_canota_active_cb on_active)
{ (void)on_active; return ESP_ERR_NOT_SUPPORTED; }
void cec_canota_mark_valid(void) { }
esp_err_t cec_canota_send(const uint8_t *image, size_t len, cec_canota_progress_cb p)
{ (void)image; (void)len; (void)p; return ESP_ERR_NOT_SUPPORTED; }

#endif /* CEC_CAN_ENABLED */
