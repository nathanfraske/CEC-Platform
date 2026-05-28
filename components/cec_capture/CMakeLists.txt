idf_component_register(
    SRCS "cec_capture.c"
    INCLUDE_DIRS "include"
    REQUIRES cec_common cec_sensors cec_telemetry esp_adc esp_timer
)
