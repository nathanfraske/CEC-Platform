/* 12vhpwr-proto ESP32-P4 bring-up v0.
 * SPI master to the GW5A: poll DRDY, pull an 18-byte frame
 * (0xA5, seq, V1..V8 big-endian), print codes and volts.
 * Pins per doc section 6.3 / 10. License: Apache-2.0 (CEC-Platform). */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"

#define PIN_SCLK  20   /* P1-13 -> field T13 (F2)  */
#define PIN_MOSI  21   /* P1-15 -> field T14 (B2)  */
#define PIN_MISO  22   /* P1-16 -> field B14 (C2)  */
#define PIN_CS    23   /* P1-7  -> field B13 (F1)  */
#define PIN_DRDY  24   /* P1-18 <- field B12 (A1)  */

#define FRAME_BYTES 18
#define LSB_VOLTS   (5.0 / 32768.0)   /* +/-5 V range: 152.59 uV per LSB */

void app_main(void)
{
    gpio_config_t drdy = {
        .pin_bit_mask = 1ULL << PIN_DRDY,
        .mode         = GPIO_MODE_INPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&drdy));

    spi_bus_config_t bus = {
        .mosi_io_num   = PIN_MOSI,
        .miso_io_num   = PIN_MISO,
        .sclk_io_num   = PIN_SCLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 64,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));

    spi_device_interface_config_t dev = {
        .clock_speed_hz = 4 * 1000 * 1000,   /* 4 MHz: < 5 MHz oversample rec */
        .mode           = 0,
        .spics_io_num   = PIN_CS,
        .queue_size     = 2,
    };
    spi_device_handle_t spi;
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &spi));

    uint8_t tx[FRAME_BYTES] = {0};
    uint8_t rx[FRAME_BYTES];

    printf("12vhpwr-proto v0: waiting on DRDY\n");
    while (1) {
        if (!gpio_get_level(PIN_DRDY)) {
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }
        spi_transaction_t t = {
            .length    = FRAME_BYTES * 8,
            .tx_buffer = tx,
            .rx_buffer = rx,
        };
        ESP_ERROR_CHECK(spi_device_transmit(spi, &t));

        if (rx[0] != 0xA5) {
            printf("bad header 0x%02x (alignment?)\n", rx[0]);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        printf("seq %3u |", rx[1]);
        for (int ch = 0; ch < 8; ch++) {
            int16_t code = (int16_t)(((uint16_t)rx[2 + 2*ch] << 8) | rx[3 + 2*ch]);
            printf(" V%d %+6d (%+8.4f V)", ch + 1, code, code * LSB_VOLTS);
        }
        printf("\n");
        vTaskDelay(pdMS_TO_TICKS(200));   /* ~5 Hz console; FPGA keeps pacing */
    }
}
