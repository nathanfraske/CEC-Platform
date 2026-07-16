idf_component_register(
    SRCS "cec_teleplot.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_uart
    PRIV_REQUIRES esp_common
)
