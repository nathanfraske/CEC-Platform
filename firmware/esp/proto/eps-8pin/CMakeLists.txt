# CEC EPS Module Firmware
# ESP-IDF top-level project file
cmake_minimum_required(VERSION 3.16)

# Shared CEC components (firmware/esp/components) become visible to this
# app via this line; app-local components/ still take precedence by name.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(cec_eps)
