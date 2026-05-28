idf_component_register(
    SRCS "acs758.c"
         "ntc.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_adc
)
