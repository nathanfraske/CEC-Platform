cmake_minimum_required(VERSION 3.16)

set(PROJECT_NAME cec_12vhpwr_standard)

# Shared CEC components (firmware/esp/components) become visible via this line.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(${PROJECT_NAME})
