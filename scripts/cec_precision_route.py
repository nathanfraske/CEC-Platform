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
import os, sys, math, shutil, json, heapq, time, re, copy

import pcbnew

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py (hub all-9999 root cause).
import cec_swig_guard as _swig_guard                     # noqa: E402
_swig_guard.pin()

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cec_fr
import cec_score
import cec_impedance
import cec_fab_profile
import cec_constraints

MM = 1_000_000                       # nm per mm
_SPLIT_TERMINAL_FANOUT_MAX_MM = 8.0


class PrecisionRouteRefused(RuntimeError):
    """Fail-closed precision refusal carrying its complete evidence."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def _nm(v):
    return int(round(v * MM))


def _v(x, y):
    return pcbnew.VECTOR2I(_nm(x), _nm(y))


def _deadline_expired(deadline):
    return deadline is not None and time.monotonic() >= float(deadline)


# ---------------------------------------------------------------------------
# netclass geometry
# ---------------------------------------------------------------------------
def _netclass_geometry(board_path):
    """Pair routing geometry from the sibling project's real netclasses.

    Width, gap, clearance, and ordinary through-via dimensions travel together
    so an atomic pair portal cannot satisfy the board minimum while silently
    undercutting the assigned class via contract.
    """
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
    # Two pair members are still different nets. A nominal impedance gap may
    # therefore never undercut the class/fabrication copper clearance. The old
    # selector preferred ``diff_gap`` (0.13 mm on several legacy USB classes)
    # and ignored their 0.20 mm clearance, producing routes that the release
    # fab profile correctly rejected. Preserve a wider authored pair gap, but
    # lift a narrow one to the same minimum spacing contract seen by DRC.
    gap_values = [value for value in (
        spec.get("diff_gap"), spec.get("clearance")) if value is not None]
    gap = max(float(value) for value in gap_values) if gap_values else None
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
        row = {"name": name, "kind": kind, "p": p, "n": n,
               "width": w, "gap": g, "ztarget": ztarget}
        spec = classes.get(kind, {})
        if spec:
            row.update({
                "clearance": float(spec.get("clearance") or 0.20),
                "via_diameter": float(spec.get("via_diameter") or 0.50),
                "via_drill": float(spec.get("via_drill") or 0.25),
            })
        pairs.append(row)

    # (a) the _P/_N pairs cec_score already derives (eps USB)
    rules = cec_score.Rules.from_board(board_path)
    for p, n in (rules.diff_pairs or []):
        kind = "usb" if "USB" in p.upper() else ("can" if "CAN" in p.upper() else "diff")
        _add(p.rsplit("_", 1)[0].lstrip("/") or p, kind, p, n,
             120.0 if kind == "can" else 90.0)

    def _unique_leaf(leaf):
        """Resolve one hierarchical KiCad leaf without guessing.

        Current hierarchical boards prefix local net labels with a sheet path;
        checking only literal ``/CAN_H`` made a declared CAN pair disappear
        from precision routing.  Ambiguous leaves intentionally return None.
        """
        matches = sorted(name for name in names
                         if name.rsplit("/", 1)[-1] == leaf)
        return matches[0] if len(matches) == 1 else None

    # (b) CAN differential bus. Resolve exact historical globals first, then
    # the unique leaf on a hierarchical board. TX/RX remain single-ended.
    for hi_leaf, lo_leaf in (("CAN_H", "CAN_L"),
                             ("CAN_H_BUS", "CAN_L_BUS")):
        hi = ("/" + hi_leaf) if ("/" + hi_leaf) in names else \
             _unique_leaf(hi_leaf)
        lo = ("/" + lo_leaf) if ("/" + lo_leaf) in names else \
             _unique_leaf(lo_leaf)
        if hi and lo:
            _add("CAN", "can", hi, lo, 120.0)
            break

    # (c) USB differential -- the non-underscore spellings _P/_N drops
    for p_leaf, n_leaf in (("USB_DP", "USB_DM"), ("USB_D+", "USB_D-")):
        p = ("/" + p_leaf) if ("/" + p_leaf) in names else \
            _unique_leaf(p_leaf)
        n = ("/" + n_leaf) if ("/" + n_leaf) in names else \
            _unique_leaf(n_leaf)
        if p and n:
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


def _pair_endpoint_stations(board, pair):
    """Describe physical P/N endpoint stations for placement feedback.

    A differential endpoint is usually one footprint carrying both members,
    but split termination networks legitimately put P and N on two separate,
    adjacent footprints.  Routing already treats those as one electrical
    station; expose the same topology in refusal evidence so placement can
    translate the complete station rather than rotating or nudging one member
    at a time.  The derivation is geometry/package based and contains no board
    or reference-designator exception.
    """
    p_rows = _pads_on_net(board, pair["p"])
    n_rows = _pads_on_net(board, pair["n"])
    by_p, by_n = {}, {}
    for row in p_rows:
        by_p.setdefault(str(row[0]), []).append(row)
    for row in n_rows:
        by_n.setdefault(str(row[0]), []).append(row)

    footprint_by_ref = {
        str(footprint.GetReference()): footprint
        for footprint in board.GetFootprints()
    }

    def centre(rows):
        points = [row[2] for row in rows]
        return (sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points))

    def station_geometry(p_members, n_members):
        """Return electrical centre and the physical P-to-N lane vector."""
        p_center = centre(p_members)
        n_center = centre(n_members)
        center = ((p_center[0] + n_center[0]) / 2.0,
                  (p_center[1] + n_center[1]) / 2.0)
        dx, dy = n_center[0] - p_center[0], n_center[1] - p_center[1]
        pitch = math.hypot(dx, dy)
        member_axis = ([round(dx / pitch, 6), round(dy / pitch, 6)]
                       if pitch > 1.0e-9 else None)
        return {
            "center": [round(value, 6) for value in center],
            "p_center": [round(value, 6) for value in p_center],
            "n_center": [round(value, 6) for value in n_center],
            "member_axis": member_axis,
            "member_pitch_mm": round(pitch, 6),
        }

    def contact_evidence(rows):
        """JSON-stable physical pad evidence for route-aware orientation."""
        return [{
            "ref": str(row[0]),
            "pad": str(row[1]),
            "point_mm": [round(float(row[2][0]), 6),
                         round(float(row[2][1]), 6)],
        } for row in rows]

    def package_signature(ref):
        footprint = footprint_by_ref.get(str(ref))
        prefix_match = re.match(r"[A-Za-z]+", str(ref))
        prefix = prefix_match.group(0).upper() if prefix_match else ""
        if footprint is None:
            return prefix, ""
        try:
            library_item = str(footprint.GetFPID().GetLibItemName())
        except Exception:                                # noqa: BLE001
            library_item = ""
        return prefix, library_item

    stations = []
    common = sorted(set(by_p) & set(by_n))
    for ref in common:
        stations.append({
            "id": ref,
            "kind": "same-footprint-pair",
            "physical_refs": [ref],
            "p_contacts": contact_evidence(by_p[ref]),
            "n_contacts": contact_evidence(by_n[ref]),
            **station_geometry(by_p[ref], by_n[ref]),
        })

    unmatched_p = sorted(set(by_p) - set(by_n))
    unmatched_n = sorted(set(by_n) - set(by_p))
    split_candidates = []
    for p_ref in unmatched_p:
        if len(by_p[p_ref]) != 1:
            continue
        p_signature = package_signature(p_ref)
        for n_ref in unmatched_n:
            if len(by_n[n_ref]) != 1:
                continue
            n_signature = package_signature(n_ref)
            # Split pair members should be the same component family and,
            # when populated, the same land pattern.  Distance then provides
            # a deterministic one-to-one match among repeated stations.
            if (not p_signature[0] or p_signature[0] != n_signature[0]
                    or (p_signature[1] and n_signature[1]
                        and p_signature[1] != n_signature[1])):
                continue
            separation = _dist(by_p[p_ref][0][2], by_n[n_ref][0][2])
            if separation > _SPLIT_TERMINAL_FANOUT_MAX_MM + 1e-9:
                continue
            split_candidates.append((round(separation, 6), p_ref, n_ref))

    used_p, used_n = set(), set()
    for separation, p_ref, n_ref in sorted(split_candidates):
        if p_ref in used_p or n_ref in used_n:
            continue
        used_p.add(p_ref)
        used_n.add(n_ref)
        stations.append({
            "id": "%s|%s" % (p_ref, n_ref),
            "kind": "split-member-footprints",
            "physical_refs": sorted([p_ref, n_ref]),
            "member_separation_mm": separation,
            "p_contacts": contact_evidence(by_p[p_ref]),
            "n_contacts": contact_evidence(by_n[n_ref]),
            **station_geometry(by_p[p_ref], by_n[n_ref]),
        })
    return sorted(stations, key=lambda row: (
        float(row["center"][0]), float(row["center"][1]), row["id"]))


def _endpoints(pads):
    """The two pads that are FARTHEST apart -- the net's routing endpoints. On a diff net
    with an extra tap (USB-C A6/B6, an ESD-clamp shunt pad) the extremes are the real ends.
    A successful precision pair is subsequently closed across every same-footprint
    duplicate land and is refused unless locked copper owns every physical pad; the
    broad router is never asked to repair an incomplete "protected" pair."""
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


def _flow_through_pair_legs(board, pair):
    """Return ordered pair legs through any inline flow-through footprint.

    USB ESD arrays commonly expose two pads for D+ and two for D- so layout can
    enter one side of the package and leave the other.  Treating the farthest
    pads on each whole net as the only endpoints silently bypasses that package
    and turns its four signal pads into branches.  This derivation is based on
    pad topology and geometry rather than reference names:

    * the two mutually farthest footprints carrying both members are terminals;
    * an intermediate footprint with exactly two pads on each member is an
      inline station;
    * the station's two P/N ports are the minimum-distance P-to-N matching and
      are ordered along the terminal axis.

    The result is ``(legs, station_refs)`` where each leg is the explicit
    ``(P_src, P_dst, N_src, N_dst)`` tuple accepted by
    :func:`route_coupled_pair`.  ``None`` means the pair has no unambiguous
    flow-through topology and retains the ordinary endpoint path.
    """
    p_pads = _pads_on_net(board, pair["p"])
    n_pads = _pads_on_net(board, pair["n"])
    by_p, by_n = {}, {}
    for row in p_pads:
        by_p.setdefault(row[0], []).append(row)
    for row in n_pads:
        by_n.setdefault(row[0], []).append(row)
    common = sorted(set(by_p) & set(by_n))
    # A multidrop pair may terminate each member on different connector
    # footprints while sharing only the transceiver package.  Such a topology
    # is valid, but it cannot contain an inline four-pad flow-through station.
    # Treat it as an ordinary/multidrop pair instead of taking max() over an
    # empty terminal-pair domain and poisoning both placement evidence and
    # future-congestion analysis.
    if len(common) < 2:
        return None

    def ref_center(ref):
        values = [r[2] for r in by_p[ref] + by_n[ref]]
        return (sum(p[0] for p in values) / len(values),
                sum(p[1] for p in values) / len(values))

    # Physical terminals are the farthest common-mode footprints.  This keeps
    # duplicated reversible-connector pads at an endpoint instead of
    # misclassifying that connector itself as a flow station.
    terminal_pair = max(
        ((a, b) for i, a in enumerate(common) for b in common[i + 1:]),
        key=lambda ab: _dist(ref_center(ab[0]), ref_center(ab[1])))
    a_ref, b_ref = terminal_pair
    a_center, b_center = ref_center(a_ref), ref_center(b_ref)
    axis = (b_center[0] - a_center[0], b_center[1] - a_center[1])
    span2 = axis[0] * axis[0] + axis[1] * axis[1]
    if span2 <= 1e-9:
        return None

    def projection(value):
        return ((value[0] - a_center[0]) * axis[0]
                + (value[1] - a_center[1]) * axis[1]) / span2

    station_refs = [r for r in common if r not in terminal_pair
                    and len(by_p[r]) == 2 and len(by_n[r]) == 2]
    station_refs = [r for r in station_refs
                    if 0.0 < projection(ref_center(r)) < 1.0]
    station_refs.sort(key=lambda r: projection(ref_center(r)))
    if not station_refs:
        return None

    def station_ports(ref):
        ps, ns = by_p[ref], by_n[ref]
        direct = _dist(ps[0][2], ns[0][2]) + _dist(ps[1][2], ns[1][2])
        crossed = _dist(ps[0][2], ns[1][2]) + _dist(ps[1][2], ns[0][2])
        matched = ((ps[0], ns[0]), (ps[1], ns[1])) if direct <= crossed else \
                  ((ps[0], ns[1]), (ps[1], ns[0]))
        return sorted(matched, key=lambda pn: projection((
            (pn[0][2][0] + pn[1][2][0]) / 2.0,
            (pn[0][2][1] + pn[1][2][1]) / 2.0)))

    ports = [station_ports(ref) for ref in station_refs]

    def terminal_port(ref, target):
        # Reversible connectors can expose duplicate pads on a member.  Select
        # the P/N combination whose centre is nearest the adjacent station;
        # pair separation is the stable secondary preference.
        choices = []
        for pp in by_p[ref]:
            for np in by_n[ref]:
                centre = ((pp[2][0] + np[2][0]) / 2.0,
                          (pp[2][1] + np[2][1]) / 2.0)
                choices.append((_dist(centre, target), _dist(pp[2], np[2]),
                                pp[1], np[1], pp, np))
        best = min(choices)
        return best[-2], best[-1]

    first_port = ports[0][0]
    first_target = ((first_port[0][2][0] + first_port[1][2][0]) / 2.0,
                    (first_port[0][2][1] + first_port[1][2][1]) / 2.0)
    last_port = ports[-1][1]
    last_target = ((last_port[0][2][0] + last_port[1][2][0]) / 2.0,
                   (last_port[0][2][1] + last_port[1][2][1]) / 2.0)
    a_port = terminal_port(a_ref, first_target)
    b_port = terminal_port(b_ref, last_target)

    chain = [a_port]
    for near_port, far_port in ports:
        chain.extend((near_port, far_port))
    chain.append(b_port)
    legs = []
    for source, dest in zip(chain[0::2], chain[1::2]):
        legs.append((source[0][2], dest[0][2], source[1][2], dest[1][2]))
    return legs, station_refs


def _multidrop_pair_plan(board, pair):
    """Return a deterministic physical tree for a multi-terminal pair.

    A CAN bus commonly has one H/L pad on each of several connectors plus the
    transceiver.  The two-endpoint precision router cannot own that topology,
    while routing H and L independently produces avoidable loop area and
    length skew.  Treat each footprint carrying both members as one paired
    terminal, choose its closest physical P/N port, then build a Euclidean MST
    over terminal centres.  The returned plan deliberately separates terminal
    discovery from copper generation.  A later router can replace a repeated
    internal pad endpoint with one nearby paired junction and a short terminal
    stub.  Asking an endpoint router to leave the same pad twice is not a
    trunk: the second launch must cross or double back through the first.

    This is deliberately topology-derived: it applies to any named physical
    pair with at least three paired terminal footprints and contains no board,
    reference-designator, or connector-family special case.
    """
    p_rows = _pads_on_net(board, pair["p"])
    n_rows = _pads_on_net(board, pair["n"])
    by_p, by_n = {}, {}
    for row in p_rows:
        by_p.setdefault(row[0], []).append(row)
    for row in n_rows:
        by_n.setdefault(row[0], []).append(row)
    common = sorted(set(by_p) & set(by_n))
    if len(common) < 3:
        return None

    try:
        board_hint = board.GetFileName() or ""
        preferred_signal_layers = tuple(
            cec_fab_profile.referenced_signal_layers(
                board, hint=board_hint) or ("F.Cu", "B.Cu"))
    except Exception:                                  # noqa: BLE001
        preferred_signal_layers = ("F.Cu", "B.Cu")

    def pad_layer_names(row):
        pad = row[3]
        if pad is None:
            return {"F.Cu"}
        names = set()
        for layer_id in pad.GetLayerSet().CuStack():
            lid = int(layer_id)
            names.add(cec_fab_profile.COPPER_LAYER_IDS.get(
                lid, board.GetLayerName(lid)))
        return names

    def is_through(row):
        pad = row[3]
        return bool(pad is not None
                    and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)

    ports = {}
    for ref in common:
        choices = []
        for p_row in by_p[ref]:
            for n_row in by_n[ref]:
                center = ((p_row[2][0] + n_row[2][0]) / 2.0,
                          (p_row[2][1] + n_row[2][1]) / 2.0)
                choices.append((
                    _dist(p_row[2], n_row[2]),
                    str(p_row[1]), str(n_row[1]), center, p_row, n_row))
        _separation, _p_pad, _n_pad, center, p_row, n_row = min(choices)
        ports[ref] = {
            "p": p_row, "n": n_row, "center": center,
            "layers": pad_layer_names(p_row) & pad_layer_names(n_row),
            "through": bool(is_through(p_row) and is_through(n_row)),
        }

    # A split termination or common-mode endpoint may expose the two pair
    # members on two separate but symmetric one-member footprints.  Requiring
    # both nets on one reference silently omits those physical pads, after
    # which the route can be electrically useful but can never satisfy full
    # locked-pad ownership.  Pair only unambiguous, nearby, package-compatible
    # one-pad references.  The synthetic terminal then enters the same MST,
    # coloring, geometry, and admission machinery as an ordinary footprint.
    footprint_by_ref = {
        footprint.GetReference(): footprint
        for footprint in board.GetFootprints()
    } if hasattr(board, "GetFootprints") else {}

    def ref_prefix(ref):
        match = re.match(r"[A-Za-z]+", str(ref))
        return match.group(0).upper() if match else ""

    def package_signature(ref):
        footprint = footprint_by_ref.get(ref)
        if footprint is None:
            return ref_prefix(ref), "", ""
        try:
            lib_id = str(footprint.GetFPID().GetLibItemName())
        except Exception:  # noqa: BLE001 -- metadata is a conservative filter
            lib_id = ""
        return (ref_prefix(ref), footprint.GetValue() or "", lib_id)

    def compatible_split_refs(p_ref, n_ref):
        p_sig, n_sig = package_signature(p_ref), package_signature(n_ref)
        if not p_sig[0] or p_sig[0] != n_sig[0]:
            return False
        # When populated metadata exists it must agree.  Empty metadata in a
        # synthetic/test board does not waive the common reference-family and
        # distance constraints below.
        return all(not left or not right or left == right
                   for left, right in zip(p_sig[1:], n_sig[1:]))

    unmatched_p = sorted(set(by_p) - set(by_n))
    unmatched_n = sorted(set(by_n) - set(by_p))
    split_candidates = []
    for p_ref in unmatched_p:
        if len(by_p[p_ref]) != 1:
            continue
        for n_ref in unmatched_n:
            if len(by_n[n_ref]) != 1 or not compatible_split_refs(p_ref, n_ref):
                continue
            p_row, n_row = by_p[p_ref][0], by_n[n_ref][0]
            separation = _dist(p_row[2], n_row[2])
            layers = pad_layer_names(p_row) & pad_layer_names(n_row)
            if separation > _SPLIT_TERMINAL_FANOUT_MAX_MM or not layers:
                continue
            split_candidates.append((
                round(separation, 6), p_ref, n_ref, p_row, n_row, layers))

    used_p, used_n = set(), set()
    split_refs = []
    for _separation, p_ref, n_ref, p_row, n_row, layers in sorted(
            split_candidates):
        if p_ref in used_p or n_ref in used_n:
            continue
        used_p.add(p_ref); used_n.add(n_ref)
        virtual_ref = "%s|%s" % (p_ref, n_ref)
        split_refs.append(virtual_ref)
        ports[virtual_ref] = {
            "p": p_row, "n": n_row,
            "center": ((p_row[2][0] + n_row[2][0]) / 2.0,
                       (p_row[2][1] + n_row[2][1]) / 2.0),
            "layers": layers,
            "through": bool(is_through(p_row) and is_through(n_row)),
            "terminal_kind": "split-member-footprints",
            "physical_refs": [p_ref, n_ref],
        }

    terminals = sorted(common + split_refs)
    if len(terminals) < 3:
        return None

    # Prim's algorithm with a complete deterministic tie-break.  The MST is a
    # good physical default for multidrop copper: it minimizes total branch
    # length and naturally becomes a daisy-chain on a row of connectors.
    connected = {terminals[0]}
    edges = []
    while len(connected) < len(terminals):
        candidates = []
        for a in sorted(connected):
            for b in terminals:
                if b in connected:
                    continue
                candidates.append((
                    _dist(ports[a]["center"], ports[b]["center"]),
                    a, b))
        if not candidates:
            return None
        length, a, b = min(candidates)
        connected.add(b)
        edges.append((a, b, length))

    evidence = []
    for a, b, length in edges:
        allowed = ports[a]["layers"] & ports[b]["layers"]
        ordered = [layer for layer in preferred_signal_layers
                   if layer in allowed]
        # Through-hole endpoints already reach both exteriors.  Prefer B.Cu
        # for their local pair branch so the component-side escape surface is
        # preserved for SMD devices; fall back deterministically everywhere.
        if ports[a]["through"] and ports[b]["through"] and "B.Cu" in ordered:
            ordered = ["B.Cu"] + [layer for layer in ordered
                                  if layer != "B.Cu"]
        split_terminal_refs = sorted(
            ref for ref in (a, b)
            if ports[ref].get("terminal_kind") ==
            "split-member-footprints")
        bounded_terminal_fanout = bool(
            split_terminal_refs
            and length <= _SPLIT_TERMINAL_FANOUT_MAX_MM + 1e-9)
        evidence.append({
            "a": a, "b": b, "length_mm": round(length, 3),
            "layers": ordered or ["F.Cu"],
            "through_hole_edge": bool(
                ports[a]["through"] and ports[b]["through"]),
            # Two physically separate termination members cannot preserve a
            # narrow pair gap all the way to both pads.  Permit only a short,
            # explicitly bounded terminal fanout to relax the per-edge
            # coupling floor; clearance, member topology, route quality, and
            # the whole-tree coupled-coverage authority remain mandatory.
            "bounded_terminal_fanout": bounded_terminal_fanout,
            "split_terminal_refs": split_terminal_refs,
            "terminal_fanout_limit_mm": (
                _SPLIT_TERMINAL_FANOUT_MAX_MM
                if bounded_terminal_fanout else None),
        })
    return {
        "terminals": terminals,
        "ports": {
            ref: {
                "p": ports[ref]["p"][2],
                "n": ports[ref]["n"][2],
                "p_pad": str(ports[ref]["p"][1]),
                "n_pad": str(ports[ref]["n"][1]),
                "center": ports[ref]["center"],
                "layers": sorted(ports[ref]["layers"]),
                "through": ports[ref]["through"],
                "terminal_kind": ports[ref].get(
                    "terminal_kind", "same-footprint-pair"),
                "physical_refs": ports[ref].get("physical_refs", [ref]),
            }
            for ref in terminals
        },
        "edges": evidence,
        "preferred_signal_layers": list(preferred_signal_layers),
    }


def _multidrop_pair_legs(board, pair):
    """Compatibility view of :func:`_multidrop_pair_plan`.

    Placement and preflight evidence predates the paired-junction router.  Keep
    exposing the terminal-to-terminal MST while production routing consumes
    the richer plan and inserts one stub at every branching terminal.
    """
    plan = _multidrop_pair_plan(board, pair)
    if plan is None:
        return None
    ports = plan["ports"]
    legs = [
        (ports[row["a"]]["p"], ports[row["b"]]["p"],
         ports[row["a"]]["n"], ports[row["b"]]["n"])
        for row in plan["edges"]]
    return legs, plan["terminals"], plan["edges"]


def _multidrop_planar_embedding(plan, edges):
    """Derive a deterministic H/L lane orientation for each tree junction.

    Each selected copper layer is an independent tree.  Its weighted diameter
    is the professional "through" trunk; the P/N normal is propagated along
    that path without sign flips.  Off-diameter junctions inherit the closest
    assigned orientation and choose their two widest incident directions as a
    local through path.  The result is topology-derived and works for any
    paired tree, not a CAN/reference-specific layout.
    """
    ports = plan["ports"]
    by_layer = {}
    for edge in edges:
        by_layer.setdefault(edge["selected_layer"], []).append(edge)
    result = {}

    def center(ref):
        value = ports[ref].get("center")
        if value is not None:
            return tuple(value)
        p_value, n_value = ports[ref]["p"], ports[ref]["n"]
        return ((p_value[0] + n_value[0]) / 2.0,
                (p_value[1] + n_value[1]) / 2.0)

    def unit(vector):
        length = math.hypot(*vector)
        return None if length <= 1e-9 else (
            vector[0] / length, vector[1] / length)

    for layer, layer_edges in sorted(by_layer.items()):
        adjacency = {}
        for edge in layer_edges:
            adjacency.setdefault(edge["a"], []).append(
                (edge["b"], float(edge["length_mm"])))
            adjacency.setdefault(edge["b"], []).append(
                (edge["a"], float(edge["length_mm"])))
        unseen = set(adjacency)
        component_index = 0
        while unseen:
            seed = min(unseen)
            stack, component = [seed], set()
            while stack:
                ref = stack.pop()
                if ref in component:
                    continue
                component.add(ref)
                stack.extend(other for other, _length in adjacency[ref])
            unseen -= component

            def farthest(start):
                parent = {start: None}
                distance = {start: 0.0}
                todo = [start]
                while todo:
                    ref = todo.pop()
                    for other, weight in adjacency[ref]:
                        if other == parent[ref]:
                            continue
                        parent[other] = ref
                        distance[other] = distance[ref] + weight
                        todo.append(other)
                end = max(component,
                          key=lambda ref: (distance[ref], ref))
                return end, parent, distance

            first, _parent, _distance = farthest(min(component))
            last, parent, _distance = farthest(first)
            path = []
            cursor = last
            while cursor is not None:
                path.append(cursor)
                if cursor == first:
                    break
                cursor = parent[cursor]
            path.reverse()

            previous_normal = None
            for index, ref in enumerate(path):
                if len(adjacency[ref]) < 2:
                    continue
                before = path[index - 1] if index > 0 else None
                after = path[index + 1] if index + 1 < len(path) else None
                if before is None or after is None:
                    continue
                tangent = unit((center(after)[0] - center(before)[0],
                                center(after)[1] - center(before)[1]))
                if tangent is None:
                    continue
                normal = (-tangent[1], tangent[0])
                if previous_normal is None:
                    physical = unit((ports[ref]["n"][0] - ports[ref]["p"][0],
                                     ports[ref]["n"][1] - ports[ref]["p"][1]))
                    if (physical is not None
                            and normal[0] * physical[0]
                            + normal[1] * physical[1] < 0):
                        normal = (-normal[0], -normal[1])
                elif (normal[0] * previous_normal[0]
                      + normal[1] * previous_normal[1] < 0):
                    normal = (-normal[0], -normal[1])
                previous_normal = normal
                result[(ref, layer)] = {
                    "lane_axis": normal,
                    "through": [before, after],
                    "component": component_index,
                    "diameter": list(path),
                }

            # A branch junction not on the diameter still needs an orientation.
            # Select its two most separated neighbor directions, then align the
            # sign to the nearest already-oriented junction when possible.
            for ref in sorted(component):
                key = (ref, layer)
                if len(adjacency[ref]) < 2 or key in result:
                    continue
                neighbors = [other for other, _weight in adjacency[ref]]
                before, after = max(
                    ((a, b) for i, a in enumerate(neighbors)
                     for b in neighbors[i + 1:]),
                    key=lambda row: _dist(center(row[0]), center(row[1])))
                tangent = unit((center(after)[0] - center(before)[0],
                                center(after)[1] - center(before)[1]))
                if tangent is None:
                    continue
                normal = (-tangent[1], tangent[0])
                assigned = [result[(other, layer)]["lane_axis"]
                            for other in neighbors
                            if (other, layer) in result]
                if assigned and normal[0] * assigned[0][0] + \
                        normal[1] * assigned[0][1] < 0:
                    normal = (-normal[0], -normal[1])
                result[key] = {
                    "lane_axis": normal, "through": [before, after],
                    "component": component_index,
                    "diameter": list(path),
                }
            component_index += 1
    return result


def _assign_multidrop_edge_layers(plan, edges, *, max_states=8192,
                                  forced_layers=None,
                                  route_layer_evidence=None):
    """Assign available layers to a paired tree before creating junctions.

    A plated through-hole terminal is already a zero-via layer articulation.
    Greedily selecting the first layer for every edge can manufacture a
    difficult same-layer star at every connector in a chain.  Search the small
    discrete edge-coloring problem instead:

    * non-PTH internal terminals must keep all incident edges on one layer;
    * PTH terminals may articulate, and repeated incidence on one layer is the
      dominant cost because it requires a planar paired junction cell;
    * preferred-layer rank and gratuitous articulations are deterministic
      secondary costs.

    The search is bounded and branch-and-bound.  The best complete assignment
    found before the cap is returned with explicit evidence; the first-layer
    assignment is always a legal deterministic fallback.
    """
    ports = plan["ports"]
    rows = [dict(edge) for edge in edges]
    forced_layers = dict(forced_layers or {})
    route_layer_evidence = route_layer_evidence or {}
    preferred = list(plan.get("preferred_signal_layers") or ())
    rank = {layer: index for index, layer in enumerate(preferred)}
    for row in rows:
        values = []
        for layer in row.get("layers") or ("F.Cu",):
            if layer not in values:
                values.append(layer)
        key = tuple(sorted((row["a"], row["b"])))
        forced = forced_layers.get(key)
        if forced is not None:
            values = [forced] if forced in values else []
        row["_layer_options"] = values or ["F.Cu"]

    # Constrained edges first makes a useful incumbent early and strengthens
    # the collision lower bound for the remaining search.
    order = sorted(range(len(rows)), key=lambda index: (
        len(rows[index]["_layer_options"]),
        float(rows[index].get("length_mm", 0.0)),
        rows[index]["a"], rows[index]["b"]))
    best = None
    states = 0
    truncated = False

    def score_assignment(assignment):
        incidence = {}
        layers_by_ref = {}
        preferred_cost = 0
        learned_refusals = 0
        learned_timeouts = 0
        learned_successes = 0
        for index, layer in assignment.items():
            edge = rows[index]
            preferred_cost += rank.get(layer, len(preferred) + 4)
            key = tuple(sorted((edge["a"], edge["b"])))
            learned = route_layer_evidence.get(key, {}).get(layer, {})
            learned_refusals += int(learned.get("refusals", 0))
            learned_timeouts += int(learned.get("timeouts", 0))
            learned_successes += int(learned.get("successes", 0))
            for ref in (edge["a"], edge["b"]):
                incidence[(ref, layer)] = incidence.get((ref, layer), 0) + 1
                layers_by_ref.setdefault(ref, set()).add(layer)
        junction_excess = sum(max(0, count - 1)
                              for count in incidence.values())
        articulations = sum(
            max(0, len(values) - 1)
            for ref, values in layers_by_ref.items()
            if ports[ref].get("through"))
        return (junction_excess, learned_refusals, learned_timeouts,
                -learned_successes, preferred_cost, articulations)

    def non_pth_consistent(assignment):
        layers_by_ref = {}
        for index, layer in assignment.items():
            edge = rows[index]
            for ref in (edge["a"], edge["b"]):
                if not ports[ref].get("through"):
                    layers_by_ref.setdefault(ref, set()).add(layer)
        return all(len(values) <= 1 for values in layers_by_ref.values())

    def search(position, assignment):
        nonlocal best, states, truncated
        if states >= int(max_states):
            truncated = True
            return
        states += 1
        if not non_pth_consistent(assignment):
            return
        partial_score = score_assignment(assignment)
        if best is not None and partial_score[0] > best[0][0]:
            return
        if position == len(order):
            layers = tuple(assignment[index] for index in range(len(rows)))
            score = partial_score + (layers,)
            if best is None or score < best[0]:
                best = (score, dict(assignment))
            return
        index = order[position]
        options = sorted(rows[index]["_layer_options"], key=lambda layer: (
            rank.get(layer, len(preferred) + 4), layer))
        for layer in options:
            assignment[index] = layer
            search(position + 1, assignment)
            assignment.pop(index, None)

    search(0, {})
    if best is None:
        assignment = {index: row["_layer_options"][0]
                      for index, row in enumerate(rows)}
        status = "fallback-first-layer"
        score = score_assignment(assignment)
    else:
        score, assignment = best
        status = "bounded-optimum" if not truncated else "bounded-best"
    selected = [assignment[index] for index in range(len(rows))]
    incidence = {}
    for index, layer in enumerate(selected):
        for ref in (rows[index]["a"], rows[index]["b"]):
            incidence.setdefault(ref, []).append(layer)
    return {
        "status": status,
        "states_checked": states,
        "max_states": int(max_states),
        "truncated": truncated,
        "score": {
            "same_layer_junction_excess": int(score[0]),
            "learned_refusals": int(score[1]),
            "learned_timeouts": int(score[2]),
            "learned_successes": int(-score[3]),
            "preferred_layer_cost": int(score[4]),
            "pth_articulations": int(score[5]),
        },
        "selected_layers": selected,
        "forced_layers": {
            "%s-%s" % key: layer
            for key, layer in sorted(forced_layers.items())},
        "incidence": {ref: values for ref, values in sorted(incidence.items())},
    }


def _orient_junction_candidates(rows, lane_axis, pair, *, orientation_sign=1):
    """Apply one propagated lane ordering to unique candidate centres."""
    separation = float(pair["width"]) + float(pair["gap"])
    axis_length = math.hypot(*lane_axis)
    if axis_length <= 1e-9:
        return list(rows)
    sign = 1 if float(orientation_sign) >= 0 else -1
    axis = (sign * lane_axis[0] / axis_length,
            sign * lane_axis[1] / axis_length)
    output, seen = [], set()
    for row in rows:
        center = tuple(row["center"])
        key = (round(center[0], 6), round(center[1], 6))
        if key in seen:
            continue
        seen.add(key)
        value = dict(row)
        value["p"] = (center[0] - axis[0] * separation / 2.0,
                      center[1] - axis[1] * separation / 2.0)
        value["n"] = (center[0] + axis[0] * separation / 2.0,
                      center[1] + axis[1] * separation / 2.0)
        value["lane_axis"] = [round(axis[0], 6), round(axis[1], 6)]
        value["embedding_sign"] = sign
        output.append(value)
    return output


def _classify_junction_candidates(rows, lane_axis, *, orientation_sign=None):
    """Classify package-native breakouts against a propagated trunk order.

    A connector can present the two members several millimetres apart and at
    an angle unrelated to the eventual coupled trunk.  Replacing that natural
    launch geometry with the trunk's narrow lane geometry makes the terminal
    fan-in needlessly (and sometimes topologically) impossible.  Preserve the
    candidate endpoints and attach only their lane-order sign here.  The local
    star subsequently performs the bounded orientation transition to a narrow,
    globally ordered throat.

    ``orientation_sign`` filters to one already-selected component ordering;
    ``None`` returns both orders in the generator's deterministic preference.
    """
    axis_length = math.hypot(*lane_axis)
    if axis_length <= 1e-9:
        return [dict(row) for row in rows]
    axis = (lane_axis[0] / axis_length, lane_axis[1] / axis_length)
    output = []
    for row in rows:
        local = (row["n"][0] - row["p"][0],
                 row["n"][1] - row["p"][1])
        local_length = math.hypot(*local)
        if local_length <= 1e-9:
            continue
        dot = (local[0] * axis[0] + local[1] * axis[1]) / local_length
        sign = 1 if dot >= 0.0 else -1
        if orientation_sign is not None and sign != int(orientation_sign):
            continue
        value = dict(row)
        value["local_lane_axis"] = [
            round(local[0] / local_length, 6),
            round(local[1] / local_length, 6)]
        value["trunk_lane_axis"] = [round(axis[0], 6), round(axis[1], 6)]
        value["embedding_sign"] = sign
        output.append(value)
    return output


def _expand_junction_trunk_signs(rows, lane_axis, *, trunk_sign=None):
    """Cross package-native launches with legal component trunk orders.

    Local pad orientation is a footprint property: rotating a connector 180
    degrees reverses its geometric axis without swapping the electrical nets.
    The component trunk order is a routing variable.  Keep those variables
    separate and let exact local-star admission prove whether a launch can
    transition to a requested trunk order.
    """
    classified = _classify_junction_candidates(rows, lane_axis)
    output = []
    seen = set()
    for row in classified:
        local_sign = int(row.get("embedding_sign", 1))
        signs = ([int(trunk_sign)] if trunk_sign is not None
                 else [local_sign, -local_sign])
        for sign in signs:
            center = tuple(row["center"])
            key = (round(center[0], 6), round(center[1], 6), sign)
            if key in seen:
                continue
            seen.add(key)
            value = dict(row)
            value["local_embedding_sign"] = local_sign
            value["embedding_sign"] = sign
            output.append(value)
    return output


def _mitered_junction_candidate(plan, pair, ref, layer, junction,
                                incident_edges, embedding):
    """Turn a virtual centre into a planar offset-ribbon junction cell.

    A pair corner cannot use two arbitrary points around the centre: the inner
    and outer lanes meet at different miter intersections.  Build the local
    through centreline, offset it by half the pair centre spacing, and use the
    exact offset vertices for both the junction and its two through throats.
    Additional branches receive edge-normal throats whose order is selected by
    minimum connection distance; the whole-star authority still admits or
    refuses the resulting cell atomically.
    """
    value = dict(junction)
    center = tuple(value["center"])
    embedding_row = embedding.get((ref, layer)) or {}
    neighbors = [edge["b"] if edge["a"] == ref else edge["a"]
                 for edge in incident_edges]
    through = [other for other in embedding_row.get("through", ())
               if other in neighbors]
    if len(through) < 2 and len(neighbors) >= 2:
        through = list(max(
            ((a, b) for index, a in enumerate(neighbors)
             for b in neighbors[index + 1:]),
            key=lambda row: _dist(plan["ports"][row[0]]["center"],
                                  plan["ports"][row[1]]["center"])))
    if len(through) < 2:
        return value

    edge_by_neighbor = {
        (edge["b"] if edge["a"] == ref else edge["a"]): edge
        for edge in incident_edges}

    def throat_center(other):
        edge = edge_by_neighbor[other]
        other_center = tuple(plan["ports"][other]["center"])
        direction = (other_center[0] - center[0],
                     other_center[1] - center[1])
        length = math.hypot(*direction)
        if length <= 1e-9:
            return center, 0.0
        direction = (direction[0] / length, direction[1] / length)
        reach = min(1.5, max(0.75, 0.12 * float(edge["length_mm"])))
        return ((center[0] + direction[0] * reach,
                 center[1] + direction[1] * reach), reach)

    before, after = through[:2]
    before_center, before_reach = throat_center(before)
    after_center, after_reach = throat_center(after)
    offset = (float(pair["width"]) + float(pair["gap"])) / 2.0
    ribbons = _offset_centerline([before_center, center, after_center], offset)
    if ribbons is None:
        return value
    left, right = ribbons
    sign = int(value.get("embedding_sign", 1))
    p_path, n_path = ((right, left) if sign >= 0 else (left, right))
    value["p"], value["n"] = p_path[1], n_path[1]
    throats = {
        before: {
            "center": before_center, "p": p_path[0], "n": n_path[0],
            "length_mm": round(before_reach, 3)},
        after: {
            "center": after_center, "p": p_path[2], "n": n_path[2],
            "length_mm": round(after_reach, 3)},
    }

    # Branches outside the principal through path use their own edge normal.
    # Choose its polarity by the shorter non-crossed connection to the mitered
    # node; exact star geometry remains the final authority.
    separation = 2.0 * offset
    for other in neighbors:
        if other in throats:
            continue
        branch_center, reach = throat_center(other)
        direction = (branch_center[0] - center[0],
                     branch_center[1] - center[1])
        length = math.hypot(*direction)
        if length <= 1e-9:
            continue
        normal = (-direction[1] / length, direction[0] / length)
        first = {
            "p": (branch_center[0] - normal[0] * separation / 2.0,
                  branch_center[1] - normal[1] * separation / 2.0),
            "n": (branch_center[0] + normal[0] * separation / 2.0,
                  branch_center[1] + normal[1] * separation / 2.0),
        }
        second = {"p": first["n"], "n": first["p"]}
        selected = min(
            (first, second),
            key=lambda row: (_dist(value["p"], row["p"])
                             + _dist(value["n"], row["n"])))
        throats[other] = dict(
            selected, center=branch_center, length_mm=round(reach, 3))
    for other, throat in throats.items():
        lane = (throat["n"][0] - throat["p"][0],
                throat["n"][1] - throat["p"][1])
        lane_length = math.hypot(*lane)
        throat["lane_axis"] = [
            round(lane[0] / lane_length, 6),
            round(lane[1] / lane_length, 6)]
    value["_junction_throats"] = throats
    value["junction_geometry"] = "mitered-offset-ribbon"
    return value


def _multidrop_junction_throats(plan, pair, ref, layer, junction,
                                incident_edges, embedding):
    """Return the exact narrow portals for one package-native local star.

    The terminal launch keeps the footprint's natural P/N orientation.  Each
    incident tree edge receives a short portal in its physical direction, but
    every portal uses the component-wide trunk order.  Routing the launch and
    these spokes together is therefore an exact local feasibility test for a
    professional fan-in/fan-out cell rather than a point approximation.
    """
    if junction.get("_junction_throats") is not None:
        return {key: dict(row)
                for key, row in junction["_junction_throats"].items()}
    embedding_row = embedding.get((ref, layer)) or {}
    axis = tuple(embedding_row.get("lane_axis") or (
        junction["n"][0] - junction["p"][0],
        junction["n"][1] - junction["p"][1]))
    axis_length = math.hypot(*axis)
    if axis_length <= 1e-9:
        return {}
    orientation_sign = int(junction.get("embedding_sign", 1))
    axis = (orientation_sign * axis[0] / axis_length,
            orientation_sign * axis[1] / axis_length)
    separation = float(pair["width"]) + float(pair["gap"])
    output = {}
    for edge in incident_edges:
        other = edge["b"] if edge["a"] == ref else edge["a"]
        other_center = tuple(plan["ports"][other]["center"])
        direction = (other_center[0] - junction["center"][0],
                     other_center[1] - junction["center"][1])
        direction_length = math.hypot(*direction)
        if direction_length <= 1e-9:
            continue
        direction = (direction[0] / direction_length,
                     direction[1] / direction_length)
        throat_length = min(
            1.5, max(0.75, 0.12 * float(edge["length_mm"])))
        throat_center = (
            junction["center"][0] + direction[0] * throat_length,
            junction["center"][1] + direction[1] * throat_length)
        output[other] = {
            "center": throat_center,
            "p": (throat_center[0] - axis[0] * separation / 2.0,
                  throat_center[1] - axis[1] * separation / 2.0),
            "n": (throat_center[0] + axis[0] * separation / 2.0,
                  throat_center[1] + axis[1] * separation / 2.0),
            "lane_axis": [round(axis[0], 6), round(axis[1], 6)],
            "length_mm": round(throat_length, 3),
        }
    return output


def _multidrop_junction_candidates(board, plan, ref, pair,
                                   max_candidates=48):
    """Return bounded paired junctions beside one internal bus terminal.

    An internal multidrop terminal needs one pad escape, not one escape per
    incident tree edge.  Candidate junctions are derived from the physical
    neighbor vectors and board interior, then retain the P/N pad ordering or a
    normal-to-launch coupled ordering.  No reference or connector family is
    special-cased; exact copper guards decide which candidate is usable.
    """
    port = plan["ports"][ref]
    center = tuple(port["center"])
    neighbors = []
    for row in plan["edges"]:
        if row["a"] == ref:
            neighbors.append(plan["ports"][row["b"]]["center"])
        elif row["b"] == ref:
            neighbors.append(plan["ports"][row["a"]]["center"])
    if len(neighbors) < 2:
        return []

    def unit(vector):
        length = math.hypot(*vector)
        if length <= 1e-9:
            return None
        return vector[0] / length, vector[1] / length

    directions = []

    def add_direction(vector):
        value = unit(vector)
        if value is None:
            return
        key = (round(value[0], 6), round(value[1], 6))
        if key not in {(round(row[0], 6), round(row[1], 6))
                       for row in directions}:
            directions.append(value)

    neighbor_units = [unit((point[0] - center[0], point[1] - center[1]))
                      for point in neighbors]
    neighbor_units = [row for row in neighbor_units if row is not None]
    add_direction((sum(row[0] for row in neighbor_units),
                   sum(row[1] for row in neighbor_units)))

    # For a terminal on a straight run the neighbor vectors cancel.  Put the
    # trunk on either side of the terminal rather than placing its junction on
    # top of a pad bank.
    trunk_normal = None
    if len(neighbors) >= 2:
        longest = max(
            ((a, b) for i, a in enumerate(neighbors)
             for b in neighbors[i + 1:]),
            key=lambda ab: _dist(ab[0], ab[1]))
        tangent = unit((longest[1][0] - longest[0][0],
                        longest[1][1] - longest[0][1]))
        if tangent is not None:
            trunk_normal = (-tangent[1], tangent[0])
            add_direction(trunk_normal)
            add_direction((-trunk_normal[0], -trunk_normal[1]))

    # Board-interior direction is a stable preference for edge connectors.
    try:
        bbox = board.GetBoardEdgesBoundingBox()
        board_center = ((bbox.GetX() + bbox.GetWidth() / 2.0) / MM,
                        (bbox.GetY() + bbox.GetHeight() / 2.0) / MM)
        add_direction((board_center[0] - center[0],
                       board_center[1] - center[1]))
    except Exception:                                  # noqa: BLE001
        pass
    for row in neighbor_units:
        add_direction(row)
    for row in ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0),
                (1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)):
        add_direction(row)

    p_value, n_value = tuple(port["p"]), tuple(port["n"])
    pad_axis = unit((n_value[0] - p_value[0], n_value[1] - p_value[1]))
    separation = float(pair["width"]) + float(pair["gap"])
    physical_span = _dist(p_value, n_value)
    first_distance = max(1.5, physical_span * 0.65 + 0.6)
    distances = sorted({round(min(6.0, first_distance + delta), 6)
                        for delta in (0.0, 0.75, 1.5, 2.5, 3.5)})
    candidates = []
    seen = set()
    for distance in distances:
        # Breadth before depth: cover every physical direction with the best
        # trunk-normal lane before spending the bounded budget on secondary
        # lane orientations.  The old direction-major loop could consume all
        # 32 slots around only a few headings and falsely report no junction.
        for lane_index in range(5):
            for direction in directions:
                junction_center = (center[0] + direction[0] * distance,
                                   center[1] + direction[1] * distance)
                lane_axes = []
                # A paired trunk has one planar lane ordering.  Align its
                # virtual H/L junctions normal to the local through direction
                # before trying the package's unrelated pad-bank axis.
                if trunk_normal is not None:
                    lane_axes.extend((trunk_normal,
                                      (-trunk_normal[0], -trunk_normal[1])))
                if pad_axis is not None:
                    lane_axes.append(pad_axis)
                lane_axes.extend(((-direction[1], direction[0]),
                                  (direction[1], -direction[0])))
                if lane_index >= len(lane_axes):
                    continue
                lane = lane_axes[lane_index]
                p_join = (junction_center[0] - lane[0] * separation / 2.0,
                          junction_center[1] - lane[1] * separation / 2.0)
                n_join = (junction_center[0] + lane[0] * separation / 2.0,
                          junction_center[1] + lane[1] * separation / 2.0)
                key = tuple(round(value, 6)
                            for point in (p_join, n_join) for value in point)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "ref": ref,
                    "p": p_join,
                    "n": n_join,
                    "center": junction_center,
                    "distance_mm": round(distance, 3),
                    "direction": [round(direction[0], 6),
                                  round(direction[1], 6)],
                })
                if len(candidates) >= int(max_candidates):
                    return candidates
    return candidates


def _pair_graph_geometry(board, pair, created_ids, physical_only=False):
    """Check pair-member crossings and spacing across a routed bus graph.

    The point-to-point router checks each leg in isolation.  A multidrop graph
    additionally needs a whole-graph authority so a later leg cannot cross an
    earlier sibling while both nets are excluded from foreign-copper checks.
    Shared same-net junction endpoints are intentional and are never waived
    between the two different members.
    """
    scope = set(created_ids or ())
    by_net = {pair["p"]: [], pair["n"]: []}
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_TRACK"
                or item.m_Uuid.AsString() not in scope
                or item.GetNetname() not in by_net):
            continue
        start, end = item.GetStart(), item.GetEnd()
        by_net[item.GetNetname()].append({
            "uuid": item.m_Uuid.AsString(),
            "a": (start.x / MM, start.y / MM),
            "b": (end.x / MM, end.y / MM),
            "layer": int(item.GetLayer()),
        })
    issues = []
    # The main coupled-route solver must hold the electrical pair gap.  The
    # final duplicate-pad closure, however, necessarily necks down to the
    # package pitch and is admitted by physical copper clearance.  Do not
    # reject a legal connector escape merely because its land pitch is smaller
    # than the controlled-impedance centre spacing; do still reject every P/N
    # crossing or copper overlap (the failure this whole-graph audit guards).
    minimum = ((float(pair["width"]) if physical_only else
                float(pair["width"]) + float(pair["gap"])) - 1e-6)
    for p_row in by_net[pair["p"]]:
        for n_row in by_net[pair["n"]]:
            if p_row["layer"] != n_row["layer"]:
                continue
            distance = _seg_seg_dist(
                p_row["a"], p_row["b"], n_row["a"], n_row["b"])
            crossing = _seg_cross(
                p_row["a"], p_row["b"], n_row["a"], n_row["b"])
            if crossing or distance + 1e-7 < minimum:
                issues.append({
                    "type": "member_crossing" if crossing
                            else "member_clearance",
                    "layer": board.GetLayerName(p_row["layer"]),
                    "p_uuid": p_row["uuid"], "n_uuid": n_row["uuid"],
                    "p_segment_mm": [
                        [round(value, 6) for value in p_row["a"]],
                        [round(value, 6) for value in p_row["b"]]],
                    "n_segment_mm": [
                        [round(value, 6) for value in n_row["a"]],
                        [round(value, 6) for value in n_row["b"]]],
                    "distance_mm": round(distance, 6),
                    "minimum_mm": round(minimum, 6),
                })
    # Crossed branches of one member are also a needless bus loop even though
    # they are electrically legal and cannot be found by P-vs-N spacing.
    for net, rows in by_net.items():
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                if first["layer"] != second["layer"]:
                    continue
                if _seg_cross(first["a"], first["b"],
                              second["a"], second["b"]):
                    issues.append({
                        "type": "self_crossing", "net": net,
                        "layer": board.GetLayerName(first["layer"]),
                        "first_uuid": first["uuid"],
                        "second_uuid": second["uuid"],
                    })
    return {"ok": not issues, "issues": issues,
            "p_segments": len(by_net[pair["p"]]),
            "n_segments": len(by_net[pair["n"]])}


def _route_paired_stub(board, pair, endpoints, *, layer="F.Cu",
                       clearance=0.20, avoid=(), allow_detour=True,
                       minimum_coupled_fraction=0.0, deadline=None,
                       detour_member_paths=32,
                       preferred_end_direction=None,
                       minimum_end_heading_alignment=0.0,
                       allow_terminal_gap_taper=False,
                       foreign_shape_cache=None,
                       partner_shape_cache=None,
                       blocker_shape_cache=None):
    """Lay one short paired terminal escape without invoking global A*.

    Multidrop candidate selection may evaluate several nearby junctions.  A
    full-board grid search for every 2--6 mm terminal stub is both wasteful and
    opaque.  This local solver enumerates bounded chamfered dogbones, applies
    the exact edge/foreign-pad/partner-pad guards, and emits copper only after
    the two members pass their joint crossing and spacing test.
    """
    try:
        p_start, p_end, n_start, n_end = endpoints
    except (TypeError, ValueError):
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "invalid paired stub endpoints"}
    if _deadline_expired(deadline):
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "paired terminal search deadline exhausted"}
    layer_id = board.GetLayerID(layer)
    if layer_id < 0:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "layer %s absent" % layer}
    avoid = _avoid_for_layer(avoid, layer)
    width, gap = float(pair["width"]), float(pair["gap"])
    width_nm = _nm(width)
    clearance_nm = _nm(clearance)
    p_code = board.GetNetcodeFromNetname(pair["p"])
    n_code = board.GetNetcodeFromNetname(pair["n"])
    own = {p_code, n_code}
    # Candidate enumeration is intentionally broad, but the board geometry is
    # immutable until one complete paired stub is admitted.  Walking every
    # footprint/track and rebuilding KiCad effective shapes for every dogbone
    # leg made this bounded search consume its wall-clock limit rather than
    # exhaust its finite candidate domain.  Reuse the same exact Collide()-
    # based spatial snapshot as the grid router.  Callers that transactionally
    # add/remove only the two exempt pair nets may safely share these indexes
    # across candidate probes; foreign-copper mutations must use a fresh cache.
    foreign_shape_cache = ({} if foreign_shape_cache is None
                           else foreign_shape_cache)
    foreign_zones, foreign_copper = cec_fr._foreign_shape_indexes(
        board, layer_id, own, cache=foreign_shape_cache)
    partner_shape_cache = ({} if partner_shape_cache is None
                           else partner_shape_cache)
    blocker_shape_cache = ({} if blocker_shape_cache is None
                           else blocker_shape_cache)

    def blocker_shapes():
        key = (int(layer_id), tuple(sorted(int(code) for code in own)))
        if key not in blocker_shape_cache:
            blocker_shape_cache[key] = \
                cec_fr._identified_foreign_shape_indexes(
                    board, layer_id, own)
        return blocker_shape_cache[key]

    def partner_shapes(net_code):
        key = (int(layer_id), int(net_code))
        if key in partner_shape_cache:
            return partner_shape_cache[key]
        rows = []
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if (pad.GetNetCode() != int(net_code)
                        or layer_id not in pad.GetLayerSet().CuStack()):
                    continue
                try:
                    shape = pad.GetEffectiveShape(layer_id)
                    rows.append((shape, shape.BBox()))
                except Exception:                    # noqa: BLE001
                    # Preserve the historical guard: an engine-specific pad
                    # shape failure skips only that shape, not the whole test.
                    continue
        indexed = cec_fr._bucket_foreign_shapes(rows)
        partner_shape_cache[key] = indexed
        return indexed

    def member_admission(a, b, partner_code):
        if a == b:
            return {"board_edge": True, "foreign_copper": True,
                    "partner_pad": True, "partner_copper": True,
                    "ok": True}
        value = {
            "board_edge": cec_fr._edge_leg_clear(
                board, _v(*a), _v(*b), width_nm // 2, edge_mm=0.5),
            "foreign_copper": cec_fr._snapshot_foreign_clear(
                _v(*a), _v(*b), width_nm, clearance_nm,
                foreign_zones, foreign_copper),
            "partner_pad": _partner_pads_clear(
                board, a, b, width_nm, layer_id,
                partner_code, clearance_nm,
                partner_shapes=partner_shapes(partner_code)),
            # Existing copper of the opposite pair member is allowed to run
            # beside this segment at the specified pair gap, but it may never
            # physically overlap or cross it.  This matters when an inline
            # package tie or an earlier topology edge is already present.
            "partner_copper": _partner_tracks_clear(
                board, a, b, width_nm, layer_id, partner_code),
        }
        if not value["foreign_copper"]:
            identified = blocker_shapes()
            if identified is not None:
                value["foreign_blockers"] = \
                    cec_fr._snapshot_foreign_blockers(
                        _v(*a), _v(*b), width_nm, clearance_nm,
                        identified[0], identified[1])
        value["ok"] = all(value.values())
        # Evidence is not an admission term.  ``all(value.values())`` above
        # deliberately precedes the optional blocker list so a populated
        # diagnostic cannot turn a refusal into truth.
        value["ok"] = (value["board_edge"]
                       and value["foreign_copper"]
                       and value["partner_pad"]
                       and value["partner_copper"])
        return value

    def member_clear(a, b, partner_code):
        return member_admission(a, b, partner_code)["ok"]

    p_direct, n_direct = [p_start, p_end], [n_start, n_end]
    p_direct_admission = member_admission(p_start, p_end, n_code)
    n_direct_admission = member_admission(n_start, n_end, p_code)
    direct_crossing_free = _polys_no_cross(p_direct, n_direct)
    direct_spacing_ok = _pair_min_clear(
        p_direct, n_direct, -1, -1, width, gap)
    # A hard reversal cannot be repaired at the portal handoff.  Callers may
    # raise this floor when dissimilar pin fields require a forward taper;
    # otherwise an orthogonal arrival remains a legal assembled-route
    # fallback.  The joint solver's score still prefers <=67.5deg arrivals.
    minimum_heading_alignment = float(minimum_end_heading_alignment)
    direct_heading_alignment = min(
        _path_end_heading_alignment(
            p_direct, preferred_end_direction),
        _path_end_heading_alignment(
            n_direct, preferred_end_direction))
    direct_heading_ok = (
        direct_heading_alignment + 1e-9 >= minimum_heading_alignment)
    admission = {
        "direct": {
            "p": p_direct_admission,
            "n": n_direct_admission,
            "crossing_free": direct_crossing_free,
            "pair_spacing": direct_spacing_ok,
            "heading_alignment": round(direct_heading_alignment, 6),
            "heading_compatible": direct_heading_ok,
        },
        "detour": {},
        "paired_ribbon": {},
    }
    solved = None
    paired_ribbon = None
    ribbon_rejections = []
    for ribbon in _short_pair_ribbon_candidates(
            pair, p_start, p_end, n_start, n_end):
        if _deadline_expired(deadline):
            break
        p_points, n_points = ribbon["p"], ribbon["n"]
        p_admissions = [member_admission(a, b, n_code)
                        for a, b in zip(p_points, p_points[1:])]
        n_admissions = [member_admission(a, b, p_code)
                        for a, b in zip(n_points, n_points[1:])]
        p_clear = all(row["ok"] for row in p_admissions)
        n_clear = all(row["ok"] for row in n_admissions)
        crossing_free = _polys_no_cross(p_points, n_points)
        pair_spacing = _pair_min_clear(
            p_points, n_points, 1, 1, width, gap,
            strict_pair_gap=True)
        reservation = (_crosses_avoid(p_points, avoid, width)
                       or _crosses_avoid(n_points, avoid, width))
        ribbon_heading = min(
            _path_end_heading_alignment(
                p_points, preferred_end_direction),
            _path_end_heading_alignment(
                n_points, preferred_end_direction))
        minimum_opening = min(
            _polyline_min_opening_angle(p_points),
            _polyline_min_opening_angle(n_points))
        turn_quality = minimum_opening + 1.0e-9 >= 89.0
        accepted = bool(
            p_clear and n_clear and crossing_free and pair_spacing
            and not reservation
            and ribbon["coupling_contract"]["ok"]
            and turn_quality
            and ribbon_heading + 1e-9 >= minimum_heading_alignment)
        public = {key: value for key, value in ribbon.items()
                  if key not in ("p", "n")}
        public.update({
            "p_clear": p_clear, "n_clear": n_clear,
            "crossing_free": crossing_free,
            "pair_spacing": pair_spacing,
            "reservation": reservation,
            "heading_alignment": round(ribbon_heading, 6),
            "minimum_opening_angle_deg": round(minimum_opening, 6),
            "turn_quality": turn_quality,
            "accepted": accepted,
        })
        # Preserve the first exact failing legs.  A Boolean-only rejection
        # makes a legalizer blind to whether the funnel hit the board edge,
        # foreign copper, the sibling pad, or already-routed sibling copper.
        # Coordinates plus the four stable admission terms are compact enough
        # for certificates and generic placement feedback.
        for member, points, rows in (("p", p_points, p_admissions),
                                     ("n", n_points, n_admissions)):
            failures = []
            for (a, b), row in zip(zip(points, points[1:]), rows):
                if row["ok"]:
                    continue
                failures.append({
                    "start": [round(float(a[0]), 6), round(float(a[1]), 6)],
                    "end": [round(float(b[0]), 6), round(float(b[1]), 6)],
                    **{key: row.get(key) for key in (
                        "board_edge", "foreign_copper", "partner_pad",
                        "partner_copper", "foreign_blockers")
                       if key in row},
                })
            if failures:
                public[f"{member}_failures"] = failures[:3]
        if accepted:
            solved = (p_points, n_points)
            paired_ribbon = public
            break
        ribbon_rejections.append(public)
    admission["paired_ribbon"] = {
        "selected": paired_ribbon,
        "rejected": ribbon_rejections[:4],
    }
    if solved is not None:
        pass
    elif (p_direct_admission["ok"]
            and n_direct_admission["ok"]
            and direct_crossing_free and direct_spacing_ok
            and direct_heading_ok):
        solved = (p_direct, n_direct)
    elif allow_detour:
        solved = _joint_endpoint_escape(
            p_start, n_start, p_end, n_end, width=width, gap=gap,
            p_segment_clear=lambda a, b: member_clear(a, b, n_code),
            n_segment_clear=lambda a, b: member_clear(a, b, p_code),
            max_detour=max(_pair_escape_budget(p_start, n_start),
                           _pair_escape_budget(p_end, n_end)),
            max_skew=float(pair.get(
                "skew_limit_mm",
                3.81 if pair.get("kind") == "usb" else 4.0)),
            max_member_paths=int(detour_member_paths),
            preferred_end_direction=preferred_end_direction,
            diagnostics=admission["detour"], deadline=deadline)
    else:
        solved = None
        admission["detour"]["skipped"] = True
    if solved is None:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": ("no clear direct paired terminal stub"
                            if not allow_detour
                            else "no clear bounded paired terminal stub"),
                "admission": admission}
    p_points, n_points = solved
    heading_alignment = min(
        _path_end_heading_alignment(
            p_points, preferred_end_direction),
        _path_end_heading_alignment(
            n_points, preferred_end_direction))
    if heading_alignment + 1e-9 < minimum_heading_alignment:
        admission["selected_heading_alignment"] = round(
            heading_alignment, 6)
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": "paired terminal handoff arrives against trunk heading",
            "admission": admission,
        }
    if (float(minimum_coupled_fraction) > 0.0
            and not allow_terminal_gap_taper
            and not _pair_min_clear(
                p_points, n_points, -1, -1, width, gap,
                strict_pair_gap=True)):
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": "paired trunk path violates requested pair gap",
            "admission": admission,
        }
    coupling = _polyline_coupling_coverage(
        p_points, n_points, width, gap)
    if coupling["fraction"] + 1e-9 < float(minimum_coupled_fraction):
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": "paired terminal path coupling %.1f%% is below %.1f%%" % (
                100.0 * coupling["fraction"],
                100.0 * float(minimum_coupled_fraction)),
            "coupling": coupling,
            "admission": admission,
        }
    p_avoid = _crosses_avoid(p_points, avoid, width)
    n_avoid = _crosses_avoid(n_points, avoid, width)
    if p_avoid or n_avoid:
        reservation_hits = []
        for member, points in (("p", p_points), ("n", n_points)):
            for hit in _crosses_avoid_details(points, avoid, width):
                reservation_hits.append(dict(hit, member=member))
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "paired terminal stub entered reservation %s" %
                           (p_avoid or n_avoid),
                "reservation_hits": reservation_hits,
                "admission": admission}
    laid = _lay(board, p_code, p_points, width_nm, layer_id)
    laid += _lay(board, n_code, n_points, width_nm, layer_id)
    p_length = sum(_dist(a, b) for a, b in zip(p_points, p_points[1:]))
    n_length = sum(_dist(a, b) for a, b in zip(n_points, n_points[1:]))
    return {
        "name": pair["name"], "p": pair["p"], "n": pair["n"],
        "route_mode": "paired-terminal-stub", "layer": layer,
        "segments": len(laid),
        "length_mm": round(max(p_length, n_length), 2),
        "coupled_len_mm": round(min(p_length, n_length), 2),
        "coupled_coverage_pct": coupling["coverage_pct"],
        "handoff_heading_alignment": round(heading_alignment, 6),
        "terminal_gap_policy": (
            "symmetric-pitch-taper" if paired_ribbon is not None else
            "pad-pitch-taper" if allow_terminal_gap_taper else
            "strict-nominal"),
        "local_search": {
            "used_detour": solved != (p_direct, n_direct),
            "paired_ribbon": paired_ribbon,
            "paired_ribbon_rejected": ribbon_rejections[:4],
            "detour": admission.get("detour") or {},
        },
    }


def _route_multidrop_pair_tree(board, pair, plan, *, avoid=(),
                               pair_grid=False, verbose=False,
                               max_variants=12, variant_start=0):
    """Route a paired MST as one trunk/stub transaction.

    Internal terminals receive a single paired stub into a nearby virtual
    junction; all tree edges meet that junction instead of independently
    relaunching from the same pad.  Candidate selection is bounded and
    deterministic.  Every failed variant is rolled back, and the whole-graph
    pair geometry must pass before any copper is returned to the caller.
    """
    base_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    ports = plan["ports"]
    degrees = {ref: 0 for ref in plan["terminals"]}
    for row in plan["edges"]:
        degrees[row["a"]] += 1
        degrees[row["b"]] += 1
    branch_refs = sorted(ref for ref, degree in degrees.items() if degree >= 2)
    candidates = {
        ref: _multidrop_junction_candidates(board, plan, ref, pair)
        for ref in branch_refs}
    if any(not rows for rows in candidates.values()):
        missing = sorted(ref for ref, rows in candidates.items() if not rows)
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "no paired junction candidate for %s" % missing,
                "paired_terminals": plan["terminals"],
                "tree_edges": plan["edges"]}

    common_layers = None
    for ref in plan["terminals"]:
        layers = set(ports[ref]["layers"])
        common_layers = layers if common_layers is None else common_layers & layers
    preferred = list(plan.get("preferred_signal_layers") or ())
    layer_attempts = [row for row in preferred if row in (common_layers or set())]
    if not layer_attempts:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "multidrop terminals have no common copper layer",
                "paired_terminals": plan["terminals"],
                "tree_edges": plan["edges"]}

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                board.Remove(item)

    refusals = []
    for layer in layer_attempts:
        # Select internal junctions independently.  Advancing every terminal's
        # candidate index in lockstep is an artificial search constraint: one
        # crowded leaf may need an outward junction while every other terminal
        # already has the best local choice.  Prove each terminal stub together
        # with all of its degree-one branches using the cheap local solver, and
        # move the first whole-graph-clean choice to the front of that terminal's
        # own list before any global A* work begins.
        active_candidates = {ref: list(rows)
                             for ref, rows in candidates.items()}
        candidate_prefilter = {}
        for ref in branch_refs:
            leaf_edges = []
            for edge in plan["edges"]:
                if edge["a"] == ref and degrees[edge["b"]] == 1:
                    leaf_edges.append((edge, edge["b"]))
                elif edge["b"] == ref and degrees[edge["a"]] == 1:
                    leaf_edges.append((edge, edge["a"]))
            selected_index = None
            checked = 0
            for index, junction in enumerate(active_candidates[ref]):
                rollback()
                checked += 1
                port = ports[ref]
                report = _route_paired_stub(
                    board, pair,
                    (port["p"], junction["p"],
                     port["n"], junction["n"]),
                    avoid=avoid, layer=layer)
                if report.get("refused"):
                    continue
                leaf_failed = False
                for _edge, leaf_ref in leaf_edges:
                    leaf = ports[leaf_ref]
                    report = _route_paired_stub(
                        board, pair,
                        (junction["p"], leaf["p"],
                         junction["n"], leaf["n"]),
                        avoid=avoid, layer=layer)
                    if report.get("refused"):
                        leaf_failed = True
                        break
                if leaf_failed:
                    continue
                created = {item.m_Uuid.AsString()
                           for item in board.GetTracks()
                           if item.m_Uuid.AsString() not in base_ids}
                if _pair_graph_geometry(board, pair, created)["ok"]:
                    selected_index = index
                    break
            rollback()
            candidate_prefilter[ref] = {
                "leaf_terminals": sorted(row[1] for row in leaf_edges),
                "checked": checked,
                "selected_original_index": selected_index,
            }
            if selected_index is not None:
                rows = active_candidates[ref]
                active_candidates[ref] = (
                    [rows[selected_index]] + rows[:selected_index]
                    + rows[selected_index + 1:])

        def leaf_neighbors(ref):
            values = []
            for edge in plan["edges"]:
                if edge["a"] == ref and degrees[edge["b"]] == 1:
                    values.append(edge["b"])
                elif edge["b"] == ref and degrees[edge["a"]] == 1:
                    values.append(edge["a"])
            return sorted(values)

        def local_edge_assignment_ok(edge, assignment):
            """Cheap arc-consistency probe for two neighboring junctions."""
            rollback()
            for ref, junction in sorted(assignment.items()):
                port = ports[ref]
                report = _route_paired_stub(
                    board, pair,
                    (port["p"], junction["p"],
                     port["n"], junction["n"]),
                    avoid=avoid, layer=layer)
                if report.get("refused"):
                    rollback()
                    return False
                for leaf_ref in leaf_neighbors(ref):
                    leaf = ports[leaf_ref]
                    report = _route_paired_stub(
                        board, pair,
                        (junction["p"], leaf["p"],
                         junction["n"], leaf["n"]),
                        avoid=avoid, layer=layer)
                    if report.get("refused"):
                        rollback()
                        return False
            a_port = assignment.get(edge["a"], ports[edge["a"]])
            b_port = assignment.get(edge["b"], ports[edge["b"]])
            report = _route_paired_stub(
                board, pair,
                (a_port["p"], b_port["p"],
                 a_port["n"], b_port["n"]),
                avoid=avoid, layer=layer)
            created = {item.m_Uuid.AsString() for item in board.GetTracks()
                       if item.m_Uuid.AsString() not in base_ids}
            ok = (not report.get("refused")
                  and _pair_graph_geometry(board, pair, created)["ok"])
            rollback()
            return ok

        # Enforce pairwise compatibility along internal trunk arcs before the
        # expensive router runs.  Change the less-constrained endpoint first
        # (a junction without a leaf breakout) and never disturb unrelated
        # terminals.  Two bounded propagation rounds are enough for a tree:
        # any changed vertex is reconsidered against its other neighbor.
        pairwise_adjustments = []
        internal_edges = [
            row for row in plan["edges"]
            if degrees[row["a"]] >= 2 and degrees[row["b"]] >= 2]
        for propagation_round in range(2):
            changed = False
            for edge in sorted(internal_edges,
                               key=lambda row: (row["length_mm"],
                                                row["a"], row["b"])):
                assignment = {
                    edge["a"]: active_candidates[edge["a"]][0],
                    edge["b"]: active_candidates[edge["b"]][0],
                }
                if local_edge_assignment_ok(edge, assignment):
                    continue
                endpoints = sorted(
                    (edge["a"], edge["b"]),
                    key=lambda ref: (len(leaf_neighbors(ref)), ref))
                repaired = False
                for target in endpoints:
                    other = edge["b"] if target == edge["a"] else edge["a"]
                    for index, candidate in enumerate(
                            active_candidates[target][1:13], start=1):
                        trial = {target: candidate,
                                 other: active_candidates[other][0]}
                        if not local_edge_assignment_ok(edge, trial):
                            continue
                        rows = active_candidates[target]
                        active_candidates[target] = (
                            [rows[index]] + rows[:index]
                            + rows[index + 1:])
                        pairwise_adjustments.append({
                            "round": propagation_round,
                            "edge": [edge["a"], edge["b"]],
                            "changed_terminal": target,
                            "candidate_index": index,
                        })
                        changed = True
                        repaired = True
                        break
                    if repaired:
                        break
            if not changed:
                break
        candidate_prefilter["pairwise_adjustments"] = pairwise_adjustments

        for variant in range(int(variant_start),
                             int(variant_start) + int(max_variants)):
            attempt_started = time.monotonic()
            rollback()
            chosen = {
                ref: active_candidates[ref][
                    variant % len(active_candidates[ref])]
                for ref in branch_refs}
            reports = []
            failed = None

            # One physical launch per internal terminal.  These short stubs are
            # routed first so the scarce pad-access geometry is authoritative.
            for ref in branch_refs:
                port, junction = ports[ref], chosen[ref]
                endpoints = (port["p"], junction["p"],
                             port["n"], junction["n"])
                leg_before = {item.m_Uuid.AsString()
                              for item in board.GetTracks()}
                report = _route_paired_stub(
                    board, pair, endpoints, avoid=avoid, layer=layer)
                if report.get("refused"):
                    failed = {"stage": "terminal_stub", "ref": ref,
                              "reason": report["refused"]}
                    break
                item_uuids = sorted(
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in leg_before)
                reports.append(dict(
                    report, graph_role="terminal_stub", terminal=ref,
                    item_uuids=item_uuids))
            if failed is None:
                # Commit scarce leaf access before long internal trunk legs.
                # The prefilter proved these exact junction/leaf combinations;
                # routing them last lets unrelated trunk geometry consume their
                # breakout channel and defeats the purpose of the proof.
                ordered_edges = sorted(
                    plan["edges"],
                    key=lambda row: (
                        0 if min(degrees[row["a"]], degrees[row["b"]]) == 1
                        else 1,
                        float(row.get("length_mm", 0.0)),
                        row["a"], row["b"]))
                for edge_index, edge in enumerate(ordered_edges):
                    a, b = edge["a"], edge["b"]
                    a_port = chosen.get(a, ports[a])
                    b_port = chosen.get(b, ports[b])
                    endpoints = (a_port["p"], b_port["p"],
                                 a_port["n"], b_port["n"])
                    # A clear chamfered trunk leg is vastly cheaper than a
                    # full-board A* and just as exact.  Escalate to the global
                    # coupled search only when the bounded local forms are
                    # genuinely obstructed.
                    leg_before = {item.m_Uuid.AsString()
                                  for item in board.GetTracks()}
                    report = _route_paired_stub(
                        board, pair, endpoints, avoid=avoid, layer=layer)
                    if report.get("refused"):
                        report = route_coupled_pair(
                            board, pair, verbose=verbose, avoid=avoid,
                            endpoints=endpoints, pair_grid=True, layer=layer)
                    if report.get("refused"):
                        failed = {"stage": "trunk_edge", "edge": [a, b],
                                  "reason": report["refused"]}
                        break
                    item_uuids = sorted(
                        item.m_Uuid.AsString() for item in board.GetTracks()
                        if item.m_Uuid.AsString() not in leg_before)
                    reports.append(dict(
                        report, graph_role="trunk_edge", edge=[a, b],
                        item_uuids=item_uuids))
            if failed is None:
                created = {item.m_Uuid.AsString() for item in board.GetTracks()
                           if item.m_Uuid.AsString() not in base_ids}
                geometry = _pair_graph_geometry(board, pair, created)
                if not geometry["ok"]:
                    ownership = {
                        item_uuid: {
                            "graph_role": row.get("graph_role"),
                            "terminal": row.get("terminal"),
                            "edge": row.get("edge"),
                        }
                        for row in reports
                        for item_uuid in row.get("item_uuids", ())}
                    for issue in geometry["issues"]:
                        for key in ("p_uuid", "n_uuid", "first_uuid",
                                    "second_uuid"):
                            if issue.get(key) in ownership:
                                issue[key.replace("_uuid", "_owner")] = (
                                    ownership[issue[key]])
                    failed = {"stage": "whole_graph_geometry",
                              "reason": geometry["issues"][:8]}
            if failed is not None:
                refusal = {"layer": layer, "variant": variant,
                           "wall_seconds": round(
                               time.monotonic() - attempt_started, 3),
                           **failed}
                refusals.append(refusal)
                if verbose:
                    print("[precision] multidrop %s/%d refused at %s: %s"
                          % (layer, variant, failed["stage"],
                             failed.get("reason")), file=sys.stderr)
                continue

            for edge in plan["edges"]:
                edge["selected_layer"] = layer
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "route_mode": "paired-trunk-short-stub",
                "paired_terminals": plan["terminals"],
                "tree_edges": plan["edges"],
                "junctions": {
                    ref: {key: value for key, value in chosen[ref].items()
                          if key != "ref"}
                    for ref in branch_refs},
                "layer": layer, "variant": variant,
                "wall_seconds": round(time.monotonic() - attempt_started, 3),
                "legs": reports,
                "segments": sum(row.get("segments", 0) for row in reports),
                "length_mm": round(sum(row.get("length_mm", 0.0)
                                       for row in reports), 2),
                "coupled_len_mm": round(sum(
                    row.get("coupled_len_mm", 0.0) for row in reports), 2),
                "graph_geometry": geometry,
                "candidate_prefilter": candidate_prefilter,
            }
    rollback()
    return {
        "name": pair["name"], "p": pair["p"], "n": pair["n"],
        "paired_terminals": plan["terminals"],
        "tree_edges": plan["edges"],
        "refused": "paired trunk/stub variants exhausted",
        "attempts": refusals,
        "candidate_prefilter": candidate_prefilter,
    }


def _conflict_free_edge_layers(edge, edges, preferred_layers=()):
    """Return alternate colours that do not duplicate an endpoint launch."""
    selected = edge["selected_layer"]
    a, b = edge["a"], edge["b"]
    preferred = list(preferred_layers or ())
    return sorted(
        (layer for layer in edge.get("layers", ())
         if layer != selected
         and all(
             other is edge
             or ref not in (other["a"], other["b"])
             or other["selected_layer"] != layer
             for ref in (a, b) for other in edges)),
        key=lambda layer: (
            preferred.index(layer) if layer in preferred else 999,
            layer))


def _route_layered_multidrop_pair_tree(board, pair, plan, *, avoid=(),
                                       verbose=False,
                                       max_search_seconds=240.0,
                                       _component_sign_overrides=None,
                                       _absolute_deadline=None,
                                       _forced_edge_layers=None,
                                       _layer_backtrack_depth=0,
                                       _route_layer_evidence=None):
    """Route a multidrop pair with PTH pads as legal layer articulations.

    Edge-layer choice is derived from the two endpoint pad stacks and the fab
    profile's preferred signal layers.  A junction is inserted only when a
    terminal has two or more incident edges on the *same* layer.  Thus an SMD
    transceiver can reach a PTH connector on F.Cu while the connector row uses
    B.Cu, with the plated connector lands providing the real transition and no
    synthetic via or repeated same-layer pad launch.
    """
    search_started = time.monotonic()
    absolute_deadline = (_absolute_deadline
                         if _absolute_deadline is not None
                         else search_started + float(max_search_seconds))
    base_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    ports = plan["ports"]
    edges = [dict(row) for row in plan["edges"]]
    forced_edge_layers = dict(_forced_edge_layers or {})
    route_layer_evidence = (_route_layer_evidence
                            if _route_layer_evidence is not None else {})

    def public_route_layer_evidence():
        output = {}
        for key, layers in sorted(route_layer_evidence.items()):
            output["%s-%s" % key] = {}
            for layer, row in sorted(layers.items()):
                template = row.get("route_template") or {}
                output["%s-%s" % key][layer] = {
                    field: row[field] for field in (
                        "successes", "refusals", "timeouts", "reuses",
                        "best_wall_seconds", "last_wall_seconds",
                        "last_refusal") if field in row
                }
                output["%s-%s" % key][layer].update({
                    "template_available": bool(template.get("tracks")),
                    "template_segments": len(template.get("tracks") or ()),
                })
        return output
    layer_assignment = _assign_multidrop_edge_layers(
        plan, edges, forced_layers=forced_edge_layers,
        route_layer_evidence=route_layer_evidence)
    for edge, layer in zip(edges, layer_assignment["selected_layers"]):
        edge["selected_layer"] = layer
    embedding = _multidrop_planar_embedding(plan, edges)

    incident = {}
    for edge in edges:
        layer = edge["selected_layer"]
        for ref in (edge["a"], edge["b"]):
            incident.setdefault((ref, layer), []).append(edge)
    junction_keys = sorted(key for key, rows in incident.items()
                           if len(rows) >= 2)

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                board.Remove(item)

    def budget_exhausted():
        return _deadline_expired(absolute_deadline)

    def budget_refusal(stage, prefilter):
        rollback()
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "paired_terminals": plan["terminals"],
            "tree_edges": edges,
            "refused": "layered multidrop search budget exhausted at %s" %
                       stage,
            "search_budget_seconds": float(max_search_seconds),
            "wall_seconds": round(time.monotonic() - search_started, 3),
            "candidate_prefilter": prefilter,
            "route_layer_evidence": public_route_layer_evidence(),
        }

    def candidate_throats(ref, layer, junction):
        return _multidrop_junction_throats(
            plan, pair, ref, layer, junction,
            incident[(ref, layer)], embedding)

    def emit_local_star(ref, layer, junction, *, allow_detour):
        """Emit one exact package breakout and every narrow tree portal."""
        port = ports[ref]
        reports = []
        report = _route_paired_stub(
            board, pair,
            (port["p"], junction["p"],
             port["n"], junction["n"]),
            avoid=avoid, layer=layer, allow_detour=allow_detour,
            deadline=absolute_deadline)
        if report.get("refused"):
            return None, "terminal: " + report["refused"], report
        reports.append(report)
        throats = candidate_throats(ref, layer, junction)
        for other, throat in sorted(throats.items()):
            report = _route_paired_stub(
                board, pair,
                (junction["p"], throat["p"],
                 junction["n"], throat["n"]),
                avoid=avoid, layer=layer, allow_detour=allow_detour,
                deadline=absolute_deadline)
            if report.get("refused"):
                return None, "spoke %s: %s" % (other, report["refused"]), report
            reports.append(report)
        return throats, None, reports

    chosen = {}
    candidate_sets = {}
    component_signs = dict(_component_sign_overrides or {})
    forced_components = set(component_signs)
    prefilter = {"layer_assignment": layer_assignment}
    for ref, layer in junction_keys:
        rows = _multidrop_junction_candidates(board, plan, ref, pair)
        if (ref, layer) in embedding:
            component = (layer, embedding[(ref, layer)]["component"])
            rows = _expand_junction_trunk_signs(
                rows, embedding[(ref, layer)]["lane_axis"],
                trunk_sign=component_signs.get(component))
            rows = [
                _mitered_junction_candidate(
                    plan, pair, ref, layer, row,
                    incident[(ref, layer)], embedding)
                for row in rows]
        candidate_sets[(ref, layer)] = rows
        selected = None
        index = None
        checked = 0
        rejection_counts = {}
        rejection_samples = []

        def reject(reason, detail=None):
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            sampled_reasons = {row["reason"] for row in rejection_samples}
            if reason not in sampled_reasons and len(rejection_samples) < 8:
                rejection_samples.append({
                    "reason": reason,
                    "detail": detail,
                })

        # Branch-and-bound: exhaust the cheap straight candidates before any
        # candidate is allowed to invoke the combinatorial dogbone solver.
        # A later direct candidate often dominates an early detoured one, and
        # this ordering converts a minutes-long false plateau into a bounded
        # linear screen without reducing the solution space.
        for allow_detour in (False, True):
            for index, junction in enumerate(rows):
                if budget_exhausted():
                    return budget_refusal("junction_prefilter", prefilter)
                rollback()
                checked += 1
                _throats, failed, detail = emit_local_star(
                    ref, layer, junction, allow_detour=allow_detour)
                if failed:
                    reject(failed, (detail or {}).get("admission"))
                    continue
                created = {item.m_Uuid.AsString() for item in board.GetTracks()
                           if item.m_Uuid.AsString() not in base_ids}
                geometry = _pair_graph_geometry(board, pair, created)
                if geometry["ok"]:
                    selected = junction
                    break
                reject("local_star_geometry", geometry.get("issues"))
            if selected is not None:
                break
        rollback()
        key_name = "%s@%s" % (ref, layer)
        prefilter[key_name] = {
            "checked": checked,
            "selected_index": (index if selected is not None else None),
            "selected_sign": (selected.get("embedding_sign")
                              if selected is not None else None),
            "rejection_counts": rejection_counts,
            "rejection_samples": rejection_samples,
            "incident_edges": sorted(
                [row["a"], row["b"]] for row in incident[(ref, layer)]),
        }
        if selected is None:
            embedding_row = embedding.get((ref, layer))
            component = ((layer, embedding_row["component"])
                         if embedding_row is not None else None)
            # A lane order is a component-wide binary variable.  If the first
            # feasible junction chose one order greedily and a later junction
            # empties that domain, retry the whole atomic transaction exactly
            # once with the opposite order.  Never swap H/L at only one star.
            if (component is not None
                    and component in component_signs
                    and component not in forced_components):
                rollback()
                retry_overrides = dict(_component_sign_overrides or {})
                retry_overrides[component] = -int(component_signs[component])
                retry = _route_layered_multidrop_pair_tree(
                    board, pair, plan, avoid=avoid, verbose=verbose,
                    max_search_seconds=max_search_seconds,
                    _component_sign_overrides=retry_overrides,
                    _absolute_deadline=absolute_deadline,
                    _forced_edge_layers=forced_edge_layers,
                    _layer_backtrack_depth=_layer_backtrack_depth,
                    _route_layer_evidence=route_layer_evidence)
                retry.setdefault("orientation_backtracking", []).insert(0, {
                    "component": [component[0], component[1]],
                    "rejected_sign": int(component_signs[component]),
                    "retry_sign": int(retry_overrides[component]),
                    "trigger": "no layered paired junction for %s" % key_name,
                    "first_attempt_prefilter": prefilter,
                })
                return retry
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "paired_terminals": plan["terminals"],
                "tree_edges": edges,
                "refused": "no layered paired junction for %s" % key_name,
                "candidate_prefilter": prefilter,
                "route_layer_evidence": public_route_layer_evidence(),
            }
        chosen[(ref, layer)] = selected
        if (ref, layer) in embedding:
            component = (layer, embedding[(ref, layer)]["component"])
            component_signs[component] = int(
                selected.get("embedding_sign", 1))

    def layered_assignment_ok(edge, trial):
        rollback()
        layer = edge["selected_layer"]
        for (ref, key_layer), junction in sorted(trial.items()):
            _throats, failed, _detail = emit_local_star(
                ref, key_layer, junction, allow_detour=True)
            if failed:
                rollback()
                return False
        a_key, b_key = (edge["a"], layer), (edge["b"], layer)
        a_junction = trial.get(a_key, chosen.get(a_key))
        b_junction = trial.get(b_key, chosen.get(b_key))
        a_port = (candidate_throats(edge["a"], layer, a_junction).get(
            edge["b"]) if a_junction is not None else None) or ports[edge["a"]]
        b_port = (candidate_throats(edge["b"], layer, b_junction).get(
            edge["a"]) if b_junction is not None else None) or ports[edge["b"]]
        report = _route_paired_stub(
            board, pair,
            (a_port["p"], b_port["p"],
             a_port["n"], b_port["n"]),
            avoid=avoid, layer=layer, deadline=absolute_deadline)
        created = {item.m_Uuid.AsString() for item in board.GetTracks()
                   if item.m_Uuid.AsString() not in base_ids}
        ok = (not report.get("refused")
              and _pair_graph_geometry(board, pair, created)["ok"])
        rollback()
        return ok

    # Apply exact local-star arc consistency on every edge touching a
    # junction.  This also proves leaf access instead of treating a PTH pad as
    # automatically compatible with the selected star.
    adjustments = []
    for edge in sorted(edges, key=lambda row: (row["length_mm"],
                                               row["a"], row["b"])):
        layer = edge["selected_layer"]
        keys = [(edge["a"], layer), (edge["b"], layer)]
        owned_keys = [key for key in keys if key in chosen]
        if not owned_keys:
            continue
        current = {key: chosen[key] for key in owned_keys}
        if layered_assignment_ok(edge, current):
            continue
        # Move the endpoint without a leaf first; its junction is less
        # constrained.  Candidate verification includes every local leaf and
        # the whole pair graph, so an adjustment cannot sacrifice access.
        targets = sorted(
            owned_keys,
            key=lambda key: (
                sum(1 for row in incident[key]
                    if len(incident.get((
                        row["b"] if row["a"] == key[0] else row["a"],
                        key[1]), ())) == 1),
                key))
        repaired = False
        for target in targets:
            other = keys[1] if target == keys[0] else keys[0]
            for candidate_index, candidate in enumerate(
                    candidate_sets[target][:12]):
                if budget_exhausted():
                    return budget_refusal("pairwise_prefilter", prefilter)
                if candidate is chosen[target]:
                    continue
                trial = {target: candidate}
                if other in chosen:
                    trial[other] = chosen[other]
                if not layered_assignment_ok(edge, trial):
                    continue
                chosen[target] = candidate
                adjustments.append({
                    "edge": [edge["a"], edge["b"]],
                    "changed": "%s@%s" % target,
                    "candidate_index": candidate_index,
                })
                repaired = True
                break
            if repaired:
                break
    prefilter["pairwise_adjustments"] = adjustments

    throats = {}
    for (ref, layer), junction in sorted(chosen.items()):
        for other, throat in candidate_throats(ref, layer, junction).items():
            throats[(ref, layer, other)] = throat

    rollback()
    started = time.monotonic()
    reports = []
    for (ref, layer), junction in sorted(chosen.items()):
        if budget_exhausted():
            return budget_refusal("terminal_stubs", prefilter)
        port = ports[ref]
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        report = _route_paired_stub(
            board, pair,
            (port["p"], junction["p"],
             port["n"], junction["n"]),
            avoid=avoid, layer=layer, deadline=absolute_deadline)
        if report.get("refused"):
            rollback()
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "layered terminal stub %s@%s refused: %s" %
                           (ref, layer, report["refused"]),
                "candidate_prefilter": prefilter,
                "tree_edges": edges,
            }
        reports.append(dict(
            report, graph_role="terminal_stub", terminal=ref, layer=layer,
            item_uuids=sorted(
                item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in before)))

    # Emit the jointly oriented local star before any long edge search.  Long
    # spans subsequently connect throat-to-throat and can no longer choose a
    # new lane ordering at the shared junction.
    for (ref, layer, other), throat in sorted(throats.items()):
        if budget_exhausted():
            return budget_refusal("junction_spokes", prefilter)
        junction = chosen[(ref, layer)]
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        report = _route_paired_stub(
            board, pair,
            (junction["p"], throat["p"],
             junction["n"], throat["n"]),
            avoid=avoid, layer=layer, deadline=absolute_deadline)
        if report.get("refused"):
            rollback()
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "paired_terminals": plan["terminals"],
                "tree_edges": edges,
                "refused": "planar junction spoke %s@%s->%s refused: %s" %
                           (ref, layer, other, report["refused"]),
                "failed_junction": "%s@%s" % (ref, layer),
                "candidate_prefilter": prefilter,
            }
        reports.append(dict(
            report, graph_role="junction_spoke", terminal=ref,
            neighbor=other, layer=layer,
            item_uuids=sorted(
                item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in before)))

    def learned_edge_cost(edge):
        key = tuple(sorted((edge["a"], edge["b"])))
        rows = route_layer_evidence.get(key, {})
        return (
            sum(int(row.get("refusals", 0))
                + int(row.get("timeouts", 0)) for row in rows.values()),
            sum(int(row.get("successes", 0)) for row in rows.values()),
        )

    # Route the hardest constrained spans first.  The old leaf/shortest-first
    # order paid for several easy edges before discovering that a long edge's
    # selected colour had no corridor, then discarded all that work during
    # recoloring.  A professional critical-net pass fails fast on scarce layer
    # domains and high-cost spans; learned failures from a prior bounded branch
    # receive the highest priority on the retry.
    ordered_edges = sorted(
        edges,
        key=lambda edge: (
            -learned_edge_cost(edge)[0],
            len(edge.get("layers") or ("F.Cu",)),
            -float(edge["length_mm"]),
            learned_edge_cost(edge)[1], edge["a"], edge["b"]))
    runtime_layer_adjustments = []
    route_template_reuses = []
    for edge in ordered_edges:
        if budget_exhausted():
            return budget_refusal("trunk_edges", prefilter)
        a, b = edge["a"], edge["b"]
        edge_key = tuple(sorted((a, b)))
        selected_layer = edge["selected_layer"]
        layer_attempts = [selected_layer]
        # A PTH-to-PTH edge may change layer without vias.  If its selected
        # colour is physically blocked, try only colours unused by every other
        # edge incident at either endpoint.  This preserves the layer-colorer
        # invariant (no repeated same-layer pad launch) and never invents a
        # local star after junction planning has finished.
        if (edge.get("through_hole_edge")
                and (a, selected_layer) not in chosen
                and (b, selected_layer) not in chosen
                and edge_key not in forced_edge_layers):
            layer_attempts.extend(_conflict_free_edge_layers(
                edge, edges, plan.get("preferred_signal_layers") or ()))

        layer_refusals = []
        report = None
        before = None
        accepted_layer = None
        edge_minimum_coupled_fraction = (
            0.0 if edge.get("bounded_terminal_fanout") else 0.35)
        for layer in layer_attempts:
            if budget_exhausted():
                break
            attempt_deadline = min(
                absolute_deadline,
                time.monotonic() + (
                    90.0 if edge_key in forced_edge_layers else
                    60.0 if len(edge.get("layers") or ()) == 1 else
                    30.0))
            a_port = throats.get((a, layer, b),
                                 chosen.get((a, layer), ports[a]))
            b_port = throats.get((b, layer, a),
                                 chosen.get((b, layer), ports[b]))
            endpoints = (a_port["p"], b_port["p"],
                         a_port["n"], b_port["n"])
            before = {item.m_Uuid.AsString() for item in board.GetTracks()}
            layer_started = time.monotonic()
            learned = route_layer_evidence.setdefault(
                edge_key, {}).setdefault(layer, {
                    "successes": 0, "refusals": 0, "timeouts": 0,
                    "best_wall_seconds": None,
                })
            signature = _paired_endpoint_signature(endpoints)
            cached = learned.get("route_template") or {}
            report = None
            if cached.get("endpoint_signature") == signature:
                replayed = _replay_track_template(
                    board, cached.get("tracks") or ())
                created_now = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in base_ids}
                if (replayed
                        and _pair_graph_geometry(
                            board, pair, created_now)["ok"]):
                    report = dict(cached.get("report") or {})
                    report["reused_route_template"] = True
                    report["segments"] = len(replayed)
                    learned["reuses"] = int(learned.get("reuses", 0)) + 1
                    route_template_reuses.append({
                        "edge": [a, b], "layer": layer,
                        "segments": len(replayed),
                    })
                else:
                    for item in list(board.GetTracks()):
                        if item.m_Uuid.AsString() in replayed:
                            board.Remove(item)
                    report = None
            if report is None:
                report = _route_paired_stub(
                    board, pair, endpoints, avoid=avoid, layer=layer,
                    minimum_coupled_fraction=edge_minimum_coupled_fraction,
                    deadline=attempt_deadline)
                if report.get("refused"):
                    report = route_coupled_pair(
                        board, pair, verbose=verbose, avoid=avoid,
                        endpoints=endpoints, pair_grid=True, layer=layer,
                        minimum_coupled_fraction=(
                            edge_minimum_coupled_fraction),
                        deadline=attempt_deadline)
            elapsed = round(time.monotonic() - layer_started, 3)
            if not report.get("refused"):
                learned["successes"] += 1
                best_wall = learned.get("best_wall_seconds")
                learned["best_wall_seconds"] = (
                    elapsed if best_wall is None else min(best_wall, elapsed))
                if not report.get("reused_route_template"):
                    template_ids = {
                        item.m_Uuid.AsString() for item in board.GetTracks()
                        if item.m_Uuid.AsString() not in before}
                    template_rows = _capture_track_template(
                        board, template_ids)
                    if template_rows:
                        learned["route_template"] = {
                            "endpoint_signature": signature,
                            "tracks": template_rows,
                            "report": {
                                field: report[field] for field in (
                                    "name", "p", "n", "route_mode", "layer",
                                    "width", "gap_nominal", "zdiff_nominal",
                                    "ztarget", "segments", "length_mm",
                                    "coupled_len_mm", "coupled_coverage_pct")
                                if field in report
                            },
                        }
                accepted_layer = layer
                break
            if "deadline" in str(report.get("refused", "")).lower():
                learned["timeouts"] += 1
            else:
                learned["refusals"] += 1
            learned["last_refusal"] = report.get("refused")
            learned["last_wall_seconds"] = elapsed
            layer_refusals.append({
                "layer": layer, "reason": report.get("refused"),
                "detail": report,
            })
        if accepted_layer is None:
            rollback()
            refusal = {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "paired_terminals": plan["terminals"],
                "tree_edges": edges,
                "refused": "layered trunk edge %s-%s layer ensemble refused" %
                           (a, b),
                "failed_edge": [a, b],
                "failed_layer": selected_layer,
                "failed_edge_detail": report,
                "layer_refusals": layer_refusals,
                "candidate_prefilter": prefilter,
                "route_layer_evidence": public_route_layer_evidence(),
            }
            # Local conflict-free alternatives can be empty even though a
            # different global coloring is feasible.  Force the failed PTH
            # edge to each untried color in preferred order and rerun the
            # bounded colorer, which moves adjacent edges legally.  Share the
            # original absolute deadline and cap recursion depth so routing
            # feedback cannot become an unbounded wave loop.
            if (edge.get("through_hole_edge")
                    and edge_key not in forced_edge_layers
                    and int(_layer_backtrack_depth) < 3):
                preferred = list(plan.get("preferred_signal_layers") or ())
                untried = sorted(
                    (layer for layer in edge.get("layers", ())
                     if layer not in layer_attempts),
                    key=lambda layer: (
                        preferred.index(layer)
                        if layer in preferred else 999, layer))
                timed_out = [
                    row["layer"] for row in layer_refusals
                    if "deadline exhausted" in str(row.get("reason", ""))]
                retry_layers = untried + [
                    layer for layer in timed_out if layer not in untried]
                backtracks = []
                for forced_layer in retry_layers:
                    if budget_exhausted():
                        break
                    retry_forced = dict(forced_edge_layers)
                    retry_forced[edge_key] = forced_layer
                    retry = _route_layered_multidrop_pair_tree(
                        board, pair, plan, avoid=avoid, verbose=verbose,
                        max_search_seconds=max_search_seconds,
                        _component_sign_overrides=_component_sign_overrides,
                        _absolute_deadline=absolute_deadline,
                        _forced_edge_layers=retry_forced,
                        _layer_backtrack_depth=(
                            int(_layer_backtrack_depth) + 1),
                        _route_layer_evidence=route_layer_evidence)
                    backtracks.append({
                        "edge": [a, b], "forced_layer": forced_layer,
                        "result": ("accepted" if not retry.get("refused")
                                   else retry.get("refused")),
                    })
                    if not retry.get("refused"):
                        retry.setdefault(
                            "route_layer_backtracking", []).insert(0, {
                                "edge": [a, b],
                                "failed_local_layers": layer_refusals,
                                "forced_layer": forced_layer,
                                "depth": int(_layer_backtrack_depth) + 1,
                            })
                        return retry
                refusal["route_layer_backtracking"] = backtracks
            return refusal
        layer = accepted_layer
        if layer != selected_layer:
            edge["selected_layer"] = layer
            runtime_layer_adjustments.append({
                "edge": [a, b], "from": selected_layer, "to": layer,
                "refusals": layer_refusals,
            })
        reports.append(dict(
            report, graph_role="trunk_edge", edge=[a, b], layer=layer,
            coupling_policy=(
                "bounded-terminal-fanout"
                if edge.get("bounded_terminal_fanout") else
                "paired-trunk"),
            minimum_coupled_fraction=edge_minimum_coupled_fraction,
            item_uuids=sorted(
                item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in before)))

    created = {item.m_Uuid.AsString() for item in board.GetTracks()
               if item.m_Uuid.AsString() not in base_ids}
    normalization = _drop_fully_covered_tracks(board, created)
    created = {item.m_Uuid.AsString() for item in board.GetTracks()
               if item.m_Uuid.AsString() not in base_ids}
    geometry = _pair_graph_geometry(board, pair, created)
    if not geometry["ok"]:
        rollback()
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "paired_terminals": plan["terminals"],
            "tree_edges": edges,
            "refused": "layered whole-graph pair geometry failed",
            "graph_geometry": geometry,
            "candidate_prefilter": prefilter,
            "normalization": normalization,
            "route_layer_evidence": public_route_layer_evidence(),
        }
    coupling = _pair_coupling_summary(board, pair, created)
    if (coupling["total_samples"]
            and coupling["coverage_pct"] + 1e-9 < coupling["minimum_pct"]):
        rollback()
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "paired_terminals": plan["terminals"],
            "tree_edges": edges,
            "refused": "layered whole-graph coupled coverage failed",
            "graph_geometry": geometry,
            "coupling": coupling,
            "candidate_prefilter": prefilter,
            "normalization": normalization,
            "route_layer_evidence": public_route_layer_evidence(),
        }
    import cec_route_quality
    route_quality = (cec_route_quality.analyze_board(
        board, critical_nets=(pair["p"], pair["n"]),
        track_uuid_scope=created) if created else {
            "ok": True, "issue_count": 0, "blocking_count": 0,
            "advisory_count": 0, "critical_nets": sorted(
                (pair["p"], pair["n"])), "issues": [],
        })
    if not route_quality["ok"]:
        rollback()
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "paired_terminals": plan["terminals"],
            "tree_edges": edges,
            "refused": "layered whole-graph route quality failed",
            "graph_geometry": geometry, "coupling": coupling,
            "route_quality": route_quality,
            "candidate_prefilter": prefilter,
            "normalization": normalization,
            "route_layer_evidence": public_route_layer_evidence(),
        }
    return {
        "name": pair["name"], "p": pair["p"], "n": pair["n"],
        "route_mode": "layered-paired-trunk-short-stub",
        "paired_terminals": plan["terminals"],
        "tree_edges": edges,
        "junctions": {
            "%s@%s" % key: {
                field: value for field, value in row.items()
                if field not in ("ref", "_junction_throats")}
            for key, row in chosen.items()},
        "junction_throats": {
            "%s@%s->%s" % key: value for key, value in throats.items()},
        "planar_embedding": {
            "%s@%s" % key: value for key, value in embedding.items()},
        "legs": reports,
        "segments": sum(row.get("segments", 0) for row in reports),
        "length_mm": round(sum(row.get("length_mm", 0.0)
                               for row in reports), 2),
        "coupled_len_mm": round(sum(row.get("coupled_len_mm", 0.0)
                                   for row in reports), 2),
        "graph_geometry": geometry,
        "coupling": coupling,
        "route_quality": route_quality,
        "normalization": normalization,
        "candidate_prefilter": prefilter,
        "layer_assignment": layer_assignment,
        "route_layer_evidence": public_route_layer_evidence(),
        "runtime_layer_adjustments": runtime_layer_adjustments,
        "route_template_reuses": route_template_reuses,
        "wall_seconds": round(time.monotonic() - started, 3),
    }


def flow_through_launch_evidence(board_path, *, board=None, length_mm=3.0,
                                 clearance_mm=0.20):
    """Measure foreign-pad incursions into inline-pair launch channels.

    Placement keepouts are constructive hints; this is the independent
    board-artifact admission.  The channel tapers from the station's physical
    pad-bank span to the routed pair envelope, so a central GND pad is allowed
    inside its own package while unrelated pads in front of either port are
    named before detailed routing starts.
    """
    board = board or pcbnew.LoadBoard(board_path)
    if board is None:
        return {"schema": 1, "ok": False,
                "error": "board unloadable", "violations": []}
    violations = []
    channels = []
    for pair in derive_coupled_pairs(board_path, board=board):
        flow = _flow_through_pair_legs(board, pair)
        if flow is None:
            continue
        legs, stations = flow
        own_nets = {pair["p"], pair["n"]}
        station_points = {
            ref: {tuple(row[2]) for row in
                  _pads_on_net(board, pair["p"])
                  + _pads_on_net(board, pair["n"])
                  if row[0] == ref}
            for ref in stations}
        for leg_index, (pa, pb, na, nb) in enumerate(legs):
            ports = ((pa, na), (pb, nb))
            station_ref = next((
                ref for ref, points in station_points.items()
                if any(p in points and n in points for p, n in ports)), None)
            if station_ref is None:
                continue
            if pa in station_points[station_ref] and na in station_points[station_ref]:
                station_port, far_port = (pa, na), (pb, nb)
            else:
                station_port, far_port = (pb, nb), (pa, na)
            far_refs = {
                row[0] for row in
                _pads_on_net(board, pair["p"])
                + _pads_on_net(board, pair["n"])
                if tuple(row[2]) in {tuple(far_port[0]), tuple(far_port[1])}
            }
            start = ((station_port[0][0] + station_port[1][0]) / 2.0,
                     (station_port[0][1] + station_port[1][1]) / 2.0)
            end = ((far_port[0][0] + far_port[1][0]) / 2.0,
                   (far_port[0][1] + far_port[1][1]) / 2.0)
            dx, dy = end[0] - start[0], end[1] - start[1]
            span = math.hypot(dx, dy)
            if span <= 0.5:
                continue
            ux, uy = dx / span, dy / span
            vx, vy = -uy, ux
            reach = min(float(length_mm), max(0.1, span - 0.4))
            member_span = _dist(*station_port)
            station_half = (member_span / 2.0 + pair["width"] / 2.0
                            + float(clearance_mm))
            route_half = ((2.0 * pair["width"] + pair["gap"]) / 2.0
                          + float(clearance_mm))
            channel = {
                "pair": pair["name"], "station_ref": station_ref,
                "leg": leg_index + 1,
                "start_mm": [round(start[0], 4), round(start[1], 4)],
                "end_mm": [round(start[0] + ux * reach, 4),
                           round(start[1] + uy * reach, 4)],
                "axis": [round(ux, 6), round(uy, 6)],
                "perpendicular": [round(vx, 6), round(vy, 6)],
                "length_mm": round(reach, 4), "blockers": [],
            }
            for footprint in board.GetFootprints():
                ref = footprint.GetReference()
                if ref == station_ref or ref in far_refs:
                    continue
                for pad in footprint.Pads():
                    if pad.GetNetname() in own_nets:
                        continue
                    box = pad.GetBoundingBox()
                    corners = [
                        (box.GetLeft() / MM, box.GetTop() / MM),
                        (box.GetRight() / MM, box.GetTop() / MM),
                        (box.GetRight() / MM, box.GetBottom() / MM),
                        (box.GetLeft() / MM, box.GetBottom() / MM),
                    ]
                    axial = [((x - start[0]) * ux + (y - start[1]) * uy)
                             for x, y in corners]
                    lo, hi = min(axial), max(axial)
                    pad_pos = pad.GetPosition()
                    pad_xy = (pad_pos.x / MM, pad_pos.y / MM)
                    axial_center = ((pad_xy[0] - start[0]) * ux
                                    + (pad_xy[1] - start[1]) * uy)
                    # Require a clear *launch*, not a permanently empty
                    # six-millimetre strip.  A pad whose copper edge grazes the
                    # end plane can be routed around by the coupled A* search;
                    # a pad centre inside the launch cannot.
                    if axial_center < 0.15 or axial_center > reach:
                        continue
                    lateral = [((x - start[0]) * vx + (y - start[1]) * vy)
                               for x, y in corners]
                    lat_lo, lat_hi = min(lateral), max(lateral)
                    sample = axial_center
                    taper = min(1.0, sample / 2.0)
                    half = station_half + (route_half - station_half) * taper
                    if lat_hi < -half or lat_lo > half:
                        continue
                    side = -1.0 if abs(lat_lo) < abs(lat_hi) else 1.0
                    needed = max(0.4, half - min(abs(lat_lo), abs(lat_hi))
                                 + 0.25)
                    item = {
                        "pair": pair["name"], "station_ref": station_ref,
                        "leg": leg_index + 1, "blocker_ref": ref,
                        "blocker_pad": pad.GetPadName(),
                        "blocker_net": pad.GetNetname(),
                        "pad_uuid": pad.m_Uuid.AsString(),
                        "axis": [round(ux, 6), round(uy, 6)],
                        "perpendicular": [round(vx, 6), round(vy, 6)],
                        "suggested_side": side,
                        "minimum_shift_mm": round(needed, 3),
                    }
                    violations.append(item)
                    channel["blockers"].append(item)
            channels.append(channel)
    # A multi-pad footprint gets one relocation proposal but retains each pad
    # UUID in evidence for the blocker stack and dashboard highlighting.
    return {"schema": 1, "ok": not violations,
            "violations": violations, "channels": channels}


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _escape_candidate_quality(points):
    """Return a deterministic quality key for a short pad escape, or ``None``.

    A one-bend escape is local fanout, not a length-tuning structure.  The old
    first-clear-angle search could step *away* from its lane and then reverse,
    producing a connected hairpin that looks exactly like a dangling stub in a
    board review.  Require monotonically increasing progress from pad to lane
    and reject any greater-than-90-degree reversal.  The caller may then choose
    the shortest clear candidate instead of depending on angle enumeration.
    """
    if len(points) < 2:
        return None
    source, target = points[0], points[-1]
    axis = (target[0] - source[0], target[1] - source[1])
    span2 = axis[0] * axis[0] + axis[1] * axis[1]
    if span2 <= 1e-12:
        return None
    progress = [((point[0] - source[0]) * axis[0]
                 + (point[1] - source[1]) * axis[1]) / span2
                for point in points]
    if any(b + 1e-9 < a for a, b in zip(progress, progress[1:])):
        return None
    if progress[0] < -1e-9 or progress[-1] > 1.0 + 1e-9:
        return None
    vectors = [(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points, points[1:])]
    if any(a[0] * b[0] + a[1] * b[1] < -1e-9
           for a, b in zip(vectors, vectors[1:])):
        return None
    length = sum(math.hypot(dx, dy) for dx, dy in vectors)
    detour = length / math.sqrt(span2)
    bends = sum(1 for a, b in zip(vectors, vectors[1:])
                if abs(a[0] * b[1] - a[1] * b[0]) > 1e-9)
    return round(detour, 9), round(length, 9), bends, tuple(points)


def _polyline_has_reverse_bend(points):
    """True when adjacent legs form a greater-than-90-degree turn.

    Octilinear obstacle paths may legitimately turn left, right, or route around
    a keepout, but a single vertex must never double back.  Such a vertex is a
    hairpin discontinuity and is easily misread as a dangling branch in review.
    """
    vectors = [(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points, points[1:])
               if _dist(a, b) > 1e-9]
    return any(a[0] * b[0] + a[1] * b[1] < -1e-9
               for a, b in zip(vectors, vectors[1:]))


def _drop_fully_covered_tracks(board, track_uuids):
    """Drop generated straight tracks wholly covered by equivalent copper.

    Independently admitted route stages can meet at a portal with one short
    collinear leg laid on top of a longer leg.  The physical copper is
    connected, but retaining both primitives creates a covered 180-degree
    pseudo-stub in the route graph.  Normalize only the unambiguous case: same
    net and layer, an equal-or-wider covering trace, and both endpoints of the
    shorter centreline on the longer centreline.  The covering trace may come
    from an earlier priority stage; only UUIDs in ``track_uuids`` are ever
    removed.  Partial overlaps, branches, arcs, vias, and any cross-net/layer
    geometry remain untouched for the normal admission gates to judge.
    """
    scope = set(track_uuids or ())
    all_tracks = [
        item for item in board.GetTracks()
        if (item.GetClass() == "PCB_TRACK"
            and item.GetStart() != item.GetEnd())
    ]
    candidates = [item for item in all_tracks
                  if item.m_Uuid.AsString() in scope]
    candidates.sort(key=lambda item: (
        -int(item.GetLength()), item.GetNetCode(), int(item.GetLayer()),
        int(item.GetWidth()), item.GetStart().x, item.GetStart().y,
        item.GetEnd().x, item.GetEnd().y, item.m_Uuid.AsString()))

    def covered(candidate, survivor):
        if (candidate.GetNetCode() != survivor.GetNetCode()
                or candidate.GetLayer() != survivor.GetLayer()
                or survivor.GetWidth() < candidate.GetWidth()):
            return False
        c, d = survivor.GetStart(), survivor.GetEnd()
        vx, vy = d.x - c.x, d.y - c.y
        span2 = vx * vx + vy * vy
        if span2 <= 0:
            return False
        for point in (candidate.GetStart(), candidate.GetEnd()):
            if vx * (point.y - c.y) - vy * (point.x - c.x) != 0:
                return False
            projection = ((point.x - c.x) * vx + (point.y - c.y) * vy)
            if projection < 0 or projection > span2:
                return False
        return True

    survivors = [item for item in all_tracks
                 if item.m_Uuid.AsString() not in scope]
    remaining_scope = []
    removed = []
    for candidate in candidates:
        if any(covered(candidate, survivor) for survivor in survivors):
            removed.append(candidate.m_Uuid.AsString())
            board.Remove(candidate)
        else:
            survivors.append(candidate)
            remaining_scope.append(candidate)
    return {
        "removed_count": len(removed),
        "removed_track_uuids": sorted(removed),
        "remaining_track_uuids": sorted(
            item.m_Uuid.AsString() for item in remaining_scope),
    }


def _paired_endpoint_signature(endpoints):
    """Return an exact, serialization-safe identity for four pair endpoints."""
    return [[int(round(point[0] * MM)), int(round(point[1] * MM))]
            for point in endpoints]


def _capture_track_template(board, track_uuids):
    """Capture deterministic straight-track geometry without KiCad UUIDs."""
    scope = set(track_uuids or ())
    rows = []
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_TRACK"
                or item.m_Uuid.AsString() not in scope):
            continue
        start, end = item.GetStart(), item.GetEnd()
        rows.append({
            "net": item.GetNetname(), "layer_id": int(item.GetLayer()),
            "width_nm": int(item.GetWidth()),
            "start_nm": [int(start.x), int(start.y)],
            "end_nm": [int(end.x), int(end.y)],
            "locked": bool(item.IsLocked()),
        })
    return sorted(rows, key=lambda row: (
        row["net"], row["layer_id"], row["width_nm"],
        row["start_nm"], row["end_nm"]))


def _replay_track_template(board, rows):
    """Replay an in-call exact route template and return its fresh UUIDs."""
    created = []
    for row in rows:
        net_code = board.GetNetcodeFromNetname(row["net"])
        if net_code <= 0:
            for item in created:
                board.Remove(item)
            return set()
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(*row["start_nm"]))
        track.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
        track.SetWidth(int(row["width_nm"]))
        track.SetLayer(int(row["layer_id"]))
        track.SetNetCode(net_code)
        track.SetLocked(bool(row.get("locked", False)))
        board.Add(track)
        created.append(track)
    return {item.m_Uuid.AsString() for item in created}


def _seg_cross(a, b, c, d):
    """True iff segment a-b properly crosses c-d (shared endpoints don't count)."""
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    if a in (c, d) or b in (c, d):
        return False
    return (ccw(a, c, d) * ccw(b, c, d) < 0) and (ccw(a, b, c) * ccw(a, b, d) < 0)


def _seg_seg_dist(a, b, c, d):
    """Min distance between segments ab and cd (mm coords)."""
    if _seg_cross(a, b, c, d):
        return 0.0
    def pt_seg(p, s, e):
        vx, vy = e[0] - s[0], e[1] - s[1]
        L2 = vx * vx + vy * vy
        if L2 <= 1e-12:
            return math.hypot(p[0] - s[0], p[1] - s[1])
        t = max(0.0, min(1.0, ((p[0] - s[0]) * vx + (p[1] - s[1]) * vy) / L2))
        return math.hypot(p[0] - (s[0] + t * vx), p[1] - (s[1] + t * vy))
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def _pair_min_clear(p_pts, n_pts, mid_p, mid_n, width, gap,
                    *, strict_pair_gap=False):
    """True iff no P segment runs illegally close to any N segment. The foreign guard
    exempts BOTH pair nets (own={pc,nc}) and _polys_no_cross only catches strict
    CROSSINGS, so partner-track OVERLAP was unguarded -- measured live on the Hub
    chain 2026-07-19: 3-19 locked-vs-locked /CAN_H x /CAN_L collisions on EVERY
    route ("the locked lay overlaps ITSELF"). Floors: the coupled MIDDLE pair
    (indices mid_p/mid_n) is constructed at exactly width+gap -> allow only a
    numerical epsilon; every other segment combination must keep >= width + gap/2
    centerline (an escape dipping inside half the pair gap is always wrong
    geometry; legitimate outside-approaches keep >= gap)."""
    floor_mid = width + gap - 1e-6
    # Search may temporarily use the historical half-gap escape allowance so
    # swapped package pin orders retain legal go-around candidates.  Copper
    # admission passes ``strict_pair_gap`` and must meet the requested gap.
    floor_other = (width + gap - 1e-6 if strict_pair_gap
                   else width + 0.5 * gap)
    for i, (a, b) in enumerate(zip(p_pts, p_pts[1:])):
        for j, (c, d) in enumerate(zip(n_pts, n_pts[1:])):
            need = floor_mid if (i == mid_p and j == mid_n) else floor_other
            actual = _seg_seg_dist(a, b, c, d)
            if actual < need:
                if os.environ.get("CEC_PAIR_DEBUG") == "1":
                    print("[precision] pair clearance fail",
                          "Pseg", i, "Nseg", j,
                          "actual", round(actual, 4), "need", round(need, 4),
                          file=sys.stderr)
                return False
    return True


def _polyline_coupling_coverage(p_points, n_points, width, gap,
                                *, sample_mm=0.5):
    """Return bidirectional sampled coupling for two member polylines.

    This mirrors the final physical-pair oracle's definition so intermediate
    routing cannot call two distant but non-crossing traces a coupled pair.
    Endpoint fan-in is allowed, but at least the requested fraction must have
    an opposite member on the same layer-equivalent path within the calibrated
    maximum edge gap.
    """
    p_segments = [(a, b) for a, b in zip(p_points, p_points[1:]) if a != b]
    n_segments = [(a, b) for a, b in zip(n_points, n_points[1:]) if a != b]

    def point_segment(point, segment):
        return _seg_seg_dist(point, point, segment[0], segment[1])

    coupled = 0
    total = 0
    maximum_edge_gap = 2.5 * float(gap) + 0.15
    for segments, opposite in ((p_segments, n_segments),
                               (n_segments, p_segments)):
        for start, end in segments:
            length = _dist(start, end)
            count = max(1, int(math.ceil(length / float(sample_mm))))
            for index in range(count):
                u = (index + 0.5) / count
                point = (start[0] + (end[0] - start[0]) * u,
                         start[1] + (end[1] - start[1]) * u)
                total += 1
                if not opposite:
                    continue
                center_distance = min(
                    point_segment(point, segment) for segment in opposite)
                edge_gap = center_distance - float(width)
                if -0.03 <= edge_gap <= maximum_edge_gap:
                    coupled += 1
    fraction = coupled / max(1, total)
    return {
        "coupled_samples": coupled,
        "total_samples": total,
        "fraction": fraction,
        "coverage_pct": round(100.0 * fraction, 1),
        "maximum_edge_gap_mm": round(maximum_edge_gap, 4),
    }


def _pair_coupling_summary(board, pair, created_ids=None, *, sample_mm=0.5):
    """Measure same-layer coupled coverage for a generated pair graph."""
    scope = set(created_ids or ())
    by_layer = {}
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_TRACK"
                or item.GetNetname() not in (pair["p"], pair["n"])
                or (scope and item.m_Uuid.AsString() not in scope)):
            continue
        start, end = item.GetStart(), item.GetEnd()
        by_layer.setdefault(int(item.GetLayer()), {}).setdefault(
            item.GetNetname(), []).append((
                (start.x / MM, start.y / MM),
                (end.x / MM, end.y / MM)))
    coupled = total = 0
    layers = {}
    for layer_id, nets in sorted(by_layer.items()):
        p_segments = nets.get(pair["p"], [])
        n_segments = nets.get(pair["n"], [])
        # Reconstruct as disconnected two-point polylines; sampling is segment
        # based, so sentinel duplication does not affect the result.
        p_points = [point for segment in p_segments for point in segment]
        n_points = [point for segment in n_segments for point in segment]
        # Avoid artificial links between flattened segments.
        def sample_segments(segments, opposite):
            local_coupled = local_total = 0
            maximum_edge_gap = 2.5 * float(pair["gap"]) + 0.15
            for start, end in segments:
                count = max(1, int(math.ceil(
                    _dist(start, end) / float(sample_mm))))
                for index in range(count):
                    u = (index + 0.5) / count
                    point = (start[0] + (end[0] - start[0]) * u,
                             start[1] + (end[1] - start[1]) * u)
                    local_total += 1
                    if opposite:
                        distance = min(_seg_seg_dist(
                            point, point, row[0], row[1]) for row in opposite)
                        if (-0.03 <= distance - float(pair["width"])
                                <= maximum_edge_gap):
                            local_coupled += 1
            return local_coupled, local_total
        pc, pt = sample_segments(p_segments, n_segments)
        nc, nt = sample_segments(n_segments, p_segments)
        coupled += pc + nc
        total += pt + nt
        layers[board.GetLayerName(layer_id)] = {
            "coupled_samples": pc + nc,
            "total_samples": pt + nt,
        }
    fraction = coupled / max(1, total)
    return {
        "coupled_samples": coupled,
        "total_samples": total,
        "fraction": fraction,
        "coverage_pct": round(100.0 * fraction, 1),
        "minimum_pct": 60.0 if pair.get("kind") == "can" else 80.0,
        "layers": layers,
    }


