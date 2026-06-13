`timescale 1ns/1ps
`default_nettype none
// ----------------------------------------------------------------------------
// 12vhpwr-proto v0 testbench.
// Behavioral AD7606 stub: BUSY 4 us after CONVST, then serial mode shifting
// known channel words on DOUTA/DOUTB (MSB at CS fall, next bits on SCLK falls).
// Behavioral ESP master: mode-0, 2 MHz, 144-bit reads gated on DRDY.
// Pass criteria: two consecutive frames decode with correct header, an
// incrementing sequence, and all eight channel words intact.
// Run: iverilog -g2012 -o tb tb_top.v top.v ../common/cec_spi_slave.v && vvp tb
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

    top #(.SAMPLE_HZ(20_000), .DEPTH(8)) dut (   // 50 us pace, tiny ring for the sim
        .clk50(clk50),
        .adc_reset(adc_reset), .adc_convst(adc_convst),
        .adc_cs_n(adc_cs_n),   .adc_sclk(adc_sclk),
        .adc_busy(adc_busy),   .adc_douta(adc_douta), .adc_doutb(adc_doutb),
        .esp_sclk(esp_sclk),   .esp_mosi(esp_mosi),
        .esp_miso(esp_miso),   .esp_cs_n(esp_cs_n),   .esp_drdy(esp_drdy)
    );

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

    // MSB valid at CS fall; shift on SCLK falling edges while CS low
    always @(negedge adc_sclk) begin
        if (!adc_cs_n) begin
            stubA = {stubA[62:0], 1'b0};
            stubB = {stubB[62:0], 1'b0};
        end
    end
    assign adc_douta = adc_cs_n ? 1'b0 : stubA[63];
    assign adc_doutb = adc_cs_n ? 1'b0 : stubB[63];

    // ---- ESP master stub: mode 0, ~2 MHz ----
    reg [143:0] rx;
    integer i;
    task esp_read;
        begin
            esp_cs_n = 1'b0;
            #200;
            for (i = 0; i < 144; i = i + 1) begin
                esp_sclk = 1'b1;               // rising: master samples
                #100 rx = {rx[142:0], esp_miso};
                #150 esp_sclk = 1'b0;          // falling: slave shifts
                #250;
            end
            #100 esp_cs_n = 1'b1;
            #200;
        end
    endtask

    integer errors = 0;
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

    // Buffered-readout check: header + payload intact, sequence consecutive.
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

    initial begin
        // through POR (~1.31 ms) and the RESET pulse
        #1_400_000;
        if (adc_reset !== 1'b0) begin
            $display("FAIL: adc_reset stuck high after POR window");
            errors = errors + 1;
        end

        wait (esp_drdy === 1'b1);
        esp_read; check_frame(8'd1);
        if (esp_drdy !== 1'b0) begin
            $display("FAIL: DRDY did not clear after read"); errors = errors + 1;
        end

        wait (esp_drdy === 1'b1);
        esp_read; check_frame(8'd2);

        // ---- buffered-readout (fastburst) test ----
        // Let the tiny DEPTH=8 ring fill + wrap (>8 frames at 50 us), then read
        // it out by holding MOSI high: the 1st read ARMS (discard), the next
        // reads walk the ring with a consecutive sequence and intact payload.
        #1_000_000;
        esp_mosi = 1'b1;
        esp_read;                 // arm (returns the live frame, discarded)
        esp_read; check_buf(0);
        esp_read; check_buf(1);
        esp_read; check_buf(2);
        esp_read; check_buf(3);
        esp_mosi = 1'b0;

        if (errors == 0) $display("PASS: frames intact, seq advances, DRDY + buffered readout clean");
        else             $display("FAILED with %0d errors", errors);
        $finish;
    end

    initial begin
        #20_000_000;
        $display("FAIL: timeout");
        $finish;
    end
endmodule
`default_nettype wire
