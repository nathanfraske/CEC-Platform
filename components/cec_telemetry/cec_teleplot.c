/*
 * TelePlot output helpers.
 */

#include <stdio.h>
#include <inttypes.h>
#include "cec_teleplot.h"

void teleplot_emit(const char *name, float value)
{
    printf(">%s:%.6f\n", name, value);
}

void teleplot_emit_t(const char *name, int64_t time_ms, float value)
{
    printf(">%s:%" PRId64 ":%.6f\n", name, time_ms, value);
}

void teleplot_emit_state(const cec_state_t *state, bool include_raw)
{
    int64_t t_ms = state->timestamp_us / 1000;

    teleplot_emit_t("eps1_current", t_ms, state->current_a[0]);
    teleplot_emit_t("eps2_current", t_ms, state->current_a[1]);

    if (include_raw) {
        teleplot_emit_t("eps1_raw", t_ms, state->current_raw_a[0]);
        teleplot_emit_t("eps2_raw", t_ms, state->current_raw_a[1]);
    }

    teleplot_emit_t("board_temp", t_ms, state->board_temp_c);
    teleplot_emit_t("load_state", t_ms, (float)state->load_state);
    teleplot_emit_t("flags",      t_ms, (float)state->status_flags);
}
