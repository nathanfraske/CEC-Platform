`default_nettype none
// ----------------------------------------------------------------------------
// cec_native_rail -- 12V-rail spike / brownout / load-unexplained detector.
//
// Watches ONE voltage channel (the 12V-rail divider, `rail_ch`). The hard part,
// per the bench: the rail droops/sags as the GPU loads (~40 mVpp, ~46 ADC codes,
// ANTI-PHASE with the current) and that is IN SPEC -- it must NOT trip. A real
// rail event (PSU turn-on/off, a brownout, a regulation fault, a degrading feed)
// must. Two discriminators, and they stack:
//
//   (1) MAGNITUDE -- the in-spec droop is tiny (~46 codes pp) next to the ATX
//       +/-5% window (~1380 codes pp) or a PSU on/off edge (~full scale). The
//       BAND test trips on |vrail - slow_baseline| > VDEV, with VDEV set in the
//       wide gap between the two: above the droop, below the spec edge. This
//       alone catches PSU on/off + any gross excursion.
//   (2) LOAD-CORRELATION -- the normal droop is CAUSED by the current (V dips
//       because I rose, by the source impedance). Predict it and trip on the
//       UNEXPLAINED residual: r = (vrail-vbase) + KGAIN*(isum-ibase). The droop
//       is predicted and cancels; a rail change the load does NOT account for
//       (a sag at constant current) survives. Same common-mode-rejection idea as
//       the imbalance detector, applied across the V<->I relationship. Lets you
//       tighten below the droop envelope to catch a degrading connector.
//
// THREE tests, each independently disable-able, all gated by WARM-UP (the slow
// baselines must converge first):
//   BAND      (VDEV!=0) && |vrail - vbase| > VDEV          fast spike/step/edge
//   WINDOW    vrail > VMAX || vrail < VMIN                 slow out-of-spec drift
//   RESIDUAL  (VRES!=0) && |vrail-vbase + (KGAIN*idev)>>KG| > VRES   unexplained
// (To disable: VDEV=0 / VRES=0 / WINDOW VMIN=0x8000,VMAX=0x7FFF = full-scale.)
//
// PSU turn-ON: arm while the rail is ~0, the baseline converges to ~0, then the
// rail appears -> a big +deviation -> BAND trips. Turn-OFF: baseline ~nominal,
// rail collapses -> big -deviation -> BAND trips. (The instrument is on its own
// USB power, so it survives a rail collapse and can capture it.) freeze is the
// centered (POSTROLL) ring trigger; trip_ch one-hots the rail channel so the ESP
// reads it as a `vrail` event; trip_cause says which test fired. KGAIN/VDEV/VRES/
// VMIN/VMAX/K_SHIFT are INPUTS so top.v (and the future MOSI runtime-config) drive
// them with no module change. License: Apache-2.0 (CEC-Platform)
// ----------------------------------------------------------------------------
module cec_native_rail #(
    parameter integer CHANNELS = 8,
    parameter integer W        = 16,   // signed per-channel sample width
    parameter integer KMAX     = 14,   // max EMA shift; accs carry +KMAX bits
    parameter integer KG_SHIFT = 8,    // residual gain scale: G = KGAIN / 2^KG_SHIFT
    parameter integer PRW      = 12    // post-roll counter width (>= clog2 ring DEPTH)
)(
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   arm,        // 1 = watch + allow a fresh trip; 0 = clear/re-arm
    input  wire                   in_stb,     // 1-clk: in_data is a valid native frame
    input  wire [CHANNELS*W-1:0]  in_data,    // packed signed channels (ch0 in low W bits)
    input  wire [3:0]             rail_ch,    // index of the 12V-rail voltage channel
    input  wire [CHANNELS-1:0]    cur_mask,   // current channels to sum for the load-line
    input  wire [3:0]             k_shift,    // slow baseline EMA shift; tau ~ 2^k frames
    input  wire [W-1:0]           vdev,       // BAND |vrail-vbase| > vdev (codes); 0 = off
    input  wire signed [W-1:0]    vmin,       // WINDOW absolute low limit (codes, signed)
    input  wire signed [W-1:0]    vmax,       // WINDOW absolute high limit (codes, signed)
    input  wire signed [W-1:0]    kgain,      // load-line gain (signed); 0 = residual off
    input  wire [W-1:0]           vres,       // RESIDUAL |r| > vres (codes); 0 = off
    input  wire [PRW-1:0]         postroll,   // frames after trip before freeze (center = DEPTH/2)
    input  wire [15:0]            warmup,     // frames to converge the baselines before arming trips
    output reg                    freeze,     // 1-clk: freeze the ring (centered dump)
    output reg                    tripped,    // latched until re-armed
    output reg  [CHANNELS-1:0]    trip_ch,    // one-hot the rail channel at the trip
    output reg  [2:0]             trip_cause  // {residual, window, band} that fired
);
    localparam integer VAW = W + KMAX;          // rail EMA accumulator width
    localparam integer ISW = W + 4;             // isum width (sum of <=8 signed channels + headroom)
    localparam integer IAW = ISW + KMAX;        // isum EMA accumulator width
    localparam integer RW  = 2*W + KMAX;         // residual working width (kgain*idev headroom)
    localparam [1:0] S_ARM = 2'd0, S_POST = 2'd1, S_DONE = 2'd2;

    reg signed [VAW-1:0] vacc;                  // rail baseline accumulator
    reg signed [IAW-1:0] iacc;                  // total-current baseline accumulator
    reg                  seeded;
    reg [15:0]           warm;
    reg                  warmed;
    reg [1:0]            st;
    reg [PRW-1:0]        pr_cnt;

    // per-frame scratch (blocking; recomputed every in_stb)
    reg signed [W-1:0]   vrail;
    reg signed [ISW-1:0] isum;
    reg signed [VAW-1:0] vbase;
    reg signed [IAW-1:0] ibase;
    reg signed [W:0]     vdev_s;                // vrail - vbase (one guard bit)
    reg signed [ISW:0]   idev;                  // isum - ibase
    reg signed [RW-1:0]  pred, resid, vabs, rabs;
    reg [2:0]            cause;
    reg                  band_hit, win_hit, res_hit, hit;
    integer i;

    always @(posedge clk) begin
        freeze <= 1'b0;
        if (rst || !arm) begin
            st <= S_ARM; seeded <= 1'b0; warm <= 16'd0; warmed <= 1'b0;
            tripped <= 1'b0; trip_ch <= {CHANNELS{1'b0}}; trip_cause <= 3'b0;
            pr_cnt <= {PRW{1'b0}};
            if (rst) begin vacc <= {VAW{1'b0}}; iacc <= {IAW{1'b0}}; end
        end else if (in_stb) begin
            // ---- pick the rail sample + sum the masked current channels --------
            vrail = $signed(in_data[rail_ch*W +: W]);
            isum  = {ISW{1'b0}};
            for (i = 0; i < CHANNELS; i = i + 1)
                if (cur_mask[i]) isum = isum + $signed(in_data[i*W +: W]);

            if (!seeded) begin
                seeded <= 1'b1;
                vacc <= vrail <<< k_shift;
                iacc <= isum  <<< k_shift;
            end else begin
                // ---- slow baselines (pre-update estimate, used this frame) -----
                vbase = vacc >>> k_shift;
                ibase = iacc >>> k_shift;
                vacc  <= vacc + (vrail - (vacc >>> k_shift));
                iacc  <= iacc + (isum  - (iacc >>> k_shift));

                if (!warmed) begin
                    if (warm >= warmup) warmed <= 1'b1;
                    else warm <= warm + 16'd1;
                end

                // ---- the three tests ------------------------------------------
                vdev_s = vrail - vbase[W:0];           // rail deviation from baseline
                idev   = isum  - ibase[ISW-1:0];        // load deviation from baseline
                pred   = ($signed(kgain) * idev) >>> KG_SHIFT;  // load-explained droop
                resid  = vdev_s + pred;                 // what the load does NOT explain
                vabs   = vdev_s[W]   ? -vdev_s : vdev_s;
                rabs   = resid[RW-1] ? -resid  : resid;

                band_hit = (vdev != {W{1'b0}}) && (vabs > {{(RW-W){1'b0}}, vdev});
                win_hit  = (vrail > vmax) || (vrail < vmin);
                res_hit  = (vres != {W{1'b0}}) && (rabs > {{(RW-W){1'b0}}, vres});
                cause    = {res_hit, win_hit, band_hit};
                hit      = warmed && (band_hit || win_hit || res_hit);

                case (st)
                    S_ARM: if (hit) begin
                        tripped    <= 1'b1;
                        trip_ch    <= ({{(CHANNELS-1){1'b0}}, 1'b1} << rail_ch);
                        trip_cause <= cause;
                        if (postroll == {PRW{1'b0}}) begin
                            freeze <= 1'b1; st <= S_DONE;
                        end else begin
                            pr_cnt <= postroll; st <= S_POST;
                        end
                    end
                    S_POST: if (pr_cnt <= {{(PRW-1){1'b0}}, 1'b1}) begin
                        freeze <= 1'b1; st <= S_DONE;
                    end else
                        pr_cnt <= pr_cnt - 1'b1;
                    default: ;                          // S_DONE: idle until disarmed
                endcase
            end
        end
    end
endmodule
`default_nettype wire
