/*
 * FPGA acquisition link — implementation. The SPI/GPIO mechanics are
 * the proto12v v0 main.c read path, extracted (Phase H1).
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "cec_fpga_link.h"

static const char *TAG = "cec_fpga_link";

#define FRAME_BYTES 18

static cec_fpga_link_config_t s_cfg;
static spi_device_handle_t    s_spi = NULL;
static SemaphoreHandle_t      s_lock = NULL;

esp_err_t cec_fpga_link_init(const cec_fpga_link_config_t *cfg)
{
    if (s_spi != NULL)  return ESP_OK;
    if (cfg == NULL)    return ESP_ERR_INVALID_ARG;
    s_cfg = *cfg;

    gpio_config_t drdy = {
        .pin_bit_mask = 1ULL << cfg->pin_drdy,
        .mode         = GPIO_MODE_INPUT,
    };
    esp_err_t err = gpio_config(&drdy);
    if (err != ESP_OK) return err;
    ESP_LOGI(TAG, "init: DRDY gpio ok; bringing up SPI host %d (sclk=%d mosi=%d miso=%d cs=%d)",
             (int)cfg->host, cfg->pin_sclk, cfg->pin_mosi, cfg->pin_miso, cfg->pin_cs);

    spi_bus_config_t bus = {
        .mosi_io_num   = cfg->pin_mosi,
        .miso_io_num   = cfg->pin_miso,
        .sclk_io_num   = cfg->pin_sclk,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 64,
    };
    err = spi_bus_initialize(cfg->host, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;
    ESP_LOGI(TAG, "init: spi_bus_initialize ok; adding device");

    spi_device_interface_config_t dev = {
        .clock_speed_hz = cfg->clock_speed_hz,
        .mode           = 0,
        .spics_io_num   = cfg->pin_cs,
        .queue_size     = 2,
    };
    err = spi_bus_add_device(cfg->host, &dev, &s_spi);
    if (err != ESP_OK) {
        spi_bus_free(cfg->host);
        s_spi = NULL;
        return err;
    }

    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        spi_bus_remove_device(s_spi);
        spi_bus_free(cfg->host);
        s_spi = NULL;
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "up: host=%d sclk=%d mosi=%d miso=%d cs=%d drdy=%d @ %d Hz",
             (int)cfg->host, cfg->pin_sclk, cfg->pin_mosi, cfg->pin_miso,
             cfg->pin_cs, cfg->pin_drdy, cfg->clock_speed_hz);
    return ESP_OK;
}

bool cec_fpga_link_poll(void)
{
    if (s_spi == NULL) return false;
    return gpio_get_level(s_cfg.pin_drdy) != 0;
}

/* The MOSI fill byte selects the fabric's read path: 0x00 = live latest frame,
 * 0xFF = buffered burst (native-rate ring), 0x55 = continuous decimated stream
 * (the free-running FIFO), 0x33 = status (free-running native-frame counter,
 * header 0x5C, count[31:16] in code[0] / [15:0] in code[1]). The fabric latches
 * the source at CS-fall, so a mode takes effect on the transaction AFTER the one
 * carrying its command byte: send the command once, discard one frame, then
 * read. polling_transmit busy-waits the hardware instead of queueing + blocking
 * on an ISR semaphore -- a few us instead of ~64 us per 18-byte frame. */
static esp_err_t read_tx(cec_fpga_frame_t *out, uint8_t mosi_fill)
{
    if (s_spi == NULL)  return ESP_ERR_INVALID_STATE;
    if (out == NULL)    return ESP_ERR_INVALID_ARG;

    uint8_t tx[FRAME_BYTES];
    uint8_t rx[FRAME_BYTES];
    memset(tx, mosi_fill, sizeof(tx));

    spi_transaction_t t = {
        .length    = FRAME_BYTES * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t err = spi_device_polling_transmit(s_spi, &t);
    xSemaphoreGive(s_lock);
    if (err != ESP_OK) return err;

    out->header    = rx[0];
    out->header_ok = (rx[0] == CEC_FPGA_FRAME_HEADER);
    out->seq       = rx[1];
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
        out->code[ch] = (int16_t)(((uint16_t)rx[2 + 2*ch] << 8) | rx[3 + 2*ch]);
    }
    return ESP_OK;
}

esp_err_t cec_fpga_link_read(cec_fpga_frame_t *out)
{
    return read_tx(out, 0x00);
}

esp_err_t cec_fpga_link_read_buffered(cec_fpga_frame_t *out)
{
    return read_tx(out, 0xFF);
}

esp_err_t cec_fpga_link_read_stream(cec_fpga_frame_t *out)
{
    return read_tx(out, 0x55);
}

esp_err_t cec_fpga_link_read_status(cec_fpga_frame_t *out)
{
    return read_tx(out, 0x33);
}

/* 0x44 / 0x46 drive the native detector's sticky arm latch. The returned frame
 * is the prior mode's data (discarded into a scratch). */
esp_err_t cec_fpga_link_detect_arm(void)
{
    cec_fpga_frame_t scratch;
    return read_tx(&scratch, 0x44);
}

esp_err_t cec_fpga_link_detect_clear(void)
{
    cec_fpga_frame_t scratch;
    return read_tx(&scratch, 0x46);
}
