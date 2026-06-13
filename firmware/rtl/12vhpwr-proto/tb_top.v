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
// Run: iverilog -g2012 -o tb tb_top.v top.v cec_boxcar_decim.v ../common/cec_spi_slave.v && vvp tb
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
    top #(.SAMPLE_HZ(20_000), .DECIM_M(4), .DEPTH(8), .STREAM_DEPTH(8)) dut (
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

    always @(posedge adc_convst) begin
        #50  adc_busy = 1'b1;                  // t_conv start
        #4000;                                 // 4 us conversion, OS = 000
        stubA = {C1, C2, C3, C4};
        stubB = {C5, C6, C7, C8};
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

        if (errors == 0)
            $display("PASS: decimator average, LIVE seq, BURST ring, STREAM dropcount (gap-free + starved)");
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
