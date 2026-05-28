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
        cec_telemetry
        cec_nvs
        esp_timer
)