def _pair_coupling_contract(pair, coupling, member_lengths):
    """Apply the final-board coupled-length contract to one routed pair.

    A millimetre-scale package escape may legitimately spend a bounded absolute
    length outside the nominal pair gap.  Longer separated members must meet
    the normal coverage floor.  Keep these values identical to the independent
    final-board checker so precision success cannot become a signoff failure
    without any intervening geometry change.
    """
    kind = str(pair.get("kind") or "diff").lower()
    minimum_fraction = 0.60 if kind == "can" else 0.80
    uncoupled_budget_mm = 2.0 if kind == "can" else 0.75
    fraction = float((coupling or {}).get("fraction") or 0.0)
    maximum_length = max(
        (float(value) for value in (member_lengths or {}).values()),
        default=0.0)
    uncoupled_mm = maximum_length * (1.0 - fraction)
    sampled = int((coupling or {}).get("total_samples") or 0) > 0
    ok = bool(sampled and (
        fraction + 1e-9 >= minimum_fraction
        or uncoupled_mm <= uncoupled_budget_mm + 1e-9))
    return {
        "schema": 1,
        "ok": ok,
        "kind": kind,
        "coupled_coverage_pct": round(100.0 * fraction, 1),
        "minimum_coupled_coverage_pct": round(
            100.0 * minimum_fraction, 1),
        "member_lengths_mm": {
            str(net): round(float(length), 6)
            for net, length in sorted((member_lengths or {}).items())},
        "uncoupled_length_mm": round(uncoupled_mm, 6),
        "uncoupled_length_budget_mm": uncoupled_budget_mm,
        "sampled": sampled,
    }


