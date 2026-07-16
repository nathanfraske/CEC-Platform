idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        cec_common        # module-type IDs
        cec_comms         # cec_module runtime (CAN + OTA + poke-ack + telemetry)
        esp_timer
        # bring-up: add esp_driver_i2c (INA238 reads) + esp_driver_gpio (the
        # §6.13 per-cable DET latch + threshold PWM).
)
