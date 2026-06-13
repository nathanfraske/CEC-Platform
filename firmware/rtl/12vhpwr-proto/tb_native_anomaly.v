`default_nettype none
`timescale 1ns/1ps
// ----------------------------------------------------------------------------
// tb_native_anomaly -- self-checking sim for cec_native_anomaly.
// The whole point vs a transient detector: the COMMON load swing must NOT trip.
// Masked current channels = {2,3,4,7}; each carries a big common bias (15000) +
// a common load + a per-pin imbalance. Checks:
//   A  big COMMON load swing (all pins together)   -> NO trip (CMR + bias cancel)
//   B  one-frame spike on a pin (edge-skew blip)   -> NO trip (slow EMA rejects)
//   C  SUSTAINED divergence on one pin (share up)  -> TRIP on that pin, centered
//   D  warm-up gate: imbalance present before warm -> NO trip until warmed
//   E  disarm + re-arm                             -> trips again
// Prints "PASS: ..." only if every check holds.
// ----------------------------------------------------------------------------
module tb_native_anomaly;
    localparam integer CH   = 8;
    localparam integer W    = 16;
    localparam integer NMASK= 4;
    localparam integer PRW  = 12;
    localparam integer POSTROLL = 8;
    localparam integer KSH  = 4;             // tau ~ 16 frames
    localparam integer THR  = 800;           // |NMASK*(avg-mean)| codes
    localparam integer WARM = 48;
    localparam [CH-1:0] MASK = 8'b1001_1100; // current channels 2,3,4,7 (NMASK=4)

    reg clk = 1'b0; always #5 clk = ~clk;
    reg                rst = 1'b1, arm = 1'b0, in_stb = 1'b0;
    reg  [CH*W-1:0]    in_data = {CH*W{1'b0}};
    wire               freeze, tripped;
    wire [CH-1:0]      trip_ch;

    cec_native_anomaly #(.CHANNELS(CH), .W(W), .NMASK(NMASK), .KMAX(14), .PRW(PRW)) dut (
        .clk(clk), .rst(rst), .arm(arm), .in_stb(in_stb), .in_data(in_data),
        .ch_mask(MASK), .k_shift(KSH[3:0]), .thresh(THR[W-1:0]),
        .postroll(POSTROLL[PRW-1:0]), .warmup(WARM[15:0]),
        .freeze(freeze), .tripped(tripped), .trip_ch(trip_ch));

    integer fails = 0, nframe = 0, k, j, m;
    integer trip_frame = -1, freeze_frame = -1, freeze_count = 0;
    integer load = 0;
    integer imb [0:CH-1];
    reg signed [W-1:0] smp [0:CH-1];

    // masked pins = 15000 bias + common load + per-pin imbalance; others = a
    // fixed (voltage-like) level -- not masked, must not affect the residual.
    task setframe; begin
        for (m = 0; m < CH; m = m + 1)
            smp[m] = MASK[m] ? (15000 + load + imb[m]) : (8000 + imb[m]);
    end endtask

    task tick; begin
        setframe;
        for (j = 0; j < CH; j = j + 1) in_data[j*W +: W] = smp[j];
        @(negedge clk); in_stb = 1'b1;
        @(negedge clk); in_stb = 1'b0;
        nframe = nframe + 1;
        @(negedge clk);
    end endtask

    always @(posedge clk) begin
        if (freeze)  begin freeze_count = freeze_count + 1; freeze_frame = nframe; end
        if (tripped && trip_frame < 0) trip_frame = nframe;
    end

    task chk(input cond, input [1023:0] msg); begin
        if (!cond) begin fails = fails + 1; $display("FAIL: %0s", msg); end
    end endtask

    task clr_imb; begin for (m=0;m<CH;m=m+1) imb[m]=0; end endtask

    initial begin
        clr_imb; load = 0;
        repeat (3) @(negedge clk); rst = 1'b0; @(negedge clk);
        arm = 1'b1;

        // ---- warm up on a balanced, swinging baseline ----
        for (k = 0; k < 80; k = k + 1) begin
            load = (k % 8) * 250;            // a periodic common swing while warming
            tick;
        end
        load = 0;
        chk(!tripped && freeze_count == 0, "warm-up balanced baseline tripped");

        // ---- A: big COMMON load swing (all pins together) -> NO trip ----
        for (k = 0; k < 60; k = k + 1) begin
            load = (k % 6) * 600;            // 0..3000 swing, all masked pins together
            tick;
        end
        load = 0; for (k=0;k<8;k=k+1) tick;
        chk(!tripped && freeze_count == 0, "A: common load swing TRIPPED (CMR failed)");

        // ---- B: one-frame spike on ch4 (edge-skew blip) -> NO trip ----
        imb[4] = 2000; tick; imb[4] = 0;     // single frame
        for (k = 0; k < 20; k = k + 1) tick;
        chk(!tripped && freeze_count == 0, "B: one-frame spike TRIPPED (EMA too fast)");

        // ---- C: SUSTAINED divergence on ch4 -> TRIP on ch4, centered ----
        trip_frame = -1; freeze_count = 0; freeze_frame = -1;
        imb[4] = 400;                        // ch4 now hogs ~+400 over fair share
        for (k = 0; k < 60; k = k + 1) tick; // let the slow average follow + post-roll
        chk(tripped, "C: sustained divergence did not trip");
        chk(trip_ch[4] === 1'b1, "C: trip_ch[4] not set");
        chk(trip_ch == 8'b0001_0000, "C: trip_ch not exactly ch4");
        chk(freeze_count == 1, "C: freeze did not pulse exactly once");
        chk((freeze_frame - trip_frame) == POSTROLL, "C: freeze not centered (POSTROLL)");

        // ---- D: warm-up gate -- imbalance present from arm, no trip until warmed ----
        arm = 1'b0; repeat (2) tick;         // disarm/reset
        clr_imb; imb[4] = 400; load = 0;     // imbalance present immediately on re-arm
        arm = 1'b1; trip_frame = -1; freeze_count = 0;
        for (k = 0; k < WARM - 8; k = k + 1) tick;   // still inside warm-up
        chk(!tripped, "D: tripped before warm-up completed");
        for (k = 0; k < 40; k = k + 1) tick;         // past warm-up -> should trip
        chk(tripped && trip_ch[4] === 1'b1, "D: did not trip after warm-up");

        // ---- E: disarm + re-arm trips again ----
        arm = 1'b0; repeat (2) tick;
        chk(!tripped, "E: tripped not cleared on disarm");
        arm = 1'b1; trip_frame = -1; freeze_count = 0;  // imb[4] still 400
        for (k = 0; k < WARM + 40; k = k + 1) tick;
        chk(tripped && trip_ch[4] === 1'b1 && freeze_count >= 1, "E: did not re-trip after re-arm");

        if (fails == 0)
            $display("PASS: anomaly rejects common-swing + edge-skew, trips on sustained imbalance, warm-up + re-arm");
        else
            $display("FAIL: %0d check(s) failed", fails);
        $finish;
    end

    initial begin #5_000_000; $display("FAIL: timeout"); $finish; end
endmodule
`default_nettype wire
