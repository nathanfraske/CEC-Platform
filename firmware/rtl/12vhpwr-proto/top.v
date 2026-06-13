`default_nettype none
// ----------------------------------------------------------------------------
// 12vhpwr-proto top.
// AD7606 in serial mode (OS=000 strapped, +/-5 V, internal ref):
//   pulse RESET once, pace CONVST, wait BUSY, clock 64 SCLKs at 12.5 MHz,
//   shift V1-V4 off DOUTA and V5-V8 off DOUTB, latch an 8x16 frame.
// ESP32-P4 reads frames as SPI slave: 18 bytes = 0xA5, seq, V1..V8 MSB first.
//
// TWO read paths over the one SPI link, selected by MOSI:
//   MOSI low  -> LIVE: returns the latest frame (DRDY high while one waits).
//                The 5 Hz monitor + the ESP-paced `burst` use this; the ESP's
//                per-frame handshake caps it ~12 kHz regardless of read speed.
//   MOSI high -> BUFFERED: every frame is captured into a DEPTH-deep BRAM ring
//                at the NATIVE rate (no drops, no per-frame handshake); the ESP
//                holds MOSI high to freeze the ring and stream the whole window
//                out (1st read arms+discards, then consecutive ring frames).
//                This is the path to the AD7606's native rate / the ~80 kHz
//                inductive corner -- capture is FPGA-paced, immune to ESP jitter.
// Pin map: rtl/12vhpwr-proto/12vhpwr-proto.cst (dock 2x20 GPIO field, doc section 9).
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module top #(
    parameter integer CLK_HZ    = 50_000_000,
    // Native capture pace = "run at max" for oversample + host-side decimate.
    // 200 kHz is the AD7606 OS=000 throughput target; the free-running pacer
    // self-limits to what the FSM can service, and `fastburst` reports the real
    // achieved rate. The CURRENT sequential conv->read at 12.5 MHz SCLK caps it
    // well below 200 kSPS -- reaching the full 200 kSPS needs (a) the read SCLK
    // toward the AD7606's ~23.5 MHz max and (b) a PIPELINED FSM (read frame N
    // while converting N+1: throughput -> max(conv ~4us, read) -> ~200 kSPS).
    // The host decimates 200 k -> ~25 kSPS useful band (sqrt(N) noise drop).
    parameter integer SAMPLE_HZ = 200_000,
    // Capture-ring depth in frames (BRAM). 2048 x 144b = 288 kbit. The sim
    // overrides this small so the ring fills + wraps quickly.
    parameter integer DEPTH     = 2048
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
    localparam integer AW  = $clog2(DEPTH);      // ring address width

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

    // ---- free-running conversion pacer ----
    // A 1-clock do_conv pulse every DIV clocks, INDEPENDENT of the read FSM,
    // so the CONVST cadence is an exact CLK_HZ/SAMPLE_HZ. The convert+read
    // (~9 us: ~4 us BUSY + ~5 us 64-SCLK read) must fit inside one DIV window
    // (20 us at 50 kHz) -- it does, ~10 us to spare. If SAMPLE_HZ is pushed
    // past the read-limited ceiling, ticks that land mid-read are simply
    // skipped (the rate floors at the read time) -- never a corrupt frame.
    reg [31:0] pace    = 32'd0;
    reg        do_conv = 1'b0;
    always @(posedge clk50) begin
        if (rst) begin
            pace <= 32'd0; do_conv <= 1'b0;
        end else if (pace >= DIV-1) begin
            pace <= 32'd0; do_conv <= 1'b1;
        end else begin
            pace <= pace + 1'b1; do_conv <= 1'b0;
        end
    end

    // ---- acquisition FSM ----
    localparam [2:0] S_RST=3'd0, S_IDLE=3'd1, S_CONV=3'd2, S_WHI=3'd3,
                     S_WLO=3'd4, S_GAP=3'd5, S_READ=3'd6, S_LATCH=3'd7;
    reg [2:0]   st     = S_RST;
    reg [3:0]   k      = 4'd0;
    reg [1:0]   ph     = 2'd0;       // SCLK phase counter: 12.5 MHz from 50 MHz
    reg [6:0]   bit_n  = 7'd0;       // 0..63
    reg [63:0]  shA    = 64'd0;      // V1..V4, MSB first
    reg [63:0]  shB    = 64'd0;      // V5..V8, MSB first
    reg [127:0] frame  = 128'd0;
    reg [7:0]   seq    = 8'd0;
    reg         drdy   = 1'b0;
    reg         cap_stb = 1'b0;     // 1-clk: a frame completed -> capture it
    wire        esp_busy;
    wire        esp_done;

    always @(posedge clk50) begin
        if (rst) begin
            st <= S_RST; k <= 4'd0;
            adc_reset <= 1'b0; adc_convst <= 1'b0;
            adc_cs_n  <= 1'b1; adc_sclk   <= 1'b0;
            drdy <= 1'b0; seq <= 8'd0; cap_stb <= 1'b0;
        end else begin
            if (esp_done) drdy <= 1'b0;
            cap_stb <= 1'b0;
            case (st)
                S_RST: begin                       // RESET high for 10 clks = 200 ns
                    adc_reset <= 1'b1;
                    k <= k + 1'b1;
                    if (k == 4'd9) begin
                        adc_reset <= 1'b0;
                        st <= S_IDLE;
                    end
                end
                S_IDLE: if (do_conv) begin k <= 4'd0; st <= S_CONV; end
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
                    // LIVE single-frame path (5 Hz monitor / slow burst): held
                    // stable under an active CS, so dropped while the ESP reads.
                    if (!esp_busy) begin
                        frame <= {shA, shB};
                        seq   <= seq + 1'b1;
                        drdy  <= 1'b1;
                    end
                    // CAPTURE path: EVERY completed frame goes to the ring (the
                    // ring write is independent of the live frame register, so
                    // it never drops -- this is what makes the buffered readout
                    // a gap-free native-rate window).
                    cap_stb <= 1'b1;
                    st <= S_IDLE;
                end
                default: st <= S_RST;
            endcase
        end
    end

    // ---- capture ring + buffered readout ----------------------------------
    // Every completed frame lands in a DEPTH-deep BRAM ring at the native rate.
    // The ESP reads the whole window by holding MOSI HIGH across a run of
    // transactions: the FIRST high transaction ARMS (freezes the ring + points
    // at the oldest frame; its returned data is the still-live frame, discarded
    // by the host), and each subsequent high transaction returns the next ring
    // frame {0xA5, ring-seq, V1..V8} and advances. A MOSI-low (normal) read
    // resumes the fill; a stalled readout auto-resumes via the watchdog. This
    // decouples capture (uniform, FPGA-paced, gap-free) from the slow ESP read.
    reg [143:0]  cap_buf [0:DEPTH-1];
    reg [AW-1:0] wr_ptr  = {AW{1'b0}};
    reg [7:0]    cap_seq = 8'd0;
    reg [1:0]    mosi_s  = 2'b00;
    reg          busy_d  = 1'b0;
    reg          frozen  = 1'b0;
    reg [AW-1:0] rd_ptr  = {AW{1'b0}};
    reg [143:0]  rd_data = 144'd0;
    reg [23:0]   wdog    = 24'd0;          // ~0.33 s stalled -> auto-resume fill

    always @(posedge clk50) begin
        mosi_s  <= {mosi_s[0], esp_mosi};
        busy_d  <= esp_busy;
        rd_data <= cap_buf[rd_ptr];        // registered (BRAM) read port
        if (rst) begin
            wr_ptr <= {AW{1'b0}}; cap_seq <= 8'd0;
            frozen <= 1'b0; rd_ptr <= {AW{1'b0}}; wdog <= 24'd0;
        end else begin
            if (cap_stb && !frozen) begin  // write port: capture this frame
                cap_buf[wr_ptr] <= {8'hA5, cap_seq, shA, shB};
                wr_ptr  <= wr_ptr  + 1'b1;
                cap_seq <= cap_seq + 1'b1;
            end
            if (esp_busy & ~busy_d) begin  // transaction start (~cs_fall)
                wdog <= 24'd0;
                if (mosi_s[1]) begin
                    if (!frozen) begin frozen <= 1'b1; rd_ptr <= wr_ptr; end
                end else begin
                    frozen <= 1'b0;
                end
            end else if (frozen) begin
                wdog <= wdog + 1'b1;
                if (&wdog) frozen <= 1'b0;
            end
            if (frozen && esp_done) rd_ptr <= rd_ptr + 1'b1;
        end
    end

    // ---- ESP link: 18-byte payload = header, sequence, eight channels ----
    // frozen -> stream the ring (rd_data); else the live latest frame.
    cec_spi_slave #(.FRAME_BITS(144)) u_esp (
        .clk        (clk50),
        .rst        (rst),
        .frame      (frozen ? rd_data : {8'hA5, seq, frame}),
        .sclk       (esp_sclk),
        .cs_n       (esp_cs_n),
        .miso       (esp_miso),
        .busy       (esp_busy),
        .frame_done (esp_done)
    );

    assign esp_drdy = drdy;
endmodule
`default_nettype wire
