#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#define CEC_NUM_CABLES 2

// Module identity
#define CEC_MODULE_TYPE_EPS 0x02

// Status flag bits
#define CEC_FLAG_OVERCURRENT  (1 << 0)
#define CEC_FLAG_SWING        (1 << 1)
#define CEC_FLAG_FAULT        (1 << 2)
#define CEC_FLAG_DROPOUT      (1 << 3)

// Operating state from the classifier
typedef enum {
    CEC_STATE_IDLE = 0,
    CEC_STATE_LIGHT,
    CEC_STATE_MODERATE,
    CEC_STATE_HEAVY,
    CEC_STATE_TRANSIENT,
} cec_op_state_t;

// Shared measurement state. sample_task is the only writer.
// Readers (output, comms) take the mutex briefly to snapshot.
typedef struct {
    float current_a[CEC_NUM_CABLES];      // filtered current per cable (amps)
    float current_raw_a[CEC_NUM_CABLES];  // unfiltered current (amps)
    float board_temp_c;                   // NTC board temperature
    cec_op_state_t op_state;              // classifier output
    uint8_t status_flags;                 // CEC_FLAG_* bits
    int64_t timestamp_us;                 // esp_timer time of last update
    SemaphoreHandle_t mutex;
} cec_state_t;

// Runtime configuration (persisted in NVS)
typedef struct {
    uint8_t module_id;          // instance ID for multi-module setups
    float supply_voltage;       // measured ACS758 Vcc (ratiometric reference)
    float oc_threshold_a;       // overcurrent threshold per cable
    float ema_alpha;            // filter responsiveness
    bool output_raw;            // telemetry mode: raw vs filtered
} cec_config_t;

// Defaults (used when NVS is empty)
#define CEC_DEFAULT_SUPPLY_V    4.4f    // measured: USB Vbus through dev board diode
#define CEC_DEFAULT_OC_A        35.0f   // above normal EPS load, below sensor limit
#define CEC_DEFAULT_EMA_ALPHA   0.2f
#define CEC_DEFAULT_MODULE_ID   1

// Hardware presence flag. The CAN transceiver lives on the daughterboard;
// while it isn't attached the TWAI driver must not be installed (RX pin
// would float and the controller would log bus errors). Flip to 1 when the
// daughterboard is connected.
#define CEC_CAN_ENABLED         0
