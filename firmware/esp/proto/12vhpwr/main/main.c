/* 12vhpwr-proto ESP32-P4 bring-up.
 * SPI master to the GW5A via the shared cec_fpga_link component: poll
 * DRDY, pull an 18-byte frame (0xA5, seq, V1..V8 big-endian).
 *
 * Two output paths (Kconfig CEC_PROTO_RAW_CONSOLE):
 *   - RAW (default until bench step 3 passes): the v0 printf loop,
 *     byte-for-byte — the path verified in simulation.
 *   - TelePlot: eight channels (volts) plus seq through the shared
 *     cec_teleplot engine, ~5 Hz.
 * Either way the cec_cli 'frame' command dumps one frame on demand.
 *
 * Pins per main/cec_config.h (doc section 6.3 / 10).
 * License: Apache-2.0 (CEC-Platform). */
#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cec_fpga_link.h"
#include "cec_config.h"
#include "cec_teleplot.h"
#include "cec_cli.h"
#include "cec_filters.h"

static const char *TAG = "12vhpwr_proto";

/* DRDY idle-poll delay. Must be >= 1 tick so the idle task gets to run
 * (the task watchdog watches it): pdMS_TO_TICKS(1) rounds to 0 at the
 * default 100 Hz tick rate, and vTaskDelay(0) never yields -> a low DRDY
 * (FPGA not pacing yet) spins the loop at 100% and starves IDLE -> TWDT.
 * One tick (10 ms @ 100 Hz) is far below the ~200 ms frame period. */
#define PROTO_DRDY_POLL_TICKS  1

/* Set while a `burst` capture is running so the TelePlot loop yields the
 * FPGA link to the tight capture loop. */
static volatile bool s_capturing = false;

/* ---------------------------- CLI handlers ---------------------------- */

/* Dump one frame on demand (any mode). Reads whatever the fabric has
 * latched; DRDY state is reported rather than awaited so the command
 * never blocks the console. */
static int cli_cmd_frame(int argc, char **argv)
{
    (void)argc; (void)argv;
    bool drdy = cec_fpga_link_poll();
    cec_fpga_frame_t f;
    esp_err_t err = cec_fpga_link_read(&f);
    if (err != ESP_OK) {
        printf("error: %s\n", esp_err_to_name(err));
        return 1;
    }
    printf("drdy=%d header=0x%02x (%s) seq=%u\n",
           drdy ? 1 : 0, f.header, f.header_ok ? "ok" : "BAD", f.seq);
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
        const proto_ch_cal_t *c = &PROTO_CH_CAL[ch];
        if (c->label == NULL) {
            printf("  ch%-2d  (unconnected)         (raw %+6d, %+7.4f Vadc)\n",
                   ch + 1, f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
            continue;
        }
        printf("  %-5s %+9.4f %-4s (raw %+6d, %+7.4f Vadc)\n",
               c->label, proto_channel_phys(ch, f.code[ch]), proto_kind_unit(c->kind),
               f.code[ch], f.code[ch] * PROTO_LSB_VOLTS);
    }
    return 0;
}

/* Capture N frames at the FPGA rate (~50 kHz) into RAM, then dump a CSV
 * block (us offset, seq, calibrated channels) for host plotting. The 50 kHz
 * stream is too fast to send live over USB-CDC (text ~6 MB/s vs ~1 MB/s),
 * so this grabs a finite window and dumps it afterward. The us/seq columns
 * reveal the true captured rate and any dropped frames. Usage: `burst [N]`
 * (default 2048; ~41 ms window). */
static int cli_cmd_burst(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : 2048;
    if (n < 1)    n = 1;
    if (n > 8192) n = 8192;

    struct cap { int64_t us; cec_fpga_frame_t f; };
    struct cap *buf = malloc((size_t)n * sizeof(*buf));
    if (buf == NULL) { printf("burst: out of memory for %d frames\n", n); return 1; }

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));              /* let the TelePlot loop pause */
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2); /* min preemption jitter while capturing */
    int  got  = 0;
    bool dead = false;
    int64_t t0 = esp_timer_get_time();
    for (; got < n && !dead; got++) {
        uint32_t spin = 0;
        while (!cec_fpga_link_poll()) {
            if (++spin > 2000000u) { dead = true; break; }   /* no DRDY -> bail */
        }
        if (dead || cec_fpga_link_read(&buf[got].f) != ESP_OK) break;
        buf[got].us = esp_timer_get_time() - t0;
    }
    vTaskPrioritySet(NULL, old_prio);          /* restore before the slow dump */

    /* Dump with the link still owned (TelePlot stays paused) so the CSV block
     * prints clean -- no live ">..." lines interleaved into it. Markers
     * (===) bracket the block so it is trivial to extract from a serial log. */
    int64_t span = got ? buf[got - 1].us : 0;
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# burst: %d frames in %lld us (~%.1f kHz)\n",
           got, span, span ? 1000.0 * (got - 1) / span : 0.0);
    printf("us,seq");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    for (int i = 0; i < got; i++) {
        printf("%lld,%u", buf[i].us, buf[i].f.seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].f.code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    s_capturing = false;
    free(buf);
    return 0;
}

