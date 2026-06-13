`default_nettype none
`timescale 1ns/1ps
// ----------------------------------------------------------------------------
// tb_native_detect -- self-checking sim for cec_native_detect.
// Drives a synthetic native-rate frame stream and checks:
//   A  seeded steady stream            -> no warm-up trip, no freeze
//   B  slow per-channel drift          -> EMA tracks it, no trip
//   C  transient on an UNMASKED channel-> no trip
//   D  fast transient on a MASKED chan -> trip on that channel, freeze exactly
//                                         POSTROLL frames later (centered dump)
//   E  disarm + re-arm                 -> trips again (latches cleared)
// Prints "PASS: ..." only if every check holds.
// ----------------------------------------------------------------------------
module tb_native_detect;
    localparam integer CH   = 8;
    localparam integer W    = 16;
    localparam integer PRW  = 12;
    localparam integer POSTROLL = 8;     // small for sim; real use = ring DEPTH/2
    localparam integer KSH  = 3;         // tau ~ 8 frames
    localparam integer THR  = 100;
    localparam [CH-1:0] MASK = 8'b1001_1100;  // watch ch 2,3,4,7 (the i3/i4/i5/i8 pins)

    reg clk = 1'b0; always #5 clk = ~clk;
    reg                rst = 1'b1, arm = 1'b0, in_stb = 1'b0;
    reg  [CH*W-1:0]    in_data = {CH*W{1'b0}};
    wire               freeze, tripped;
    wire [CH-1:0]      trip_ch;

    cec_native_detect #(.CHANNELS(CH), .W(W), .KMAX(12), .PRW(PRW)) dut (
        .clk(clk), .rst(rst), .arm(arm), .in_stb(in_stb), .in_data(in_data),
        .ch_mask(MASK), .k_shift(KSH[3:0]), .thresh(THR[W-1:0]),
        .postroll(POSTROLL[PRW-1:0]),
        .freeze(freeze), .tripped(tripped), .trip_ch(trip_ch));

    integer fails = 0, nframe = 0, k, j;
    integer trip_frame = -1, freeze_frame = -1, freeze_count = 0;
    reg signed [W-1:0] smp [0:CH-1];

    // base level per channel (steady)
    function signed [W-1:0] base_of(input integer ch);
        base_of = 800 + ch*50;
    endfunction

    task set_steady; begin
        for (j = 0; j < CH; j = j + 1) smp[j] = base_of(j);
    end endtask

    // one native frame: pack smp[] (ch0 low) and pulse in_stb for 1 clk.
    task tick; begin
        for (j = 0; j < CH; j = j + 1) in_data[j*W +: W] = smp[j];
        @(negedge clk); in_stb = 1'b1;
        @(negedge clk); in_stb = 1'b0;
        nframe = nframe + 1;
        @(negedge clk);                  // idle gap between frames
    end endtask

    // freeze / trip observers (count any freeze pulses; record their frame)
    always @(posedge clk) begin
        if (freeze) begin freeze_count = freeze_count + 1; freeze_frame = nframe; end
        if (tripped && trip_frame < 0) trip_frame = nframe;
    end

    task chk(input cond, input [1023:0] msg); begin
        if (!cond) begin fails = fails + 1; $display("FAIL: %0s", msg); end
    end endtask

    initial begin
        // reset
        repeat (3) @(negedge clk); rst = 1'b0; @(negedge clk);
        set_steady; arm = 1'b1;

        // ---- A: seed + steady -> no trip/freeze ----
        for (k = 0; k < 30; k = k + 1) tick;
        chk(!tripped && freeze_count == 0, "A: steady stream tripped/froze");

        // ---- B: slow drift on ch2 (+3/frame) -> EMA tracks, no trip ----
        for (k = 0; k < 40; k = k + 1) begin
            smp[2] = base_of(2) + k*3;   // lag ~ slope*(2^k-1) = 21 << THR
            tick;
        end
        smp[2] = base_of(2);
        for (k = 0; k < 12; k = k + 1) tick;   // settle back
        chk(!tripped && freeze_count == 0, "B: slow drift tripped/froze");

        // ---- C: transient on UNMASKED ch0 -> no trip ----
        smp[0] = base_of(0) + 600; tick; smp[0] = base_of(0);
        for (k = 0; k < 12; k = k + 1) tick;
        chk(!tripped && freeze_count == 0, "C: unmasked-channel transient tripped");

        // ---- D: fast transient on MASKED ch2 -> trip + centered freeze ----
        trip_frame = -1; freeze_count = 0; freeze_frame = -1;
        smp[2] = base_of(2) + 600; tick;       // <-- the transient frame
        smp[2] = base_of(2);
        for (k = 0; k < POSTROLL + 4; k = k + 1) tick;   // run past the post-roll
        chk(tripped, "D: masked transient did not trip");
        chk(trip_ch[2] === 1'b1, "D: trip_ch[2] not set");
        chk(trip_ch == 8'b0000_0100, "D: trip_ch not exactly ch2");
        chk(freeze_count == 1, "D: freeze did not pulse exactly once");
        chk((freeze_frame - trip_frame) == POSTROLL,
               "D: freeze not POSTROLL frames after trip (not centered)");

        // ---- E: disarm + re-arm clears the latch, can trip again ----
        arm = 1'b0; repeat (2) tick;           // disarm a couple frames
        chk(!tripped, "E: tripped not cleared on disarm");
        arm = 1'b1; trip_frame = -1; freeze_count = 0; freeze_frame = -1;
        for (k = 0; k < 12; k = k + 1) tick;   // re-seed + settle
        smp[2] = base_of(2) + 600; tick;       // transient again
        smp[2] = base_of(2);
        for (k = 0; k < POSTROLL + 4; k = k + 1) tick;
        chk(tripped && trip_ch[2] === 1'b1 && freeze_count == 1, "E: did not re-trip after re-arm");
        chk((freeze_frame - trip_frame) == POSTROLL, "E: re-trip freeze not centered");

        if (fails == 0)
            $display("PASS: native-detect seed/steady, slow-drift, masked vs unmasked, centered freeze, re-arm");
        else
            $display("FAIL: %0d check(s) failed", fails);
        $finish;
    end

    // global timeout
    initial begin #2_000_000; $display("FAIL: timeout"); $finish; end
endmodule
`default_nettype wire
