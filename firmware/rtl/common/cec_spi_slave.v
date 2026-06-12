`default_nettype none
// ----------------------------------------------------------------------------
// CEC common RTL: oversampled SPI slave, mode 0, MSB first, read-only payload.
// Fabric clock must be >= 5x the SPI clock (50 MHz fabric, <= 5 MHz SPI rec.).
// The payload is latched on the CS falling edge, so the producer must hold
// `frame` stable while `busy` is high.
// Shared between 12vhpwr-proto and FPGA-Max targets.
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module cec_spi_slave #(
    parameter integer FRAME_BITS = 144
)(
    input  wire                  clk,
    input  wire                  rst,
    input  wire [FRAME_BITS-1:0] frame,       // data to present, sampled at CS fall
    input  wire                  sclk,        // SPI pad inputs (async)
    input  wire                  cs_n,
    output wire                  miso,
    output reg                   busy,        // high while CS low (synced)
    output reg                   frame_done   // 1-clk pulse: full frame was read
);
    // 2/3-stage synchronizers into the fabric clock domain
    reg [2:0] sclk_s = 3'b000;
    reg [2:0] cs_s   = 3'b111;
    always @(posedge clk) begin
        sclk_s <= {sclk_s[1:0], sclk};
        cs_s   <= {cs_s[1:0],   cs_n};
    end
    wire sclk_rise = (sclk_s[2:1] == 2'b01);
    wire sclk_fall = (sclk_s[2:1] == 2'b10);
    wire cs_fall   = (cs_s[2:1]   == 2'b10);
    wire cs_rise   = (cs_s[2:1]   == 2'b01);
    wire cs_act    = ~cs_s[1];

    reg [FRAME_BITS-1:0] sh = {FRAME_BITS{1'b0}};
    reg [15:0]           bitcnt = 16'd0;

    always @(posedge clk) begin
        frame_done <= 1'b0;
        busy       <= cs_act;
        if (rst) begin
            bitcnt <= 16'd0;
        end else begin
            if (cs_fall) begin
                sh     <= frame;            // MSB valid before the first rising edge
                bitcnt <= 16'd0;
            end else if (cs_act && sclk_fall) begin
                sh <= {sh[FRAME_BITS-2:0], 1'b0};   // mode 0: change on falling
            end else if (cs_act && sclk_rise) begin
                bitcnt <= bitcnt + 1'b1;            // master samples on rising
            end
            if (cs_rise && (bitcnt >= FRAME_BITS[15:0]))
                frame_done <= 1'b1;
        end
    end

    assign miso = sh[FRAME_BITS-1];
endmodule
`default_nettype wire
