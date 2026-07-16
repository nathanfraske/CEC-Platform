`default_nettype none
// ----------------------------------------------------------------------------
// cec_native_detect -- per-channel native-rate transient / imbalance detector.
//
// Runs at the native sample rate (one in_stb per acquisition frame, fed the SAME
// packed bus as cec_boxcar_decim). For each channel it tracks a slow per-channel
// baseline with a single-pole EMA and trips when the instantaneous sample
// deviates from that baseline by more than THRESH codes. This is the FPGA-side
// half of the §6.10/§6.13 event-capture model: it catches the fast (6-13 kHz)
// band the ESP decimated stream cannot see, and -- unlike the ESP `autoburst`,
// which freezes the instant it reacts and so tail-loads the event -- it waits
// POSTROLL more native frames before freezing, so the event lands CENTERED in
// the ring (set POSTROLL = ring DEPTH/2; the ring already carries the pre-roll).
//
// Detection metric is DEVIATION FROM EACH PIN'S OWN BASELINE, so it fires on
// BOTH a global transient (every pin steps from its baseline) AND a sudden
// per-pin imbalance shift (one pin's contact resistance changes -> its share
// steps) -- the contact-resistance early-warning the bench measured directly.
//
// EMA (high-resolution accumulator form, exact at steady state):
//     base  = acc >>> k                  (acc carries k fractional bits)
//     err   = sample - base              (== the deviation we threshold)
//     acc  += err                        (acc -> sample<<k, base -> sample)
// tau ~ 2^k native frames; k is a runtime input (no bitstream rebuild to tune).
// acc seeds to sample<<k on the first armed frame, so there is NO warm-up trip.
//
// Config (THRESH / K_SHIFT / CH_MASK / POSTROLL) are INPUTS: top.v can drive
// them from constants or from MOSI-written registers (the deferred runtime-config
// path) without changing this module. freeze is a 1-clk pulse meant to OR into
// the ring's frozen-set; tripped/trip_ch latch for the STATUS report until the
// next disarm. Hold arm low for >=1 frame to re-arm after reading a dump.
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module cec_native_detect #(
    parameter integer CHANNELS = 8,
    parameter integer W        = 16,   // signed per-channel sample width
    parameter integer KMAX     = 12,   // max EMA shift; acc carries W+KMAX bits
    parameter integer PRW      = 12    // post-roll counter width (>= clog2 ring DEPTH)
)(
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   arm,        // 1 = watch + allow a fresh trip; 0 = clear/re-arm
    input  wire                   in_stb,     // 1-clk: in_data is a valid native frame
    input  wire [CHANNELS*W-1:0]  in_data,    // packed signed channels (ch0 in low W bits)
    input  wire [CHANNELS-1:0]    ch_mask,    // 1 = this channel arms the trigger
    input  wire [3:0]             k_shift,    // EMA shift 0..KMAX; tau ~ 2^k frames
    input  wire [W-1:0]           thresh,     // |sample - baseline| > thresh (codes) -> trip
    input  wire [PRW-1:0]         postroll,   // frames after trip before freeze (center = DEPTH/2)
    output reg                    freeze,     // 1-clk: freeze the ring (centered dump)
    output reg                    tripped,    // latched until re-armed
    output reg  [CHANNELS-1:0]    trip_ch     // channel(s) that crossed at the trip instant
);
    localparam integer AW = W + KMAX;          // EMA accumulator width
    localparam [1:0] S_ARM = 2'd0, S_POST = 2'd1, S_DONE = 2'd2;

    reg signed [AW-1:0] acc [0:CHANNELS-1];
    reg                 seeded;
    reg [1:0]           st;
    reg [PRW-1:0]       pr_cnt;

    // per-frame scratch (blocking; recomputed every in_stb)
    reg signed [W-1:0]  s_i;
    reg signed [AW:0]   base_i, err_i, aerr;
    reg [CHANNELS-1:0]  hits;
    integer i;

    always @(posedge clk) begin
        freeze <= 1'b0;
        if (rst) begin
            st <= S_ARM; seeded <= 1'b0; tripped <= 1'b0; trip_ch <= {CHANNELS{1'b0}};
            pr_cnt <= {PRW{1'b0}};
            for (i = 0; i < CHANNELS; i = i + 1) acc[i] <= {AW{1'b0}};
        end else if (!arm) begin
            // disarmed: ready a fresh arm. Keep the accs warm (baseline survives).
            st <= S_ARM; seeded <= 1'b0; tripped <= 1'b0; trip_ch <= {CHANNELS{1'b0}};
        end else if (in_stb) begin
            if (!seeded) begin
                // seed each baseline to its sample -> err 0 -> no warm-up trip
                seeded <= 1'b1;
                for (i = 0; i < CHANNELS; i = i + 1)
                    acc[i] <= $signed(in_data[i*W +: W]) <<< k_shift;
            end else begin
                hits = {CHANNELS{1'b0}};
                for (i = 0; i < CHANNELS; i = i + 1) begin
                    s_i    = $signed(in_data[i*W +: W]);
                    base_i = acc[i] >>> k_shift;          // arithmetic (acc is signed)
                    err_i  = s_i - base_i;                // = deviation
                    acc[i] <= acc[i] + err_i;             // EMA: acc += sample - baseline
                    aerr   = err_i[AW] ? -err_i : err_i;  // |deviation|
                    if (ch_mask[i] && (aerr > {{(AW-W+1){1'b0}}, thresh}))
                        hits[i] = 1'b1;
                end
                case (st)
                    S_ARM: if (|hits) begin
                        tripped <= 1'b1;
                        trip_ch <= hits;
                        if (postroll == {PRW{1'b0}}) begin
                            freeze <= 1'b1;               // tail-loaded (autoburst-equivalent)
                            st     <= S_DONE;
                        end else begin
                            pr_cnt <= postroll;           // wait, then center the dump
                            st     <= S_POST;
                        end
                    end
                    S_POST: if (pr_cnt <= {{(PRW-1){1'b0}}, 1'b1}) begin
                        freeze <= 1'b1;
                        st     <= S_DONE;
                    end else
                        pr_cnt <= pr_cnt - 1'b1;
                    default: ;                              // S_DONE: idle until disarmed
                endcase
            end
        end
    end
endmodule
`default_nettype wire