def _polys_no_cross(p_pts, n_pts):
    """True iff the two members never CROSS each other. The foreign guard (cec_fr._tap_foreign_clear)
    deliberately excludes the pair's own two nets (they are MEANT to run adjacent), so P-vs-N
    crossing is checked separately here."""
    for a, b in zip(p_pts, p_pts[1:]):
        for c, d in zip(n_pts, n_pts[1:]):
            if _seg_cross(a, b, c, d):
                return False
    return True


def _portal_pair_taper_escape(
        p_portal, n_portal, p_middle, n_middle, *, width, gap,
        segment_clear, max_middle_vertices=3):
    """Join a widened matched-via portal to a nominal coupled ribbon.

    Signal-via lands generally require a wider P/N pitch than the controlled-
    impedance traces they feed. A constant-offset centreline therefore cannot
    land directly on both via centres. Search a tiny, deterministic prefix of
    the already proven ribbon and admit the first symmetric taper whose two
    members remain individually clear, non-crossing, and at or above the
    requested pair gap. Callers may reverse the middle polylines to construct
    the destination-side taper with the identical contract.
    """
    p_middle = list(p_middle or ())
    n_middle = list(n_middle or ())
    limit = min(len(p_middle), len(n_middle),
                max(1, int(max_middle_vertices or 1)) + 1)
    for index in range(1, limit):
        p_path = [tuple(p_portal), tuple(p_middle[index])]
        n_path = [tuple(n_portal), tuple(n_middle[index])]
        if not (segment_clear(*p_path) and segment_clear(*n_path)):
            continue
        if not _polys_no_cross(p_path, n_path):
            continue
        if not _pair_min_clear(
                p_path, n_path, -1, -1, width, gap,
                strict_pair_gap=True):
            continue
        return {"p": p_path, "n": n_path, "middle_index": index}
    return None


