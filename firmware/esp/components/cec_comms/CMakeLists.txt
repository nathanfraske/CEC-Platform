idf_component_register(
    SRCS "cec_can.c" "cec_telem.c" "cec_canota.c"
    INCLUDE_DIRS "include"
    REQUIRES cec_common esp_driver_twai
    # app_update + esp_partition + esp_system: the CAN-OTA receiver writes the
    # streamed image to the inactive OTA slot (esp_ota_*) and reboots. The Hub
    # sender side links them too (unused there); all are small.
    PRIV_REQUIRES app_update esp_partition esp_system
)
