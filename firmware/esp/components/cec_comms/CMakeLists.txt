idf_component_register(
    SRCS "cec_can.c" "cec_telem.c" "cec_canota.c" "cec_pokeack.c" "cec_module.c"
    INCLUDE_DIRS "include"
    REQUIRES cec_common esp_driver_twai
    # app_update + esp_partition + esp_system: the CAN-OTA receiver writes the
    # streamed image to the inactive OTA slot (esp_ota_*) and reboots.
    # esp_adc + esp_driver_gpio: the poke-and-ack DETECT read (Hub ADC) + the
    # module-side high-Z tap edge sense / Hub poke driver.
    # The Hub sender / a tap-less module links the ones it doesn't call; all small.
    PRIV_REQUIRES app_update esp_partition esp_system esp_adc esp_driver_gpio esp_timer
)