def _partner_pads_clear(board, a, b, width_nm, layer_id, partner_code, clr_nm,
                        *, partner_shapes=None):
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
    if partner_shapes is not None:
        return cec_fr._snapshot_foreign_clear(
            _v(*a), _v(*b), width_nm, clr_nm, (), partner_shapes)
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


def _partner_tracks_clear(board, a, b, width_nm, layer_id, partner_code):
    """Reject physical overlap with already-established partner copper.

    A differential pair's opposite member is intentionally closer than the
    ordinary netclass clearance, so treating it as generic foreign copper
    over-refuses every valid coupled run.  Conversely, excluding both pair
    nets entirely permits a later flow-through leg or tree edge to cross an
    earlier member.  Use zero-clearance effective-shape collision here: legal
    adjacent copper remains admissible, while crossings, shorts, and via-land
    overlaps are refused before materialization.  Same-member copper is not
    inspected so a new leg may intentionally rejoin its existing topology.
    """
    if a == b:
        return True
    segment = pcbnew.SHAPE_SEGMENT(_v(*a), _v(*b), width_nm)
    for item in getattr(board, "GetTracks", lambda: ())():
        if item.GetNetCode() != int(partner_code):
            continue
        try:
            if item.Type() == pcbnew.PCB_VIA_T:
                if layer_id not in item.GetLayerSet().CuStack():
                    continue
            elif item.GetLayer() != layer_id:
                continue
            if item.GetEffectiveShape(layer_id).Collide(segment, 0):
                return False
        except Exception:                           # noqa: BLE001
            # Retain the existing exact-geometry guard convention: a malformed
            # engine-specific shape skips that object, while final DRC remains
            # the independent fail-closed authority.
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


def _avoid_for_layer(avoid, layer):
    """Project tagged routed-object reservations onto one copper layer.

    Historical callers pass five-tuples and those remain stack-wide obstacles.
    Production reservations carry a sixth layer field so an F.Cu rail cannot
    accidentally wall off a legal In2.Cu/B.Cu pair ribbon.  Returning the
    established five-tuple shape keeps the geometry hot path allocation-light.
    """
    selected = []
    for row in avoid or ():
        if len(row) == 5:
            selected.append(tuple(row))
            continue
        if len(row) != 6:
            raise ValueError("avoid rectangle must have 5 or 6 fields")
        if str(row[5]) == str(layer):
            selected.append(tuple(row[:5]))
    return tuple(selected)


def _crosses_avoid(pts, avoid, width):
    """Does this polyline (at *width*) enter any reserved rect? Returns the rect ref."""
    if not avoid:
        return None

    def segment_hits_rect(px, py, qx, qy, rect):
        """Exact closed segment/AABB test (Liang-Barsky clipping).

        Bounding-box overlap alone is not intersection: an octilinear trace
        can pass outside a reservation corner while its axis-aligned bbox
        overlaps that corner.  The old shortcut over-blocked those legal
        diagonals, forcing staircase detours and sometimes declaring the
        complete coupled corridor impossible.
        """
        x0, y0, x1, y1 = rect
        dx, dy = qx - px, qy - py
        lo, hi = 0.0, 1.0
        for p, q in ((-dx, px - x0), (dx, x1 - px),
                     (-dy, py - y0), (dy, y1 - py)):
            if abs(p) <= 1e-15:
                if q < 0.0:
                    return False
                continue
            ratio = q / p
            if p < 0.0:
                lo = max(lo, ratio)
            else:
                hi = min(hi, ratio)
            if lo > hi:
                return False
        return True

    hw = width / 2.0
    for (x0, y0, x1, y1, ref) in avoid:
        ax0, ay0, ax1, ay1 = x0 - hw, y0 - hw, x1 + hw, y1 + hw
        for (px, py), (qx, qy) in zip(pts, pts[1:]):
            # Cheap rejection first; exact clipping decides the corner case.
            if max(px, qx) < ax0 or min(px, qx) > ax1 or max(py, qy) < ay0 or min(py, qy) > ay1:
                continue
            if segment_hits_rect(px, py, qx, qy,
                                 (ax0, ay0, ax1, ay1)):
                return ref
    return None


def _crosses_avoid_details(pts, avoid, width, *, limit=24):
    """Return bounded, JSON-safe exact reservation intersections.

    ``_crosses_avoid`` intentionally returns only the first reservation owner
    for the routing hot path.  Failure analysis needs the geometry that made a
    candidate illegal, however: without the struck segment and rectangle the
    placer cannot distinguish a component-access problem from a power-route
    barrier.  This companion uses the identical Liang-Barsky admission test
    and never changes routing acceptance.
    """
    if not avoid or len(pts) < 2:
        return []

    def segment_hits_rect(px, py, qx, qy, rect):
        x0, y0, x1, y1 = rect
        dx, dy = qx - px, qy - py
        lo, hi = 0.0, 1.0
        for p, q in ((-dx, px - x0), (dx, x1 - px),
                     (-dy, py - y0), (dy, y1 - py)):
            if abs(p) <= 1e-15:
                if q < 0.0:
                    return False
                continue
            ratio = q / p
            if p < 0.0:
                lo = max(lo, ratio)
            else:
                hi = min(hi, ratio)
            if lo > hi:
                return False
        return True

    hits = []
    seen = set()
    hw = float(width) / 2.0
    for row in avoid:
        if len(row) < 5:
            continue
        x0, y0, x1, y1, ref = row[:5]
        layer = str(row[5]) if len(row) >= 6 else None
        inflated = (float(x0) - hw, float(y0) - hw,
                    float(x1) + hw, float(y1) + hw)
        for index, ((px, py), (qx, qy)) in enumerate(
                zip(pts, pts[1:])):
            if (max(px, qx) < inflated[0]
                    or min(px, qx) > inflated[2]
                    or max(py, qy) < inflated[1]
                    or min(py, qy) > inflated[3]):
                continue
            if not segment_hits_rect(px, py, qx, qy, inflated):
                continue
            signature = (
                str(ref), layer, index,
                round(float(px), 6), round(float(py), 6),
                round(float(qx), 6), round(float(qy), 6),
                *(round(value, 6) for value in inflated),
            )
            if signature in seen:
                continue
            seen.add(signature)
            hits.append({
                "reservation": str(ref),
                "layer": layer,
                "segment_index": int(index),
                "segment_mm": [[round(float(px), 6),
                                round(float(py), 6)],
                               [round(float(qx), 6),
                                round(float(qy), 6)]],
                "rect_mm": [round(float(x0), 6), round(float(y0), 6),
                            round(float(x1), 6), round(float(y1), 6)],
                "inflated_rect_mm": [round(value, 6)
                                     for value in inflated],
                "route_width_mm": round(float(width), 6),
            })
            if len(hits) >= max(0, int(limit)):
                return hits
    return hits


def corridor_avoid_from_hints(hints):
    """Translate shared route keepouts into precision-router obstacles.

    Precision pairs are laid before the detailed router, so they must consume
    the same authoritative ``corr_*`` rectangles rather than relying on a later
    DSN keepout to protect already-locked copper.
    """
    avoid = []
    for hint in hints or ():
        if not str(hint.get("name") or "").startswith("corr_"):
            continue
        if not all(key in hint for key in ("x0", "y0", "x1", "y1")):
            continue
        avoid.append((float(hint["x0"]), float(hint["y0"]),
                      float(hint["x1"]), float(hint["y1"]),
                      str(hint.get("name") or "high-current-pour")))
    return tuple(avoid)


def pour_avoid_from_board(board_path):
    """Precision obstacles from the checker-authoritative pour regions.

    ``corr_*`` hints are useful detailed-router reservations but may be clipped
    at a shunt or connector field.  They cannot admit pre-routed locked copper.
    """
    return tuple(
        (float(row["x0"]), float(row["y0"]),
         float(row["x1"]), float(row["y1"]),
         "pour_%s_%s" % (str(row["net"]).strip("/"), row["layer"]))
        for row in cec_constraints.high_current_pour_regions(board_path)
    )


def _offset_centerline(points, offset):
    """Return the two constant-offset polylines around an octilinear centreline.

    Interior vertices use the intersection of the adjacent offset lines, which
    produces the same mitered 45/90-degree geometry as an interactive
    differential-pair router instead of leaving gaps at bends.
    """
    if len(points) < 2:
        return None

    segments = []
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        segments.append((start, end, dx / length, dy / length))
    if not segments:
        return None

    def one_side(sign):
        out = []
        for index in range(len(segments) + 1):
            if index == 0:
                start, _end, ux, uy = segments[0]
                out.append((start[0] - uy * offset * sign,
                            start[1] + ux * offset * sign))
                continue
            if index == len(segments):
                _start, end, ux, uy = segments[-1]
                out.append((end[0] - uy * offset * sign,
                            end[1] + ux * offset * sign))
                continue
            _a0, vertex, ux0, uy0 = segments[index - 1]
            _a1, _b1, ux1, uy1 = segments[index]
            p0 = (vertex[0] - uy0 * offset * sign,
                  vertex[1] + ux0 * offset * sign)
            p1 = (vertex[0] - uy1 * offset * sign,
                  vertex[1] + ux1 * offset * sign)
            det = ux0 * uy1 - uy0 * ux1
            if abs(det) <= 1e-9:
                out.append(((p0[0] + p1[0]) / 2.0,
                            (p0[1] + p1[1]) / 2.0))
                continue
            rx, ry = p1[0] - p0[0], p1[1] - p0[1]
            t = (rx * uy1 - ry * ux1) / det
            out.append((p0[0] + ux0 * t, p0[1] + uy0 * t))
        return out

    return one_side(1.0), one_side(-1.0)


def _chamfer_axis_path(points, chamfer=0.35):
    """Turn an axis-aligned escape into 0/45/90 geometry.

    Endpoint fanout is short and may need to go around the end of the sibling
    lane when the two packages present different pad-row orientations.  Hard
    Manhattan elbows are unnecessary; trim each legal 90-degree vertex by a
    bounded amount and join the trims with one 45-degree segment.
    """
    clean = []
    for point in points:
        if not clean or _dist(clean[-1], point) > 1e-9:
            clean.append(point)
    if len(clean) < 3:
        return clean
    out = [clean[0]]
    for index in range(1, len(clean) - 1):
        before, corner, after = clean[index - 1:index + 2]
        v0 = (corner[0] - before[0], corner[1] - before[1])
        v1 = (after[0] - corner[0], after[1] - corner[1])
        l0, l1 = math.hypot(*v0), math.hypot(*v1)
        cross = v0[0] * v1[1] - v0[1] * v1[0]
        dot = v0[0] * v1[0] + v0[1] * v1[1]
        if l0 <= 1e-9 or l1 <= 1e-9 or abs(cross) <= 1e-9 or dot < -1e-9:
            out.append(corner)
            continue
        trim = min(float(chamfer), 0.35 * l0, 0.35 * l1)
        if trim < 0.08:
            out.append(corner)
            continue
        out.append((corner[0] - v0[0] / l0 * trim,
                    corner[1] - v0[1] / l0 * trim))
        out.append((corner[0] + v1[0] / l1 * trim,
                    corner[1] + v1[1] / l1 * trim))
    out.append(clean[-1])
    return out


def _path_end_heading_alignment(path, preferred_direction):
    """Cosine alignment of a path's final leg with a desired exit heading."""
    if preferred_direction is None:
        return 1.0
    dx, dy = preferred_direction
    direction_length = math.hypot(dx, dy)
    if direction_length <= 1e-9:
        return 1.0
    for start, end in reversed(list(zip(path, path[1:]))):
        vx, vy = end[0] - start[0], end[1] - start[1]
        leg_length = math.hypot(vx, vy)
        if leg_length > 1e-9:
            return ((vx * dx + vy * dy)
                    / (leg_length * direction_length))
    return 1.0


def _polyline_min_opening_angle(path):
    """Return the smallest interior opening angle of a polyline in degrees.

    The route-quality authority treats openings below 89 degrees as an acute
    backtrack.  Applying the same geometry before copper emission prevents a
    locally legal ribbon from being selected only to fail the final protected-
    net audit after mutation.
    """
    minimum = 180.0
    for before, vertex, after in zip(path, path[1:], path[2:]):
        first = (before[0] - vertex[0], before[1] - vertex[1])
        second = (after[0] - vertex[0], after[1] - vertex[1])
        first_length, second_length = math.hypot(*first), math.hypot(*second)
        if first_length <= 1.0e-9 or second_length <= 1.0e-9:
            continue
        cosine = max(-1.0, min(1.0,
            (first[0] * second[0] + first[1] * second[1])
            / (first_length * second_length)))
        minimum = min(minimum, math.degrees(math.acos(cosine)))
    return minimum


def _bounded_pair_choice_score(p_len, n_len, p_span, n_span, *, skew,
                               max_skew, heading_shortfall):
    """Rank a locally legal pair against the final transaction bounds."""
    member_detour = max(
        float(p_len) / max(float(p_span), 1e-9),
        float(n_len) / max(float(n_span), 1e-9))
    return (round(max(0.0, float(skew) - float(max_skew)), 6),
            round(float(heading_shortfall), 6),
            round(member_detour, 6),
            round(float(p_len) + float(n_len), 6),
            round(float(skew), 6))


def _short_pair_ribbon_candidates(pair, p_start, p_end, n_start, n_end):
    """Create a nominal-gap ribbon with symmetric endpoint pitch tapers.

    Short package-to-package pairs often expose different P/N land pitches.
    Routing the members independently can connect both nets while producing no
    coupled interval. Collapse each station to one electrical centre, establish
    the nominal P/N pitch there, and connect those lanes with a constant-offset
    middle run. Exact clearance remains the caller's responsibility.
    """
    start_center = ((p_start[0] + n_start[0]) / 2.0,
                    (p_start[1] + n_start[1]) / 2.0)
    end_center = ((p_end[0] + n_end[0]) / 2.0,
                  (p_end[1] + n_end[1]) / 2.0)

    def launch_options(p_point, n_point):
        """Bounded station-normal launch rays, including no launch.

        Pair pins embedded in a package row can be flanked by unrelated pads.
        Angling immediately toward the peer then clips that neighboring land,
        even though a short, parallel escape normal to the row opens a legal
        corridor.  Both normal polarities remain proposals; the exact board
        guard selects the outward side and refuses the inward side.
        """
        member_x = n_point[0] - p_point[0]
        member_y = n_point[1] - p_point[1]
        member_length = math.hypot(member_x, member_y)
        rows = [(0.0, (0.0, 0.0))]
        if member_length <= 1.0e-9:
            return rows
        tangent = (-member_y / member_length,
                   member_x / member_length)
        for distance in (0.6, 1.0):
            rows.append((distance, tangent))
            rows.append((distance, (-tangent[0], -tangent[1])))
        return rows

    def clean_points(points):
        clean = []
        for point in points:
            point = (float(point[0]), float(point[1]))
            if not clean or _dist(clean[-1], point) > 1.0e-9:
                clean.append(point)
        return clean

    half_pitch = (float(pair["width"]) + float(pair["gap"])) / 2.0
    rows = []
    for start_distance, start_direction in launch_options(p_start, n_start):
        start_dx = start_distance * start_direction[0]
        start_dy = start_distance * start_direction[1]
        p_start_launch = (p_start[0] + start_dx,
                          p_start[1] + start_dy)
        n_start_launch = (n_start[0] + start_dx,
                          n_start[1] + start_dy)
        launched_start_center = (start_center[0] + start_dx,
                                 start_center[1] + start_dy)
        for end_distance, end_direction in launch_options(p_end, n_end):
            end_dx = end_distance * end_direction[0]
            end_dy = end_distance * end_direction[1]
            p_end_launch = (p_end[0] + end_dx, p_end[1] + end_dy)
            n_end_launch = (n_end[0] + end_dx, n_end[1] + end_dy)
            launched_end_center = (end_center[0] + end_dx,
                                   end_center[1] + end_dy)
            dx = launched_end_center[0] - launched_start_center[0]
            dy = launched_end_center[1] - launched_start_center[1]
            span = math.hypot(dx, dy)
            if span <= 1.0e-9:
                continue
            axis = (dx / span, dy / span)
            normal = (-axis[1], axis[0])
            # Establish the nominal lanes after a forward taper runway rather
            # than at the station centre.  A centre-coincident pitch change
            # can put one lane point behind its own pad when the physical pin
            # axis differs from the route normal, producing an acute
            # backtrack even though spacing and coupling are otherwise legal.
            # Symmetric bounded runways preserve equal member length.
            taper_distance = max(0.0, min(
                1.0, 0.25 * span, 0.5 * max(0.0, span - 0.25)))
            start_lane_center = (
                launched_start_center[0] + axis[0] * taper_distance,
                launched_start_center[1] + axis[1] * taper_distance)
            end_lane_center = (
                launched_end_center[0] - axis[0] * taper_distance,
                launched_end_center[1] - axis[1] * taper_distance)
            start_projection = (
                (p_start_launch[0] - launched_start_center[0]) * normal[0]
                + (p_start_launch[1] - launched_start_center[1]) * normal[1])
            end_projection = (
                (p_end_launch[0] - launched_end_center[0]) * normal[0]
                + (p_end_launch[1] - launched_end_center[1]) * normal[1])
            preferred_sign = (1.0 if start_projection + end_projection >= 0.0
                              else -1.0)
            for sign in (preferred_sign, -preferred_sign):
                p_start_lane = (
                    start_lane_center[0] + sign * normal[0] * half_pitch,
                    start_lane_center[1] + sign * normal[1] * half_pitch)
                n_start_lane = (
                    start_lane_center[0] - sign * normal[0] * half_pitch,
                    start_lane_center[1] - sign * normal[1] * half_pitch)
                p_end_lane = (
                    end_lane_center[0] + sign * normal[0] * half_pitch,
                    end_lane_center[1] + sign * normal[1] * half_pitch)
                n_end_lane = (
                    end_lane_center[0] - sign * normal[0] * half_pitch,
                    end_lane_center[1] - sign * normal[1] * half_pitch)
                p_points = clean_points([
                    p_start, p_start_launch, p_start_lane,
                    p_end_lane, p_end_launch, p_end])
                n_points = clean_points([
                    n_start, n_start_launch, n_start_lane,
                    n_end_lane, n_end_launch, n_end])
                p_length = sum(_dist(a, b)
                               for a, b in zip(p_points, p_points[1:]))
                n_length = sum(_dist(a, b)
                               for a, b in zip(n_points, n_points[1:]))
                coupling = _polyline_coupling_coverage(
                    p_points, n_points,
                    float(pair["width"]), float(pair["gap"]))
                contract = _pair_coupling_contract(
                    pair, coupling,
                    {pair["p"]: p_length, pair["n"]: n_length})
                rows.append({
                    "p": p_points, "n": n_points,
                    "axis": [round(axis[0], 6), round(axis[1], 6)],
                    "normal": [round(normal[0], 6), round(normal[1], 6)],
                    "polarity_sign": int(sign),
                    "preferred_polarity": sign == preferred_sign,
                    "start_launch_mm": round(start_distance, 6),
                    "start_launch_direction": [
                        round(start_direction[0], 6),
                        round(start_direction[1], 6)],
                    "end_launch_mm": round(end_distance, 6),
                    "end_launch_direction": [
                        round(end_direction[0], 6),
                        round(end_direction[1], 6)],
                    "taper_runway_mm": round(taper_distance, 6),
                    "p_length_mm": round(p_length, 6),
                    "n_length_mm": round(n_length, 6),
                    "coupling": coupling,
                    "coupling_contract": contract,
                })
    rows.sort(key=lambda row: (
        0 if row["coupling_contract"]["ok"] else 1,
        -float(row["coupling"]["fraction"]),
        0 if row["preferred_polarity"] else 1,
        float(row["p_length_mm"]) + float(row["n_length_mm"])))
    return rows


