idf_component_register(
    SRCS "eps_main.c"
         "cec_config.c"
    INCLUDE_DIRS "."
    REQUIRES
        cec_common
        cec_sensors
        cec_filters
        cec_detection
        cec_capture
        cec_comms
        cec_output
        nvs_flash
        esp_timer
)
