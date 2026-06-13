`default_nettype none
// ----------------------------------------------------------------------------
// 12vhpwr-proto top.
// AD7606 in serial mode (OS=000 strapped, +/-5 V, internal ref):
//   pulse RESET once, pace CONVST, wait BUSY, clock 64 SCLKs at 12.5 MHz,
//   shift V1-V4 off DOUTA and V5-V8 off DOUTB, latch an 8x16 frame.
// ESP32-P4 reads frames as SPI slave: 18 bytes = 0xA5, seq, V1..V8 MSB first.
//
// THREE read paths over the one SPI link, selected by the MOSI fill byte. The
// fabric latches the frame source at CS-fall, so a mode takes effect on the
// transaction AFTER the one that carried its command byte (send the command,
// discard one frame, then read) -- the same arm-and-discard idiom the burst
// path already uses.
//   0x00 LIVE   -> the latest single frame (DRDY high while one waits). The
//                  5 Hz monitor + `frame`/`burst` use this; the ESP's per-frame
//                  handshake + console formatting caps it ~12-13 kHz.
//   0xFF BURST  -> the DEPTH-deep native-rate ring, frozen on the first 0xFF
//                  transaction and streamed out (`fastburst`): a gap-free
//                  native-rate window. UNCHANGED from the v0 design; still keyed
//                  off the MOSI level (0xFF MSB=1) so fastburst is untouched.
//   0x55 STREAM -> the CONTINUOUS path (piece 1+2): every native frame is boxcar-
//                  decimated by DECIM_M (cec_boxcar_decim) into a free-running
//                  FIFO, drained continuously. The frame's seq byte carries the
//                  saturating DROPPED-SAMPLE COUNT (FIFO overrun = ESP too slow),
//                  and the header is 0x5A instead of 0xA5 on an underrun read
//                  (FIFO momentarily empty = ESP too fast) -- so a stall is a
//                  NUMBER in the record, never silently missing time.
// Pin map: rtl/12vhpwr-proto/12vhpwr-proto.cst (dock 2x20 GPIO field, doc section 9).
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module top #(
    parameter integer CLK_HZ    = 50_000_000,
    // NATIVE sample rate (A2: explicit, not a comment). The free-running pacer
    // targets this; the sequential conv->read FSM self-limits to what it can
    // service (v0 ~107k at 12.5 MHz read SCLK; an overlapped-read FSM would push
    // toward ~195k -- a separate, bench-validated change). `fastburst`/the host
    // derive the TRUE achieved native rate from the frame cadence.
    parameter integer SAMPLE_HZ = 200_000,
    // Boxcar decimation factor for the continuous stream (MUST be a power of two).
    // Stream rate = SAMPLE_HZ / DECIM_M. 200k/8 = 25k; if the bench native is the
    // v0 ~107k, set DECIM_M 4 -> ~27k. M tracks native: it is NOT pinned to either
    // FSM speed -- retune DECIM_M to keep the stream near 25 kSPS.
    parameter integer DECIM_M   = 8,
    // Burst capture-ring depth in frames (BRAM). 2048 x 144b = 288 kbit.
    parameter integer DEPTH     = 2048,
    // Continuous-stream FIFO depth in frames (BRAM). 2048 x 144b = 288 kbit;
    // 2048 @ 25k = ~80 ms of ESP drain-jitter slack. NOTE both BRAMs together are
    // ~0.57 Mbit -- confirm against the GW5A-25 BSRAM budget at Gowin P&R; drop
    // STREAM_DEPTH if tight (the stream is slow, 1024 = ~40 ms still ample).
    parameter integer STREAM_DEPTH = 2048
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
    localparam integer AW  = $clog2(DEPTH);          // burst ring address width
    localparam integer SAW = $clog2(STREAM_DEPTH);   // stream FIFO address width

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
    reg [1:0]   ph     = 2'd0;
    reg [6:0]   bit_n  = 7'd0;
    reg [63:0]  shA    = 64'd0;
    reg [63:0]  shB    = 64'd0;
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
                S_RST: begin
                    adc_reset <= 1'b1;
                    k <= k + 1'b1;
                    if (k == 4'd9) begin
                        adc_reset <= 1'b0;
                        st <= S_IDLE;
                    end
                end
                S_IDLE: if (do_conv) begin k <= 4'd0; st <= S_CONV; end
                S_CONV: begin
                    adc_convst <= 1'b1;
                    k <= k + 1'b1;
                    if (k == 4'd2) begin
                        adc_convst <= 1'b0;
                        st <= S_WHI;
                    end
                end
                S_WHI: if (busy_s[1]) st <= S_WLO;
                S_WLO: if (!busy_s[1]) begin k <= 4'd0; st <= S_GAP; end
                S_GAP: begin
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
                        2'd1: adc_sclk <= 1'b1;
                        2'd3: begin
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
                    // LIVE single-frame path: held stable under an active CS, so
                    // dropped while the ESP reads.
                    if (!esp_busy) begin
                        frame <= {shA, shB};
                        seq   <= seq + 1'b1;
                        drdy  <= 1'b1;
                    end
                    // CAPTURE strobe: EVERY completed frame -> burst ring + decimator,
                    // independent of the live register so neither path drops.
                    cap_stb <= 1'b1;
                    st <= S_IDLE;
                end
                default: st <= S_RST;
            endcase
        end
    end

    // ---- ESP MOSI command decode (in the fabric domain, slave untouched) -----
    // The ESP holds a uniform fill byte across the transaction; accumulate it
    // MSB-first and latch at frame end. cmd_reg is then the command for the NEXT
    // transaction (latched before its CS-fall). Only 0x55 (STREAM) is decoded
    // here; LIVE/BURST stay on the MOSI level the burst block already samples.
    reg [2:0] esclk_s = 3'b000;
    reg [1:0] emosi_s = 2'b00;
    always @(posedge clk50) begin
        esclk_s <= {esclk_s[1:0], esp_sclk};
        emosi_s <= {emosi_s[0],   esp_mosi};
    end
    wire esclk_rise = (esclk_s[2:1] == 2'b01);
    reg [7:0] cmd_accum = 8'd0;
    reg [7:0] cmd_reg   = 8'd0;
    always @(posedge clk50) begin
        if (rst) begin
            cmd_accum <= 8'd0; cmd_reg <= 8'd0;
        end else begin
            if (esp_busy && esclk_rise) cmd_accum <= {cmd_accum[6:0], emosi_s[1]};
            if (esp_done)               cmd_reg   <= cmd_accum;
        end
    end
    wire stream_sel = (cmd_reg == 8'h55);

    // ---- piece 1: boxcar decimator (native frames -> ~25 kSPS) --------------
    wire         decim_stb;
    wire [127:0] decim_data;
    cec_boxcar_decim #(.CHANNELS(8), .W(16), .M(DECIM_M)) u_decim (
        .clk      (clk50),
        .rst      (rst),
        .in_stb   (cap_stb),
        .in_data  ({shA, shB}),
        .out_stb  (decim_stb),
        .out_data (decim_data)
    );

    // ---- burst capture ring + frozen readout (UNCHANGED v0 path) ------------
    reg [143:0]  cap_buf [0:DEPTH-1];
    reg [AW-1:0] wr_ptr  = {AW{1'b0}};
    reg [7:0]    cap_seq = 8'd0;
    reg [1:0]    mosi_s  = 2'b00;
    reg          busy_d  = 1'b0;
    reg          frozen  = 1'b0;
    reg [AW-1:0] rd_ptr  = {AW{1'b0}};
    reg [143:0]  rd_data = 144'd0;
    reg [23:0]   wdog    = 24'd0;

    always @(posedge clk50) begin
        mosi_s  <= {mosi_s[0], esp_mosi};
        busy_d  <= esp_busy;
        rd_data <= cap_buf[rd_ptr];
        if (rst) begin
            wr_ptr <= {AW{1'b0}}; cap_seq <= 8'd0;
            frozen <= 1'b0; rd_ptr <= {AW{1'b0}}; wdog <= 24'd0;
        end else begin
            if (cap_stb && !frozen) begin
                cap_buf[wr_ptr] <= {8'hA5, cap_seq, shA, shB};
                wr_ptr  <= wr_ptr  + 1'b1;
                cap_seq <= cap_seq + 1'b1;
            end
            if (esp_busy & ~busy_d) begin   // transaction start
                wdog <= 24'd0;
                if (mosi_s[1]) begin        // 0xFF -> BURST (MSB high)
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

    // ---- piece 2: free-running stream FIFO + dropped-sample counter ---------
    // Producer: the decimator (decim_stb) at ~native/DECIM_M. Consumer: the ESP,
    // one stream frame per transaction (esp_done while stream_sel). Push and pop
    // are independent clk50 events and may coincide; the fill counter handles it.
    reg [127:0]   sfifo [0:STREAM_DEPTH-1];
    reg [SAW-1:0] sw_ptr  = {SAW{1'b0}};
    reg [SAW-1:0] sr_ptr  = {SAW{1'b0}};
    reg [SAW:0]   sfill   = {(SAW+1){1'b0}};   // 0 .. STREAM_DEPTH
    reg [7:0]     sdrop   = 8'd0;              // saturating overrun (lost samples)
    reg [127:0]   sr_data = 128'd0;            // registered FIFO read
    reg [7:0]     shdr    = 8'hA5;             // 0xA5 ok / 0x5A underrun (stale)

    wire s_push   = decim_stb && (sfill <  STREAM_DEPTH);
    wire s_over   = decim_stb && (sfill == STREAM_DEPTH);
    wire s_popreq = esp_done && stream_sel;        // ESP took a stream frame
    wire s_pop    = s_popreq && (sfill != 0);      // a real (fresh) pop

    always @(posedge clk50) begin
        sr_data <= sfifo[sr_ptr];                  // registered (BRAM) read port
        // Held cleared whenever NOT streaming: the dropcount is PER-SESSION, so a
        // fresh stream starts at drop=0 and only climbs if the ESP can't keep up.
        if (rst || !stream_sel) begin
            sw_ptr <= {SAW{1'b0}}; sr_ptr <= {SAW{1'b0}};
            sfill  <= {(SAW+1){1'b0}}; sdrop <= 8'd0; shdr <= 8'hA5;
        end else begin
            if (s_push) begin
                sfifo[sw_ptr] <= decim_data;
                sw_ptr <= sw_ptr + 1'b1;
            end
            if (s_over && sdrop != 8'hFF) sdrop <= sdrop + 1'b1;   // count the loss
            if (s_pop) sr_ptr <= sr_ptr + 1'b1;
            // fill = +push -realpop (both -> unchanged)
            case ({s_push, s_pop})
                2'b10:   sfill <= sfill + 1'b1;
                2'b01:   sfill <= sfill - 1'b1;
                default: sfill <= sfill;
            endcase
            // header for the frame the NEXT transaction will return: 0x5A if the
            // ESP popped an empty FIFO (underrun -> stale data), else 0xA5.
            if (s_popreq) shdr <= (sfill != 0) ? 8'hA5 : 8'h5A;
        end
    end

    // ---- ESP link: 18-byte payload = header, seq/drop, eight channels -------
    //   frozen        -> BURST ring frame {0xA5, ring-seq, V1..V8}
    //   stream_sel    -> STREAM frame {hdr, dropcount, decimated V1..V8}
    //   otherwise     -> LIVE latest frame {0xA5, seq, V1..V8}
    wire [143:0] live_frame   = {8'hA5, seq,  frame};
    wire [143:0] stream_frame = {shdr,  sdrop, sr_data};
    cec_spi_slave #(.FRAME_BITS(144)) u_esp (
        .clk        (clk50),
        .rst        (rst),
        .frame      (frozen ? rd_data : (stream_sel ? stream_frame : live_frame)),
        .sclk       (esp_sclk),
        .cs_n       (esp_cs_n),
        .miso       (esp_miso),
        .busy       (esp_busy),
        .frame_done (esp_done)
    );

    assign esp_drdy = drdy;
endmodule
`default_nettype wire