/* Pull the FPGA's native-rate capture ring in one shot: hold MOSI high
 * (buffered reads), discard the ARM read, then read N frames straight out of
 * BRAM and dump a CSV. Unlike `burst` (ESP-paced, ~12 kHz), this is the FPGA's
 * full native rate -- uniform and gap-free (the seq column is consecutive).
 * N <= PROTO_RING_DEPTH. Usage: `fastburst [N]` (default = full ring). */
static int cli_cmd_fastburst(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : PROTO_RING_DEPTH;
    if (n < 1)                n = 1;
    if (n > PROTO_RING_DEPTH) n = PROTO_RING_DEPTH;

    cec_fpga_frame_t *buf = malloc((size_t)n * sizeof(*buf));
    if (buf == NULL) { printf("fastburst: out of memory for %d frames\n", n); return 1; }

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2);
    cec_fpga_frame_t armf;
    cec_fpga_link_read_buffered(&armf);       /* ARM: freeze ring at oldest (discard) */
    int got = 0;
    for (; got < n; got++)
        if (cec_fpga_link_read_buffered(&buf[got]) != ESP_OK) break;
    vTaskPrioritySet(NULL, old_prio);
    s_capturing = false;

    int gaps = 0, badhdr = 0;
    for (int i = 0; i < got; i++) {
        if (!buf[i].header_ok) badhdr++;
        if (i && buf[i].seq != (uint8_t)(buf[i - 1].seq + 1)) gaps++;
    }
    const double real_hz = proto_measured_native_hz();
    const double us_per  = 1.0e6 / real_hz;
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# fastburst: %d frames @ %.2f kSPS native %s, %d seq-gaps, %d bad-hdr; "
           "us = idx x %.3f us\n",
           got, real_hz / 1000.0,
           proto_native_hz_measured() ? "(measured)" : "(NOMINAL -- run `rate`)",
           gaps, badhdr, us_per);
    printf("us,seq");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    for (int i = 0; i < got; i++) {
        printf("%.1f,%u", i * us_per, buf[i].seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    free(buf);
    return 0;
}

/* Drain the FPGA's CONTINUOUS decimated stream (the free-running FIFO) in a
 * tight block loop -- the ~25 kSPS path. The FPGA boxcar-averages DECIM_M native
 * samples per stream sample (oversample + decimate), so the link rate is modest
 * and the drain stays OFF the per-frame console/teleplot path -- which is what
 * lets it run continuously instead of capping at the ~13 kHz live ceiling. The
 * seq byte is the per-session dropped-sample count (FIFO overrun = the ESP fell
 * behind -> constant 0 == gap-free); a 0x5A header is an underrun (FIFO empty,
 * stale codes -> skipped). Usage: `stream [N]` (default = full window). */
static int cli_cmd_stream(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : PROTO_STREAM_DEPTH;
    if (n < 1)    n = 1;
    if (n > 8192) n = 8192;

    cec_fpga_frame_t *buf = malloc((size_t)n * sizeof(*buf));
    if (buf == NULL) { printf("stream: out of memory for %d frames\n", n); return 1; }

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));              /* let the TelePlot loop pause */
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2);
    cec_fpga_frame_t primef;
    cec_fpga_link_read_stream(&primef);        /* select stream mode (discard) */
    int64_t t0 = esp_timer_get_time();
    int got = 0;
    for (; got < n; got++)
        if (cec_fpga_link_read_stream(&buf[got]) != ESP_OK) break;
    int64_t span = esp_timer_get_time() - t0;
    vTaskPrioritySet(NULL, old_prio);
    s_capturing = false;

    int     under = 0;
    uint8_t drop0 = 0, dropN = 0;
    bool    first = true;
    for (int i = 0; i < got; i++) {
        if (buf[i].header == 0x5A) {
            under++;
        } else if (buf[i].header_ok) {
            if (first) { drop0 = buf[i].seq; first = false; }
            dropN = buf[i].seq;
        }
    }
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# stream: %d frames in %lld us (~%.1f kSPS link), %d underruns, "
           "dropcount %u->%u (%u lost); nominal %d kSPS\n",
           got, span, span ? 1000.0 * got / span : 0.0, under,
           drop0, dropN, (uint8_t)(dropN - drop0), PROTO_STREAM_HZ / 1000);
    printf("us,drop");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    const double us_per = 1.0e6 / (double)PROTO_STREAM_HZ;
    for (int i = 0; i < got; i++) {
        if (buf[i].header == 0x5A) continue;   /* underrun: stale codes, skip */
        printf("%.1f,%u", i * us_per, buf[i].seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    free(buf);
    return 0;
}

/* Zero-calibrate the per-channel current-sense offset at NO LOAD: average N
 * frames and set each AMP channel's bias to its measured 0-A output (the INA
 * offset differs per channel, so a single provisional bias can't null them all).
 * VOLT/RAW channels (vrail) are left as configured -- the rail is not 0 at idle.
 * Run with the GPU idle / sense pins at ~0 A. Offsets are runtime-only (lost on
 * reboot; NVS-persist is a follow-up). Usage: `cal [N]` (default 256). */
static int cli_cmd_cal(int argc, char **argv)
{
    int n = (argc >= 2) ? atoi(argv[1]) : 256;
    if (n < 16)   n = 16;
    if (n > 4096) n = 4096;

    double sum[CEC_FPGA_FRAME_CHANNELS] = {0};
    int got = 0;
    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));
    for (int i = 0; i < n; i++) {
        cec_fpga_frame_t f;
        if (cec_fpga_link_read(&f) == ESP_OK && f.header_ok) {
            for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
                sum[ch] += (double)f.code[ch];
            got++;
        }
        if ((i & 0x1F) == 0x1F) vTaskDelay(1);   /* keep IDLE alive during the average */
    }
    s_capturing = false;
    if (got == 0) { printf("cal: no good frames (link down?)\n"); return 1; }

    printf("cal: averaged %d frames; per-channel zero:\n", got);
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
        const proto_ch_cal_t *c = &PROTO_CH_CAL[ch];
        double avg_code = sum[ch] / got;
        float  avg_v    = (float)(avg_code * PROTO_LSB_VOLTS);
        if (c->kind == PROTO_KIND_AMP) {
            float old = proto_cal_get_offset_v(ch);
            proto_cal_set_offset_v(ch, avg_v);            /* this channel's 0-A bias */
            printf("  %-5s code %+8.1f -> bias %+7.4f V (was %+7.4f) [SET]\n",
                   c->label ? c->label : "?", avg_code, avg_v, old);
        } else {
            printf("  %-5s code %+8.1f -> %+7.4f V  (%s, offset unchanged)\n",
                   c->label ? c->label : "(nc)", avg_code, avg_v, proto_kind_unit(c->kind));
        }
    }
    printf("cal: done -- current channels now read ~0 A at idle.\n");
    return 0;
}

