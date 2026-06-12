`default_nettype none
// ----------------------------------------------------------------------------
// 12vhpwr-proto top, bring-up v0.
// AD7606 in serial mode (OS=000 strapped, +/-5 V, internal ref):
//   pulse RESET once, pace CONVST, wait BUSY, clock 64 SCLKs at 12.5 MHz,
//   shift V1-V4 off DOUTA and V5-V8 off DOUTB, latch an 8x16 frame.
// ESP32-P4 reads frames as SPI slave: 18 bytes = 0xA5, seq, V1..V8 MSB first.
// DRDY is high while an unread frame is waiting.
// Pin map: rtl/12vhpwr-proto/12vhpwr-proto.cst (dock 2x20 GPIO field, doc section 9).
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module top #(
    parameter integer CLK_HZ    = 50_000_000,
    parameter integer SAMPLE_HZ = 1_000          // v0 pace; raise after step 3
)(
    input  wire clk50,
    // AD7606 module (silk: RST, CA, CS, RD, BUSY, D7, D8)
    output reg  adc_reset,
    output reg  adc_convst,
    output reg  adc_cs_n,
    output reg  adc_sclk,
    input  wire adc_busy,
    input  wire adc_douta,
    input  wire adc_doutb,
    // ESP32-P4 SPI link (this side is the slave)
    input  wire esp_sclk,
    input  wire esp_mosi,
    output wire esp_miso,
    input  wire esp_cs_n,
    output wire esp_drdy
);
    localparam integer DIV = CLK_HZ / SAMPLE_HZ;

    // ---- power-on reset: ~1.3 ms, then a 200 ns ADC reset pulse ----
    reg [16:0] por = 17'd0;
    wire por_done = por[16];
    always @(posedge clk50) if (!por_done) por <= por + 1'b1;
    wire rst = ~por_done;

    // ---- pad synchronizers ----
    reg [1:0] busy_s = 2'b00, da_s = 2'b00, db_s = 2'b00;
    always @(posedge clk50) begin
        busy_s <= {busy_s[0], adc_busy};
        da_s   <= {da_s[0],   adc_douta};
        db_s   <= {db_s[0],   adc_doutb};
    end

    // ---- acquisition FSM ----
    localparam [2:0] S_RST=3'd0, S_IDLE=3'd1, S_CONV=3'd2, S_WHI=3'd3,
                     S_WLO=3'd4, S_GAP=3'd5, S_READ=3'd6, S_LATCH=3'd7;
    reg [2:0]   st     = S_RST;
    reg [31:0]  pace   = 32'd0;
    reg [3:0]   k      = 4'd0;
    reg [1:0]   ph     = 2'd0;       // SCLK phase counter: 12.5 MHz from 50 MHz
    reg [6:0]   bit_n  = 7'd0;       // 0..63
    reg [63:0]  shA    = 64'd0;      // V1..V4, MSB first
    reg [63:0]  shB    = 64'd0;      // V5..V8, MSB first
    reg [127:0] frame  = 128'd0;
    reg [7:0]   seq    = 8'd0;
    reg         drdy   = 1'b0;
    wire        esp_busy;
    wire        esp_done;

    always @(posedge clk50) begin
        if (rst) begin
            st <= S_RST; k <= 4'd0; pace <= 32'd0;
            adc_reset <= 1'b0; adc_convst <= 1'b0;
            adc_cs_n  <= 1'b1; adc_sclk   <= 1'b0;
            drdy <= 1'b0; seq <= 8'd0;
        end else begin
            if (esp_done) drdy <= 1'b0;
            case (st)
                S_RST: begin                       // RESET high for 10 clks = 200 ns
                    adc_reset <= 1'b1;
                    k <= k + 1'b1;
                    if (k == 4'd9) begin
                        adc_reset <= 1'b0;
                        pace <= 32'd0;
                        st <= S_IDLE;
                    end
                end
                S_IDLE: begin
                    pace <= pace + 1'b1;
                    if (pace >= DIV-1) begin
                        pace <= 32'd0; k <= 4'd0; st <= S_CONV;
                    end
                end
                S_CONV: begin                      // CONVST high 3 clks = 60 ns
                    adc_convst <= 1'b1;
                    k <= k + 1'b1;
                    if (k == 4'd2) begin
                        adc_convst <= 1'b0;
                        st <= S_WHI;
                    end
                end
                S_WHI: if (busy_s[1]) st <= S_WLO;
                S_WLO: if (!busy_s[1]) begin k <= 4'd0; st <= S_GAP; end
                S_GAP: begin                       // settle, then CS low with SCLK low
                    k <= k + 1'b1;
                    if (k == 4'd3) begin
                        adc_cs_n <= 1'b0;
                        ph <= 2'd0; bit_n <= 7'd0;
                        st <= S_READ;
                    end
                end
                S_READ: begin
                    ph <= ph + 1'b1;
                    case (ph)
                        2'd1: adc_sclk <= 1'b1;    // rising edge entering phase 2
                        2'd3: begin                // sample late-high, fall entering 0
                            adc_sclk <= 1'b0;
                            shA <= {shA[62:0], da_s[1]};
                            shB <= {shB[62:0], db_s[1]};
                            bit_n <= bit_n + 1'b1;
                            if (bit_n == 7'd63) begin
                                adc_cs_n <= 1'b1;
                                st <= S_LATCH;
                            end
                        end
                        default: ;
                    endcase
                end
                S_LATCH: begin
                    // Skip the update if the ESP is mid-read; the frame must
                    // stay stable under an active CS. The sample is dropped.
                    if (!esp_busy) begin
                        frame <= {shA, shB};
                        seq   <= seq + 1'b1;
                        drdy  <= 1'b1;
                    end
                    st <= S_IDLE;
                end
                default: st <= S_RST;
            endcase
        end
    end

    // ---- ESP link: 18-byte payload = header, sequence, eight channels ----
    cec_spi_slave #(.FRAME_BITS(144)) u_esp (
        .clk        (clk50),
        .rst        (rst),
        .frame      ({8'hA5, seq, frame}),
        .sclk       (esp_sclk),
        .cs_n       (esp_cs_n),
        .miso       (esp_miso),
        .busy       (esp_busy),
        .frame_done (esp_done)
    );

    assign esp_drdy = drdy;

    // MOSI is unused in v0 (read-only link); keep the pad in the port list so
    // the .cst stays complete for later command traffic.
    wire unused_mosi = esp_mosi;
endmodule
`default_nettype wire
