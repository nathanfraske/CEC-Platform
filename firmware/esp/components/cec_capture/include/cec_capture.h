/*
 * Burst capture engine — shared, config-driven (firmware consolidation,
 * Phase D). The eps implementation is the canonical core: dynamic
 * PSRAM buffers, a Core-1 dispatcher task, trigger/cooldown/busy
 * semantics, index-snapshotting, and the chunked TelePlot dump with
 * in-loop yields and a priority drop. Everything app-specific rides in
 * cec_capture_config_t:
 *
 *   - SAMPLE SHAPES are opaque (void* + size): each app defines its own
 *     pre-trigger and HS row structs (the 24-pin's 9-field rail set,
 *     the eps 2-cable set) and renders them itself, so each app's
 *     >BURST dump stays byte-identical to its pre-merge output.
 *   - HS ACQUISITION is selected per app:
 *       CEC_CAPTURE_HS_ADC_CONTINUOUS — the eps path: borrow ADC1 via
 *         the adc_acquire/adc_release hooks, run adc_continuous DMA on
 *         the configured channel pattern, feed each calibrated reading
 *         to hs_on_reading and stamp completed rows via hs_row_finish
 *         (synthesized, evenly-spaced timestamps).
 *       CEC_CAPTURE_HS_CALLBACK — the 24-pin path: pace hs_fill at
 *         hs_sample_rate_hz on the dispatcher task (tick-based when the
 *         FreeRTOS tick is fine enough, else the legacy timer spin) with
 *         real esp_timer timestamps and access to the previous row (for
 *         the 24-pin's zero-artifact carry-forward).
 *   - OUTPUT goes through the config's write callback (the apps pass
 *     teleplot_write_raw), so the engine has no transport dependency.
 *
 * Dump envelope (identical in both lineages):
 *   >BURST_BEGIN:<reason>:<n_pre>_normal+<n_hs>_hs:<state-token>
 *   >BURST_ANNOTATION:<text>            (only if trigger_with_text)
 *   <render_pre output per pre-trigger sample, oldest -> newest>
 *   <render_hs output per HS row, decimated by hs_dump_decimation>
 *   >BURST_END
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Trigger sources. Names line up with v0.5.9; the enum is the shared
 * cross-module vocabulary (not every source is wired on every app). */
typedef enum {
    CEC_TRIG_NONE = 0,
    CEC_TRIG_MANUAL,
    CEC_TRIG_STATIC_WARN,
    CEC_TRIG_STATIC_CRIT,
    CEC_TRIG_TRANSIENT,
    CEC_TRIG_ANOMALY,
    CEC_TRIG_STATE_CHANGE,
    CEC_TRIG_SHUTDOWN,
    CEC_TRIG_POWER_SWING,
    CEC_TRIG_CURRENT_SWING,
    CEC_TRIG_COUNT,
} cec_trigger_t;

/* Engine-side ceiling on the adc_continuous channel pattern. */
#define CEC_CAPTURE_MAX_CHANNELS 8

/* Per-channel conversion params used by the DMA HS path's consumer
 * hooks. The engine itself only uses .channel (pattern + routing);
 * the conversion fields are passed through to the app's hs_on_reading
 * via cec_capture_channel_get and kept current by
 * cec_capture_update_channel after runtime calibration changes. */
typedef struct {
    adc_channel_t channel;
    float         divider_gain;      /* recover chip voltage from ADC pin */
    float         quiescent_v;       /* chip output at 0 A */
    float         sensitivity_v_a;   /* V/A (ratiometric with Vcc) */
    float         zero_offset_v;     /* per-unit zero trim */
} cec_capture_channel_t;

/* HS acquisition source. */
typedef enum {
    CEC_CAPTURE_HS_ADC_CONTINUOUS = 0,   /* eps lineage: adc_continuous DMA */
    CEC_CAPTURE_HS_CALLBACK,             /* 24-pin lineage: paced fill callback */
} cec_capture_hs_source_t;

/* ---- App hooks -------------------------------------------------------- */

/* Transport for every dump byte (apps pass teleplot_write_raw). */
typedef void (*cec_capture_write_fn_t)(const char *buf, size_t n);

/* Render ONE pre-trigger sample into buf (snprintf semantics: return
 * would-be length; the engine writes min(ret, cap-1) bytes). */
typedef int (*cec_capture_render_pre_fn_t)(const void *sample,
                                           char *buf, size_t cap);

/* Render ONE HS row. hs_start_us is the esp_timer time HS capture
 * began (the 24-pin derives absolute-ms stamps from it; eps ignores it
 * and prints the row's own us-offset). */
typedef int (*cec_capture_render_hs_fn_t)(const void *row,
                                          int64_t hs_start_us,
                                          char *buf, size_t cap);

/* Render the <state-token> field of the BURST_BEGIN line. Optional:
 * NULL emits the eps literal "cap". */
typedef void (*cec_capture_state_token_fn_t)(char *buf, size_t cap);

/* DMA mode: consume one calibrated reading (chan_idx is the index into
 * cfg->channels[]) into the row being assembled. */
typedef void (*cec_capture_hs_on_reading_fn_t)(void *row, int chan_idx, int mv);

/* DMA mode: a row is complete; stamp its (synthesized, evenly-spaced)
 * us-offset into the app's row struct. */
typedef void (*cec_capture_hs_row_finish_fn_t)(void *row, uint32_t ts_us_offset);

