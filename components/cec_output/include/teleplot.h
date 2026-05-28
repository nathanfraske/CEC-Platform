#pragma once

#include <stdint.h>
#include "cec_state.h"

// Teleplot serial telemetry. Format: >name:time_ms:value\n
// View with the Teleplot VS Code extension or standalone app.

void teleplot_emit_float(const char *name, float value, int64_t time_ms);

// Emit a full state snapshot (both currents, raw + filtered, temp).
void teleplot_emit_state(const cec_state_t *state, bool include_raw);
