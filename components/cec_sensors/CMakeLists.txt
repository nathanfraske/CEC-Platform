idf_component_register(
    SRCS "cec_adc.c"
         "acs758.c"
         "ntc.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_adc
    PRIV_REQUIRES esp_common
)
