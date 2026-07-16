idf_component_register(
    SRCS "cec_fpga_link.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_spi esp_driver_gpio
)
