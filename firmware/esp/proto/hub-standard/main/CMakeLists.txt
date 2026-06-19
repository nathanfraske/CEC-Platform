idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        # CEC components
        cec_common        # cec_state.h (module-type IDs)
        cec_comms         # CAN (TWAI) + cec_telem frame pack/unpack
        cec_telemetry     # TelePlot emit (rides the USB console)
        # ESP-IDF components used directly by main.c
        esp_timer
)
