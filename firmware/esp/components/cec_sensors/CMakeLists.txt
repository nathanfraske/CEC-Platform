# Per-app sensor selection via Kconfig (CEC_SENSOR_*); cec_adc always
# builds, with its backend chosen by CEC_ADC_BACKEND_* inside the source.
idf_component_register(
    SRCS "cec_adc.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_adc
        esp_driver_i2c
    PRIV_REQUIRES esp_common
)

if(CONFIG_CEC_SENSOR_ACS712)
    target_sources(${COMPONENT_LIB} PRIVATE "acs712.c")
endif()
if(CONFIG_CEC_SENSOR_ACS758)
    target_sources(${COMPONENT_LIB} PRIVATE "acs758.c")
endif()
if(CONFIG_CEC_SENSOR_INA226)
    target_sources(${COMPONENT_LIB} PRIVATE "ina226.c")
endif()
if(CONFIG_CEC_SENSOR_INA228)
    target_sources(${COMPONENT_LIB} PRIVATE "ina228.c")
endif()
# One thermistor source serves both the thermistor- and ntc-named APIs.
if(CONFIG_CEC_SENSOR_THERMISTOR OR CONFIG_CEC_SENSOR_NTC)
    target_sources(${COMPONENT_LIB} PRIVATE "thermistor.c")
endif()