def _joint_endpoint_escape(p_start, n_start, p_end, n_end, *,
                           width, gap, segment_clear=None,
                           p_segment_clear=None, n_segment_clear=None,
                           max_detour=2.0, max_member_paths=32,
                           max_skew=None, preferred_end_direction=None,
                           diagnostics=None, deadline=None):
    """Jointly solve the two short endpoint escapes.

    Selecting the shortest P and N escape independently is incomplete: two
    individually legal paths can cross when connector and IC pad rows have
    different orientations.  Enumerate a bounded octilinear neighborhood for
    both members and admit the pair atomically.  This is deliberately a local
    fanout solver; the coupled-grid centreline still owns the long route.
    """
    def raw_candidates(start, end):
        sx, sy = start
        ex, ey = end
        rows = [[start, end],
                [start, (ex, sy), end],
                [start, (sx, ey), end]]
        # A two-leg L turns at the destination coordinate.  That is often
        # exactly where an adjacent pad blocks the approach, while a legal
        # escape exists if the turn happens earlier in the open channel
        # between the two packages.  Sample bounded interior spines before
        # considering perimeter detours.  This is package-agnostic and is the
        # local analogue of a visibility-graph bend candidate: it lets a
        # trace leave one pin row in its native channel, change rows in open
        # space, then enter the destination pad from its clear side.
        for fraction in (0.25, 0.5, 0.75):
            x_mid = sx + (ex - sx) * fraction
            y_mid = sy + (ey - sy) * fraction
            rows.extend((
                [start, (x_mid, sy), (x_mid, ey), end],
                [start, (sx, y_mid), (ex, y_mid), end],
            ))
        lo_x, hi_x = min(sx, ex), max(sx, ex)
        lo_y, hi_y = min(sy, ey), max(sy, ey)
        for distance in (0.5, 1.0, 1.5, 2.0, 3.0,
                         float(max_detour)):
            rows.extend((
                [start, (lo_x - distance, sy),
                 (lo_x - distance, ey), end],
                [start, (hi_x + distance, sy),
                 (hi_x + distance, ey), end],
                [start, (sx, lo_y - distance),
                 (ex, lo_y - distance), end],
                [start, (sx, hi_y + distance),
                 (ex, hi_y + distance), end],
            ))
            # Four-bend "go around the end" forms. These matter when the
            # lane order and package pad-row order differ: a simple L or
            # three-leg dogleg is topologically forced to cross its sibling.
            for y_detour in (lo_y - distance, hi_y + distance):
                for x_approach in (lo_x - distance, hi_x + distance):
                    rows.append([
                        start, (sx, y_detour),
                        (x_approach, y_detour),
                        (x_approach, ey), end])
            for x_detour in (lo_x - distance, hi_x + distance):
                for y_approach in (lo_y - distance, hi_y + distance):
                    rows.append([
                        start, (x_detour, sy),
                        (x_detour, y_approach),
                        (ex, y_approach), end])
        unique = {}
        for row in rows:
            path = _chamfer_axis_path(row)
            key = tuple((round(x, 6), round(y, 6)) for x, y in path)
            unique[key] = path
        return list(unique.values())

    p_clear = p_segment_clear or segment_clear
    n_clear = n_segment_clear or segment_clear
    if p_clear is None or n_clear is None:
        raise ValueError("joint endpoint escape requires member clearance guards")

    def admitted(path, clear):
        return (not _polyline_has_reverse_bend(path)
                and all(clear(a, b)
                        for a, b in zip(path, path[1:])))

    timed_out = False

    def member_paths(start, end, clear):
        nonlocal timed_out
        raw = raw_candidates(start, end)
        raw.sort(key=lambda path: (
            round(sum(_dist(a, b) for a, b in zip(path, path[1:])), 9),
            len(path), tuple(path)))
        accepted = []
        reverse_rejected = 0
        clearance_rejected = 0
        for path in raw:
            if _deadline_expired(deadline):
                timed_out = True
                break
            if _polyline_has_reverse_bend(path):
                reverse_rejected += 1
                continue
            if not all(clear(a, b) for a, b in zip(path, path[1:])):
                clearance_rejected += 1
                continue
            accepted.append(path)
            if len(accepted) >= int(max_member_paths):
                break
        return accepted, {
            "generated": len(raw),
            "admitted": len(accepted),
            "reverse_bend_rejected": reverse_rejected,
            "clearance_rejected": clearance_rejected,
        }

    p_paths, p_evidence = member_paths(p_start, p_end, p_clear)
    n_paths, n_evidence = member_paths(n_start, n_end, n_clear)
    p_span = max(_dist(p_start, p_end), 1e-9)
    n_span = max(_dist(n_start, n_end), 1e-9)
    choices = []
    crossing_rejected = 0
    pair_clearance_rejected = 0
    for p_path in p_paths:
        if _deadline_expired(deadline):
            timed_out = True
            break
        p_len = sum(_dist(a, b) for a, b in zip(p_path, p_path[1:]))
        for n_path in n_paths:
            if _deadline_expired(deadline):
                timed_out = True
                break
            if not _polys_no_cross(p_path, n_path):
                crossing_rejected += 1
                continue
            if not _pair_min_clear(
                    p_path, n_path, -1, -1, width, gap):
                pair_clearance_rejected += 1
                continue
            n_len = sum(_dist(a, b) for a, b in zip(n_path, n_path[1:]))
            skew = abs(p_len - n_len)
            heading_alignment = min(
                _path_end_heading_alignment(
                    p_path, preferred_end_direction),
                _path_end_heading_alignment(
                    n_path, preferred_end_direction))
            # Joining a local fan-in to a known trunk heading must not create
            # a 90/135-degree elbow at the handoff.  Treat 67.5 degrees as the
            # bounded maximum turn; a compatible path dominates a shorter
            # backwards-arriving one, while callers without a hard handoff
            # direction retain the historical score exactly.
            heading_shortfall = max(
                0.0, math.cos(math.radians(67.5)) - heading_alignment)
            if max_skew is None:
                score = (round(skew, 6), round(heading_shortfall, 6),
                         round(p_len + n_len, 6))
            else:
                # Constraints are bounds, not lexicographic style goals.
                # Once skew is within the electrical budget, prefer the
                # shorter escape; otherwise a needlessly long matched detour
                # destroys coupling and consumes routing area merely to turn
                # 1 mm of allowed skew into 0 mm.
                # The complete transaction independently caps each member's
                # copper/MST detour ratio.  Minimizing only the *sum* can pick
                # one very short member plus one needlessly long perimeter
                # dogbone and then fail that final gate by a few microns even
                # though a slightly longer, balanced pair is available.  Use
                # the exact two-terminal lower bound here, after the electrical
                # skew and handoff bounds, so local search and final admission
                # optimize the same physical quantity.
                score = _bounded_pair_choice_score(
                    p_len, n_len, p_span, n_span, skew=skew,
                    max_skew=max_skew,
                    heading_shortfall=heading_shortfall)
            choices.append(score + (
                len(p_path) + len(n_path),
                tuple(p_path), tuple(n_path)))
    if diagnostics is not None:
        diagnostics.update({
            "p_paths": p_evidence,
            "n_paths": n_evidence,
            "path_pairs_checked": len(p_paths) * len(n_paths),
            "crossing_rejected": crossing_rejected,
            "pair_clearance_rejected": pair_clearance_rejected,
            "admitted_pairs": len(choices),
            "deadline_exhausted": timed_out,
        })
    if not choices:
        return None
    selected = min(choices)
    p_path, n_path = selected[-2:]
    if diagnostics is not None:
        p_length = sum(_dist(a, b) for a, b in zip(p_path, p_path[1:]))
        n_length = sum(_dist(a, b) for a, b in zip(n_path, n_path[1:]))
        diagnostics["selected"] = {
            "p_length_mm": round(p_length, 6),
            "n_length_mm": round(n_length, 6),
            "p_span_mm": round(p_span, 6),
            "n_span_mm": round(n_span, 6),
            "maximum_member_detour_ratio": round(
                max(p_length / p_span, n_length / n_span), 6),
            "skew_mm": round(abs(p_length - n_length), 6),
        }
    return list(p_path), list(n_path)


def _pair_escape_budget(pad_a, pad_b, *, floor_mm=4.0,
                        cap_mm=12.0):
    """Scale a coupled breakout to the physical pair-pin separation.

    A compact IC pair needs only the historical 4mm neighborhood.  Widely
    separated connector contacts (for example a modular jack's pins 3 and 6)
    need room to converge without crossing; a fixed 4mm search falsely proves
    those legal launches impossible.  Keep the search local and bounded while
    scaling it to the package geometry rather than a connector name.
    """
    return min(float(cap_mm), max(float(floor_mm),
                                 1.5 * _dist(pad_a, pad_b)))


def _paired_portal_candidates(p_start, n_start, p_end, n_end, *,
                              width, gap, portal_separation=None):
    """Reduce dissimilar package pin fields to aligned pair portals.

    A wide connector pair and a compact IC pair are not useful endpoints for
    one global coupled-path search: the router must both converge the first
    pin field and discover the board-scale corridor at once.  Enumerate a
    bounded, package-agnostic set of octilinear portals instead.  Local exact
    fan-in proves each portal independently; a later shared-centreline search
    joins only compatible P/N lane orderings.
    """
    start_center = ((p_start[0] + n_start[0]) / 2.0,
                    (p_start[1] + n_start[1]) / 2.0)
    end_center = ((p_end[0] + n_end[0]) / 2.0,
                  (p_end[1] + n_end[1]) / 2.0)
    delta = (end_center[0] - start_center[0],
             end_center[1] - start_center[1])
    span = math.hypot(*delta)
    if span <= 1e-9:
        return {"span_mm": 0.0, "axis": (1.0, 0.0),
                "normal": (0.0, 1.0), "sign_order": (1, -1),
                "by_sign": {1: {"start": [], "end": []},
                            -1: {"start": [], "end": []}}}
    raw_directions = ((1, 0), (1, 1), (0, 1), (-1, 1),
                      (-1, 0), (-1, -1), (0, -1), (1, -1))
    directions = tuple((x / math.hypot(x, y), y / math.hypot(x, y))
                       for x, y in raw_directions)
    ux, uy = max(directions, key=lambda row: (
        row[0] * delta[0] + row[1] * delta[1]))
    nx, ny = -uy, ux
    separation = float(
        portal_separation if portal_separation is not None
        else float(width) + float(gap))
    if separation + 1e-9 < float(width) + float(gap):
        raise ValueError("pair portal separation is below routed pair geometry")
    offset = separation / 2.0

    start_preferred = (1 if ((p_start[0] - start_center[0]) * nx
                             + (p_start[1] - start_center[1]) * ny) >= 0
                       else -1)
    end_preferred = (1 if ((p_end[0] - end_center[0]) * nx
                           + (p_end[1] - end_center[1]) * ny) >= 0
                     else -1)
    sign_order = tuple(sorted((1, -1), key=lambda sign: (
        int(sign != start_preferred) + int(sign != end_preferred),
        -sign)))
    max_lead = max(1.3, span / 2.0 - 0.5)
    lateral_rows = (0.0, 0.6, -0.6, 1.0, -1.0,
                    1.5, -1.5, 2.0, -2.0)

    def side_rows(side, actual_p, actual_n, budget):
        # At 45 degrees the axial distance needed to converge two pins to the
        # routed pair separation is approximately half their excess spread.
        # Keep a small tolerance for diagonal/native pad geometry, but never
        # spend exact dogbone search on a portal that is physically too close
        # to seat the convergence.
        minimum_lead = max(
            1.3,
            0.5 * (_dist(actual_p, actual_n)
                   - (float(width) + float(gap))) - 0.15)
        leads = sorted({
            value for value in (1.3, 2.0, 3.0, 4.0, 5.0, 6.0,
                                round(float(budget), 6))
            if minimum_lead - 1e-9 <= value <= max_lead + 1e-9})
        rows = {1: [], -1: []}
        direction = 1.0 if side == "start" else -1.0
        anchor = start_center if side == "start" else end_center
        for lead in leads:
            for lateral in lateral_rows:
                center = (anchor[0] + direction * ux * lead + nx * lateral,
                          anchor[1] + direction * uy * lead + ny * lateral)
                for sign in (1, -1):
                    rows[sign].append({
                        "side": side, "sign": sign,
                        "lead_mm": round(lead, 6),
                        "lateral_mm": round(lateral, 6),
                        "center": center,
                        "p": (center[0] + nx * offset * sign,
                              center[1] + ny * offset * sign),
                        "n": (center[0] - nx * offset * sign,
                              center[1] - ny * offset * sign),
                        "actual_p": actual_p, "actual_n": actual_n,
                    })
        return rows

    start_rows = side_rows(
        "start", p_start, n_start, _pair_escape_budget(p_start, n_start))
    end_rows = side_rows(
        "end", p_end, n_end, _pair_escape_budget(p_end, n_end))
    return {
        "span_mm": round(span, 6), "axis": (ux, uy),
        "normal": (nx, ny), "sign_order": sign_order,
        "portal_separation_mm": round(separation, 6),
        "preferred_signs": {
            "start": start_preferred, "end": end_preferred},
        "by_sign": {
            sign: {"start": start_rows[sign], "end": end_rows[sign]}
            for sign in (1, -1)},
    }


