#include "teleplot.h"
#include <stdio.h>

void teleplot_emit_float(const char *name, float value, int64_t time_ms)
{
    printf(">%s:%lld:%.3f\n", name, time_ms, value);
}

void teleplot_emit_state(const cec_state_t *state, bool include_raw)
{
    int64_t t_ms = state->timestamp_us / 1000;

    teleplot_emit_float("eps1_current", state->current_a[0], t_ms);
    teleplot_emit_float("eps2_current", state->current_a[1], t_ms);

    if (include_raw) {
        teleplot_emit_float("eps1_raw", state->current_raw_a[0], t_ms);
        teleplot_emit_float("eps2_raw", state->current_raw_a[1], t_ms);
    }

    teleplot_emit_float("board_temp", state->board_temp_c, t_ms);
    teleplot_emit_float("load_state", (float)state->load_state, t_ms);
    teleplot_emit_float("flags", (float)state->status_flags, t_ms);
}
