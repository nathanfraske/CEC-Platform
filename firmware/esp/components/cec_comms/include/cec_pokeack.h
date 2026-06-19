/*
 * DETECT poke-and-ack — port-to-identity binding (spec §2.3 v2.6, OQ-28).
 *
 * The DETECT line (RJ-45 pin 8) carries a precision resistor to GND on each
 * module; the Hub reads it through its own 10 kΩ pull-up to 3.3 V as a
 * divider, which encodes the module's COMM CLASS (static, always readable).
 *
 * Poke-and-ack binds a CAN-enumerated identity to its physical PORT without
 * putting identity on the pin: the Hub briefly PERTURBS ("pokes") one port's
 * DETECT line; a module with a high-Z pin-8 tap to a GPIO senses the edge and
 * ACKs over CAN (a MOVED frame carrying its identity); the Hub, knowing which
 * port it poked, binds that serial to that port. Identity stays on CAN, so the
 * pin spends no namespace.
 *
 * SAFE FALLBACK (required): a module with NO tap (e.g. the 24-pin, whose
 * MINI-1 GPIO pads are under the shroud — no tap can be added) simply never
 * acks. The Hub times out and treats the port as a LEGACY known-but-unbound
 * module — still known from CAN + read for comm class from the static divider,
 * just not poke-bound. Absence of an ack is a normal state, never an error.
 *
 * OQ-28 leaves the sense METHOD open; this implements the spec-favored DIGITAL
 * EDGE read (the module only needs to see its line moved — the Hub measures
 * the analog value), which costs the module no ADC channel.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Module->Hub ack: "my DETECT line was perturbed." payload:
 *   [0]=module_type  [1]=instance  [2]=nonce(echoed)  [3..7]=0 */
#define CEC_POKEACK_ID_MOVED   0x120

/* Poke pattern — Hub and module MUST agree. The Hub drives this many rising
 * edges; the module acks if it sees at least MIN_EDGES within WINDOW_MS. */
#define CEC_POKEACK_PULSES      4
#define CEC_POKEACK_PULSE_MS    3
#define CEC_POKEACK_WINDOW_MS   60
#define CEC_POKEACK_MIN_EDGES   3

/* Comm class from the DETECT divider (10 kΩ pull-up, 3.3 V), spec §2.3. */
typedef enum {
    CEC_DETECT_FAULT = 0,      /* short, ~0 V */
    CEC_DETECT_CAN_ONLY,       /* 2.2 kΩ → ~0.60 V */
    CEC_DETECT_CAN_RS485,      /* 4.7 kΩ → ~1.06 V */
    CEC_DETECT_CAN_100BT1,     /* 10 kΩ → ~1.65 V */
    CEC_DETECT_RESERVED_22K,   /* 22 kΩ → ~2.27 V */
    CEC_DETECT_RESERVED_47K,   /* 47 kΩ → ~2.72 V */
    CEC_DETECT_ABSENT,         /* open, ~3.3 V (no module) */
} cec_detect_class_t;

const char *cec_detect_class_name(cec_detect_class_t c);

/* ---------------- module (responder) side ---------------- */

#define CEC_POKEACK_TAP_NONE   (-1)

/* Start the poke responder. If tap_gpio < 0 the board has no pin-8 sense tap
 * → INERT (safe fallback / legacy mode): it logs and never acks. Otherwise it
 * watches the tap GPIO for the Hub's poke pattern and acks with a MOVED frame.
 * Requires CAN up (can_init) when a tap is present. */
esp_err_t cec_pokeack_responder_start(int tap_gpio, uint8_t module_type, uint8_t instance);

/* ---------------- Hub side ---------------- */

/* Set up the DETECT ADC read (adc_gpio, an ADC1 pin) + the poke driver
 * (poke_gpio). The 10 kΩ pull-up from 3.3 V to the DETECT node is EXTERNAL. */
esp_err_t cec_pokeack_hub_init(int adc_gpio, int poke_gpio);

/* Read the static DETECT divider and classify it. If out_mv != NULL it gets
 * the measured millivolts. Call on a quiet line (not mid-poke). */
cec_detect_class_t cec_pokeack_read_class(int *out_mv);

/* Poke the line, then wait up to timeout_ms for a module MOVED ack. Returns
 * true and fills module_type/instance if a module acked (bind it to this
 * port); false on no ack within the window (safe fallback → legacy/unbound).
 * The CALLER must own can_receive() for the duration (suspend any RX drain). */
bool cec_pokeack_poke_and_bind(uint32_t timeout_ms, uint8_t *module_type, uint8_t *instance);

#ifdef __cplusplus
}
#endif
