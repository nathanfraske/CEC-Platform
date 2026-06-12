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

esp_err_t cec_fpga_link_read(cec_fpga_frame_t *out)
{
    if (s_spi == NULL)  return ESP_ERR_INVALID_STATE;
    if (out == NULL)    return ESP_ERR_INVALID_ARG;

    uint8_t tx[FRAME_BYTES] = {0};
    uint8_t rx[FRAME_BYTES];

    spi_transaction_t t = {
        .length    = FRAME_BYTES * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t err = spi_device_transmit(s_spi, &t);
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