/* Auto-burst on an anomalous transient -- the platform's event-driven capture
 * (spec 6.10/6.13: detect -> freeze the pre-roll ring -> dump), in firmware on
 * this rig. Continuously drain the decimated stream, track each current
 * channel's running baseline (software EMA), and when one DEVIATES past the
 * threshold, freeze the FPGA native ring and dump it (the detailed transient +
 * its pre-roll, at the native rate). Detection runs on the ~13 kSPS stream (the
 * ESP keeps up there) so it catches transients to a few kHz -- which is all the
 * perfboard anti-alias passes anyway; the DETAIL is the native-rate ring.
 * Usage: `autoburst <thresh_codes> [<ntrig>]`  (~655 codes/A on i*; default
 * ntrig 1). Returns after ntrig captures or a 30 s no-trigger timeout. */
static int cli_cmd_autoburst(int argc, char **argv)
{
    const double codes_per_A = PROTO_ISENSE_V_PER_A / PROTO_LSB_VOLTS;  /* ~655 */
    if (argc < 2) {
        printf("usage: autoburst <thresh_codes> [<ntrig>]  (~%.0f codes/A on i*)\n",
               codes_per_A);
        return 1;
    }
    int thresh = atoi(argv[1]); if (thresh < 1) thresh = 1;
    int ntrig  = (argc >= 3) ? atoi(argv[2]) : 1; if (ntrig < 1) ntrig = 1;

    bool watch[CEC_FPGA_FRAME_CHANNELS];
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        watch[ch] = (PROTO_CH_CAL[ch].kind == PROTO_KIND_AMP);

    cec_fpga_frame_t *buf = malloc((size_t)PROTO_RING_DEPTH * sizeof(*buf));
    if (buf == NULL) { printf("autoburst: out of memory\n"); return 1; }

    const int     K       = 6;                      /* EMA shift, ~64-sample baseline */
    const int     ARM_N   = 256;                    /* settle the baseline before arming */
    const int     YIELD_N = 1024;                   /* reads between IDLE yields */
    const int64_t MAX_US  = 30LL * 1000 * 1000;

    printf("autoburst: thresh=%d codes (~%.2f A), ntrig=%d -- watching the stream, "
           "induce the transient...\n", thresh, thresh / codes_per_A, ntrig);

    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));
    cec_fpga_frame_t f;
    cec_fpga_link_read_stream(&f);                  /* select stream mode (discard) */

    int     fired   = 0;
    int64_t t0      = esp_timer_get_time();
    int32_t base[CEC_FPGA_FRAME_CHANNELS] = {0};
    int     seen    = 0;                            /* fresh samples since (re)arm */
    int     yield_i = 0;

    while (fired < ntrig && (esp_timer_get_time() - t0) < MAX_US) {
        if (cec_fpga_link_read_stream(&f) != ESP_OK) break;
        if (f.header != CEC_FPGA_FRAME_HEADER) continue;   /* skip underruns (0x5A) */

        int     trig_ch  = -1;
        int32_t trig_dev = 0;
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
            if (!watch[ch]) continue;
            if (seen == 0) base[ch] = f.code[ch];          /* first fresh sample seeds */
            int32_t dev = (int32_t)f.code[ch] - base[ch];
            if (dev < 0) dev = -dev;
            if (seen >= ARM_N && dev > thresh && dev > trig_dev) { trig_ch = ch; trig_dev = dev; }
            base[ch] += ((int32_t)f.code[ch] - base[ch]) >> K;   /* EMA update */
        }
        seen++;

        if (trig_ch >= 0) {                            /* TRIGGER: freeze + dump native ring */
            UBaseType_t op = uxTaskPriorityGet(NULL);
            vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2);
            cec_fpga_frame_t armf;
            cec_fpga_link_read_buffered(&armf);        /* arm/freeze (discard) */
            int rgot = 0;
            for (; rgot < PROTO_RING_DEPTH; rgot++)
                if (cec_fpga_link_read_buffered(&buf[rgot]) != ESP_OK) break;
            vTaskPrioritySet(NULL, op);

            int gaps = 0;
            for (int i = 1; i < rgot; i++)
                if (buf[i].seq != (uint8_t)(buf[i - 1].seq + 1)) gaps++;
            const double real_hz = proto_measured_native_hz();
            const double us_per  = 1.0e6 / real_hz;
            printf("\n===BURST_CSV_BEGIN===\n");
            printf("# autoburst TRIGGER %d/%d: ch=%s dev=%d codes (~%.2f A); native ring "
                   "%d frames @ %.2f kSPS %s, %d seq-gaps; us = idx x %.3f (transient near the TAIL)\n",
                   fired + 1, ntrig,
                   PROTO_CH_CAL[trig_ch].label ? PROTO_CH_CAL[trig_ch].label : "?",
                   (int)trig_dev, trig_dev / codes_per_A, rgot, real_hz / 1000.0,
                   proto_native_hz_measured() ? "(measured)" : "(nominal)", gaps, us_per);
            printf("us,seq");
            for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
                if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
            printf("\n");
            for (int i = 0; i < rgot; i++) {
                printf("%.1f,%u", i * us_per, buf[i].seq);
                for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
                    if (PROTO_CH_CAL[ch].label)
                        printf(",%.4f", proto_channel_phys(ch, buf[i].code[ch]));
                printf("\n");
            }
            printf("===BURST_CSV_END===\n");
            fired++;
            cec_fpga_link_read_stream(&f);             /* resume stream + re-arm baseline */
            seen = 0; yield_i = 0;
            continue;
        }

        if (++yield_i >= YIELD_N) { yield_i = 0; vTaskDelay(1); }   /* let IDLE run */
    }

    s_capturing = false;
    free(buf);
    printf("autoburst: %s after %d/%d triggers\n",
           (fired >= ntrig) ? "done" : "stopped (timeout)", fired, ntrig);
    return 0;
}

