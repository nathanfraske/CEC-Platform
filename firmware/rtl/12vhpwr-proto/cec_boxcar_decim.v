`default_nettype none
// ----------------------------------------------------------------------------
// cec_boxcar_decim -- boxcar (moving-average) decimator, piece 1 of the
// continuous-stream path. Sums M consecutive native samples per channel and
// emits one decimated sample per channel at native/M, packed the same way as
// the acquisition frame (CHANNELS x W, signed, MSB channel high).
//
// It feeds the free-running FIFO in top.v, NEVER the SPI slave directly
// (B4: keep the stages separate) -- decimate -> FIFO -> slave.
//
// FILTER CAVEAT (B3): a boxcar is a sinc (sin(Mx)/M sin(x)) low-pass. It
// ATTENUATES, it does not reject -- energy near the native Nyquist folds back
// into the decimated band only PARTIALLY suppressed by the sinc nulls. That is
// acceptable HERE only because the perfboard analog ceiling (~14 kHz RC corner)
// sits far below the native Nyquist (~native/2 >= 50 kHz), so there is little
// real HF content to fold. If this input ever carries genuine HF (a faster
// front-end, fewer/larger anti-alias caps), the boxcar is NOT a sufficient
// anti-alias filter and a real decimation FIR / CIC-comp is required.
//
// M MUST be a power of two (the average is an arithmetic >> SHIFT); enforced
// below. The accumulator carries SHIFT bits of headroom + a sign guard so the
// sum of M signed W-bit samples never overflows.
// License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module cec_boxcar_decim #(
    parameter integer CHANNELS = 8,
    parameter integer W        = 16,   // signed per-channel sample width
    parameter integer M        = 8     // decimation factor (power of two)
)(
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   in_stb,    // 1-clk: in_data is a valid native frame
    input  wire [CHANNELS*W-1:0]  in_data,   // packed signed channels (ch0 in low W bits)
    output reg                    out_stb,   // 1-clk: out_data is a valid decimated frame
    output reg  [CHANNELS*W-1:0]  out_data   // packed signed channels (boxcar average)
);
    localparam integer SHIFT = $clog2(M);    // M = 1<<SHIFT (power-of-two)
    localparam integer AW    = W + SHIFT + 1; // sum of M signed W-bit + sign guard
    localparam integer CW    = $clog2(M);     // window-position counter width

    // synthesis/sim guard: M must be a power of two for the >> average.
    initial if ((1 << SHIFT) != M)
        $fatal(1, "cec_boxcar_decim: M=%0d is not a power of two", M);

    reg signed [AW-1:0] acc [0:CHANNELS-1];
    reg        [CW:0]   cnt;                  // 0 .. M-1
    integer i;

    always @(posedge clk) begin
        out_stb <= 1'b0;
        if (rst) begin
            cnt <= {(CW+1){1'b0}};
            for (i = 0; i < CHANNELS; i = i + 1) acc[i] <= {AW{1'b0}};
        end else if (in_stb) begin
            if (cnt == M-1) begin             // this is the M-th sample: emit + reset
                cnt     <= {(CW+1){1'b0}};
                out_stb <= 1'b1;
                for (i = 0; i < CHANNELS; i = i + 1) begin
                    out_data[i*W +: W] <=
                        (acc[i] + $signed(in_data[i*W +: W])) >>> SHIFT;
                    acc[i] <= {AW{1'b0}};
                end
            end else begin                    // accumulate
                cnt <= cnt + 1'b1;
                for (i = 0; i < CHANNELS; i = i + 1)
                    acc[i] <= acc[i] + $signed(in_data[i*W +: W]);
            end
        end
    end
endmodule
`default_nettype wire
