cmake_minimum_required(VERSION 3.16)

# Project name; this becomes the binary filename
set(PROJECT_NAME cec_24pin)

# Pull in ESP-IDF build system
# Shared CEC components (firmware/esp/components) become visible to this
# app via this line; app-local components/ still take precedence by name.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(${PROJECT_NAME})
