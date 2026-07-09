#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_precision_route -- STAGE S2 of the pass-form redesign (docs/pass-form-plan.md
#  §4 R2/R3/R4, §5 S2). PRECISION-FIRST ROUTING: "route the important ones with high
#  precision first alone, and then fill in the gaps cheaply" (owner, 2026-07-08).
# ============================================================================
# This is `cec_router.two_pass_corridor`'s lock/protect discipline (foreign 48->0,
# 2026-06-27) GENERALIZED from corridor scope to LADDER scope and wired into the
# ACTIVE pipeline (`route_oracle_grade`), instead of resurrecting TPC (which the
# grader bypasses). The precision copper is laid on the UNCONTENDED placement --
# where nothing contends -- and LOCKED, so Freerouting (run afterward with
# `protect_nets`) treats it as immovable and fills ONLY the residual.
#
# The ladder this module lays (pre-FR):
#   R2 KELVIN  -> cec_fr.synthesize_kelvin_taps (canonical datasheet geometry,
#                 landed 798526e): the four-wire inner-edge sense stub from each
#                 shunt to its sense IC. Laid/refused recorded per net.
#   R3 PAIRS   -> deterministic COUPLED-corridor routing of the board's diff/coupled
#                 pairs (USB _P/_N; CAN_H/CAN_L class) at their netclass width/gap,
#                 via the sanctioned pcbnew toolkit. Straight or one-bend, GUARDED
#                 against existing copper+pads (cec_fr._tap_foreign_clear pattern);
#                 a pair that cannot lay clean is REFUSED with a named snag
#                 (escalate-never-force, plan §3.3), never a bad pair.
#   R4 RESERV. -> PourPlan keepout hints -- compiled by
#                 cec_synth_pipeline._oracle_hints_pours in the grader and passed to
#                 route_once as `hints`; NOT re-derived here.
#   LOCK       -> SetLocked(True) on every R2/R3 track; the locked net names are
#                 returned for route_once(protect_nets=...) (FR DROPS unprotected fix
#                 wires -- measured, cec_fr02 bench).
#
# The wiring lives in route_oracle_grade(precision=True); default precision=False is
# byte-identical to today's single-route_once path.
import os, sys, math, shutil, json

import pcbnew

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cec_fr
import cec_score
import cec_impedance

MM = 1_000_000                       # nm per mm


def _nm(v):
    return int(round(v * MM))


def _v(x, y):
    return pcbnew.VECTOR2I(_nm(x), _nm(y))


# ---------------------------------------------------------------------------
# netclass geometry
# ---------------------------------------------------------------------------
def _netclass_geometry(board_path):
    """{class_name_lower: {'width','diff_width','diff_gap','clearance'}} from the .kicad_pro.
    Reuses cec_impedance._netclasses (width/diff_width/diff_gap) + adds the class clearance."""
    out = {}
    base = cec_impedance._netclasses(board_path)
    for name, spec in base.items():
        if name:
            out[name.lower()] = dict(spec)
    # clearance is not in _netclasses -- pull it straight from the .kicad_pro
    pro = board_path[:-len(".kicad_pcb")] + ".kicad_pro"
    if os.path.isfile(pro):
        try:
            d = json.load(open(pro))
            for c in (d.get("net_settings") or {}).get("classes", []) or []:
                nm = (c.get("name") or "").lower()
                if nm in out:
                    out[nm]["clearance"] = c.get("clearance")
        except Exception:                                    # noqa: BLE001
            pass
    return out


def _pair_geometry(classes, kind):
    """Return (width_mm, gap_mm) for a coupled pair of the given *kind* ('usb'|'can'),
    from the same-named netclass. Falls back to sane per-kind defaults when the class
    (or its diff geometry) is absent -- the 24-pin CAN netclass_patterns are stale, so
    the CAN nets currently fall into Default; keying by class NAME avoids that trap."""
    spec = classes.get(kind, {})
    width = spec.get("diff_width") or spec.get("width")
    gap = spec.get("diff_gap")
    if gap is None:
        gap = spec.get("clearance")
    # per-kind fallbacks (match the shipped board netclasses)
    if kind == "usb":
        width = width or 0.20
        gap = gap or 0.13
    else:  # can (and any other coupled bus)
        width = width or 0.25
        gap = gap or 0.20
    return float(width), float(gap)


