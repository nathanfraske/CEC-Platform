idf_component_register(
    SRCS "can.c"
    INCLUDE_DIRS "include"
    REQUIRES cec_common esp_driver_twai
)