def _grid_coupled_path(board, *, start_center, end_center, p_start, n_start,
                       p_end, n_end, layer_id, width, gap, clearance, own,
                       avoid=(), step=0.5, start_sign=1.0, end_sign=1.0,
                       launch_distance=1.25, start_lead=1.0, end_lead=3.0,
                       start_lateral=0.0, end_lateral=0.0,
                       initial_turn_steps=0, portal_mode=False,
                       deadline=None, diagnostics=None,
                       max_visited=120000,
                       foreign_shape_cache=None):
    """Find an obstacle-aware octilinear corridor and split it into a pair.

    The A* search guards a single envelope whose width is exactly two trace
    widths plus the requested copper gap.  Therefore every accepted centreline
    has room for both offset members, while direction state and bend penalties
    keep the result short and conventionally 0/45/90 degree.  Exact member
    geometry is rechecked before anything is committed.
    """
    corridor_width = 2.0 * width + gap
    width_nm = _nm(corridor_width)
    member_half_nm = _nm(width) // 2
    clearance_nm = _nm(clearance)
    bbox = board.GetBoardEdgesBoundingBox()
    x_min = bbox.GetX() / MM + corridor_width / 2.0 + clearance
    y_min = bbox.GetY() / MM + corridor_width / 2.0 + clearance
    x_max = (bbox.GetX() + bbox.GetWidth()) / MM - corridor_width / 2.0 - clearance
    y_max = (bbox.GetY() + bbox.GetHeight()) / MM - corridor_width / 2.0 - clearance

    def launch(center, p_value, n_value, toward, sign, distance, lateral):
        vx, vy = n_value[0] - p_value[0], n_value[1] - p_value[1]
        length = math.hypot(vx, vy)
        if length <= 1e-9:
            return center
        ax, ay = vx / length, vy / length
        tx, ty = -vy / length, vx / length
        wx, wy = toward[0] - center[0], toward[1] - center[1]
        if tx * wx + ty * wy < 0:
            tx, ty = -tx, -ty
        tx, ty = tx * sign, ty * sign
        return (center[0] + tx * distance + ax * lateral,
                center[1] + ty * distance + ay * lateral)

    if portal_mode:
        # The endpoint pin fields have already been reduced to two aligned
        # pair portals.  Search one shared centreline from portal to portal;
        # its constant offsets are the two members.  This avoids the old
        # failure mode where two independent A* searches found individually
        # legal paths that wandered apart or crossed.  The portal lane axis is
        # deliberately octilinear, so the first/last offsets land exactly on
        # the supplied P/N portals without another package escape search.
        route_start = start_center
        route_end = end_center
        start_vector = (end_center[0] - start_center[0],
                        end_center[1] - start_center[1])
        end_vector = start_vector
    else:
        route_start = launch(
            start_center, p_start, n_start, end_center, start_sign,
            float(launch_distance), float(start_lateral))
        route_end = launch(
            end_center, p_end, n_end, start_center, end_sign,
            float(launch_distance), float(end_lateral))
        start_vector = (route_start[0] - start_center[0],
                        route_start[1] - start_center[1])
        end_vector = (end_center[0] - route_end[0],
                      end_center[1] - route_end[1])

    def extend(value, vector, distance):
        length = math.hypot(*vector) or 1.0
        return (value[0] + vector[0] / length * distance,
                value[1] + vector[1] / length * distance)

    if portal_mode:
        grid_start, grid_end = route_start, route_end
    else:
        grid_start = extend(route_start, start_vector, float(start_lead))
        grid_end = extend(
            route_end, (-end_vector[0], -end_vector[1]), float(end_lead))
    origin = grid_start

    def key(value):
        return (int(round((value[0] - origin[0]) / step)),
                int(round((value[1] - origin[1]) / step)))

    def point(node):
        return (origin[0] + node[0] * step,
                origin[1] + node[1] * step)

    start = key(grid_start)
    goal = key(grid_end)
    directions = ((1, 0), (1, 1), (0, 1), (-1, 1),
                  (-1, 0), (-1, -1), (0, -1), (1, -1))

    def nearest_direction(vector):
        length = math.hypot(*vector) or 1.0
        ux, uy = vector[0] / length, vector[1] / length
        return max(range(len(directions)), key=lambda index: (
            ux * directions[index][0] + uy * directions[index][1])
            / math.hypot(*directions[index]))

    start_direction = nearest_direction(start_vector)
    goal_direction = nearest_direction(end_vector)
    edge_cache = {}
    shape_key = (int(layer_id), tuple(sorted(int(code) for code in own)))
    cached_shapes = ((foreign_shape_cache or {}).get(shape_key)
                     if foreign_shape_cache is not None else None)
    if cached_shapes is None:
        zone_rows, copper_rows = cec_fr._layer_foreign_shapes(
            board, layer_id, own)
        zone_rows = cec_fr._bucket_foreign_shapes(zone_rows)
        copper_rows = cec_fr._bucket_foreign_shapes(copper_rows)
        if foreign_shape_cache is not None:
            foreign_shape_cache[shape_key] = (zone_rows, copper_rows)
    else:
        zone_rows, copper_rows = cached_shapes
    identified_shapes = None
    diagnostic_counts = {}
    diagnostic_blockers = {}
    diagnostic_reservations = {}
    diagnostic_samples = []

    def record_rejection(reason, a, b, *, reservation_hits=()):
        if diagnostics is None:
            return
        reason = str(reason)
        diagnostic_counts[reason] = diagnostic_counts.get(reason, 0) + 1
        if len(diagnostic_samples) < 16:
            diagnostic_samples.append({
                "reason": reason,
                "segment_mm": [[round(float(a[0]), 6),
                                round(float(a[1]), 6)],
                               [round(float(b[0]), 6),
                                round(float(b[1]), 6)]],
            })
        for hit in reservation_hits or ():
            key = json.dumps(hit, sort_keys=True, separators=(",", ":"),
                             default=str)
            diagnostic_reservations[key] = (
                diagnostic_reservations.get(key, 0) + 1)

    def record_foreign_blockers(a, b):
        nonlocal identified_shapes
        if diagnostics is None or len(diagnostic_blockers) >= 16:
            return
        if identified_shapes is None:
            identified_shapes = cec_fr._identified_foreign_shape_indexes(
                board, layer_id, own)
        for hit in cec_fr._snapshot_foreign_blockers(
                _v(*a), _v(*b), width_nm, clearance_nm,
                identified_shapes[0], identified_shapes[1], limit=8):
            key = json.dumps(hit, sort_keys=True, separators=(",", ":"),
                             default=str)
            diagnostic_blockers[key] = diagnostic_blockers.get(key, 0) + 1

    def flush_diagnostics():
        if diagnostics is None:
            return
        diagnostics.update({
            "rejection_counts": dict(sorted(diagnostic_counts.items())),
            "dominant_blockers": [
                dict(json.loads(key), count=count)
                for key, count in sorted(
                    diagnostic_blockers.items(),
                    key=lambda item: (-item[1], item[0]))[:16]],
            "reservation_hits": [
                dict(json.loads(key), count=count)
                for key, count in sorted(
                    diagnostic_reservations.items(),
                    key=lambda item: (-item[1], item[0]))[:16]],
            "rejected_segment_samples": diagnostic_samples,
            "route_start_mm": [round(float(value), 6)
                               for value in route_start],
            "route_end_mm": [round(float(value), 6)
                             for value in route_end],
        })

    def exact_clear(a, b):
        return cec_fr._snapshot_foreign_clear(
            _v(*a), _v(*b), width_nm, clearance_nm,
            zone_rows, copper_rows)

    def edge_clear(a, b):
        cache_key = (a, b) if a <= b else (b, a)
        cached = edge_cache.get(cache_key)
        if cached is not None:
            return cached
        pa, pb = point(a), point(b)
        midpoint = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
        endpoint_escape = (not portal_mode
                           and min(_dist(midpoint, start_center),
                                   _dist(midpoint, end_center)) <= 2.6)
        # Board material is an obstacle too.  Foreign-copper collision tests do
        # not see Edge.Cuts, so without this guard a legal-looking A* edge can
        # cross a reverse-mount LED aperture (or a slot) and leave the pair with
        # no adjacent reference plane.  Guard the whole two-member envelope,
        # not merely either member centreline.
        material_clear = cec_fr._edge_leg_clear(
            board, _v(*pa), _v(*pb), width_nm // 2, edge_mm=0.5)
        in_bounds = (x_min <= pb[0] <= x_max
                     and y_min <= pb[1] <= y_max)
        reservation_ref = _crosses_avoid(
            [pa, pb], avoid, corridor_width)
        reservation_hits = (
            _crosses_avoid_details(
                [pa, pb], avoid, corridor_width, limit=8)
            if (diagnostics is not None and reservation_ref
                and len(diagnostic_reservations) < 16) else ())
        foreign_clear = endpoint_escape or exact_clear(pa, pb)
        ok = (in_bounds and material_clear and not reservation_ref
              and foreign_clear)
        if not ok:
            if not in_bounds:
                record_rejection("board_bounds", pa, pb)
            elif not material_clear:
                record_rejection("board_material", pa, pb)
            elif reservation_ref:
                record_rejection(
                    "reservation_barrier", pa, pb,
                    reservation_hits=reservation_hits)
            elif not foreign_clear:
                record_rejection("foreign_copper", pa, pb)
                record_foreign_blockers(pa, pb)
        edge_cache[cache_key] = ok
        return ok

    initial = (start[0], start[1], start_direction)
    queue = [(0.0, 0.0, initial)]
    cost = {initial: 0.0}
    parent = {}
    terminal = None
    visited = 0
    nearest_state = initial
    nearest_goal_distance = math.hypot(
        start[0] - goal[0], start[1] - goal[1]) * step
    max_visited = max(1, int(max_visited))
    while queue and visited < max_visited:
        if _deadline_expired(deadline):
            if diagnostics is not None:
                diagnostics.update({
                    "status": "deadline_exhausted", "visited": visited,
                    "edge_cache_entries": len(edge_cache),
                    "clear_edges": sum(edge_cache.values()),
                })
                flush_diagnostics()
            return None
        _priority, current_cost, state = heapq.heappop(queue)
        if current_cost != cost.get(state):
            continue
        visited += 1
        node = (state[0], state[1])
        goal_distance = math.hypot(
            node[0] - goal[0], node[1] - goal[1]) * step
        if goal_distance < nearest_goal_distance:
            nearest_goal_distance = goal_distance
            nearest_state = state
        if node == goal and state[2] == goal_direction:
            terminal = state
            break
        for direction_index, (dx, dy) in enumerate(directions):
            if state == initial:
                first_turn = min(abs(direction_index - start_direction),
                                 len(directions)
                                 - abs(direction_index - start_direction))
                if first_turn > int(initial_turn_steps):
                    continue
            if state[2] != -1:
                turn_steps = min(abs(direction_index - state[2]),
                                 len(directions) - abs(direction_index - state[2]))
                if turn_steps > 1:
                    continue
            nxt = (node[0] + dx, node[1] + dy)
            if not edge_clear(node, nxt):
                continue
            travel = step * (math.sqrt(2.0) if dx and dy else 1.0)
            bend = 0.0 if state[2] in (-1, direction_index) else 0.35
            new_cost = current_cost + travel + bend
            nxt_state = (nxt[0], nxt[1], direction_index)
            if new_cost >= cost.get(nxt_state, float("inf")):
                continue
            cost[nxt_state] = new_cost
            parent[nxt_state] = state
            heuristic = math.hypot(nxt[0] - goal[0], nxt[1] - goal[1]) * step
            heapq.heappush(queue, (new_cost + heuristic, new_cost, nxt_state))
    if terminal is None:
        if diagnostics is not None:
            diagnostics.update({
                "status": "grid_exhausted", "visited": visited,
                "max_visited": max_visited,
                "edge_cache_entries": len(edge_cache),
                "clear_edges": sum(edge_cache.values()),
                "nearest_frontier_mm": [
                    round(float(value), 6)
                    for value in point((nearest_state[0], nearest_state[1]))],
                "frontier_gap_mm": round(nearest_goal_distance, 6),
            })
            flush_diagnostics()
        if os.environ.get("CEC_PAIR_DEBUG") == "1":
            print("[precision] pair grid exhausted", visited,
                  "states; clear edges", sum(edge_cache.values()),
                  "of", len(edge_cache), file=sys.stderr)
        return None

    nodes = []
    state = terminal
    while True:
        nodes.append((state[0], state[1]))
        if state == initial:
            break
        state = parent[state]
    nodes.reverse()
    centres = [route_start, grid_start]
    centres.extend(point(node) for node in nodes)
    centres.extend((grid_end, route_end))

    # Remove duplicate and collinear vertices so the emitted copper is a small
    # set of intentional segments rather than grid-cell fragments.
    compact = []
    for value in centres:
        if compact and _dist(compact[-1], value) <= 1e-9:
            continue
        compact.append(value)
        while len(compact) >= 3:
            a, b, c = compact[-3:]
            cross = ((b[0] - a[0]) * (c[1] - b[1])
                     - (b[1] - a[1]) * (c[0] - b[0]))
            if abs(cross) > 1e-8:
                break
            compact.pop(-2)
    changed = True
    while changed and len(compact) >= 3:
        changed = False
        # Portal endpoints are hard direction constraints: the first and last
        # grid legs are what make the constant-offset ribbon land exactly on
        # the supplied P/N portal points.  Smoothing either adjacent vertex
        # silently rotates that offset and previously created a measurable
        # endpoint miss.  Package-mode endpoints have a separate exact escape
        # solver and retain the wider simplification range.
        first_index = 2 if portal_mode else 1
        stop_index = len(compact) - 2 if portal_mode else len(compact) - 1
        for index in range(first_index, stop_index):
            a, b, c = compact[index - 1:index + 2]
            ab, bc = _dist(a, b), _dist(b, c)
            if ab <= 1e-9 or bc <= 1e-9:
                compact.pop(index); changed = True; break
            dot = (((b[0] - a[0]) * (c[0] - b[0])
                    + (b[1] - a[1]) * (c[1] - b[1])) / (ab * bc))
            if min(ab, bc) < 0.75 and dot > math.cos(math.radians(22.5)):
                compact.pop(index); changed = True; break

    # A grid endpoint can land a fraction of a cell beyond the fixed launch
    # before returning toward the pad.  That tiny centreline backstep is not
    # benign: constant-offset miters magnify it into a several-millimetre
    # hairpin on one pair member.  Shortcut only reverse kinks for which the
    # complete pair envelope remains legal.  If a reverse kink is essential to
    # the obstacle path, refuse this launch and let the next tier solve it.
    def centre_leg_clear(a, b):
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        endpoint_escape = (not portal_mode
                           and min(_dist(midpoint, start_center),
                                   _dist(midpoint, end_center)) <= 2.6)
        return (cec_fr._edge_leg_clear(
                    board, _v(*a), _v(*b), width_nm // 2, edge_mm=0.5)
                and not _crosses_avoid([a, b], avoid, corridor_width)
                and (endpoint_escape or exact_clear(a, b)))

    changed = True
    while changed and len(compact) >= 3:
        changed = False
        first_index = 2 if portal_mode else 1
        stop_index = len(compact) - 2 if portal_mode else len(compact) - 1
        for index in range(first_index, stop_index):
            a, b, c = compact[index - 1:index + 2]
            ab = (b[0] - a[0], b[1] - a[1])
            bc = (c[0] - b[0], c[1] - b[1])
            if ab[0] * bc[0] + ab[1] * bc[1] >= -1e-9:
                continue
            if centre_leg_clear(a, c):
                compact.pop(index)
                changed = True
                break
            if diagnostics is not None:
                diagnostics.update({
                    "status": "essential_reverse_kink",
                    "visited": visited, "centre_vertices": len(compact),
                })
                flush_diagnostics()
            return None
    if _polyline_has_reverse_bend(compact):
        if diagnostics is not None:
            diagnostics.update({
                "status": "centreline_reverse_bend", "visited": visited,
                "centre_vertices": len(compact),
            })
            flush_diagnostics()
        return None
    offset = _offset_centerline(compact, (width + gap) / 2.0)
    if offset is None:
        if diagnostics is not None:
            diagnostics.update({
                "status": "offset_generation_failed", "visited": visited,
                "centre_vertices": len(compact),
            })
            flush_diagnostics()
        return None
    plus, minus = offset
    plus_is_p = (_dist(plus[0], p_start) + _dist(minus[0], n_start)
                 <= _dist(minus[0], p_start) + _dist(plus[0], n_start))
    def endpoint_segment_clear(a, b):
        if _dist(a, b) <= 1e-9:
            return True
        material_clear = cec_fr._edge_leg_clear(
            board, _v(*a), _v(*b), member_half_nm, edge_mm=0.5)
        reservation_ref = _crosses_avoid([a, b], avoid, width)
        reservation_hits = (
            _crosses_avoid_details([a, b], avoid, width, limit=8)
            if (diagnostics is not None and reservation_ref
                and len(diagnostic_reservations) < 16) else ())
        foreign_clear = cec_fr._snapshot_foreign_clear(
            _v(*a), _v(*b), _nm(width), clearance_nm,
            zone_rows, copper_rows)
        if not material_clear:
            record_rejection("endpoint_board_material", a, b)
        elif reservation_ref:
            record_rejection(
                "endpoint_reservation_barrier", a, b,
                reservation_hits=reservation_hits)
        elif not foreign_clear:
            record_rejection("endpoint_foreign_copper", a, b)
            record_foreign_blockers(a, b)
        return material_clear and not reservation_ref and foreign_clear

    def clean(points):
        out = []
        for value in points:
            if not out or _dist(out[-1], value) > 1e-6:
                out.append(value)
        return out

    # Nearest-at-start is usually the correct member ordering, but a centre
    # GND pad in a flow-through package can topologically require the opposite
    # lane assignment.  Admit either orientation using the same exact guards.
    orientations = ((plus, minus), (minus, plus))
    if not plus_is_p:
        orientations = tuple(reversed(orientations))
    for p_mid, n_mid in orientations:
        middle_start_index = 0
        middle_end_index = min(len(p_mid), len(n_mid)) - 1
        if portal_mode:
            # A portal is a hard boundary condition, not another pin field.
            # The first/last centreline direction was constrained to be
            # perpendicular to its P/N lane, so a correct offset must land on
            # all four portal points directly.  Refuse a numerical/geometric
            # mismatch instead of invoking the package dogbone solver, which
            # can only manufacture a micro-crossover here.
            alignment_error = max(
                _dist(p_start, p_mid[0]), _dist(n_start, n_mid[0]),
                _dist(p_end, p_mid[-1]), _dist(n_end, n_mid[-1]))
            if alignment_error <= 1e-5:
                start_escape = ([p_start], [n_start])
                end_escape = ([p_end], [n_end])
            else:
                start_taper = _portal_pair_taper_escape(
                    p_start, n_start, p_mid, n_mid,
                    width=width, gap=gap,
                    segment_clear=endpoint_segment_clear)
                end_taper_from_portal = _portal_pair_taper_escape(
                    p_end, n_end, list(reversed(p_mid)),
                    list(reversed(n_mid)), width=width, gap=gap,
                    segment_clear=endpoint_segment_clear)
                if (start_taper is None
                        or end_taper_from_portal is None):
                    if diagnostics is not None:
                        diagnostics.update({
                            "status": "portal_taper_refused",
                            "alignment_error_mm": round(
                                alignment_error, 6),
                            "start_taper_ok": start_taper is not None,
                            "end_taper_ok": (
                                end_taper_from_portal is not None),
                            "visited": visited,
                        })
                    continue
                middle_start_index = int(
                    start_taper["middle_index"])
                middle_end_index = (min(len(p_mid), len(n_mid)) - 1
                                    - int(end_taper_from_portal[
                                        "middle_index"]))
                if middle_start_index > middle_end_index:
                    if diagnostics is not None:
                        diagnostics.update({
                            "status": "portal_taper_overlap",
                            "alignment_error_mm": round(
                                alignment_error, 6),
                            "start_middle_index": middle_start_index,
                            "end_middle_index": middle_end_index,
                            "visited": visited,
                        })
                    continue
                start_escape = (
                    start_taper["p"], start_taper["n"])
                end_escape = (
                    list(reversed(end_taper_from_portal["p"])),
                    list(reversed(end_taper_from_portal["n"])))
        else:
            start_escape = _joint_endpoint_escape(
                p_start, n_start, p_mid[0], n_mid[0],
                width=width, gap=gap, segment_clear=endpoint_segment_clear,
                max_detour=_pair_escape_budget(p_start, n_start),
                deadline=deadline)
            end_escape = _joint_endpoint_escape(
                p_mid[-1], n_mid[-1], p_end, n_end,
                width=width, gap=gap, segment_clear=endpoint_segment_clear,
                max_detour=_pair_escape_budget(p_end, n_end),
                deadline=deadline)
        if start_escape is None or end_escape is None:
            if diagnostics is not None:
                diagnostics.update({
                    "status": "portal_escape_refused",
                    "visited": visited,
                    "start_escape_ok": start_escape is not None,
                    "end_escape_ok": end_escape is not None,
                    "centre_vertices": len(compact),
                })
            if os.environ.get("CEC_PAIR_DEBUG") == "1":
                print("[precision] pair grid joint endpoint escape refused",
                      "start=", start_escape is not None,
                      "end=", end_escape is not None, file=sys.stderr)
            continue
        p_start_path, n_start_path = start_escape
        p_end_path, n_end_path = end_escape
        p_core = p_mid[middle_start_index:middle_end_index + 1]
        n_core = n_mid[middle_start_index:middle_end_index + 1]
        p_points = clean(p_start_path[:-1] + p_core + p_end_path[1:])
        n_points = clean(n_start_path[:-1] + n_core + n_end_path[1:])
        material_clear = all(
            cec_fr._edge_leg_clear(
                board, _v(*a), _v(*b), member_half_nm, edge_mm=0.5)
            for points in (p_points, n_points)
            for a, b in zip(points, points[1:]))
        no_cross = _polys_no_cross(p_points, n_points)
        min_clear = _pair_min_clear(
            p_points, n_points, -1, -1, width, gap)
        no_hairpin = not (_polyline_has_reverse_bend(p_points)
                          or _polyline_has_reverse_bend(n_points))
        if material_clear and no_cross and min_clear and no_hairpin:
            if diagnostics is not None:
                diagnostics.update({
                    "status": "accepted", "visited": visited,
                    "centre_vertices": len(compact),
                    "member_vertices": [len(p_points), len(n_points)],
                    "portal_taper": bool(
                        portal_mode and alignment_error > 1e-5),
                })
                flush_diagnostics()
            return p_points, n_points, sum(
                _dist(a, b) for a, b in zip(compact, compact[1:]))
        if os.environ.get("CEC_PAIR_DEBUG") == "1":
            print("[precision] pair grid offset geometry refused",
                  "material_clear=", material_clear,
                  "no_cross=", no_cross, "min_clear=", min_clear,
                  "no_hairpin=", no_hairpin,
                      "P=", p_points, "N=", n_points, file=sys.stderr)
    if diagnostics is not None:
        diagnostics.setdefault("status", "offset_geometry_refused")
        diagnostics.update({
            "visited": visited, "centre_vertices": len(compact)})
        flush_diagnostics()
    return None


def _route_coupled_via_portals(board, pair, endpoints, *, layer="F.Cu",
                               clearance=0.20, avoid=(),
                               minimum_coupled_fraction=0.0,
                               deadline=None, verbose=False,
                               max_fanins_per_side=None,
                               max_portal_pairs=None,
                               max_grid_visited=120000,
                               middle_layer=None,
                               signal_via_diameter_mm=0.50,
                               signal_via_drill_mm=0.25,
                               return_via_diameter_mm=0.60,
                               return_via_drill_mm=0.30,
                               return_reach_mm=1.50,
                               portal_screen_cache=None):
    """Route a pair through independently proven package portals.

    This is the bounded fallback for dissimilar pin fields.  It never searches
    P and N globally as independent nets: exact local fan-ins are screened
    transactionally, then one obstacle-aware centreline is expanded into a
    constant-gap ribbon.  Whole-edge geometry, coupled coverage, and acute
    backtrack checks must all pass before the transaction is retained.
    """
    p_start, p_end, n_start, n_end = endpoints
    (signal_via_diameter_mm, signal_via_drill_mm,
     signal_via_limits) = cec_fab_profile.board_legal_through_via_geometry(
         board, signal_via_diameter_mm, signal_via_drill_mm)
    (return_via_diameter_mm, return_via_drill_mm,
     return_via_limits) = cec_fab_profile.board_legal_through_via_geometry(
         board, return_via_diameter_mm, return_via_drill_mm)
    base_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    layer_id = board.GetLayerID(layer)
    if layer_id < 0:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "portal layer %s absent" % layer}
    width, gap = float(pair["width"]), float(pair["gap"])
    middle_layer = middle_layer or layer
    middle_layer_id = board.GetLayerID(middle_layer)
    if middle_layer_id < 0:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "portal middle layer %s absent" % middle_layer}
    layer_transition = middle_layer != layer
    source_avoid = _avoid_for_layer(avoid, layer)
    middle_avoid = _avoid_for_layer(avoid, middle_layer)
    width_nm = _nm(width)
    p_code = board.GetNetcodeFromNetname(pair["p"])
    n_code = board.GetNetcodeFromNetname(pair["n"])
    own = {p_code, n_code}
    # Through-via lands cannot sit at the narrow trace-pair pitch.  Widen only
    # the two transition portals enough for real annular lands plus clearance;
    # the jointly routed inner ribbon converges back to nominal pair geometry.
    portal_separation = (max(width + gap,
                             float(signal_via_diameter_mm) + float(clearance))
                         if layer_transition else None)
    portal_plan = _paired_portal_candidates(
        p_start, n_start, p_end, n_end, width=width, gap=gap,
        portal_separation=portal_separation)
    start_spread = _dist(p_start, n_start)
    end_spread = _dist(p_end, n_end)
    pinfield_ratio = (max(start_spread, end_spread)
                      / max(min(start_spread, end_spread), 1e-9))
    minimum_handoff_alignment = (
        math.cos(math.radians(67.5)) if pinfield_ratio > 2.0 else 0.0)
    # A long board-scale span needs only a narrow beam; A* dominates and two
    # good fan-ins are sufficient.  A short package-to-package edge has little
    # middle corridor but a small finite fan-in combination space, so retain a
    # wider local beam to avoid declaring placement infeasible merely because
    # the two shortest candidates form a hairpin together.
    short_edge = portal_plan["span_mm"] < 10.0
    max_fanins_per_side = int(
        max_fanins_per_side
        if max_fanins_per_side is not None else (6 if short_edge else 2))
    max_portal_pairs = int(
        max_portal_pairs
        if max_portal_pairs is not None else (24 if short_edge else 4))
    evidence = {
        "span_mm": portal_plan["span_mm"],
        "axis": [round(value, 6) for value in portal_plan["axis"]],
        "normal": [round(value, 6) for value in portal_plan["normal"]],
        "preferred_signs": portal_plan["preferred_signs"],
        "sign_order": list(portal_plan["sign_order"]),
        "pinfield_spread_mm": [round(start_spread, 6),
                               round(end_spread, 6)],
        "pinfield_spread_ratio": round(pinfield_ratio, 6),
        "minimum_handoff_alignment": round(
            minimum_handoff_alignment, 6),
        "source_layer": layer, "middle_layer": middle_layer,
        "layer_transition": layer_transition,
        "signal_via": {
            "diameter_mm": float(signal_via_diameter_mm),
            "drill_mm": float(signal_via_drill_mm),
            "board_limits": signal_via_limits,
            "pair_spacing_mm": round(portal_plan.get(
                "portal_separation_mm", width + gap), 6),
        },
        "return_via": {
            "diameter_mm": float(return_via_diameter_mm),
            "drill_mm": float(return_via_drill_mm),
            "board_limits": return_via_limits,
        },
        "screened": {}, "attempts": [],
    }
    foreign_shape_cache = {}
    partner_shape_cache = {}
    blocker_shape_cache = {}
    portal_screen_cache = (portal_screen_cache
                           if portal_screen_cache is not None else {})
    screen_domain = (
        str(pair.get("p")), str(pair.get("n")), str(layer),
        tuple(round(float(value), 6) for point in endpoints for value in point),
        round(width, 6), round(gap, 6), round(float(clearance), 6),
        round(float(portal_plan.get(
            "portal_separation_mm", width + gap)), 6),
        int(max_fanins_per_side), round(minimum_handoff_alignment, 6),
        tuple(source_avoid),
    )

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                board.Remove(item)

    def public_row(row):
        public = {
            "sign": row["sign"], "lead_mm": row["lead_mm"],
            "lateral_mm": row["lateral_mm"],
            "center": [round(value, 6) for value in row["center"]],
            "p": [round(value, 6) for value in row["p"]],
            "n": [round(value, 6) for value in row["n"]],
        }
        if "grid_snap_mm" in row:
            public["grid_snap_mm"] = row["grid_snap_mm"]
        return public

    def emit_fanin(row, *, allow_detour, detour_member_paths=32):
        axis = portal_plan["axis"]
        preferred_heading = (
            axis if row["side"] == "start"
            else (-axis[0], -axis[1]))
        return _route_paired_stub(
            board, pair,
            (row["actual_p"], row["p"],
             row["actual_n"], row["n"]),
            layer=layer, clearance=clearance, avoid=avoid,
            allow_detour=allow_detour, deadline=deadline,
            detour_member_paths=detour_member_paths,
            preferred_end_direction=preferred_heading,
            minimum_end_heading_alignment=minimum_handoff_alignment,
            foreign_shape_cache=foreign_shape_cache,
            partner_shape_cache=partner_shape_cache,
            blocker_shape_cache=blocker_shape_cache)

    def add_signal_via(point, net_code):
        at = _v(*point)
        if not cec_fr._via_spot_clear(
                board, at, _nm(signal_via_diameter_mm), _nm(clearance),
                {int(net_code)}, drill_nm=_nm(signal_via_drill_mm),
                net_code=int(net_code)):
            return None
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(at)
        via.SetWidth(_nm(signal_via_diameter_mm))
        via.SetDrill(_nm(signal_via_drill_mm))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(int(net_code))
        board.Add(via)
        return via

    def existing_gnd_vias():
        return [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"
                and item.GetNetname() == "GND"]

    def add_return_via(center, pair_vector, route_axis=None,
                       signal_points=()):
        gnd = board.FindNet("GND")
        if gnd is None:
            return [], "board has no GND net"
        # Return ownership belongs to both signal barrels, not merely their
        # midpoint.  A single flank via can be within 1.5 mm of the centre yet
        # leave the far member outside the field-return budget.  Prefer one
        # site covering both; add the opposite flank only when obstacles make
        # that impossible.  This is the same bounded geometry for every pair.
        signal_points = tuple(signal_points) or (tuple(center),)

        def covered(points, vias):
            return [point for point in points if any(
                math.dist(
                    point,
                    (via.GetPosition().x / MM,
                     via.GetPosition().y / MM))
                <= float(return_reach_mm) + 1e-9
                for via in vias)]

        uncovered = [point for point in signal_points
                     if point not in covered(signal_points,
                                             existing_gnd_vias())]
        if not uncovered:
            return [], "covered"
        vx, vy = pair_vector
        length = math.hypot(vx, vy) or 1.0
        pair_angle = math.atan2(vy / length, vx / length)
        if route_axis is not None:
            route_length = math.hypot(*route_axis) or 1.0
            route_unit = (route_axis[0] / route_length,
                          route_axis[1] / route_length)
        else:
            route_unit = None
        bounds = board.GetBoardEdgesBoundingBox()
        left, top = bounds.GetLeft() / MM, bounds.GetTop() / MM
        right, bottom = bounds.GetRight() / MM, bounds.GetBottom() / MM
        gnd_code = int(gnd.GetNetCode())
        radius_land = float(return_via_diameter_mm) / 2.0
        corridor_half = ((2.0 * width + gap) / 2.0
                         + radius_land + float(clearance))
        candidates = []
        for radius in (0.90, 1.10, 1.30, 1.45):
            for step_index in range(8):
                # Begin on the P/N separation axis, not the route axis. The
                # historical perpendicular-first order put the first legal
                # GND via directly in front of a matched pair and made the
                # subsequently invoked A* start cell a dead end.
                angle = pair_angle + step_index * math.pi / 4.0
                delta = (radius * math.cos(angle),
                         radius * math.sin(angle))
                route_projection = (abs(
                    delta[0] * route_unit[0]
                    + delta[1] * route_unit[1])
                    if route_unit is not None else 0.0)
                candidates.append((round(route_projection, 9), radius,
                                   step_index, delta))
        added = []
        while uncovered:
            legal = []
            for route_projection, radius, step_index, delta in sorted(
                    candidates):
                # The return via may sit beside either member, but never
                # inside the two-member routing envelope in front of or behind
                # the portal. If no lateral site exists this portal is not an
                # atomic transition candidate and must fail closed.
                if (route_unit is not None
                        and route_projection + 1e-9 >= corridor_half):
                    continue
                point = (center[0] + delta[0], center[1] + delta[1])
                if (point[0] - radius_land < left + 0.5
                        or point[0] + radius_land > right - 0.5
                        or point[1] - radius_land < top + 0.5
                        or point[1] + radius_land > bottom - 0.5):
                    continue
                at = _v(*point)
                if not cec_fr._via_spot_clear(
                        board, at, _nm(return_via_diameter_mm),
                        _nm(clearance), {gnd_code},
                        drill_nm=_nm(return_via_drill_mm),
                        net_code=gnd_code):
                    continue
                # Keep the distance expression separate from KiCad units so
                # the rank is deterministic and directly reviewable.
                hits = [signal for signal in uncovered
                        if math.dist(signal, point)
                        <= float(return_reach_mm) + 1e-9]
                if not hits:
                    continue
                legal.append((
                    -len(hits), route_projection, radius, step_index,
                    point, hits))
            if not legal:
                return added, (
                    "no legal GND return via within %.2fmm of every pair member"
                    % return_reach_mm)
            _neg_hits, _projection, _radius, _step, point, hits = min(legal)
            at = _v(*point)
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(at)
            via.SetWidth(_nm(return_via_diameter_mm))
            via.SetDrill(_nm(return_via_drill_mm))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(gnd_code)
            board.Add(via)
            added.append(via)
            uncovered = [signal for signal in uncovered if signal not in hits]
        return added, "added"

    def screen(rows, label):
        screen_started = time.monotonic()
        cache_key = screen_domain + (str(label),)
        cached = portal_screen_cache.get(cache_key)
        if cached is not None:
            cached_evidence = copy.deepcopy(cached["evidence"])
            cached_evidence["cache_hit"] = True
            cached_evidence["wall_seconds"] = 0.0
            evidence["screened"][label] = cached_evidence
            return copy.deepcopy(cached["accepted"])
        accepted = []
        checked = 0
        rejection_counts = {}
        blocker_counts = {}
        rejected_rows = []
        def lower_bound(row):
            return (
                round(_dist(row["actual_p"], row["p"])
                      + _dist(row["actual_n"], row["n"]), 6),
                round(abs(
                    _dist(row["actual_p"], row["p"])
                    - _dist(row["actual_n"], row["n"])), 6),
                round(abs(row["lateral_mm"]), 6),
                row["lead_mm"],
            )

        def record_rejected(row, reason, *, allow_detour, report=None):
            """Retain the nearest refused portal seats, not just totals.

            These rows are bounded diagnostic witnesses.  They are never used
            as routing admission, but they give placement repair a concrete
            destination and explain whether that destination was rejected by
            package copper, a reservation, or a transition-via field.
            """
            if len(rejected_rows) >= 24:
                return
            report = report or {}
            direct = (report.get("admission") or {}).get("direct") or {}
            blockers = []
            for member in ("p", "n"):
                blockers.extend(list((direct.get(member) or {}).get(
                    "foreign_blockers") or ()))
            rejected_rows.append({
                "score": list(lower_bound(row)),
                "portal": public_row(row),
                "allow_detour": bool(allow_detour),
                "reason": str(reason),
                "blockers": blockers[:8],
                "reservation_hits": list(
                    report.get("reservation_hits") or ())[:8],
            })

        # Breadth before depth: trying every nominally cheap straight fan-in
        # first still performs two exact board-copper queries per row and can
        # starve the bounded dogbones that wide connector pin fields actually
        # require.  Probe a ranked direct beam, then the ranked exact dogbone
        # domain.  Only if neither yields a candidate do we exhaust the
        # remaining direct rows, so no legal direct solution is removed from
        # the search space.
        ranked = sorted(rows, key=lower_bound)
        direct_beam = min(len(ranked), max(
            12, 4 * int(max_fanins_per_side)))
        phases = (
            (False, ranked[:direct_beam], "direct-beam", 32),
            (True, ranked, "bounded-dogbone", 32),
            (False, ranked[direct_beam:], "direct-exhaustive", 32),
        )
        phase_counts = {}
        for (allow_detour, ordered_rows, phase_name,
             detour_member_paths) in phases:
            phase_started = time.monotonic()
            phase_checked = 0
            for row in ordered_rows:
                if _deadline_expired(deadline):
                    break
                rollback()
                if layer_transition:
                    # A transition portal is not feasible merely because its
                    # surface fan-in is clear. Prove the matched signal-via
                    # field and nearby reference return before admitting this
                    # row into the beam; otherwise the first trace-optimal row
                    # can deterministically fail after selection while a
                    # slightly longer, fully viable portal is never tried.
                    p_via = add_signal_via(row["p"], p_code)
                    n_via = add_signal_via(row["n"], n_code)
                    pair_vector = (row["n"][0] - row["p"][0],
                                   row["n"][1] - row["p"][1])
                    _return_vias, return_status = add_return_via(
                        row["center"], pair_vector,
                        route_axis=portal_plan["axis"],
                        signal_points=(row["p"], row["n"]))
                    transition_reason = None
                    if p_via is None or n_via is None:
                        transition_reason = (
                            "matched signal-via field is not clear")
                    elif return_status not in ("covered", "added"):
                        transition_reason = return_status
                    rollback()
                    if transition_reason is not None:
                        checked += 1
                        phase_checked += 1
                        reason = "transition portal: %s" % transition_reason
                        rejection_counts[reason] = (
                            rejection_counts.get(reason, 0) + 1)
                        record_rejected(
                            row, reason, allow_detour=allow_detour)
                        continue
                checked += 1
                phase_checked += 1
                report = emit_fanin(
                    row, allow_detour=allow_detour,
                    detour_member_paths=detour_member_paths)
                if report.get("refused"):
                    reason = report["refused"]
                    rejection_counts[reason] = (
                        rejection_counts.get(reason, 0) + 1)
                    record_rejected(
                        row, reason, allow_detour=allow_detour,
                        report=report)
                    direct = (report.get("admission") or {}).get(
                        "direct") or {}
                    for member in ("p", "n"):
                        for blocker in ((direct.get(member) or {}).get(
                                "foreign_blockers") or ()):
                            key = json.dumps(
                                blocker, sort_keys=True,
                                separators=(",", ":"), default=str)
                            blocker_counts[key] = (
                                blocker_counts.get(key, 0) + 1)
                    continue
                created = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in base_ids}
                geometry = _pair_graph_geometry(board, pair, created)
                if not geometry["ok"]:
                    rejection_counts["pair geometry"] = (
                        rejection_counts.get("pair geometry", 0) + 1)
                    continue
                candidate = dict(row)
                candidate["fanin_length_mm"] = float(
                    report.get("length_mm", 0.0))
                candidate["fanin_coupling_pct"] = float(
                    report.get("coupled_coverage_pct", 0.0))
                candidate["allow_detour"] = allow_detour
                candidate["detour_member_paths"] = int(
                    detour_member_paths)
                candidate["score"] = (
                    round(candidate["fanin_length_mm"], 6),
                    round(abs(row["lateral_mm"]), 6),
                    round(row["lead_mm"], 6),
                )
                accepted.append(candidate)
                if len(accepted) >= int(max_fanins_per_side):
                    break
            phase_counts[phase_name] = {
                "checked": phase_checked,
                "wall_seconds": round(time.monotonic() - phase_started, 6),
            }
            if accepted or _deadline_expired(deadline):
                break
        rollback()
        accepted.sort(key=lambda row: row["score"])
        evidence["screened"][label] = {
            "checked": checked, "accepted": len(accepted),
            "phase_checked": phase_counts,
            "wall_seconds": round(time.monotonic() - screen_started, 6),
            "rejection_counts": rejection_counts,
            "blockers": [dict(json.loads(key), count=count)
                         for key, count in sorted(
                             blocker_counts.items(),
                             key=lambda item: (-item[1], item[0]))[:16]],
            "nearest_rejected": sorted(
                rejected_rows,
                key=lambda row: (tuple(row["score"]), row["reason"]))[:8],
            "candidates": [public_row(row) for row in accepted],
        }
        # An expired phase may have searched only a prefix of the domain. Do
        # not poison a later, larger phase with that incomplete negative. A
        # completed screen is exact local geometry and is safe to reuse while
        # this route_coupled_pair transaction keeps the board unchanged.
        if not _deadline_expired(deadline):
            portal_screen_cache[cache_key] = {
                "accepted": copy.deepcopy(accepted),
                "evidence": copy.deepcopy(evidence["screened"][label]),
            }
        return accepted

    for sign in portal_plan["sign_order"]:
        if _deadline_expired(deadline):
            break
        sign_rows = portal_plan["by_sign"][sign]
        start_rows = screen(sign_rows["start"], "start:%+d" % sign)
        end_rows = screen(sign_rows["end"], "end:%+d" % sign)
        if not start_rows or not end_rows:
            continue
        combinations = sorted(
            ((start["score"] + end["score"], start, end)
             for start in start_rows for end in end_rows),
            key=lambda row: row[0])[:int(max_portal_pairs)]
        for _score, start, raw_end in combinations:
            if _deadline_expired(deadline):
                break
            # Use the source portal as the A* lattice origin.  The nearest
            # rounded destination is not necessarily legal: a 0.1-mm snap can
            # push a previously screened fan-in into a power reservation or
            # package pad.  Enumerate the 3x3 floor/round/ceil neighborhood,
            # nearest first, and exact-screen the snapped fan-in before the
            # joint transaction.  This retains an octilinear lattice endpoint
            # without converting a valid placement into a false refusal.
            step = 0.5
            grid_x = ((raw_end["center"][0] - start["center"][0])
                      / step)
            grid_y = ((raw_end["center"][1] - start["center"][1])
                      / step)
            x_indices = sorted({math.floor(grid_x), round(grid_x),
                                math.ceil(grid_x)})
            y_indices = sorted({math.floor(grid_y), round(grid_y),
                                math.ceil(grid_y)})
            snap_rows = []
            for grid_ix in x_indices:
                for grid_iy in y_indices:
                    snapped_center = (
                        start["center"][0] + step * grid_ix,
                        start["center"][1] + step * grid_iy)
                    snap_delta = (
                        snapped_center[0] - raw_end["center"][0],
                        snapped_center[1] - raw_end["center"][1])
                    snap_rows.append((
                        round(math.hypot(*snap_delta), 9),
                        int(grid_ix), int(grid_iy), snapped_center,
                        snap_delta))
            snap_rows.sort(key=lambda row: (row[0], row[1], row[2]))
            end = None
            lattice_rejections = []
            for snap_distance, _ix, _iy, snapped_center, snap_delta in \
                    snap_rows:
                if _deadline_expired(deadline):
                    break
                candidate_end = dict(raw_end)
                candidate_end["center"] = snapped_center
                candidate_end["p"] = (
                    raw_end["p"][0] + snap_delta[0],
                    raw_end["p"][1] + snap_delta[1])
                candidate_end["n"] = (
                    raw_end["n"][0] + snap_delta[0],
                    raw_end["n"][1] + snap_delta[1])
                candidate_end["grid_snap_mm"] = round(
                    snap_distance, 6)
                rollback()
                snap_report = emit_fanin(
                    candidate_end,
                    allow_detour=candidate_end["allow_detour"],
                    detour_member_paths=candidate_end[
                        "detour_member_paths"])
                rollback()
                if not snap_report.get("refused"):
                    end = candidate_end
                    break
                lattice_rejections.append({
                    "grid_snap_mm": round(snap_distance, 6),
                    "reason": snap_report.get("refused"),
                })
            if end is None:
                evidence["attempts"].append({
                    "sign": sign, "start": public_row(start),
                    "end": public_row(raw_end),
                    "refused": (
                        "no reproducible lattice-aligned destination portal"),
                    "lattice_rejections": lattice_rejections[:9],
                })
                continue
            rollback()
            start_report = emit_fanin(
                start, allow_detour=start["allow_detour"],
                detour_member_paths=start["detour_member_paths"])
            end_report = emit_fanin(
                end, allow_detour=end["allow_detour"],
                detour_member_paths=end["detour_member_paths"])
            if start_report.get("refused") or end_report.get("refused"):
                evidence["attempts"].append({
                    "sign": sign, "start": public_row(start),
                    "end": public_row(end),
                    "refused": "screened fan-in was not reproducible",
                    "start_refused": start_report.get("refused"),
                    "end_refused": end_report.get("refused"),
                    "start_admission": start_report.get("admission"),
                    "end_admission": end_report.get("admission"),
                })
                continue

            middle_endpoints = (
                start["p"], end["p"], start["n"], end["n"])
            transition_evidence = []
            grid_diagnostics = {}
            if layer_transition:
                transition_refused = None
                for label, row in (("start", start), ("end", end)):
                    p_via = add_signal_via(row["p"], p_code)
                    n_via = add_signal_via(row["n"], n_code)
                    if p_via is None or n_via is None:
                        transition_refused = (
                            "%s matched signal-via field is not clear" % label)
                        break
                    pair_vector = (row["n"][0] - row["p"][0],
                                   row["n"][1] - row["p"][1])
                    return_vias, return_status = add_return_via(
                        row["center"], pair_vector,
                        route_axis=portal_plan["axis"],
                        signal_points=(row["p"], row["n"]))
                    if return_status not in ("covered", "added"):
                        transition_refused = "%s %s" % (
                            label, return_status)
                        break
                    transition_evidence.append({
                        "side": label,
                        "p_at_mm": [round(value, 6) for value in row["p"]],
                        "n_at_mm": [round(value, 6) for value in row["n"]],
                        "pair_spacing_mm": round(
                            _dist(row["p"], row["n"]), 6),
                        "return_status": return_status,
                        "return_at_mm": (
                            [round(return_vias[0].GetPosition().x / MM, 6),
                             round(return_vias[0].GetPosition().y / MM, 6)]
                            if return_vias else None),
                        "return_vias_at_mm": [[
                            round(via.GetPosition().x / MM, 6),
                            round(via.GetPosition().y / MM, 6),
                        ] for via in return_vias],
                    })
                if transition_refused:
                    evidence["attempts"].append({
                        "sign": sign, "start": public_row(start),
                        "end": public_row(end),
                        "refused": transition_refused,
                        "transitions": transition_evidence,
                    })
                    continue
                # These are already screened, aligned transition portals. A
                # long-span terminal-stub enumeration is neither a cheap
                # direct check nor useful here: it can overrun the inner-layer
                # allocation before A* sees a single state. Search the shared
                # centreline first; its first expansion covers the unobstructed
                # direct case. The legacy ensemble remains a last fallback if
                # the bounded grid finishes while time remains.
                local_refusal = {
                    "refused": "explicit via portals use grid-first search"}
                middle = local_refusal
                grid_started = time.monotonic()
                grid = _grid_coupled_path(
                    board, start_center=start["center"],
                    end_center=end["center"],
                    p_start=start["p"], n_start=start["n"],
                    p_end=end["p"], n_end=end["n"],
                    layer_id=middle_layer_id, width=width, gap=gap,
                    clearance=clearance, own=own, avoid=middle_avoid,
                    step=step, initial_turn_steps=0,
                    portal_mode=True, deadline=deadline,
                    diagnostics=grid_diagnostics,
                    max_visited=max_grid_visited,
                    foreign_shape_cache=foreign_shape_cache)
                grid_diagnostics["wall_seconds"] = round(
                    time.monotonic() - grid_started, 6)
                if grid is not None:
                    p_points, n_points, coupled_len = grid
                    coupling = _polyline_coupling_coverage(
                        p_points, n_points, width, gap)
                    if (_pair_min_clear(
                            p_points, n_points, -1, -1, width, gap,
                            strict_pair_gap=True)
                            and coupling["fraction"] + 1e-9 >= 0.80):
                        laid = _lay(
                            board, p_code, p_points, width_nm,
                            middle_layer_id)
                        laid += _lay(
                            board, n_code, n_points, width_nm,
                            middle_layer_id)
                        middle = {
                            "name": pair["name"], "p": pair["p"],
                            "n": pair["n"],
                            "route_mode": "portal-centreline-grid",
                            "layer": middle_layer,
                            "segments": len(laid),
                            "length_mm": round(sum(
                                _dist(a, b)
                                for points in (p_points, n_points)
                                for a, b in zip(
                                    points, points[1:])) / 2.0, 2),
                            "coupled_len_mm": round(coupled_len, 2),
                            "coupled_coverage_pct": coupling[
                                "coverage_pct"],
                        }
                if middle.get("refused"):
                    if _deadline_expired(deadline):
                        legacy = {
                            "refused": "coupled route deadline exhausted",
                            "search_budget_exhausted": True,
                        }
                    else:
                        legacy = route_coupled_pair(
                            board, pair, endpoints=middle_endpoints,
                            layer=middle_layer, clearance=clearance,
                            verbose=False, avoid=middle_avoid,
                            pair_grid=False,
                            minimum_coupled_fraction=0.80,
                            deadline=deadline,
                            allow_layer_transitions=False)
                    if not legacy.get("refused"):
                        middle = legacy
                    else:
                        evidence["attempts"].append({
                            "sign": sign,
                            "start": public_row(start),
                            "end": public_row(end),
                            "refused": (
                                "inner-layer paired ribbon refused: %s" %
                                legacy["refused"]),
                            "inner_route": {
                                "local_refused": local_refusal.get(
                                    "refused"),
                                "grid": grid_diagnostics,
                                "legacy_refused": legacy.get("refused"),
                                "legacy_search_budget_exhausted": bool(
                                    legacy.get(
                                        "search_budget_exhausted")),
                            },
                            "transitions": transition_evidence,
                        })
                        continue
            else:
                middle = _route_paired_stub(
                    board, pair, middle_endpoints, layer=layer,
                    clearance=clearance, avoid=source_avoid,
                    allow_detour=False,
                    minimum_coupled_fraction=0.80, deadline=deadline,
                    foreign_shape_cache=foreign_shape_cache,
                    partner_shape_cache=partner_shape_cache,
                    blocker_shape_cache=blocker_shape_cache)
                if middle.get("refused"):
                    grid_started = time.monotonic()
                    grid = _grid_coupled_path(
                        board, start_center=start["center"],
                        end_center=end["center"],
                        p_start=start["p"], n_start=start["n"],
                        p_end=end["p"], n_end=end["n"],
                        layer_id=layer_id, width=width, gap=gap,
                        clearance=clearance, own=own, avoid=source_avoid,
                        step=step, initial_turn_steps=0,
                        portal_mode=True, deadline=deadline,
                        diagnostics=grid_diagnostics,
                        max_visited=max_grid_visited,
                        foreign_shape_cache=foreign_shape_cache)
                    grid_diagnostics["wall_seconds"] = round(
                        time.monotonic() - grid_started, 6)
                    if grid is None:
                        evidence["attempts"].append({
                            "sign": sign, "start": public_row(start),
                            "end": public_row(end),
                            "refused": "no shared-centreline corridor",
                            "grid": grid_diagnostics,
                        })
                        continue
                    p_points, n_points, coupled_len = grid
                    coupling = _polyline_coupling_coverage(
                        p_points, n_points, width, gap)
                    if (not _pair_min_clear(
                            p_points, n_points, -1, -1, width, gap,
                            strict_pair_gap=True)
                            or coupling["fraction"] + 1e-9 < 0.80):
                        evidence["attempts"].append({
                            "sign": sign, "start": public_row(start),
                            "end": public_row(end),
                            "refused": "shared-centreline ribbon failed exact gap/coupling",
                        })
                        continue
                    laid = _lay(board, p_code, p_points, width_nm, layer_id)
                    laid += _lay(board, n_code, n_points, width_nm, layer_id)
                    middle = {
                        "name": pair["name"], "p": pair["p"],
                        "n": pair["n"], "route_mode": "portal-centreline-grid",
                        "layer": layer, "segments": len(laid),
                        "length_mm": round(sum(
                            _dist(a, b) for points in (p_points, n_points)
                            for a, b in zip(points, points[1:])) / 2.0, 2),
                        "coupled_len_mm": round(coupled_len, 2),
                        "coupled_coverage_pct": coupling["coverage_pct"],
                    }

            created = {
                item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in base_ids}
            normalization = _drop_fully_covered_tracks(board, created)
            created = {
                item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in base_ids}
            geometry = _pair_graph_geometry(board, pair, created)
            coupling = _pair_coupling_summary(board, pair, created)
            import cec_route_quality
            quality = cec_route_quality.analyze_board(
                board, critical_nets=(pair["p"], pair["n"]),
                track_uuid_scope=created)
            admitted = (
                geometry["ok"] and quality["ok"]
                and coupling["coverage_pct"] + 1e-9
                >= 100.0 * float(minimum_coupled_fraction))
            attempt = {
                "sign": sign, "start": public_row(start),
                "end": public_row(end),
                "graph_ok": geometry["ok"],
                "coupled_coverage_pct": coupling["coverage_pct"],
                "route_quality_blocking": quality["blocking_count"],
                "normalization": normalization,
                "transitions": transition_evidence,
            }
            if not admitted:
                attempt["refused"] = "whole portal edge admission failed"
                attempt["graph_issues"] = geometry.get("issues", [])[:8]
                attempt["route_quality_issues"] = quality.get(
                    "issues", [])[:8]
                evidence["attempts"].append(attempt)
                continue

            if middle.get("route_mode") == "portal-centreline-grid":
                attempt["grid"] = grid_diagnostics
            evidence["attempts"].append(attempt)
            stackup = cec_impedance.stackup_for_board(
                board.GetFileName() or "", board=board, layer=middle_layer)
            zkw = {"h_mm": stackup["h_mm"], "er": stackup["er"],
                   "t_mm": stackup["t_mm"]}
            length_mm = sum(
                item.GetLength() / MM for item in board.GetTracks()
                if (item.m_Uuid.AsString() in created
                    and item.GetClass() == "PCB_TRACK")) / 2.0
            if verbose:
                print("[precision] R3 %s portal ribbon on %s%s: "
                      "coverage=%.1f%% segments=%d"
                      % (pair["name"], middle_layer,
                         (" via %s" % layer if layer_transition else ""),
                         coupling["coverage_pct"], len(created)),
                      file=sys.stderr)
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "route_mode": (
                    "paired-portals-atomic-layer-transition"
                    if layer_transition else
                    "paired-portals-shared-centreline"),
                "layer": middle_layer, "source_layer": layer,
                "layer_transition": layer_transition,
                "width": width, "gap_nominal": gap,
                "zdiff_nominal": round(
                    cec_impedance.zdiff_edge_coupled(width, gap, **zkw), 1),
                "ztarget": pair.get("ztarget"), "stackup": stackup,
                "segments": len(created),
                "length_mm": round(length_mm, 2),
                "coupled_len_mm": round(
                    float(start_report.get("coupled_len_mm", 0.0))
                    + float(middle.get("coupled_len_mm", 0.0))
                    + float(end_report.get("coupled_len_mm", 0.0)), 2),
                "coupled_coverage_pct": coupling["coverage_pct"],
                "graph_geometry": geometry, "route_quality": quality,
                "normalization": normalization,
                "portal_evidence": evidence,
                "transitions": transition_evidence,
                "legs": [start_report, middle, end_report],
            }

    rollback()
    reason = ("paired portal search deadline exhausted"
              if _deadline_expired(deadline)
              else "paired portal candidates exhausted")
    return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": reason, "portal_evidence": evidence}


