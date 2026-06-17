/*
 * INA228 driver implementation for ESP-IDF 6.x
 *
 * Register map + scaling per the TI INA228 datasheet (SBOS736). Distinct from
 * the INA226: 20-bit shunt/bus/current returned in the top 20 bits of a 24-bit
 * read, selectable ADCRANGE, a die-temp sensor, and 40-bit ENERGY/CHARGE.
 */

#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include "esp_log.h"
#include "esp_check.h"
#include "ina228.h"

static const char *TAG = "ina228";

/* Register addresses */
#define INA228_REG_CONFIG      0x00
#define INA228_REG_ADC_CONFIG  0x01
#define INA228_REG_SHUNT_CAL   0x02
#define INA228_REG_VSHUNT      0x04
#define INA228_REG_VBUS        0x05
#define INA228_REG_DIETEMP     0x06
#define INA228_REG_CURRENT     0x07
#define INA228_REG_POWER       0x08
#define INA228_REG_ENERGY      0x09
#define INA228_REG_CHARGE      0x0A
#define INA228_REG_MFR_ID      0x3E
#define INA228_REG_DEVICE_ID   0x3F

#define INA228_MFR_ID_EXPECTED  0x5449   /* "TI" */
#define INA228_DIE_ID_EXPECTED  0x228    /* DEVICE_ID[15:4] */

/* CONFIG bits */
#define INA228_CONFIG_RSTACC    (1u << 14)
#define INA228_CONFIG_ADCRANGE  (1u << 4)

/*
 * ADC_CONFIG: MODE=1111 (continuous bus+shunt+temperature), VBUSCT/VSHCT/VTCT =
 * 101 (1052 us each), AVG=000 (1 sample) -> ~3.2 ms full cycle = ~315 Hz, ample
 * for the 50 Hz detection loop; the layers do their own averaging. = 0xFB68
 * (this is also the INA228 power-on default).
 */
#define INA228_ADC_CONFIG_VALUE 0xFB68

/* Fixed LSBs (volts / celsius) */
#define INA228_VBUS_LSB_V       195.3125e-6     /* 195.3125 uV */
#define INA228_VSHUNT_LSB_R0_V  312.5e-9        /* ADCRANGE=0: 312.5 nV */
#define INA228_VSHUNT_LSB_R1_V  78.125e-9       /* ADCRANGE=1: 78.125 nV */
#define INA228_DIETEMP_LSB_C    7.8125e-3       /* 7.8125 m degC */

#define INA228_I2C_TIMEOUT_MS   100

struct ina228_dev_t {
    i2c_master_dev_handle_t dev_handle;
    float    shunt_ohms;
    float    current_lsb;     /* Amps per LSB of CURRENT (= max/2^19) */
    uint8_t  adc_range;
    float    voltage_trim;
    float    current_trim;
    uint16_t cal_value;
};

/* --- I2C primitives --- */

static esp_err_t ina228_write_reg16(struct ina228_dev_t *dev, uint8_t reg, uint16_t value)
{
    uint8_t buf[3] = { reg, (uint8_t)(value >> 8), (uint8_t)(value & 0xFF) };
    return i2c_master_transmit(dev->dev_handle, buf, sizeof(buf), INA228_I2C_TIMEOUT_MS);
}

static esp_err_t ina228_read_reg16(struct ina228_dev_t *dev, uint8_t reg, uint16_t *value)
{
    uint8_t rx[2];
    esp_err_t err = i2c_master_transmit_receive(dev->dev_handle, &reg, 1, rx, sizeof(rx),
                                                INA228_I2C_TIMEOUT_MS);
    if (err != ESP_OK) return err;
    *value = ((uint16_t)rx[0] << 8) | rx[1];
    return ESP_OK;
}

