`default_nettype none
// ----------------------------------------------------------------------------
// cec_native_anomaly -- per-pin IMBALANCE / share-departure detector.
//
// The bench data settles WHY a plain transient detector is the wrong trigger:
// the GPU load is a ~342 Hz periodic swing (per-pin ~4 A peak-to-peak) and ALL
// pins swing TOGETHER, so a "deviation from my own baseline" detector fires on
// every load edge -- no signal. The thing that is ANOMALOUS (and melt-relevant)
// is a pin's SHARE of the load departing from fair-share -- a contact degrading
// so one pin hogs / starves while the rest carry the common swing.
//
// METRIC (common-mode rejected, bias-free): keep a SLOW per-pin average (EMA,
// tau >> the load period so the periodic swing AND the few-us edge-skew average
// out), then per masked pin form
//     e_i = NMASK*avg_i - sum(masked avg)        ( = NMASK*(avg_i - mean) )
// The per-channel ADC bias is common to all current channels, so it CANCELS in
// e_i (NMASK*bias - NMASK*bias = 0); a balanced load gives e_i = 0 regardless of
// the load LEVEL or its swing. e_i is non-zero only for a pin carrying more/less
// than fair-share. Trip when |e_i| > THRESH on any masked pin. THRESH is in raw
// code units, set ABOVE the board's normal worst imbalance (~3.5% here) so the
// normal fingerprint passes and only a real divergence trips.
//
// SCOPE: THRESH is a FIXED code count, so it is tuned for a load LEVEL (the
// imbalance is a fixed % of the load, so its absolute size scales with current).
// A fully load-INVARIANT trip wants the ratio e_i/total_current, which needs the
// bias to recover the total current (a divide / a bias config) -- deferred to the
// runtime-config increment. For a fixed bench workload the fixed threshold is the
// right tool and is what rejects the normal cycle.
//
// WARM-UP: the slow EMA needs ~a few tau to converge after arming; trips are
// held off until `warmup` frames have passed so the converging average can't
// false-fire. acc seeds to sample<<k on the first armed frame.
//
// freeze/tripped/trip_ch + the POSTROLL centered-freeze FSM are identical to
// cec_native_detect (it ORs into the ring's frozen-set the same way). Config
// (THRESH/K_SHIFT/CH_MASK/POSTROLL/WARMUP) are INPUTS for top.v to drive.
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module cec_native_anomaly #(
    parameter integer CHANNELS = 8,
    parameter integer W        = 16,   // signed per-channel sample width
    parameter integer NMASK    = 4,    // number of masked (current) channels
    parameter integer KMAX     = 14,   // max EMA shift; acc carries W+KMAX bits
    parameter integer PRW      = 12    // post-roll counter width (>= clog2 ring DEPTH)
)(
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   arm,        // 1 = watch + allow a fresh trip; 0 = clear/re-arm
    input  wire                   in_stb,     // 1-clk: in_data is a valid native frame
    input  wire [CHANNELS*W-1:0]  in_data,    // packed signed channels (ch0 in low W bits)
    input  wire [CHANNELS-1:0]    ch_mask,    // 1 = current channel (must total NMASK)
    input  wire [3:0]             k_shift,    // slow EMA shift; tau ~ 2^k frames (>> load period)
    input  wire [W-1:0]           thresh,     // |NMASK*(avg_i-mean)| > thresh (codes) -> trip
    input  wire [PRW-1:0]         postroll,   // frames after trip before freeze (center = DEPTH/2)
    input  wire [15:0]            warmup,     // frames to converge the average before arming trips
    output reg                    freeze,     // 1-clk: freeze the ring (centered dump)
    output reg                    tripped,    // latched until re-armed
    output reg  [CHANNELS-1:0]    trip_ch     // pin(s) whose share departed at the trip
);
    localparam integer AW = W + KMAX;          // EMA accumulator width
    localparam integer EW = AW + 4;            // residual headroom (NMASK*avg - sum)
    localparam [1:0] S_ARM = 2'd0, S_POST = 2'd1, S_DONE = 2'd2;

    reg signed [AW-1:0] acc [0:CHANNELS-1];
    reg                 seeded;
    reg [15:0]          warm;
    reg                 warmed;
    reg [1:0]           st;
    reg [PRW-1:0]       pr_cnt;

    // per-frame scratch (blocking; recomputed every in_stb)
    reg signed [W-1:0]  s_i;
    reg signed [EW-1:0] avg [0:CHANNELS-1];    // per-pin slow average (bias-inclusive)
    reg signed [EW-1:0] tot, e_i, ae;
    reg [CHANNELS-1:0]  hits;
    integer i;

    always @(posedge clk) begin
        freeze <= 1'b0;
        if (rst || !arm) begin
            st <= S_ARM; seeded <= 1'b0; warm <= 16'd0; warmed <= 1'b0;
            tripped <= 1'b0; trip_ch <= {CHANNELS{1'b0}}; pr_cnt <= {PRW{1'b0}};
            if (rst) for (i = 0; i < CHANNELS; i = i + 1) acc[i] <= {AW{1'b0}};
        end else if (in_stb) begin
            if (!seeded) begin
                seeded <= 1'b1;
                for (i = 0; i < CHANNELS; i = i + 1)
                    acc[i] <= $signed(in_data[i*W +: W]) <<< k_shift;
            end else begin
                // slow per-pin EMA (avg = pre-update estimate, used this frame)
                for (i = 0; i < CHANNELS; i = i + 1) begin
                    s_i    = $signed(in_data[i*W +: W]);
                    avg[i] = acc[i] >>> k_shift;
                    acc[i] <= acc[i] + (s_i - (acc[i] >>> k_shift));
                end
                // masked total (bias-inclusive); bias cancels in e_i below
                tot = {EW{1'b0}};
                for (i = 0; i < CHANNELS; i = i + 1)
                    if (ch_mask[i]) tot = tot + avg[i];
                // warm-up: let the average converge before enabling any trip
                if (!warmed) begin
                    if (warm >= warmup) warmed <= 1'b1;
                    else warm <= warm + 16'd1;
                end
                // common-mode-rejected share residual per masked pin
                hits = {CHANNELS{1'b0}};
                for (i = 0; i < CHANNELS; i = i + 1) begin
                    e_i = $signed(avg[i]) * NMASK - tot;     // = NMASK*(avg_i - mean)
                    ae  = e_i[EW-1] ? -e_i : e_i;            // |residual|
                    if (ch_mask[i] && warmed && (ae > {{(EW-W){1'b0}}, thresh}))
                        hits[i] = 1'b1;
                end
                case (st)
                    S_ARM: if (|hits) begin
                        tripped <= 1'b1;
                        trip_ch <= hits;
                        if (postroll == {PRW{1'b0}}) begin
                            freeze <= 1'b1; st <= S_DONE;
                        end else begin
                            pr_cnt <= postroll; st <= S_POST;
                        end
                    end
                    S_POST: if (pr_cnt <= {{(PRW-1){1'b0}}, 1'b1}) begin
                        freeze <= 1'b1; st <= S_DONE;
                    end else
                        pr_cnt <= pr_cnt - 1'b1;
                    default: ;                                // S_DONE: idle until disarmed
                endcase
            end
        end
    end
endmodule
`default_nettype wire