def _pair_route_failure_certificate(
        pair, endpoints, *, layer, width, gap, clearance,
        short_pair_refusal=None, portal_refusal=None,
        layer_transition_refusals=(), conventional_diagnostics=None,
        grid_failure_diagnostics=(), corridor_rejects=()):
    """Collapse the complete bounded pair-search fail stack into geometry.

    This certificate is deliberately diagnostic, not a waiver or a proof of
    global impossibility.  It keeps exact reservation intersections, endpoint
    portal seats, foreign-object identities, A* frontier gaps, and suggested
    rigid-station probe vectors.  Placement can therefore repair the *cause*
    of a refusal rather than translating arbitrary pair references.
    """
    p_start, p_end, n_start, n_end = endpoints
    start_center = ((p_start[0] + n_start[0]) / 2.0,
                    (p_start[1] + n_start[1]) / 2.0)
    end_center = ((p_end[0] + n_end[0]) / 2.0,
                  (p_end[1] + n_end[1]) / 2.0)
    dx = end_center[0] - start_center[0]
    dy = end_center[1] - start_center[1]
    span = math.hypot(dx, dy) or 1.0
    axis = (dx / span, dy / span)
    normal = (-axis[1], axis[0])

    reason_counts = {}
    screen_rows = []
    grid_rows = list(grid_failure_diagnostics or ())
    reservation_hits = []
    grid_reservation_hits = []
    blockers = []
    grid_blockers = []
    seen_nodes = set()

    def add_reason(value):
        if not value:
            return
        value = str(value)
        reason_counts[value] = reason_counts.get(value, 0) + 1

    def visit(value, path=(), *, forensic_grid=False):
        if isinstance(value, dict):
            identity = id(value)
            if identity in seen_nodes:
                return
            seen_nodes.add(identity)
            add_reason(value.get("refused"))
            add_reason(value.get("reason"))
            for reason, count in (value.get("rejection_counts") or {}).items():
                reason_counts[str(reason)] = (
                    reason_counts.get(str(reason), 0) + int(count or 0))
            for hit in value.get("reservation_hits") or ():
                if isinstance(hit, dict):
                    (grid_reservation_hits if forensic_grid
                     else reservation_hits).append(dict(hit))
            for hit in value.get("blockers") or ():
                if isinstance(hit, dict):
                    (grid_blockers if forensic_grid
                     else blockers).append(dict(hit))
            screened = value.get("screened")
            if isinstance(screened, dict):
                for label, row in sorted(screened.items()):
                    if not isinstance(row, dict):
                        continue
                    screen_rows.append({
                        "path": "/".join(str(part) for part in path[-5:]),
                        "endpoint": str(label).split(":", 1)[0],
                        "sign": (str(label).split(":", 1)[1]
                                 if ":" in str(label) else None),
                        "checked": int(row.get("checked", 0) or 0),
                        "accepted": int(row.get("accepted", 0) or 0),
                        "rejection_counts": dict(
                            row.get("rejection_counts") or {}),
                        "blockers": list(row.get("blockers") or ())[:8],
                        "nearest_rejected": list(
                            row.get("nearest_rejected") or ())[:4],
                    })
            # Portal and layer-transition A* attempts already carry compact
            # diagnostics.  Retain them alongside the final package-grid fan.
            grid = value.get("grid")
            if isinstance(grid, dict) and grid.get("status"):
                grid_rows.append({
                    "path": "/".join(str(part) for part in path[-5:]),
                    "grid": dict(grid),
                })
            for key, child in value.items():
                if isinstance(child, (dict, list, tuple)):
                    visit(child, path + (key,),
                          forensic_grid=(forensic_grid or key == "grid"))
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list, tuple)):
                    visit(child, path + (index,),
                          forensic_grid=forensic_grid)

    visit(short_pair_refusal, ("short_pair",))
    visit(portal_refusal, ("portal",))
    visit(list(layer_transition_refusals or ()), ("layer_transition",))
    visit(list(grid_failure_diagnostics or ()), ("package_grid",),
          forensic_grid=True)
    if conventional_diagnostics:
        visit(conventional_diagnostics, ("conventional",))

    def unique_rows(rows, limit):
        out, seen = [], set()
        for row in rows:
            key = json.dumps(row, sort_keys=True, separators=(",", ":"),
                             default=str)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= int(limit):
                break
        return out

    reservation_hits = unique_rows(reservation_hits, 24)
    grid_reservation_hits = unique_rows(grid_reservation_hits, 24)
    blockers = unique_rows(blockers, 24)
    grid_blockers = unique_rows(grid_blockers, 16)
    screen_rows = unique_rows(screen_rows, 24)
    grid_rows = unique_rows(grid_rows, 32)

    def projected_normal_displacement(hit):
        rect = hit.get("inflated_rect_mm") or hit.get("rect_mm")
        segment = hit.get("segment_mm")
        if (not isinstance(rect, (list, tuple)) or len(rect) < 4
                or not isinstance(segment, (list, tuple))
                or len(segment) < 2):
            return None
        x0, y0, x1, y1 = (float(value) for value in rect[:4])
        corners = ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
        rect_projection = [x * normal[0] + y * normal[1]
                           for x, y in corners]
        segment_projection = [
            float(point[0]) * normal[0] + float(point[1]) * normal[1]
            for point in segment[:2]]
        positive = max(0.0, max(rect_projection) - min(segment_projection))
        negative = max(0.0, max(segment_projection) - min(rect_projection))
        return {
            "positive_mm": round(positive + 0.01, 6),
            "negative_mm": round(negative + 0.01, 6),
            "minimum_mm": round(min(positive, negative) + 0.01, 6),
        }

    barriers = []
    for hit in reservation_hits:
        row = dict(hit)
        if not row.get("layer"):
            row["layer"] = str(layer)
        displacement = projected_normal_displacement(hit)
        if displacement is not None:
            row["projected_normal_displacement"] = displacement
        barriers.append(row)

    endpoint_summary = {}
    for endpoint, center in (("start", start_center), ("end", end_center)):
        rows = [row for row in screen_rows if row["endpoint"] == endpoint]
        rejection_totals = {}
        endpoint_blockers = []
        nearest = []
        for row in rows:
            for reason, count in row["rejection_counts"].items():
                rejection_totals[str(reason)] = (
                    rejection_totals.get(str(reason), 0) + int(count or 0))
            endpoint_blockers.extend(row["blockers"])
            nearest.extend(row["nearest_rejected"])
        endpoint_summary[endpoint] = {
            "center_mm": [round(value, 6) for value in center],
            "screens": len(rows),
            "checked": sum(row["checked"] for row in rows),
            "accepted": sum(row["accepted"] for row in rows),
            "all_screened_portals_refused": bool(
                rows and all(row["accepted"] == 0 for row in rows)),
            "rejection_counts": dict(sorted(rejection_totals.items())),
            "dominant_blockers": unique_rows(endpoint_blockers, 12),
            "nearest_rejected_portals": unique_rows(nearest, 8),
        }

    grid_status_counts = {}
    nearest_frontier = None
    compact_grid_rows = []
    for row in grid_rows:
        grid = row.get("grid") if isinstance(row, dict) else None
        if not isinstance(grid, dict):
            continue
        status = str(grid.get("status") or "unknown")
        grid_status_counts[status] = grid_status_counts.get(status, 0) + 1
        if grid.get("frontier_gap_mm") is not None:
            candidate = {
                "gap_mm": float(grid["frontier_gap_mm"]),
                "at_mm": grid.get("nearest_frontier_mm"),
                "path": row.get("path"),
            }
            if (nearest_frontier is None
                    or candidate["gap_mm"] < nearest_frontier["gap_mm"]):
                nearest_frontier = candidate
        compact_grid_rows.append({
            "path": row.get("path"),
            "launch_signs": row.get("launch_signs"),
            "launch_geometry": row.get("launch_geometry"),
            "status": status,
            "visited": grid.get("visited"),
            "max_visited": grid.get("max_visited"),
            "frontier_gap_mm": grid.get("frontier_gap_mm"),
            "nearest_frontier_mm": grid.get("nearest_frontier_mm"),
            "rejection_counts": dict(
                grid.get("rejection_counts") or {}),
            "reservation_owners": sorted({
                str(hit.get("reservation"))
                for hit in (grid.get("reservation_hits") or ())
                if isinstance(hit, dict) and hit.get("reservation")}),
            "blocker_refs": sorted({
                str(hit.get("ref"))
                for hit in (grid.get("dominant_blockers") or ())
                if isinstance(hit, dict) and hit.get("ref")}),
        })

    classifications = []
    if barriers or corridor_rejects:
        classifications.append("reservation_barrier")
    if any(row["all_screened_portals_refused"]
           for row in endpoint_summary.values()):
        classifications.append("endpoint_escape_refused")
    conventional_diagnostics = conventional_diagnostics or {}
    if (int(conventional_diagnostics.get(
            "middle_guard_refused", 0) or 0)
            or any(status in {
                "grid_exhausted", "offset_geometry_refused",
                "exact_member_guard_refused", "essential_reverse_kink",
                "centreline_reverse_bend"}
                   for status in grid_status_counts)):
        classifications.append("middle_guard_refused")
    if any("deadline" in status for status in grid_status_counts) or any(
            "deadline" in reason.lower() for reason in reason_counts):
        classifications.append("search_exhausted")
    if any("transition portal" in reason.lower()
           or "signal-via field" in reason.lower()
           for reason in reason_counts):
        classifications.append("layer_transition_refused")
    if not classifications:
        classifications.append("bounded_candidates_exhausted")

    tested_steps = {0.5, 1.0, 2.0}
    barrier_minima = [
        float((barrier.get("projected_normal_displacement") or {}).get(
            "minimum_mm", 0.0) or 0.0)
        for barrier in barriers]
    barrier_minima = [value for value in barrier_minima if value > 0.0]
    if barrier_minima:
        tested_steps.add(min(
            8.0, math.ceil(min(barrier_minima) * 4.0) / 4.0))
    relief_reason = classifications[0]
    relief_vectors = []
    for endpoint in ("start", "end"):
        for direction, vector in (
                ("normal-positive", normal),
                ("normal-negative", (-normal[0], -normal[1]))):
            relief_vectors.append({
                "endpoint": endpoint,
                "direction": direction,
                "vector": [round(value, 6) for value in vector],
                "probe_steps_mm": sorted(tested_steps),
                "reason": relief_reason,
            })

    return {
        "schema": 1,
        "conclusion": "bounded_search_exhausted_not_global_impossibility",
        "classification": classifications,
        "pair": {"name": pair.get("name"), "p": pair.get("p"),
                 "n": pair.get("n")},
        "layer": str(layer),
        "width_mm": round(float(width), 6),
        "gap_mm": round(float(gap), 6),
        "clearance_mm": round(float(clearance), 6),
        "corridor": {
            "span_mm": round(span, 6),
            "axis": [round(value, 6) for value in axis],
            "normal": [round(value, 6) for value in normal],
        },
        "endpoints": endpoint_summary,
        "reservation_barriers": barriers,
        "reservation_owners": sorted({
            str(row.get("reservation")) for row in barriers
            if row.get("reservation")}
            | {str(value) for value in corridor_rejects or ()}),
        "dominant_blockers": blockers,
        "dominant_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(
                reason_counts.items(),
                key=lambda item: (-item[1], item[0]))[:16]],
        "conventional": {
            key: value for key, value in conventional_diagnostics.items()
            if key != "reservation_hits"},
        "grid": {
            "attempt_count": len(grid_rows),
            "status_counts": dict(sorted(grid_status_counts.items())),
            "nearest_frontier": nearest_frontier,
            "explored_reservation_owners": sorted({
                str(row.get("reservation")) for row in grid_reservation_hits
                if row.get("reservation")}),
            "explored_blocker_refs": sorted({
                str(row.get("ref")) for row in grid_blockers
                if row.get("ref")}),
            "attempts": compact_grid_rows[:16],
        },
        "relief_vectors": relief_vectors,
    }


def route_coupled_pair(board, pair, *, layer="F.Cu", clearance=None, verbose=False,
                       avoid=(), endpoints=None, pair_grid=False,
                       minimum_coupled_fraction=0.0, deadline=None,
                       allow_layer_transitions=True):
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
    _corridor_rejects = set()
    reservation_avoid = avoid
    avoid = _avoid_for_layer(avoid, layer)
    p_net, n_net = pair["p"], pair["n"]
    width, gap = pair["width"], pair["gap"]
    if _deadline_expired(deadline):
        return {"name": pair["name"], "p": p_net, "n": n_net,
                "refused": "coupled route deadline exhausted"}
    if endpoints is None:
        p_ends = _endpoints(_pads_on_net(board, p_net))
        n_ends = _endpoints(_pads_on_net(board, n_net))
        if not p_ends or not n_ends:
            return {"name": pair["name"], "p": p_net, "n": n_net,
                    "refused": "missing pads on one member"}
        (pa, pb) = (p_ends[0][2], p_ends[1][2])
        (na, nb) = (n_ends[0][2], n_ends[1][2])
    else:
        try:
            pa, pb, na, nb = endpoints
        except (TypeError, ValueError):
            return {"name": pair["name"], "p": p_net, "n": n_net,
                    "refused": "invalid explicit pair endpoints"}

    lay_id = board.GetLayerID(layer)
    if lay_id < 0:
        return {"name": pair["name"], "p": p_net, "n": n_net,
                "refused": "layer %s absent" % layer}

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
        return (cec_fr._edge_leg_clear(board, _v(*a), _v(*b),
                                       width_nm // 2, edge_mm=0.5)
                and cec_fr._tap_foreign_clear(board, _v(*a), _v(*b), width_nm,
                                          lay_id, clr_nm, own)
                and _partner_pads_clear(
                    board, a, b, width_nm, lay_id, partner, clr_nm)
                and _partner_tracks_clear(
                    board, a, b, width_nm, lay_id, partner))

    def escape(src, dst, partner, max_radius=3.2):
        """Shortest clear monotonic pad->lane path with at most one bend.

        A route that must reverse direction during this tiny escape is not a
        precision route.  Refuse it here so the grid/fallback tier can solve the
        topology without manufacturing a connected pseudo-stub.
        """
        candidates = []
        direct = [src, dst]
        if seg_clear(src, dst, partner):
            quality = _escape_candidate_quality(direct)
            if quality is not None:
                candidates.append((quality, direct))
        radii = tuple(sorted({0.8, 1.2, 1.6, 2.0, 2.6, 3.2,
                              round(float(max_radius), 6)}))
        for r in radii:
            # OWNER SCORECARD FIX (2026-07-09): 8 directions at 45-degree steps -- the
            # 24x15-degree fan laid 'strange acute angles... jarring, HF-style' bends.
            for k in range(8):
                th = 2.0 * math.pi * k / 8.0
                mid = (src[0] + r * math.cos(th), src[1] + r * math.sin(th))
                if seg_clear(src, mid, partner) and seg_clear(mid, dst, partner):
                    points = [src, mid, dst]
                    quality = _escape_candidate_quality(points)
                    if quality is not None:
                        candidates.append((quality, points))
        return min(candidates, key=lambda row: row[0])[1] if candidates else None

    Sc = ((P_src[0] + N_src[0]) / 2.0, (P_src[1] + N_src[1]) / 2.0)
    Dc = ((P_dst[0] + N_dst[0]) / 2.0, (P_dst[1] + N_dst[1]) / 2.0)
    dx, dy = Dc[0] - Sc[0], Dc[1] - Sc[1]
    span = math.hypot(dx, dy) or 1.0
    ux, uy = dx / span, dy / span                 # corridor axis
    px, py = -uy, ux                              # perpendicular
    sgn = 1.0 if ((P_src[0] - Sc[0]) * px + (P_src[1] - Sc[1]) * py) >= 0 else -1.0

    # Try a few insets (how far the coupled run is pulled in from each cluster) x lateral
    # shifts. SHORTEST inset FIRST (owner scorecard fix 2026-07-09: the pair 'takes too
    # long to loop around and start riding alongside' -- earliest pairing pickup wins).
    # Widely separated connector contacts are the exception: their physical
    # fan-in needs a longer taper than an IC.  Scale each end independently so
    # a 4.6mm modular-jack pin spread is not forced through the IC-sized 3.6mm
    # ceiling, while compact endpoints keep the old search order and cost.
    start_budget = _pair_escape_budget(P_src, N_src)
    end_budget = _pair_escape_budget(P_dst, N_dst)
    short_pair_refusal = None
    if span <= _SPLIT_TERMINAL_FANOUT_MAX_MM + 1e-9:
        short_pair = _route_paired_stub(
            board, pair, (P_src, P_dst, N_src, N_dst),
            layer=layer,
            clearance=(clearance if clearance is not None else 0.2),
            avoid=reservation_avoid,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=deadline,
            allow_terminal_gap_taper=True)
        if not short_pair.get("refused"):
            short_pair["route_mode"] = "short-pair-local-cell"
            short_pair["short_pair_span_mm"] = round(span, 6)
            short_pair["width"] = width
            short_pair["gap_nominal"] = gap
            short_pair["ztarget"] = pair.get("ztarget")
            return short_pair
        short_pair_refusal = short_pair
    # Dissimilar endpoint pin fields are a portal problem, not a reason to
    # exhaust the legacy single-corridor inset fan first.  Give every screened
    # portal pair a shallow A* budget up front.  A viable later candidate then
    # cannot be starved by one earlier 120k-state dead end; genuinely difficult
    # candidates retain a deep retry after the cheap conventional forms.
    portal_refusal = None
    layer_transition_refusals = []
    portal_screen_cache = {}

    def phase_deadline(cap_seconds, remaining_fraction):
        """Reserve search time for later route ensembles.

        A single portal solver may legally consume its whole deadline.  Passing
        the pair-wide deadline to every sequential fallback therefore starves
        the inner layers whenever the first surface domain is difficult.  Give
        early phases a bounded share while retaining the original unlimited
        behaviour when the caller supplied no deadline.
        """
        if deadline is None:
            return None, None
        now = time.monotonic()
        remaining = max(0.0, float(deadline) - now)
        budget = min(float(cap_seconds),
                     remaining * float(remaining_fraction))
        return min(float(deadline), now + budget), budget

    def deadline_refusal():
        refusal = {"name": pair["name"], "p": p_net, "n": n_net,
                   "refused": "coupled route deadline exhausted",
                   "search_budget_exhausted": True}
        if short_pair_refusal is not None:
            refusal["short_pair_fallback"] = short_pair_refusal
        if portal_refusal is not None:
            refusal["portal_fallback"] = portal_refusal
        if layer_transition_refusals:
            refusal["layer_transition_fallback"] = \
                layer_transition_refusals
        return refusal
    start_spread = _dist(P_src, N_src)
    end_spread = _dist(P_dst, N_dst)
    nominal_separation = width + gap
    spread_ratio = (max(start_spread, end_spread)
                    / max(min(start_spread, end_spread), 1e-9))
    portal_warranted = (
        pair_grid
        and (max(start_spread, end_spread) > 2.5 * nominal_separation
             or spread_ratio > 2.0))
    if portal_warranted and not _deadline_expired(deadline):
        shallow_deadline, shallow_budget = phase_deadline(4.0, 0.20)
        shallow_started = time.monotonic()
        portal = _route_coupled_via_portals(
            board, pair, (P_src, P_dst, N_src, N_dst),
            layer=layer,
            clearance=(clearance if clearance is not None else 0.2),
            signal_via_diameter_mm=float(
                pair.get("via_diameter") or 0.50),
            signal_via_drill_mm=float(pair.get("via_drill") or 0.25),
            avoid=reservation_avoid,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=shallow_deadline, verbose=verbose,
            max_grid_visited=10000,
            portal_screen_cache=portal_screen_cache)
        portal["phase_budget_seconds"] = (
            round(shallow_budget, 6) if shallow_budget is not None else None)
        portal["phase_wall_seconds"] = round(
            time.monotonic() - shallow_started, 6)
        if not portal.get("refused"):
            portal["portal_search_phase"] = "shallow-first"
            return portal
        portal_refusal = {"shallow": portal}
    start_insets = tuple(sorted({1.3, 2.0, 2.8, 3.6,
                                 round(start_budget, 6)}))
    end_insets = tuple(sorted({1.3, 2.0, 2.8, 3.6,
                               round(end_budget, 6)}))
    conventional_diagnostics = {
        "candidates": 0, "middle_guard_refused": 0,
        "endpoint_escape_refused": 0, "member_crossing_refused": 0,
        "pair_gap_refused": 0, "coupling_refused": 0,
        "reservation_barrier_refused": 0,
        "reservation_hits": [],
    }
    for start_inset in start_insets:
      for end_inset in end_insets:
        if _deadline_expired(deadline):
            return deadline_refusal()
        if start_inset + end_inset >= span - 0.5:
            continue                              # clusters too close to seat a coupled run
        Se = (Sc[0] + ux * start_inset, Sc[1] + uy * start_inset)
        De = (Dc[0] - ux * end_inset, Dc[1] - uy * end_inset)
        for shift in (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.6, -2.6):
            conventional_diagnostics["candidates"] += 1
            po, no = sgn * off + shift, -sgn * off + shift
            Pls = (Se[0] + px * po, Se[1] + py * po)
            Ple = (De[0] + px * po, De[1] + py * po)
            Nls = (Se[0] + px * no, Se[1] + py * no)
            Nle = (De[0] + px * no, De[1] + py * no)
            if not (seg_clear(Pls, Ple, nc) and seg_clear(Nls, Nle, pc)):
                conventional_diagnostics["middle_guard_refused"] += 1
                continue
            eP0 = escape(P_src, Pls, nc, start_budget)
            eN0 = escape(N_src, Nls, pc, start_budget)
            eP1 = escape(P_dst, Ple, nc, end_budget)
            eN1 = escape(N_dst, Nle, pc, end_budget)
            if None in (eP0, eP1, eN0, eN1):
                conventional_diagnostics["endpoint_escape_refused"] += 1
                continue
            p_pts = eP0 + [Ple] + list(reversed(eP1))[1:]
            n_pts = eN0 + [Nle] + list(reversed(eN1))[1:]
            if not _polys_no_cross(p_pts, n_pts):
                conventional_diagnostics["member_crossing_refused"] += 1
                continue
            if not _pair_min_clear(p_pts, n_pts, len(eP0) - 1, len(eN0) - 1,
                                   width, gap, strict_pair_gap=True):
                conventional_diagnostics["pair_gap_refused"] += 1
                continue                          # partner overlap/graze -> next candidate
            coupling = _polyline_coupling_coverage(
                p_pts, n_pts, width, gap)
            if coupling["fraction"] + 1e-9 < float(minimum_coupled_fraction):
                conventional_diagnostics["coupling_refused"] += 1
                continue
            # RESERVED POUR CORRIDORS ARE OBSTACLES (2026-07-25). This router runs
            # on the "UNCONTENDED" placement and locks what it lays, and its
            # docstring says reservations are "the PourPlan keepout HINTS ...
            # passed to FR" -- true for FR, and exactly why the pairs themselves
            # cut straight through them: measured on eps, the USB pair laid 14mm
            # of LOCKED copper across /SENSEC1_LO's corridor before FR ever saw
            # the board, and the pour was then poured around it. A candidate that
            # enters a corridor is rejected here; if every candidate does, the
            # pair REFUSES (its own discipline) and FR routes it instead --
            # honouring the keepout, which is the outcome we want.
            _av = _crosses_avoid(p_pts, avoid, width) or _crosses_avoid(n_pts, avoid, width)
            if _av:
                _corridor_rejects.add(_av)
                conventional_diagnostics[
                    "reservation_barrier_refused"] += 1
                if len(conventional_diagnostics["reservation_hits"]) < 16:
                    details = _crosses_avoid_details(
                        p_pts, avoid, width, limit=8)
                    details += _crosses_avoid_details(
                        n_pts, avoid, width, limit=8)
                    conventional_diagnostics["reservation_hits"].extend(
                        details[:16 - len(conventional_diagnostics[
                            "reservation_hits"])])
                continue
            laid = _lay(board, pc, p_pts, width_nm, lay_id)
            laid += _lay(board, nc, n_pts, width_nm, lay_id)
            stackup = cec_impedance.stackup_for_board(
                board.GetFileName() or "", board=board, layer=layer)
            zkw = {"h_mm": stackup["h_mm"], "er": stackup["er"],
                   "t_mm": stackup["t_mm"]}
            zd_nom = cec_impedance.zdiff_edge_coupled(width, gap, **zkw)
            g_meas = _measured_gap(p_pts, n_pts, width)
            zd_meas = (cec_impedance.zdiff_edge_coupled(width, g_meas, **zkw)
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
                    "stackup": stackup,
                    "length_mm": run_len, "coupled_len_mm": coupled_len,
                    "coupled_coverage_pct": coupling["coverage_pct"]}

    # When the two endpoint pin fields differ substantially in pitch, split
    # the problem before asking global A* to solve it.  Exact local fan-ins
    # converge each package to an aligned portal and one shared centreline
    # owns the board-scale ribbon.  The trigger is purely geometric, so the
    # same fallback applies to modular jacks, headers, protection arrays, and
    # future packages without reference-designator exceptions.
    if portal_warranted and not _deadline_expired(deadline):
        deep_deadline, deep_budget = phase_deadline(4.0, 0.25)
        deep_started = time.monotonic()
        portal = _route_coupled_via_portals(
            board, pair, (P_src, P_dst, N_src, N_dst),
            layer=layer,
            clearance=(clearance if clearance is not None else 0.2),
            signal_via_diameter_mm=float(
                pair.get("via_diameter") or 0.50),
            signal_via_drill_mm=float(pair.get("via_drill") or 0.25),
            avoid=reservation_avoid,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=deep_deadline, verbose=verbose,
            max_grid_visited=120000,
            portal_screen_cache=portal_screen_cache)
        portal["phase_budget_seconds"] = (
            round(deep_budget, 6) if deep_budget is not None else None)
        portal["phase_wall_seconds"] = round(
            time.monotonic() - deep_started, 6)
        if not portal.get("refused"):
            portal["portal_search_phase"] = "deep-retry"
            return portal
        portal_refusal = dict(portal_refusal or {}, deep=portal)

    # A professional pair transition is not two independent single-net vias
    # repaired after routing.  If the surface corridor is exhausted, search
    # the board's other impedance-legal signal layers with one atomic object:
    # both package fan-ins, both matched signal-via fields, the inner coupled
    # ribbon, and a nearby GND return at each transition.  Only a completely
    # admitted transaction survives.  This is the generic escape for dense
    # IC/ESD pin fields and does not depend on board or reference names.
    if (pair_grid and allow_layer_transitions
            and not _deadline_expired(deadline)):
        try:
            referenced_layers = tuple(
                cec_fab_profile.referenced_signal_layers(
                    board, hint=board.GetFileName() or ""))
        except Exception:                              # noqa: BLE001
            referenced_layers = ()
        target_layers = [target_layer for target_layer in referenced_layers
                         if target_layer != layer]
        for target_index, target_layer in enumerate(target_layers):
            if _deadline_expired(deadline):
                break
            if deadline is None:
                target_deadline, target_budget = None, None
            else:
                now = time.monotonic()
                remaining = max(0.0, float(deadline) - now)
                target_budget = remaining / max(
                    1, len(target_layers) - target_index)
                target_deadline = min(
                    float(deadline), now + target_budget)
            target_started = time.monotonic()
            portal = _route_coupled_via_portals(
                board, pair, (P_src, P_dst, N_src, N_dst),
                layer=layer, middle_layer=target_layer,
                clearance=(clearance if clearance is not None else 0.2),
                signal_via_diameter_mm=float(
                    pair.get("via_diameter") or 0.50),
                signal_via_drill_mm=float(
                    pair.get("via_drill") or 0.25),
                avoid=reservation_avoid,
                minimum_coupled_fraction=minimum_coupled_fraction,
                deadline=target_deadline, verbose=verbose,
                max_grid_visited=40000,
                portal_screen_cache=portal_screen_cache)
            target_wall = time.monotonic() - target_started
            portal["phase_budget_seconds"] = (
                round(target_budget, 6)
                if target_budget is not None else None)
            portal["phase_wall_seconds"] = round(target_wall, 6)
            if not portal.get("refused"):
                portal["portal_search_phase"] = "atomic-multilayer"
                portal["layer_transition_attempts"] = (
                    layer_transition_refusals + [{
                        "layer": target_layer, "status": "accepted"}])
                return portal
            layer_transition_refusals.append({
                "layer": target_layer,
                "reason": portal.get("refused"),
                "portal_evidence": portal.get("portal_evidence"),
                "phase_budget_seconds": portal.get(
                    "phase_budget_seconds"),
                "phase_wall_seconds": portal.get("phase_wall_seconds"),
            })

    _grid_launches = (((1.0, 1.0), (1.0, -1.0),
                       (-1.0, 1.0), (-1.0, -1.0))
                      if pair_grid or os.environ.get("CEC_PAIR_GRID", "0") == "1"
                      else ())
    grid_foreign_shape_cache = {}
    grid_failure_diagnostics = []
    # Start with the conventional long normal launch.  Dense flow-through
    # packages may put a centre GND pad between the pair and a nearby bypass
    # part directly in front of it; in that case search progressively shorter
    # leads and bounded lateral lane shifts.  This is a topology-independent
    # endpoint-fanout search, not a reference-designator exception.
    _launch_shapes = (
        (1.25, 1.00, 3.00, 0.0, 0),
        (1.00, 0.50, 1.50, 0.0, 1),
        (0.75, 0.25, 1.00, 0.0, 1),
        (0.75, 0.25, 1.00, 0.6, 1),
        (0.75, 0.25, 1.00, -0.6, 1),
        (0.75, 0.25, 1.00, 1.0, 1),
        (0.75, 0.25, 1.00, -1.0, 1),
        (0.50, 0.15, 0.75, 1.4, 1),
        (0.50, 0.15, 0.75, -1.4, 1),
    )
    for start_sign, end_sign in _grid_launches:
      for (launch_distance, start_lead, end_lead, start_lateral,
           initial_turn_steps) in _launch_shapes:
        if _deadline_expired(deadline):
            return deadline_refusal()
        grid_diagnostics = {}
        grid = _grid_coupled_path(
            board, start_center=Sc, end_center=Dc,
            p_start=P_src, n_start=N_src, p_end=P_dst, n_end=N_dst,
            layer_id=lay_id, width=width, gap=gap,
            clearance=(clearance if clearance is not None else 0.2),
            own=own, avoid=avoid, start_sign=start_sign,
            end_sign=end_sign, launch_distance=launch_distance,
            start_lead=start_lead, end_lead=end_lead,
            start_lateral=start_lateral,
            initial_turn_steps=initial_turn_steps,
            deadline=deadline,
            diagnostics=grid_diagnostics,
            foreign_shape_cache=grid_foreign_shape_cache)
        if grid is None:
            grid_failure_diagnostics.append({
                "launch_signs": [start_sign, end_sign],
                "launch_geometry": {
                    "launch_distance_mm": launch_distance,
                    "start_lead_mm": start_lead,
                    "end_lead_mm": end_lead,
                    "start_lateral_mm": start_lateral,
                    "initial_turn_steps": initial_turn_steps,
                },
                "grid": grid_diagnostics,
            })
            continue
        p_pts, n_pts, coupled_len = grid
        coupling = _polyline_coupling_coverage(
            p_pts, n_pts, width, gap)
        strict_pair_gap = _pair_min_clear(
            p_pts, n_pts, -1, -1, width, gap,
            strict_pair_gap=True)
        p_clear = all(seg_clear(a, b, nc)
                      for a, b in zip(p_pts, p_pts[1:]))
        n_clear = all(seg_clear(a, b, pc)
                      for a, b in zip(n_pts, n_pts[1:]))
        p_avoid = _crosses_avoid(p_pts, avoid, width)
        n_avoid = _crosses_avoid(n_pts, avoid, width)
        if (p_clear and n_clear and not p_avoid and not n_avoid
                and strict_pair_gap
                and coupling["fraction"] + 1e-9
                >= float(minimum_coupled_fraction)):
            laid = _lay(board, pc, p_pts, width_nm, lay_id)
            laid += _lay(board, nc, n_pts, width_nm, lay_id)
            stackup = cec_impedance.stackup_for_board(
                board.GetFileName() or "", board=board, layer=layer)
            zkw = {"h_mm": stackup["h_mm"], "er": stackup["er"],
                   "t_mm": stackup["t_mm"]}
            zd_nom = cec_impedance.zdiff_edge_coupled(width, gap, **zkw)
            g_meas = _measured_gap(p_pts, n_pts, width)
            zd_meas = (cec_impedance.zdiff_edge_coupled(width, g_meas, **zkw)
                       if g_meas is not None else None)
            run_len = round(sum(_dist(a, b)
                                for a, b in zip(p_pts, p_pts[1:])), 2)
            if verbose:
                print("[precision] R3 %s grid-coupled on %s: w=%.3f "
                      "gap_nom=%.3f gap_meas=%s coupled=%.1fmm total=%.1fmm"
                      % (pair["name"], layer, width, gap, g_meas,
                         coupled_len, run_len), file=sys.stderr)
            return {"name": pair["name"], "p": p_net, "n": n_net,
                    "width": width, "gap_nominal": gap,
                    "gap_measured": g_meas,
                    "zdiff_nominal": round(zd_nom, 1),
                    "zdiff_measured": (round(zd_meas, 1)
                                       if zd_meas is not None else None),
                    "ztarget": pair.get("ztarget"), "segments": len(laid),
                    "stackup": stackup, "length_mm": run_len,
                    "coupled_len_mm": round(coupled_len, 2),
                    "coupled_coverage_pct": coupling["coverage_pct"],
                    "route_mode": "octilinear-grid",
                    "launch_signs": [start_sign, end_sign],
                    "launch_geometry": {
                        "launch_distance_mm": launch_distance,
                        "start_lead_mm": start_lead,
                        "end_lead_mm": end_lead,
                        "start_lateral_mm": start_lateral,
                        "initial_turn_steps": initial_turn_steps,
                    }}
        grid_diagnostics["status"] = "exact_member_guard_refused"
        grid_diagnostics["member_guard"] = {
            "p_clear": bool(p_clear), "n_clear": bool(n_clear),
            "p_reservation": p_avoid, "n_reservation": n_avoid,
            "strict_pair_gap": bool(strict_pair_gap),
            "coupled_coverage_pct": coupling["coverage_pct"],
            "minimum_coupled_coverage_pct": round(
                100.0 * float(minimum_coupled_fraction), 3),
        }
        reservation_hits = []
        if p_avoid:
            reservation_hits.extend(
                _crosses_avoid_details(p_pts, avoid, width, limit=8))
        if n_avoid:
            reservation_hits.extend(
                _crosses_avoid_details(n_pts, avoid, width, limit=8))
        if reservation_hits:
            grid_diagnostics["reservation_hits"] = reservation_hits[:16]
        grid_failure_diagnostics.append({
            "launch_signs": [start_sign, end_sign],
            "launch_geometry": {
                "launch_distance_mm": launch_distance,
                "start_lead_mm": start_lead,
                "end_lead_mm": end_lead,
                "start_lateral_mm": start_lateral,
                "initial_turn_steps": initial_turn_steps,
            },
            "grid": grid_diagnostics,
        })
        if os.environ.get("CEC_PAIR_DEBUG") == "1":
            print("[precision] pair grid exact guard refused",
                  "launch_signs=", (start_sign, end_sign),
                  "p_clear=", p_clear, "n_clear=", n_clear,
                  "p_avoid=", p_avoid, "n_avoid=", n_avoid,
                  file=sys.stderr)
            for label, points, partner in (("P", p_pts, nc),
                                           ("N", n_pts, pc)):
                for index, (a, b) in enumerate(zip(points, points[1:])):
                    if not seg_clear(a, b, partner):
                        print("[precision]", label, "blocked segment", index,
                              a, b, file=sys.stderr)
                        break
    _why = ("no clear coupled corridor at exact %sR geometry (escape+middle guard refused); "
            "hand off to cec_staged_fr tier-fallback"
            % (clearance if clearance is not None else 0.2))
    if _corridor_rejects:
        _why += (" -- every candidate entered a RESERVED POUR CORRIDOR (%s); FR will route "
                 "this pair instead, honouring the keepout"
                 % ", ".join(sorted(_corridor_rejects)))
    refused = {"name": pair["name"], "p": p_net, "n": n_net,
               "refused": _why}
    if short_pair_refusal is not None:
        refused["short_pair_fallback"] = short_pair_refusal
    if portal_refusal is not None:
        refused["portal_fallback"] = portal_refusal
    if layer_transition_refusals:
        refused["layer_transition_fallback"] = layer_transition_refusals
    refused["failure_certificate"] = _pair_route_failure_certificate(
        pair, (P_src, P_dst, N_src, N_dst),
        layer=layer, width=width, gap=gap,
        clearance=(clearance if clearance is not None else 0.2),
        short_pair_refusal=short_pair_refusal,
        portal_refusal=portal_refusal,
        layer_transition_refusals=layer_transition_refusals,
        conventional_diagnostics=conventional_diagnostics,
        grid_failure_diagnostics=grid_failure_diagnostics,
        corridor_rejects=_corridor_rejects)
    return refused


def _flow_leg_difficulty(board, pair, endpoints):
    """Cheap deterministic congestion proxy for a flow-through pair leg.

    Flow-through devices split one electrical pair into two physical routing
    problems.  Routing them in schematic/pad order let an easy leg consume the
    shared exact-search budget and starve the dense package leg.  This score is
    deliberately only an ordering hint: exact geometry remains the admission
    authority.  Foreign pads and copper in the expanded endpoint corridor
    dominate, followed by pin-field pitch change and route span.
    """
    pa, pb, na, nb = endpoints
    points = (pa, pb, na, nb)
    margin = max(1.0, 3.0 * float(pair["width"] + pair["gap"]))
    x0 = min(point[0] for point in points) - margin
    y0 = min(point[1] for point in points) - margin
    x1 = max(point[0] for point in points) + margin
    y1 = max(point[1] for point in points) + margin
    own = {board.GetNetcodeFromNetname(pair["p"]),
           board.GetNetcodeFromNetname(pair["n"])}
    foreign_pads = 0
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() in own:
                continue
            at = pad.GetPosition()
            x, y = at.x / MM, at.y / MM
            if x0 <= x <= x1 and y0 <= y <= y1:
                foreign_pads += 1
    foreign_copper = 0
    for item in board.GetTracks():
        if item.GetNetCode() in own:
            continue
        box = item.GetBoundingBox()
        bx0, by0 = box.GetLeft() / MM, box.GetTop() / MM
        bx1, by1 = box.GetRight() / MM, box.GetBottom() / MM
        if bx1 >= x0 and bx0 <= x1 and by1 >= y0 and by0 <= y1:
            foreign_copper += 1
    source_pitch = _dist(pa, na)
    destination_pitch = _dist(pb, nb)
    pitch_change = abs(source_pitch - destination_pitch)
    source_center = ((pa[0] + na[0]) / 2.0, (pa[1] + na[1]) / 2.0)
    destination_center = ((pb[0] + nb[0]) / 2.0,
                          (pb[1] + nb[1]) / 2.0)
    span = _dist(source_center, destination_center)
    return (foreign_pads, foreign_copper,
            round(pitch_change, 6), round(span, 6))


def _scheduled_flow_legs(board, pair, legs):
    """Return hardest-first ``(original_index, endpoints, score)`` rows."""
    rows = [(index, endpoints,
             _flow_leg_difficulty(board, pair, endpoints))
            for index, endpoints in enumerate(legs)]
    return sorted(rows, key=lambda row: (row[2], -row[0]), reverse=True)


def _fair_subdeadline(absolute_deadline, remaining_jobs, *, now=None):
    """Reserve an equal share of the remaining bounded search for each job."""
    current = time.monotonic() if now is None else float(now)
    remaining = max(0.0, float(absolute_deadline) - current)
    return min(float(absolute_deadline),
               current + remaining / max(1, int(remaining_jobs)))


def _pair_leg_center_span(endpoints):
    """Centreline span of one explicit ``(P0,P1,N0,N1)`` pair leg."""
    pa, pb, na, nb = endpoints
    source = ((pa[0] + na[0]) / 2.0, (pa[1] + na[1]) / 2.0)
    target = ((pb[0] + nb[0]) / 2.0, (pb[1] + nb[1]) / 2.0)
    return _dist(source, target)


def _pair_route_span(board, pair):
    """Direct physical span used to schedule mutually blocking pairs.

    A short local pair has few legal detours and is easy for a previously
    routed long pair to fence off.  Long board-scale pairs have more layer and
    corridor alternatives.  Route the constrained local geometry first, then
    let the longer pair consume the remaining space.  This is a scheduling
    heuristic only; exact coupled geometry and post-route admission remain the
    authority.
    """
    flow = _flow_through_pair_legs(board, pair)
    if flow is not None:
        return sum(_pair_leg_center_span(leg) for leg in flow[0])
    multidrop = _multidrop_pair_plan(board, pair)
    if multidrop is not None:
        return sum(float(edge.get("length_mm", 0.0) or 0.0)
                   for edge in multidrop.get("edges") or ())
    p_ends = _endpoints(_pads_on_net(board, pair["p"]))
    n_ends = _endpoints(_pads_on_net(board, pair["n"]))
    spans = []
    for ends in (p_ends, n_ends):
        if ends is not None:
            spans.append(_dist(ends[0][2], ends[1][2]))
    return (sum(spans) / len(spans)) if spans else float("inf")


def _pad_mst_span_mm(board, net_name):
    """Topology-safe lower bound for copper joining every pad on one net."""
    points = sorted({(pad.GetPosition().x / MM,
                      pad.GetPosition().y / MM)
                     for footprint in board.GetFootprints()
                     for pad in footprint.Pads()
                     if pad.GetNetname() == net_name})
    if len(points) < 2:
        return 0.0
    reached = {0}
    total = 0.0
    while len(reached) < len(points):
        distance, _first, second = min(
            (_dist(points[first], points[second]), first, second)
            for first in reached for second in range(len(points))
            if second not in reached)
        total += distance
        reached.add(second)
    return total


def _pair_transaction_detour(board, pair, *, limit=2.0,
                             minimum_span_mm=2.0):
    """Reject a connected pair that is grossly longer than its pad topology.

    Coupling, gap, and skew can all look excellent on a needless perimeter
    loop.  Compare each member's complete copper length with the Euclidean pad
    MST before the precision transaction is committed.  The MST supports
    ordinary two-terminal, flow-through, and multidrop pairs with one generic
    lower bound; the generous 2x limit leaves room for legal obstacle detours.
    """
    rows = []
    ok = True
    for net_name in (pair["p"], pair["n"]):
        span = _pad_mst_span_mm(board, net_name)
        length = 0.0
        for item in board.GetTracks():
            if item.GetNetname() != net_name or item.GetClass() == "PCB_VIA":
                continue
            try:
                length += item.GetLength() / MM
            except Exception:                            # noqa: BLE001
                start, end = item.GetStart(), item.GetEnd()
                length += math.hypot((end.x - start.x) / MM,
                                     (end.y - start.y) / MM)
        ratio = (length / span) if span > 1e-9 else None
        refused = bool(span >= float(minimum_span_mm)
                       and ratio is not None
                       and ratio > float(limit) + 1e-9)
        ok = ok and not refused
        rows.append({
            "net": net_name,
            "copper_length_mm": round(length, 6),
            "endpoint_mst_mm": round(span, 6),
            "ratio": round(ratio, 6) if ratio is not None else None,
            "refused": refused,
        })
    return {"schema": 1, "ok": ok, "limit": float(limit),
            "minimum_span_mm": float(minimum_span_mm), "members": rows}


def _pair_detour_failure_certificate(board, pair, detour, created_ids,
                                     endpoint_stations, *, local_search=None):
    """Preserve the exact copper and placement witness behind a detour refusal.

    The route transaction is rolled back immediately after this certificate is
    built. Without it, placement sees only ``2.01x`` and cannot distinguish an
    obstacle-induced member loop from a generic no-path failure.
    """
    scope = set(created_ids or ())
    pair_nets = {str(pair.get("p") or ""), str(pair.get("n") or "")}
    geometry = []
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_TRACK"
                or item.m_Uuid.AsString() not in scope
                or item.GetNetname() not in pair_nets):
            continue
        start, end = item.GetStart(), item.GetEnd()
        geometry.append({
            "net": item.GetNetname(),
            "layer": board.GetLayerName(item.GetLayer()),
            "start_mm": [round(start.x / MM, 6), round(start.y / MM, 6)],
            "end_mm": [round(end.x / MM, 6), round(end.y / MM, 6)],
            "length_mm": round(item.GetLength() / MM, 6),
        })
    geometry.sort(key=lambda row: (
        row["net"], row["layer"], row["start_mm"], row["end_mm"]))

    stations = [row for row in (endpoint_stations or ())
                if isinstance(row, dict)
                and isinstance(row.get("center"), (list, tuple))
                and len(row["center"]) >= 2]
    endpoints = {}
    relief = []
    if len(stations) >= 2:
        first, second = max(
            ((a, b) for index, a in enumerate(stations)
             for b in stations[index + 1:]),
            key=lambda rows: _dist(rows[0]["center"], rows[1]["center"]))
        a = (float(first["center"][0]), float(first["center"][1]))
        b = (float(second["center"][0]), float(second["center"][1]))
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = max(math.hypot(dx, dy), 1e-9)
        axis = (dx / span, dy / span)
        normal = (-axis[1], axis[0])
        endpoints = {
            "start": {"center_mm": [round(a[0], 6), round(a[1], 6)],
                      "station": first.get("id")},
            "end": {"center_mm": [round(b[0], 6), round(b[1], 6)],
                    "station": second.get("id")},
        }
        for endpoint in ("start", "end"):
            for sign, direction in ((1.0, "normal-positive"),
                                    (-1.0, "normal-negative")):
                relief.append({
                    "endpoint": endpoint, "direction": direction,
                    "vector": [round(sign * normal[0], 6),
                               round(sign * normal[1], 6)],
                    "probe_steps_mm": [0.5, 1.0, 2.0],
                    "reason": "excessive_detour",
                })

    members = list(detour.get("members") or ())
    refused = [row for row in members if row.get("refused")]
    return {
        "schema": 1,
        "conclusion": "exact_route_rejected_by_detour_quality_gate",
        "classification": ["excessive_detour"],
        "pair": {"name": pair.get("name"), "p": pair.get("p"),
                 "n": pair.get("n")},
        "limit": detour.get("limit"),
        "members": members,
        "dominant_member": (max(
            refused or members,
            key=lambda row: float(row.get("ratio") or 0.0))
            if members else None),
        "endpoints": endpoints,
        "relief_vectors": relief,
        "copper_witness": geometry[:32],
        "local_search": dict(local_search or {}),
    }