/* Measure the TRUE native sample rate: read the FPGA's free-running native-frame
 * counter (status mode, header 0x5C) twice over a known interval. The conv+read
 * FSM self-limits below the nominal pacer, so the burst/FFT time axis must use
 * THIS, not the nominal label -- a 2x error otherwise. Stores it for the
 * burst/autoburst dumps. Usage: `rate [ms]` (default 250). */
static int cli_cmd_rate(int argc, char **argv)
{
    int ms = (argc >= 2) ? atoi(argv[1]) : 250;
    if (ms < 50)   ms = 50;
    if (ms > 5000) ms = 5000;

    /* Pause the TelePlot loop: otherwise it keeps reading the link (MOSI=0x00 =
     * live) during the measurement window and flips the fabric out of status
     * mode, so the 2nd counter read grabs live channel data -> garbage rate. */
    s_capturing = true;
    vTaskDelay(pdMS_TO_TICKS(3));

    cec_fpga_frame_t f;
    cec_fpga_link_read_status(&f);              /* select status mode (discard) */
    if (cec_fpga_link_read_status(&f) != ESP_OK || f.header != 0x5C) {
        s_capturing = false;
        printf("rate: no status frame (hdr 0x%02x) -- old bitstream? rebuild the FPGA\n",
               f.header);
        return 1;
    }
    uint32_t c1 = ((uint32_t)(uint16_t)f.code[0] << 16) | (uint16_t)f.code[1];
    int64_t  t1 = esp_timer_get_time();
    vTaskDelay(pdMS_TO_TICKS(ms));
    if (cec_fpga_link_read_status(&f) != ESP_OK || f.header != 0x5C) {
        s_capturing = false;
        printf("rate: status read failed (hdr 0x%02x)\n", f.header);
        return 1;
    }
    uint32_t c2 = ((uint32_t)(uint16_t)f.code[0] << 16) | (uint16_t)f.code[1];
    int64_t  t2 = esp_timer_get_time();
    s_capturing = false;

    uint32_t dframes = c2 - c1;                 /* unsigned -> wrap-safe */
    double   dt_s    = (t2 - t1) / 1.0e6;
    if (dt_s <= 0.0 || dframes == 0) {
        printf("rate: no frames counted (FPGA not pacing?)\n"); return 1;
    }
    double hz = dframes / dt_s;
    proto_set_measured_native_hz((float)hz);
    printf("rate: %u native frames in %.3f s = %.0f Hz (%.2f kSPS) [nominal %d kSPS] "
           "-- burst/autoburst now use the measured rate\n",
           (unsigned)dframes, dt_s, hz, hz / 1000.0, PROTO_NATIVE_HZ / 1000);
    return 0;
}