/* 24-bit register read (VSHUNT/VBUS/CURRENT/POWER). Returns the raw 24 bits. */
static esp_err_t ina228_read_reg24(struct ina228_dev_t *dev, uint8_t reg, uint32_t *raw24)
{
    uint8_t rx[3];
    esp_err_t err = i2c_master_transmit_receive(dev->dev_handle, &reg, 1, rx, sizeof(rx),
                                                INA228_I2C_TIMEOUT_MS);
    if (err != ESP_OK) return err;
    *raw24 = ((uint32_t)rx[0] << 16) | ((uint32_t)rx[1] << 8) | rx[2];
    return ESP_OK;
}

/* 40-bit register read (ENERGY/CHARGE). Returns the raw 40 bits in a uint64. */
static esp_err_t ina228_read_reg40(struct ina228_dev_t *dev, uint8_t reg, uint64_t *raw40)
{
    uint8_t rx[5];
    esp_err_t err = i2c_master_transmit_receive(dev->dev_handle, &reg, 1, rx, sizeof(rx),
                                                INA228_I2C_TIMEOUT_MS);
    if (err != ESP_OK) return err;
    *raw40 = ((uint64_t)rx[0] << 32) | ((uint64_t)rx[1] << 24) | ((uint64_t)rx[2] << 16) |
             ((uint64_t)rx[3] << 8) | rx[4];
    return ESP_OK;
}

/* Sign-extend the top 20 bits of a 24-bit register read to a signed int32. */
static int32_t ina228_signed20(uint32_t raw24)
{
    int32_t v = (int32_t)(raw24 >> 4);   /* 20-bit data in [23:4] */
    if (v & 0x80000) v -= 0x100000;
    return v;
}

/* --- Public API --- */