/* DMA mode: hand the ADC unit over / back around the capture window
 * (apps pass cec_adc_pause / cec_adc_resume). Optional: NULL skips. */
typedef esp_err_t (*cec_capture_adc_acquire_fn_t)(void);
typedef esp_err_t (*cec_capture_adc_release_fn_t)(void);

/* DMA mode: calibration handle for raw->mV (apps pass
 * cec_adc_get_cali_handle). Optional: NULL falls back to nominal
 * 3100/4095 scaling. */
typedef adc_cali_handle_t (*cec_capture_get_cali_fn_t)(void);

/* CALLBACK mode: fill one HS row. ts_us_offset is the real elapsed time
 * since capture start; prev_row is the previous filled row (NULL on the
 * first), for carry-forward-style mitigations. The app writes the
 * timestamp into its own struct field. */
typedef void (*cec_capture_hs_fill_fn_t)(void *row, const void *prev_row,
                                         uint32_t ts_us_offset);

/* ---- Init-time configuration. Buffers are allocated in PSRAM. -------- */
typedef struct {
    /* Shapes + capacities. Capacities are SAMPLES; sizes are BYTES of
     * the app's structs. HS capacity = hs_sample_rate_hz * hs_duration_ms
     * / 1000. */
    int    pre_trigger_capacity;
    size_t pre_sample_size;
    size_t hs_row_size;
    int    hs_sample_rate_hz;       /* per-channel HS rate */
    int    hs_duration_ms;          /* HS capture window length */
    int    cooldown_ms;             /* min gap between bursts; 0 = none */

    /* Emit every Nth HS row to the dump (1 = no decimation). Capture
     * itself stays at full rate; this only thins the dump. */
    int    hs_dump_decimation;

    /* true (eps lineage): snapshot the pre-ring indices at trigger time
     * so the dump reflects the state when the trigger fired. false
     * (24-pin lineage): compute them at dump time, so pushes during the
     * HS window are included. */
    bool   snapshot_pre_at_trigger;

    /* Dispatcher task stack in bytes; 0 = engine default (6144). The
     * render callbacks run on this task. */
    int    dispatch_task_stack;

    /* Output + render hooks (write, render_pre, render_hs required). */
    cec_capture_write_fn_t        write;
    cec_capture_render_pre_fn_t   render_pre;
    cec_capture_render_hs_fn_t    render_hs;
    cec_capture_state_token_fn_t  state_token;     /* optional */

    /* HS source + its hooks. */
    cec_capture_hs_source_t hs_source;

    /* CEC_CAPTURE_HS_ADC_CONTINUOUS: */
    int                    n_channels;
    cec_capture_channel_t  channels[CEC_CAPTURE_MAX_CHANNELS];
    cec_capture_hs_on_reading_fn_t hs_on_reading;
    cec_capture_hs_row_finish_fn_t hs_row_finish;
    cec_capture_adc_acquire_fn_t   adc_acquire;    /* optional */
    cec_capture_adc_release_fn_t   adc_release;    /* optional */
    cec_capture_get_cali_fn_t      get_cali;       /* optional */

    /* CEC_CAPTURE_HS_CALLBACK: */
    cec_capture_hs_fill_fn_t hs_fill;
} cec_capture_config_t;

/* Update the dump decimation factor at runtime. Clamped to >= 1. */
esp_err_t cec_capture_set_hs_dump_decimation(int decim);
int       cec_capture_get_hs_dump_decimation(void);

/* Human-readable trigger name for log / dump output. */
const char *cec_trigger_name(cec_trigger_t t);

/*
 * Allocate the pre-trigger + HS buffers in PSRAM (internal-heap
 * fallback), start the burst dispatcher task on Core 1, and copy the
 * config. In DMA mode the app's cec_adc must be initialized first.
 */
esp_err_t cec_capture_init(const cec_capture_config_t *cfg);

/*
 * Push one pre-trigger sample (pre_sample_size bytes are copied).
 * Called by the app's sample loop on every iteration. Lock-free for
 * the writer; the ring is read only at dump time on the dispatcher.
 */
void cec_capture_push(const void *sample);

/*
 * Request a burst capture.
 *   ESP_OK                  - capture queued
 *   ESP_ERR_NOT_FINISHED    - a capture is already running
 *   ESP_ERR_INVALID_STATE   - within cooldown window, or init not called
 * CEC_TRIG_SHUTDOWN bypasses the cooldown so a real shutdown is never
 * missed.
 */
esp_err_t cec_capture_trigger(cec_trigger_t reason);

/*
 * Same as cec_capture_trigger but attaches a short annotation string
 * to the dump as `>BURST_ANNOTATION:<text>`.
 */
esp_err_t cec_capture_trigger_with_text(cec_trigger_t reason, const char *text);

/*
 * True from the moment a trigger is accepted until the dump finishes.
 * Apps that share the ADC with the DMA HS path should skip ADC-touching
 * work while this returns true.
 */
bool cec_capture_is_busy(void);

/*
 * DMA mode: refresh the cached conversion params for one channel after
 * a runtime calibration change. idx in [0, n_channels); the .channel
 * field of `params` is ignored (the pattern is fixed at init).
 */
esp_err_t cec_capture_update_channel(int idx, const cec_capture_channel_t *params);

/*
 * DMA mode: read back the current conversion params for one channel
 * (for the app's hs_on_reading hook). Returns NULL on bad idx.
 */
const cec_capture_channel_t *cec_capture_channel_get(int idx);

#ifdef __cplusplus
}
#endif
