/*
 * Shared CEC firmware types.
 *
 * This header is part of the cec_common component (vs. any specific
 * detection layer) so callers can use the enums without dragging in
 * the full detector machinery — Layer 1 needs cec_severity_t, the
 * burst-capture engine wants cec_state_t for the pre-trigger sample
 * shape, the serial CLI surfaces both in `status` output, etc.
 * Implementations of the declared helpers live in the component that
 * owns the corresponding algorithm.
 *
 * MERGED HEADER (firmware consolidation): the union of the 24-pin and
 * eps app headers. Existing enumerator NUMERIC VALUES are frozen — the
 * cec_nvs blob schema persists them (Layer 3 profiles are indexed by
 * cec_state_t; settings/config blobs carry flag bytes) — so new
 * enumerators are only ever APPENDED before the _COUNT sentinel of an
 * existing enum, never renumbered.
 *
 * NAME-CONFLICT RESOLUTION (recorded in firmware/FOLLOWUPS.md and the
 * consolidation PR): both source trees used the name `cec_state_t` for
 * DIFFERENT things — the 24-pin PSU-state enum below vs. the eps
 * shared-measurement struct. The enum keeps the name (it is the
 * NVS-persisted one, and the older lineage); the eps struct is renamed
 * `cec_shared_state_t`, a pure compile-time type rename with zero
 * persisted-byte impact.
 *
 * The 24-pin module's state classifier maps (v_12v, v_5vsb, p_total)
 * to a coarse PSU operating state with hysteresis on the power-defined
 * transitions:
 *
 *   OFF      - 5VSB below 1.0 V (PSU unplugged / completely off)
 *   STANDBY  - 5VSB up, 12V below 10.5 V (PSU plugged in, main rails off)
 *   IDLE     - main rails up, p_total < 40 W (entry) / < 32 W (exit hysteresis)
 *   ACTIVE   - p_total < 150 W (entry) / < 130 W (exit hysteresis)
 *   PEAK     - p_total >= 150 W (entry) / >= 130 W (exit hysteresis)
 *
 * Note this diverges slightly from v0.5.9 in the OFF/STANDBY split:
 * v0.5.9 used 12V alone, which conflated "PSU unplugged" with "PSU
 * plugged in, switched off". Using 5VSB as the OFF discriminant lets
 * the two be distinguished.
 *
 * Power is the sum of main-rail products: V_12V*I_12V + V_5V*I_5V +
 * V_3V3*I_3V3. The 5VSB rail is not included by design (matches v0.5.9).
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- PSU state (24-pin module) ---- */

typedef enum {
    CEC_STATE_OFF = 0,
    CEC_STATE_STANDBY,
    CEC_STATE_IDLE,
    CEC_STATE_ACTIVE,
    CEC_STATE_PEAK,
    CEC_STATE_COUNT
} cec_state_t;

/*
 * Human-readable state name. Always returns a valid pointer.
 */
const char *cec_state_name(cec_state_t s);

/*
 * Classify the next state given the latest filtered readings and the
 * caller's current state. Hysteresis is applied to the IDLE<->ACTIVE
 * and ACTIVE<->PEAK transitions.
 */
cec_state_t cec_state_classify(float v_12v, float v_5vsb, float p_total,
                               cec_state_t current);

/* ---- Detection severity (shared by Layer 1 and the CLI) ---- */

typedef enum {
    CEC_SEV_NONE = 0,
    CEC_SEV_WARNING,
    CEC_SEV_CRITICAL,
} cec_severity_t;

/*
 * Human-readable severity name. Always returns a valid pointer.
 * Implementation lives in the detection component alongside Layer 1.
 */
const char *cec_severity_name(cec_severity_t s);

/* ---- Per-cable types (eps module) ---- */

#define CEC_NUM_CABLES 2

/* Module identity */
#define CEC_MODULE_TYPE_EPS 0x02
#define CEC_MODULE_TYPE_ATX24 0x01   /* 24-pin ATX interposer (4 rails) */
#define CEC_MODULE_TYPE_PCIE 0x03    /* PCIe 8-pin interposer (per-cable, 2-3) */
#define CEC_MODULE_TYPE_12VHPWR 0x04 /* 12VHPWR Standard (6 per-pin -> ADC) */

/* Status flag bits */
#define CEC_FLAG_OVERCURRENT  (1 << 0)
#define CEC_FLAG_SWING        (1 << 1)
#define CEC_FLAG_FAULT        (1 << 2)
#define CEC_FLAG_DROPOUT      (1 << 3)

/* Per-cable load classifier output. The 24-pin module's cec_state_t
 * (above) names the whole-PSU operating mode (OFF/STANDBY/...); EPS is
 * per-cable, so this enum is deliberately named differently. */
typedef enum {
    CEC_LOAD_IDLE = 0,
    CEC_LOAD_LIGHT,
    CEC_LOAD_MODERATE,
    CEC_LOAD_HEAVY,
    CEC_LOAD_TRANSIENT,
    CEC_LOAD_COUNT,
} cec_load_state_t;

/* Shared measurement state (eps app data model; renamed from the eps
 * tree's `cec_state_t`, see the header comment). sample_task is the
 * only writer. Readers (output, comms) take the mutex briefly to
 * snapshot. */
typedef struct {
    float current_a[CEC_NUM_CABLES];      /* filtered current per cable (amps) */
    float current_raw_a[CEC_NUM_CABLES];  /* unfiltered current (amps) */
    float bus_voltage_v;                  /* 12V rail measured via divider */
    float board_temp_c;                   /* NTC board temperature */
    cec_load_state_t load_state;          /* per-cable load classifier output */
    uint8_t status_flags;                 /* CEC_FLAG_* bits */
    int64_t timestamp_us;                 /* esp_timer time of last update */
    SemaphoreHandle_t mutex;
} cec_shared_state_t;

/* Runtime configuration (persisted in NVS by the eps cec_config layer) */
typedef struct {
    uint8_t module_id;          /* instance ID for multi-module setups */
    float supply_voltage;       /* measured ACS758 Vcc (ratiometric reference) */
    float oc_threshold_a;       /* overcurrent threshold per cable */
    float ema_alpha;            /* filter responsiveness */
    bool output_raw;            /* telemetry mode: raw vs filtered */
} cec_config_t;

/* Defaults (used when NVS is empty) */
#define CEC_DEFAULT_SUPPLY_V    4.4f    /* measured: USB Vbus through dev board diode */
#define CEC_DEFAULT_OC_A        35.0f   /* above normal EPS load, below sensor limit */
#define CEC_DEFAULT_EMA_ALPHA   0.2f
#define CEC_DEFAULT_MODULE_ID   1

/* Hardware presence flag. Set to 1 once the daughterboard with the
 * CAN transceiver is attached; the esp_twai node-handle code in
 * cec_comms/cec_can.c becomes active. NOTE: with this enabled the
 * build needs ESP-IDF >= 6.0 (esp_driver_twai APIs; see versions.env). */
#define CEC_CAN_ENABLED         1

#ifdef __cplusplus
}
#endif