/* FPGA-side native-rate detector: ARM the in-fabric detector (top.v
 * cec_native_detect), wait for it to catch a transient / per-pin imbalance step
 * (it freezes the ring CENTERED on the event), then dump that centered native
 * window as CSV and disarm. Unlike `autoburst` (ESP software EMA on the decimated
 * stream, event lands near the TAIL), the threshold + EMA run in the fabric at
 * the full native rate and the dump is centered. Threshold/k/mask live in the
 * bitstream (top.v DET_*); this just drives the arm/poll/read/rearm protocol.
 * Usage: `detect [timeout_ms]` (default 5000). */
static int cli_cmd_detect(int argc, char **argv)
{
    int timeout_ms = (argc >= 2) ? atoi(argv[1]) : 5000;
    if (timeout_ms < 100) timeout_ms = 100;

    cec_fpga_frame_t *buf = malloc((size_t)PROTO_RING_DEPTH * sizeof(*buf));
    if (buf == NULL) { printf("detect: out of memory\n"); return 1; }

    s_capturing = true;                          /* pause the TelePlot loop (shares the link) */
    vTaskDelay(pdMS_TO_TICKS(3));
    cec_fpga_link_detect_arm();                  /* 0x44: arm the sticky detector */
    printf("detect: armed; watching for a transient (timeout %d ms)...\n", timeout_ms);

    /* Poll STATUS for the tripped bit (code[2] bit15). Status reads do NOT
     * disarm the detector or consume the ring; skip non-status frames (the
     * mode-select discard returns a live frame first). */
    cec_fpga_frame_t f;
    bool    tripped = false;
    uint8_t trip_ch = 0;
    cec_fpga_link_read_status(&f);               /* select status mode (discard) */
    for (int waited = 0; waited < timeout_ms; waited += 5) {
        if (cec_fpga_link_read_status(&f) == ESP_OK && f.header == 0x5C) {
            uint16_t det = (uint16_t)f.code[2];
            if (det & 0x8000) { tripped = true; trip_ch = (uint8_t)(det & 0xFF); break; }
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }

    if (!tripped) {
        cec_fpga_link_detect_clear();            /* 0x46: disarm + resume the ring */
        s_capturing = false;
        free(buf);
        printf("detect: no trip within %d ms (disarmed). Lower DET_THRESH in the "
               "bitstream or check the load.\n", timeout_ms);
        return 0;
    }

    /* Which pin crossed: detector ch i maps to ESP frame index (7 - i). */
    printf("detect: TRIP (trip_ch=0x%02x) on", trip_ch);
    for (int i = 0; i < CEC_FPGA_FRAME_CHANNELS; i++)
        if (trip_ch & (1 << i)) {
            const char *lbl = PROTO_CH_CAL[7 - i].label;
            printf(" %s", lbl ? lbl : "ch?");
        }
    printf(" -- reading the centered ring\n");

    /* Read the centered, frozen ring (0xFF); discard one for the 0x33->0xFF switch. */
    UBaseType_t old_prio = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, configMAX_PRIORITIES - 2);
    cec_fpga_frame_t armf;
    cec_fpga_link_read_buffered(&armf);          /* mode switch (discard) */
    int got = 0;
    for (; got < PROTO_RING_DEPTH; got++)
        if (cec_fpga_link_read_buffered(&buf[got]) != ESP_OK) break;
    vTaskPrioritySet(NULL, old_prio);

    cec_fpga_link_detect_clear();                /* disarm + resume the ring */
    s_capturing = false;

    int gaps = 0, badhdr = 0;
    for (int i = 0; i < got; i++) {
        if (!buf[i].header_ok) badhdr++;
        if (i && buf[i].seq != (uint8_t)(buf[i - 1].seq + 1)) gaps++;
    }
    const double real_hz = proto_measured_native_hz();
    const double us_per  = 1.0e6 / real_hz;
    printf("\n===BURST_CSV_BEGIN===\n");
    printf("# detect TRIP trip_ch=0x%02x: %d frames @ %.2f kSPS native %s, %d seq-gaps, "
           "%d bad-hdr; us = idx x %.3f us (transient ~CENTERED near idx %d)\n",
           trip_ch, got, real_hz / 1000.0,
           proto_native_hz_measured() ? "(measured)" : "(NOMINAL -- run `rate`)",
           gaps, badhdr, us_per, got / 2);
    printf("us,seq");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        if (PROTO_CH_CAL[ch].label) printf(",%s", PROTO_CH_CAL[ch].label);
    printf("\n");
    for (int i = 0; i < got; i++) {
        printf("%.1f,%u", i * us_per, buf[i].seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
            if (PROTO_CH_CAL[ch].label)
                printf(",%.4f", proto_channel_phys(ch, buf[i].code[ch]));
        printf("\n");
    }
    printf("===BURST_CSV_END===\n");
    free(buf);
    return 0;
}

static const cec_cli_command_t CLI_COMMANDS[] = {
    { "frame",     "pull + dump one FPGA frame (header, seq, V1..V8)", cli_cmd_frame },
    { "burst",     "ESP-paced capture [N] frames to RAM, dump CSV (~12 kHz)", cli_cmd_burst },
    { "fastburst", "FPGA ring readout [N] at the full native rate (uniform)", cli_cmd_fastburst },
    { "stream",    "continuous decimated FIFO drain [N] (~25 kSPS, dropcount)", cli_cmd_stream },
    { "cal",       "zero-cal current-sense offsets at no load [N avg]", cli_cmd_cal },
    { "autoburst", "auto-dump native ring on a transient <thresh_codes> [ntrig]", cli_cmd_autoburst },
    { "rate",      "measure the true native sample rate [ms avg]", cli_cmd_rate },
    { "detect",    "arm the FPGA native detector; dump the centered ring on a trip [timeout_ms]", cli_cmd_detect },
};

#if !CONFIG_CEC_PROTO_RAW_CONSOLE
/* Rolling-median de-glitch for the median-flagged (steady) channels. */
#define PROTO_MEDIAN_WIN 5
static float    s_med_buf[CEC_FPGA_FRAME_CHANNELS][PROTO_MEDIAN_WIN];
static median_t s_med[CEC_FPGA_FRAME_CHANNELS];

/* TelePlot streaming loop: calibrated channels (volts/amps per PROTO_CH_CAL)
 * plus seq. The rail is median-filtered to reject its per-channel glitch. */
static void teleplot_loop(void)
{
    ESP_LOGI(TAG, "TelePlot loop: waiting on DRDY");
    for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++)
        median_init(&s_med[ch], s_med_buf[ch], PROTO_MEDIAN_WIN);
    while (1) {
        if (s_capturing) {                 /* a `burst` owns the link */
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        if (!cec_fpga_link_poll()) {
            vTaskDelay(PROTO_DRDY_POLL_TICKS);
            continue;
        }
        cec_fpga_frame_t f;
        if (cec_fpga_link_read(&f) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (!f.header_ok) {
            ESP_LOGW(TAG, "bad header 0x%02x (alignment?)", f.header);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        int64_t now_ms = esp_timer_get_time() / 1000;
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
            if (PROTO_CH_CAL[ch].label == NULL) continue;   /* unconnected channel */
            float v = proto_channel_phys(ch, f.code[ch]);
            if (PROTO_CH_CAL[ch].median) v = median_update(&s_med[ch], v);
            teleplot_emit_t(PROTO_CH_CAL[ch].label, now_ms, v);
        }
        teleplot_emit_t("seq", now_ms, (float)f.seq);
        vTaskDelay(pdMS_TO_TICKS(200));   /* ~5 Hz; FPGA keeps pacing */
    }
}
#else
/* v0 raw console loop, byte-for-byte (the simulation-verified path). */
static void raw_console_loop(void)
{
    printf("12vhpwr-proto v0: waiting on DRDY\n");
    while (1) {
        if (!cec_fpga_link_poll()) {
            vTaskDelay(PROTO_DRDY_POLL_TICKS);
            continue;
        }
        cec_fpga_frame_t f;
        if (cec_fpga_link_read(&f) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (!f.header_ok) {
            printf("bad header 0x%02x (alignment?)\n", f.header);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        printf("seq %3u |", f.seq);
        for (int ch = 0; ch < CEC_FPGA_FRAME_CHANNELS; ch++) {
            printf(" V%d %+6d (%+8.4f V)", ch + 1, f.code[ch],
                   f.code[ch] * PROTO_LSB_VOLTS);
        }
        printf("\n");
        vTaskDelay(pdMS_TO_TICKS(200));   /* ~5 Hz console; FPGA keeps pacing */
    }
}
#endif

void app_main(void)
{
    ESP_LOGI(TAG, "app_main: start (proto bring-up)");

    proto_cal_init();   /* seed runtime cal offsets (also auto-seeds on first use) */

    cec_fpga_link_config_t link_cfg;
    cec_config_fpga_link(&link_cfg);
    /* Non-fatal: a stuck/failed FPGA link must not boot-loop the board
     * via ESP_ERROR_CHECK -- log and continue so the console stays up
     * and the failing step is visible. */
    esp_err_t link_err = cec_fpga_link_init(&link_cfg);
    if (link_err != ESP_OK) {
        ESP_LOGE(TAG, "cec_fpga_link_init failed: %s", esp_err_to_name(link_err));
    } else {
        ESP_LOGI(TAG, "app_main: fpga link up");
    }

    esp_err_t cli_err = cec_cli_init(CLI_COMMANDS,
                                     sizeof(CLI_COMMANDS) / sizeof(CLI_COMMANDS[0]));
    if (cli_err != ESP_OK) {
        ESP_LOGW(TAG, "cec_cli_init failed: %s — serial commands unavailable",
                 esp_err_to_name(cli_err));
    }

#if CONFIG_CEC_PROTO_RAW_CONSOLE
    raw_console_loop();
#else
    teleplot_loop();
#endif
}
