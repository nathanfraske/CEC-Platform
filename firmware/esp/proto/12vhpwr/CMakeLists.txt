cmake_minimum_required(VERSION 3.16)
# Shared CEC components become visible to every app via this line; add
# component dirs under firmware/esp/components as they appear.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(cec_12vhpwr_proto)
