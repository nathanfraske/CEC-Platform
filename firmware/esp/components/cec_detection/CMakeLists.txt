idf_component_register(
    SRCS
        "cec_state.c"
        "cec_layer1.c"
        "cec_layer2.c"
        "cec_layer3.c"
        "cec_swing.c"
        "cec_classifier.c"
        "cec_detection.c"
    INCLUDE_DIRS "include"
    REQUIRES
        cec_common
        cec_filters
)
