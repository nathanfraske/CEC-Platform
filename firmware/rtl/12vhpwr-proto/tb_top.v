`timescale 1ns/1ps
`default_nettype none
// ----------------------------------------------------------------------------
// 12vhpwr-proto testbench.
// Behavioral AD7606 stub: BUSY 4 us after CONVST, then serial mode shifting
// known channel words on DOUTA/DOUTB (MSB at CS fall, next bits on SCLK falls).
// Behavioral ESP master: mode-0, ~2 MHz, 144-bit reads; esp_read holds MOSI at
// a level (LIVE/BURST), esp_read_cmd drives a MOSI command byte (STREAM = 0x55).
// Pass criteria:
//   * boxcar decimator (piece 1, standalone): M samples -> one correct average,
//     signed, per-channel isolated, accumulator resets between windows.
//   * LIVE: two consecutive frames decode (header, seq, eight channels).
//   * BURST (fastburst): frozen native ring, consecutive sequence, payload intact.
//   * STREAM (piece 2): continuous decimated FIFO -- dropcount byte reads ZERO
//     when drained promptly (gap-free) and NONZERO after a deliberate stall.
// Run: iverilog -g2012 -o tb tb_top.v top.v cec_boxcar_decim.v cec_native_anomaly.v cec_native_rail.v ../common/cec_spi_slave.v && vvp tb
// ----------------------------------------------------------------------------
module tb_top;
    reg clk50 = 1'b0;
    always #10 clk50 = ~clk50;                 // 50 MHz

    // DUT pads
    wire adc_reset, adc_convst, adc_cs_n, adc_sclk;
    reg  adc_busy = 1'b0;
    wire adc_douta, adc_doutb;
    reg  esp_sclk = 1'b0, esp_cs_n = 1'b1, esp_mosi = 1'b0;
    wire esp_miso, esp_drdy;

    // tiny ring + FIFO + small M so the sim fills/wraps/overflows quickly
    top #(.SAMPLE_HZ(20_000), .DECIM_M(4), .DEPTH(8), .STREAM_DEPTH(8),
          .DET_KSHIFT(4), .DET_THRESH(800), .DET_WARMUP(4),
          .RAIL_KSHIFT(4), .RAIL_VDEV(800), .RAIL_WARMUP(4)) dut (
        .clk50(clk50),
        .adc_reset(adc_reset), .adc_convst(adc_convst),
        .adc_cs_n(adc_cs_n),   .adc_sclk(adc_sclk),
        .adc_busy(adc_busy),   .adc_douta(adc_douta), .adc_doutb(adc_doutb),
        .esp_sclk(esp_sclk),   .esp_mosi(esp_mosi),
        .esp_miso(esp_miso),   .esp_cs_n(esp_cs_n),   .esp_drdy(esp_drdy)
    );

    integer errors = 0;
    integer i, j;

    // ---- AD7606 stub ----
    localparam [15:0] C1=16'h1234, C2=16'h2345, C3=16'h3456, C4=16'h4567,
                      C5=16'h5678, C6=16'h6789, C7=16'h789A, C8=16'h89AB;
    reg [63:0] stubA = 64'd0, stubB = 64'd0;
    reg               det_mode = 1'b0;         // anomaly test: drive a BALANCED current set...
    reg signed [15:0] det_imb  = 16'sd0;       // ...with this imbalance added to V3 (== detector ch5)
    reg signed [15:0] rail_v6  = C6;           // rail test: drives V6 (== detector ch2 = vrail); default C6

    always @(posedge adc_convst) begin
        #50  adc_busy = 1'b1;                  // t_conv start
        #4000;                                 // 4 us conversion, OS = 000
        if (det_mode) begin
            // masked currents V3/V4/V5/V8 balanced at 5000; det_imb diverges V3.
            stubA = {C1, C2, 16'sd5000 + det_imb, 16'sd5000};   // V3(ch5)=5000+imb, V4(ch4)=5000
            stubB = {16'sd5000, rail_v6, C7, 16'sd5000};        // V5(ch3)=5000, V6(ch2=vrail)=rail_v6, V8(ch0)=5000
        end else begin
            stubA = {C1, C2, C3, C4};
            stubB = {C5, C6, C7, C8};
        end
        adc_busy = 1'b0;
    end

    always @(negedge adc_sclk) begin
        if (!adc_cs_n) begin
            stubA = {stubA[62:0], 1'b0};
            stubB = {stubB[62:0], 1'b0};
        end
    end
    assign adc_douta = adc_cs_n ? 1'b0 : stubA[63];
    assign adc_doutb = adc_cs_n ? 1'b0 : stubB[63];

    // ---- piece 1: standalone boxcar decimator under test ----
    reg          d_rst    = 1'b1;
    reg          d_in_stb = 1'b0;
    reg  [127:0] d_in     = 128'd0;
    wire         d_out_stb;
    wire [127:0] d_out;
    integer      d_out_count = 0;
    cec_boxcar_decim #(.CHANNELS(8), .W(16), .M(4)) u_dut_decim (
        .clk(clk50), .rst(d_rst), .in_stb(d_in_stb), .in_data(d_in),
        .out_stb(d_out_stb), .out_data(d_out)
    );
    always @(posedge clk50) if (d_out_stb) d_out_count <= d_out_count + 1;

    // Drive on the NEGEDGE so in_stb is unambiguously one posedge wide (a
    // posedge blocking-assign would race the DUT's own posedge sampling).
    task decim_push(input [127:0] v);
        begin
            @(negedge clk50); d_in = v; d_in_stb = 1'b1;
            @(negedge clk50); d_in_stb = 1'b0;
        end
    endtask

    // ---- ESP master stub: mode 0, ~2 MHz, MOSI held at a level (LIVE/BURST) ----
    reg [143:0] rx;
    reg [31:0]  cnt1, cnt2;
    task esp_read;
        begin
            esp_cs_n = 1'b0;
            #200;
            for (i = 0; i < 144; i = i + 1) begin
                esp_sclk = 1'b1;
                #100 rx = {rx[142:0], esp_miso};
                #150 esp_sclk = 1'b0;
                #250;
            end
            #100 esp_cs_n = 1'b1;
            #200;
        end
    endtask

    // Same, but drive an 8-bit command repeated MSB-first on MOSI (STREAM=0x55).
    task esp_read_cmd(input [7:0] cmd);
        begin
            esp_cs_n = 1'b0;
            esp_mosi = cmd[7];
            #200;
            for (i = 0; i < 144; i = i + 1) begin
                esp_mosi = cmd[7 - (i % 8)];   // present the bit before the rising edge
                #20;
                esp_sclk = 1'b1;
                #100 rx = {rx[142:0], esp_miso};
                #130 esp_sclk = 1'b0;
                #250;
            end
            #100 esp_cs_n = 1'b1;
            esp_mosi = 1'b0;
            #200;
        end
    endtask

    task check_frame(input [7:0] expect_seq);
        begin
            if (rx[143:136] !== 8'hA5) begin
                $display("FAIL: header %02x", rx[143:136]); errors = errors + 1;
            end
            if (rx[135:128] !== expect_seq) begin
                $display("FAIL: seq %0d expected %0d", rx[135:128], expect_seq);
                errors = errors + 1;
            end
            if (rx[127:0] !== {C1,C2,C3,C4,C5,C6,C7,C8}) begin
                $display("FAIL: payload %032x", rx[127:0]); errors = errors + 1;
            end
        end
    endtask

    reg [7:0] bseq0;
    task check_buf(input integer idx);
        begin
            if (rx[143:136] !== 8'hA5) begin
                $display("FAIL: buf header %02x", rx[143:136]); errors = errors + 1;
            end
            if (rx[127:0] !== {C1,C2,C3,C4,C5,C6,C7,C8}) begin
                $display("FAIL: buf payload %032x", rx[127:0]); errors = errors + 1;
            end
            if (idx == 0) bseq0 = rx[135:128];
            else if (rx[135:128] !== (bseq0 + idx[7:0])) begin
                $display("FAIL: buf seq %0d expected %0d", rx[135:128], bseq0 + idx);
                errors = errors + 1;
            end
        end
    endtask

    // STREAM frame: header 0xA5 (fresh) or 0x5A (underrun, stale -> payload not
    // checked), seq byte carries the dropcount. expect_drop = the dropcount that
    // must be present (0 = gap-free).
    task check_stream(input [7:0] expect_drop);
        begin
            if (rx[143:136] !== 8'hA5 && rx[143:136] !== 8'h5A) begin
                $display("FAIL: stream header %02x", rx[143:136]); errors = errors + 1;
            end
            if (rx[135:128] !== expect_drop) begin
                $display("FAIL: stream drop %0d expected %0d", rx[135:128], expect_drop);
                errors = errors + 1;
            end
            if (rx[143:136] === 8'hA5 && rx[127:0] !== {C1,C2,C3,C4,C5,C6,C7,C8}) begin
                $display("FAIL: stream payload %032x", rx[127:0]); errors = errors + 1;
            end
        end
    endtask

    task check_stream_dropped;          // expect the stall to have been counted
        begin
            if (rx[143:136] !== 8'hA5 && rx[143:136] !== 8'h5A) begin
                $display("FAIL: stream header %02x", rx[143:136]); errors = errors + 1;
            end
            if (rx[135:128] === 8'h00) begin
                $display("FAIL: stream dropcount 0, expected a counted overrun");
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        // ---- piece 1: decimator in isolation ----
        d_rst = 1'b1; repeat (4) @(posedge clk50); d_rst = 1'b0;
        // window A: 4x {C1..C8} -> average = {C1..C8} (datapath + signed C8 + packing)
        for (j = 0; j < 4; j = j + 1) decim_push({C1,C2,C3,C4,C5,C6,C7,C8});
        repeat (3) @(posedge clk50);
        if (d_out_count !== 1) begin
            $display("FAIL: decim window A out_count %0d (expected 1)", d_out_count);
            errors = errors + 1;
        end
        if (d_out !== {C1,C2,C3,C4,C5,C6,C7,C8}) begin
            $display("FAIL: decim window A average %032x", d_out); errors = errors + 1;
        end
        // window B: ch0 ramp 0,4,8,12 -> avg 6; others 0 (averaging + isolation + reset)
        decim_push(128'd0);  decim_push(128'd4);
        decim_push(128'd8);  decim_push(128'd12);
        repeat (3) @(posedge clk50);
        if (d_out_count !== 2) begin
            $display("FAIL: decim window B out_count %0d (expected 2)", d_out_count);
            errors = errors + 1;
        end
        if (d_out !== 128'd6) begin
            $display("FAIL: decim window B average %032x (expected 6)", d_out);
            errors = errors + 1;
        end

        // ---- through POR (~1.31 ms) and the RESET pulse ----
        #1_400_000;
        if (adc_reset !== 1'b0) begin
            $display("FAIL: adc_reset stuck high after POR window");
            errors = errors + 1;
        end

        // ---- LIVE ----
        wait (esp_drdy === 1'b1);
        esp_read; check_frame(8'd1);
        if (esp_drdy !== 1'b0) begin
            $display("FAIL: DRDY did not clear after read"); errors = errors + 1;
        end
        wait (esp_drdy === 1'b1);
        esp_read; check_frame(8'd2);

        // ---- BURST (fastburst): let the DEPTH=8 ring fill + wrap, then read out ----
        #1_000_000;
        esp_mosi = 1'b1;
        esp_read;                 // arm (returns the live frame, discarded)
        esp_read; check_buf(0);
        esp_read; check_buf(1);
        esp_read; check_buf(2);
        esp_read; check_buf(3);
        esp_mosi = 1'b0;

        // ---- STREAM (piece 2): continuous decimated FIFO ----
        // Prime the mode (cmd_reg <- 0x55, FIFO session starts at drop=0), then
        // let a few decimated samples land (STREAM_DEPTH=8, no overflow yet).
        esp_read_cmd(8'h55);                 // prime: returns non-stream, discard
        #1_000_000;                          // ~5 decimated samples (< depth 8)
        // (a) NOMINAL: drain promptly -> the FIFO never overruns -> dropcount == 0.
        esp_read_cmd(8'h55); check_stream(8'd0);
        esp_read_cmd(8'h55); check_stream(8'd0);
        esp_read_cmd(8'h55); check_stream(8'd0);
        // (b) STARVED: stop reading; the depth-8 FIFO overruns and counts the loss.
        #3_000_000;
        esp_read_cmd(8'h55); check_stream_dropped;
        esp_read_cmd(8'h55); check_stream_dropped;
        esp_mosi = 1'b0;

        // ---- STATUS (free-running native-frame counter for the rate check) ----
        esp_read_cmd(8'h33);                    // prime: cmd_reg <- 0x33
        esp_read_cmd(8'h33);                    // status frame
        if (rx[143:136] !== 8'h5C) begin
            $display("FAIL: status header %02x (expected 5C)", rx[143:136]); errors = errors + 1;
        end
        cnt1 = rx[127:96];                      // frame_count: ch0<<16 | ch1
        if (cnt1 === 32'd0) begin
            $display("FAIL: status frame_count is 0 (no native frames counted)"); errors = errors + 1;
        end
        #1_000_000;                             // ~20 more native frames @ 20 kHz
        esp_read_cmd(8'h33);                    // status frame again
        cnt2 = rx[127:96];
        if (!(cnt2 > cnt1)) begin
            $display("FAIL: status counter did not advance (%0d -> %0d)", cnt1, cnt2);
            errors = errors + 1;
        end
        esp_mosi = 1'b0;

        // ---- NATIVE ANOMALY DETECTOR: a BALANCED current set must NOT trip; a
        //      single-pin SHARE divergence (V3 == ch5) must trip on ch5 + freeze
        //      the ring; STATUS V3 reports it; disarm/re-arm clears it. ---------
        det_mode = 1'b1; det_imb = 16'sd0;       // balanced masked currents (5000 each)
        esp_read_cmd(8'h44);                      // ARM (sticky)
        #500_000;                                // past DET_WARMUP=4 on the balanced set
        esp_read_cmd(8'h33); esp_read_cmd(8'h33);
        if (rx[95] !== 1'b0) begin               // V3 bit15 = tripped -- MUST be 0 on a balanced load
            $display("FAIL: anomaly tripped on a BALANCED load (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        det_imb = 16'sd500;                      // V3 (ch5) hogs ~+500 -> a share divergence
        #1_000_000;                              // average follows + post-roll + centered freeze
        esp_read_cmd(8'h33); esp_read_cmd(8'h33);
        if (rx[143:136] !== 8'h5C) begin
            $display("FAIL: anomaly status header %02x", rx[143:136]); errors = errors + 1;
        end
        if (rx[95] !== 1'b1) begin               // tripped
            $display("FAIL: anomaly did not trip on a share divergence (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        if (rx[85] !== 1'b1) begin               // trip_ch bit5 = ch5 (V3) -- the diverging pin
            $display("FAIL: trip_ch ch5 (V3) not set (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        if (rx[94] !== 1'b1) begin               // det_frozen
            $display("FAIL: anomaly did not freeze the ring (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        esp_mosi = 1'b1;                          // read the centered ring (0xFF)
        esp_read;                                // discard (cmd_reg 0x33 -> 0xFF)
        esp_read;                                // ring frame
        if (rx[143:136] !== 8'hA5) begin
            $display("FAIL: anomaly-frozen ring header %02x", rx[143:136]); errors = errors + 1;
        end
        esp_mosi = 1'b0;
        det_imb = 16'sd0;                         // back to balanced
        esp_read_cmd(8'h46);                      // DISARM -> clears trip + freeze, ring resumes
        esp_read_cmd(8'h44);                      // RE-ARM
        #500_000;                                 // warm-up on the balanced set
        esp_read_cmd(8'h33); esp_read_cmd(8'h33);
        if (rx[95] !== 1'b0) begin                // tripped cleared (balanced, re-armed)
            $display("FAIL: anomaly tripped not cleared after disarm/re-arm (V3=%04x)", rx[95:80]); errors = errors + 1;
        end

        // ---- NATIVE RAIL DETECTOR: the rail (V6 = detector ch2 = vrail) is steady
        //      and the re-arm check above already saw tripped=0; a SPIKE on V6 must
        //      trip on ch2 + freeze the ring with rail_cause=BAND; disarm/re-arm
        //      clears. Currents stay balanced so the imbalance detector is quiet. -
        rail_v6 = C6 + 16'sd4000;                 // +4000-code rail spike (>> RAIL_VDEV 800)
        #1_000_000;                               // post-roll + centered freeze
        esp_read_cmd(8'h33); esp_read_cmd(8'h33);
        if (rx[95] !== 1'b1) begin                // tripped
            $display("FAIL: rail did not trip on a spike (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        if (rx[82] !== 1'b1) begin                // trip_ch bit2 = ch2 (V6 = vrail)
            $display("FAIL: rail trip_ch ch2 (vrail) not set (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        if (rx[91] !== 1'b1) begin                // rail_cause bit0 = BAND
            $display("FAIL: rail cause not BAND (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        if (rx[94] !== 1'b1) begin                // det_frozen
            $display("FAIL: rail did not freeze the ring (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        esp_mosi = 1'b1;                          // read the centered ring (0xFF)
        esp_read; esp_read;
        if (rx[143:136] !== 8'hA5) begin
            $display("FAIL: rail-frozen ring header %02x", rx[143:136]); errors = errors + 1;
        end
        esp_mosi = 1'b0;
        rail_v6 = C6;                             // rail back to steady
        esp_read_cmd(8'h46);                      // DISARM -> clears trip + freeze
        esp_read_cmd(8'h44);                      // RE-ARM (seeds at steady C6)
        #500_000;                                 // warm-up on the steady rail
        esp_read_cmd(8'h33); esp_read_cmd(8'h33);
        if (rx[95] !== 1'b0) begin                // cleared
            $display("FAIL: rail tripped not cleared after disarm/re-arm (V3=%04x)", rx[95:80]); errors = errors + 1;
        end
        esp_read_cmd(8'h46);                      // leave both disarmed

        det_mode = 1'b0;
        esp_mosi = 1'b0;

        if (errors == 0)
            $display("PASS: decimator average, LIVE seq, BURST ring, STREAM dropcount, STATUS rate counter, NATIVE-ANOMALY balanced-pass+divergence-trip+rearm, NATIVE-RAIL steady-pass+spike-trip+rearm");
        else
            $display("FAILED with %0d errors", errors);
        $finish;
    end

    initial begin
        #30_000_000;
        $display("FAIL: timeout");
        $finish;
    end
endmodule
`default_nettype wire
