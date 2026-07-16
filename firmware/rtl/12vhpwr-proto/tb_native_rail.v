`default_nettype none
`timescale 1ns/1ps
// ----------------------------------------------------------------------------
// tb_native_rail -- self-checking sim for cec_native_rail.
// The whole point: the in-spec load droop (rail dips when current rises) must
// NOT trip, while PSU on/off edges, an out-of-spec drift, and a rail sag the
// load does NOT explain must. Model: rail = vnom - droop; the 4 masked current
// channels = ibias + load. "Correlated droop" sets droop = load (the rail dips
// because the load rose). With KG_SHIFT=8 and 4 current channels, KGAIN=64
// makes the load-line prediction exactly cancel a correlated droop.
//   A  correlated droop, band set above it          -> NO trip (magnitude)
//   B  BIG correlated droop, band off, load-line on  -> NO trip (residual cancels)
//   C  PSU turn-ON  (rail 0 -> nominal)              -> TRIP, cause=band
//   D  PSU turn-OFF (rail nominal -> 0)              -> TRIP, cause=band
//   E  unexplained sag (rail drops, load flat)       -> TRIP, cause=residual
//   F  out-of-spec drift below VMIN                  -> TRIP, cause=window
//   G  warm-up gate                                  -> NO trip until warmed
//   H  disarm + re-arm                               -> trips again
// Prints "PASS: ..." only if every check holds.
// ----------------------------------------------------------------------------
module tb_native_rail;
    localparam integer CH       = 8;
    localparam integer W        = 16;
    localparam integer KG_SHIFT = 8;
    localparam integer PRW      = 12;
    localparam integer POSTROLL = 8;
    localparam integer KSH      = 4;             // tau ~ 16 frames
    localparam integer WARM     = 48;
    localparam integer RAIL_CH  = 2;
    localparam [CH-1:0] CUR_MASK = 8'b0011_1001; // 4 current channels (bits 0,3,4,5)

    reg clk = 1'b0; always #5 clk = ~clk;
    reg                rst = 1'b1, arm = 1'b0, in_stb = 1'b0;
    reg  [CH*W-1:0]    in_data = {CH*W{1'b0}};
    // config (driven live; the module takes them as inputs)
    reg  [W-1:0]        vdev = 16'd1000;
    reg  signed [W-1:0] vmin = 16'sh8000, vmax = 16'sh7FFF;  // window off
    reg  signed [W-1:0] kgain = 16'sd0;
    reg  [W-1:0]        vres = 16'd0;
    wire               freeze, tripped;
    wire [CH-1:0]      trip_ch;
    wire [2:0]         trip_cause;

    cec_native_rail #(.CHANNELS(CH), .W(W), .KMAX(14), .KG_SHIFT(KG_SHIFT), .PRW(PRW)) dut (
        .clk(clk), .rst(rst), .arm(arm), .in_stb(in_stb), .in_data(in_data),
        .rail_ch(RAIL_CH[3:0]), .cur_mask(CUR_MASK), .k_shift(KSH[3:0]),
        .vdev(vdev), .vmin(vmin), .vmax(vmax), .kgain(kgain), .vres(vres),
        .postroll(POSTROLL[PRW-1:0]), .warmup(WARM[15:0]),
        .freeze(freeze), .tripped(tripped), .trip_ch(trip_ch), .trip_cause(trip_cause));

    integer fails = 0, nframe = 0, k, j, m;
    integer freeze_count = 0;
    integer vnom = 13800, ibias = 4000, load = 0, droop = 0;
    reg signed [W-1:0] smp [0:CH-1];

    task setframe; begin
        for (m = 0; m < CH; m = m + 1) begin
            if (m == RAIL_CH)        smp[m] = vnom - droop;     // 12V rail
            else if (CUR_MASK[m])    smp[m] = ibias + load;     // correlated current
            else                     smp[m] = 7000;             // ignored channel
        end
    end endtask

    task tick; begin
        setframe;
        for (j = 0; j < CH; j = j + 1) in_data[j*W +: W] = smp[j];
        @(negedge clk); in_stb = 1'b1;
        @(negedge clk); in_stb = 1'b0;
        nframe = nframe + 1;
        @(negedge clk);
    end endtask

    always @(posedge clk) if (freeze) freeze_count = freeze_count + 1;

    task chk(input cond, input [1023:0] msg); begin
        if (!cond) begin fails = fails + 1; $display("FAIL: %0s", msg); end
    end endtask

    initial begin
        repeat (3) @(negedge clk); rst = 1'b0; @(negedge clk);
        arm = 1'b1;

        // ---- warm + A: correlated droop, band (1000) set above it -> NO trip ---
        for (k = 0; k < 90; k = k + 1) begin
            load  = (k % 8) * 32;          // 0..224 per-channel swing
            droop = load;                  // rail dips because the load rose (in spec)
            tick;
        end
        chk(!tripped && freeze_count == 0, "A: in-spec correlated droop TRIPPED");

        // ---- B: BIG correlated droop, band OFF, load-line ON -> NO trip --------
        vdev = 16'd0; kgain = 16'sd64; vres = 16'd300;  // residual cancels droop
        for (k = 0; k < 30; k = k + 1) begin
            load = 3000; droop = 3000;     // huge, but fully load-explained
            tick;
        end
        chk(!tripped && freeze_count == 0, "B: load-explained big droop TRIPPED (residual didn't cancel)");

        // ---- C: PSU turn-ON (rail 0 -> nominal) -> TRIP, cause=band ------------
        arm = 1'b0; repeat (2) tick;            // disarm -> re-seed on re-arm
        vdev = 16'd1000; kgain = 16'sd0; vres = 16'd0;
        load = 0; droop = 0; vnom = 0;          // rail OFF
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < WARM + 10; k = k + 1) tick;   // baseline converges to 0
        chk(!tripped, "C: tripped while rail flat at 0");
        vnom = 13800;                            // PSU turns on
        for (k = 0; k < 20; k = k + 1) tick;
        chk(tripped, "C: turn-on did not trip");
        chk(trip_ch == (8'd1 << RAIL_CH), "C: trip_ch not the rail channel");
        chk(trip_cause[0] === 1'b1, "C: cause not BAND");
        chk(freeze_count == 1, "C: freeze did not pulse once");

        // ---- D: PSU turn-OFF (rail nominal -> 0) -> TRIP, cause=band -----------
        arm = 1'b0; repeat (2) tick;
        vnom = 13800; load = 0; droop = 0;
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < WARM + 10; k = k + 1) tick;   // baseline at nominal
        chk(!tripped, "D: tripped while rail steady at nominal");
        vnom = 0;                                // PSU turns off
        for (k = 0; k < 20; k = k + 1) tick;
        chk(tripped && trip_cause[0] === 1'b1, "D: turn-off did not band-trip");

        // ---- E: unexplained sag (rail drops, load FLAT) -> TRIP, cause=residual -
        arm = 1'b0; repeat (2) tick;
        vdev = 16'd0; kgain = 16'sd64; vres = 16'd300;  // band off, load-line on
        vnom = 13800; load = 1200; droop = 1200;        // steady load + its droop
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < WARM + 10; k = k + 1) tick;      // converge at the loaded point
        chk(!tripped, "E: tripped under steady load (residual false-fired)");
        droop = droop + 1500;                            // rail SAGS, load unchanged
        for (k = 0; k < 15; k = k + 1) tick;
        chk(tripped, "E: unexplained sag did not trip");
        chk(trip_cause[2] === 1'b1, "E: cause not RESIDUAL");
        chk(trip_ch == (8'd1 << RAIL_CH), "E: trip_ch not the rail channel");

        // ---- F: out-of-spec drift below VMIN -> TRIP, cause=window ------------
        arm = 1'b0; repeat (2) tick;
        vdev = 16'd0; kgain = 16'sd0; vres = 16'd0;       // band+residual off
        vmin = 16'sd13000; vmax = 16'sd14500;             // window on
        vnom = 13800; load = 0; droop = 0;
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < WARM + 10; k = k + 1) tick;       // in spec -> no trip
        chk(!tripped, "F: tripped while in the spec window");
        vnom = 12000;                                     // slow brownout below VMIN
        for (k = 0; k < 10; k = k + 1) tick;
        chk(tripped && trip_cause[1] === 1'b1, "F: out-of-window drift did not trip");

        // ---- G: warm-up gate -- a deviation DURING warm-up must NOT trip ------
        arm = 1'b0; repeat (2) tick;
        vmin = 16'sh8000; vmax = 16'sh7FFF;               // window off
        vdev = 16'd1000; kgain = 16'sd0; vres = 16'd0;
        vnom = 13800; load = 0; droop = 0;
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < 8; k = k + 1) tick;               // seed at 13800, still warming
        vnom = 6000;                                      // big deviation, still in warm-up
        for (k = 0; k < 8; k = k + 1) tick;
        chk(!tripped, "G: tripped during warm-up");
        vnom = 13800;                                     // recover, finish warming
        for (k = 0; k < WARM; k = k + 1) tick;
        chk(!tripped, "G: tripped while warming back at nominal");
        vnom = 6000;                                      // now warmed -> should trip
        for (k = 0; k < 20; k = k + 1) tick;
        chk(tripped && trip_cause[0] === 1'b1, "G: did not trip after warm-up");

        // ---- H: disarm + re-arm trips again ----------------------------------
        arm = 1'b0; repeat (2) tick;
        chk(!tripped, "H: tripped not cleared on disarm");
        vnom = 13800;                                     // back in band
        arm = 1'b1; freeze_count = 0;
        for (k = 0; k < WARM + 6; k = k + 1) tick;        // warm, steady -> quiet
        chk(!tripped, "H: false-fired after re-arm at steady rail");
        vnom = 6000;                                      // a fresh excursion
        for (k = 0; k < 20; k = k + 1) tick;
        chk(tripped && freeze_count >= 1, "H: did not re-trip after re-arm");

        if (fails == 0)
            $display("PASS: rail rejects in-spec + load-explained droop, trips on PSU on/off + unexplained sag + out-of-window, warm-up + re-arm");
        else
            $display("FAIL: %0d check(s) failed", fails);
        $finish;
    end

    initial begin #5_000_000; $display("FAIL: timeout"); $finish; end
endmodule
`default_nettype wire