# ---------------------------------------------------------------------------
# coupled-pair derivation
# ---------------------------------------------------------------------------
def derive_coupled_pairs(board_path, *, board=None):
    """The R3 pair set = UNION of cec_score.Rules.from_board().diff_pairs (the _P/_N pairs,
    e.g. eps /USB_D_P//USB_D_N) PLUS name-derived coupled buses the _P/_N rule misses:
      * CAN differential -- /CAN_H//CAN_L (preferred), else /CAN_H_BUS//CAN_L_BUS. TX/RX are
        the single-ended MCU legs, never coupled.
      * USB differential -- /USB_DP//USB_DM or /USB_D+//USB_D- (the non-underscore spellings
        the _P/_N regex drops).
    Each entry: {'name','kind','p','n','width','gap','ztarget'}. Kelvin (_HI/_LO) is R2's job,
    never returned here."""
    b = board if board is not None else pcbnew.LoadBoard(board_path)
    names = {n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    classes = _netclass_geometry(board_path)

    pairs = []
    seen = set()

    def _add(name, kind, p, n, ztarget):
        key = frozenset((p, n))
        if key in seen or p not in names or n not in names or p == n:
            return
        seen.add(key)
        w, g = _pair_geometry(classes, kind)
        pairs.append({"name": name, "kind": kind, "p": p, "n": n,
                      "width": w, "gap": g, "ztarget": ztarget})

    # (a) the _P/_N pairs cec_score already derives (eps USB)
    rules = cec_score.Rules.from_board(board_path)
    for p, n in (rules.diff_pairs or []):
        kind = "usb" if "USB" in p.upper() else ("can" if "CAN" in p.upper() else "diff")
        _add(p.rsplit("_", 1)[0].lstrip("/") or p, kind, p, n,
             120.0 if kind == "can" else 90.0)

    # (b) CAN differential bus -- prefer the plain names, else the _BUS spelling
    for hi, lo in (("/CAN_H", "/CAN_L"), ("/CAN_H_BUS", "/CAN_L_BUS")):
        if hi in names and lo in names:
            _add("CAN", "can", hi, lo, 120.0)
            break

    # (c) USB differential -- the non-underscore spellings _P/_N drops
    for p, n in (("/USB_DP", "/USB_DM"), ("/USB_D+", "/USB_D-")):
        if p in names and n in names:
            _add("USB", "usb", p, n, 90.0)
            break

    return pairs


# ---------------------------------------------------------------------------
# geometry helpers (mm space)
# ---------------------------------------------------------------------------
def _pads_on_net(board, net):
    """[(ref, padname, (x_mm, y_mm), pad_obj)] for every pad on *net*."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                pos = p.GetPosition()
                out.append((fp.GetReference(), p.GetPadName(),
                            (pos.x / MM, pos.y / MM), p))
    return out


def _endpoints(pads):
    """The two pads that are FARTHEST apart -- the net's routing endpoints. On a diff net
    with an extra tap (USB-C A6/B6, an ESD-clamp shunt pad) the extremes are the real ends;
    the middle same-net pads are left for FR to stub."""
    if len(pads) < 2:
        return None
    best = None
    for i in range(len(pads)):
        for j in range(i + 1, len(pads)):
            (xi, yi) = pads[i][2]
            (xj, yj) = pads[j][2]
            d = math.hypot(xi - xj, yi - yj)
            if best is None or d > best[0]:
                best = (d, pads[i], pads[j])
    return (best[1], best[2]) if best else None


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_cross(a, b, c, d):
    """True iff segment a-b properly crosses c-d (shared endpoints don't count)."""
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    if a in (c, d) or b in (c, d):
        return False
    return (ccw(a, c, d) * ccw(b, c, d) < 0) and (ccw(a, b, c) * ccw(a, b, d) < 0)


def _polys_no_cross(p_pts, n_pts):
    """True iff the two members never CROSS each other. The foreign guard (cec_fr._tap_foreign_clear)
    deliberately excludes the pair's own two nets (they are MEANT to run adjacent), so P-vs-N
    crossing is checked separately here."""
    for a, b in zip(p_pts, p_pts[1:]):
        for c, d in zip(n_pts, n_pts[1:]):
            if _seg_cross(a, b, c, d):
                return False
    return True


def _partner_pads_clear(board, a, b, width_nm, layer_id, partner_code, clr_nm):
    """True iff segment a->b stays *clr_nm* clear of the PARTNER net's PADS. The foreign guard
    excludes BOTH pair nets (they legitimately run adjacent at the gap), so one member's escape
    could otherwise plow across its sibling's pad -- MEASURED on the first eps arm-B route: an
    R3 /CAN_L escape crossed U2 pad 7 [/CAN_H] = 2 shorting_items + 2 solder_mask_bridge (the
    whole 4-DRC delta). The partner TRACK stays unguarded (it sits at the gap by construction;
    _polys_no_cross catches crossings) -- only its PADS are hard keepouts, mirroring
    synthesize_kelvin_taps' _tap_pair_overlap_clear defence."""
    if a == b:
        return True
    seg = pcbnew.SHAPE_SEGMENT(_v(*a), _v(*b), width_nm)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != partner_code:
                continue
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if p.GetEffectiveShape(layer_id).Collide(seg, clr_nm):
                    return False
            except Exception:                       # noqa: BLE001 -- a weird shape never breaks the guard
                continue
    return True


def _measured_gap(p_pts, n_pts, width):
    """The gap the pair ACTUALLY achieves once laid: median nearest-distance between the two
    members' segment midpoints minus the track width (the same estimator build/blind_routes2.py
    uses on routed geometry). Returns None when either member has no segment."""
    def _mids(pts):
        return [((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                for a, b in zip(pts, pts[1:]) if a != b]

    def _pt_seg(px, py, a, b):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / L2))
        return math.hypot(px - (a[0] + t * vx), py - (a[1] + t * vy))

    pm = _mids(p_pts)
    n_segs = [(a, b) for a, b in zip(n_pts, n_pts[1:]) if a != b]
    if not pm or not n_segs:
        return None
    gaps = sorted(min(_pt_seg(mx, my, a, b) for a, b in n_segs) for mx, my in pm)
    return max(0.05, round(gaps[len(gaps) // 2] - width, 3))


def _lay(board, net_code, pts, width_nm, layer_id):
    """Lay a polyline as PCB_TRACK segments; return the laid track objects."""
    laid = []
    for a, b in zip(pts, pts[1:]):
        if a == b:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(_v(*a))
        t.SetEnd(_v(*b))
        t.SetWidth(width_nm)
        t.SetLayer(layer_id)
        t.SetNetCode(net_code)
        board.Add(t)
        laid.append(t)
    return laid


def route_coupled_pair(board, pair, *, layer="F.Cu", clearance=None, verbose=False):
    """Route ONE coupled pair on *board* (in place): a short per-endpoint ESCAPE (a modest fan of
    angles, plan §4 R3 '(B)-lite') off each pad into clear space, then a COUPLED MIDDLE RUN at the
    netclass width/gap between the source-side and dest-side escapes. Every segment is guarded with
    EXACT pad geometry (cec_fr._tap_foreign_clear -> GetEffectiveShape().Collide, the same test DRC
    uses -- no inflated bbox, so a legal pass between two round THT pads is NOT over-refused) at the
    real netclass clearance; a genuine <clearance short to ANY foreign pad (incl. the pair's own
    connector's GND pin) REFUSES the pair (escalate-never-force). A cross-board pair with no clear
    corridor is refused cleanly for the cec_staged_fr tier-fallback.

    Zdiff is reported BOTH ways (owner ask): 'zdiff_nominal' from the netclass width/gap and
    'zdiff_measured' from the actually-laid geometry, vs 'ztarget'. On refusal returns
    {'name','p','n','refused'} so the manifest handoff is clean."""
    p_net, n_net = pair["p"], pair["n"]
    width, gap = pair["width"], pair["gap"]
    p_ends = _endpoints(_pads_on_net(board, p_net))
    n_ends = _endpoints(_pads_on_net(board, n_net))
    if not p_ends or not n_ends:
        return {"name": pair["name"], "p": p_net, "n": n_net,
                "refused": "missing pads on one member"}

    lay_id = board.GetLayerID(layer)
    if lay_id < 0:
        return {"name": pair["name"], "p": p_net, "n": n_net,
                "refused": "layer %s absent" % layer}

    (pa, pb) = (p_ends[0][2], p_ends[1][2])
    (na, nb) = (n_ends[0][2], n_ends[1][2])
    # pair the ends so P_src is near N_src and P_dst near N_dst (minimize the summed spread)
    if _dist(pa, na) + _dist(pb, nb) <= _dist(pa, nb) + _dist(pb, na):
        P_src, P_dst, N_src, N_dst = pa, pb, na, nb
    else:
        P_src, P_dst, N_src, N_dst = pa, pb, nb, na

    pc = board.GetNetcodeFromNetname(p_net)
    nc = board.GetNetcodeFromNetname(n_net)
    own = {pc, nc}
    off = (width + gap) / 2.0
    width_nm = _nm(width)
    clr_nm = _nm(clearance if clearance is not None else 0.2)

    def seg_clear(a, b, partner):
        """Clear of foreign copper AND of the PARTNER member's pads (a member may run adjacent
        to its partner's TRACK at the gap, but never across its partner's PAD -- the measured
        /CAN_L-over-U2.7 short)."""
        if a == b:
            return True
        return (cec_fr._tap_foreign_clear(board, _v(*a), _v(*b), width_nm,
                                          lay_id, clr_nm, own)
                and _partner_pads_clear(board, a, b, width_nm, lay_id, partner, clr_nm))

    def escape(src, dst, partner):
        """A clear pad->lane path: direct, else ONE mid-point over a modest fan of angles/radii."""
        if seg_clear(src, dst, partner):
            return [src, dst]
        for r in (0.8, 1.2, 1.6, 2.0, 2.6, 3.2):
            # OWNER SCORECARD FIX (2026-07-09): 8 directions at 45-degree steps -- the
            # 24x15-degree fan laid 'strange acute angles... jarring, HF-style' bends.
            for k in range(8):
                th = 2.0 * math.pi * k / 8.0
                mid = (src[0] + r * math.cos(th), src[1] + r * math.sin(th))
                if seg_clear(src, mid, partner) and seg_clear(mid, dst, partner):
                    return [src, mid, dst]
        return None

    Sc = ((P_src[0] + N_src[0]) / 2.0, (P_src[1] + N_src[1]) / 2.0)
    Dc = ((P_dst[0] + N_dst[0]) / 2.0, (P_dst[1] + N_dst[1]) / 2.0)
    dx, dy = Dc[0] - Sc[0], Dc[1] - Sc[1]
    span = math.hypot(dx, dy) or 1.0
    ux, uy = dx / span, dy / span                 # corridor axis
    px, py = -uy, ux                              # perpendicular
    sgn = 1.0 if ((P_src[0] - Sc[0]) * px + (P_src[1] - Sc[1]) * py) >= 0 else -1.0

    # try a few insets (how far the coupled run is pulled in from each cluster) x lateral
    # shifts. SHORTEST inset FIRST (owner scorecard fix 2026-07-09: the pair 'takes too
    # long to loop around and start riding alongside' -- earliest pairing pickup wins).
    for inset in (1.3, 2.0, 2.8, 3.6):
        if 2 * inset >= span - 0.5:
            continue                              # clusters too close to seat a coupled run
        Se = (Sc[0] + ux * inset, Sc[1] + uy * inset)
        De = (Dc[0] - ux * inset, Dc[1] - uy * inset)
        for shift in (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.6, -2.6):
            po, no = sgn * off + shift, -sgn * off + shift
            Pls = (Se[0] + px * po, Se[1] + py * po)
            Ple = (De[0] + px * po, De[1] + py * po)
            Nls = (Se[0] + px * no, Se[1] + py * no)
            Nle = (De[0] + px * no, De[1] + py * no)
            if not (seg_clear(Pls, Ple, nc) and seg_clear(Nls, Nle, pc)):
                continue
            eP0, eP1 = escape(P_src, Pls, nc), escape(P_dst, Ple, nc)
            eN0, eN1 = escape(N_src, Nls, pc), escape(N_dst, Nle, pc)
            if None in (eP0, eP1, eN0, eN1):
                continue
            p_pts = eP0 + [Ple] + list(reversed(eP1))[1:]
            n_pts = eN0 + [Nle] + list(reversed(eN1))[1:]
            if not _polys_no_cross(p_pts, n_pts):
                continue
            laid = _lay(board, pc, p_pts, width_nm, lay_id)
            laid += _lay(board, nc, n_pts, width_nm, lay_id)
            zd_nom = cec_impedance.zdiff_edge_coupled(width, gap)
            g_meas = _measured_gap(p_pts, n_pts, width)
            zd_meas = (cec_impedance.zdiff_edge_coupled(width, g_meas)
                       if g_meas is not None else None)
            run_len = round(sum(_dist(a, b) for a, b in zip(p_pts, p_pts[1:])), 2)
            coupled_len = round(_dist(Pls, Ple), 2)
            if verbose:
                print("[precision] R3 %s coupled: w=%.3f gap_nom=%.3f gap_meas=%s "
                      "Zdiff_nom~%.0fR Zdiff_meas~%s coupled=%.1fmm total=%.1fmm"
                      % (pair["name"], width, gap, g_meas, zd_nom,
                         ("%.0fR" % zd_meas if zd_meas is not None else "n/a"),
                         coupled_len, run_len), file=sys.stderr)
            return {"name": pair["name"], "p": p_net, "n": n_net,
                    "width": width, "gap_nominal": gap, "gap_measured": g_meas,
                    "zdiff_nominal": round(zd_nom, 1),
                    "zdiff_measured": (round(zd_meas, 1) if zd_meas is not None else None),
                    "ztarget": pair.get("ztarget"), "segments": len(laid),
                    "length_mm": run_len, "coupled_len_mm": coupled_len}
    return {"name": pair["name"], "p": p_net, "n": n_net, "refused":
            "no clear coupled corridor at exact %sR geometry (escape+middle guard refused); "
            "hand off to cec_staged_fr tier-fallback" % (clearance if clearance is not None else 0.2)}


# ---------------------------------------------------------------------------
# the precision ladder
# ---------------------------------------------------------------------------
def precision_route(placed_board, out_board, *, kelvin_width=0.25, verbose=True,
                    do_kelvin=True, do_pairs=True):
    """Run the PRE-FR precision ladder (R2 kelvin + R3 coupled pairs) on the UNCONTENDED
    placement *placed_board*, LOCK every track laid, and save to *out_board*.

    Returns a report dict:
      {'out', 'locked_nets' (for route_once protect_nets), 'n_locked_segments',
       'kelvin' (synthesize_kelvin_taps report), 'pairs' {'routed':[...], 'refused':[...]},
       'pairs_ok'}.

    R4 reservations are NOT laid here -- they are the PourPlan keepout HINTS the grader
    already compiles (_oracle_hints_pours) and passes to FR as `hints`."""
    board = pcbnew.LoadBoard(placed_board)
    pre_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}

    # ---- R2 KELVIN (canonical inner-edge taps, pre-FR on the uncontended board) ----
    kelvin = {"taps": 0, "by_net": {}, "refused": {}, "segments": 0}
    if do_kelvin:
        kelvin = cec_fr.synthesize_kelvin_taps(board, width=kelvin_width)
        if verbose:
            print("[precision] R2 kelvin: %d tap(s) laid %s; refused %s"
                  % (kelvin.get("taps", 0), kelvin.get("by_net", {}),
                     kelvin.get("refused", {})), file=sys.stderr)

    # ---- R3 COUPLED PAIRS (deterministic, guarded, refuse-not-force) ----
    routed_pairs, refused_pairs = [], []
    if do_pairs:
        for pair in derive_coupled_pairs(placed_board, board=board):
            rep = route_coupled_pair(board, pair, verbose=verbose)
            if rep.get("refused"):
                refused_pairs.append(rep)
                if verbose:
                    print("[precision] R3 %s REFUSED: %s"
                          % (rep["name"], rep["refused"]), file=sys.stderr)
            else:
                routed_pairs.append(rep)

    # ---- LOCK every R2/R3 track; collect the protect net set ----
    locked_nets, n_locked = set(), 0
    for t in board.GetTracks():
        if t.m_Uuid.AsString() in pre_ids:
            continue
        t.SetLocked(True)
        n_locked += 1
        nn = t.GetNetname()
        if nn:
            locked_nets.add(nn)

    pcbnew.SaveBoard(out_board, board)
    # DRC/netclass context travels with the board (bake_hints copies these onward)
    for ext in (".kicad_pro", ".kicad_dru"):
        src = placed_board[:-len(".kicad_pcb")] + ext
        if os.path.isfile(src):
            shutil.copy2(src, out_board[:-len(".kicad_pcb")] + ext)

    report = {
        "out": out_board,
        "locked_nets": sorted(locked_nets),
        "n_locked_segments": n_locked,
        "kelvin": kelvin,
        "pairs": {"routed": routed_pairs, "refused": refused_pairs},
        "pairs_ok": (len(refused_pairs) == 0),
    }
    if verbose:
        print("[precision] LOCKED %d segment(s) on %d net(s); pairs routed=%d refused=%d"
              % (n_locked, len(locked_nets), len(routed_pairs), len(refused_pairs)),
              file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# CLI: python3 scripts/cec_precision_route.py PLACED OUT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: cec_precision_route.py PLACED.kicad_pcb OUT.kicad_pcb", file=sys.stderr)
        sys.exit(2)
    rep = precision_route(sys.argv[1], sys.argv[2], verbose=True)
    print(json.dumps({k: v for k, v in rep.items() if k != "kelvin"}, indent=1, default=str))
    print("kelvin:", json.dumps(rep["kelvin"], default=str))
