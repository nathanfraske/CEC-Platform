/*
 * INA228 driver for ESP-IDF 6.x
 *
 * The 24-pin BENCH UNITS' sensing: one INA228 per rail (12V/5V/3V3/5VSB),
 * each giving BOTH bus voltage and current over I2C. Handle-based API mirroring
 * ina226.h so multiple instances share one bus.
 *
 * SCOPE (owner direction 2026-07-15): this driver serves the current bench
 * units only — the 24-pin alpha/rev2 boards, frozen artifacts populated with
 * the INA228. The production part going forward is the INA238 (spec v1.5.0:
 * 24-pin rev3+; EPS/PCIe were always INA238 per cable). Same VSSOP-10 land
 * and family register map, but 16-bit ADC, no energy/charge accumulators
 * (energy integrates in firmware, OQ-13) — a separate ina238 driver, not an
 * extension of this one. Keep this driver working; don't grow it.
 *
 * The INA228 is NOT register-compatible with the INA226 -- it is the
 * INA228/237/238 family map: a 20-bit ADC (shunt/bus/current returned in the top
 * 20 bits of a 24-bit read), a selectable shunt full-scale (ADCRANGE), an
 * on-die temperature sensor, and 40-bit ENERGY/CHARGE accumulators. CURRENT_LSB
 * is max_current/2^19 (vs the INA226's /2^15), so resolution is much finer.
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque handle for an INA228 device. */
typedef struct ina228_dev_t* ina228_handle_t;

/* Configuration for an INA228 instance. */
typedef struct {
    i2c_master_bus_handle_t bus_handle;   /* I2C bus this device sits on */
    uint8_t i2c_addr;                     /* 7-bit I2C address (0x40-0x4F) */
    float shunt_ohms;                     /* Physical shunt resistor value */
    float max_current_a;                  /* Target max current; sets CURRENT_LSB = max/2^19 */
    uint8_t adc_range;                    /* 0 = +/-163.84 mV shunt FS, 1 = +/-40.96 mV (4x finer) */
    uint32_t scl_speed_hz;                /* Per-device SCL speed (typically 400000) */
    float voltage_trim;                   /* Multiplier applied to bus voltage (1.0 = raw) */
    float current_trim;                   /* Multiplier applied to current (1.0 = raw) */
} ina228_config_t;

/* Default configuration block. Caller overrides fields they want changed. */
#define INA228_CONFIG_DEFAULT() (ina228_config_t){     \
    .bus_handle = NULL,                                 \
    .i2c_addr = 0x40,                                   \
    .shunt_ohms = 0.002f,                               \
    .max_current_a = 20.0f,                             \
    .adc_range = 1,                                     \
    .scl_speed_hz = 400000,                             \
    .voltage_trim = 1.0f,                               \
    .current_trim = 1.0f,                               \
}

/*
 * Initialize an INA228 on the bus.
 *
 * Validates MANUFACTURER_ID (0x5449) and DEVICE_ID (die 0x228), sets CONFIG
 * (ADCRANGE) and ADC_CONFIG (continuous bus+shunt+temp), and programs SHUNT_CAL
 * from shunt_ohms / max_current_a / adc_range.
 *
 * Returns ESP_OK, ESP_ERR_NOT_FOUND on an ID mismatch, ESP_ERR_INVALID_ARG if
 * the computed SHUNT_CAL exceeds the 15-bit register (raise max_current_a), or
 * the underlying i2c_master_* error.
 */
esp_err_t ina228_create(const ina228_config_t *config, ina228_handle_t *out_handle);

/* Release an INA228 and remove it from the bus. */
esp_err_t ina228_destroy(ina228_handle_t handle);

/*
 * Read the bus voltage in volts (trim applied). VBUS LSB = 195.3125 uV,
 * 20-bit unsigned, 0..85 V range.
 */
esp_err_t ina228_read_bus_voltage(ina228_handle_t handle, float *out_volts);

/*
 * Read the current in amps with the calibration applied:
 *   amps = gain * raw + offset
 * (gain = current_trim, offset = 0 until a 2-point cal sets it). 20-bit
 * signed; sign reflects direction. Resolution = CURRENT_LSB = max_current_a/2^19.
 */
esp_err_t ina228_read_current(ina228_handle_t handle, float *out_amps);

/*
 * Read the RAW current in amps with NO gain/offset applied -- the reference
 * reading used when capturing a calibration point against a known load.
 */
esp_err_t ina228_read_current_uncal(ina228_handle_t handle, float *out_amps);

/*
 * Calibration setters/getters (host- or CLI-driven; persisted by the app).
 * Current cal is gain + offset; voltage cal is gain only (the INA228 bus
 * offset is negligible). Defaults: gain 1.0, offset 0.0 (= raw reading).
 */
void  ina228_set_current_cal(ina228_handle_t handle, float gain, float offset_a);
void  ina228_set_voltage_trim(ina228_handle_t handle, float gain);
float ina228_get_voltage_trim(ina228_handle_t handle);
float ina228_get_current_trim(ina228_handle_t handle);
float ina228_get_current_offset(ina228_handle_t handle);

/*
 * Read the shunt voltage directly in microvolts (untrimmed). 20-bit signed;
 * LSB = 312.5 nV (ADCRANGE=0) or 78.125 nV (ADCRANGE=1). Diagnostic:
 * current = shunt_uV / shunt_ohms.
 */
esp_err_t ina228_read_shunt_microvolts(ina228_handle_t handle, int32_t *out_microvolts);

/*
 * Read the on-die temperature in degrees C. DIETEMP is 16-bit signed,
 * LSB = 7.8125 m degC. (The INA226 has no equivalent.)
 */
esp_err_t ina228_read_die_temp_c(ina228_handle_t handle, float *out_celsius);

/*
 * Read the accumulated ENERGY in joules (unsigned 40-bit accumulator).
 * ENERGY LSB = 16 * 3.2 * CURRENT_LSB. Reset with ina228_reset_accumulators().
 */
esp_err_t ina228_read_energy_joules(ina228_handle_t handle, double *out_joules);

/*
 * Read the accumulated CHARGE in coulombs (signed 40-bit accumulator).
 * CHARGE LSB = CURRENT_LSB.
 */
esp_err_t ina228_read_charge_coulombs(ina228_handle_t handle, double *out_coulombs);

/* Reset the ENERGY and CHARGE accumulators (CONFIG.RSTACC). */
esp_err_t ina228_reset_accumulators(ina228_handle_t handle);

/* Get the actual programmed CURRENT_LSB in amps (informational). */
float ina228_get_current_lsb(ina228_handle_t handle);

/* Get the programmed SHUNT_CAL register value (informational, boot logging). */
uint16_t ina228_get_cal_value(ina228_handle_t handle);

#ifdef __cplusplus
}
#endif