esp_err_t ina228_create(const ina228_config_t *config, ina228_handle_t *out_handle)
{
    ESP_RETURN_ON_FALSE(config != NULL && out_handle != NULL,
                        ESP_ERR_INVALID_ARG, TAG, "null config or out_handle");
    ESP_RETURN_ON_FALSE(config->bus_handle != NULL,
                        ESP_ERR_INVALID_ARG, TAG, "bus_handle is NULL");
    ESP_RETURN_ON_FALSE(config->shunt_ohms > 0.0f,
                        ESP_ERR_INVALID_ARG, TAG, "shunt_ohms must be positive");
    ESP_RETURN_ON_FALSE(config->max_current_a > 0.0f,
                        ESP_ERR_INVALID_ARG, TAG, "max_current_a must be positive");
    ESP_RETURN_ON_FALSE(config->voltage_trim > 0.0f && config->current_trim > 0.0f,
                        ESP_ERR_INVALID_ARG, TAG, "trims must be positive");

    struct ina228_dev_t *dev = calloc(1, sizeof(struct ina228_dev_t));
    ESP_RETURN_ON_FALSE(dev != NULL, ESP_ERR_NO_MEM, TAG, "alloc failed");

    i2c_device_config_t i2c_dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = config->i2c_addr,
        .scl_speed_hz = config->scl_speed_hz,
    };
    esp_err_t err = i2c_master_bus_add_device(config->bus_handle, &i2c_dev_cfg, &dev->dev_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_master_bus_add_device failed: %s", esp_err_to_name(err));
        free(dev);
        return err;
    }

    /* Verify manufacturer + device ID */
    uint16_t mfr_id = 0, dev_id = 0;
    err = ina228_read_reg16(dev, INA228_REG_MFR_ID, &mfr_id);
    if (err != ESP_OK) { ESP_LOGE(TAG, "MFR_ID read failed: %s", esp_err_to_name(err)); goto cleanup; }
    err = ina228_read_reg16(dev, INA228_REG_DEVICE_ID, &dev_id);
    if (err != ESP_OK) { ESP_LOGE(TAG, "DEVICE_ID read failed: %s", esp_err_to_name(err)); goto cleanup; }
    if (mfr_id != INA228_MFR_ID_EXPECTED || (dev_id >> 4) != INA228_DIE_ID_EXPECTED) {
        ESP_LOGE(TAG, "ID mismatch @ 0x%02X: MFR=0x%04X DEV=0x%04X (want MFR 0x5449, die 0x228)",
                 config->i2c_addr, mfr_id, dev_id);
        err = ESP_ERR_NOT_FOUND;
        goto cleanup;
    }

    /* CONFIG: ADCRANGE per config, everything else default (no reset/delay). */
    uint16_t cfg = config->adc_range ? INA228_CONFIG_ADCRANGE : 0;
    err = ina228_write_reg16(dev, INA228_REG_CONFIG, cfg);
    if (err != ESP_OK) { ESP_LOGE(TAG, "CONFIG write failed: %s", esp_err_to_name(err)); goto cleanup; }

    err = ina228_write_reg16(dev, INA228_REG_ADC_CONFIG, INA228_ADC_CONFIG_VALUE);
    if (err != ESP_OK) { ESP_LOGE(TAG, "ADC_CONFIG write failed: %s", esp_err_to_name(err)); goto cleanup; }

    /* SHUNT_CAL = 13107.2e6 * CURRENT_LSB * R_shunt, x4 when ADCRANGE=1.
     * CURRENT_LSB = max_current / 2^19. Must fit the 15-bit register. */
    dev->shunt_ohms   = config->shunt_ohms;
    dev->adc_range    = config->adc_range;
    dev->current_lsb  = config->max_current_a / 524288.0f;     /* 2^19 */
    dev->voltage_trim = config->voltage_trim;
    dev->current_trim = config->current_trim;
    double cal = 13107.2e6 * (double)dev->current_lsb * (double)dev->shunt_ohms;
    if (config->adc_range) cal *= 4.0;
    uint32_t cal_u = (uint32_t)(cal + 0.5);
    if (cal_u > 0x7FFF) {
        ESP_LOGE(TAG, "Computed SHUNT_CAL=%" PRIu32 " exceeds 15-bit range. Increase max_current_a.", cal_u);
        err = ESP_ERR_INVALID_ARG;
        goto cleanup;
    }
    dev->cal_value = (uint16_t)cal_u;
    err = ina228_write_reg16(dev, INA228_REG_SHUNT_CAL, dev->cal_value);
    if (err != ESP_OK) { ESP_LOGE(TAG, "SHUNT_CAL write failed: %s", esp_err_to_name(err)); goto cleanup; }

    uint16_t cal_verify = 0;
    err = ina228_read_reg16(dev, INA228_REG_SHUNT_CAL, &cal_verify);
    if (err != ESP_OK) { ESP_LOGE(TAG, "SHUNT_CAL verify read failed: %s", esp_err_to_name(err)); goto cleanup; }
    if (cal_verify != dev->cal_value) {
        ESP_LOGE(TAG, "SHUNT_CAL verify mismatch: wrote 0x%04X, read 0x%04X", dev->cal_value, cal_verify);
        err = ESP_FAIL;
        goto cleanup;
    }

    ESP_LOGI(TAG, "INA228 @ 0x%02X: shunt=%.4f ohm, max=%.1f A, range=%d, LSB=%.3f uA, CAL=0x%04X, trim V=%.4f I=%.4f",
             config->i2c_addr, dev->shunt_ohms, config->max_current_a, dev->adc_range,
             dev->current_lsb * 1e6f, dev->cal_value, dev->voltage_trim, dev->current_trim);

    *out_handle = dev;
    return ESP_OK;

cleanup:
    i2c_master_bus_rm_device(dev->dev_handle);
    free(dev);
    return err;
}

esp_err_t ina228_destroy(ina228_handle_t handle)
{
    ESP_RETURN_ON_FALSE(handle != NULL, ESP_ERR_INVALID_ARG, TAG, "null handle");
    esp_err_t err = i2c_master_bus_rm_device(handle->dev_handle);
    free(handle);
    return err;
}