def _scheduled_coupled_pairs(board, pairs):
    """Deterministic constrained-first schedule for independent pair nets."""
    rows = [(round(_pair_route_span(board, pair), 6),
             str(pair.get("name") or ""), pair)
            for pair in pairs]
    rows.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in rows], [
        {"name": row[2].get("name"), "p": row[2].get("p"),
         "n": row[2].get("n"), "span_mm": row[0],
         "order": index + 1}
        for index, row in enumerate(rows)]


def _pair_leg_launch_reservations(endpoints, pair, *, launch_mm=3.6,
                                  clearance_mm=0.25, layer="F.Cu",
                                  leg_index=0):
    """Reserve both terminal escapes of one not-yet-routed pair leg.

    A constrained-first schedule is insufficient when the first route can
    traverse the only launch fan of a later pair.  These small, physical
    reservations cover the paired pad field and a bounded inward launch; they
    do not guess the later global route.  The ordinary exact avoid geometry
    then makes every earlier pair solve around that future access resource.
    """
    pa, pb, na, nb = endpoints
    if _dist(pa, na) + _dist(pb, nb) > _dist(pa, nb) + _dist(pb, na):
        na, nb = nb, na
    source = ((pa[0] + na[0]) / 2.0, (pa[1] + na[1]) / 2.0)
    target = ((pb[0] + nb[0]) / 2.0, (pb[1] + nb[1]) / 2.0)
    dx, dy = target[0] - source[0], target[1] - source[1]
    span = math.hypot(dx, dy)
    if span <= 1e-9:
        return []
    ux, uy = dx / span, dy / span
    reach = min(max(0.0, float(launch_mm)), span / 2.0)
    width = float(pair.get("width") or 0.2)
    gap = float(pair.get("gap") or 0.2)
    bundle_half = max(_dist(pa, na), _dist(pb, nb), width + gap) / 2.0
    radius = bundle_half + width / 2.0 + max(0.0, float(clearance_mm))
    name = str(pair.get("name") or "%s/%s" %
               (pair.get("p"), pair.get("n")))
    rows = []
    for end_name, start, sign in (("source", source, 1.0),
                                  ("target", target, -1.0)):
        finish = (start[0] + sign * ux * reach,
                  start[1] + sign * uy * reach)
        rows.append((min(start[0], finish[0]) - radius,
                     min(start[1], finish[1]) - radius,
                     max(start[0], finish[0]) + radius,
                     max(start[1], finish[1]) + radius,
                     "future-pair:%s:leg%d:%s" %
                     (name, int(leg_index) + 1, end_name), str(layer)))
    return rows


def _future_pair_launch_reservations(board, pairs):
    """Compile name-agnostic F.Cu launch reservations for pending pairs."""
    reservations = []
    for pair in pairs or ():
        flow = _flow_through_pair_legs(board, pair)
        if flow is not None:
            legs = list(flow[0])
        else:
            p_ends = _endpoints(_pads_on_net(board, pair["p"]))
            n_ends = _endpoints(_pads_on_net(board, pair["n"]))
            if not p_ends or not n_ends:
                continue
            legs = [(p_ends[0][2], p_ends[1][2],
                     n_ends[0][2], n_ends[1][2])]
        for index, endpoints in enumerate(legs):
            reservations.extend(_pair_leg_launch_reservations(
                endpoints, pair, leg_index=index))
    return reservations


# ---------------------------------------------------------------------------
# the precision ladder
# ---------------------------------------------------------------------------
def precision_route_board(board, *, board_path=None, kelvin_width=0.25,
                          verbose=True, do_kelvin=True, do_pairs=True,
                          avoid=(), kelvin_avoid=(), pair_grid=False,
                          existing_locked_nets=(), include_pair_names=None):
    """Run the precision ladder on an already-loaded board, in place.

    ``existing_locked_nets`` names fully-owned nets laid by an earlier pipeline
    stage.  A coupled pair whose two members are already in that set is reported
    as covered and is not duplicated.  This is what lets materialization route
    the pair before broad GND closure while the later route orchestrator merely
    protects that exact copper.
    """
    board_path = board_path or board.GetFileName() or ""
    pre_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
    existing_locked_nets = set(existing_locked_nets or ())

    # ---- R2 KELVIN (canonical inner-edge taps, pre-FR on the uncontended board) ----
    kelvin = {"taps": 0, "by_net": {}, "refused": {}, "segments": 0}
    if do_kelvin:
        kelvin = cec_fr.synthesize_kelvin_taps(
            board, width=kelvin_width, avoid=kelvin_avoid)
        if verbose:
            print("[precision] R2 kelvin: %d tap(s) laid %s; refused %s; "
                  "future-power obstacles=%d"
                  % (kelvin.get("taps", 0), kelvin.get("by_net", {}),
                     kelvin.get("refused", {}), len(kelvin_avoid or ())),
                  file=sys.stderr)

    # ---- R3 COUPLED PAIRS (deterministic, guarded, refuse-not-force) ----
    routed_pairs, refused_pairs = [], []
    pair_schedule = []
    if verbose and avoid:
        print("[precision] R3 pairs: %d reserved pour corridor(s) treated as obstacles"
              % len(avoid), file=sys.stderr)
    if do_pairs:
        derived_pairs = derive_coupled_pairs(board_path, board=board)
        if include_pair_names is not None:
            selected_names = {str(name) for name in include_pair_names}
            derived_pairs = [
                pair for pair in derived_pairs
                if str(pair.get("name")) in selected_names]
        pairs_to_route, pair_schedule = _scheduled_coupled_pairs(
            board, derived_pairs)
        for pair_index, pair in enumerate(pairs_to_route):
            # A bounded search space is not an operational bound when each
            # exact-copper probe is expensive.  Give every complete pair
            # transaction one shared wall-clock budget across surface,
            # portal, layer-transition, and flow-through legs.  Exhaustion is
            # a named refusal handed to the staged fallback, never a stalled
            # unattended wave.  The environment knob supports deliberate
            # high-effort runs without weakening the default fail-closed cap.
            pair_budget_s = max(5.0, float(os.environ.get(
                "CEC_PRECISION_PAIR_TIMEOUT", "240")))
            pair_deadline = time.monotonic() + pair_budget_s
            future_pair_avoid = _future_pair_launch_reservations(
                board, pairs_to_route[pair_index + 1:])
            pair_avoid = tuple(avoid or ()) + tuple(future_pair_avoid)
            pair_schedule[pair_index]["future_launch_reservations"] = len(
                future_pair_avoid)
            if {pair["p"], pair["n"]}.issubset(existing_locked_nets):
                routed_pairs.append({
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "route_mode": "preexisting-locked", "segments": 0,
                })
                continue
            pair_pre_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            endpoint_stations = _pair_endpoint_stations(board, pair)
            flow = _flow_through_pair_legs(board, pair)
            multidrop = (_multidrop_pair_plan(board, pair)
                         if flow is None else None)
            flow_pad_closure = None
            flow_pad_closure_refused = False
            if flow is not None:
                # Establish the package-native straight-through copper before
                # routing either external leg.  If this is deferred until the
                # end, an independently synthesized endpoint taper can occupy
                # the opposing member's through corridor and make a perfectly
                # valid ESD/CMC flow-through footprint impossible to close.
                # Topology, not a reference or MPN allowlist, selects these
                # stations: exactly two lands for each pair member on an
                # intermediate footprint.  The generic guarded local linker
                # still refuses any foreign-copper or pair-clearance conflict.
                _flow_legs, flow_stations = flow
                flow_pad_closure = cec_fr.synthesize_same_footprint_links(
                    board, include_nets={pair["p"], pair["n"]},
                    include_refs=set(flow_stations), lock=True)
                flow_pad_closure_refused = bool(
                    int(flow_pad_closure.get("pair_refused", 0) or 0)
                    or int(flow_pad_closure.get("refused", 0) or 0))
                if flow_pad_closure_refused:
                    for track in list(board.GetTracks()):
                        if (track.m_Uuid.AsString() not in pair_pre_ids
                                and track.GetNetname()
                                in {pair["p"], pair["n"]}):
                            board.Remove(track)
                    rep = {
                        "name": pair["name"], "p": pair["p"],
                        "n": pair["n"], "flow_through": flow_stations,
                        "refused": (
                            "flow-through package-native pair closure "
                            "refused before external routing"),
                        "flow_through_pad_closure": flow_pad_closure,
                    }
            if flow_pad_closure_refused:
                pass
            elif flow is None and multidrop is None:
                rep = route_coupled_pair(
                    board, pair, verbose=verbose, avoid=pair_avoid,
                    pair_grid=pair_grid, deadline=pair_deadline)
            elif multidrop is not None:
                rep = _route_layered_multidrop_pair_tree(
                    board, pair, multidrop, avoid=pair_avoid, verbose=verbose,
                    max_search_seconds=pair_budget_s,
                    _absolute_deadline=pair_deadline)
            else:
                legs, stations = flow
                route_mode = "flow-through"
                topology_key = "flow_through"
                topology_value = stations
                edge_evidence = None
                # Atomicity includes the station pre-closure: if either
                # external leg refuses, remove the through ties as well.
                pre_leg_ids = pair_pre_ids
                leg_reports_by_index = {}
                refused = None
                failed_leg_evidence = None
                scheduled_legs = _scheduled_flow_legs(board, pair, legs)
                leg_difficulty = {
                    index: score for index, _endpoints, score in scheduled_legs}
                for scheduled_index, (leg_index, endpoints, _score) in enumerate(
                        scheduled_legs):
                    # A single easy A* search may otherwise spend the complete
                    # pair deadline.  Preserve a deterministic share for every
                    # remaining physical leg, while retaining the one global
                    # bound for unattended operation.
                    leg_deadline = _fair_subdeadline(
                        pair_deadline, len(scheduled_legs) - scheduled_index)
                    layer_attempts = (["F.Cu"] if edge_evidence is None
                                      else list(edge_evidence[leg_index].get(
                                          "layers") or ("F.Cu",)))
                    layer_refusals = []
                    leg = None
                    for layer_index, leg_layer in enumerate(layer_attempts):
                        layer_deadline = _fair_subdeadline(
                            leg_deadline, len(layer_attempts) - layer_index)
                        trial = route_coupled_pair(
                            board, pair, verbose=verbose, avoid=pair_avoid,
                            endpoints=endpoints, pair_grid=pair_grid,
                            layer=leg_layer,
                            minimum_coupled_fraction=0.35,
                            deadline=layer_deadline)
                        if not trial.get("refused"):
                            leg = trial
                            if edge_evidence is not None:
                                edge_evidence[leg_index]["selected_layer"] = (
                                    leg_layer)
                            break
                        layer_refusals.append({
                            "layer": leg_layer,
                            "reason": trial.get("refused"),
                            "deadline_exhausted": bool(
                                trial.get("search_budget_exhausted")
                                or _deadline_expired(layer_deadline)),
                            "attempt": {key: trial[key] for key in (
                                "short_pair_fallback", "portal_fallback",
                                "layer_transition_fallback")
                                if key in trial},
                        })
                    if leg is None:
                        leg = {"refused": "layer ensemble exhausted: %s" %
                               layer_refusals}
                    if leg.get("refused"):
                        failed_leg_evidence = {
                            "leg": leg_index + 1,
                            "total_legs": len(legs),
                            "layers": layer_refusals,
                            "deadline_exhausted": any(
                                row.get("deadline_exhausted")
                                for row in layer_refusals),
                        }
                        refused = "%s leg %d/%d via %s refused: %s" % (
                            route_mode,
                            leg_index + 1, len(legs), ",".join(stations),
                            leg["refused"])
                        break
                    leg_reports_by_index[leg_index] = leg
                if refused is not None:
                    # Refuse atomically.  Leaving the first half of a protected
                    # pair locked when a later flow-through leg fails makes the
                    # fallback router solve a needlessly constrained topology.
                    for track in list(board.GetTracks()):
                        if track.m_Uuid.AsString() not in pre_leg_ids:
                            board.Remove(track)
                    rep = {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                           topology_key: topology_value, "refused": refused,
                           "flow_leg_order": [index + 1 for index, _ends, _score
                                              in scheduled_legs],
                           "flow_leg_difficulty": {
                               str(index + 1): list(leg_difficulty[index])
                               for index in sorted(leg_difficulty)},
                           "flow_leg_refusal": failed_leg_evidence,
                           "flow_leg_budget_exhausted": bool(
                               (failed_leg_evidence or {}).get(
                                   "deadline_exhausted"))}
                    if edge_evidence is not None:
                        rep["tree_edges"] = edge_evidence
                else:
                    leg_reports = [leg_reports_by_index[index]
                                   for index in range(len(legs))]
                    rep = dict(leg_reports[0])
                    rep.update({
                        "route_mode": route_mode,
                        topology_key: topology_value,
                        "legs": leg_reports,
                        "flow_leg_order": [index + 1 for index, _ends, _score
                                           in scheduled_legs],
                        "flow_leg_difficulty": {
                            str(index + 1): list(leg_difficulty[index])
                            for index in sorted(leg_difficulty)},
                        "segments": sum(r.get("segments", 0) for r in leg_reports),
                        "length_mm": round(sum(r.get("length_mm", 0.0)
                                               for r in leg_reports), 2),
                        "coupled_len_mm": round(sum(r.get("coupled_len_mm", 0.0)
                                                       for r in leg_reports), 2),
                    })
                    if edge_evidence is not None:
                        rep["tree_edges"] = edge_evidence
            if not rep.get("refused"):
                # A reversible connector exposes two physical D+ lands and two
                # physical D- lands; flow-through protectors do the same.  The
                # long coupled route historically selected one terminal from
                # each member, reported success, and left the other lands to
                # broad FR.  That made "important first" cosmetic: the later
                # router still had to rewrite/extend the pair and could destroy
                # its layer/skew/return-path contract.  Complete all duplicate
                # same-footprint legs atomically using the guarded pair fanout,
                # then require the normal full locked-ownership predicate.
                pair_nets = {pair["p"], pair["n"]}
                for track in board.GetTracks():
                    if (track.m_Uuid.AsString() not in pair_pre_ids
                            and track.GetNetname() in pair_nets):
                        track.SetLocked(True)
                local = cec_fr.synthesize_same_footprint_links(
                    board, include_nets=pair_nets, lock=True)
                pair_created_ids = {
                    track.m_Uuid.AsString() for track in board.GetTracks()
                    if (track.m_Uuid.AsString() not in pair_pre_ids
                        and track.GetNetname() in pair_nets)}
                local_normalization = _drop_fully_covered_tracks(
                    board, pair_created_ids)
                pair_created_ids = {
                    track.m_Uuid.AsString() for track in board.GetTracks()
                    if (track.m_Uuid.AsString() not in pair_pre_ids
                        and track.GetNetname() in pair_nets)}
                post_closure_geometry = _pair_graph_geometry(
                    board, pair, pair_created_ids, physical_only=True)
                missing = sorted(
                    pair_nets - cec_fr.owned_locked_nets_board(board))
                if (missing or int(local.get("pair_refused", 0) or 0)
                        or not post_closure_geometry["ok"]):
                    # Refuse atomically: never leave a half-owned pair as an
                    # obstacle for the high-effort fallback tier.
                    for track in list(board.GetTracks()):
                        if (track.m_Uuid.AsString() not in pair_pre_ids
                                and track.GetNetname() in pair_nets):
                            board.Remove(track)
                    rep = {
                        "name": pair["name"], "p": pair["p"],
                        "n": pair["n"],
                        "refused": (
                            "precision pair did not own every physical pad; "
                            "duplicate-pad closure missing=%s refused=%d "
                            "geometry_issues=%d"
                            % (missing, int(local.get("pair_refused", 0) or 0),
                               len(post_closure_geometry.get("issues", ())))),
                        "local_pad_closure": local,
                        "local_pad_normalization": local_normalization,
                        "post_closure_geometry": post_closure_geometry,
                    }
                else:
                    rep["local_pad_closure"] = local
                    rep["local_pad_normalization"] = local_normalization
                    rep["post_closure_geometry"] = post_closure_geometry
                    rep["fully_owned"] = True
                if flow_pad_closure is not None:
                    rep["flow_through_pad_closure"] = flow_pad_closure
            if not rep.get("refused"):
                detour = _pair_transaction_detour(board, pair)
                rep["detour_admission"] = detour
                if not detour["ok"]:
                    pair_created_ids = {
                        track.m_Uuid.AsString()
                        for track in board.GetTracks()
                        if (track.m_Uuid.AsString() not in pair_pre_ids
                            and track.GetNetname() in pair_nets)}
                    rep["failure_certificate"] = (
                        _pair_detour_failure_certificate(
                            board, pair, detour, pair_created_ids,
                            endpoint_stations,
                            local_search=rep.get("local_search")))
                    # Roll the complete pair transaction back atomically so
                    # the high-effort fallback or placement repair sees open
                    # routing resources, not a rejected locked perimeter wall.
                    for track in list(board.GetTracks()):
                        if (track.m_Uuid.AsString() not in pair_pre_ids
                                and track.GetNetname() in pair_nets):
                            board.Remove(track)
                    detail = ", ".join(
                        "%s %.2fx" % (row["net"], row["ratio"])
                        for row in detour["members"] if row["refused"])
                    rep["refused"] = (
                        "precision pair route detour exceeds %.2fx "
                        "endpoint-MST span: %s" %
                        (detour["limit"], detail))
            if not rep.get("refused"):
                # A connected short-cell route is not necessarily a coupled
                # route.  Validate the complete atomic transaction using the
                # same relative/absolute contract as independent signoff before
                # advertising critical-pair ownership to placement or FR.
                pair_created_ids = {
                    track.m_Uuid.AsString()
                    for track in board.GetTracks()
                    if (track.m_Uuid.AsString() not in pair_pre_ids
                        and track.GetNetname() in pair_nets)}
                coupling = _pair_coupling_summary(
                    board, pair, pair_created_ids)
                member_lengths = {}
                for net_name in sorted(pair_nets):
                    member_lengths[net_name] = sum(
                        track.GetLength() / MM
                        for track in board.GetTracks()
                        if (track.GetClass() == "PCB_TRACK"
                            and track.GetNetname() == net_name
                            and (not pair_created_ids
                                 or track.m_Uuid.AsString()
                                 in pair_created_ids)))
                coupling_admission = _pair_coupling_contract(
                    pair, coupling, member_lengths)
                rep["physical_coupling_admission"] = coupling_admission
                rep["coupled_coverage_pct"] = coupling[
                    "coverage_pct"]
                if not coupling_admission["ok"]:
                    certificate = _pair_detour_failure_certificate(
                        board, pair, detour, pair_created_ids,
                        endpoint_stations,
                        local_search=rep.get("local_search"))
                    certificate.update({
                        "conclusion": (
                            "exact_route_rejected_by_coupling_quality_gate"),
                        "classification": ["insufficient_coupling"],
                        "coupling": coupling_admission,
                        "dominant_member": None,
                    })
                    for row in certificate.get("relief_vectors", ()):
                        row["reason"] = "insufficient_coupling"
                    rep["failure_certificate"] = certificate
                    for track in list(board.GetTracks()):
                        if (track.m_Uuid.AsString() not in pair_pre_ids
                                and track.GetNetname() in pair_nets):
                            board.Remove(track)
                    rep["refused"] = (
                        "precision pair coupled coverage %.1f%% is below "
                        "%.1f%% and uncoupled length %.3fmm exceeds %.3fmm"
                        % (coupling_admission["coupled_coverage_pct"],
                           coupling_admission[
                               "minimum_coupled_coverage_pct"],
                           coupling_admission["uncoupled_length_mm"],
                           coupling_admission[
                               "uncoupled_length_budget_mm"]))
            rep.setdefault("endpoint_stations", endpoint_stations)
            if rep.get("refused"):
                rep.setdefault("pair_search_budget_s", pair_budget_s)
                rep.setdefault("pair_search_budget_exhausted",
                               bool(rep.get("flow_leg_budget_exhausted")
                                    or rep.get("search_budget_exhausted")
                                    or _deadline_expired(pair_deadline)))
                refused_pairs.append(rep)
                if verbose:
                    print("[precision] R3 %s REFUSED: %s"
                          % (rep["name"], rep["refused"]), file=sys.stderr)
            else:
                rep.setdefault("pair_search_budget_s", pair_budget_s)
                routed_pairs.append(rep)

    # ---- LOCK every R2/R3 track; collect the protect net set ----
    locked_nets, n_new_locked = set(), 0
    for t in board.GetTracks():
        if t.m_Uuid.AsString() in pre_ids:
            continue
        t.SetLocked(True)
        n_new_locked += 1
        nn = t.GetNetname()
        # A local transition return via is locked geometry, not ownership of
        # the global GND net.  Promoting GND to DSN ``protect`` would prevent
        # the broad router and plane stage from completing every other ground
        # terminal merely because one critical pair received a return barrel.
        if nn and nn != "GND":
            locked_nets.add(nn)
    covered_pair_nets = {net for rep in routed_pairs
                         if rep.get("route_mode") == "preexisting-locked"
                         for net in (rep["p"], rep["n"])}
    locked_nets |= covered_pair_nets
    n_existing = sum(1 for t in board.GetTracks()
                     if t.IsLocked() and t.GetNetname() in covered_pair_nets)
    n_locked = n_new_locked + n_existing

    # Post-generation admission is independent of the path planner.  The Hub
    # pseudo-stub proved that a generator-local guard can be incomplete while
    # still emitting connected, DRC-clean copper.  Audit only tracks created by
    # this invocation and fail the precision contract before broad routing can
    # protect a malformed critical route.
    import cec_route_quality
    created_ids = {t.m_Uuid.AsString() for t in board.GetTracks()
                   if t.m_Uuid.AsString() not in pre_ids}
    generated_items = [
        {"uuid": t.m_Uuid.AsString(), "net": t.GetNetname(),
         "kind": t.GetClass()}
        for t in board.GetTracks()
        if t.m_Uuid.AsString() in created_ids]
    pair_nets = {net for rep in routed_pairs
                 for net in (rep.get("p"), rep.get("n")) if net}
    kelvin_nets = set((kelvin.get("by_net") or {}).keys())
    route_quality = cec_route_quality.analyze_board(
        board, critical_nets=pair_nets | kelvin_nets,
        track_uuid_scope=created_ids)

    pairs_ok = (len(refused_pairs) == 0
                and route_quality.get("ok", False))
    kelvin_ok = not any((kelvin.get("refused") or {}).values())
    report = {
        "locked_nets": sorted(locked_nets),
        "n_locked_segments": n_locked,
        "n_new_locked_segments": n_new_locked,
        "generated_items": generated_items,
        "generated_item_count": len(generated_items),
        "kelvin": kelvin,
        "pairs": {"routed": routed_pairs, "refused": refused_pairs,
                  "schedule": pair_schedule},
        "route_quality": route_quality,
        "pairs_ok": pairs_ok,
        "kelvin_ok": kelvin_ok,
        "critical_routes_ok": pairs_ok and kelvin_ok,
    }
    if verbose:
        print("[precision] LOCKED %d segment(s) on %d net(s); pairs routed=%d refused=%d"
              % (n_locked, len(locked_nets), len(routed_pairs), len(refused_pairs)),
              file=sys.stderr)
    return report


def precision_route(placed_board, out_board, *, kelvin_width=0.25,
                    verbose=True, do_kelvin=True, do_pairs=True, avoid=(),
                    kelvin_avoid=(), pair_grid=False):
    """Run the PRE-FR precision ladder and save its protected board.

    Returns a report dict containing the output path, protected nets, Kelvin
    report, and routed/refused pair records.  R4 reservations are not laid here;
    they remain the route planner's keepout hints.
    """
    board = pcbnew.LoadBoard(placed_board)
    try:
        existing_locked = cec_fr.owned_locked_nets(placed_board)
    except Exception:                                  # noqa: BLE001 -- no coverage is safe
        existing_locked = ()
    report = precision_route_board(
        board, board_path=placed_board, kelvin_width=kelvin_width,
        verbose=verbose, do_kelvin=do_kelvin, do_pairs=do_pairs,
        avoid=avoid, kelvin_avoid=kelvin_avoid, pair_grid=pair_grid,
        existing_locked_nets=existing_locked)
    if not report.get("critical_routes_ok",
                      report.get("pairs_ok", False)):
        quality = report.get("route_quality") or {}
        if quality.get("blocking_count"):
            message = "precision route topology admission failed: %s" % [
                row.get("message") for row in quality.get("issues", ())
                if row.get("severity") == "blocking"][:5]
        else:
            kelvin_refused = (
                (report.get("kelvin") or {}).get("refused") or {})
            message = ("precision Kelvin route refused: %s" % kelvin_refused
                       if kelvin_refused else
                       "precision critical route refused")
        # Preserve the refused copper and complete certificate before raising.
        # The coordinator can now publish a reviewable failure artifact and a
        # structured candidate summary rather than leaking a raw traceback.
        pcbnew.SaveBoard(out_board, board)
        report["copied_sidecars"] = cec_fr.copy_project_sidecars(
            placed_board, out_board)
        report["out"] = out_board
        raise PrecisionRouteRefused(message, report)
    pcbnew.SaveBoard(out_board, board)
    # DRC/netclass and executable route ownership context travel with every
    # renamed board artifact.  Use the shared sidecar authority so precision
    # routing cannot silently drop qualified fab rules, pour ownership, or the
    # project filename rebind while other pipeline stages preserve them.
    report["copied_sidecars"] = cec_fr.copy_project_sidecars(
        placed_board, out_board)
    report["out"] = out_board
    return report


# ---------------------------------------------------------------------------
# CLI: python3 scripts/cec_precision_route.py PLACED OUT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: cec_precision_route.py PLACED.kicad_pcb OUT.kicad_pcb", file=sys.stderr)
        sys.exit(2)
    rep = precision_route(
        sys.argv[1], sys.argv[2], verbose=True,
        pair_grid=os.environ.get("CEC_PAIR_GRID", "0") == "1")
    print(json.dumps({k: v for k, v in rep.items() if k != "kelvin"}, indent=1, default=str))
    print("kelvin:", json.dumps(rep["kelvin"], default=str))
