idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        cec_common        # module-type IDs
        cec_comms         # cec_module runtime (CAN + OTA + poke-ack + telemetry)
        esp_timer
        # bring-up: add esp_adc + esp_driver_gpio when wiring the real INA240
        # ADC reads + the §6.10 ALERT/threshold capture trigger.
)