esp_err_t ina228_read_bus_voltage(ina228_handle_t handle, float *out_volts)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_volts != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint32_t raw;
    esp_err_t err = ina228_read_reg24(handle, INA228_REG_VBUS, &raw);
    if (err != ESP_OK) return err;
    /* VBUS is 20-bit UNSIGNED in [23:4]. */
    *out_volts = (float)((double)(raw >> 4) * INA228_VBUS_LSB_V) * handle->voltage_trim;
    return ESP_OK;
}

esp_err_t ina228_read_current(ina228_handle_t handle, float *out_amps)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_amps != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint32_t raw;
    esp_err_t err = ina228_read_reg24(handle, INA228_REG_CURRENT, &raw);
    if (err != ESP_OK) return err;
    *out_amps = (float)ina228_signed20(raw) * handle->current_lsb * handle->current_trim;
    return ESP_OK;
}

esp_err_t ina228_read_shunt_microvolts(ina228_handle_t handle, int32_t *out_microvolts)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_microvolts != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint32_t raw;
    esp_err_t err = ina228_read_reg24(handle, INA228_REG_VSHUNT, &raw);
    if (err != ESP_OK) return err;
    double lsb_uv = (handle->adc_range ? INA228_VSHUNT_LSB_R1_V : INA228_VSHUNT_LSB_R0_V) * 1e6;
    *out_microvolts = (int32_t)((double)ina228_signed20(raw) * lsb_uv);
    return ESP_OK;
}

esp_err_t ina228_read_die_temp_c(ina228_handle_t handle, float *out_celsius)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_celsius != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint16_t raw;
    esp_err_t err = ina228_read_reg16(handle, INA228_REG_DIETEMP, &raw);
    if (err != ESP_OK) return err;
    *out_celsius = (float)((int16_t)raw) * INA228_DIETEMP_LSB_C;
    return ESP_OK;
}

esp_err_t ina228_read_energy_joules(ina228_handle_t handle, double *out_joules)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_joules != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint64_t raw;
    esp_err_t err = ina228_read_reg40(handle, INA228_REG_ENERGY, &raw);
    if (err != ESP_OK) return err;
    /* ENERGY LSB = 16 * POWER_LSB = 16 * 3.2 * CURRENT_LSB; unsigned 40-bit. */
    *out_joules = (double)raw * (16.0 * 3.2 * (double)handle->current_lsb);
    return ESP_OK;
}

esp_err_t ina228_read_charge_coulombs(ina228_handle_t handle, double *out_coulombs)
{
    ESP_RETURN_ON_FALSE(handle != NULL && out_coulombs != NULL, ESP_ERR_INVALID_ARG, TAG, "null arg");
    uint64_t raw;
    esp_err_t err = ina228_read_reg40(handle, INA228_REG_CHARGE, &raw);
    if (err != ESP_OK) return err;
    /* CHARGE is signed 40-bit; sign-extend bit 39. LSB = CURRENT_LSB. */
    int64_t s = (raw & 0x8000000000ULL) ? (int64_t)(raw | 0xFFFFFF0000000000ULL) : (int64_t)raw;
    *out_coulombs = (double)s * (double)handle->current_lsb;
    return ESP_OK;
}

esp_err_t ina228_reset_accumulators(ina228_handle_t handle)
{
    ESP_RETURN_ON_FALSE(handle != NULL, ESP_ERR_INVALID_ARG, TAG, "null handle");
    uint16_t cfg = handle->adc_range ? INA228_CONFIG_ADCRANGE : 0;
    return ina228_write_reg16(handle, INA228_REG_CONFIG, cfg | INA228_CONFIG_RSTACC);
}

float ina228_get_current_lsb(ina228_handle_t handle)
{
    return handle ? handle->current_lsb : 0.0f;
}

uint16_t ina228_get_cal_value(ina228_handle_t handle)
{
    return handle ? handle->cal_value : 0;
}
