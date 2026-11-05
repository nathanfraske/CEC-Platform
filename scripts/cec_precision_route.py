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
import os, sys, math, shutil, json, heapq, time, re, copy, collections

import pcbnew

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py (hub all-9999 root cause).
import cec_swig_guard as _swig_guard                     # noqa: E402
_swig_guard.pin()
import cec_native_layer_masks as _native_layer_masks     # noqa: E402
_native_layer_masks.install(pcbnew)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cec_fr
import cec_score
import cec_impedance
import cec_fab_profile
import cec_constraints
import cec_pair_skew
from cec_native_items import discard_items as _discard_items

MM = 1_000_000                       # nm per mm
_SPLIT_TERMINAL_FANOUT_MAX_MM = 8.0
# The exact paired-stub solver enumerates a finite local visibility domain.
# It is useful for package escapes and short branches, but a board-scale edge
# belongs to the coupled grid/portal router.  Bounding that distinction keeps
# the local combinatorial search from consuming the entire edge deadline
# before the global solver gets a turn.
_MULTIDROP_LOCAL_STUB_MAX_MM = 12.0


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
    # A pair kind is a semantic role, not necessarily the KiCad netclass
    # name.  Many current boards intentionally assign USB/CAN to Default and
    # carry their complete differential contract there.  Falling straight to
    # the historical per-kind literals in that case silently undercuts both
    # the assigned clearance and diff-pair gap.  Prefer a role-named class
    # when present, otherwise consume the project's actual Default authority.
    spec = classes.get(kind) or classes.get("default") or {}
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


def _pair_clearance(board, pair, requested=None):
    """A search override may tighten, never undercut, the pair contract."""
    values = [float(pair.get("clearance", 0.20))]
    if requested is not None:
        values.append(float(requested))
    values.append(float(board.GetDesignSettings().m_MinClearance) / MM)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("invalid pair clearance contract")
    return max(values)


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
        spec = classes.get(kind) or classes.get("default") or {}
        if spec:
            row.update({
                "clearance": float(spec.get("clearance") or 0.20),
                "via_diameter": float(spec.get("via_diameter") or 0.50),
                "via_drill": float(spec.get("via_drill") or 0.25),
            })
        pairs.append(row)

    # Shared electrical identity; geometry and independent signoff remain
    # separate. Do not infer transmission-line behavior from _P/_N alone.
    from cec_pair_semantics import coupled_pair_names
    rules = cec_score.Rules.from_board(board_path)
    identities = coupled_pair_names(b, rules.diff_pairs or ())
    for kind, p, n in identities:
        leaf = p.rsplit("/", 1)[-1]
        name = p.rsplit("_", 1)[0].lstrip("/") or p
        if kind == "can" and leaf.startswith("CAN_H"):
            name = "CAN" + leaf[len("CAN_H"):]
        elif kind == "usb" and leaf in ("USB_DP", "USB_D+"):
            name = "USB"
        # Repeated buses need distinct diagnostic/search-cache identities.
        if sum(row[0] == kind and row[1].rsplit("/", 1)[-1] == leaf
               for row in identities) > 1:
            name = p.rsplit("/", 1)[0].lstrip("/") + "/" + name
        _add(name, kind, p, n, 120.0 if kind == "can" else 90.0)

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


def _parallel_link_owner_map(board):
    """Use the same populated-link topology as source placement ownership."""
    import cec_parallel_links
    if not hasattr(board, "GetFootprints"):
        return {}
    pin_nets, active = {}, []
    for footprint in board.GetFootprints():
        if not hasattr(footprint, "Pads"):
            continue
        ref = str(footprint.GetReference())
        pin_nets[ref] = {str(pad.GetNumber()): str(pad.GetNetname())
                         for pad in footprint.Pads()}
        if (cec_parallel_links.is_zero_link(footprint.GetValue())
                and hasattr(footprint, "IsDNP") and not footprint.IsDNP()):
            active.append(ref)
    groups, _ambiguities = cec_parallel_links.derive(pin_nets, active)
    return {member["ref"]: (group["owner_ref"], frozenset(
        row["ref"] for row in group["members"]))
        for group in groups for member in group["members"]}


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
    link_owners = _parallel_link_owner_map(board)

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
            proven_link_group = (p_ref in link_owners
                                 and link_owners.get(p_ref) == link_owners.get(n_ref))
            if (p_ref in link_owners or n_ref in link_owners) and not proven_link_group:
                continue
            # Split pair members should be the same component family and,
            # when populated, the same land pattern.  Distance then provides
            # a deterministic one-to-one match among repeated stations.
            if not proven_link_group and (not p_signature[0] or p_signature[0] != n_signature[0]
                    or (p_signature[1] and n_signature[1]
                        and p_signature[1] != n_signature[1])):
                continue
            separation = _dist(by_p[p_ref][0][2], by_n[n_ref][0][2])
            if separation > _SPLIT_TERMINAL_FANOUT_MAX_MM + 1e-9 and not proven_link_group:
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
            "topology_owner": (link_owners[p_ref][0] if p_ref in link_owners else None),
            "locality_ok": separation <= _SPLIT_TERMINAL_FANOUT_MAX_MM + 1e-9,
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

    * an unambiguous two-terminal bank chain owns the endpoint roles even when
      its inline station was placed outside the terminal-to-terminal span;
    * otherwise the historical farthest-terminal heuristic remains a fallback;
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

    # First identify an unambiguous physical two-bank chain. Distance is not
    # electrical role: an off-corridor protection array must not become a
    # terminal and make a one-land IC into the branching junction. Interleaved
    # duplicate connector contacts do not satisfy the bank predicate.
    from cec_pair_banks import ordered_banks
    bank_matches = {ref: ordered_banks(
        [row[2] for row in by_p[ref]], [row[2] for row in by_n[ref]])
        for ref in common}
    physical_stations = [ref for ref in common if bank_matches[ref] is not None]
    physical_terminals = [ref for ref in common if bank_matches[ref] is None]
    unambiguous_chain = bool(physical_stations and len(physical_terminals) == 2)
    terminal_pair = (tuple(physical_terminals) if unambiguous_chain else max(
        ((a, b) for i, a in enumerate(common) for b in common[i + 1:]),
        key=lambda ab: _dist(ref_center(ab[0]), ref_center(ab[1]))))
    a_ref, b_ref = terminal_pair
    a_center, b_center = ref_center(a_ref), ref_center(b_ref)
    axis = (b_center[0] - a_center[0], b_center[1] - a_center[1])
    span2 = axis[0] * axis[0] + axis[1] * axis[1]
    if span2 <= 1e-9:
        return None

    def projection(value):
        return ((value[0] - a_center[0]) * axis[0]
                + (value[1] - a_center[1]) * axis[1]) / span2

    station_refs = (physical_stations if unambiguous_chain else [
        r for r in common if r not in terminal_pair
        and len(by_p[r]) == 2 and len(by_n[r]) == 2
        and 0.0 < projection(ref_center(r)) < 1.0])
    station_refs.sort(key=lambda r: projection(ref_center(r)))
    if not station_refs:
        return None

    def station_ports(ref):
        ps, ns = by_p[ref], by_n[ref]
        if unambiguous_chain:
            order = bank_matches[ref]
            return ((ps[0], ns[order[0]]), (ps[1], ns[order[1]]))
        direct = _dist(ps[0][2], ns[0][2]) + _dist(ps[1][2], ns[1][2])
        crossed = _dist(ps[0][2], ns[1][2]) + _dist(ps[1][2], ns[0][2])
        matched = ((ps[0], ns[0]), (ps[1], ns[1])) if direct <= crossed else \
                  ((ps[0], ns[1]), (ps[1], ns[0]))
        return tuple(matched)

    unoriented_ports = [station_ports(ref) for ref in station_refs]

    def port_center(port):
        return ((port[0][2][0] + port[1][2][0]) / 2.0,
                (port[0][2][1] + port[1][2][1]) / 2.0)

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

    # Projection alone cannot orient a station whose two pad banks are
    # perpendicular to the terminal axis (both banks then have the same
    # projection).  Enumeration order is not physical intent and, on a dense
    # ESD/CMC footprint, choosing the far bank can fence off the short external
    # escape.  Solve the two possible orientations of every station as a tiny
    # deterministic minimax chain dynamic program: minimize the longest
    # external leg first, then total length.  This preserves the most
    # constrained route while the short leg retains more detour freedom.  The
    # solve is linear in station count and applies to any two-bank footprint.
    orientations = [((row[0], row[1]), (row[1], row[0]))
                    for row in unoriented_ports]
    states = []
    for orientation_index, orientation in enumerate(orientations[0]):
        inbound, _outbound = orientation
        terminal = terminal_port(a_ref, port_center(inbound))
        span = _dist(port_center(terminal), port_center(inbound))
        states.append(((span, span), (orientation_index,), (orientation,)))
    for station_index in range(1, len(orientations)):
        next_states = []
        for orientation_index, orientation in enumerate(
                orientations[station_index]):
            inbound, _outbound = orientation
            candidates = []
            for cost, selected_indices, selected_ports in states:
                previous_outbound = selected_ports[-1][1]
                span = _dist(port_center(previous_outbound),
                             port_center(inbound))
                candidates.append((
                    (max(cost[0], span), cost[1] + span),
                    selected_indices + (orientation_index,),
                    selected_ports + (orientation,)))
            next_states.append(min(candidates, key=lambda row: (
                round(row[0][0], 9), round(row[0][1], 9), row[1])))
        states = next_states
    completed = []
    for cost, selected_indices, selected_ports in states:
        outbound = selected_ports[-1][1]
        terminal = terminal_port(b_ref, port_center(outbound))
        span = _dist(port_center(outbound), port_center(terminal))
        completed.append(((max(cost[0], span), cost[1] + span),
                          selected_indices, selected_ports))
    _cost, _indices, selected = min(completed, key=lambda row: (
        round(row[0][0], 9), round(row[0][1], 9), row[1]))
    ports = list(selected)

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
    link_owners = _parallel_link_owner_map(board)

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
        if p_ref in link_owners or n_ref in link_owners:
            return link_owners.get(p_ref) == link_owners.get(n_ref)
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


def _multidrop_tree_alternatives(plan, *, max_trees=4, max_exchanges=4096):
    """Bounded single-edge exchanges of the geometric spanning-tree seed.

    Euclidean MST length does not capture pin-field escape or junction
    feasibility. Keep its topology first, then connected cycle-free exchanges
    as exact-router proposals. Every proposal carries the same physical pad
    layers and bounded-terminal-fanout policy as the seed.
    """
    from itertools import combinations
    ports = plan['ports']; terminals = sorted(ports)
    base = [dict(e) for e in plan['edges']]
    base_keys = {tuple(sorted((e['a'],e['b']))) for e in base}
    def signature(edges): return tuple(sorted(tuple(sorted((e['a'],e['b']))) for e in edges))
    def connected(edges):
        reached = {terminals[0]}
        for _ in terminals:
            before = len(reached)
            for e in edges:
                if e['a'] in reached or e['b'] in reached:
                    reached.update((e['a'],e['b']))
            if len(reached)==before:break
        return len(reached)==len(terminals)
    proposals={signature(base):base}; checked=0
    for a,b in combinations(terminals,2):
        if (a,b) in base_keys:continue
        length=_dist(ports[a]['center'],ports[b]['center'])
        allowed=set(ports[a]['layers']) & set(ports[b]['layers'])
        layers=[name for name in plan['preferred_signal_layers'] if name in allowed]
        if not layers:continue
        through=ports[a]['through'] and ports[b]['through']
        if through and 'B.Cu' in layers:layers=['B.Cu']+[l for l in layers if l!='B.Cu']
        split=[r for r in (a,b) if ports[r].get('terminal_kind')=='split-member-footprints']
        fanout=bool(split and length <= _SPLIT_TERMINAL_FANOUT_MAX_MM+1e-9)
        extra=dict(a=a,b=b,length_mm=round(length,3),layers=layers,
            through_hole_edge=bool(through),split_terminal_refs=split,
            bounded_terminal_fanout=fanout,
            terminal_fanout_limit_mm=_SPLIT_TERMINAL_FANOUT_MAX_MM if fanout else None)
        for i in range(len(base)):
            if checked>=max_exchanges:break
            checked+=1
            edges=base[:i]+base[i+1:]+[extra]
            if connected(edges):proposals[signature(edges)]=edges
        if checked>=max_exchanges:break
    other=[edges for key,edges in proposals.items() if key!=signature(base)]
    other.sort(key=lambda edges:(sum(e['length_mm'] for e in edges),signature(edges)))
    return [dict(plan,edges=edges) for edges in ([base]+other)[:max(1,int(max_trees))]]


def _native_pair_edge_orders(plan, *, max_orders=2):
    """Bounded backbone-first and local-first orders of the same real tree.

    A short drop routed first can consume the shared launch used by the trunk.
    Rank the backbone using graph centrality, branch role and actual layer
    domains. Retain the old local-first ordering as one atomic alternative;
    no factorial permutation search, endpoint movement or relaxed physics.
    """
    edges = list(plan['edges'])
    centrality = _multidrop_edge_betweenness(edges)
    backbone = sorted(edges, key=lambda edge: (
        -centrality.get(tuple(sorted((edge['a'], edge['b']))), 0),
        bool(edge.get('bounded_terminal_fanout')),
        len(edge.get('layers') or ()), -float(edge['length_mm']),
        edge['a'], edge['b']))
    local = sorted(edges, key=lambda edge: (edge['length_mm'], edge['a'], edge['b']))
    rows = []
    seen = set()
    for name, order in [('backbone-first', backbone), ('local-first', local)]:
        signature = tuple(tuple(sorted((edge['a'], edge['b']))) for edge in order)
        if signature not in seen:
            rows.append((name, order)); seen.add(signature)
    return rows[:max(1, int(max_orders))]


def _native_plated_pair_face(board, pair, endpoints, layer):
    """Prove four actual plated terminals on an authorized signal face.

    This is dispatch evidence, not route/return qualification. Coordinate
    coincidence, a pad layer mask alone, or a planner's through-hole label
    cannot manufacture native access. Unknown/legacy boards retain the
    existing routing path.
    """
    evidence = dict(applicable=False, native_pad_uuids=[], layer=str(layer),
                    new_signal_vias_required=None, physical_qualified=False)
    try:
        profile_name = cec_fab_profile.board_profile_name(board)
        profile = cec_fab_profile.get_profile(profile_name) if profile_name else None
        if not profile or profile.get('pofv') is not True:
            return evidence
        lid = int(board.GetLayerID(str(layer)))
        canonical = cec_fab_profile.COPPER_LAYER_IDS.get(lid)
        if (canonical not in cec_fab_profile.referenced_signal_layers(
                board, hint=board.GetFileName() or "")
                or lid not in set(map(int, board.GetEnabledLayers().CuStack()))):
            return evidence
        pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
        if len(pads) > 8192 or len(endpoints) != 4:
            return evidence
        for net, xy in zip((pair['p'], pair['p'], pair['n'], pair['n']), endpoints):
            point = tuple(_v(*xy))
            matches = [p for p in pads if str(p.GetNetname()) == net
                       and tuple(p.GetPosition()) == point]
            if (len(matches) != 1 or matches[0].GetAttribute() != pcbnew.PAD_ATTRIB_PTH
                    or not matches[0].HasHole() or not matches[0].IsOnLayer(lid)):
                return evidence
            evidence['native_pad_uuids'].append(matches[0].m_Uuid.AsString())
        if len(set(evidence['native_pad_uuids'])) != 4:
            return evidence
        evidence.update(applicable=True, new_signal_vias_required=0)
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return evidence


def _route_direct_pair_tree(board, pair, plan, *, avoid=(), verbose=False,
                            deadline=None, minimum_leg_coupling=.35,
                            edge_order=None, primary_layer_budget_fraction=2.0/3.0):
    """Try native pad junctions before synthesizing an artificial star.

    Short paired branches can meet on their actual component lands. Creating
    virtual throats everywhere can unnecessarily consume a small pin field.
    Final native ownership, whole-graph quality and coupling remain mandatory.
    """
    if (type(primary_layer_budget_fraction) not in (int,float)
            or not math.isfinite(primary_layer_budget_fraction)
            or not 0 < primary_layer_budget_fraction < 1):
        raise ValueError('primary native layer budget fraction must be finite and between zero and one')
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    edges = (list(edge_order) if edge_order is not None else
             _native_pair_edge_orders(plan, max_orders=1)[0][1])
    reports = []
    for index, edge in enumerate(edges):
        a,b = plan['ports'][edge['a']],plan['ports'][edge['b']]
        # Exhaust the actual common native layer domain before manufacturing
        # transitions. A PTH barrel is already a legal zero-via layer portal.
        # Previously this constructive path used only layers[0], while its
        # nested transition search consumed the other layers' entire budget.
        common = set(a['layers']) & set(b['layers'])
        layers = list(dict.fromkeys(layer for layer in edge.get('layers', ())
                                    if layer in common))
        edge_deadline = (_fair_subdeadline(deadline, len(edges)-index)
                         if deadline is not None else None)
        edge_before = {t.m_Uuid.AsString() for t in board.GetTracks()}
        attempts = []
        report = {'refused': 'no common native pair layer'}
        fanout_limit = edge.get('terminal_fanout_limit_mm')
        bounded_fanout = bool(edge.get('bounded_terminal_fanout')
                              and fanout_limit is not None
                              and math.isfinite(float(fanout_limit))
                              and float(fanout_limit) > 0)
        # Keep transition routing as a bounded second class, not the first
        # layer's hidden monopoly. All classes share one edge deadline.
        jobs = [(layer, False) for layer in layers]
        jobs += [(layer, True) for layer in layers]
        for job_index, (layer, transitions) in enumerate(jobs):
            if _deadline_expired(edge_deadline):
                break
            started = time.monotonic()
            # One complete preferred native lane needs construction time,
            # not an equal fraction of every hypothetical layer/transition.
            # Keep the same edge/global cap and reserve the remainder for
            # fallbacks. A fast native refusal releases its unused share.
            subdeadline = None
            if edge_deadline is not None:
                subdeadline = (started + max(0.,edge_deadline-started)*primary_layer_budget_fraction
                    if job_index==0 else _fair_subdeadline(edge_deadline,len(jobs)-job_index))
            endpoints = (a['p'],b['p'],a['n'],b['n'])
            native_face = (_native_plated_pair_face(board, pair, endpoints, layer)
                           if not transitions else dict(applicable=False))
            coupling_floor = 0.0 if bounded_fanout else minimum_leg_coupling
            if native_face['applicable']:
                # Do not spend this native layer's lease searching remote
                # signal portals for pads already plated onto that face.
                # The endpoint helper uses the prepared body grid and still
                # requires the actual plated reference-return synthesis.
                report = _route_coupled_endpoint_pofv(board, pair, endpoints,
                    target_layer=layer, clearance=_pair_clearance(board,pair,None),
                    avoid=avoid,verbose=verbose,minimum_coupled_fraction=coupling_floor,
                    deadline=subdeadline)
            else:
                report = route_coupled_pair(board, pair, avoid=avoid, verbose=verbose,
                    endpoints=endpoints, layer=layer,pair_grid=True,
                    minimum_coupled_fraction=coupling_floor,
                    allow_layer_transitions=transitions, deadline=subdeadline)
            if bounded_fanout and not report.get('refused'):
                lengths = {net: sum(item.GetLength() / MM for item in board.GetTracks()
                                    if item.GetClass() == 'PCB_TRACK'
                                    and item.m_Uuid.AsString() not in edge_before
                                    and item.GetNetname() == net)
                           for net in (pair['p'], pair['n'])}
                contract = dict(limit_mm=float(fanout_limit), lengths_mm=lengths,
                    ok=max(lengths.values()) <= float(fanout_limit) + 1e-6,
                    whole_pair_coupling_required=True)
                report['bounded_terminal_contract'] = contract
                if not contract['ok']:
                    report['refused'] = 'native terminal fanout exceeds routed length limit'
            exhausted = bool(report.get('refused') and
                             (_deadline_expired(subdeadline) or
                              report.get('search_budget_exhausted')))
            attempts.append({'layer': layer, 'allow_layer_transitions': transitions,
                'native_plated_face_access': native_face,
                'allowed_s':None if subdeadline is None else max(0.,subdeadline-started),
                'budget_policy':'preferred-native-share-then-fair-reclaimed-fallbacks',
                'elapsed_s': round(time.monotonic()-started, 4),
                'status': ('deferred_budget' if exhausted else
                           'refused' if report.get('refused') else 'routed'),
                'reason': report.get('refused'), 'evidence': report})
            if not report.get('refused'):
                break
            # Include supporting ground vias; a rejected branch cannot poison
            # the next native-layer attempt or erase already accepted edges.
            _rollback_created_tracks(board, edge_before)
        reports.append(dict(report, graph_role='trunk_edge',
            edge=[edge['a'],edge['b']], native_layer_domain=layers,
            layer_attempts=attempts,
            search_budget_exhausted=any(row['status']=='deferred_budget'
                                       for row in attempts)))
        if report.get('refused'): break
    complete = len(reports)==len(edges) and not any(r.get('refused') for r in reports)
    created = {t.m_Uuid.AsString() for t in board.GetTracks()}-before
    normalization = _drop_fully_covered_tracks(board,created)
    created = {t.m_Uuid.AsString() for t in board.GetTracks()}-before
    geometry = _pair_graph_geometry(board,pair,created)
    detour = _pair_transaction_detour(board,pair,route_reports=reports)
    skew = cec_pair_skew.from_board(board, pair) if complete else None
    ok = complete and geometry['ok'] and detour['ok'] and skew['ok']
    result = dict(name=pair['name'],p=pair['p'],n=pair['n'],
        route_mode='native-pad-tree',tree_edges=edges,legs=reports,
        normalization=normalization,graph_geometry=geometry,detour_admission=detour,
        physical_skew_admission=skew,
        completed_edge_count=sum(not r.get('refused') for r in reports),
        total_edge_count=len(edges),remaining_edge_count=len(edges)-sum(not r.get('refused') for r in reports),
        segments=sum(r.get('segments',0) for r in reports),
        length_mm=sum(r.get('length_mm',0.) for r in reports),
        coupled_len_mm=sum(r.get('coupled_len_mm',0.) for r in reports),
        search_budget_exhausted=any(r.get('search_budget_exhausted') for r in reports))
    if not ok:
        result['refused'] = ('native pad tree edge refused' if not complete else
                             'native pad tree geometry refused' if not geometry['ok'] else
                             'native pad tree detour refused' if not detour['ok'] else
                             'native pad tree whole-pair skew refused')
        _rollback_created_tracks(board,before)
    return result


def _route_multidrop_topologies(board, pair, plan, *, avoid=(), verbose=False,
                                 deadline=None, max_trees=3, max_native_orders=2,
                                 primary_budget_fraction=2.0/3.0,
                                 candidate_qualifier=None, restore_parent=None):
    """Try a bounded topology domain under one atomic pair deadline.

    The primary native tree is one complete constructive solve, not a cheap
    screening probe. Previously two nested equal splits (representation and
    order) left it a quarter of the pair budget, then edge/layer splits made
    otherwise solvable trees appear blocked. Give it one explicit primary
    share, and distribute the remaining time across the bounded alternatives.
    Unused time is reclaimed; no trial may outlive the enclosing deadline.
    """
    if not math.isfinite(float(primary_budget_fraction)) or not 0 < float(primary_budget_fraction) < 1:
        raise ValueError('primary pair budget fraction must be finite and between zero and one')
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    proposals = _multidrop_tree_alternatives(plan, max_trees=max_trees)
    orders = _native_pair_edge_orders(plan, max_orders=max_native_orders)
    attempts = []; best = None

    def reset_candidate():
        _rollback_created_tracks(board,before)
        if restore_parent is not None:
            restore_parent()

    def qualify(result):
        if candidate_qualifier is None or result.get('refused'):
            return result
        try:
            checked=candidate_qualifier(result)
            if not isinstance(checked,dict):
                raise TypeError('candidate qualification must return a report')
            return checked
        except Exception:
            reset_candidate()
            raise

    for order_index, (order_name, order) in enumerate(orders):
        if _deadline_expired(deadline): break
        started = time.monotonic()
        subdeadline = None
        if deadline is not None:
            subdeadline = (started + max(0., deadline-started)*float(primary_budget_fraction)
                           if order_index == 0 else
                           _fair_subdeadline(deadline, len(orders)-order_index+len(proposals)))
        direct = _route_direct_pair_tree(board,pair,plan,avoid=avoid,verbose=verbose,
            deadline=subdeadline,edge_order=order)
        direct=qualify(direct)
        attempts.append({'strategy':'native-pad-tree','edge_order':order_name,
            'allowed_s':None if subdeadline is None else max(0.,subdeadline-started),
            'elapsed_s':round(time.monotonic()-started,4),
            'attempt':direct,'refused':direct.get('refused')})
        if not direct.get('refused'): return dict(direct,topology_attempts=attempts)
        reset_candidate()
        if best is None or int(direct.get('remaining_edge_count',len(order))) < int(best.get('remaining_edge_count',len(order))):
            best = direct
    for index, proposal in enumerate(proposals):
        if _deadline_expired(deadline): break
        subdeadline = (_fair_subdeadline(deadline, len(proposals)-index)
                       if deadline is not None else None)
        result = _route_layered_multidrop_pair_tree(
            board, pair, proposal, avoid=avoid, verbose=verbose,
            _absolute_deadline=subdeadline)
        if not result.get('refused'):
            detour = _pair_transaction_detour(board, pair,
                                             route_reports=result.get('legs') or ())
            if not detour['ok']:
                result = dict(result, refused='topology route exceeds detour contract',
                              detour_admission=detour)
            else:
                skew = cec_pair_skew.from_board(board, pair)
                result['physical_skew_admission'] = skew
                if not skew['ok']:
                    result['refused'] = 'topology route exceeds whole-pair skew contract'
        result=qualify(result)
        attempts.append({'topology_index':index,
            'edges':[[e['a'],e['b']] for e in proposal['edges']],
            'refused':result.get('refused'), 'attempt':result})
        if not result.get('refused'):
            return dict(result, topology_attempts=attempts)
        reset_candidate()
        if best is None or int(result.get('remaining_edge_count',len(proposal['edges']))) < int(best.get('remaining_edge_count',len(proposal['edges']))):
            best = result
    return dict(best or {'name':pair['name'],'p':pair['p'],'n':pair['n'],
                         'refused':'topology search deadline exhausted'},
                topology_attempts=attempts)


def _rollback_created_tracks(board, before):
    """Rollback all transaction-owned copper, including supporting GND vias."""
    removed = []
    for item in list(board.GetTracks()):
        identifier = item.m_Uuid.AsString()
        if identifier not in before:
            _discard_items(board,[item])
            removed.append(identifier)
    return removed


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


def _assign_multidrop_edge_layers(plan, edges, *, pair=None,
                                  max_states=8192, forced_layers=None,
                                  route_layer_evidence=None):
    """Assign available layers to a paired tree before creating junctions.

    A plated through-hole terminal is already a zero-via layer articulation.
    Greedily selecting the first layer for every edge can manufacture a
    difficult same-layer star at every connector in a chain.  Search the small
    discrete edge-coloring problem instead:

    * non-PTH internal terminals must keep all incident edges on one layer;
    * PTH terminals may articulate, but a high-betweenness serial backbone is
      kept continuous when exact route evidence does not reject that layer;
    * repeated incidence outside that backbone is still penalized because it
      requires a planar paired junction cell;
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
    betweenness = _multidrop_edge_betweenness(rows)
    maximum_betweenness = max(betweenness.values(), default=0)
    backbone_floor = 0.75 * float(maximum_betweenness)
    backbone_indices = {
        index for index, edge in enumerate(rows)
        if maximum_betweenness > 0
        and betweenness.get(tuple(sorted((edge["a"], edge["b"]))), 0)
        + 1e-9 >= backbone_floor
    }

    def score_assignment(assignment):
        incidence = {}
        backbone_incidence = {}
        layers_by_ref = {}
        preferred_cost = 0
        interface_outer_cost = 0
        learned_refusals = 0
        learned_timeouts = 0
        learned_successes = 0
        for index, layer in assignment.items():
            edge = rows[index]
            preferred_cost += rank.get(layer, len(preferred) + 4)
            difficulty = _multidrop_edge_interface_difficulty(edge, ports)
            has_inner_signal_option = any(
                candidate not in ("F.Cu", "B.Cu")
                for candidate in edge.get("_layer_options") or ())
            if (difficulty.get("constrained")
                    and has_inner_signal_option
                    and layer in ("F.Cu", "B.Cu")):
                interface_outer_cost += 1
            key = tuple(sorted((edge["a"], edge["b"])))
            learned = route_layer_evidence.get(key, {}).get(layer, {})
            learned_refusals += int(learned.get("refusals", 0))
            learned_timeouts += int(learned.get("timeouts", 0))
            learned_successes += int(learned.get("successes", 0))
            for ref in (edge["a"], edge["b"]):
                incidence[(ref, layer)] = incidence.get((ref, layer), 0) + 1
                layers_by_ref.setdefault(ref, set()).add(layer)
                if index in backbone_indices:
                    backbone_incidence.setdefault(ref, []).append(layer)
        backbone_discontinuities = sum(
            max(0, len(set(layers)) - 1)
            for layers in backbone_incidence.values()
            if len(layers) >= 2)
        junction_excess = sum(max(0, count - 1)
                              for count in incidence.values())
        routed_pitch = (float(pair["width"]) + float(pair["gap"])
                        if pair is not None else None)
        wide_junction_excess = 0
        if routed_pitch is not None:
            for (ref, _layer), count in incidence.items():
                port = ports.get(ref) or {}
                if (count <= 1 or not port.get("through")
                        or port.get("p") is None or port.get("n") is None):
                    continue
                if _dist(port["p"], port["n"]) > 2.0 * routed_pitch + 1e-9:
                    wide_junction_excess += count - 1
        articulations = sum(
            max(0, len(values) - 1)
            for ref, values in layers_by_ref.items()
            if ports[ref].get("through"))
        return (learned_refusals, learned_timeouts, -learned_successes,
                wide_junction_excess, backbone_discontinuities,
                junction_excess,
                interface_outer_cost,
                preferred_cost, articulations)

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
            "learned_refusals": int(score[0]),
            "learned_timeouts": int(score[1]),
            "learned_successes": int(-score[2]),
            "wide_pth_junction_excess": int(score[3]),
            "backbone_discontinuities": int(score[4]),
            "same_layer_junction_excess": int(score[5]),
            "interface_outer_layer_cost": int(score[6]),
            "preferred_layer_cost": int(score[7]),
            "pth_articulations": int(score[8]),
        },
        "backbone": {
            "betweenness_floor": float(backbone_floor),
            "edges": [
                [rows[index]["a"], rows[index]["b"]]
                for index in sorted(backbone_indices)],
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
                                incident_edges, embedding,
                                max_edge_fraction=0.45):
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
    if not math.isfinite(max_edge_fraction) or not 0 < max_edge_fraction <= 0.5:
        raise ValueError("junction edge fraction must be finite and in (0, 0.5]")
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
        # A physical neighbor bearing is not a legal copper heading.  These
        # portals include direct-only runways, so an arbitrary unit vector
        # makes every candidate fail the downstream octilinear guard before
        # global routing can begin.  Quantize the *virtual* launch (never a
        # footprint or existing copper); exact clearance still admits it.
        angle = round(math.atan2(direction[1], direction[0])
                      / (math.pi / 4.0)) * (math.pi / 4.0)
        direction = (math.cos(angle), math.sin(angle))
        reach = min(1.5, max(0.75, 0.12 * float(edge["length_mm"])))
        projected = ((other_center[0] - center[0]) * direction[0]
                     + (other_center[1] - center[1]) * direction[1])
        reach = min(reach, max_edge_fraction * projected / 2.0)
        return ((center[0] + direction[0] * reach,
                 center[1] + direction[1] * reach), reach)

    before, after = through[:2]
    before_center, before_reach = throat_center(before)
    after_center, after_reach = throat_center(after)
    nominal_separation = float(pair["width"]) + float(pair["gap"])
    port = plan["ports"].get(ref) or {}
    physical_separation = (_dist(port["p"], port["n"])
                           if port.get("p") is not None
                           and port.get("n") is not None else 0.0)
    # A wide, interleaved connector pin field needs a little more clearance at
    # a multidrop T/corner than a straight controlled-impedance pair.  Keep
    # that manufacturing margin inside the package-native junction cell; every
    # board-scale edge tapers back to the nominal pair pitch.  This is derived
    # from endpoint geometry, not connector identity, and is deliberately
    # bounded so a large terminal pitch cannot make the whole bus wide.
    junction_pair_scale = (
        1.25 if physical_separation > 2.0 * nominal_separation else 1.0)
    offset = nominal_separation * junction_pair_scale / 2.0
    ribbons = _offset_centerline([before_center, center, after_center], offset)
    if ribbons is None:
        return value
    left, right = ribbons
    sign = int(value.get("embedding_sign", 1))
    p_path, n_path = ((right, left) if sign >= 0 else (left, right))
    value["p"], value["n"] = p_path[1], n_path[1]
    value["junction_pair_scale"] = junction_pair_scale
    value["junction_pair_spacing_mm"] = round(2.0 * offset, 6)
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
        direction = (throat["center"][0] - center[0],
                     throat["center"][1] - center[1])
        direction_length = math.hypot(*direction)
        if direction_length > 1e-9:
            unit_direction = (direction[0] / direction_length,
                              direction[1] / direction_length)
            throat["_runway_origin"] = {
                key: tuple(throat[key]) for key in ("center", "p", "n")}
            runway_length = max(
                0.75, 2.0 * (2.0 * float(pair["width"])
                             + float(pair["gap"])),
                min(8.0, float(value.get("distance_mm", 0.0))))
            # These are virtual routing runways, not minimum copper/spacing
            # requirements.  Fixed millimetre lengths can project a local
            # portal past a nearby peer and force the trunk to turn back.
            # Reserve the peer's half of the corridor; exact shape and route
            # quality admission still decide whether a short cell is legal.
            peer = plan["ports"][other]["center"]
            projected = ((peer[0] - center[0]) * unit_direction[0]
                         + (peer[1] - center[1]) * unit_direction[1])
            runway_length = min(runway_length, max(
                0.0, max_edge_fraction * projected - direction_length))
            for key in ("center", "p", "n"):
                throat[key] = (
                    throat[key][0] + unit_direction[0] * runway_length,
                    throat[key][1] + unit_direction[1] * runway_length)
            throat["length_mm"] = round(
                float(throat.get("length_mm", 0.0)) + runway_length, 3)
            throat["clear_runway"] = True
            throat["route_heading"] = [
                round(unit_direction[0], 6),
                round(unit_direction[1], 6)]
        lane = (throat["n"][0] - throat["p"][0],
                throat["n"][1] - throat["p"][1])
        lane_length = math.hypot(*lane)
        throat["lane_axis"] = [
            round(lane[0] / lane_length, 6),
            round(lane[1] / lane_length, 6)]
    value["_junction_throats"] = throats
    value["junction_geometry"] = "mitered-offset-ribbon"
    value["max_edge_fraction"] = max_edge_fraction
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


def _multidrop_leaf_breakout_required(plan, pair, ref, layer,
                                      incident_edges):
    """Return whether a one-edge PTH terminal needs a proved local throat.

    A plated connector pad can articulate layers without a via, but that does
    not make a wide or staggered P/N pin field a useful board-scale routing
    endpoint.  When its physical member pitch is more than twice the routed
    pair centre spacing, first prove one bounded package-native fan-in and let
    the long edge connect throat-to-throat.  Compact pads continue to route
    directly, and SMD leaves remain owned by the normal transition/POFV
    machinery.  The predicate is entirely geometric and applies to any
    multidrop bus or connector family.
    """
    if len(incident_edges or ()) != 1:
        return False
    port = (plan.get("ports") or {}).get(ref) or {}
    if not port.get("through"):
        return False
    p_value, n_value = port.get("p"), port.get("n")
    if p_value is None or n_value is None:
        return False
    physical_pitch = _dist(tuple(p_value), tuple(n_value))
    routed_pitch = float(pair["width"]) + float(pair["gap"])
    return physical_pitch > 2.0 * routed_pitch + 1e-9


def _multidrop_orientation_owner(embedding, incident, ref, layer):
    """Return the planar component that owns a junction or attached leaf.

    The embedding contains real branch/through junctions.  A one-edge leaf on
    the same layer is nevertheless part of that physical ribbon and must use
    its lane order; otherwise the global edge is asked to swap P/N lanes with
    a long taper.  Leaves between two non-embedded endpoints remain free.
    """
    owner = embedding.get((ref, layer))
    if owner is not None:
        return owner
    rows = list(incident.get((ref, layer), ()))
    if len(rows) != 1:
        return None
    edge = rows[0]
    other = edge["b"] if edge["a"] == ref else edge["a"]
    return embedding.get((other, layer))


def _multidrop_leaf_throat_candidates(plan, pair, ref, incident_edges,
                                      max_candidates=48):
    """Return bounded, direction-aware portals for one wide PTH leaf.

    Leaf breakouts are a two-pin-field convergence problem, not a virtual
    multi-edge junction.  Reuse the coupled-portal geometry domain so lead
    length, lateral relief, reverse launch, and both lane orders are sampled
    consistently.  Each candidate is its own final throat; the board-scale
    edge connects to it without synthesizing a second local spoke.
    """
    if len(incident_edges or ()) != 1:
        return []
    edge = incident_edges[0]
    other = edge["b"] if edge["a"] == ref else edge["a"]
    ports = plan.get("ports") or {}
    port, peer = ports.get(ref) or {}, ports.get(other) or {}
    if any(value is None for value in (
            port.get("p"), port.get("n"), peer.get("p"), peer.get("n"))):
        return []
    portal_plan = _paired_portal_candidates(
        tuple(port["p"]), tuple(port["n"]),
        tuple(peer["p"]), tuple(peer["n"]),
        width=float(pair["width"]), gap=float(pair["gap"]))
    rows = []
    for sign in portal_plan["sign_order"]:
        rows.extend(portal_plan["by_sign"][sign]["start"])

    def rank(row):
        return (
            int(bool(row.get("reverse_launch"))),
            round(_dist(row["actual_p"], row["p"])
                  + _dist(row["actual_n"], row["n"]), 6),
            round(abs(float(row.get("lateral_mm", 0.0))), 6),
            int(row.get("sign", 1)),
        )

    fair = _fair_portal_screen_order(rows, rank)
    # The small junction beam must retain escape-depth coverage even as the
    # heading domain grows. Reserve one row per depth/launch class first;
    # additional headings consume only the remaining bounded slots.
    depth_seen, reserved, remainder = set(), [], []
    for row in fair:
        key = (row['lead_mm'], bool(row.get('reverse_launch')))
        if key not in depth_seen:
            depth_seen.add(key)
            reserved.append(row)
        else:
            remainder.append(row)
    sampled = (reserved + remainder)[:int(max_candidates)]
    output = []
    for row in sampled:
        value = dict(row)
        heading = tuple(float(component)
                        for component in row.get("route_heading", ()))
        heading_length = math.hypot(*heading) if len(heading) == 2 else 0.0
        if heading_length <= 1e-9:
            continue
        heading = (heading[0] / heading_length,
                   heading[1] / heading_length)
        # A package escape is not useful if the shared router immediately
        # re-enters the adjacent pad field.  Carry a short coupled runway as
        # part of the exact local cell, so later global search begins beyond
        # the package and with a physically realizable heading.
        runway_length = max(
            0.75, 2.0 * (2.0 * float(pair["width"])
                         + float(pair["gap"])))
        throat_center = (
            row["center"][0] + heading[0] * runway_length,
            row["center"][1] + heading[1] * runway_length)
        throat_p = (row["p"][0] + heading[0] * runway_length,
                    row["p"][1] + heading[1] * runway_length)
        throat_n = (row["n"][0] + heading[0] * runway_length,
                    row["n"][1] + heading[1] * runway_length)
        value.update({
            "ref": ref,
            "distance_mm": round(float(row.get("lead_mm", 0.0)), 3),
            "leaf_breakout": True,
            "embedding_sign": int(row.get("sign", 1)),
            "_junction_throats": {
                other: {
                    "center": throat_center,
                    "p": throat_p,
                    "n": throat_n,
                    "_runway_origin": {
                        "center": tuple(row["center"]),
                        "p": tuple(row["p"]),
                        "n": tuple(row["n"]),
                    },
                    "route_heading": [round(float(component), 6)
                                      for component in heading],
                    "length_mm": round(runway_length, 3),
                    "leaf_breakout": True,
                    "clear_runway": True,
                },
            },
        })
        output.append(value)
    return output


def _flow_bank_candidates(legs, stations, *, max_variants=8):
    """Bounded physical bank assignments; no polarity or package-role swap.

    Euclidean minimax is only the first proposal. A bank facing an obstructed
    corridor may be worse than the other bank of the same inline footprint.
    Retain the incumbent, each single-bank reversal, then all reversed, within
    an explicit cap instead of an exponential topology enumeration.
    """
    base = [tuple(tuple(p) for p in leg) for leg in legs]
    yield dict(legs=base, reversed_stations=[])
    if len(base) != len(stations)+1 or max_variants <= 1:
        return
    seen = {tuple(base)}
    choices = [(index,) for index in range(len(stations))]
    if len(stations)>1:
        choices.append(tuple(range(len(stations))))
    for indices in choices:
        trial = [list(row) for row in base]
        for index in indices:
            for incoming,outgoing in ((1,0),(3,2)):
                trial[index][incoming],trial[index+1][outgoing] = (
                    trial[index+1][outgoing],trial[index][incoming])
        trial = [tuple(row) for row in trial]
        key = tuple(trial)
        if key in seen:continue
        seen.add(key)
        yield dict(legs=trial,reversed_stations=[stations[i] for i in indices])
        if len(seen)>=max_variants:return


def _route_flow_bank_orders(board, pair, legs, stations, *, avoid=(),
                           verbose=False, pair_grid=True, deadline=None,
                           candidate_qualifier=None, restore_parent=None,
                           max_variants=8, alternative_budget_policy='complete-attempt'):
    """Native transaction over bank assignment and leg order, with rollback.

    Bank/order/primary-layer choices are alternatives, not mandatory pieces
    of one board. Do not multiply their counts into each required leg's
    effort. One complete attempt gets a bounded slice of the ORIGINAL lease;
    actual missing legs still share that slice, and all failed copper rolls
    back before a different hypothesis. No failed attempt resets its parent.
    """
    _inline_alternative_deadline(deadline,1,policy=alternative_budget_policy)
    base = {item.m_Uuid.AsString() for item in board.GetTracks()}
    variants = list(_flow_bank_candidates(legs,stations,max_variants=max_variants))
    attempts=[]
    final=None
    for index,variant in enumerate(variants):
        if _deadline_expired(deadline):break
        local_deadline = _inline_alternative_deadline(
            deadline,len(variants)-index,policy=alternative_budget_policy)
        started=time.monotonic()
        if verbose:
            print('[precision] inline bank candidate %d/%d reversed=%s' %
                  (index+1,len(variants),variant['reversed_stations']),file=sys.stderr)
        result=_route_flow_leg_orders(board,pair,variant['legs'],stations,
            avoid=avoid,verbose=verbose,pair_grid=pair_grid,deadline=local_deadline,
            alternative_budget_policy=alternative_budget_policy)
        if not result.get('refused') and candidate_qualifier is not None:
            result=candidate_qualifier(result)
        attempts.append(dict(reversed_stations=variant['reversed_stations'],
            elapsed_s=round(time.monotonic()-started,6),
            budget=dict(policy=alternative_budget_policy,parent_deadline=deadline,
                attempt_deadline=local_deadline,granted_s=(max(0.,local_deadline-started)
                    if local_deadline is not None else None)),
            refused=result.get('refused'),attempt=result))
        if not result.get('refused'):
            return dict(result,flow_bank_selection=variant['reversed_stations'],
                        flow_bank_attempts=attempts)
        _rollback_created_tracks(board,base)
        if restore_parent is not None:restore_parent()
        final=result
    return dict(final or dict(name=pair['name'],p=pair['p'],n=pair['n'],
        refused='inline bank search deadline exhausted'),flow_bank_attempts=attempts)


def _retained_inline_leg_contact(board, pair, endpoints, retained_track_uuids, *,
                                 deadline=None, max_items=8192):
    """Exact retained native contact, deliberately NOT pair qualification.

    A partial inline chain is not an entirely open pair. Rebuilding its
    already-connected leg wastes the shared lease and can overlay copper.
    Inspect only the immutable transaction-prefix copper and actual endpoint
    lands. Never infer contact from coordinates, airwires or a shortest-path
    estimate. The caller still receives the COMPLETE assembled pair's native
    ownership, graph, skew, coupling, field and return-path obligations.
    Unknown, ambiguous or one-sided contact cannot skip a coupled solve.
    """
    result = dict(complete=False, connected=False, members=[],
        physical_qualified=False, release_authority=False,
        whole_pair_physical_receiving_still_required=True)
    try:
        if _deadline_expired(deadline):
            raise ValueError('retained_inline_contact_deadline')
        names = {pair['p'], pair['n']}
        pads = [p for fp in board.GetFootprints() for p in fp.Pads()
                if p.GetNetname() in names]
        copper = [t for t in board.GetTracks() if t.GetNetname() in names
                  and t.m_Uuid.AsString() in retained_track_uuids]
        copper += [z for z in board.Zones()
                   if not z.GetIsRuleArea() and z.GetNetname() in names]
        if not 1 <= len(pads) <= max_items or len(pads) + len(copper) > max_items:
            raise ValueError('bounded_retained_inline_inventory_required')
        graph = pcbnew.CONNECTIVITY_DATA()
        for item in [*pads, *copper]:
            if _deadline_expired(deadline) or not graph.Add(item):
                raise ValueError('retained_inline_native_graph_unknown')
        for net, start, end in ((pair['p'], endpoints[0], endpoints[1]),
                                (pair['n'], endpoints[2], endpoints[3])):
            def terminal(xy):
                at = tuple(_v(*xy))
                matches = [p for p in pads if p.GetNetname() == net
                           and tuple(p.GetPosition()) == at]
                if len(matches) != 1:
                    raise ValueError('unique_retained_inline_terminal_required')
                return matches[0]
            first, last = terminal(start), terminal(end)
            reached = {first.m_Uuid.AsString()} | {
                i.m_Uuid.AsString() for i in graph.GetConnectedItems(first)}
            result['members'].append(dict(net=net,
                source_uuid=first.m_Uuid.AsString(), destination_uuid=last.m_Uuid.AsString(),
                connected=last.m_Uuid.AsString() in reached))
        if _deadline_expired(deadline):
            raise ValueError('retained_inline_contact_final_deadline')
        result.update(complete=True,
            connected=all(row['connected'] for row in result['members']))
    except Exception as exc:
        result['reason'] = type(exc).__name__ + ':' + str(exc)
    return result


def _route_flow_leg_orders(board, pair, legs, stations, *, avoid=(),
                           verbose=False, pair_grid=True, deadline=None,
                           max_orders=3, future_launch_mm=1.2,
                           alternative_budget_policy='complete-attempt'):
    """Bounded conflict-directed ordering of one atomic inline pair chain.

    A proved first leg can obstruct the second with its signal/return vias.
    Retry the refused leg first on the original copper, not on an abandoned
    partial route. Pre-existing station ties and protected routes survive;
    all copper created by a failed order is removed, including GND returns.
    Final whole-pair geometry, ownership and electrical gates remain external.
    """
    _inline_alternative_deadline(deadline,1,policy=alternative_budget_policy)
    base = {item.m_Uuid.AsString() for item in board.GetTracks()}
    schedule = _scheduled_flow_legs(board, pair, legs)
    difficulty = {index:score for index, _ends, score in schedule}
    attempts, tried = [], set()
    final = None
    order_limit=max(1,int(max_orders))
    for order_index in range(order_limit):
        negotiated = order_index >= 2
        if negotiated:
            # Guessed sibling launch rectangles are proposals, not native
            # copper. After both reserved orders fail, prove the short local
            # prerequisite first and make its successor respect real copper.
            # Both legs remain one atomic transaction with whole-pair signoff.
            schedule = sorted(schedule,key=lambda row:(
                _dist(row[1][0],row[1][1])+_dist(row[1][2],row[1][3]),row[0]))
        order = tuple(row[0] for row in schedule)
        key = (order,negotiated)
        if key in tried or _deadline_expired(deadline):
            break
        tried.add(key)
        order_deadline = _inline_alternative_deadline(
            deadline,order_limit-order_index,policy=alternative_budget_policy)
        reports, failure = {}, None
        pending = []
        for index, endpoints, score in schedule:
            retained = _retained_inline_leg_contact(board, pair, endpoints, base,
                deadline=order_deadline)
            if retained.get('complete') is True and retained.get('connected') is True:
                reports[index] = dict(name=pair['name'], p=pair['p'], n=pair['n'],
                    route_mode='retained-inline-native-contact', segments=0,
                    solver_local_qualified=False, retained_native_contact=retained,
                    whole_pair_physical_receiving_still_required=True)
            else:
                pending.append((index, endpoints, score))
        # Already-connected legs retain their actual prefix copper as hard
        # obstacles. They need neither another route nor prospective launch
        # rectangles, and must not consume a share of the pending solve lease.
        schedule_for_solve = pending
        for scheduled_index, (index, endpoints, _score) in enumerate(schedule_for_solve):
            leg_deadline = (_fair_subdeadline(order_deadline, len(schedule_for_solve)-scheduled_index)
                            if order_deadline is not None else None)
            future = []
            for pending_index, pending_endpoints, _ in (
                    () if negotiated else schedule_for_solve[scheduled_index+1:]):
                future.extend(_pair_leg_launch_reservations(
                    pending_endpoints, pair, launch_mm=future_launch_mm,
                    clearance_mm=0.20, leg_index=pending_index))
            from cec_pair_native_layer_order import rank as rank_native_layers
            layer_portfolio=rank_native_layers(board,pair,endpoints)
            layer_attempts=[];trial=None
            for layer_index,choice in enumerate(layer_portfolio):
                if _deadline_expired(leg_deadline):break
                layer_deadline=_inline_alternative_deadline(
                    leg_deadline,len(layer_portfolio)-layer_index,policy=alternative_budget_policy)
                layer_started=time.monotonic()
                layer_base={t.m_Uuid.AsString() for t in board.GetTracks()}
                trial=route_coupled_pair(board,pair,verbose=verbose,
                    avoid=tuple(avoid or ())+tuple(future),endpoints=endpoints,
                    pair_grid=pair_grid,layer=choice['layer'],minimum_coupled_fraction=.35,
                    deadline=layer_deadline)
                if not trial.get('refused'):break
                rolled_back=_rollback_created_tracks(board,layer_base)
                layer_attempts.append(dict(layer=choice['layer'],reason=trial['refused'],attempt=trial,
                    budget=dict(policy=alternative_budget_policy,parent_deadline=leg_deadline,
                        attempt_deadline=layer_deadline,granted_s=(max(0.,layer_deadline-layer_started)
                            if layer_deadline is not None else None)),
                    native_port_access=choice,rollback_created_items=rolled_back,
                    deadline_exhausted=bool(trial.get('search_budget_exhausted') or _deadline_expired(layer_deadline))))
            if trial is None or trial.get('refused'):
                if not layer_attempts:
                    exhausted=_deadline_expired(leg_deadline)
                    layer_attempts=[dict(layer=None,reason=('inline layer portfolio deadline exhausted'
                        if exhausted else 'no profile-referenced inline route layer'),deadline_exhausted=exhausted)]
                failure = dict(leg=index+1, total_legs=len(legs),
                    layers=layer_attempts)
                failure['deadline_exhausted'] = any(q['deadline_exhausted'] for q in layer_attempts)
                break
            reports[index] = dict(trial, future_inline_launch_reservations=len(future),
                native_layer_portfolio=layer_portfolio,prior_layer_refusals=layer_attempts)
        attempt = dict(order=[i+1 for i in order], completed_legs=sorted(i+1 for i in reports),
                       alternative_budget_policy=alternative_budget_policy,
                       attempt_deadline=order_deadline,
                       completed_leg_evidence=[dict(leg=i+1, scope="inline-leg-only",
                           release_authority=False,
                           solver_local_qualified=row.get('solver_local_qualified', True),
                           evidence={key:row[key] for key in (
                               "name", "p", "n", "route_mode", "segments", "length_mm",
                               "coupled_coverage_pct", "graph_geometry", "route_quality",
                               "pofv", "return_route_backtrack", "retained_native_contact",
                               "whole_pair_physical_receiving_still_required") if key in row})
                           for i,row in sorted(reports.items())],
                       refusal=failure,internal_reservation_policy=(
                           'actual-copper-atomic' if negotiated else 'prospective-launch'))
        attempts.append(attempt)
        if failure is None:
            rows = [reports[i] for i in range(len(legs))]
            result = dict(rows[0])
            result.update(route_mode='flow-through', flow_through=stations, legs=rows,
                flow_leg_order=list(attempt['order']), flow_order_attempts=attempts,
                flow_leg_difficulty={str(i+1):list(difficulty[i]) for i in sorted(difficulty)},
                segments=sum(r.get('segments',0) for r in rows),
                length_mm=round(sum(r.get('length_mm',0.) for r in rows),2),
                coupled_len_mm=round(sum(r.get('coupled_len_mm',0.) for r in rows),2))
            return result
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base:
                _discard_items(board,[item])
        final = dict(name=pair['name'],p=pair['p'],n=pair['n'],flow_through=stations,
            refused='flow-through leg %d/%d via %s refused: %s' % (
                failure['leg'],len(legs),','.join(stations),failure['layers'][0]['reason']),
            flow_leg_order=list(attempt['order']),flow_leg_refusal=failure,
            flow_leg_budget_exhausted=failure['deadline_exhausted'],
            flow_order_attempts=attempts,
            flow_leg_difficulty={str(i+1):list(difficulty[i]) for i in sorted(difficulty)})
        if not reports:
            # A first-leg failure under future-launch reservations is not an
            # intrinsic escape failure: the pending leg owns those resources.
            # Let that owner route first once, within the same finite budget.
            if len(schedule) < 2: break
            schedule = schedule[1:] + schedule[:1]
            continue
        failed_index = failure['leg']-1
        schedule = sorted(schedule, key=lambda row: row[0] != failed_index)
    return final or dict(name=pair['name'],p=pair['p'],n=pair['n'],
                        refused='inline order search deadline exhausted',
                        flow_order_attempts=attempts)


def _paired_portal_lane_compatible(start, end):
    """Return whether two directed throats preserve P/N ribbon polarity.

    ``route_heading`` points from each package/junction into its board-scale
    edge.  Traversal leaves the start along that vector and reaches the end
    against its vector.  P/N must occupy the same signed side of both traversal
    tangents; opposite signs would require a copper crossover somewhere along
    the shared ribbon.
    """
    start_heading = tuple(start.get("route_heading") or ())
    end_outward = tuple(end.get("route_heading") or ())
    if len(start_heading) != 2 or len(end_outward) != 2:
        return True

    def side(port, tangent):
        lane = (port["n"][0] - port["p"][0],
                port["n"][1] - port["p"][1])
        return tangent[0] * lane[1] - tangent[1] * lane[0]

    start_side = side(start, start_heading)
    end_side = side(end, (-end_outward[0], -end_outward[1]))
    if abs(start_side) <= 1e-9 or abs(end_side) <= 1e-9:
        return False
    return start_side * end_side > 0.0


def _multidrop_junction_candidates(board, plan, ref, pair,
                                   max_candidates=48):
    """Return bounded paired junctions beside one internal bus terminal.

    An internal multidrop terminal needs one pad escape, not one escape per
    incident tree edge.  Candidate junctions are derived from the physical
    neighbor vectors and board interior, then retain the P/N pad ordering or a
    normal-to-launch coupled ordering.  Wide one-edge terminals use
    :func:`_multidrop_leaf_throat_candidates` instead.  No reference or
    connector family is special-cased; exact copper guards decide which
    candidate is usable.
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
    # A finite candidate budget must cover the physical escape depth domain.
    # Returning from the distance-major generator filled every slot at the
    # shortest radius, so a dense connector could report dozens of exact
    # refusals without ever inspecting the ordinary longer breakout just past
    # its pad bank.  Round-robin by distance retains direction/lane ordering
    # within each bucket while reserving comparable capacity for every depth.
    by_distance = {}
    for row in candidates:
        by_distance.setdefault(float(row["distance_mm"]), []).append(row)
    sampled = []
    ordered_distances = sorted(by_distance)
    for index in range(max((len(by_distance[value])
                            for value in ordered_distances), default=0)):
        for distance in ordered_distances:
            bucket = by_distance[distance]
            if index < len(bucket):
                sampled.append(bucket[index])
                if len(sampled) >= int(max_candidates):
                    return sampled
    return sampled


def _pair_via_clearance_issues(board, pair, created_ids):
    """Check actual annular lands against the opposite member on every layer.

    Pair centreline distance is not a via-clearance proof. Include authored
    partner pads/copper and later emitted ribbons, but report only conflicts
    involving transaction-created copper. Plane antipads remain the filler
    and independent final DRC's responsibility.
    """
    scope = set(created_ids or ())
    nets = {pair['p'], pair['n']}
    copper = [item for item in board.GetTracks() if item.GetNetname() in nets]
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
            if pad.GetNetname() in nets]
    issues, seen = [], set()
    clearance = max(0, _nm(float(pair.get('clearance', 0.20))) - 1)
    for via in copper:
        if via.GetClass() != 'PCB_VIA':
            continue
        via_id = via.m_Uuid.AsString()
        for other in copper + pads:
            other_id = other.m_Uuid.AsString()
            if (other.GetNetname() == via.GetNetname()
                    or not ({via_id, other_id} & scope)):
                continue
            shared = set(via.GetLayerSet().CuStack()) & set(other.GetLayerSet().CuStack())
            for layer_id in sorted(shared):
                key = (tuple(sorted((via_id, other_id))), layer_id)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    collision = via.GetEffectiveShape(layer_id).Collide(
                        other.GetEffectiveShape(layer_id), clearance)
                except Exception as exc:
                    issues.append(dict(type='member_via_shape_error', via_uuid=via_id,
                                       other_uuid=other_id, error=str(exc)))
                    continue
                if collision:
                    issues.append(dict(type='member_via_clearance', via_uuid=via_id,
                        other_uuid=other_id, via_net=via.GetNetname(),
                        other_net=other.GetNetname(), other_kind=other.GetClass(),
                        layer=board.GetLayerName(layer_id),
                        clearance_mm=round(clearance / MM, 6)))
    return issues


def _pair_graph_geometry(board, pair, created_ids, physical_only=False,
                         strict_ids=None):
    """Check pair-member crossings and spacing across a routed bus graph.

    The point-to-point router checks each leg in isolation.  A multidrop graph
    additionally needs a whole-graph authority so a later leg cannot cross an
    earlier sibling while both nets are excluded from foreign-copper checks.
    Shared same-net junction endpoints are intentional and are never waived
    between the two different members. ``strict_ids`` identifies a candidate
    trunk during incremental construction: any interaction involving that
    trunk holds the full electrical gap, while unchanged local fanouts hold
    the native physical clearance. Their final coupling/skew/DRC signoff is
    still mandatory. Without this distinction an already-proved fine-pitch
    terminal escape rejects every unrelated trunk on every layer.
    """
    scope = set(created_ids or ())
    by_net = {pair["p"]: [], pair["n"]: []}
    material_issues = []
    for item in board.GetTracks():
        if (item.m_Uuid.AsString() in scope
                and item.GetNetname() in by_net
                and item.GetClass() in ("PCB_TRACK", "PCB_VIA")):
            start = (item.GetPosition() if item.GetClass() == "PCB_VIA"
                     else item.GetStart())
            end = start if item.GetClass() == "PCB_VIA" else item.GetEnd()
            land_width = (max(item.GetWidth(layer) for layer in
                              item.GetLayerSet().CuStack())
                          if item.GetClass() == "PCB_VIA" else item.GetWidth())
            if not cec_fr._edge_leg_clear(
                    board, start, end, land_width // 2):
                material_issues.append({
                    "type": "board_material_clearance",
                    "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
                    "segment_mm": [[start.x/MM, start.y/MM],
                                   [end.x/MM, end.y/MM]],
                    "copper_radius_mm": land_width / (2*MM),
                    "edge_clearance_mm": 0.5,
                })
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
    issues = material_issues + _pair_via_clearance_issues(board, pair, scope)
    # The main coupled-route solver must hold the electrical pair gap.  The
    # final duplicate-pad closure, however, necessarily necks down to the
    # package pitch and is admitted by physical copper clearance.  Do not
    # reject a legal connector escape merely because its land pitch is smaller
    # than the controlled-impedance centre spacing; do still reject every P/N
    # crossing or copper overlap (the failure this whole-graph audit guards).
    minimum = ((float(pair["width"]) if physical_only else
                float(pair["width"]) + float(pair["gap"])) - 1e-6)
    strict_scope = None if strict_ids is None else set(strict_ids)
    unchanged_minimum = (float(pair["width"])
                         + _pair_clearance(board, pair, None) - 1e-6)
    for p_row in by_net[pair["p"]]:
        for n_row in by_net[pair["n"]]:
            if p_row["layer"] != n_row["layer"]:
                continue
            distance = _seg_seg_dist(
                p_row["a"], p_row["b"], n_row["a"], n_row["b"])
            crossing = _seg_cross(
                p_row["a"], p_row["b"], n_row["a"], n_row["b"])
            required = minimum
            if (not physical_only and strict_scope is not None
                    and not ({p_row["uuid"], n_row["uuid"]} & strict_scope)):
                required = unchanged_minimum
            if crossing or distance + 1e-7 < required:
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
                    "minimum_mm": round(required, 6),
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
                       minimum_end_coherence=None,
                       allow_terminal_gap_taper=False,
                       strict_pair_gap=False,
                       foreign_shape_cache=None,
                       partner_shape_cache=None,
                       blocker_shape_cache=None,
                       complete_pair_context=None,
                       terminal_via_diameter_mm=None):
    """Lay one short paired terminal escape without invoking global A*.

    Multidrop candidate selection may evaluate several nearby junctions.  A
    full-board grid search for every 2--6 mm terminal stub is both wasteful and
    opaque.  This local solver enumerates bounded chamfered dogbones, applies
    the exact edge/foreign-pad/partner-pad guards, and emits copper only after
    the two members pass their joint crossing and spacing test.

    Optional future terminal lands occupy the two destination points. They
    constrain the opposite member during enumeration, not just after a
    trace-only winner has been selected. This is a keepout, never permission
    to emit a via: native process/all-layer/return-field admission still runs.
    """
    if terminal_via_diameter_mm is not None:
        terminal_via_diameter_mm = float(terminal_via_diameter_mm)
        if (not math.isfinite(terminal_via_diameter_mm)
                or terminal_via_diameter_mm <= 0):
            raise ValueError('invalid terminal via diameter')
    clearance = _pair_clearance(board, pair, clearance)
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
    # Callers can reuse immutable package-pad shapes across portal trials, but
    # they emit/retire pair copper between those trials. Opposite-member tracks
    # and vias therefore belong to THIS local solve only. A shared track cache
    # otherwise ignores newly emitted copper or keeps rolled-back ghost copper.
    partner_track_cache = {}
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
        key = ("pads", int(layer_id), int(net_code))
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

    def partner_track_shapes(net_code):
        """Index established opposite-member copper once per local solve.

        Multidrop routing invokes this guard thousands of times while
        screening finite portal/dogbone candidates.  Rewalking every board
        track on every leg made later edges consume their wall-clock budget in
        clearance bookkeeping even when earlier copper was spatially remote.
        Candidate copper is emitted only after both members pass admission,
        so the transaction-start snapshot is the correct obstacle authority.
        """
        key = ("tracks", int(layer_id), int(net_code))
        if key in partner_track_cache:
            return partner_track_cache[key]
        rows = []
        for item in getattr(board, "GetTracks", lambda: ())():
            if item.GetNetCode() != int(net_code):
                continue
            try:
                if item.Type() == pcbnew.PCB_VIA_T:
                    if layer_id not in item.GetLayerSet().CuStack():
                        continue
                elif item.GetLayer() != layer_id:
                    continue
                shape = item.GetEffectiveShape(layer_id)
                rows.append((shape, shape.BBox()))
            except Exception:                         # noqa: BLE001
                continue
        if terminal_via_diameter_mm is not None:
            point = p_end if int(net_code) == int(p_code) else n_end
            # Get the generic native shape interface. SHAPE_CIRCLE's Python
            # Collide overload only accepts SEG, not SHAPE_SEGMENT; passing
            # that derived proxy into the shared snapshot would skip it.
            # This detached object contributes geometry only, never a hole.
            land = pcbnew.PCB_VIA(board)
            land.SetPosition(_v(*point))
            land.SetWidth(_nm(terminal_via_diameter_mm))
            land.SetViaType(pcbnew.VIATYPE_THROUGH)
            land.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            shape = land.GetEffectiveShape(layer_id)
            rows.append((shape, shape.BBox()))
        indexed = cec_fr._bucket_foreign_shapes(rows)
        partner_track_cache[key] = indexed
        return indexed

    def member_terms(a, b, partner_code):
        # Shared exact predicates: diagnostics evaluate all terms, whereas
        # search may stop on the first refusal without collecting identities.
        yield 'board_edge', cec_fr._edge_leg_clear(
            board, _v(*a), _v(*b), width_nm // 2, edge_mm=0.5)
        # A local escape is part of the same owner order as its trunk. Reject
        # occupied corridors while enumerating alternatives, not only after
        # the shortest otherwise-clear path has already won the local beam.
        yield 'reservation', not bool(_crosses_avoid((a, b), avoid, width))
        yield 'foreign_copper', cec_fr._snapshot_foreign_clear(
            _v(*a), _v(*b), width_nm, clearance_nm,
            foreign_zones, foreign_copper)
        yield 'partner_pad', _partner_pads_clear(
            board, a, b, width_nm, layer_id, partner_code, clearance_nm,
            partner_shapes=partner_shapes(partner_code))
        # Earlier opposite-member copper may run alongside, never through,
        # this leg. The transaction-start snapshot is still authoritative.
        yield 'partner_copper', _partner_tracks_clear(
            board, a, b, width_nm, layer_id, partner_code,
            clearance_nm=clearance_nm,
            partner_shapes=partner_track_shapes(partner_code))

    def member_admission(a, b, partner_code):
        if a == b:
            return {"board_edge": True, "foreign_copper": True,
                    "partner_pad": True, "partner_copper": True,
                    "reservation": True, "ok": True}
        value = dict(member_terms(a, b, partner_code))
        if not value["foreign_copper"]:
            identified = blocker_shapes()
            if identified is not None:
                value["foreign_blockers"] = \
                    cec_fr._snapshot_foreign_blockers(
                        _v(*a), _v(*b), width_nm, clearance_nm,
                        identified[0], identified[1])
        # Evidence is not an admission term.
        value["ok"] = (value["board_edge"]
                       and value["reservation"]
                       and value["foreign_copper"]
                       and value["partner_pad"]
                       and value["partner_copper"])
        return value

    from functools import lru_cache

    @lru_cache(maxsize=4096)
    def cached_member_clear(a, b, partner_code):
        # Exact coordinates and partner identity; no rounding or looser
        # clearance. This cache exists only during this immutable local solve,
        # never across board mutations, different pair policies, or layers.
        return a == b or all(value for _name, value in
                             member_terms(a, b, partner_code))

    def member_clear(a, b, partner_code):
        return cached_member_clear(tuple(a), tuple(b), int(partner_code))

    p_direct, n_direct = [p_start, p_end], [n_start, n_end]
    p_direct_admission = member_admission(p_start, p_end, n_code)
    n_direct_admission = member_admission(n_start, n_end, p_code)
    direct_crossing_free = _polys_no_cross(p_direct, n_direct)
    direct_octilinear = (_polyline_is_octilinear(p_direct)
                         and _polyline_is_octilinear(n_direct))
    strict_terminal_gap = bool(
        strict_pair_gap
        or (float(minimum_coupled_fraction) > 0.0
            and not allow_terminal_gap_taper))
    direct_spacing_ok = _pair_min_clear(
        p_direct, n_direct, -1, -1, width, gap,
        strict_pair_gap=strict_terminal_gap)
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
    direct_coherence_ok = (minimum_end_coherence is None or
        _pair_end_coherence(p_direct, n_direct) + 1e-9 >= float(minimum_end_coherence))
    admission = {
        "direct": {
            "p": p_direct_admission,
            "n": n_direct_admission,
            "crossing_free": direct_crossing_free,
            "octilinear": direct_octilinear,
            "pair_spacing": direct_spacing_ok,
            "heading_alignment": round(direct_heading_alignment, 6),
            "heading_compatible": direct_heading_ok,
            "coherence_compatible": direct_coherence_ok,
        },
        "detour": {},
        "paired_ribbon": {},
    }
    solved = None
    paired_ribbon = None
    ribbon_rejections = []
    ribbon_witness_limit = 4
    ribbon_physical_prefilter_refusals = 0
    def ribbon_domain():
        if not allow_detour:
            return
        yield from _short_pair_ribbon_candidates(
            pair, p_start, p_end, n_start, n_end)
        # Preserve successful fast paths. Only expand this correlated domain
        # when the historical straight-axis menu was rejected.
        import cec_pair_ribbon
        existing = cec_pair_skew.from_board(board, pair)
        yield from cec_pair_ribbon.candidates(
            pair, p_start, p_end, n_start, n_end, deadline=deadline,
            existing_signed_skew_mm=existing['p_length_mm']-existing['n_length_mm'],
            max_skew=float(pair.get('skew_limit_mm',
                3.81 if pair.get('kind') == 'usb' else 4.0)))

    ribbon_counts = collections.Counter()
    for ribbon in ribbon_domain():
        if _deadline_expired(deadline):
            break
        ribbon_counts[ribbon.get('geometry', 'legacy-straight-axis')] += 1
        p_points, n_points = ribbon["p"], ribbon["n"]
        # Once the bounded detailed witnesses are full, an exact physical
        # refusal needs no second walk of every leg or blocker identity.
        # Reuse the same immutable-solve clearance predicates/cache as the
        # joint escape search. This can only reject an already-illegal row;
        # every surviving proposal still receives all existing admission.
        if len(ribbon_rejections) >= ribbon_witness_limit and (
                not all(member_clear(a, b, n_code)
                        for a, b in zip(p_points, p_points[1:]))
                or not all(member_clear(a, b, p_code)
                           for a, b in zip(n_points, n_points[1:]))):
            ribbon_physical_prefilter_refusals += 1
            continue
        octilinear = (_polyline_is_octilinear(p_points)
                      and _polyline_is_octilinear(n_points))
        p_admissions = [member_admission(a, b, n_code)
                        for a, b in zip(p_points, p_points[1:])]
        n_admissions = [member_admission(a, b, p_code)
                        for a, b in zip(n_points, n_points[1:])]
        p_clear = all(row["ok"] for row in p_admissions)
        n_clear = all(row["ok"] for row in n_admissions)
        crossing_free = (_polys_no_cross(p_points, n_points)
                         and not _polyline_has_self_crossing(p_points)
                         and not _polyline_has_self_crossing(n_points))
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
            and octilinear
            and turn_quality
            and ribbon_heading + 1e-9 >= minimum_heading_alignment
            and (minimum_end_coherence is None or
                 _pair_end_coherence(p_points, n_points) + 1e-9
                 >= float(minimum_end_coherence)))
        public = {key: value for key, value in ribbon.items()
                  if key not in ("p", "n")}
        public.update({
            "p_clear": p_clear, "n_clear": n_clear,
            "crossing_free": crossing_free,
            "octilinear": octilinear,
            "pair_spacing": pair_spacing,
            "reservation": reservation,
            "heading_alignment": round(ribbon_heading, 6),
            "handoff_member_coherence": round(
                _pair_end_coherence(p_points, n_points), 6),
            "minimum_opening_angle_deg": round(minimum_opening, 6),
            "turn_quality": turn_quality,
            "accepted": accepted,
        })
        # Preserve the first exact failing legs.  A Boolean-only rejection
        # makes a legalizer blind to whether the funnel hit the board edge,
        # foreign copper, the sibling pad, or already-routed sibling copper.
        # Coordinates plus the exact admission terms are compact enough
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
                        "partner_copper", "foreign_blockers", "reservation")
                       if key in row},
                })
            if failures:
                public[f"{member}_failures"] = failures[:3]
        if accepted:
            solved = (p_points, n_points)
            paired_ribbon = public
            break
        if len(ribbon_rejections) < ribbon_witness_limit:
            ribbon_rejections.append(public)
    admission["paired_ribbon"] = {
        "selected": paired_ribbon,
        "rejected": ribbon_rejections,
        "evaluated_by_geometry": dict(ribbon_counts),
        "physical_prefilter_refusals": ribbon_physical_prefilter_refusals,
    }
    if solved is not None:
        pass
    elif (p_direct_admission["ok"]
            and n_direct_admission["ok"]
            and direct_crossing_free and direct_spacing_ok
            and direct_octilinear
            and direct_heading_ok and direct_coherence_ok):
        solved = (p_direct, n_direct)
    elif allow_detour:
        # A locally acceptable mismatch can compound earlier tree/flow legs.
        # Rank this bounded escape against copper already on the native board,
        # preserving its sign so an opposite imbalance can compensate it.
        # This is a search objective, not admission: normalization and the
        # unchanged saved-board whole-pair checks remain authoritative.
        existing_lengths = cec_pair_skew.from_board(board, pair)
        existing_signed_skew = (existing_lengths['p_length_mm']
                                - existing_lengths['n_length_mm'])
        solved = _joint_endpoint_escape(
            p_start, n_start, p_end, n_end, width=width, gap=gap,
            p_segment_clear=lambda a, b: member_clear(a, b, n_code),
            n_segment_clear=lambda a, b: member_clear(a, b, p_code),
            max_detour=max(_pair_escape_budget(p_start, n_start),
                           _pair_escape_budget(p_end, n_end)),
            max_skew=float(pair.get(
                "skew_limit_mm",
                3.81 if pair.get("kind") == "usb" else 4.0)),
            existing_signed_skew_mm=existing_signed_skew,
            max_member_paths=int(detour_member_paths),
            preferred_end_direction=preferred_end_direction,
            minimum_end_heading_alignment=minimum_heading_alignment,
            minimum_end_coherence=minimum_end_coherence,
            strict_pair_gap=strict_terminal_gap,
            complete_pair_context=complete_pair_context,
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
    if (minimum_end_coherence is not None and
            _pair_end_coherence(p_points, n_points) + 1e-9 < float(minimum_end_coherence)):
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "paired terminal members lack a coherent handoff",
                "admission": admission}
    if (not _polyline_is_octilinear(p_points)
            or not _polyline_is_octilinear(n_points)):
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": "paired terminal path contains a non-octilinear segment",
            "admission": admission,
        }
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
    if (strict_terminal_gap
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
    p_handoff = _path_end_heading(p_points)
    n_handoff = _path_end_heading(n_points)
    handoff_coherence = (
        p_handoff[0] * n_handoff[0] + p_handoff[1] * n_handoff[1]
        if p_handoff is not None and n_handoff is not None else -1.0)
    handoff_route_heading = None
    if p_handoff is not None and n_handoff is not None \
            and handoff_coherence >= -1e-9:
        combined = (p_handoff[0] + n_handoff[0],
                    p_handoff[1] + n_handoff[1])
        if math.hypot(*combined) > 1e-9:
            directions = ((1, 0), (1, 1), (0, 1), (-1, 1),
                          (-1, 0), (-1, -1), (0, -1), (1, -1))
            direction = max(directions, key=lambda row: (
                combined[0] * row[0] + combined[1] * row[1])
                / math.hypot(*row))
            direction_length = math.hypot(*direction)
            handoff_route_heading = (
                direction[0] / direction_length,
                direction[1] / direction_length)
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
        "handoff_member_headings": {
            "p": ([round(value, 6) for value in p_handoff]
                  if p_handoff is not None else None),
            "n": ([round(value, 6) for value in n_handoff]
                  if n_handoff is not None else None),
        },
        "handoff_member_coherence": round(handoff_coherence, 6),
        "handoff_route_heading": (
            [round(value, 6) for value in handoff_route_heading]
            if handoff_route_heading is not None else None),
        "terminal_gap_policy": (
            "symmetric-pitch-taper" if paired_ribbon is not None else
            "pad-pitch-taper" if allow_terminal_gap_taper else
            "strict-nominal"),
        "local_search": {
            "used_detour": solved != (p_direct, n_direct),
            "paired_ribbon": paired_ribbon,
            "paired_ribbon_rejected": ribbon_rejections[:4],
            "paired_ribbon_evaluated_by_geometry": dict(ribbon_counts),
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
                _discard_items(board,[item])

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


def _multidrop_edge_betweenness(edges):
    """Return the number of terminal pairs whose tree path uses each edge.

    A professional multidrop route establishes the shared backbone before
    attaching low-fanout drops.  Euclidean length and layer-domain size do not
    identify that backbone: a short single-layer leaf can detour across the
    entire future trunk when routed first.  For a tree, removing an edge splits
    the terminals into sets of size ``a`` and ``b``; ``a*b`` is its exact path
    betweenness and is independent of reference names or board identity.
    """
    rows = [dict(row) for row in (edges or ())]
    adjacency = {}
    for row in rows:
        a, b = str(row["a"]), str(row["b"])
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    total = len(adjacency)
    scores = {}
    for row in rows:
        a, b = str(row["a"]), str(row["b"])
        seen = {a}
        frontier = [a]
        while frontier:
            node = frontier.pop()
            for neighbor in adjacency.get(node, ()):
                if ((node == a and neighbor == b)
                        or (node == b and neighbor == a)
                        or neighbor in seen):
                    continue
                seen.add(neighbor)
                frontier.append(neighbor)
        left = len(seen)
        scores[tuple(sorted((a, b)))] = left * max(0, total - left)
    return scores


def _multidrop_edge_interface_difficulty(edge, ports):
    """Rank PTH-to-PTH transitions that transform the pair pin field.

    Plated terminals can move a pair between layers without vias, but a link
    between dissimilar connector pin fields still owns a scarce geometric
    escape.  If it is postponed until after a long backbone, the existing
    trunk can consume the only legal pitch/orientation transition and leave
    too little bounded retry time.  This metric is purely package geometry;
    it generalizes to headers, jacks, terminal blocks, and future connectors.
    """
    a = (ports or {}).get(edge.get("a")) or {}
    b = (ports or {}).get(edge.get("b")) or {}
    pth_transition = bool(a.get("through") and b.get("through"))

    def field(port):
        p = tuple(port.get("p") or ())
        n = tuple(port.get("n") or ())
        if len(p) != 2 or len(n) != 2:
            return 0.0, None
        pitch = _dist(p, n)
        axis = ((n[0] - p[0]) / pitch, (n[1] - p[1]) / pitch) \
            if pitch > 1e-9 else None
        return pitch, axis

    a_pitch, a_axis = field(a)
    b_pitch, b_axis = field(b)
    if not pth_transition or min(a_pitch, b_pitch) <= 1e-9:
        return {
            "pth_transition": pth_transition,
            "constrained": False,
            "score": 0.0,
            "pitch_ratio": None,
            "axis_mismatch": None,
        }
    pitch_ratio = max(a_pitch, b_pitch) / min(a_pitch, b_pitch)
    axis_mismatch = 0.0
    if a_axis is not None and b_axis is not None:
        axis_mismatch = 1.0 - min(1.0, abs(
            a_axis[0] * b_axis[0] + a_axis[1] * b_axis[1]))
    score = max(0.0, pitch_ratio - 1.0) + axis_mismatch
    return {
        "pth_transition": True,
        "constrained": bool(score > 0.10),
        "score": round(score, 6),
        "pitch_ratio": round(pitch_ratio, 6),
        "axis_mismatch": round(axis_mismatch, 6),
    }


def _multidrop_edge_attempt_seconds(edge, ports, *, forced=False):
    """Return a bounded edge budget proportional to escape difficulty."""
    if forced:
        return 90.0
    if _multidrop_edge_interface_difficulty(
            edge, ports).get("constrained"):
        return 60.0
    if len(edge.get("layers") or ()) == 1:
        return 60.0
    return 30.0


def _junction_continuation_rank(board, pair, plan, ref, junction, throats,
                                created_ids):
    """Rank an admitted star by copper already paid for and remaining reach.

    This is a search-order heuristic, not an admissible bound or acceptance
    waiver: future branches may overlap or need obstacle detours.  Measure
    both electrical members, not just the centreline or summed length, so a
    short P path cannot hide an unnecessarily long N escape.  Exact global
    geometry, coupling and detour admission still decide the transaction.
    """
    costs = {pair["p"]: 0.0, pair["n"]: 0.0}
    for item in board.GetTracks():
        if (item.m_Uuid.AsString() in created_ids
                and item.GetNetname() in costs
                and item.GetClass() != "PCB_VIA"):
            costs[item.GetNetname()] += item.GetLength() / MM
    # A short clear star can spend too much of the pair's separation budget.
    # Prefer less actually separated copper before the continuation estimate;
    # never inflate length just to improve a coupling percentage. Whole-tree
    # coupling, skew, detour and exact geometry remain independent gates.
    coverage = _pair_coupling_summary(board, pair, created_ids)
    uncoupled = max(costs.values()) * (1.0 - coverage['fraction'])
    for peer, throat in throats.items():
        port = plan["ports"][peer]
        for member in ("p", "n"):
            costs[pair[member]] += _dist(throat[member], port[member])
    values = list(costs.values())
    return (round(uncoupled, 6), round(max(values), 6), round(sum(values), 6),
            round(_dist(junction["center"], plan["ports"][ref]["center"]), 6))


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
    completed_edges = []
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
        plan, edges, pair=pair, forced_layers=forced_edge_layers,
        route_layer_evidence=route_layer_evidence)
    for edge, layer in zip(edges, layer_assignment["selected_layers"]):
        edge["selected_layer"] = layer
    embedding = _multidrop_planar_embedding(plan, edges)

    incident = {}
    for edge in edges:
        layer = edge["selected_layer"]
        for ref in (edge["a"], edge["b"]):
            incident.setdefault((ref, layer), []).append(edge)
    junction_keys = sorted(
        key for key, rows in incident.items()
        if (len(rows) >= 2
            or _multidrop_leaf_breakout_required(
                plan, pair, key[0], key[1], rows)))

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                _discard_items(board,[item])

    def budget_exhausted():
        return _deadline_expired(absolute_deadline)

    def edge_progress():
        """Return monotonic partial-tree completion before transaction rollback."""
        total = len(edges)
        completed = len(completed_edges)
        return {
            "completed_edge_count": completed,
            "total_edge_count": total,
            "remaining_edge_count": max(0, total - completed),
            "completed_edges": [list(edge) for edge in completed_edges],
        }

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
            **edge_progress(),
        }

    def candidate_throats(ref, layer, junction):
        return _multidrop_junction_throats(
            plan, pair, ref, layer, junction,
            incident[(ref, layer)], embedding)

    # Only this pair's copper mutates during local candidate screening.  Its
    # nets are excluded, so those probes may share exact foreign shapes.
    # After trunk routing starts, new GND return vias can be foreign obstacles
    # to a reselected star: do not reuse the prefilter snapshot there.
    star_foreign_cache, star_blocker_cache = {}, {}
    star_screening = True

    def emit_local_star(ref, layer, junction, *, allow_detour):
        """Emit one exact package breakout and every narrow tree portal."""
        before_star = {item.m_Uuid.AsString() for item in board.GetTracks()}
        port = ports[ref]
        reports = []
        foreign_cache = star_foreign_cache if star_screening else {}
        blocker_cache = star_blocker_cache if star_screening else {}
        report = _route_paired_stub(
            board, pair,
            (port["p"], junction["p"],
             port["n"], junction["n"]),
            avoid=avoid, layer=layer, allow_detour=allow_detour,
            deadline=absolute_deadline,
            foreign_shape_cache=foreign_cache,
            blocker_shape_cache=blocker_cache)
        if report.get("refused"):
            return None, "terminal: " + report["refused"], report
        reports.append(report)
        throats = candidate_throats(ref, layer, junction)
        for other, throat in sorted(throats.items()):
            origin = throat.get("_runway_origin") or throat
            if (_dist(junction["p"], origin["p"]) > 1e-9
                    or _dist(junction["n"], origin["n"]) > 1e-9):
                report = _route_paired_stub(
                    board, pair,
                    (junction["p"], origin["p"],
                     junction["n"], origin["n"]),
                    avoid=avoid, layer=layer,
                    allow_detour=allow_detour,
                    # The following exact runway already fixes the outgoing
                    # direction.  Admit only a spoke that reaches its origin
                    # without reversing against that direction; otherwise the
                    # individually clean legs assemble into an acute hook.
                    preferred_end_direction=tuple(
                        throat.get("route_heading") or ()),
                    minimum_end_heading_alignment=0.0,
                    deadline=absolute_deadline,
                    foreign_shape_cache=foreign_cache,
                    blocker_shape_cache=blocker_cache)
                if report.get("refused"):
                    return (None, "spoke %s: %s" % (
                        other, report["refused"]), report)
                reports.append(report)
            if (_dist(origin["p"], throat["p"]) > 1e-9
                    or _dist(origin["n"], throat["n"]) > 1e-9):
                report = _route_paired_stub(
                    board, pair,
                    (origin["p"], throat["p"],
                     origin["n"], throat["n"]),
                    avoid=avoid, layer=layer, allow_detour=False,
                    preferred_end_direction=tuple(
                        throat.get("route_heading") or ()),
                    minimum_end_heading_alignment=0.99,
                    deadline=absolute_deadline,
                    foreign_shape_cache=foreign_cache,
                    blocker_shape_cache=blocker_cache)
                if report.get("refused"):
                    return (None, "runway %s: %s" % (
                        other, report["refused"]), report)
                reports.append(report)
        # Prove the same normalized graph that the final transaction audits.
        # Covered duplicate legs can make a two-ray reversal look like a
        # three-track branch until final cleanup.  Screening only the raw star
        # therefore selected candidates that inevitably failed after routing
        # every long edge.  Apply this admission also to pairwise reassignment,
        # not just the first junction candidate selection.
        quality = _normalized_pair_star_quality(board, pair, before_star)
        if not (quality.get("ok") and quality.get("geometry_ok")):
            return None, "normalized local star route quality", {
                "admission": quality}
        return throats, None, reports

    chosen = {}
    candidate_sets = {}
    component_signs = dict(_component_sign_overrides or {})
    forced_components = set(component_signs)
    prefilter = {"layer_assignment": layer_assignment}
    for ref, layer in junction_keys:
        incident_rows = incident[(ref, layer)]
        if _multidrop_leaf_breakout_required(
                plan, pair, ref, layer, incident_rows):
            rows = _multidrop_leaf_throat_candidates(
                plan, pair, ref, incident_rows)
        else:
            rows = _multidrop_junction_candidates(
                board, plan, ref, pair)
        orientation_owner = _multidrop_orientation_owner(
            embedding, incident, ref, layer)
        if (ref, layer) in embedding:
            component = (layer, orientation_owner["component"])
            rows = _expand_junction_trunk_signs(
                rows, orientation_owner["lane_axis"],
                trunk_sign=component_signs.get(component))
            rows = [
                _mitered_junction_candidate(
                    plan, pair, ref, layer, row,
                    incident[(ref, layer)], embedding)
                for row in rows]
        elif orientation_owner is not None:
            component = (layer, orientation_owner["component"])
            rows = _classify_junction_candidates(
                rows, orientation_owner["lane_axis"],
                orientation_sign=component_signs.get(component))
        candidate_sets[(ref, layer)] = rows
        selected = None
        index = None
        checked = 0
        rejection_counts = {}
        rejection_samples = []
        admissible = []

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
                if not geometry["ok"]:
                    reject("local_star_geometry", geometry.get("issues"))
                    continue
                # Crossing/spacing authority alone does not catch an acute
                # reversal formed where two independently valid local legs
                # meet.  Apply the same route-quality gate here that owns the
                # completed transaction, while the candidate can still be
                # cheaply rejected and the next junction tried.
                import cec_route_quality
                local_quality = (cec_route_quality.analyze_board(
                    board, critical_nets=(pair["p"], pair["n"]),
                    track_uuid_scope=created) if created else {
                        "ok": True, "geometry_ok": True,
                        "blocking_count": 0, "non_octilinear_count": 0,
                        "issues": [],
                    })
                if (local_quality.get("ok")
                        and local_quality.get("geometry_ok", False)):
                    # A clear local star is not necessarily a useful global
                    # junction.  Rank the entire cheap feasible menu before
                    # committing an escape; the first clear radius/direction
                    # can send a short branch away from both of its peers.
                    rank = _junction_continuation_rank(
                        board, pair, plan, ref, junction, _throats, created)
                    admissible.append((rank, index, junction))
                    continue
                reject("local_star_route_quality", {
                    "blocking_count": int(
                        local_quality.get("blocking_count", 0) or 0),
                    "non_octilinear_count": int(
                        local_quality.get("non_octilinear_count", 0) or 0),
                    "issues": list(local_quality.get("issues") or ())[:8],
                })
            if admissible:
                _rank, index, selected = min(admissible, key=lambda row: (
                    row[0], row[1]))
                break
        rollback()
        key_name = "%s@%s" % (ref, layer)
        prefilter[key_name] = {
            "checked": checked,
            "selected_index": (index if selected is not None else None),
            "selected_sign": (selected.get("embedding_sign")
                              if selected is not None else None),
            "admissible_count": len(admissible),
            "continuation_rank": (list(_rank) if selected is not None else None),
            "rejection_counts": rejection_counts,
            "rejection_samples": rejection_samples,
            "incident_edges": sorted(
                [row["a"], row["b"]] for row in incident[(ref, layer)]),
        }
        if selected is None:
            component = ((layer, orientation_owner["component"])
                         if orientation_owner is not None else None)
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
            refusal = {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "paired_terminals": plan["terminals"],
                "tree_edges": edges,
                "refused": "no layered paired junction for %s" % key_name,
                "candidate_prefilter": prefilter,
                "route_layer_evidence": public_route_layer_evidence(),
            }
            # An empty same-layer PTH junction domain is often a coloring
            # failure rather than a placement failure.  A plated terminal can
            # articulate incident edges on different layers without vias.
            # Move the least-central eligible edge first and prefer an
            # alternate that is unused at its peer, then rerun the bounded
            # colorer under the original absolute deadline.
            if (bool(ports.get(ref, {}).get("through"))
                    and int(_layer_backtrack_depth) < 3):
                betweenness = _multidrop_edge_betweenness(edges)
                movable = sorted(
                    incident_rows,
                    key=lambda row: (
                        betweenness.get(tuple(sorted(
                            (row["a"], row["b"]))), 0),
                        float(row.get("length_mm", 0.0)),
                        row["a"], row["b"]))
                attempts = []
                preferred = list(plan.get("preferred_signal_layers") or ())
                for move_edge in movable:
                    move_key = tuple(sorted(
                        (move_edge["a"], move_edge["b"])))
                    if move_key in forced_edge_layers:
                        continue
                    other = (move_edge["b"] if move_edge["a"] == ref
                             else move_edge["a"])

                    def alternate_rank(candidate_layer):
                        peer_conflicts = sum(
                            1 for row in edges
                            if row is not move_edge
                            and other in (row["a"], row["b"])
                            and row.get("selected_layer") == candidate_layer)
                        return (
                            peer_conflicts,
                            preferred.index(candidate_layer)
                            if candidate_layer in preferred else 999,
                            candidate_layer)

                    alternatives = sorted(
                        (candidate_layer
                         for candidate_layer in move_edge.get("layers", ())
                         if candidate_layer != layer),
                        key=alternate_rank)
                    for candidate_layer in alternatives:
                        if budget_exhausted():
                            break
                        retry_forced = dict(forced_edge_layers)
                        retry_forced[move_key] = candidate_layer
                        retry = _route_layered_multidrop_pair_tree(
                            board, pair, plan, avoid=avoid, verbose=verbose,
                            max_search_seconds=max_search_seconds,
                            _component_sign_overrides=(
                                _component_sign_overrides),
                            _absolute_deadline=absolute_deadline,
                            _forced_edge_layers=retry_forced,
                            _layer_backtrack_depth=(
                                int(_layer_backtrack_depth) + 1),
                            _route_layer_evidence=route_layer_evidence)
                        attempts.append({
                            "edge": list(move_key),
                            "from": layer, "to": candidate_layer,
                            "depth": int(_layer_backtrack_depth) + 1,
                            "result": retry.get("refused") or "accepted",
                        })
                        if not retry.get("refused"):
                            retry.setdefault(
                                "junction_layer_backtracking", []).insert(0, {
                                    "failed_junction": key_name,
                                    "edge": list(move_key),
                                    "from": layer, "to": candidate_layer,
                                    "depth": int(_layer_backtrack_depth) + 1,
                                    "first_attempt_prefilter": prefilter,
                                })
                            return retry
                    if budget_exhausted():
                        break
                refusal["junction_layer_backtracking"] = attempts
            return refusal
        chosen[(ref, layer)] = selected
        if orientation_owner is not None:
            component = (layer, orientation_owner["component"])
            component_signs[component] = int(
                selected.get("embedding_sign", 1))

    star_screening = False

    def layered_assignment_topology_ok(edge, trial):
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
        compatible = _paired_portal_lane_compatible(a_port, b_port)
        rollback()
        return compatible

    def layered_assignment_ok(edge, trial):
        rollback()
        layer = edge["selected_layer"]
        minimum_coupled_fraction = (
            0.0 if edge.get("bounded_terminal_fanout") else 0.35)
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
        if not _paired_portal_lane_compatible(a_port, b_port):
            rollback()
            return False
        report = _route_paired_stub(
            board, pair,
            (a_port["p"], b_port["p"],
             a_port["n"], b_port["n"]),
            avoid=avoid, layer=layer,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=absolute_deadline)
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
    unproven_assignments = []
    for edge in sorted(edges, key=lambda row: (row["length_mm"],
                                               row["a"], row["b"])):
        layer = edge["selected_layer"]
        keys = [(edge["a"], layer), (edge["b"], layer)]
        owned_keys = [key for key in keys if key in chosen]
        if not owned_keys:
            continue
        current = {key: chosen[key] for key in owned_keys}
        current_topology_ok = layered_assignment_topology_ok(edge, current)
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
        if not repaired and not current_topology_ok:
            # A shared-grid route can prove a topology that the finite local
            # dogbone solver cannot.  If the current assignment actually
            # requests a P/N crossover, prefer the first package-clear,
            # polarity-compatible alternative and leave full path proof to
            # production.  Do not perturb a topology that is merely unproved.
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
                    if not layered_assignment_topology_ok(edge, trial):
                        continue
                    chosen[target] = candidate
                    adjustments.append({
                        "edge": [edge["a"], edge["b"]],
                        "changed": "%s@%s" % target,
                        "candidate_index": candidate_index,
                        "proof": "package-clear-lane-polarity",
                    })
                    repaired = True
                    break
                if repaired:
                    break
        if not repaired:
            unproven_assignments.append({
                "edge": [edge["a"], edge["b"]],
                "layer": layer,
                "candidate_limits": {
                    "%s@%s" % key: min(12, len(candidate_sets[key]))
                    for key in owned_keys},
                "minimum_coupled_fraction": (
                    0.0 if edge.get("bounded_terminal_fanout") else 0.35),
            })
    prefilter["pairwise_adjustments"] = adjustments
    # This bounded local solver is a constructive fast path, not a complete
    # proof of board-scale impossibility.  Preserve unproved assignments in
    # diagnostics and let the shared grid attempt them; never misclassify a
    # finite local candidate miss as a placement failure.
    prefilter["pairwise_unproven"] = unproven_assignments

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
                **edge_progress(),
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
        origin = throat.get("_runway_origin") or throat
        stages = []
        if (_dist(junction["p"], origin["p"]) > 1e-9
                or _dist(junction["n"], origin["n"]) > 1e-9):
            stages.append(("junction_spoke", junction, origin, True, 0.0))
        if (_dist(origin["p"], throat["p"]) > 1e-9
                or _dist(origin["n"], throat["n"]) > 1e-9):
            stages.append(("junction_runway", origin, throat, False, 0.99))
        for graph_role, source, target, allow_detour, alignment in stages:
            before = {item.m_Uuid.AsString() for item in board.GetTracks()}
            report = _route_paired_stub(
                board, pair,
                (source["p"], target["p"],
                 source["n"], target["n"]),
                avoid=avoid, layer=layer, allow_detour=allow_detour,
                # Both the flexible spoke and the exact runway terminate on
                # the same directed handoff.  Supplying the direction even
                # for the spoke lets its local solver reject a reverse/acute
                # arrival before the segments become a whole-graph defect.
                preferred_end_direction=tuple(
                    throat.get("route_heading") or ()),
                minimum_end_heading_alignment=alignment,
                deadline=absolute_deadline)
            if report.get("refused"):
                rollback()
                return {
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "paired_terminals": plan["terminals"],
                    "tree_edges": edges,
                    "refused": "planar %s %s@%s->%s refused: %s" %
                               (graph_role, ref, layer, other,
                                report["refused"]),
                    "failed_junction": "%s@%s" % (ref, layer),
                    "candidate_prefilter": prefilter,
                    **edge_progress(),
                }
            reports.append(dict(
                report, graph_role=graph_role, terminal=ref,
                neighbor=other, layer=layer,
                item_uuids=sorted(
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in before)))

    # Candidate screening judges the deduplicated copper union. Materialize
    # that same union before routing edges: a terminal dogbone can be fully
    # covered by its own runway, and edge-only normalization cannot remove an
    # older star item. Otherwise a proved local star reappears as a covered
    # backtrack in the composed-edge gate. Never remove authored base copper.
    star_ids = {item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() not in base_ids}
    prefilter['emitted_star_normalization'] = _drop_fully_covered_tracks(board, star_ids)

    def learned_edge_cost(edge):
        key = tuple(sorted((edge["a"], edge["b"])))
        rows = route_layer_evidence.get(key, {})
        return (
            sum(int(row.get("refusals", 0))
                + int(row.get("timeouts", 0)) for row in rows.values()),
            sum(int(row.get("successes", 0)) for row in rows.values()),
        )

    def prequalified_portal_count(edge):
        layer = edge["selected_layer"]
        return sum(
            (ref, layer, other) in throats
            for ref, other in ((edge["a"], edge["b"]),
                               (edge["b"], edge["a"])))

    # Route the shared backbone before its drops.  The previous scarce-layer-
    # first order let a one-layer leaf take an unconstrained detour through a
    # future connector trunk; every trunk edge was individually routable, but
    # the composed transaction then spent its budget recoloring around copper
    # that should have been laid later.  Tree edge betweenness identifies the
    # board-independent backbone.  Learned failures still lead retries, and
    # layer scarcity/length retain deterministic tie-breaks.
    edge_betweenness = _multidrop_edge_betweenness(edges)
    interface_difficulty = {
        tuple(sorted((edge["a"], edge["b"]))):
            _multidrop_edge_interface_difficulty(edge, ports)
        for edge in edges
    }
    ordered_edges = sorted(
        edges,
        key=lambda edge: (
            -learned_edge_cost(edge)[0],
            -prequalified_portal_count(edge),
            -int(interface_difficulty[tuple(sorted(
                (edge["a"], edge["b"])))]["constrained"]),
            -float(interface_difficulty[tuple(sorted(
                (edge["a"], edge["b"])))]["score"]),
            -edge_betweenness.get(tuple(sorted(
                (edge["a"], edge["b"]))), 0),
            len(edge.get("layers") or ("F.Cu",)),
            -float(edge["length_mm"]),
            learned_edge_cost(edge)[1], edge["a"], edge["b"]))
    prefilter["route_order"] = [{
        "edge": [edge["a"], edge["b"]],
        "betweenness": int(edge_betweenness.get(
            tuple(sorted((edge["a"], edge["b"]))), 0)),
        "interface_difficulty": interface_difficulty[
            tuple(sorted((edge["a"], edge["b"])))],
        "layer_domain": list(edge.get("layers") or ("F.Cu",)),
        "length_mm": float(edge.get("length_mm", 0.0) or 0.0),
    } for edge in ordered_edges]
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
                time.monotonic() + _multidrop_edge_attempt_seconds(
                    edge, ports,
                    forced=edge_key in forced_edge_layers))
            a_port = throats.get((a, layer, b),
                                 chosen.get((a, layer), ports[a]))
            b_port = throats.get((b, layer, a),
                                 chosen.get((b, layer), ports[b]))
            prequalified_portals = int(
                (a, layer, b) in throats) + int(
                (b, layer, a) in throats)
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
                            _discard_items(board,[item])
                    report = None
            if report is None:
                edge_span_mm = float(edge.get("length_mm") or 0.0)
                if prequalified_portals == 2:
                    # Pairwise arc consistency already proves the same exact
                    # throat-to-throat endpoint set with the bounded stub
                    # solver.  Preserve that constructive route class in
                    # production before escalating to the much larger board
                    # grid.  The prior order could admit an edge in seconds,
                    # discard it, then exhaust hundreds of thousands of A*
                    # states trying to rediscover the identical corridor.
                    now = time.monotonic()
                    local_deadline = (None if attempt_deadline is None else
                                      min(attempt_deadline, now + 4.0))
                    local_report = _route_paired_stub(
                        board, pair, endpoints, avoid=avoid, layer=layer,
                        minimum_coupled_fraction=(
                            edge_minimum_coupled_fraction),
                        deadline=local_deadline)
                    if local_report.get("refused"):
                        bounded_report = local_report
                        local_report = _route_prequalified_pair_portals(
                            board, pair, a_port, b_port, layer=layer,
                            clearance=0.20, avoid=avoid,
                            minimum_coupled_fraction=(
                                edge_minimum_coupled_fraction),
                            deadline=attempt_deadline)
                        if local_report.get("refused"):
                            local_report.setdefault(
                                "bounded_stub_fallback", bounded_report)
                elif prequalified_portals == 1:
                    if (a, layer, b) in throats:
                        proven = a_port
                        one_sided_endpoints = endpoints
                    else:
                        # Keep the immutable junction throat as the A* lattice
                        # origin.  Only the raw package-side portal may be
                        # snapped; moving a proven throat would invalidate the
                        # local-star geometry that admitted it.
                        proven = b_port
                        one_sided_endpoints = (
                            b_port["p"], a_port["p"],
                            b_port["n"], a_port["n"])
                    local_report = route_coupled_pair(
                        board, pair, verbose=verbose, avoid=avoid,
                        endpoints=one_sided_endpoints, pair_grid=True,
                        layer=layer,
                        minimum_coupled_fraction=(
                            edge_minimum_coupled_fraction),
                        deadline=attempt_deadline,
                        start_prequalified=proven)
                elif edge_span_mm <= _MULTIDROP_LOCAL_STUB_MAX_MM + 1e-9:
                    if attempt_deadline is None:
                        local_deadline = None
                    else:
                        now = time.monotonic()
                        remaining = max(0.0, attempt_deadline - now)
                        local_deadline = min(
                            attempt_deadline,
                            now + min(4.0, 0.20 * remaining))
                    local_report = _route_paired_stub(
                        board, pair, endpoints, avoid=avoid, layer=layer,
                        minimum_coupled_fraction=(
                            edge_minimum_coupled_fraction),
                        deadline=local_deadline)
                else:
                    local_report = {
                        "refused": "local paired-stub domain skipped",
                        "local_stub_skipped": True,
                        "edge_span_mm": round(edge_span_mm, 6),
                        "local_stub_max_mm": _MULTIDROP_LOCAL_STUB_MAX_MM,
                    }
                report = local_report
                # Zero prequalified endpoints may still benefit from the full
                # package/transition router.  One endpoint already uses that
                # path above, while two proved throats have exhausted their
                # correct shared-ribbon domain here; reinterpreting them as
                # package pads only duplicates work and can invent spurious
                # POFV fallbacks for virtual points.
                if (report.get("refused")
                        and prequalified_portals == 0):
                    report = route_coupled_pair(
                        board, pair, verbose=verbose, avoid=avoid,
                        endpoints=endpoints, pair_grid=True, layer=layer,
                        minimum_coupled_fraction=(
                            edge_minimum_coupled_fraction),
                        deadline=attempt_deadline)
                    if report.get("refused"):
                        report.setdefault("local_stub_fallback",
                                          local_report)
            if not report.get("refused"):
                # Judge the copper that would actually survive this edge's
                # transaction.  A package solver can retrace part of a proved
                # runway; rejecting the duplicate before the final tree's
                # deduplication creates a false covered-backtrack refusal.
                # Restrict removals to THIS attempt: an earlier star/edge or
                # authored priority segment must survive a later rollback.
                attempt_ids = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in before}
                edge_normalization = _drop_fully_covered_tracks(
                    board, attempt_ids)
                if edge_normalization["removed_count"]:
                    report["edge_normalization"] = edge_normalization
                    report["segments"] = len(
                        edge_normalization["remaining_track_uuids"])
                # An edge solver validates the path it just created, but its
                # first/last member can still collide with a previously proved
                # package breakout or junction spoke.  Audit the composed
                # transaction before accepting the edge so the exact culprit
                # remains available to layer/candidate backtracking.
                composed_ids = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in base_ids}
                composed_geometry = _pair_graph_geometry(
                    board, pair, composed_ids)
                if not composed_geometry["ok"]:
                    attempt_ids = {
                        item.m_Uuid.AsString() for item in board.GetTracks()
                        if item.m_Uuid.AsString() not in before}
                    ownership = {
                        item_uuid: {
                            "graph_role": row.get("graph_role"),
                            "terminal": row.get("terminal"),
                            "neighbor": row.get("neighbor"),
                            "edge": row.get("edge"),
                            "layer": row.get("layer"),
                        }
                        for row in reports
                        for item_uuid in row.get("item_uuids", ())}
                    ownership.update({
                        item_uuid: {
                            "graph_role": "trunk_edge",
                            "edge": [a, b], "layer": layer,
                        }
                        for item_uuid in attempt_ids})
                    for issue in composed_geometry.get("issues", ()):
                        for key in ("p_uuid", "n_uuid", "first_uuid",
                                    "second_uuid"):
                            if issue.get(key) in ownership:
                                issue[key.replace("_uuid", "_owner")] = (
                                    ownership[issue[key]])
                    for item in list(board.GetTracks()):
                        if item.m_Uuid.AsString() in attempt_ids:
                            _discard_items(board,[item])
                    report = {
                        "name": pair["name"], "p": pair["p"],
                        "n": pair["n"],
                        "refused": "composed pair edge geometry failed",
                        "graph_geometry": composed_geometry,
                        "edge_report": report,
                    }
                else:
                    import cec_route_quality
                    composed_quality = (cec_route_quality.analyze_board(
                        board, critical_nets=(pair["p"], pair["n"]),
                        track_uuid_scope=composed_ids) if composed_ids else {
                            "ok": True, "geometry_ok": True,
                            "blocking_count": 0,
                            "non_octilinear_count": 0, "issues": [],
                        })
                    if not (composed_quality.get("ok")
                            and composed_quality.get(
                                "geometry_ok", False)):
                        attempt_ids = {
                            item.m_Uuid.AsString()
                            for item in board.GetTracks()
                            if item.m_Uuid.AsString() not in before}
                        ownership = {
                            item_uuid: {
                                "graph_role": row.get("graph_role"),
                                "terminal": row.get("terminal"),
                                "neighbor": row.get("neighbor"),
                                "edge": row.get("edge"),
                                "layer": row.get("layer"),
                            }
                            for row in reports
                            for item_uuid in row.get("item_uuids", ())
                        }
                        ownership.update({
                            item_uuid: {
                                "graph_role": "trunk_edge",
                                "edge": [a, b], "layer": layer,
                            }
                            for item_uuid in attempt_ids})
                        for issue in composed_quality.get("issues", ()):
                            track_uuids = list(
                                issue.get("track_uuids") or ())
                            if track_uuids:
                                issue["track_owners"] = [
                                    ownership.get(item_uuid, {
                                        "graph_role": "unattributed",
                                        "item_uuid": item_uuid,
                                    })
                                    for item_uuid in track_uuids]
                        for item in list(board.GetTracks()):
                            if item.m_Uuid.AsString() in attempt_ids:
                                _discard_items(board,[item])
                        report = {
                            "name": pair["name"], "p": pair["p"],
                            "n": pair["n"],
                            "refused": (
                                "composed pair edge route quality failed"),
                            "route_quality": composed_quality,
                            "edge_report": report,
                        }
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
                "failure_certificate": {
                    "schema": 1,
                    "conclusion": "layered_multidrop_edge_refused",
                    "classification": ["layered_trunk_edge_refused"],
                    "failed_edge": [a, b],
                    "failed_layer": selected_layer,
                    "attempted_layers": [
                        str(row.get("layer") or "")
                        for row in layer_refusals],
                },
                **edge_progress(),
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
        completed_edges.append((a, b))
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
    length_matching = _match_completed_new_pair(board, pair, base_ids, absolute_deadline)
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
            **edge_progress(),
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
            **edge_progress(),
        }
    import cec_route_quality
    route_quality = (cec_route_quality.analyze_board(
        board, critical_nets=(pair["p"], pair["n"]),
        track_uuid_scope=created) if created else {
            "ok": True, "geometry_ok": True,
            "non_octilinear_count": 0, "non_octilinear": [],
            "issue_count": 0, "blocking_count": 0,
            "advisory_count": 0, "critical_nets": sorted(
                (pair["p"], pair["n"])), "issues": [],
        })
    if not (route_quality["ok"]
            and route_quality.get("geometry_ok", False)):
        ownership = {
            item_uuid: {
                "graph_role": row.get("graph_role"),
                "terminal": row.get("terminal"),
                "neighbor": row.get("neighbor"),
                "edge": row.get("edge"),
                "layer": row.get("layer"),
            }
            for row in reports
            for item_uuid in row.get("item_uuids", ())
        }
        for issue in route_quality.get("issues", ()):
            track_uuids = list(issue.get("track_uuids") or ())
            if track_uuids:
                issue["track_owners"] = [
                    ownership.get(item_uuid, {
                        "graph_role": "unattributed",
                        "item_uuid": item_uuid,
                    })
                    for item_uuid in track_uuids
                ]
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
            **edge_progress(),
        }
    return {
        "name": pair["name"], "p": pair["p"], "n": pair["n"],
        "route_mode": "layered-paired-trunk-short-stub",
        "length_matching": length_matching,
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
        **edge_progress(),
        "wall_seconds": round(time.monotonic() - started, 3),
    }


def _flow_through_excursion(legs, *, max_ratio=2.0, minimum_span_mm=2.0):
    """Geometric lower bound for an inline chain, independent of routing.

    An inline device outside the terminal corridor must not become a fixed
    placement anchor merely because it has a locally clear launch.  Compare
    the sum of necessary external leg spans to the terminal span.  This is a
    placement-quality bound, not a signal-integrity or ESD qualification.
    """
    if len(legs) < 2:
        return None
    if (not math.isfinite(float(max_ratio)) or float(max_ratio) < 1.0
            or not math.isfinite(float(minimum_span_mm)) or float(minimum_span_mm) <= 0
            or any(len(leg) != 4 or any(len(point) != 2 or not all(
                math.isfinite(float(v)) for v in point) for point in leg) for leg in legs)):
        raise ValueError("inline excursion requires finite geometry and positive bounds")
    start = tuple((legs[0][0][i] + legs[0][2][i]) / 2 for i in (0, 1))
    end = tuple((legs[-1][1][i] + legs[-1][3][i]) / 2 for i in (0, 1))
    direct = _dist(start, end)
    external = sum(_pair_leg_center_span(leg) for leg in legs)
    reference = max(float(minimum_span_mm), direct)
    return {"ok": external <= float(max_ratio) * reference + 1e-9,
            "terminal_start_mm": list(start), "terminal_end_mm": list(end),
            "terminal_span_mm": round(direct, 6),
            "external_leg_span_mm": round(external, 6),
            "ratio": round(external / reference, 6),
            "limit": float(max_ratio)}


def flow_through_launch_evidence(board_path, *, board=None, length_mm=3.0,
                                 clearance_mm=0.20, max_excursion_ratio=2.0):
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
    locality = []
    for pair in derive_coupled_pairs(board_path, board=board):
        flow = _flow_through_pair_legs(board, pair)
        if flow is None:
            continue
        legs, stations = flow
        excursion = _flow_through_excursion(
            legs, max_ratio=max_excursion_ratio)
        if excursion is not None:
            locality.append(dict(excursion, pair=pair["name"],
                                 station_refs=list(stations)))
        own_nets = {pair["p"], pair["n"]}
        station_points = {
            ref: {tuple(row[2]) for row in
                  _pads_on_net(board, pair["p"])
                  + _pads_on_net(board, pair["n"])
                  if row[0] == ref}
            for ref in stations}
        if excursion is not None and not excursion["ok"]:
            for ref in stations:
                points = station_points[ref]
                banks = sorted({tuple((p[i] + n[i]) / 2 for i in (0, 1))
                                for pa, pb, na, nb in legs
                                for p, n in ((pa, na), (pb, nb))
                                if p in points and n in points})
                violations.append(dict(
                    excursion, kind="flow_through_excursion",
                    pair=pair["name"], station_ref=ref,
                    station_refs=list(stations), bank_centers_mm=banks,
                    reason="inline station forces excessive terminal detour"))
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
    return {"schema": 2, "ok": not violations,
            "violations": violations, "channels": channels,
            "locality": locality}


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _segment_is_octilinear(a, b, *, tolerance_mm=0.001):
    """Whether a segment is cardinal or 45 degrees within endpoint tolerance."""
    dx, dy = abs(float(b[0]) - float(a[0])), abs(float(b[1]) - float(a[1]))
    if math.hypot(dx, dy) <= 1.0e-12:
        return True
    miss = min(dx, dy, abs(dx - dy) / math.sqrt(2.0))
    return miss <= max(0.0, float(tolerance_mm))


def _polyline_is_octilinear(points, *, tolerance_mm=0.001):
    """Apply the pipeline's straight-copper heading policy to a polyline."""
    return all(_segment_is_octilinear(a, b, tolerance_mm=tolerance_mm)
               for a, b in zip(points, points[1:]))


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
    # An absolute dot-product epsilon scales as length squared. It hid severe
    # reversals at nanometre serialization tails even though the later native
    # junction audit rejected exactly those turns. Apply that SAME opening-
    # angle contract while enumerating alternatives, before selecting copper.
    return _polyline_min_opening_angle(points) + 1e-9 < 89.0


def _polyline_has_self_crossing(points):
    """Exact proper crossings of non-adjacent native-nanometre segments.

    A member must not loop through itself merely because its other member is
    clear. This is a proposal prefilter, never a substitute for final native
    graph, pad-contact, clearance, coupling or skew admission.
    """
    native = [(_nm(p[0]), _nm(p[1])) for p in points]
    segments = [(a, b) for a, b in zip(native, native[1:]) if a != b]
    return any(_seg_cross(a, b, c, d)
               for i, (a, b) in enumerate(segments)
               for c, d in segments[i+2:])


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
            _discard_items(board,[candidate])
        else:
            survivors.append(candidate)
            remaining_scope.append(candidate)
    return {
        "removed_count": len(removed),
        "removed_track_uuids": sorted(removed),
        "remaining_track_uuids": sorted(
            item.m_Uuid.AsString() for item in remaining_scope),
    }


def _match_completed_new_pair(board, pair, before_ids, deadline):
    """Proposal-only matching at a completed paired transaction boundary.

    Never tune a partial local star or retained source copper. The caller
    still receives the composed graph, coupling, reference, detour, current
    and saved-board DRC, and rolls the entire new transaction back on failure.
    """
    import cec_pair_skew
    if pair.get('kind') not in ('can', 'usb', 'diff'):
        return {'attempted': False, 'reason': 'positive_pair_kind_required'}
    skew = cec_pair_skew.from_board(board, pair)
    if skew['ok']:
        return {'attempted': False, 'reason': 'existing_skew_within_limit', 'skew': skew}
    if deadline is not None and time.monotonic() >= deadline:
        return {'attempted': False, 'reason': 'transaction_deadline', 'skew': skew}
    native = _native_pair_completion(board, pair)
    if not (native.get('complete') and native.get('connected')):
        return {'attempted': False, 'reason': 'incomplete_native_pair', 'completion': native}
    created = {item.m_Uuid.AsString() for item in board.GetTracks()
               if item.m_Uuid.AsString() not in before_ids}
    if not created or len(created) > 512:
        return {'attempted': False, 'reason': 'bounded_new_owned_scope_required'}
    from cec_pair_length_match import balance
    lease = time.monotonic()+4.
    if deadline is not None: lease = min(lease, deadline)
    result = balance(board, pair, created, deadline=lease, max_proposals=96, max_changes=6)
    return dict(result, attempted=True, native_completion_before=native)


def _normalized_pair_star_quality(board, pair, before_ids):
    """Audit a disposable local star in its final, deduplicated form.

    Only newly generated tracks may be removed.  Existing priority copper is
    immutable, including a wider segment covering one of the new legs.
    """
    created = {item.m_Uuid.AsString() for item in board.GetTracks()
               if item.m_Uuid.AsString() not in before_ids}
    normalization = _drop_fully_covered_tracks(board, created)
    created.difference_update(normalization["removed_track_uuids"])
    if created:
        import cec_route_quality
        quality = cec_route_quality.analyze_board(
            board, critical_nets=(pair["p"], pair["n"]),
            track_uuid_scope=created)
    else:
        quality = {"ok": True, "geometry_ok": True, "issues": []}
    return dict(quality, normalization=normalization)


def _paired_endpoint_signature(endpoints):
    """Return an exact, serialization-safe identity for four pair endpoints."""
    return [[int(round(point[0] * MM)), int(round(point[1] * MM))]
            for point in endpoints]


def _capture_track_template(board, track_uuids):
    """Capture deterministic track/via geometry without KiCad UUIDs."""
    scope = set(track_uuids or ())
    rows = []
    for item in board.GetTracks():
        if item.m_Uuid.AsString() not in scope:
            continue
        if item.GetClass() == "PCB_TRACK":
            start, end = item.GetStart(), item.GetEnd()
            rows.append({
                "kind": "track", "net": item.GetNetname(),
                "layer_id": int(item.GetLayer()),
                "width_nm": int(item.GetWidth()),
                "start_nm": [int(start.x), int(start.y)],
                "end_nm": [int(end.x), int(end.y)],
                "locked": bool(item.IsLocked()),
            })
        elif item.GetClass() == "PCB_VIA":
            at = item.GetPosition()
            rows.append({
                "kind": "via", "net": item.GetNetname(),
                "at_nm": [int(at.x), int(at.y)],
                "width_nm": int(item.GetWidth(item.TopLayer())),
                "drill_nm": int(item.GetDrillValue()),
                "top_layer_id": int(item.TopLayer()),
                "bottom_layer_id": int(item.BottomLayer()),
                "via_type": int(item.GetViaType()),
                "locked": bool(item.IsLocked()),
            })
    return sorted(rows, key=lambda row: (
        row["net"], row["kind"], row.get("layer_id", -1),
        row["width_nm"], row.get("start_nm", row.get("at_nm")),
        row.get("end_nm", row.get("at_nm"))))


def _replay_track_template(board, rows):
    """Replay an in-call exact route template and return its fresh UUIDs."""
    created = []
    for row in rows:
        net_code = board.GetNetcodeFromNetname(row["net"])
        if net_code <= 0:
            for item in created:
                _discard_items(board,[item])
            return set()
        if row.get("kind", "track") == "via":
            item = pcbnew.PCB_VIA(board)
            item.SetViaType(int(row["via_type"]))
            item.SetPosition(pcbnew.VECTOR2I(*row["at_nm"]))
            item.SetWidth(int(row["width_nm"]))
            item.SetDrill(int(row["drill_nm"]))
            item.SetLayerPair(
                int(row["top_layer_id"]), int(row["bottom_layer_id"]))
        else:
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I(*row["start_nm"]))
            item.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
            item.SetWidth(int(row["width_nm"]))
            item.SetLayer(int(row["layer_id"]))
        item.SetNetCode(net_code)
        item.SetLocked(bool(row.get("locked", False)))
        board.Add(item)
        created.append(item)
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
        # A point is not a two-ended segment. The general routine repeats the
        # same projection twice and tests an impossible proper intersection
        # for every coupling sample in every ribbon candidate. Keep all three
        # distinct distances, including endpoint roundoff/degenerate-segment
        # semantics, without that duplicate work.
        start, end = segment
        vx, vy = end[0] - start[0], end[1] - start[1]
        length2 = vx * vx + vy * vy
        dx, dy = point[0] - start[0], point[1] - start[1]
        if length2 <= 1e-12:
            return min(math.hypot(dx, dy),
                       math.hypot(point[0] - end[0], point[1] - end[1]))
        t = max(0., min(1., (dx * vx + dy * vy) / length2))
        return min(math.hypot(point[0] - (start[0] + t * vx),
                              point[1] - (start[1] + t * vy)),
                   math.hypot(dx, dy),
                   math.hypot(point[0] - end[0], point[1] - end[1]))

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


def _pair_coupling_contract(pair, coupling, member_lengths,
                            endpoint_stations=None):
    """Apply the final-board coupled-length contract to one routed pair.

    A millimetre-scale package escape may legitimately spend a bounded absolute
    length outside the nominal pair gap.  Longer separated members must meet
    the normal coverage floor.  Keep these values identical to the independent
    final-board checker so precision success cannot become a signoff failure
    without any intervening geometry change.
    """
    return cec_constraints.pair_coupling_contract(
        pair.get("kind"), coupling, member_lengths,
        endpoint_stations=endpoint_stations)


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
        segment_clear, max_middle_vertices=3, deadline=None,
        require_forward_continuation=False, portal_heading=None,
        diagnostics=None, p_segment_clear=None, n_segment_clear=None):
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
    p_clear = p_segment_clear or segment_clear
    n_clear = n_segment_clear or segment_clear
    limit = min(len(p_middle), len(n_middle),
                max(1, int(max_middle_vertices or 1)) + 1)
    rejection_counts = collections.Counter()

    def refused(reason):
        rejection_counts[str(reason)] += 1

    def flush_diagnostics(*, selected=None):
        if diagnostics is None:
            return
        diagnostics.update({
            "p_portal_mm": [round(float(value), 6)
                            for value in p_portal],
            "n_portal_mm": [round(float(value), 6)
                            for value in n_portal],
            "portal_heading": ([round(float(value), 6)
                                for value in portal_heading]
                               if portal_heading is not None else None),
            "middle_prefix_mm": [
                [[round(float(value), 6) for value in p_middle[index]],
                 [round(float(value), 6) for value in n_middle[index]]]
                for index in range(limit)],
            "rejection_counts": dict(sorted(rejection_counts.items())),
        })
        if selected is not None:
            diagnostics["selected"] = selected

    def balanced_octilinear_taper(portal, target, axis):
        """Use a straight runway plus one 45-degree pitch-change leg."""
        axis_length = math.hypot(*axis)
        if axis_length <= 1e-9:
            return None
        ux, uy = axis[0] / axis_length, axis[1] / axis_length
        directions = ((1.0, 0.0), (math.sqrt(0.5), math.sqrt(0.5)),
                      (0.0, 1.0), (-math.sqrt(0.5), math.sqrt(0.5)),
                      (-1.0, 0.0), (-math.sqrt(0.5), -math.sqrt(0.5)),
                      (0.0, -1.0), (math.sqrt(0.5), -math.sqrt(0.5)))
        ux, uy = max(
            directions, key=lambda row: ux * row[0] + uy * row[1])
        nx, ny = -uy, ux
        delta = (target[0] - portal[0], target[1] - portal[1])
        forward = delta[0] * ux + delta[1] * uy
        lateral = delta[0] * nx + delta[1] * ny
        if forward + 1e-9 < abs(lateral):
            return None
        runway = max(0.0, forward - abs(lateral))
        bend = (portal[0] + ux * runway,
                portal[1] + uy * runway)
        path = [tuple(portal)]
        if _dist(path[-1], bend) > 1e-9:
            path.append(bend)
        if _dist(path[-1], target) > 1e-9:
            path.append(tuple(target))
        if (not _polyline_is_octilinear(path)
                or _polyline_has_reverse_bend(path)):
            return None
        return path

    def continuation_is_forward(p_path, n_path, index):
        """Prove the taper-to-core join, not only the taper in isolation."""
        if index + 1 >= min(len(p_middle), len(n_middle)):
            return True
        return not (
            _polyline_has_reverse_bend(
                list(p_path) + [tuple(p_middle[index + 1])])
            or _polyline_has_reverse_bend(
                list(n_path) + [tuple(n_middle[index + 1])]))

    def departure_is_forward(path):
        """Prove the portal-to-taper join against its existing runway."""
        if portal_heading is None:
            return True
        heading = tuple(float(value) for value in portal_heading)
        if len(heading) != 2 or math.hypot(*heading) <= 1e-9:
            return True
        for first, second in zip(path, path[1:]):
            vector = (second[0] - first[0], second[1] - first[1])
            if math.hypot(*vector) <= 1e-9:
                continue
            return (vector[0] * heading[0] + vector[1] * heading[1]
                    > 1e-9)
        return True

    def portal_join_is_forward(p_path, n_path):
        return (departure_is_forward(p_path)
                and departure_is_forward(n_path))

    # Pitch changes are a local transmission-line taper, not an arbitrary raw
    # diagonal.  A straight portal-to-ribbon segment is usually only a few
    # degrees off axis and therefore cannot pass the final octilinear quality
    # gate.  Build the canonical equal-angle taper first: a straight runway
    # followed by one 45-degree convergence leg per member.
    portal_center = ((p_portal[0] + n_portal[0]) / 2.0,
                     (p_portal[1] + n_portal[1]) / 2.0)
    for index in range(limit):
        middle_center = (
            (p_middle[index][0] + n_middle[index][0]) / 2.0,
            (p_middle[index][1] + n_middle[index][1]) / 2.0)
        axis = (middle_center[0] - portal_center[0],
                middle_center[1] - portal_center[1])
        p_path = balanced_octilinear_taper(
            tuple(p_portal), tuple(p_middle[index]), axis)
        n_path = balanced_octilinear_taper(
            tuple(n_portal), tuple(n_middle[index]), axis)
        if p_path is None or n_path is None:
            refused("balanced_geometry")
            continue
        if not all(clear(a, b)
                   for path, clear in ((p_path, p_clear), (n_path, n_clear))
                   for a, b in zip(path, path[1:])):
            refused("segment_clearance")
            continue
        if not _polys_no_cross(p_path, n_path):
            refused("member_crossing")
            continue
        if not _pair_min_clear(
                p_path, n_path, -1, -1, width, gap,
                strict_pair_gap=True):
            refused("pair_gap")
            continue
        if (require_forward_continuation
                and not continuation_is_forward(p_path, n_path, index)):
            refused("core_continuation")
            continue
        if (require_forward_continuation
                and not portal_join_is_forward(p_path, n_path)):
            refused("portal_departure")
            continue
        flush_diagnostics(selected={
            "middle_index": index,
            "taper_geometry": "straight-plus-45",
            "p_path_mm": [[round(float(value), 6) for value in point]
                          for point in p_path],
            "n_path_mm": [[round(float(value), 6) for value in point]
                          for point in n_path],
        })
        return {"p": p_path, "n": n_path, "middle_index": index,
                "taper_geometry": "straight-plus-45"}

    for index in range(limit):
        p_path = [tuple(p_portal), tuple(p_middle[index])]
        n_path = [tuple(n_portal), tuple(n_middle[index])]
        # An individually clear straight line is not necessarily an allowed
        # route heading. Returning it here starves the later joint dogbone
        # search; the whole-ribbon gate then refuses the same raw diagonal.
        # Keep this proposal boundary consistent with final octilinearity,
        # rather than relaxing the final gate or retrying the same grid.
        if not (_polyline_is_octilinear(p_path)
                and _polyline_is_octilinear(n_path)):
            refused("direct_non_octilinear")
            continue
        if not (p_clear(*p_path) and n_clear(*n_path)):
            refused("direct_segment_clearance")
            continue
        if not _polys_no_cross(p_path, n_path):
            refused("direct_member_crossing")
            continue
        if not _pair_min_clear(
                p_path, n_path, -1, -1, width, gap,
                strict_pair_gap=True):
            refused("direct_pair_gap")
            continue
        if (require_forward_continuation
                and not continuation_is_forward(p_path, n_path, index)):
            refused("direct_core_continuation")
            continue
        if (require_forward_continuation
                and not portal_join_is_forward(p_path, n_path)):
            refused("direct_portal_departure")
            continue
        flush_diagnostics(selected={
            "middle_index": index, "taper_geometry": "direct",
            "p_path_mm": [[round(float(value), 6) for value in point]
                          for point in p_path],
            "n_path_mm": [[round(float(value), 6) for value in point]
                          for point in n_path],
        })
        return {"p": p_path, "n": n_path, "middle_index": index}
    # A one-step octilinear throat turn can rotate the constant-offset ribbon
    # enough that a single symmetric segment is topologically impossible even
    # though a short, conventional paired dogbone is legal.  Reuse the exact
    # joint endpoint solver for that finite prefix.  It admits the two members
    # atomically (clearance, crossing, octilinearity, and reverse-bend checks)
    # and never weakens the whole-edge graph/quality gate that follows.
    for index in range(limit):
        escape = _joint_endpoint_escape(
            tuple(p_portal), tuple(n_portal),
            tuple(p_middle[index]), tuple(n_middle[index]),
            width=width, gap=gap, segment_clear=segment_clear,
            p_segment_clear=p_clear, n_segment_clear=n_clear,
            max_detour=2.0, max_member_paths=24,
            strict_pair_gap=True, deadline=deadline)
        if escape is not None:
            if (require_forward_continuation
                    and not continuation_is_forward(
                        escape[0], escape[1], index)):
                refused("joint_core_continuation")
                continue
            if (require_forward_continuation
                    and not portal_join_is_forward(
                        escape[0], escape[1])):
                refused("joint_portal_departure")
                continue
            flush_diagnostics(selected={
                "middle_index": index, "taper_geometry": "joint",
                "p_path_mm": [[round(float(value), 6) for value in point]
                              for point in escape[0]],
                "n_path_mm": [[round(float(value), 6) for value in point]
                              for point in escape[1]],
            })
            return {"p": escape[0], "n": escape[1],
                    "middle_index": index}
        refused("joint_escape")
    flush_diagnostics()
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


def _partner_tracks_clear(board, a, b, width_nm, layer_id, partner_code,
                          *, clearance_nm=0, partner_shapes=None):
    """Reject clearance infringement with established partner copper.

    A differential pair's opposite member is intentionally closer than the
    ordinary foreign-copper index is therefore allowed to exclude both pair
    nets.  The pair members must still meet their requested edge clearance,
    however, including where a wider transition-via land replaces a track.
    A centerline-only check cannot see that extra radius.  Apply the exact
    shape collision at the caller's pair/netclass clearance; legal adjacent
    copper at the requested gap remains admissible, while crossings and
    track-to-via infringements are refused before materialization.  Same-
    member copper is not inspected so a new leg may intentionally rejoin its
    existing topology.
    """
    if a == b:
        return True
    segment = pcbnew.SHAPE_SEGMENT(_v(*a), _v(*b), width_nm)
    if partner_shapes is not None:
        # Candidate P/N paths are checked jointly before either is emitted,
        # so only copper established before this transaction belongs here.
        # Buckets conservatively shortlist shapes; KiCad's exact Collide()
        # remains the admission predicate with the historical 1 nm epsilon.
        return cec_fr._snapshot_foreign_clear(
            _v(*a), _v(*b), width_nm,
            max(0, int(clearance_nm) - 1), (), partner_shapes)
    for item in getattr(board, "GetTracks", lambda: ())():
        if item.GetNetCode() != int(partner_code):
            continue
        try:
            if item.Type() == pcbnew.PCB_VIA_T:
                if layer_id not in item.GetLayerSet().CuStack():
                    continue
            elif item.GetLayer() != layer_id:
                continue
            # One-nanometre epsilon admits exact boundary contact despite
            # integer rounding while preserving every meaningful clearance.
            exact_clearance = max(0, int(clearance_nm) - 1)
            if item.GetEffectiveShape(layer_id).Collide(
                    segment, exact_clearance):
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
    if not _polyline_is_octilinear(pts):
        bad = [(a, b) for a, b in zip(pts, pts[1:])
               if not _segment_is_octilinear(a, b)]
        raise ValueError(
            "precision route emitter refused non-octilinear copper: %r" %
            (bad[:3],))
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
    from cec_reservation_index import ReservationIndex, build
    if isinstance(avoid, ReservationIndex):
        return avoid
    selected = []
    for row in avoid or ():
        if len(row) == 5:
            selected.append(tuple(row))
            continue
        if len(row) != 6:
            raise ValueError("avoid rectangle must have 5 or 6 fields")
        if str(row[5]) == str(layer):
            selected.append(tuple(row[:5]))
    return build(selected)


def _crosses_avoid(pts, avoid, width):
    """Does this polyline (at *width*) enter any reserved rect? Returns the rect ref."""
    if not avoid:
        return None
    pts = tuple(pts)

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
    rows = (avoid.candidates(pts, hw) if hasattr(avoid, 'candidates') else avoid)
    for (x0, y0, x1, y1, ref) in rows:
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
        axis0 = abs(v0[0]) <= 1e-9 or abs(v0[1]) <= 1e-9
        axis1 = abs(v1[0]) <= 1e-9 or abs(v1[1]) <= 1e-9
        if (l0 <= 1e-9 or l1 <= 1e-9 or abs(cross) <= 1e-9
                or dot < -1e-9 or not (axis0 and axis1)):
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


def _path_end_heading(path):
    """Return the unit vector of the final non-zero path leg."""
    for start, end in reversed(list(zip(path, path[1:]))):
        vx, vy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(vx, vy)
        if length > 1e-9:
            return (vx / length, vy / length)
    return None


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


def _pair_end_coherence(p_path, n_path):
    """Cosine between the two actual arrival directions, not their sum."""
    p_heading, n_heading = _path_end_heading(p_path), _path_end_heading(n_path)
    if p_heading is None or n_heading is None:
        return -1.0
    return p_heading[0] * n_heading[0] + p_heading[1] * n_heading[1]


def _ranked_joint_escape(p_paths, n_paths, *, p_span, n_span, width, gap,
                         max_skew=None, preferred_end_direction=None,
                         minimum_end_coherence=None, strict_pair_gap=False,
                         deadline=None, diagnostics=None,
                         existing_signed_skew_mm=0.0, pair_admission=None):
    """Select the exact best legal pair without validating dominated choices.

    The objective depends only on each already-guarded member's length and
    heading, not on the expensive pairwise collision test. Sort that same
    complete objective (including deterministic path tie-breaks) first. The
    first mutually legal candidate is exactly the exhaustive argmin over the
    bounded domain; no geometry or electrical check is approximated or waived.
    """
    existing_signed_skew_mm = float(existing_signed_skew_mm)
    if not math.isfinite(existing_signed_skew_mm):
        raise ValueError('existing signed pair skew must be finite')

    def metrics(paths):
        return [(tuple(path), sum(_dist(a, b) for a, b in zip(path, path[1:])),
                 _path_end_heading_alignment(path, preferred_end_direction))
                for path in paths if not _polyline_has_reverse_bend(path)
                and not _polyline_has_self_crossing(path)]

    p_rows, n_rows = metrics(p_paths), metrics(n_paths)
    ranked = []
    evidence = dict(path_pairs_available=len(p_rows)*len(n_rows),
        path_pairs_ranked=0, path_pairs_checked=0, crossing_rejected=0,
        pair_clearance_rejected=0, coherence_rejected=0, admitted_pairs=0,
        objective_pruned_pairs=0, deadline_exhausted=False,
        selection_policy='exact-objective-first',
        existing_signed_skew_mm=existing_signed_skew_mm)
    for p_path, p_len, p_heading in p_rows:
        for n_path, n_len, n_heading in n_rows:
            if _deadline_expired(deadline):
                evidence['deadline_exhausted'] = True
                if diagnostics is not None:
                    diagnostics.update(evidence)
                return None
            skew = abs(existing_signed_skew_mm+p_len-n_len)
            shortfall = max(0.0, math.cos(math.radians(67.5)) - min(p_heading, n_heading))
            if max_skew is None:
                score = (round(skew, 6), round(shortfall, 6), round(p_len+n_len, 6))
            else:
                score = _bounded_pair_choice_score(p_len, n_len, p_span, n_span,
                    skew=skew, max_skew=max_skew, heading_shortfall=shortfall)
            ranked.append(score + (len(p_path)+len(n_path), p_path, n_path))
            evidence['path_pairs_ranked'] += 1
    ranked.sort()
    selected = None
    for index, row in enumerate(ranked):
        if _deadline_expired(deadline):
            evidence['deadline_exhausted'] = True
            break
        p_path, n_path = row[-2:]
        evidence['path_pairs_checked'] += 1
        if (minimum_end_coherence is not None
                and _pair_end_coherence(p_path, n_path) + 1e-9 < float(minimum_end_coherence)):
            evidence['coherence_rejected'] += 1
            continue
        if not _polys_no_cross(p_path, n_path):
            evidence['crossing_rejected'] += 1
            continue
        if not _pair_min_clear(p_path, n_path, -1, -1, width, gap,
                               strict_pair_gap=bool(strict_pair_gap)):
            evidence['pair_clearance_rejected'] += 1
            continue
        if pair_admission is not None and not pair_admission(p_path, n_path):
            evidence['contract_rejected'] = evidence.get('contract_rejected', 0) + 1
            continue
        selected = row
        evidence['admitted_pairs'] = 1
        evidence['objective_pruned_pairs'] = len(ranked)-index-1
        break
    if diagnostics is not None:
        diagnostics.update(evidence)
    return (list(selected[-2]), list(selected[-1])) if selected is not None else None


def _joint_endpoint_escape(p_start, n_start, p_end, n_end, *,
                           width, gap, segment_clear=None,
                           p_segment_clear=None, n_segment_clear=None,
                           max_detour=2.0, max_member_paths=32,
                           max_skew=None, preferred_end_direction=None,
                           minimum_end_heading_alignment=-1.0,
                           minimum_end_coherence=None,
                           strict_pair_gap=False,
                           diagnostics=None, deadline=None,
                           existing_signed_skew_mm=0.0,
                           complete_pair_context=None, roadmap_limits=None):
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
        # Hard handoffs also need constructive candidates. A cardinal source-
        # destination span otherwise has only cardinal arrivals in this menu,
        # even when a perfectly legal 45-degree terminal runway is required.
        if preferred_end_direction:
            hx, hy = preferred_end_direction
            hn = math.hypot(hx, hy)
            if hn > 1e-9:
                hx, hy = hx/hn, hy/hn
                if _segment_is_octilinear((0.0, 0.0), (hx, hy)):
                    # A nearby native via may leave a short legal straight
                    # throat before the two lanes fan out. Requiring one
                    # entire lane pitch as the shortest runway rejected that
                    # geometry even though all member, pair-gap and heading
                    # guards passed. Sample compact pitch-scaled runways;
                    # these are proposals, never clearance exceptions.
                    pitch = float(width)+float(gap)
                    for reach in sorted({pitch*.25, pitch*.5, pitch, 0.75, 1.5}):
                        approach = (ex-reach*hx, ey-reach*hy)
                        ax, ay = approach
                        rows.extend(([start,(ax,sy),approach,end],
                                     [start,(sx,ay),approach,end]))
                        dx, dy = ax-sx, ay-sy
                        diagonal = min(abs(dx),abs(dy))
                        ox, oy = math.copysign(diagonal,dx), math.copysign(diagonal,dy)
                        rows.extend(([start,(sx+ox,sy+oy),approach,end],
                                     [start,(ax-ox,ay-oy),approach,end]))
        # Exact octilinear visibility bends.  The historical direct segment
        # could enter a compact protector at an arbitrary angle; deleting it
        # without adding the canonical equivalent made an otherwise simple
        # terminal leg appear impossible.  Each row below is one cardinal and
        # one 45-degree segment, derived only from endpoint geometry.
        dx, dy = ex - sx, ey - sy
        ax, ay = abs(dx), abs(dy)
        if ax > 1e-9 and ay > 1e-9:
            for polarity in (-1.0, 1.0):
                rows.extend((
                    [start, (ex + polarity * ay, sy), end],
                    [start, (sx + polarity * ay, ey), end],
                    [start, (sx, ey + polarity * ax), end],
                    [start, (ex, sy + polarity * ax), end],
                ))
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
            # Compound visibility hooks leave a dense pin row through an
            # interior channel, move outside the blocker silhouette, then
            # approach the destination from its free side.  The earlier
            # perimeter forms began their detour at the pad coordinate; on a
            # connector that first vertical leg can be fenced by adjacent
            # lands.  These candidates remain bounded, cardinal before
            # chamfering, monotone on the main axis, and contain no >90-degree
            # hairpin.  They generalize to any pad row / inline protector
            # orientation without inspecting references or net names.
            for fraction in (0.25, 0.5, 0.75):
                x_mid = sx + (ex - sx) * fraction
                y_mid = sy + (ey - sy) * fraction
                for y_detour in (lo_y - distance, hi_y + distance):
                    rows.append([
                        start, (x_mid, sy), (x_mid, y_detour),
                        (ex, y_detour), end])
                for x_detour in (lo_x - distance, hi_x + distance):
                    rows.append([
                        start, (sx, y_mid), (x_detour, y_mid),
                        (x_detour, ey), end])
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
        non_octilinear_rejected = 0
        clearance_rejected = 0
        heading_rejected = 0
        for path in raw:
            if _deadline_expired(deadline):
                timed_out = True
                break
            if (_polyline_has_reverse_bend(path)
                    or _polyline_has_self_crossing(path)):
                reverse_rejected += 1
                continue
            if not _polyline_is_octilinear(path):
                non_octilinear_rejected += 1
                continue
            # A required handoff is an admission constraint, not a tie-break
            # after the shortest-path beam has already discarded alternatives.
            if (_path_end_heading_alignment(path, preferred_end_direction)
                    + 1e-9 < float(minimum_end_heading_alignment)):
                heading_rejected += 1
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
            "non_octilinear_rejected": non_octilinear_rejected,
            "clearance_rejected": clearance_rejected,
            "heading_rejected": heading_rejected,
        }

    p_paths, p_evidence = member_paths(p_start, p_end, p_clear)
    n_paths, n_evidence = member_paths(n_start, n_end, n_clear)
    p_span = max(_dist(p_start, p_end), 1e-9)
    n_span = max(_dist(n_start, n_end), 1e-9)
    selection_evidence = {}
    selected = _ranked_joint_escape(p_paths, n_paths,
        p_span=p_span, n_span=n_span, width=width, gap=gap,
        max_skew=max_skew, preferred_end_direction=preferred_end_direction,
        minimum_end_coherence=minimum_end_coherence,
        strict_pair_gap=strict_pair_gap, deadline=deadline,
        existing_signed_skew_mm=existing_signed_skew_mm,
        diagnostics=selection_evidence)
    if complete_pair_context is not None:
        import cec_endpoint_roadmap
        selected, roadmap = cec_endpoint_roadmap.refine(
            p_paths,n_paths,selected,endpoints=(p_start,n_start,p_end,n_end),
            p_clear=p_clear,n_clear=n_clear,context=complete_pair_context,
            minimum_end_heading_alignment=minimum_end_heading_alignment,
            deadline=deadline,limits=roadmap_limits,
            options=dict(p_span=p_span,n_span=n_span,width=width,gap=gap,
                max_skew=max_skew,preferred_end_direction=preferred_end_direction,
                minimum_end_coherence=minimum_end_coherence,
                strict_pair_gap=strict_pair_gap,
                existing_signed_skew_mm=existing_signed_skew_mm))
        selection_evidence['roadmap'] = roadmap
    if diagnostics is not None:
        diagnostics.update({
            "p_paths": p_evidence,
            "n_paths": n_evidence,
            **selection_evidence,
            "deadline_exhausted": timed_out or selection_evidence['deadline_exhausted'],
        })
    if selected is None:
        return None
    p_path, n_path = selected
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
            "projected_whole_skew_mm": round(abs(
                float(existing_signed_skew_mm)+p_length-n_length), 6),
        }
    return list(p_path), list(n_path)


def _pair_escape_budget(pad_a, pad_b, *, floor_mm=6.0,
                        cap_mm=12.0):
    """Scale a coupled breakout to the physical pair-pin separation.

    A compact IC pair needs enough neighborhood for two signal-via lands and
    their reference-return field after clearing its passive ring.  Widely
    separated connector contacts need still more room to converge without
    crossing.  Keep the search local and bounded while scaling it to package
    geometry rather than a connector name.
    """
    return min(float(cap_mm), max(float(floor_mm),
                                 1.5 * _dist(pad_a, pad_b)))


def _portal_return_route_axis(row, fallback):
    """Use the local throat, not the remote endpoint bearing, for returns.

    Stored headings point outward at either package. Return ranking uses the
    traversal direction, so an end throat has the opposite sign.
    """
    heading=row.get('route_heading')
    if heading is None:
        return tuple(fallback)
    if (len(heading)!=2 or not all(math.isfinite(float(v)) for v in heading)
            or math.hypot(*heading)<=1e-9 or row.get('side') not in ('start','end')):
        raise ValueError('invalid local return-field heading')
    direction=1.0 if row['side']=='start' else -1.0
    return tuple(direction*float(v) for v in heading)


def _return_via_route_rank(delta, route_axis, corridor_half, portal_side):
    """Prefer flank returns, then package-side, then corridor-side seats.

    A dense pin field can leave no legal via exactly beside a matched signal
    pair.  Rejecting every axial candidate at screening time creates a false
    placement failure even when a legal package-side return exists.  Keep the
    professional flank preference, but retain both axial fallbacks for the
    later exact fan-in and shared-centreline collision proofs.
    """
    route_length = math.hypot(*route_axis) or 1.0
    route_unit = (route_axis[0] / route_length,
                  route_axis[1] / route_length)
    signed_projection = (delta[0] * route_unit[0]
                         + delta[1] * route_unit[1])
    absolute_projection = abs(signed_projection)
    if absolute_projection + 1e-9 < float(corridor_half):
        route_class = 0
    else:
        # The inner ribbon leaves a start portal along +axis and approaches an
        # end portal along +axis.  Therefore the package side is -axis at the
        # start and +axis at the end.
        package_side = (signed_projection < 0.0
                        if portal_side == "start"
                        else signed_projection > 0.0)
        route_class = 1 if package_side else 2
    return (route_class, round(absolute_projection, 9))


def _add_pair_transition_returns(
        board, center, pair_vector, *, route_axis=None, signal_points=(),
        portal_side="start", width=0.20, gap=0.20, clearance=0.20,
        via_diameter_mm=0.60, via_drill_mm=0.30,
        return_reach_mm=1.50, reference_contact=None, diagnostics=None,
        deadline=None, refine=False):
    """Add the minimum exact-clearance GND field for one pair transition.

    Both ordinary paired portals and pad-origin filled/capped transitions need
    the same return-path contract.  Keeping this as one primitive prevents a
    later transition strategy from emitting signal barrels without proving
    that *each* pair member has a nearby reference return.
    """
    if diagnostics is not None:
        diagnostics.update(schema=1, center_mm=list(center),
            signal_points_mm=[list(point) for point in signal_points],
            return_reach_mm=float(return_reach_mm), checked=0,
            rejection_counts={}, witnesses=[], added_at_mm=[])

    def reject(reason, point, evidence=None):
        if diagnostics is None:
            return
        counts = diagnostics["rejection_counts"]
        counts[reason] = counts.get(reason, 0) + 1
        if len(diagnostics["witnesses"]) < 12:
            diagnostics["witnesses"].append(dict(
                at_mm=[round(value, 6) for value in point],
                reason=reason, evidence=evidence))

    gnd = board.FindNet("GND")
    if gnd is None:
        return [], "board has no GND net"
    if reference_contact is None:
        from cec_return_plane_preview import candidate_contact_filter
        reference_contact = candidate_contact_filter(board)
    signal_points = tuple(signal_points) or (tuple(center),)
    if diagnostics is not None:
        diagnostics["signal_points_mm"] = [list(point) for point in signal_points]

    def existing_gnd_vias():
        return [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"
                and item.GetNetname() == "GND"
                and item.GetViaType() == pcbnew.VIATYPE_THROUGH
                and (reference_contact is None or reference_contact(
                        (item.GetPosition().x/MM,item.GetPosition().y/MM),
                        item.GetWidth(item.TopLayer())/MM))]

    def covered(points, vias):
        return [point for point in points if any(
            math.dist(
                point,
                (via.GetPosition().x / MM, via.GetPosition().y / MM))
            <= float(return_reach_mm) + 1e-9
            for via in vias)]

    uncovered = [point for point in signal_points
                 if point not in covered(signal_points, existing_gnd_vias())]
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
    radius_land = float(via_diameter_mm) / 2.0
    corridor_half = ((2.0 * float(width) + float(gap)) / 2.0
                     + radius_land + float(clearance))
    candidates = []
    # Dense passive rings often leave only an oblique return pocket.  Search a
    # fine, still-finite field out to the caller's per-member reach instead of
    # assuming four cardinal/diagonal seats within 1.45 mm of the midpoint.
    maximum_radius = max(1.45, float(return_reach_mm)
                         + math.dist(signal_points[0], center))
    radii = tuple(value / 100.0 for value in range(
        90, int(math.ceil(100.0 * maximum_radius)) + 1, 15))
    for radius in radii:
        for step_index in range(16):
            angle = pair_angle + step_index * math.pi / 8.0
            delta = (radius * math.cos(angle), radius * math.sin(angle))
            route_rank = (_return_via_route_rank(
                delta, route_unit, corridor_half, portal_side)
                if route_unit is not None else (0, 0.0))
            candidates.append((route_rank, radius, step_index, delta))
    added = []
    while uncovered:
        legal = []
        # Every seat in this field sees identical copper. Reuse the exact
        # per-layer/pad indexes only until a selected via mutates the board;
        # the next iteration must build a fresh snapshot. Global caching here
        # would miss copper emitted by the preceding signal/return portal.
        foreign_cache = {}
        # Drill spacing has the same immutable-field lifetime as the copper
        # indexes. Rewalking every native track at every seat dominated pair
        # return search. Keep scalar hole geometry only, and rebuild after
        # each selected via; the guard still performs its exact drill test.
        via_holes = cec_fr._via_hole_snapshot(board)
        for route_rank, radius, step_index, delta in sorted(candidates):
            if _deadline_expired(deadline):
                if diagnostics is not None:
                    diagnostics["deadline_exhausted"] = True
                return added, "pair-return search deadline exhausted"
            point = (center[0] + delta[0], center[1] + delta[1])
            if diagnostics is not None:
                diagnostics["checked"] += 1
            if (point[0] - radius_land < left + 0.5
                    or point[0] + radius_land > right - 0.5
                    or point[1] - radius_land < top + 0.5
                    or point[1] + radius_land > bottom - 0.5):
                reject("board_edge", point)
                continue
            hits = [signal for signal in uncovered
                    if math.dist(signal, point)
                    <= float(return_reach_mm) + 1e-9]
            if not hits:
                reject("member_reach", point)
                continue
            if reference_contact is not None and not reference_contact(point,via_diameter_mm):
                reject("reference_plane_contact", point)
                continue
            at = _v(*point)
            spot_evidence = {} if diagnostics is not None else None
            if not cec_fr._via_spot_clear(
                    board, at, _nm(via_diameter_mm), _nm(clearance),
                    {gnd_code}, drill_nm=_nm(via_drill_mm),
                    net_code=gnd_code, foreign_cache=foreign_cache,
                    _via_holes=via_holes,
                    **({"report": spot_evidence} if diagnostics is not None else {})):
                reject((spot_evidence or {}).get("reason", "native_via_guard"),
                       point, spot_evidence)
                continue
            legal.append((-len(hits), route_rank, radius, step_index,
                          point, hits))
        if not legal:
            if not refine:
                return added, (
                    "no legal GND return via within %.2fmm of every pair member"
                    % return_reach_mm)
            # A greedy one-member seat can consume the other member's drill
            # space. Release only this field's new vias before the finite
            # simultaneous refinement; inherited returns remain immutable.
            if diagnostics is not None:
                diagnostics["discarded_radial_at_mm"] = list(
                    diagnostics["added_at_mm"])
                diagnostics["added_at_mm"] = []
            _discard_items(board, added)
            remaining = [point for point in signal_points if point not in
                         covered(signal_points, existing_gnd_vias())]
            return _refine_pair_transition_returns(
                board, center, pair_vector, remaining,
                route_axis=route_axis, portal_side=portal_side,
                width=width, gap=gap, clearance=clearance,
                via_diameter_mm=via_diameter_mm, via_drill_mm=via_drill_mm,
                return_reach_mm=return_reach_mm, reference_contact=reference_contact,
                diagnostics=diagnostics, deadline=deadline, rejection=reject)
        (_neg_hits, _route_rank, _radius, _step, point, hits) = min(legal)
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(_v(*point))
        via.SetWidth(_nm(via_diameter_mm))
        via.SetDrill(_nm(via_drill_mm))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(gnd_code)
        board.Add(via)
        added.append(via)
        if diagnostics is not None:
            diagnostics["added_at_mm"].append(list(point))
        uncovered = [signal for signal in uncovered if signal not in hits]
    return added, "added"


def _add_pair_transition_returns_with_land_fallback(
        board, center, pair_vector, *, via_diameter_mm=0.60,
        via_drill_mm=0.30, diagnostics=None, deadline=None, **kwargs):
    """Try at most two NEW return lands; every failed field is rolled back.

    The preferred drill is immutable across the menu. No source object is
    resized, and a deadline/refusal cannot leak a partial preferred field into
    the smaller-land attempt. Exact native guards and the same return reach,
    reference filter and shared deadline apply to both geometries.
    """
    menu = cec_fab_profile.pair_return_via_geometry_candidates(
        board, via_diameter_mm, via_drill_mm)
    parent_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    attempts = []
    status = "pair-return search deadline exhausted"

    def release_field():
        _discard_items(board, [item for item in board.GetTracks()
            if item.m_Uuid.AsString() not in parent_ids])

    def record(evidence, selected=None):
        if diagnostics is not None:
            diagnostics.update(evidence, geometry_menu=list(menu),
                geometry_attempts=attempts, selected_geometry=selected,
                drill_preserved_across_menu=True,
                current_capacity_qualification=False)

    for geometry in menu:
        if _deadline_expired(deadline):
            break
        evidence = {}
        try:
            added, status = _add_pair_transition_returns(
                board, center, pair_vector,
                via_diameter_mm=geometry["diameter_mm"],
                via_drill_mm=geometry["drill_mm"], diagnostics=evidence,
                deadline=deadline, **kwargs)
        except Exception:
            release_field()
            raise
        attempts.append(dict(geometry=geometry, status=status, evidence=evidence))
        if status in ("covered", "added"):
            record(evidence, geometry if added else None)
            return added, status
        release_field()
        if status == "board has no GND net":
            break
    record(attempts[-1]["evidence"] if attempts else {})
    if _deadline_expired(deadline):
        status = "pair-return search deadline exhausted"
    return [], status


def _refine_pair_transition_returns(
        board, center, pair_vector, signal_points, *, route_axis, portal_side,
        width, gap, clearance, via_diameter_mm, via_drill_mm,
        return_reach_mm, reference_contact, diagnostics, deadline, rejection):
    """Qualify a complete bounded local field after radial seats fail.

    The finer proposal lattice does not change any physical guard. Select all
    required seats before committing, then recheck the native hole/copper
    geometry after each addition. A failed partial field never survives.
    """
    from cec_pair_return_field import refined_seats, covering_seats
    if not signal_points:
        return [], "covered"
    field = refined_seats(center, pair_vector, signal_points,
                          reach_mm=float(return_reach_mm))
    if diagnostics is not None:
        diagnostics["refinement"] = {key:field[key] for key in (
            "pitch_mm", "sampled_domain_complete", "omitted_sites", "sampled_only")}
        diagnostics["refinement"]["proposed_seats"] = len(field["sites"])
    gnd_code = int(board.FindNet("GND").GetNetCode())
    bounds = board.GetBoardEdgesBoundingBox()
    radius = float(via_diameter_mm) / 2.0
    corridor_half = ((2 * float(width) + float(gap)) / 2
                     + radius + float(clearance))
    foreign_cache, holes = {}, cec_fr._via_hole_snapshot(board)
    legal = []
    for seat in field["sites"]:
        if _deadline_expired(deadline):
            if diagnostics is not None:
                diagnostics["deadline_exhausted"] = True
            return [], "pair-return search deadline exhausted"
        point = seat["at_mm"]
        if diagnostics is not None:
            diagnostics["checked"] += 1
        if (point[0] - radius < bounds.GetLeft() / MM + .5
                or point[0] + radius > bounds.GetRight() / MM - .5
                or point[1] - radius < bounds.GetTop() / MM + .5
                or point[1] + radius > bounds.GetBottom() / MM - .5):
            rejection("board_edge", point)
            continue
        if reference_contact is not None and not reference_contact(point, via_diameter_mm):
            rejection("reference_plane_contact", point)
            continue
        evidence = {} if diagnostics is not None else None
        reasons = {}
        if not cec_fr._via_spot_clear(board, _v(*point), _nm(via_diameter_mm),
                _nm(clearance), {gnd_code}, drill_nm=_nm(via_drill_mm),
                net_code=gnd_code, foreign_cache=foreign_cache, _via_holes=holes,
                refusal_counts=reasons,
                **({"report": evidence} if diagnostics is not None else {})):
            rejection(next(iter(reasons), "native_via_guard"), point, evidence)
            continue
        delta = (point[0] - center[0], point[1] - center[1])
        rank = (_return_via_route_rank(delta, route_axis, corridor_half, portal_side)
                if route_axis is not None else (0, 0))
        legal.append(dict(seat, route_rank=rank))
    legal.sort(key=lambda row:(-len(row["hits"]), row["route_rank"],
                               row["radius_mm"], row["grid"]))
    selection = covering_seats(legal, len(signal_points), minimum_spacing_mm=(
        float(via_drill_mm) + board.GetDesignSettings().m_HoleToHoleMin / MM))
    if diagnostics is not None:
        diagnostics["refinement"].update(legal_seats=len(legal),
            checked_pairs=selection["checked_pairs"],
            search_inconclusive=selection["search_inconclusive"])
    if not selection["selected"]:
        return [], ("pair-return search budget exhausted" if selection["search_inconclusive"] else
            "no legal GND return via within %.2fmm of every pair member" % return_reach_mm)
    added = []
    for seat in selection["selected"]:
        at = _v(*seat["at_mm"])
        if (_deadline_expired(deadline) or not cec_fr._via_spot_clear(
                board, at, _nm(via_diameter_mm), _nm(clearance), {gnd_code},
                drill_nm=_nm(via_drill_mm), net_code=gnd_code)):
            _discard_items(board, added)
            if diagnostics is not None and _deadline_expired(deadline):
                diagnostics["deadline_exhausted"] = True
            return [], ("pair-return search deadline exhausted" if _deadline_expired(deadline)
                        else "refined return field failed native mutation recheck")
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(at); via.SetWidth(_nm(via_diameter_mm))
        via.SetDrill(_nm(via_drill_mm)); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(gnd_code); board.Add(via); added.append(via)
    if diagnostics is not None:
        diagnostics["added_at_mm"] = [list(row["at_mm"]) for row in selection["selected"]]
    return added, "added"


def _paired_portal_candidates(p_start, n_start, p_end, n_end, *,
                              width, gap, portal_separation=None, minimum_lead_mm=1.3):
    """Reduce dissimilar package pin fields to aligned pair portals.

    A wide connector pair and a compact IC pair are not useful endpoints for
    one global coupled-path search: the router must both converge the first
    pin field and discover the board-scale corridor at once.  Enumerate a
    bounded, package-agnostic set of octilinear portals instead.  Local exact
    fan-in proves each portal independently; a later shared-centreline search
    joins only compatible P/N lane orderings.
    """
    if (type(minimum_lead_mm) not in (int,float) or not math.isfinite(minimum_lead_mm)
            or not .1 <= minimum_lead_mm <= 1.3):
        raise ValueError('bounded_explicit_pair_portal_lead_required')
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
                    1.5, -1.5, 2.0, -2.0, 3.0, -3.0)

    def side_rows(side, actual_p, actual_n, budget):
        # At 45 degrees the axial distance needed to converge two pins to the
        # routed pair separation is approximately half their excess spread.
        # Keep a small tolerance for diagonal/native pad geometry, but never
        # spend exact dogbone search on a portal that is physically too close
        # to seat the convergence.
        minimum_lead = max(
            float(minimum_lead_mm),
            0.5 * (_dist(actual_p, actual_n)
                   - (float(width) + float(gap))) - 0.15)
        budget_value = round(float(budget), 6)
        rows = {1: [], -1: []}
        preferred_direction = 1.0 if side == "start" else -1.0
        anchor = start_center if side == "start" else end_center
        # A forward launch must stop before the peer-side portal, but a reverse
        # launch heads away from that midpoint and is bounded by the package
        # escape budget instead.  Using the forward cap for both directions
        # silently removed every legal candidate for a wide terminal close to
        # a compact device.
        # A package escape need not point at the other package. Restricting
        # this menu to forward/reverse excluded ordinary sideways pin-field
        # breakouts before exact routing even began. Enumerate the eight legal
        # headings in the *local* traversal frame; never exchange P/N names.
        for heading_step in (0, 4, 1, -1, 2, -2, 3, -3):
            angle = heading_step * math.pi / 4.0
            cs, sn = math.cos(angle), math.sin(angle)
            hx = preferred_direction * (ux * cs - uy * sn)
            hy = preferred_direction * (ux * sn + uy * cs)
            hx, hy = (0.0 if abs(v) < 1e-12 else v for v in (hx, hy))
            reverse_launch = cs < -1e-9
            direction_limit = (min(budget_value, max_lead / cs)
                               if cs > 1e-9 else budget_value)
            # Standard whole-millimetre depths cover most packages, but short
            # spans can leave a narrow legal interval.  Seed its boundaries
            # and midpoint so the finite search cannot jump over that window.
            interval_midpoint = round(
                (minimum_lead + direction_limit) / 2.0, 6)
            # A source-ribbon splice is not a dissimilar package escape.
            # Explicit short-lead proposals may find a legal transition in
            # the local throat before a 1.3 mm lead overshoots it. This only
            # enumerates seats: all exact fan-in, drill, clearance, return,
            # coupling and saved whole-pair receivers remain mandatory.
            local_leads=(minimum_lead_mm,.35,.5,.8) if minimum_lead_mm<1.3 else ()
            leads = sorted({
                value for value in (
                    1.3, 2.0, 3.0, 4.0, 5.0, 6.0,
                    round(minimum_lead, 6), interval_midpoint,
                    round(direction_limit, 6),
                    round(budget_value - 0.5, 6), budget_value,*local_leads)
                if (minimum_lead - 1e-9
                    <= value <= direction_limit + 1e-9)})
            for lead in leads:
                for lateral in lateral_rows:
                    local_nx, local_ny = -hy, hx
                    center = (
                        anchor[0] + hx * lead + local_nx * lateral,
                        anchor[1] + hy * lead + local_ny * lateral)
                    # The local vector is the pad-to-portal heading. The shared
                    # ribbon traverses that heading at the start and its
                    # inverse at the end.  Orient the portal P/N ordering in
                    # that traversal frame so a one-sided reverse launch does
                    # not silently request a crossover.
                    traversal_sign = 1.0 if side == "start" else -1.0
                    for sign in (1, -1):
                        lane_offset = offset * sign * traversal_sign
                        rows[sign].append({
                            "side": side, "sign": sign,
                            "lead_mm": round(lead, 6),
                            "lateral_mm": round(lateral, 6),
                            "reverse_launch": bool(reverse_launch),
                            "escape_heading_step": heading_step,
                            "route_heading": (hx, hy),
                            "center": center,
                            "p": (center[0] + local_nx * lane_offset,
                                  center[1] + local_ny * lane_offset),
                            "n": (center[0] - local_nx * lane_offset,
                                  center[1] - local_ny * lane_offset),
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


def _fair_portal_screen_order(rows, score_key):
    """Interleave launch direction and escape length before local depth.

    Dense packages commonly reject every via or dogbone at the shortest lead
    while a 3--6 mm portal is ordinary and clear.  Pure length ordering spends
    a bounded endpoint budget on dozens of near-identical 1.3 mm candidates.
    Round-robin exact rows by lead and forward/reverse topology, retaining the
    caller's deterministic score within each finite bucket.
    """
    buckets = {}
    for row in rows:
        key = (round(float(row.get("lead_mm", 0.0)), 6),
               bool(row.get("reverse_launch")),
               int(row.get("escape_heading_step", 0)))
        buckets.setdefault(key, []).append(row)
    for bucket in buckets.values():
        bucket.sort(key=score_key)
        # Length preference must not exhaust a finite budget on one physical
        # P/N order.  The propagated trunk can later require the other order;
        # reverse launch also changes its relation to the logical sign.  Use
        # actual endpoint geometry and interleave both orders inside each
        # depth/direction bucket before the outer fair-depth sweep.
        orders = {}
        for row in bucket:
            if row.get("p") is None or row.get("n") is None:
                order = 0
            else:
                dx = row["n"][0] - row["p"][0]
                dy = row["n"][1] - row["p"][1]
                axis = dx if abs(dx) >= abs(dy) else dy
                order = 1 if axis >= 0 else -1
            orders.setdefault(order, []).append(row)
        if len(orders) > 1:
            bucket[:] = [values[index]
                         for index in range(max(map(len, orders.values())))
                         for values in orders.values()
                         if index < len(values)]
    bucket_order = sorted(buckets, key=lambda key: (key[0], key[1]))
    ordered = []
    for index in range(max((len(bucket) for bucket in buckets.values()),
                           default=0)):
        for key in bucket_order:
            bucket = buckets[key]
            if index < len(bucket):
                ordered.append(bucket[index])
    return ordered


def _symmetry_seeded_portal_screen_order(rows, proven):
    """Try exact peer-endpoint topologies before the remaining fair order.

    Equal-pitch connectors often need the same lead, lateral magnitude, and
    forward/reverse escape at both ends of a trunk.  Once one endpoint has
    proved such a topology, restarting its peer at tiny generic offsets wastes
    most of a pair-wide deadline.  This function changes only proposal order;
    every seeded row still passes the complete local geometry screen.
    """
    wanted = {
        (round(float(row.get("lead_mm", 0.0)), 6),
         round(abs(float(row.get("lateral_mm", 0.0))), 6),
         bool(row.get("reverse_launch")))
        for row in (proven or ())
    }
    if not wanted:
        return list(rows)

    def matches(row):
        key = (round(float(row.get("lead_mm", 0.0)), 6),
               round(abs(float(row.get("lateral_mm", 0.0))), 6),
               bool(row.get("reverse_launch")))
        return key in wanted

    rows = list(rows)
    return ([row for row in rows if matches(row)]
            + [row for row in rows if not matches(row)])


def _portal_combination_score(start, end):
    """Rank a pair of already-proved endpoint fan-ins.

    The endpoint solver's score includes exact package geometry and heading
    quality.  Replacing it with total fan-in length caused a shorter but
    topologically awkward portal pair to consume every board-scale A* attempt,
    even when the two individually best fan-ins formed a direct corridor.
    Preserve forward launches as the first topology, then trust each exact
    endpoint rank before using total length and lateral motion as tie-breakers.
    """
    reverse_count = (int(bool(start.get("reverse_launch")))
                     + int(bool(end.get("reverse_launch"))))
    return (
        reverse_count,
        tuple(start.get("score") or ()),
        tuple(end.get("score") or ()),
        round(float(start.get("fanin_length_mm", 0.0))
              + float(end.get("fanin_length_mm", 0.0)), 6),
        round(abs(float(start.get("lateral_mm", 0.0)))
              + abs(float(end.get("lateral_mm", 0.0))), 6),
    )


def _pair_edge_detour_ratio(endpoints, routed_length_mm):
    """Return routed mean-member length over the direct member lower bound."""
    p_start, p_end, n_start, n_end = endpoints
    direct = (_dist(p_start, p_end) + _dist(n_start, n_end)) / 2.0
    if direct <= 1e-9:
        return None
    return float(routed_length_mm) / direct


def _pair_quantized_construction_gap(gap, reserve_nm=4):
    """Outward construction margin; never a native-clearance exemption."""
    if (type(gap) not in (int, float) or not math.isfinite(gap) or gap < 0
            or isinstance(reserve_nm, bool) or not isinstance(reserve_nm, int)
            or not 0 <= reserve_nm <= 16):
        raise ValueError('bounded_integer_pair_quantization_reserve_required')
    return gap + reserve_nm / MM


def _grid_coupled_path(board, *, start_center, end_center, p_start, n_start,
                       p_end, n_end, layer_id, width, gap, clearance, own,
                       avoid=(), step=0.5, start_sign=1.0, end_sign=1.0,
                       launch_distance=1.25, start_lead=1.0, end_lead=3.0,
                       start_lateral=0.0, end_lateral=0.0,
                       initial_turn_steps=0, terminal_turn_steps=0,
                       portal_mode=False,
                       portal_start_heading=None, portal_end_heading=None,
                       deadline=None, diagnostics=None,
                       max_visited=120000,
                       foreign_shape_cache=None,
                       path_validator=None,
                       edge_validator=None,
                       strict_taper_continuation=False,
                       quantization_reserve_nm=4, pair_net_codes=None):
    """Find an obstacle-aware octilinear corridor and split it into a pair.

    The A* search guards a single envelope whose width is exactly two trace
    widths plus the requested copper gap.  Therefore every accepted centreline
    has room for both offset members, while direction state and bend penalties
    keep the result short and conventionally 0/45/90 degree.  Exact member
    geometry is rechecked before anything is committed.
    """
    # A diagonal offset cannot always represent its theoretical minimum
    # spacing on the integer-nanometre lattice. Construct slightly wider
    # copper, rather than waiving a below-minimum native clearance afterward.
    # Fixed package/via portals and their nominal taper policy are unchanged.
    constructed_gap = _pair_quantized_construction_gap(gap, quantization_reserve_nm)
    corridor_width = 2.0 * width + constructed_gap
    width_nm = _nm(corridor_width)
    member_half_nm = _nm(width) // 2
    clearance_nm = _nm(clearance)
    # Both nets are intentionally absent from the foreign envelope. Snapshot
    # their native partner copper separately; never infer lane identity from
    # an unordered exclusion set, and never carry this snapshot across edits.
    member_guard = None
    try:
        if pair_net_codes is None:
            if own:
                raise ValueError('explicit_native_pair_net_codes_required')
        else:
            from cec_pair_member_obstacles import MemberObstacles
            if set(pair_net_codes) != set(own):
                raise ValueError('native_pair_codes_must_match_excluded_nets')
            member_guard = MemberObstacles(board, layer_id, pair_net_codes)
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.update(status='member_guard_snapshot_refused',
                               error=str(exc), visited=0)
        return None
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
        # Package pin rows may be rotated or carry tiny placement rounding.
        # Their mathematical normal is therefore not a legal trace heading.
        # Snap the *route* launch to the nearest octilinear direction while
        # retaining the package geometry only to choose its polarity.  Keep a
        # requested lateral search displacement perpendicular to that snapped
        # heading; the joint endpoint solver owns the canonical pad-to-lane
        # fan-in, so the centreline does not need a raw diagonal here.
        raw_directions = ((1, 0), (1, 1), (0, 1), (-1, 1),
                          (-1, 0), (-1, -1), (0, -1), (1, -1))
        direction = max(raw_directions, key=lambda row: (
            (tx * row[0] + ty * row[1]) / math.hypot(*row)))
        tx, ty = (direction[0] / math.hypot(*direction),
                  direction[1] / math.hypot(*direction))
        lx, ly = -ty, tx
        if lx * ax + ly * ay < 0:
            lx, ly = -lx, -ly
        return ((center[0] + tx * distance + lx * lateral,
                 center[1] + ty * distance + ly * lateral),
                (tx, ty))

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
        default_vector = (end_center[0] - start_center[0],
                          end_center[1] - start_center[1])
        start_vector = (tuple(portal_start_heading)
                        if portal_start_heading is not None
                        else default_vector)
        end_vector = (tuple(portal_end_heading)
                      if portal_end_heading is not None
                      else default_vector)
    else:
        route_start, start_vector = launch(
            start_center, p_start, n_start, end_center, start_sign,
            float(launch_distance), float(start_lateral))
        route_end, end_heading = launch(
            end_center, p_end, n_end, start_center, end_sign,
            float(launch_distance), float(end_lateral))
        end_vector = (-end_heading[0], -end_heading[1])

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
    portal_goal_offset = None
    if portal_mode and _dist(point(goal), end_center) > 1e-9:
        # The common grid is anchored at the exact start portal, so the end
        # portal is normally fractional.  Nearest-cell rounding can place the
        # goal *behind* the end's outward runway; the final taper would then
        # need a U-turn even though A* obeyed its sampled terminal heading.
        # Select the nearest deterministic cell in the outward half-plane.
        raw_x = (grid_end[0] - origin[0]) / step
        raw_y = (grid_end[1] - origin[1]) / step
        x_values = range(math.floor(raw_x) - 1, math.ceil(raw_x) + 2)
        y_values = range(math.floor(raw_y) - 1, math.ceil(raw_y) + 2)
        outward = (-float(end_vector[0]), -float(end_vector[1]))
        outward_length = math.hypot(*outward) or 1.0
        ux, uy = outward[0] / outward_length, outward[1] / outward_length
        nx, ny = -uy, ux
        candidates = []
        for ix in x_values:
            for iy in y_values:
                candidate = point((ix, iy))
                delta = (candidate[0] - end_center[0],
                         candidate[1] - end_center[1])
                forward = delta[0] * ux + delta[1] * uy
                if forward <= 1e-9:
                    continue
                if not (x_min <= candidate[0] <= x_max
                        and y_min <= candidate[1] <= y_max):
                    continue
                lateral = abs(delta[0] * nx + delta[1] * ny)
                candidates.append((
                    math.hypot(*delta), lateral, forward, ix, iy))
        if candidates:
            _, _, _, goal_x, goal_y = min(candidates)
            goal = (goal_x, goal_y)
            chosen = point(goal)
            portal_goal_offset = {
                "requested_mm": [round(float(value), 6)
                                 for value in end_center],
                "selected_mm": [round(float(value), 6)
                                for value in chosen],
                "distance_mm": round(_dist(chosen, end_center), 6),
                "forward_projection_mm": round(
                    (chosen[0] - end_center[0]) * ux
                    + (chosen[1] - end_center[1]) * uy, 6),
            }
            if diagnostics is not None:
                diagnostics["portal_goal_offset"] = portal_goal_offset
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
    member_masks = {}
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
        # Reversing traversal reverses which member occupies each side.
        cache_key = ((a, b) if member_guard is not None else
                     ((a, b) if a <= b else (b, a)))
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
        learned_edge_clear = (edge_validator(pa, pb)
                              if edge_validator is not None else True)
        foreign_clear = endpoint_escape or exact_clear(pa, pb)
        if (not foreign_clear and portal_mode and member_guard is not None
                and (a == start or b == goal)):
            # A centreline capsule overstates the axial end-cap radius of
            # two finite offset traces. Refine only the actual terminal edge
            # against the SAME native foreign snapshot, at unchanged member
            # widths and clearance. Interior corridor/miters, board material,
            # reservations and ordered partner masks are not bypassed.
            from cec_pair_terminal_caps import clear as terminal_caps_clear
            foreign_clear = terminal_caps_clear(pa,pb,width_mm=width,
                gap_mm=constructed_gap,clearance_nm=clearance_nm,
                zone_rows=zone_rows,copper_rows=copper_rows)
            if foreign_clear and diagnostics is not None:
                diagnostic_counts['exact_native_terminal_caps_clear'] = (
                    diagnostic_counts.get('exact_native_terminal_caps_clear',0)+1)
        member_mask = (member_guard.corridor_mask(
            pa, pb, width, constructed_gap, clearance)
            if member_guard is not None else 3)
        member_masks[(a, b)] = member_mask
        ok = (in_bounds and material_clear and not reservation_ref
              and learned_edge_clear and foreign_clear and bool(member_mask))
        if not ok:
            if not in_bounds:
                record_rejection("board_bounds", pa, pb)
            elif not material_clear:
                record_rejection("board_material", pa, pb)
            elif reservation_ref:
                record_rejection(
                    "reservation_barrier", pa, pb,
                    reservation_hits=reservation_hits)
            elif not learned_edge_clear:
                record_rejection("learned_self_conflict", pa, pb)
            elif not foreign_clear:
                record_rejection("foreign_copper", pa, pb)
                record_foreign_blockers(pa, pb)
            elif not member_mask:
                record_rejection("established_partner_copper", pa, pb)
        edge_cache[cache_key] = ok
        return ok

    from cec_pair_bend_state import advance as advance_pair_bend, run_caps
    bend_run_caps = run_caps(step, width + constructed_gap)
    # Direction alone merges physically different prefixes: a short run
    # between equal-sense miters may reverse an offset member. Retain only
    # the finite signed-turn/run history needed to distinguish those states.
    initial_member_mask = 3
    if member_guard is not None and portal_mode:
        ux, uy = directions[start_direction]
        length = math.hypot(ux, uy)
        offset = (width + constructed_gap)/2
        plus_start = (route_start[0]-uy/length*offset,
                      route_start[1]+ux/length*offset)
        minus_start = (route_start[0]+uy/length*offset,
                       route_start[1]-ux/length*offset)
        initial_member_mask = (1 if
            _dist(plus_start,p_start)+_dist(minus_start,n_start) <=
            _dist(minus_start,p_start)+_dist(plus_start,n_start) else 2)
    initial = (start[0], start[1], start_direction, 0, 0, initial_member_mask)
    if start != goal:
        from cec_pair_heading_boundary import feasible_edges
        start_edges=feasible_edges(start,start_direction,min(1,int(initial_turn_steps)),edge_clear)
        end_edges=feasible_edges(goal,goal_direction,terminal_turn_steps,edge_clear,incoming=True)
        if diagnostics is not None:
            diagnostics['endpoint_heading_edges']={'start':start_edges,'end':end_edges}
        if not start_edges or not end_edges:
            if diagnostics is not None:
                diagnostics.update(status=('initial_heading_blocked' if not start_edges
                                           else 'terminal_heading_blocked'),visited=0,
                                   max_visited=max(1,int(max_visited)),
                                   blocked_endpoint=('start' if not start_edges else 'end'))
                flush_diagnostics()
            return None
    queue = [(0.0, 0.0, initial)]
    cost = {initial: 0.0}
    parent = {}
    terminal = None
    visited = 0
    nearest_state = initial
    reached_goal_headings = set()
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
        goal_turn = min(abs(state[2] - goal_direction),
                        len(directions) - abs(state[2] - goal_direction))
        if node == goal:
            reached_goal_headings.add(state[2])
        if node == goal and goal_turn <= int(terminal_turn_steps):
            if advance_pair_bend(*state[2:5], goal_direction, bend_run_caps) is None:
                continue
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
            next_bend = advance_pair_bend(
                *state[2:5], direction_index, bend_run_caps)
            if next_bend is None:
                record_rejection("pair_miter_run_too_short", point(node),
                                 point((node[0] + dx, node[1] + dy)))
                continue
            nxt = (node[0] + dx, node[1] + dy)
            if not edge_clear(node, nxt):
                continue
            member_mask = state[5] & member_masks.get((node, nxt), 3)
            if not member_mask:
                record_rejection('inconsistent_pair_lane_identity', point(node), point(nxt))
                continue
            travel = step * (math.sqrt(2.0) if dx and dy else 1.0)
            # A half-grid turn surcharge was cheaper than one pair-envelope
            # width, so A* routinely preferred two adjacent 45-degree turns
            # over a slightly longer straight run.  The centreline itself was
            # legal, but offsetting it produced an S-jog where one member came
            # within 0.23 mm of another part of the opposite member on a
            # 0.54-mm-centre-spacing USB pair.  Price a turn by the physical
            # envelope it must carry.  This remains a soft cost (tight escapes
            # are still searchable) while making conventional long straights
            # and sparse 45-degree bends win deterministically.
            bend = (0.0 if state[2] in (-1, direction_index)
                    else max(0.35, 2.0 * corridor_width))
            new_cost = current_cost + travel + bend
            nxt_state = (nxt[0], nxt[1], direction_index, *next_bend, member_mask)
            if new_cost >= cost.get(nxt_state, float("inf")):
                continue
            cost[nxt_state] = new_cost
            parent[nxt_state] = state
            heuristic = math.hypot(nxt[0] - goal[0], nxt[1] - goal[1]) * step
            heapq.heappush(queue, (new_cost + heuristic, new_cost, nxt_state))
    if terminal is None:
        if diagnostics is not None:
            # A zero-distance frontier can still have the wrong approach
            # direction. Report the finite geometric witness, not "no path"
            # or an admitted route. It lets a caller choose a new terminal
            # throat without repeatedly searching the same blocked heading.
            frontier_nodes = []
            frontier_state = nearest_state
            while len(frontier_nodes) < 512:
                frontier_nodes.append(point(frontier_state[:2]))
                if frontier_state == initial:
                    break
                frontier_state = parent[frontier_state]
            frontier_complete = frontier_state == initial
            frontier_nodes.reverse()
            frontier_compact = []
            for value in frontier_nodes:
                frontier_compact.append(value)
                while len(frontier_compact) >= 3:
                    a, b, c = frontier_compact[-3:]
                    if abs((b[0]-a[0])*(c[1]-b[1])
                           -(b[1]-a[1])*(c[0]-b[0])) > 1e-8:
                        break
                    frontier_compact.pop(-2)
            diagnostics.update({
                "status": "grid_exhausted", "visited": visited,
                "max_visited": max_visited,
                "edge_cache_entries": len(edge_cache),
                "clear_edges": sum(edge_cache.values()),
                "nearest_frontier_mm": [
                    round(float(value), 6)
                    for value in point((nearest_state[0], nearest_state[1]))],
                "frontier_gap_mm": round(nearest_goal_distance, 6),
                "nearest_frontier_heading": list(directions[nearest_state[2]]),
                "required_goal_heading": list(directions[goal_direction]),
                "reached_goal_headings": [list(directions[index])
                                          for index in sorted(reached_goal_headings)],
                "unadmitted_frontier_prefix_mm": [
                    [round(float(value), 6) for value in point_]
                    for point_ in frontier_compact[-128:]],
                "frontier_prefix_complete": frontier_complete and len(frontier_compact) <= 128,
                "no_path_proof": False,
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
    landing_bridge = []
    if not portal_mode:
        # The common lattice is rooted at the start runway.  Both coordinates
        # of the exact end runway can be fractional; appending grid_end here
        # made a raw diagonal residual even on an otherwise clear board.  A
        # forward octilinear bridge preserves both exact endpoints and the
        # required terminal heading. Native/member/envelope checks below are
        # still mandatory, and a reversed runway is never forced into place.
        from cec_pair_grid_landing import bridge
        landing_bridge = bridge(point(goal), route_end, end_vector)
        if landing_bridge is None:
            if diagnostics is not None:
                diagnostics.update(status='grid_landing_runway_refused',
                    visited=visited, rounded_goal_mm=list(point(goal)),
                    exact_runway_mm=list(route_end))
                flush_diagnostics()
            return None
        centres.extend(landing_bridge[1:])
        if diagnostics is not None:
            diagnostics['grid_goal_landing'] = dict(
                sampled_goal_mm=list(point(goal)),
                exact_grid_goal_mm=list(grid_end),
                exact_runway_mm=list(route_end),
                points_mm=[list(value) for value in landing_bridge],
                native_copper_authority=False)
    # In portal mode the rounded lattice goal generally differs from the exact
    # throat by a fraction of a grid cell.  Appending the exact point here can
    # manufacture a tiny reverse/non-octilinear terminal leg.  Offset the
    # legal lattice centreline first and let the dedicated exact portal taper
    # bridge that residual for both pair members.

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
            if (abs(cross) > 1e-8 or edge_validator is not None
                    and not edge_validator(a, c)):
                break
            compact.pop(-2)
    changed = True
    while changed and len(compact) >= 3:
        changed = False
        # Portal endpoints are fixed throat locations.  Their grid legs may
        # turn by one octilinear step when the package pin field blocks a
        # straight continuation; the exact taper below then lands the offset
        # ribbon on the supplied P/N points.  Keep those adjacent vertices out
        # of this broad simplifier so it cannot silently move the throat.
        first_index = 2 if portal_mode else 1
        stop_index = len(compact) - 2 if portal_mode else len(compact) - 1
        for index in range(first_index, stop_index):
            a, b, c = compact[index - 1:index + 2]
            ab, bc = _dist(a, b), _dist(b, c)
            if ab <= 1e-9 or bc <= 1e-9:
                compact.pop(index); changed = True; break
            dot = (((b[0] - a[0]) * (c[0] - b[0])
                    + (b[1] - a[1]) * (c[1] - b[1])) / (ab * bc))
            if (min(ab, bc) < 0.75 and dot > math.cos(math.radians(22.5))
                    and _segment_is_octilinear(a, c)
                    and (edge_validator is None or edge_validator(a, c))):
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
        return (_segment_is_octilinear(a, b)
                and cec_fr._edge_leg_clear(
                    board, _v(*a), _v(*b), width_nm // 2, edge_mm=0.5)
                and not _crosses_avoid([a, b], avoid, corridor_width)
                # Search reservations/no-goods are a construction boundary,
                # not merely an A* cost. Cleanup must not reintroduce the
                # learned bad corridor through a longer visible shortcut.
                and (edge_validator is None or edge_validator(a, b))
                and (member_guard is None or member_guard.corridor_mask(
                    a, b, width, constructed_gap, clearance) & terminal[5])
                and (endpoint_escape or exact_clear(a, b)))

    # These residual legs were not A* edges. Check the complete pair envelope
    # against real material, reservations, learned no-goods, retained member
    # copper and exact foreign copper before offsetting. Never use the broad
    # package-escape exception to bless a newly constructed landing.
    if any(not centre_leg_clear(a, b) or not exact_clear(a, b)
           for a, b in zip(landing_bridge, landing_bridge[1:])):
        if diagnostics is not None:
            diagnostics.update(status='grid_landing_envelope_refused',
                               visited=visited)
            flush_diagnostics()
        return None

    # A* optimizes the sampled centreline, but its direction-state graph can
    # retain a long staircase around a blocker after a later vertex has direct
    # line of sight.  Those needless parallel returns are especially harmful
    # to a differential pair: the two constant-offset members can then come
    # within the requested gap of a *different* part of their own route.  Run
    # an exact, obstacle-aware string pull over interior vertices before
    # offsetting.  Portal entry/exit legs remain fixed and every replacement
    # stays octilinear with no turn sharper than the original 45-degree limit.
    def turn_is_gentle(a, b, c):
        ab = (b[0] - a[0], b[1] - a[1])
        bc = (c[0] - b[0], c[1] - b[1])
        lab, lbc = math.hypot(*ab), math.hypot(*bc)
        if lab <= 1e-9 or lbc <= 1e-9:
            return True
        return ((ab[0] * bc[0] + ab[1] * bc[1]) / (lab * lbc)
                >= math.cos(math.radians(45.0)) - 1e-9)

    string_pulled = 0
    first_anchor = 1 if portal_mode else 0
    last_anchor = len(compact) - 2 if portal_mode else len(compact) - 1
    index = first_anchor
    while index < last_anchor - 1:
        replacement = None
        for target in range(last_anchor, index + 1, -1):
            if not _segment_is_octilinear(compact[index], compact[target]):
                continue
            if not centre_leg_clear(compact[index], compact[target]):
                continue
            candidate = (compact[:index + 1] + compact[target:])
            if (index > 0 and not turn_is_gentle(
                    candidate[index - 1], candidate[index],
                    candidate[index + 1])):
                continue
            if (index + 2 < len(candidate) and not turn_is_gentle(
                    candidate[index], candidate[index + 1],
                    candidate[index + 2])):
                continue
            replacement = candidate
            break
        if replacement is None:
            index += 1
            continue
        removed = len(compact) - len(replacement)
        if removed <= 0:
            index += 1
            continue
        compact = replacement
        string_pulled += removed
        last_anchor = len(compact) - 2 if portal_mode else len(compact) - 1

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
            reverse_bends = []
            for index in range(1, len(compact) - 1):
                a, b, c = compact[index - 1:index + 2]
                ab = (b[0] - a[0], b[1] - a[1])
                bc = (c[0] - b[0], c[1] - b[1])
                if ab[0] * bc[0] + ab[1] * bc[1] < -1e-9:
                    reverse_bends.append({
                        "index": index,
                        "points_mm": [[round(float(value), 6)
                                       for value in point]
                                      for point in (a, b, c)],
                    })
            diagnostics.update({
                "status": "centreline_reverse_bend", "visited": visited,
                "centre_vertices": len(compact),
                "reverse_bends": reverse_bends,
                "centreline_mm": [
                    [round(float(value), 6) for value in point]
                    for point in compact],
            })
            flush_diagnostics()
        return None
    offset = _offset_centerline(compact, (width + constructed_gap) / 2.0)
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

    def member_endpoint_clear(member, a, b):
        return (endpoint_segment_clear(a, b) and
                (member_guard is None or member_guard.clear(
                    member, a, b, width, clearance)))

    p_endpoint_clear = lambda a, b: member_endpoint_clear('p', a, b)
    n_endpoint_clear = lambda a, b: member_endpoint_clear('n', a, b)

    # Nearest-at-start is usually the correct member ordering, but a centre
    # GND pad in a flow-through package can topologically require the opposite
    # lane assignment.  Admit either orientation using the same exact guards.
    orientations = ((plus, minus), (minus, plus))
    if not plus_is_p:
        orientations = tuple(reversed(orientations))
    orientation_rejections = []
    for orientation_index, (p_mid, n_mid) in enumerate(orientations):
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
                start_taper_diagnostics = {}
                end_taper_diagnostics = {}
                start_taper = _portal_pair_taper_escape(
                    p_start, n_start, p_mid, n_mid,
                    width=width, gap=gap,
                    segment_clear=endpoint_segment_clear,
                    p_segment_clear=p_endpoint_clear,
                    n_segment_clear=n_endpoint_clear,
                    deadline=deadline,
                    max_middle_vertices=(
                        8 if strict_taper_continuation else 3),
                    require_forward_continuation=(
                        strict_taper_continuation),
                    portal_heading=start_vector,
                    diagnostics=start_taper_diagnostics)
                end_taper_from_portal = _portal_pair_taper_escape(
                    p_end, n_end, list(reversed(p_mid)),
                    list(reversed(n_mid)), width=width, gap=gap,
                    segment_clear=endpoint_segment_clear,
                    p_segment_clear=p_endpoint_clear,
                    n_segment_clear=n_endpoint_clear,
                    deadline=deadline,
                    max_middle_vertices=(
                        8 if strict_taper_continuation else 3),
                    require_forward_continuation=(
                        strict_taper_continuation),
                    portal_heading=(-end_vector[0], -end_vector[1]),
                    diagnostics=end_taper_diagnostics)
                if (start_taper is None
                        or end_taper_from_portal is None):
                    orientation_rejections.append({
                        "orientation": orientation_index,
                        "reason": "portal_taper_refused",
                        "alignment_error_mm": round(alignment_error, 6),
                        "start_taper_ok": start_taper is not None,
                        "end_taper_ok": end_taper_from_portal is not None,
                        "start_taper_diagnostics": start_taper_diagnostics,
                        "end_taper_diagnostics": end_taper_diagnostics,
                    })
                    if diagnostics is not None:
                        diagnostics.update({
                            "status": "portal_taper_refused",
                            "alignment_error_mm": round(
                                alignment_error, 6),
                            "start_taper_ok": start_taper is not None,
                            "end_taper_ok": (
                                end_taper_from_portal is not None),
                            "start_taper_diagnostics": (
                                start_taper_diagnostics),
                            "end_taper_diagnostics": (
                                end_taper_diagnostics),
                            "visited": visited,
                        })
                    continue
                middle_start_index = int(
                    start_taper["middle_index"])
                middle_end_index = (min(len(p_mid), len(n_mid)) - 1
                                    - int(end_taper_from_portal[
                                        "middle_index"]))
                if middle_start_index > middle_end_index:
                    orientation_rejections.append({
                        "orientation": orientation_index,
                        "reason": "portal_taper_overlap",
                        "alignment_error_mm": round(alignment_error, 6),
                        "start_middle_index": middle_start_index,
                        "end_middle_index": middle_end_index,
                        "start_taper_diagnostics": start_taper_diagnostics,
                        "end_taper_diagnostics": end_taper_diagnostics,
                    })
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
                p_segment_clear=p_endpoint_clear,
                n_segment_clear=n_endpoint_clear,
                max_detour=_pair_escape_budget(p_start, n_start),
                deadline=deadline)
            end_escape = _joint_endpoint_escape(
                p_mid[-1], n_mid[-1], p_end, n_end,
                width=width, gap=gap, segment_clear=endpoint_segment_clear,
                p_segment_clear=p_endpoint_clear,
                n_segment_clear=n_endpoint_clear,
                max_detour=_pair_escape_budget(p_end, n_end),
                deadline=deadline)
        if start_escape is None or end_escape is None:
            orientation_rejections.append({
                "orientation": orientation_index,
                "reason": "portal_escape_refused",
                "start_escape_ok": start_escape is not None,
                "end_escape_ok": end_escape is not None,
            })
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
        octilinear = (_polyline_is_octilinear(p_points)
                      and _polyline_is_octilinear(n_points))
        no_hairpin = not (_polyline_has_reverse_bend(p_points)
                          or _polyline_has_reverse_bend(n_points))
        external_validation = (member_guard.paths(
            p_points, n_points, width, clearance)
            if member_guard is not None else {"ok": True})
        if (material_clear and no_cross and min_clear and no_hairpin
                and octilinear and external_validation.get('ok')
                and path_validator is not None):
            external_validation = path_validator(p_points, n_points)
            if isinstance(external_validation, bool):
                external_validation = {"ok": external_validation}
            elif external_validation is None:
                external_validation = {"ok": False}
        if (material_clear and no_cross and min_clear and no_hairpin
                and octilinear and external_validation.get("ok", False)):
            if diagnostics is not None:
                diagnostics.update({
                    "status": "accepted", "visited": visited,
                    "centre_vertices": len(compact),
                    "member_vertices": [len(p_points), len(n_points)],
                    "octilinear": True,
                    "portal_taper": bool(
                        portal_mode and alignment_error > 1e-5),
                    "external_path_validation": external_validation,
                })
                flush_diagnostics()
            return p_points, n_points, sum(
                _dist(a, b) for a, b in zip(compact, compact[1:]))
        failed_material_segments = []
        if not material_clear:
            for member, points in (("p", p_points), ("n", n_points)):
                for a, b in zip(points, points[1:]):
                    if not cec_fr._edge_leg_clear(
                            board, _v(*a), _v(*b), member_half_nm,
                            edge_mm=0.5):
                        failed_material_segments.append({
                            "member": member,
                            "segment_mm": [[round(value, 6) for value in a],
                                           [round(value, 6) for value in b]],
                        })
                        if len(failed_material_segments) >= 8:
                            break
                if len(failed_material_segments) >= 8:
                    break
        orientation_rejections.append({
            "orientation": orientation_index,
            "reason": "offset_geometry_refused",
            "material_clear": material_clear,
            "no_cross": no_cross,
            "minimum_gap_clear": min_clear,
            "minimum_centerline_separation_mm": round(min(
                _seg_seg_dist(a, b, c, d)
                for a, b in zip(p_points, p_points[1:])
                for c, d in zip(n_points, n_points[1:])), 6),
            "required_centerline_separation_mm": round(width + gap, 6),
            "external_path_validation": external_validation,
            "centreline_mm": [
                [round(value, 6) for value in point]
                for point in compact[:64]],
            "no_hairpin": no_hairpin,
            "octilinear": octilinear,
            "failed_material_segments": failed_material_segments,
        })
        if os.environ.get("CEC_PAIR_DEBUG") == "1":
            print("[precision] pair grid offset geometry refused",
                  "material_clear=", material_clear,
                  "no_cross=", no_cross, "min_clear=", min_clear,
                  "no_hairpin=", no_hairpin,
                  "octilinear=", octilinear,
                      "P=", p_points, "N=", n_points, file=sys.stderr)
    if diagnostics is not None:
        diagnostics.setdefault("status", "offset_geometry_refused")
        validated_geometry_refusals = [r for r in orientation_rejections
            if r.get("reason") == "offset_geometry_refused"
            and all(r.get(k) for k in ("material_clear", "no_cross",
                "minimum_gap_clear", "no_hairpin", "octilinear"))
            and r.get("external_path_validation", {}).get("ok") is False]
        if validated_geometry_refusals:
            # The opposite lane orientation's subsequent taper rejection is
            # not the cause of refusing the geometrically valid orientation.
            diagnostics["status"] = "external_path_validation_refused"
            diagnostics["external_path_validation"] = validated_geometry_refusals[0][
                "external_path_validation"]
        diagnostics.update({
            "visited": visited, "centre_vertices": len(compact),
            "string_pulled_vertices": string_pulled,
            "orientation_rejections": orientation_rejections})
        flush_diagnostics()
    return None


def _route_prequalified_pair_portals(board, pair, start, end, *,
                                     layer="F.Cu", clearance=0.20,
                                     avoid=(), minimum_coupled_fraction=0.0,
                                     deadline=None,
                                     max_grid_visited=120000):
    """Connect two already-proven local pair throats exactly once.

    A multidrop junction synthesizer has already checked the package fan-in,
    lane order, and every local spoke.  Feeding its throat back through the
    generic package-portal search creates a second fan-in and can turn a
    straight connector backbone into a large reconvergent loop.  Search only
    the shared centreline here, retain the throat headings as hard boundary
    conditions, and taper a locally widened junction back to nominal pitch
    inside the normal portal-mode geometry authority.
    """
    clearance = _pair_clearance(board, pair, clearance)
    layer_id = board.GetLayerID(layer)
    if layer_id < 0:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "prequalified portal layer %s absent" % layer}
    if not _paired_portal_lane_compatible(start, end):
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": "prequalified portal lane order requires crossover",
            "portal_lane_compatible": False,
        }
    width, gap = float(pair["width"]), float(pair["gap"])
    p_code = board.GetNetcodeFromNetname(pair["p"])
    n_code = board.GetNetcodeFromNetname(pair["n"])
    own = {p_code, n_code}
    default_heading = (
        end["center"][0] - start["center"][0],
        end["center"][1] - start["center"][1])
    start_heading = tuple(start.get("route_heading") or default_heading)
    end_outward = tuple(end.get("route_heading") or (
        -default_heading[0], -default_heading[1]))
    end_heading = (-float(end_outward[0]), -float(end_outward[1]))
    attempts = []
    foreign_shape_cache = {}
    import cec_pair_pad_guard
    import cec_pair_field_search
    # Prefer exact throat continuation, then permit one octant of forward
    # steering when an obstacle blocks it.  The portal taper authority proves
    # the first emitted segment has non-negative projection on the existing
    # runway, so this relaxation cannot recreate the former 135-degree fold at
    # a composed local-star/trunk join.
    for allowed_turn_steps in (0, 1):
        if _deadline_expired(deadline):
            break
        diagnostics = {}
        grid = cec_pair_field_search.coupled_path(
            board, pair=pair,
            netclass_resolver=cec_fr._project_netclass_resolver(board.GetFileName())
                if board.GetFileName() else None,
            start_center=start["center"], end_center=end["center"],
            p_start=start["p"], n_start=start["n"],
            p_end=end["p"], n_end=end["n"],
            layer_id=layer_id, width=width, gap=gap,
            clearance=float(clearance), own=own,
            avoid=_avoid_for_layer(avoid, layer), step=0.5,
            initial_turn_steps=allowed_turn_steps,
            terminal_turn_steps=allowed_turn_steps,
            portal_mode=True, portal_start_heading=start_heading,
            portal_end_heading=end_heading, deadline=deadline,
            diagnostics=diagnostics, max_visited=max_grid_visited,
            foreign_shape_cache=foreign_shape_cache,
            path_validator=lambda pp,nn:cec_pair_pad_guard.paths(
                board,pair,pp,nn,layer_id=layer_id,clearance_mm=clearance),
            strict_taper_continuation=True)
        attempts.append({
            "allowed_turn_steps": int(allowed_turn_steps),
            "status": diagnostics.get(
                "status", "accepted" if grid is not None else "refused"),
            "visited": diagnostics.get("visited"),
            "frontier_gap_mm": diagnostics.get("frontier_gap_mm"),
            "reverse_bends": diagnostics.get("reverse_bends"),
            "centreline_mm": diagnostics.get("centreline_mm"),
            "alignment_error_mm": diagnostics.get("alignment_error_mm"),
            "start_taper_diagnostics": diagnostics.get(
                "start_taper_diagnostics"),
            "end_taper_diagnostics": diagnostics.get(
                "end_taper_diagnostics"),
            "orientation_rejections": diagnostics.get(
                "orientation_rejections"),
            "portal_goal_offset": diagnostics.get("portal_goal_offset"),
            "field_guidance": diagnostics.get("field_guidance"),
        })
        if grid is None:
            continue
        p_points, n_points, coupled_len = grid
        coupling = _polyline_coupling_coverage(
            p_points, n_points, width, gap)
        if (not _pair_min_clear(
                p_points, n_points, -1, -1, width, gap,
                strict_pair_gap=True)
                or coupling["fraction"] + 1e-9
                < float(minimum_coupled_fraction)):
            attempts[-1]["status"] = "post-grid pair contract refused"
            continue
        laid = _lay(board, p_code, p_points, _nm(width), layer_id)
        laid += _lay(board, n_code, n_points, _nm(width), layer_id)
        return {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "route_mode": "prequalified-junction-portal-grid",
            "layer": layer, "segments": len(laid),
            "length_mm": round(sum(
                _dist(a, b) for points in (p_points, n_points)
                for a, b in zip(points, points[1:])) / 2.0, 2),
            "coupled_len_mm": round(coupled_len, 2),
            "coupled_coverage_pct": coupling["coverage_pct"],
            "minimum_coupled_fraction": float(
                minimum_coupled_fraction),
            "prequalified_portal_attempts": attempts,
        }
    return {
        "name": pair["name"], "p": pair["p"], "n": pair["n"],
        "refused": "prequalified pair portal grid exhausted",
        "search_budget_exhausted": bool(_deadline_expired(deadline)),
        "prequalified_portal_attempts": attempts,
    }


def _route_coupled_via_portals(board, pair, endpoints, *, max_portal_refills=2,
                               early_portal_feedback=True,
                               cache_portal_negatives=True,
                               **kwargs):
    """Replenish a local escape beam using exhausted global-frontier evidence.

    The complete exact beam solver and its rollback remain authoritative.
    Successful baseline routes return unchanged. Refills share its original
    absolute deadline and are bounded independently of candidate success.
    """
    from cec_portal_feedback import (PortalProbeCache, stranded_start_observations,
                                     positive_frontier_refill)
    exclusions, history = set(), []
    screen_resumes = {}
    screen_minimum = kwargs.pop('minimum_screen_candidates', 1)
    negative_cache = PortalProbeCache(limit=4096 if cache_portal_negatives else 0)
    if kwargs.get("portal_screen_cache") is None:
        kwargs["portal_screen_cache"] = {}
    limit = max(0, int(max_portal_refills))
    for depth in range(limit + 1):
        result = _route_coupled_via_portal_beam(
            board, pair, endpoints, _excluded_start_portals=frozenset(exclusions),
            _negative_probe_cache=negative_cache,
            _screen_resumes=screen_resumes,
            minimum_screen_candidates=screen_minimum,
            _yield_stranded_portals=bool(early_portal_feedback and depth < limit
                and kwargs.get("start_prequalified") is None), **kwargs)
        if (not result.get("refused") or depth == limit
                or _deadline_expired(kwargs.get("deadline"))
                or kwargs.get("start_prequalified") is not None):
            break
        observations = stranded_start_observations(result.get("portal_evidence"))
        added = {tuple(row["portal_key"]) for row in observations} - exclusions
        if added:
            exclusions.update(added)
            action = {'kind':'stranded-start-exclusion', 'observations':observations}
        else:
            widening = positive_frontier_refill(result.get('portal_evidence'), screen_minimum)
            if widening is None:
                break
            screen_minimum = widening['minimum_candidates']
            action = dict(kind='positive-frontier-widening', **widening)
        history.append({"round": depth, "refused": result.get("refused"),
                        **action,
                        "portal_evidence": copy.deepcopy(result.get("portal_evidence"))})
    if history:
        result["portal_refill"] = {"rounds": history, "selected_round": depth,
                                   "refill_limit": limit,
                                   "excluded_start_portals": len(exclusions)}
    if result.get('refused'):
        # A first F.Cu refusal is not the complete obstruction set for a
        # through hole. Diagnose a small immutable-parent sample only AFTER
        # rollback, never on every maze hop or as admission/search authority.
        from cec_native_via_obstruction_stack import enrich_pair_refusal
        enrich_pair_refusal(board, pair, result)
    return result


def _probe_matched_transition_field(row, *, p_code, n_code, route_axis,
                                    add_signal_via, add_return_via,
                                    screen_signal_via=None):
    """Prove primary signal barrels before spending work on their returns.

    The caller owns an isolated probe transaction and rolls back all newly
    created items. A blocked signal field cannot be repaired by ground vias;
    those secondary searches must not consume its search budget. Both signal
    witnesses remain available for conflict-directed placement diagnostics.
    """
    p_report, n_report = {}, {}
    if screen_signal_via is not None:
        # The caller supplies an immutable-parent snapshot, before either
        # temporary barrel exists. Negative seats need no native mutation or
        # second full scan. Positive seats are NOT admission: the ordinary
        # sequential insertions below still test the new partner, drill
        # spacing, all copper layers and the complete reference-return field.
        p_clear = screen_signal_via(row['p'], p_code, report=p_report)
        n_clear = screen_signal_via(row['n'], n_code, report=n_report)
        if not p_clear or not n_clear:
            return dict(ok=False, reason='matched signal-via field is not clear',
                        p_via=p_report, n_via=n_report,
                        return_status='not_attempted_signal_field_blocked')
    p_via = add_signal_via(row['p'], p_code, report=p_report)
    n_via = add_signal_via(row['n'], n_code, report=n_report)
    if p_via is None or n_via is None:
        return dict(ok=False, reason='matched signal-via field is not clear',
                    p_via=p_report, n_via=n_report,
                    return_status='not_attempted_signal_field_blocked')
    vector = (row['n'][0]-row['p'][0], row['n'][1]-row['p'][1])
    _vias, status = add_return_via(row['center'], vector,
        route_axis=_portal_return_route_axis(row,route_axis),
        signal_points=(row['p'], row['n']), portal_side=row['side'])
    ok = status in ('covered', 'added')
    return dict(ok=ok, reason=None if ok else status, p_via=p_report,
                n_via=n_report, return_status=status)


def _native_pair_terminal_barrel(board, net, point, layers):
    """Read one existing, unmodified plated bore at the exact net endpoint.

    A retained through-via is physical layer access just like a connector
    barrel. A mask, zero drill, blind/backdrilled/partial bore or coincident
    duplicate hole is not. This read-only witness grants no factory, current,
    return, clearance or pair qualification and never creates a new hole.
    """
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]
    vias = [via for via in board.GetTracks() if via.GetClass() == 'PCB_VIA']
    if len(pads)+len(vias)>16384:
        return None
    at = _v(*point)
    # An SMD land may legitimately contain its existing plated via, but two
    # bores at the same point are ambiguous even if one names another net.
    bores = [item for item in [*pads,*vias] if item.GetPosition()==at
             and (item.GetClass()=='PCB_VIA' or item.HasHole())]
    if len(bores)!=1:
        return None
    item=bores[0]
    if str(item.GetNetname())!=net or not set(layers)<=set(cec_fr._through_barrel_layers(board,item)):
        return None
    if item.GetClass()=='PCB_VIA':
        drill=item.GetDrillValue()
        if drill<=0 or any(item.GetWidth(face)<=drill for face in layers):
            return None
        return dict(uuid=item.m_Uuid.AsString(),kind='via',net=net,
                    at_mm=[at.x/MM,at.y/MM],
                    existing_unmodified_plated_barrel=True,
                    new_hole_or_process_qualification=False)
    if (item.GetAttribute()!=pcbnew.PAD_ATTRIB_PTH
            or min(item.GetDrillSize().x,item.GetDrillSize().y)<=0
            or any(not item.IsOnLayer(face) for face in layers)):
        return None
    return dict(uuid=item.m_Uuid.AsString(),
                ref=item.GetParentFootprint().GetReference(),pad=item.GetNumber(),
                net=net,at_mm=[at.x/MM,at.y/MM])


def _paired_native_terminal_layers(board, pair, endpoints, *, layer, middle_layer,
                                   surface_terminal_sides=()):
    """Resolve physical plated layer access independently at each paired end.

    A native plated terminal needs neither an outer-layer dogbone nor another
    signal barrel to reach copper it already spans. Both members must resolve
    uniquely at the actual endpoint and net; a same-XY SMD/NPTH/wrong-net pad
    or a plated member without its partner grants no mixed-side shortcut.
    This selects where to search, never admits copper or skips reference,
    clearance, coupling or whole-edge geometry checks. An explicit bounded
    surface alternative may decline positively proved native access at either
    end. That end then needs the ordinary matched signal/return transition
    proofs; physical availability never obliges reuse of an obstructed face.
    """
    if (type(surface_terminal_sides) not in (tuple, list)
            or len(surface_terminal_sides) > 2
            or any(type(side) is not str or side not in ('start', 'end')
                   for side in surface_terminal_sides)
            or len(set(surface_terminal_sides)) != len(surface_terminal_sides)):
        raise ValueError('bounded_explicit_surface_terminal_sides_required')
    if surface_terminal_sides and layer not in ('F.Cu', 'B.Cu'):
        raise ValueError('surface_terminal_alternative_requires_outer_source_face')
    result = {side: dict(source_layer=layer, native_plated_access=False, pads=[],barrels=[])
              for side in ('start', 'end')}
    source_id, target_id = board.GetLayerID(layer), board.GetLayerID(middle_layer)
    if source_id == target_id or min(source_id, target_id) < 0:
        if surface_terminal_sides:
            raise ValueError('surface_terminal_alternative_requires_distinct_enabled_faces')
        return result
    enabled = set(board.GetEnabledLayers().CuStack())
    if source_id not in enabled or target_id not in enabled:
        if surface_terminal_sides:
            raise ValueError('surface_terminal_alternative_requires_distinct_enabled_faces')
        return result
    p_start, p_end, n_start, n_end = endpoints
    for side, points in (('start', (p_start, n_start)), ('end', (p_end, n_end))):
        witnesses = []
        for net, point in zip((pair['p'], pair['n']), points):
            witness=_native_pair_terminal_barrel(board,net,point,(source_id,target_id))
            if witness is None:
                break
            witnesses.append(witness)
        if len(witnesses) == 2:
            result[side].update(source_layer=middle_layer,
                                native_plated_access=True,
                                pads=[q for q in witnesses if q.get('kind')!='via'],
                                barrels=witnesses)
    for side in surface_terminal_sides:
        if not result[side]['native_plated_access']:
            raise ValueError('surface_terminal_alternative_requires_positive_native_access')
        result[side].update(source_layer=layer, native_plated_access=False,
                            native_plated_access_available=True,
                            access_choice='explicit_surface_with_new_matched_transition')
    return result


def _route_coupled_via_portal_beam(board, pair, endpoints, *, layer="F.Cu",
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
                               portal_screen_cache=None,
                               minimum_screen_candidates=1,
                               minimum_portal_lead_mm=1.3,
                               surface_terminal_sides=(),
                               start_prequalified=None,
                               _excluded_start_portals=(),
                               _negative_probe_cache=None,
                               _screen_resumes=None,
                               _yield_stranded_portals=False):
    """Route a pair through independently proven package portals.

    This is the bounded fallback for dissimilar pin fields.  It never searches
    P and N globally as independent nets: exact local fan-ins are screened
    transactionally, then one obstacle-aware centreline is expanded into a
    constant-gap ribbon.  Whole-edge geometry, coupled coverage, and acute
    backtrack checks must all pass before the transaction is retained.
    """
    clearance = _pair_clearance(board, pair, clearance)
    p_start, p_end, n_start, n_end = endpoints
    from cec_portal_feedback import (PortalProbeCache, portal_geometry_key,
                                     stranded_start_observations)
    negative_cache = (_negative_probe_cache if _negative_probe_cache is not None
                      else PortalProbeCache())
    excluded_start_portals = set(_excluded_start_portals)
    (signal_via_diameter_mm, signal_via_drill_mm,
     signal_via_limits) = cec_fab_profile.precision_signal_via_geometry(
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
    terminal_access = _paired_native_terminal_layers(
        board, pair, endpoints, layer=layer, middle_layer=middle_layer,
        surface_terminal_sides=surface_terminal_sides)
    if surface_terminal_sides and start_prequalified is not None and 'start' in surface_terminal_sides:
        raise ValueError('prequalified_start_cannot_be_reclassified_as_surface_alternative')
    if start_prequalified is not None:
        # Its producer qualified a particular surface throat, not a new one.
        terminal_access['start'] = dict(source_layer=layer,
            native_plated_access=False, pads=[], reason='prequalified_throat_retained')
    source_avoid = _avoid_for_layer(avoid, layer)
    middle_avoid = _avoid_for_layer(avoid, middle_layer)
    width_nm = _nm(width)
    p_code = board.GetNetcodeFromNetname(pair["p"])
    n_code = board.GetNetcodeFromNetname(pair["n"])
    own = {p_code, n_code}
    existing_pair_track_ids = {
        item.m_Uuid.AsString() for item in board.GetTracks()
        if item.GetNetCode() in own}
    # Through-via lands cannot sit at the narrow trace-pair pitch.  Widen only
    # the two transition portals enough for real annular lands plus clearance;
    # the jointly routed inner ribbon converges back to nominal pair geometry.
    # Do not place two different-net annular lands at the exact mathematical
    # clearance boundary.  KiCad's shape collision predicate is inclusive at
    # that boundary, so the second member would reject the first and every
    # matched transition field would appear impossible.  The extra 50 um is a
    # small deterministic manufacturing/search margin localized to the portal;
    # the ribbon still converges to the specified trace gap after the vias.
    portal_separation = (max(
                             width + gap,
                             float(signal_via_diameter_mm)
                             + float(clearance) + 0.05)
                         if layer_transition else None)
    portal_plan = _paired_portal_candidates(
        p_start, n_start, p_end, n_end, width=width, gap=gap,
        portal_separation=portal_separation,
        **({'minimum_lead_mm':minimum_portal_lead_mm} if minimum_portal_lead_mm!=1.3
           or type(minimum_portal_lead_mm) not in (int,float) else {}))
    start_spread = _dist(p_start, n_start)
    end_spread = _dist(p_end, n_end)
    pinfield_ratio = (max(start_spread, end_spread)
                      / max(min(start_spread, end_spread), 1e-9))
    # Dissimilar pin fields are precisely the case in which a connector
    # dogbone may need to arrive orthogonally at the common trunk.  Treat that
    # turn as a ranking concern, not a feasibility constraint: the terminal
    # stub generator still rejects acute/backtracking geometry and chamfers
    # accepted axis turns before copper is emitted.  A positive hard floor
    # here made otherwise legal wide-connector fan-ins impossible.
    minimum_handoff_alignment = 0.0
    # A long board-scale span still needs topology diversity at each package.
    # Two trace-optimal fan-ins can share the same shallow lead and force A*
    # into an arrival-direction loop, while the fourth locally legal candidate
    # is the ordinary longer escape that removes it.  Four endpoints retain
    # that finite lead/launch diversity; short package-to-package edges keep a
    # slightly wider beam because their fan-ins dominate the whole route.
    short_edge = portal_plan["span_mm"] < 10.0
    max_fanins_per_side = int(
        max_fanins_per_side
        if max_fanins_per_side is not None else (6 if short_edge else 4))
    max_portal_pairs = int(
        max_portal_pairs
        if max_portal_pairs is not None else (24 if short_edge else 16))
    if type(minimum_screen_candidates) is not int or minimum_screen_candidates < 1:
        raise ValueError('positive frontier minimum must be a positive integer')
    screen_minimum = min(minimum_screen_candidates, max_fanins_per_side)
    evidence = {
        'minimum_screen_candidates':screen_minimum,
        'max_fanins_per_side':max_fanins_per_side,
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
        "terminal_layer_access": terminal_access,
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

    fixed_start = None
    if start_prequalified is not None:
        fixed_center = tuple(start_prequalified["center"])
        fixed_p = tuple(start_prequalified["p"])
        fixed_n = tuple(start_prequalified["n"])
        fixed_heading = tuple(start_prequalified.get("route_heading")
                              or portal_plan["axis"])
        heading_projection = sum(
            float(a) * float(b)
            for a, b in zip(fixed_heading, portal_plan["axis"]))
        traversal_sign = 1 if heading_projection >= 0.0 else -1
        p_projection = (
            fixed_heading[0] * (fixed_p[1] - fixed_center[1])
            - fixed_heading[1] * (fixed_p[0] - fixed_center[0]))
        fixed_sign = 1 if p_projection >= 0.0 else -1
        fixed_start = {
            "side": "start", "sign": fixed_sign,
            "lead_mm": 0.0, "lateral_mm": 0.0,
            "reverse_launch": traversal_sign < 0,
            "route_heading": fixed_heading,
            "center": fixed_center, "p": fixed_p, "n": fixed_n,
            "actual_p": fixed_p, "actual_n": fixed_n,
            "nominal_route_heading": fixed_heading,
            "actual_handoff_route_heading": fixed_heading,
            "handoff_heading_alignment": 1.0,
            "fanin_length_mm": 0.0,
            "fanin_coupling_pct": 100.0,
            "allow_detour": False, "detour_member_paths": 0,
            "score": (0.0, 0.0, 0.0),
            "prequalified": True,
        }
        evidence["prequalified_start"] = {
            "sign": fixed_sign,
            "center": [round(value, 6) for value in fixed_center],
            "p": [round(value, 6) for value in fixed_p],
            "n": [round(value, 6) for value in fixed_n],
            "route_heading": [round(float(value), 6)
                              for value in fixed_heading],
        }
    foreign_shape_cache = {}
    partner_shape_cache = {}
    blocker_shape_cache = {}
    # Scoped to this immutable parent/probe transaction. Signal-hole and
    # reference-return feasibility does not depend on direct versus dogbone
    # fan-in mode, so don't redo a completed negative in each search phase.
    transition_field_refusals = {}
    # Only used by the rejection-only screen after rollback() has restored
    # this beam's original parent. Do not share with fan-in caches, which can
    # be populated while temporary copper exists, or with another beam/board.
    transition_parent_shapes = {}
    # Pure geometry/counters only, scoped to the wrapper's immutable-parent
    # rollback transaction. Never share native shapes across beam invocations.
    screen_resumes = _screen_resumes if _screen_resumes is not None else {}
    portal_screen_cache = (portal_screen_cache
                           if portal_screen_cache is not None else {})
    screen_domain = (
        "octilinear-escape-v5-terminal-via-envelope",
        str(pair.get("p")), str(pair.get("n")), str(layer),
        tuple(round(float(value), 6) for point in endpoints for value in point),
        round(width, 6), round(gap, 6), round(float(clearance), 6),
        round(float(portal_plan.get(
            "portal_separation_mm", width + gap)), 6),
        int(max_fanins_per_side), round(minimum_handoff_alignment, 6),
        float(minimum_portal_lead_mm),
        bool(layer_transition), float(signal_via_diameter_mm),
        float(signal_via_drill_mm), float(return_via_diameter_mm),
        float(return_via_drill_mm), float(return_reach_mm),
        tuple(source_avoid),
        str(middle_layer),
        tuple((side, terminal_access[side]['source_layer']) for side in ('start', 'end')),
    )

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                _discard_items(board,[item])

    def public_row(row):
        public = {
            "sign": row["sign"], "lead_mm": row["lead_mm"],
            "lateral_mm": row["lateral_mm"],
            "reverse_launch": bool(row.get("reverse_launch")),
            "escape_heading_step": row.get("escape_heading_step"),
            "route_heading": [round(value, 6) for value in
                              row.get("route_heading", ())],
            "center": [round(value, 6) for value in row["center"]],
            "p": [round(value, 6) for value in row["p"]],
            "n": [round(value, 6) for value in row["n"]],
        }
        if row.get("nominal_route_heading") is not None:
            public["nominal_route_heading"] = [
                round(float(value), 6)
                for value in row["nominal_route_heading"]]
        if row.get("actual_handoff_route_heading") is not None:
            public["actual_handoff_route_heading"] = [
                round(float(value), 6)
                for value in row["actual_handoff_route_heading"]]
        if row.get("handoff_heading_alignment") is not None:
            public["handoff_heading_alignment"] = round(
                float(row["handoff_heading_alignment"]), 6)
        if "grid_snap_mm" in row:
            public["grid_snap_mm"] = row["grid_snap_mm"]
        return public

    def emit_fanin(row, *, allow_detour, detour_member_paths=32,
                   local_deadline=None):
        if row.get("prequalified"):
            return {
                "name": pair["name"], "p": pair["p"], "n": pair["n"],
                "route_mode": "prequalified-local-throat",
                "segments": 0, "length_mm": 0.0,
                "coupled_len_mm": 0.0, "coupled_coverage_pct": 100.0,
                "handoff_route_heading": list(row["route_heading"]),
                "handoff_member_coherence": 1.0,
                "handoff_heading_alignment": 1.0,
            }
        axis = portal_plan["axis"]
        preferred_heading = tuple(row.get("route_heading") or (
            axis if row["side"] == "start"
            else (-axis[0], -axis[1])))
        local_endpoints = (row["actual_p"], row["p"], row["actual_n"], row["n"])
        import cec_endpoint_roadmap
        local_context = (cec_endpoint_roadmap.terminal_context(
            board,pair,local_endpoints,
            layer=terminal_access[row['side']]['source_layer']) if allow_detour else None)
        return _route_paired_stub(
            board, pair,
            local_endpoints,
            layer=terminal_access[row['side']]['source_layer'],
            clearance=clearance, avoid=avoid,
            allow_detour=allow_detour,
            deadline=(local_deadline
                      if local_deadline is not None else deadline),
            detour_member_paths=detour_member_paths,
            preferred_end_direction=preferred_heading,
            minimum_end_heading_alignment=minimum_handoff_alignment,
            minimum_end_coherence=math.cos(math.radians(45.0)),
            complete_pair_context=local_context,
            strict_pair_gap=True,
            foreign_shape_cache=foreign_shape_cache,
            partner_shape_cache=partner_shape_cache,
            blocker_shape_cache=blocker_shape_cache,
            terminal_via_diameter_mm=(signal_via_diameter_mm
                if layer_transition and not terminal_access[row['side']]['native_plated_access']
                else None))

    def add_signal_via(point, net_code, *, report=None):
        at = _v(*point)
        if not cec_fr._via_spot_clear(
                board, at, _nm(signal_via_diameter_mm), _nm(clearance),
                {int(net_code)}, drill_nm=_nm(signal_via_drill_mm),
                net_code=int(net_code),
                report=report):
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

    def screen_signal_via(point, net_code, *, report=None):
        return cec_fr._via_spot_clear(
            board, _v(*point), _nm(signal_via_diameter_mm), _nm(clearance),
            {int(net_code)}, drill_nm=_nm(signal_via_drill_mm),
            net_code=int(net_code), foreign_cache=transition_parent_shapes,
            report=report)

    def add_return_via(center, pair_vector, route_axis=None,
                       signal_points=(), portal_side="start"):
        return _add_pair_transition_returns(
            board, center, pair_vector, route_axis=route_axis,
            signal_points=signal_points, portal_side=portal_side,
            width=width, gap=gap, clearance=clearance,
            via_diameter_mm=return_via_diameter_mm,
            via_drill_mm=return_via_drill_mm,
            return_reach_mm=return_reach_mm)

    def screen(rows, label, *, screen_deadline=None, soft_deadline=None,
               preferred_topologies=()):
        screen_started = time.monotonic()
        initial_negative_hits = negative_cache.hits
        active_deadline = (screen_deadline
                           if screen_deadline is not None else deadline)
        preferred_signature = tuple(sorted({
            (round(float(row.get("lead_mm", 0.0)), 6),
             round(abs(float(row.get("lateral_mm", 0.0))), 6),
             bool(row.get("reverse_launch")))
            for row in (preferred_topologies or ())
        }))
        cache_key = screen_domain + (str(label), preferred_signature)
        if str(label).startswith("start:"):
            cache_key += (tuple(sorted(excluded_start_portals)),)
            rows = [row for row in rows
                    if portal_geometry_key(row) not in excluded_start_portals]
        cached = portal_screen_cache.get(cache_key)
        if cached is not None:
            cached_evidence = copy.deepcopy(cached["evidence"])
            cached_evidence["cache_hit"] = True
            cached_evidence["wall_seconds"] = 0.0
            evidence["screened"][label] = cached_evidence
            return copy.deepcopy(cached["accepted"])
        resume = screen_resumes.setdefault(cache_key, {
            'accepted':[], 'checked':0, 'rejection_counts':{},
            'blocker_counts':{}, 'rejected_rows':[], 'completed':set(),
            'wall_seconds':0., 'phase_counts':{}, 'calls':0,
            'transition_hits':0, 'negative_hits':0})
        accepted = resume['accepted']
        checked = resume['checked']
        rejection_counts = resume['rejection_counts']
        blocker_counts = resume['blocker_counts']
        rejected_rows = resume['rejected_rows']
        completed = resume['completed']
        transition_field_cache_hits = 0
        def lower_bound(row):
            return (
                round(_dist(row["actual_p"], row["p"])
                      + _dist(row["actual_n"], row["n"]), 6),
                round(abs(
                    _dist(row["actual_p"], row["p"])
                    - _dist(row["actual_n"], row["n"])), 6),
                1 if row.get("reverse_launch") else 0,
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
            report = report or {}
            direct = (report.get("admission") or {}).get("direct") or {}
            blockers = []
            for member in ("p", "n"):
                blockers.extend(list((direct.get(member) or {}).get(
                    "foreign_blockers") or ()))
            blockers.extend(list(report.get("blockers") or ()))
            witness={
                "score": list(lower_bound(row)),
                "portal": public_row(row),
                "allow_detour": bool(allow_detour),
                "reason": str(reason),
                "blockers": blockers[:8],
                "reservation_hits": list(
                    report.get("reservation_hits") or ())[:8],
                "geometry_issues": list(
                    (report.get("geometry") or {}).get("issues") or ())[:8],
            }
            admission = report.get("admission") or {}
            detour = admission.get("detour") or {}
            if detour:
                witness["local_search"] = {
                    field: detour.get(field) for field in (
                        "p_paths", "n_paths", "path_pairs_checked",
                        "path_pairs_available", "path_pairs_ranked",
                        "objective_pruned_pairs", "selection_policy",
                        "crossing_rejected", "pair_clearance_rejected",
                        "admitted_pairs", "deadline_exhausted")
                    if field in detour
                }
            ribbon = admission.get("paired_ribbon") or {}
            if ribbon.get("rejected"):
                witness["ribbon_rejection"] = dict(
                    ribbon["rejected"][0])
            if report.get("transition") is not None:
                witness["transition"] = report["transition"]
            from cec_portal_feedback import retain_rejection_witness
            retain_rejection_witness(rejected_rows,witness)

        # Breadth before depth: trying every nominally cheap straight fan-in
        # first still performs two exact board-copper queries per row and can
        # starve the bounded dogbones that wide connector pin fields actually
        # require.  Probe a ranked direct beam, then the ranked exact dogbone
        # domain.  Only if neither yields a candidate do we exhaust the
        # remaining direct rows, so no legal direct solution is removed from
        # the search space.
        # Keep launch topology *and escape length* compute-fair.  A dense set
        # of short fan-ins can otherwise consume the endpoint budget before a
        # clear longer via field or reverse escape is even inspected.  Exact
        # length and geometry still rank accepted combinations afterward.
        ranked = _fair_portal_screen_order(rows, lower_bound)
        ranked = _symmetry_seeded_portal_screen_order(
            ranked, preferred_topologies)
        direct_beam = min(len(ranked), max(
            12, 4 * int(max_fanins_per_side)))
        phases = (
            (False, ranked[:direct_beam], "direct-beam", 32),
            (True, ranked, "bounded-dogbone", 32),
            (False, ranked[direct_beam:], "direct-exhaustive", 32),
        )
        phase_counts = resume['phase_counts']
        yielded_positive_beam = False
        for (allow_detour, ordered_rows, phase_name,
             detour_member_paths) in phases:
            phase_started = time.monotonic()
            phase_checked = 0
            for row_index, row in enumerate(ordered_rows):
                query_id = (phase_name, row_index)
                if query_id in completed:
                    continue
                if _portal_screen_should_yield(accepted, soft_deadline,
                                               minimum_candidates=screen_minimum):
                    yielded_positive_beam = True
                    break
                if _deadline_expired(active_deadline):
                    break
                # Completed queries stay behind the frontier. A solver query
                # interrupted inside its own deadline is explicitly rewound
                # below; it must never become a completed negative.
                completed.add(query_id)
                # Direct and dogbone phases can describe the same seats.
                # A wider frontier means distinct geometry, not duplicate
                # positives that happen to use another local search mode.
                if any(portal_geometry_key(candidate) == portal_geometry_key(row)
                       for candidate in accepted):
                    continue
                rollback()
                if (layer_transition and
                        not terminal_access[row['side']]['native_plated_access']):
                    # A transition portal is not feasible merely because its
                    # surface fan-in is clear. Prove the matched signal-via
                    # field and nearby reference return before admitting this
                    # row into the beam; otherwise the first trace-optimal row
                    # can deterministically fail after selection while a
                    # slightly longer, fully viable portal is never tried.
                    field_key = (row['side'], tuple(row['p']), tuple(row['n']),
                                 tuple(row['center']))
                    field = transition_field_refusals.get(field_key)
                    if field is None:
                        field = _probe_matched_transition_field(row,
                            p_code=p_code, n_code=n_code, route_axis=portal_plan['axis'],
                            add_signal_via=add_signal_via, add_return_via=add_return_via,
                            screen_signal_via=screen_signal_via)
                        if not field['ok']:
                            transition_field_refusals[field_key] = field
                    else:
                        transition_field_cache_hits += 1
                    transition_reason = field['reason']
                    p_via_report, n_via_report = field['p_via'], field['n_via']
                    return_status = field['return_status']
                    rollback()
                    if transition_reason is not None:
                        checked += 1
                        phase_checked += 1
                        reason = "transition portal: %s" % transition_reason
                        rejection_counts[reason] = (
                            rejection_counts.get(reason, 0) + 1)
                        transition_blockers = list(
                            p_via_report.get("blockers") or ())
                        transition_blockers.extend(
                            n_via_report.get("blockers") or ())
                        record_rejected(
                            row, reason, allow_detour=allow_detour,
                            report={
                                "blockers": transition_blockers,
                                "transition": {
                                    "p_via": p_via_report,
                                    "n_via": n_via_report,
                                    "return_status": return_status,
                                },
                            })
                        continue
                checked += 1
                phase_checked += 1
                # Exclusions/preference ordering change which rows are tried,
                # not the exact local query. Do not repeat completed failures
                # when a global dead-end witness asks for a fresh escape beam.
                # Full row serialization preserves actual pin points, polarity,
                # heading and any future geometric fields without quantization.
                probe_key = (screen_domain, str(label), bool(allow_detour),
                             int(detour_member_paths),
                             json.dumps(row, sort_keys=True, separators=(",", ":")))
                report = negative_cache.probe(probe_key, lambda: emit_fanin(
                    row, allow_detour=allow_detour,
                    detour_member_paths=detour_member_paths,
                    local_deadline=active_deadline),
                    expired=lambda: _deadline_expired(active_deadline))
                if (report.get('refused') and _deadline_expired(active_deadline)
                        and not PortalProbeCache.completed_negative(report)):
                    completed.discard(query_id)
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
                actual_heading = report.get("handoff_route_heading")
                handoff_coherence = float(
                    report.get("handoff_member_coherence", -1.0) or -1.0)
                handoff_alignment = float(
                    report.get("handoff_heading_alignment", 1.0))
                if (not actual_heading
                        or handoff_coherence + 1e-9
                        < math.cos(math.radians(45.0))
                        or handoff_alignment + 1e-6
                        < math.cos(math.radians(45.0))):
                    reason = "paired fan-in has no coherent shared handoff"
                    rejection_counts[reason] = (
                        rejection_counts.get(reason, 0) + 1)
                    record_rejected(
                        row, reason, allow_detour=allow_detour,
                        report={"admission": report.get("admission") or {}})
                    continue
                created = {
                    item.m_Uuid.AsString() for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in base_ids}
                geometry = _pair_graph_geometry(board, pair, created)
                if not geometry["ok"]:
                    rejection_counts["pair geometry"] = (
                        rejection_counts.get("pair geometry", 0) + 1)
                    record_rejected(
                        row, "pair geometry", allow_detour=allow_detour,
                        report={"geometry": geometry})
                    continue
                if (layer_transition and
                        not terminal_access[row['side']]['native_plated_access']):
                    # Isolated field and isolated fan-in proofs do not imply
                    # their union is legal. Re-prove the full transition with
                    # this emitted fan-in present before yielding a candidate.
                    # Never use the immutable-parent screen/cache here.
                    combined = _probe_matched_transition_field(row,
                        p_code=p_code, n_code=n_code, route_axis=portal_plan['axis'],
                        add_signal_via=add_signal_via, add_return_via=add_return_via)
                    if not combined['ok']:
                        reason = 'combined fan-in/transition: %s' % combined['reason']
                        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                        record_rejected(row, reason, allow_detour=allow_detour,
                            report={'blockers': list(combined['p_via'].get('blockers') or ())
                                + list(combined['n_via'].get('blockers') or ()),
                                'transition': combined})
                        continue
                candidate = dict(row)
                candidate["nominal_route_heading"] = tuple(
                    row.get("route_heading") or ())
                # The portal P/N cross-section was constructed perpendicular
                # to the nominal heading.  Keep that heading as the global
                # trunk contract; replacing it with the final local dogbone
                # direction rotates the trunk without rotating its two lane
                # seats, forcing an artificial endpoint taper/hairpin.  The
                # exact local heading remains evidence and is admitted only
                # when it is within one octilinear step of the contract.
                candidate["actual_handoff_route_heading"] = tuple(
                    float(value) for value in actual_heading)
                candidate["handoff_heading_alignment"] = handoff_alignment
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
            previous_phase = phase_counts.get(phase_name) or {}
            phase_counts[phase_name] = {
                "checked": int(previous_phase.get('checked', 0)) + phase_checked,
                "wall_seconds": round(float(previous_phase.get('wall_seconds', 0.))
                    + time.monotonic() - phase_started, 6),
            }
            if len(accepted) >= screen_minimum or _deadline_expired(active_deadline):
                break
        rollback()
        accepted.sort(key=lambda row: row["score"])
        resume['checked'] = checked
        resume['wall_seconds'] += time.monotonic() - screen_started
        resume['calls'] += 1
        resume['transition_hits'] += transition_field_cache_hits
        resume['negative_hits'] += negative_cache.hits - initial_negative_hits
        domain_complete = len(completed) == sum(len(phase[1]) for phase in phases)
        evidence["screened"][label] = {
            "checked": checked, "accepted": len(accepted),
            "negative_probe_cache_hits": resume['negative_hits'],
            "negative_probe_cache_entries": len(negative_cache.rows),
            "transition_field_cache_hits": resume['transition_hits'],
            "transition_field_negative_entries": len(transition_field_refusals),
            "phase_checked": phase_counts,
            "wall_seconds": round(resume['wall_seconds'], 6),
            "resume_calls": resume['calls'],
            "completed_queries": len(completed),
            "domain_complete": domain_complete,
            "budget_exhausted": bool(
                _deadline_expired(active_deadline)),
            "yielded_positive_beam": yielded_positive_beam,
            "rejection_counts": rejection_counts,
            "blockers": [dict(json.loads(key), count=count)
                         for key, count in sorted(
                             blocker_counts.items(),
                             key=lambda item: (-item[1], item[0]))[:16]],
            "nearest_rejected": sorted(
                rejected_rows,
                key=lambda row: (tuple(row["score"]), row["reason"]))[:8],
            "reason_diverse_rejected": copy.deepcopy(rejected_rows),
            "candidates": [public_row(row) for row in accepted],
        }
        # An expired phase may have searched only a prefix of the domain. Do
        # not poison a later, larger phase with that incomplete negative. A
        # completed screen is exact local geometry and is safe to reuse while
        # this route_coupled_pair transaction keeps the board unchanged.
        if (domain_complete or len(accepted) >= int(max_fanins_per_side)) \
                and not yielded_positive_beam:
            portal_screen_cache[cache_key] = {
                "accepted": copy.deepcopy(accepted),
                "evidence": copy.deepcopy(evidence["screened"][label]),
            }
        return accepted

    def route_portal_grid(start, end, target_layer_id, target_avoid):
        """Route a portal trunk with exact headings before relaxed headings.

        Allowing A* to finish one octilinear direction away from a proven
        package fan-in is useful around a hard obstacle, but it must not beat
        an exactly aligned route merely because it is a little shorter.  The
        latter joins without a taper or hairpin.  Preserve the relaxed domain
        as a second, still exact-screened fallback.
        """
        started = time.monotonic()
        attempts = []
        selected_diagnostics = {}
        learned_self_conflicts = []

        def learn_self_conflict_avoidance(issues, temporary_ids):
            """Remember only the offending A* direction at a crossing.

            A full rectangular keepout near a package throat can block every
            legal arrival direction.  The failed assembled graph instead
            supplies the exact temporary member segment that crossed a proven
            fan-in.  Project its crossing witness back to both possible shared
            centreline offsets and blacklist only parallel lattice edges near
            that witness.  Perpendicular/diagonal escapes through the same
            tight area remain searchable.
            """
            added = 0
            for issue in issues or ():
                if issue.get('type')=='partner_pad_clearance':
                    candidate=issue['member_segment_mm']
                    a,b=candidate; point=issue['pad_center_mm']
                    dx,dy=b[0]-a[0],b[1]-a[1]
                    length2=dx*dx+dy*dy
                    if length2<=1e-12:continue
                    t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length2))
                    closest=(a[0]+t*dx,a[1]+t*dy)
                    fixed=[closest,closest]
                else:
                    if issue.get("type") not in {"member_crossing", "member_clearance"}:
                        continue
                    p_is_temporary = issue.get("p_uuid") in temporary_ids
                    n_is_temporary = issue.get("n_uuid") in temporary_ids
                    if p_is_temporary == n_is_temporary:
                        continue
                    candidate = issue.get(
                        "p_segment_mm" if p_is_temporary else "n_segment_mm")
                    fixed = issue.get(
                        "n_segment_mm" if p_is_temporary else "p_segment_mm")
                first, second = candidate, fixed
                if not first or not second:
                    continue
                first_x = sorted((float(first[0][0]), float(first[1][0])))
                first_y = sorted((float(first[0][1]), float(first[1][1])))
                second_x = sorted((float(second[0][0]), float(second[1][0])))
                second_y = sorted((float(second[0][1]), float(second[1][1])))
                # Midpoint of the two closest bounding intervals is exact for
                # an orthogonal crossing and conservative for the clearance
                # witnesses emitted by the graph authority.
                x0, x1 = max(first_x[0], second_x[0]), min(
                    first_x[1], second_x[1])
                y0, y1 = max(first_y[0], second_y[0]), min(
                    first_y[1], second_y[1])
                if x0 > x1:
                    x0 = x1 = (x0 + x1) / 2.0
                if y0 > y1:
                    y0 = y1 = (y0 + y1) / 2.0
                witness = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
                dx = float(first[1][0]) - float(first[0][0])
                dy = float(first[1][1]) - float(first[0][1])
                length = math.hypot(dx, dy)
                if length <= 1e-9:
                    continue
                direction = (dx / length, dy / length)
                normal = (-direction[1], direction[0])
                half_pitch = (width + gap) / 2.0
                centers = [
                    (witness[0] + sign * normal[0] * half_pitch,
                     witness[1] + sign * normal[1] * half_pitch)
                    for sign in (-1.0, 1.0)]
                row = {
                    "type": issue.get("type"),
                    "direction": [round(value, 6) for value in direction],
                    "centers_mm": [[round(value, 6) for value in center]
                                   for center in centers],
                }
                if row not in learned_self_conflicts:
                    learned_self_conflicts.append(row)
                    added += 1
            return added

        def learned_edge_clear(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length <= 1e-9:
                return True
            direction = (dx / length, dy / length)
            for row in learned_self_conflicts:
                blocked = tuple(row["direction"])
                parallel = abs(
                    direction[0] * blocked[1]
                    - direction[1] * blocked[0]) <= 1e-5
                if not parallel:
                    continue
                if any(_seg_seg_dist(a, b, center, center) <= 0.18
                       for center in row["centers_mm"]):
                    return False
            return True

        def validate_against_proven_fanins(p_points, n_points):
            """Reject a ribbon orientation that crosses its own fan-ins.

            The grid owns the global centreline, while the package solver has
            already committed two exact local fan-ins.  Foreign-copper checks
            intentionally ignore the pair's own net codes, so without this
            assembled-graph probe the first otherwise legal lane orientation
            can cross an existing member and hide the valid opposite
            orientation.  Materialize only the candidate middle, validate the
            complete temporary pair graph, and remove it before returning.
            """
            import cec_pair_pad_guard
            pad_clearance=cec_pair_pad_guard.paths(board,pair,p_points,n_points,
                layer_id=target_layer_id,clearance_mm=clearance)
            if not pad_clearance['ok']:
                learn_self_conflict_avoidance(pad_clearance['issues'],set())
                return pad_clearance
            temporary = []
            try:
                temporary += _lay(
                    board, p_code, p_points, width_nm, target_layer_id)
                temporary += _lay(
                    board, n_code, n_points, width_nm, target_layer_id)
                temporary_ids = {
                    item.m_Uuid.AsString() for item in temporary}
                # ``base_ids`` includes the already-proved package fan-in and
                # runway when this is a one-sided portal route.  Excluding it
                # reduces the supposed assembled-graph check to the temporary
                # trunk alone.  Include all P/N copper present at entry plus
                # the candidate middle so crossings at the handoff teach the
                # bounded retry loop immediately.
                scoped = set(existing_pair_track_ids) | temporary_ids
                geometry = _pair_graph_geometry(
                    board, pair, scoped, strict_ids=temporary_ids)
                if not geometry.get("ok"):
                    learn_self_conflict_avoidance(
                        geometry.get("issues"), temporary_ids)
                return {
                    "ok": bool(geometry.get("ok")),
                    "issues": list(geometry.get("issues") or ())[:8],
                }
            finally:
                for item in temporary:
                    _discard_items(board,[item])

        heading_schedule = [0, 1]
        schedule_index = 0
        learned_retries = 0
        while schedule_index < len(heading_schedule):
            allowed_turn_steps = heading_schedule[schedule_index]
            if _deadline_expired(deadline):
                break
            diagnostics = {}
            attempt_started = time.monotonic()
            learned_before = len(learned_self_conflicts)
            grid = _grid_coupled_path(
                board, start_center=start["center"],
                end_center=end["center"],
                p_start=start["p"], n_start=start["n"],
                p_end=end["p"], n_end=end["n"],
                layer_id=target_layer_id, width=width, gap=gap,
                clearance=clearance, own=own, avoid=target_avoid,
                pair_net_codes=(int(p_code), int(n_code)),
                step=0.5, initial_turn_steps=allowed_turn_steps,
                terminal_turn_steps=allowed_turn_steps,
                portal_mode=True, deadline=deadline,
                portal_start_heading=start.get("route_heading"),
                portal_end_heading=tuple(
                    -float(value) for value in
                    end.get("route_heading", ())) or None,
                diagnostics=diagnostics,
                max_visited=max_grid_visited,
                foreign_shape_cache=foreign_shape_cache,
                path_validator=validate_against_proven_fanins,
                edge_validator=learned_edge_clear,
                strict_taper_continuation=bool(
                    learned_self_conflicts))
            attempt_wall = time.monotonic() - attempt_started
            attempts.append({
                "allowed_turn_steps": int(allowed_turn_steps),
                "status": diagnostics.get(
                    "status", "accepted" if grid is not None else "refused"),
                "visited": diagnostics.get("visited"),
                "frontier_gap_mm": diagnostics.get("frontier_gap_mm"),
                "wall_seconds": round(attempt_wall, 6),
                "learned_self_conflicts": len(learned_self_conflicts),
            })
            selected_diagnostics = diagnostics
            if grid is not None:
                selected_diagnostics["endpoint_heading_policy"] = (
                    "exact" if allowed_turn_steps == 0 else "one-step-relaxed")
                selected_diagnostics["endpoint_heading_attempts"] = attempts
                selected_diagnostics["wall_seconds"] = round(
                    time.monotonic() - started, 6)
                selected_diagnostics["learned_self_conflicts"] = list(
                    learned_self_conflicts)
                return grid, selected_diagnostics
            if (len(learned_self_conflicts) > learned_before
                    and learned_retries < 2):
                # Re-run the same exact-heading search with the newly learned
                # local witness.  Only after its bounded retries are exhausted
                # may the endpoint heading relax by one octilinear step.
                learned_retries += 1
                continue
            schedule_index += 1
            learned_retries = 0
        selected_diagnostics["endpoint_heading_policy"] = "refused"
        selected_diagnostics["endpoint_heading_attempts"] = attempts
        selected_diagnostics["wall_seconds"] = round(
            time.monotonic() - started, 6)
        selected_diagnostics["learned_self_conflicts"] = list(
            learned_self_conflicts)
        return None, selected_diagnostics

    sign_order = list(portal_plan["sign_order"])
    portal_pairs_attempted = 0
    admitted_candidates = 0
    best_admitted = None

    def early_refill():
        # Yield only after a complete local frontier witness, with a refill
        # available and no admitted incumbent to lose. A fixed start throat
        # cannot be relocated. This diversifies a bounded beam, not a board-
        # scale impossibility claim; all new copper is rolled back first.
        if (not _yield_stranded_portals or fixed_start is not None
                or best_admitted is not None or _deadline_expired(deadline)
                or not stranded_start_observations(evidence)):
            return None
        rollback()
        evidence["early_refill"] = True
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "exhausted local portal yields to escape refill",
                "portal_evidence": evidence}
    detour_target = 2.0
    max_admitted_candidates = 4
    evidence["route_attempt_budget"] = {
        "total": int(max_portal_pairs), "attempted": 0, "by_sign": {}}
    from cec_portal_feedback import fair_screen_domains
    domain_specs = {}
    groups = []
    for sign in sign_order:
        labels = []
        for side in ('start', 'end'):
            label = '%s:%+d' % (side, sign)
            domain_specs[label] = (sign, side)
            labels.append(label)
        groups.append(tuple(labels))

    def resume_domain(label, local_deadline):
        sign, side = domain_specs[label]
        if side == 'start' and fixed_start is not None:
            candidates = ([fixed_start]
                          if int(fixed_start['sign']) == int(sign) else [])
            evidence['screened'][label] = {
                'checked':0, 'accepted':len(candidates), 'prequalified':True,
                'budget_exhausted':False, 'domain_complete':True,
                'candidates':[public_row(row) for row in candidates]}
            return dict(candidates=candidates, complete=True, progress=1)
        candidates = screen(portal_plan['by_sign'][sign][side], label,
                            screen_deadline=local_deadline,
                            soft_deadline=local_deadline)
        report = evidence['screened'][label]
        return dict(candidates=candidates,
                    complete=bool(report.get('domain_complete')),
                    progress=int(report.get('completed_queries', report['checked'])))

    domain_schedule = fair_screen_domains(groups, resume_domain, deadline=deadline,
                                         minimum_candidates=screen_minimum)
    evidence['screen_schedule'] = {
        key:value for key,value in domain_schedule.items() if key != 'domains'}
    for sign_index, sign in enumerate(sign_order):
        if (_deadline_expired(deadline)
                or admitted_candidates >= max_admitted_candidates):
            break
        start_rows = domain_schedule['domains'].get(
            'start:%+d' % sign, {}).get('candidates') or []
        end_rows = domain_schedule['domains'].get(
            'end:%+d' % sign, {}).get('candidates') or []
        if not start_rows or not end_rows:
            continue
        # A reverse portal is a real and sometimes necessary package escape,
        # but it asks the global route to leave away from its destination and
        # turn back.  Rank ordinary forward/forward topology before saving a
        # fraction of a millimetre in local dogbone length.  This prevents the
        # first sign from spending its full exact-search allocation on looped
        # approaches while a conventional candidate is already screened.
        remaining_signs = len(sign_order) - sign_index
        remaining_attempts = max(
            0, int(max_portal_pairs) - portal_pairs_attempted)
        sign_attempt_limit = (
            int(math.ceil(remaining_attempts / float(remaining_signs)))
            if remaining_attempts else 0)
        all_combinations = sorted(
            ((_portal_combination_score(start, end), start, end)
             for start in start_rows for end in end_rows),
            key=lambda row: row[0])
        combinations = all_combinations[:sign_attempt_limit]
        evidence["route_attempt_budget"]["by_sign"]["%+d" % sign] = {
            "screened_combinations": len(all_combinations),
            "reserved_attempts": int(sign_attempt_limit),
        }
        for _score, start, raw_end in combinations:
            if (_deadline_expired(deadline)
                    or admitted_candidates >= max_admitted_candidates):
                break
            portal_pairs_attempted += 1
            evidence["route_attempt_budget"]["attempted"] = \
                portal_pairs_attempted
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
                    if terminal_access[label]['native_plated_access']:
                        transition_evidence.append(dict(side=label, signal_vias_added=0,
                            **terminal_access[label]))
                        continue
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
                        route_axis=_portal_return_route_axis(row,portal_plan["axis"]),
                        signal_points=(row["p"], row["n"]),
                        portal_side=row["side"])
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
                grid, grid_diagnostics = route_portal_grid(
                    start, end, middle_layer_id, middle_avoid)
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
                        refill = early_refill()
                        if refill is not None:
                            return refill
                        continue
            else:
                # A locally legal straight between two portals can still meet
                # either pre-proved fan-in as a 135-degree backtrack.  That
                # failure used to be discovered only by the assembled graph
                # gate, after materializing the same invalid middle for many
                # candidate combinations.  Search the shared centreline first
                # so the portal headings are part of topology, not merely a
                # local length preference.  Its first expansion still covers
                # the unobstructed direct case.
                grid, grid_diagnostics = route_portal_grid(
                    start, end, layer_id, source_avoid)
                if grid is None:
                    evidence["attempts"].append({
                        "sign": sign, "start": public_row(start),
                        "end": public_row(end),
                        "refused": "no shared-centreline corridor",
                        "grid": grid_diagnostics,
                    })
                    refill = early_refill()
                    if refill is not None:
                        return refill
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
            candidate_detour = _complete_pair_candidate_detour(
                board,pair,route_reports=[start_report,middle,end_report])
            admitted = (
                geometry["ok"] and quality["ok"]
                and candidate_detour['ok']
                and quality.get("geometry_ok", False)
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
                "complete_pair_detour": candidate_detour,
            }
            if middle.get("route_mode") == "portal-centreline-grid":
                attempt["grid"] = grid_diagnostics
            if not admitted:
                attempt["refused"] = "whole portal edge admission failed"
                attempt["graph_issues"] = geometry.get("issues", [])[:8]
                attempt["route_quality_issues"] = quality.get(
                    "issues", [])[:8]
                evidence["attempts"].append(attempt)
                continue

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
            candidate_result = {
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

            # A valid first portal route is not necessarily a professional
            # route.  Dense fan-in combinations can differ by more than 2x in
            # length while all pass connectivity, gap, and DRC.  Keep a small
            # exact best-of-k beam when the first result exceeds the same 2x
            # detour policy enforced on the completed pair transaction.
            detour_ratio = _pair_edge_detour_ratio(endpoints, length_mm)
            candidate_result["endpoint_detour_ratio"] = (
                round(detour_ratio, 6)
                if detour_ratio is not None else None)
            admitted_candidates += 1
            attempt["endpoint_detour_ratio"] = (
                candidate_result["endpoint_detour_ratio"])
            if (detour_ratio is None
                    or detour_ratio <= detour_target + 1e-9):
                candidate_result["detour_optimization"] = {
                    "policy": "first-within-limit",
                    "limit": detour_target,
                    "admitted_candidates": admitted_candidates,
                }
                return candidate_result

            template = _capture_track_template(board, created)
            attempt["deferred_for_better_detour"] = True
            score = (float(detour_ratio), float(length_mm), len(created))
            if template and (best_admitted is None
                             or score < best_admitted["score"]):
                best_admitted = {
                    "score": score,
                    "template": template,
                    "report": candidate_result,
                }
            rollback()

    if best_admitted is not None:
        rollback()
        replayed = _replay_track_template(
            board, best_admitted["template"])
        if replayed:
            result = best_admitted["report"]
            result["segments"] = len(replayed)
            result["portal_evidence"] = evidence
            result["detour_optimization"] = {
                "policy": "best-of-bounded-admitted",
                "limit": detour_target,
                "admitted_candidates": admitted_candidates,
                "selected_ratio": result.get("endpoint_detour_ratio"),
                "within_limit": bool(
                    result.get("endpoint_detour_ratio") is not None
                    and result["endpoint_detour_ratio"]
                    <= detour_target + 1e-9),
            }
            return result

    rollback()
    reason = ("paired portal search deadline exhausted"
              if _deadline_expired(deadline)
              else "paired portal candidates exhausted")
    return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
            "refused": reason, "portal_evidence": evidence}


def _pair_route_failure_certificate(
        pair, endpoints, *, layer, width, gap, clearance,
        short_pair_refusal=None, portal_refusal=None,
        layer_transition_refusals=(), endpoint_pofv_refusals=(), conventional_diagnostics=None,
        grid_failure_diagnostics=(), corridor_rejects=(), search_interrupted=False):
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
    grid_rows = []
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
            for key in ("blockers", "dominant_blockers"):
                for hit in value.get(key) or ():
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
                    "launch_signs": value.get("launch_signs"),
                    "launch_geometry": value.get("launch_geometry"),
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
    visit(list(endpoint_pofv_refusals or ()), ("endpoint_pofv",))
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
    if search_interrupted or any("deadline" in status for status in grid_status_counts) or any(
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
        "search_interrupted": bool(search_interrupted),
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


def _existing_endpoint_barrel(board, pad, at, target_layer):
    """Resolve a physical via at a shared endpoint without manufacturing one.

    Exact database coordinates, one barrel, same net, actual layer span and
    independent dimensional/POFV eligibility are required. Ambiguous or invalid
    existing holes are refused, not repaired by overlaying another hole.
    """
    matches = [item for item in board.GetTracks()
               if item.GetClass() == "PCB_VIA"
               and item.GetPosition() == at]
    if not matches:
        return {"status": "absent"}
    evidence = {"uuids": [via.m_Uuid.AsString() for via in matches]}
    if len(matches) != 1:
        return dict(evidence, status="refused", reason="ambiguous endpoint barrels")
    via = matches[0]
    if via.GetNetCode() != pad.GetNetCode() or pad.GetNetCode() <= 0:
        return dict(evidence, status="refused", reason="foreign endpoint barrel")
    layers = set(via.GetLayerSet().CuStack())
    if (target_layer not in layers
            or not layers.intersection(pad.GetLayerSet().CuStack())):
        return dict(evidence, status="refused", reason="endpoint barrel lacks layer span")
    diameter, drill = via.GetWidth(via.TopLayer()) / MM, via.GetDrillValue() / MM
    ordinary_diameter, ordinary_drill, _ = \
        cec_fab_profile.board_legal_through_via_geometry(board, diameter, drill)
    ordinary_ok = (diameter > 0 and drill > 0
                   and diameter + 1e-9 >= ordinary_diameter
                   and drill + 1e-9 >= ordinary_drill)
    blocking, allowed = cec_fab_profile.via_at_pad_conflicts(
        board, at, _nm(diameter), _nm(drill), pad.GetNetCode())
    if not ordinary_ok and not (blocking is None and allowed):
        return dict(evidence, status="refused", reason="endpoint barrel dimensions unqualified")
    return dict(evidence, status="reused", diameter_mm=diameter, drill_mm=drill)


def _route_coupled_endpoint_pofv(
        board, pair, endpoints, *, target_layer, clearance=0.20,
        avoid=(), minimum_coupled_fraction=0.0, deadline=None,
        verbose=False):
    """Try the declared endpoint-only process geometries, preferred first.

    A narrow SMD land may contain the process minimum but not its preferred
    land. Retry only a failed endpoint-geometry qualification, before any
    coupled route or return field has been attempted. The failed attempt has
    removed all newly added barrels; inherited copper is never resized.
    Both pair members use the same requested geometry, every native guard
    remains mandatory, and all attempts share the original deadline.
    """
    profile = cec_fab_profile.PROFILES.get(
        cec_fab_profile.board_profile_name(board))
    # This is a native construction menu, not a fabrication-only query.
    # Request legal land/drill/ring dimensions before spending a paired
    # route lease; the downstream pad and all-layer guards still decide fit.
    geometries = cec_fab_profile.local_pofv_geometry_candidates(profile, board=board)
    if not geometries:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "board has no declared POFV profile"}
    attempts = []
    result = None
    for geometry in geometries:
        if _deadline_expired(deadline):
            break
        result = _route_coupled_endpoint_pofv_geometry(
            board, pair, endpoints, target_layer=target_layer,
            clearance=clearance, avoid=avoid,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=deadline, verbose=verbose, geometry=geometry)
        attempts.append({"diameter_mm": geometry[0], "drill_mm": geometry[1],
                         "refused": result.get("refused"),
                         "qualification": result.get("endpoint_qualification")})
        if result.get("refusal_kind") != "endpoint_pofv_geometry":
            break
    if result is None:
        result = {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                  "refused": "endpoint POFV geometry deadline exhausted"}
    result["pofv_geometry_search"] = {
        "attempts": attempts, "candidate_count": len(geometries),
        "deadline_exhausted": _deadline_expired(deadline),
        "scope": "declared_endpoint_process_only"}
    return result


def _route_coupled_endpoint_pofv_geometry(
        board, pair, endpoints, *, target_layer, geometry, clearance=0.20,
        avoid=(), minimum_coupled_fraction=0.0, deadline=None,
        verbose=False):
    """Route a pair from qualified pad-origin vias on a referenced layer.

    This fallback is intentionally narrower than a generic via escape: it is
    available only when an endpoint is an actual same-net SMD land under the
    board's declared filled/capped POFV profile.  THT endpoints already expose
    every copper layer.  Signal vias, the local reference-return field, and the
    complete coupled inner route are one rollback-safe transaction.
    """
    clearance = _pair_clearance(board, pair, clearance)
    profile_name = cec_fab_profile.board_profile_name(board)
    profile = cec_fab_profile.PROFILES.get(profile_name)
    if not profile or not profile.get("pofv"):
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "board has no declared POFV profile"}
    layer_id = board.GetLayerID(str(target_layer))
    if layer_id < 0:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "POFV target layer %s absent" % target_layer}
    requested_diameter, requested_drill = map(float, geometry)
    ordinary_diameter, ordinary_drill, via_limits = \
        cec_fab_profile.board_legal_through_via_geometry(
            board, requested_diameter, requested_drill)
    # A filled/capped via wholly contained by its assigned endpoint land is
    # governed by the explicit POFV process, not the ordinary off-pad barrel
    # rule.  Clamping it to ``m_ViasMinSize`` here made precision routing
    # disagree with both cec_fr and the decoupler cell, and falsely rejected
    # legal fine-pitch pad escapes.  ``via_at_pad_conflicts`` below proves the
    # process dimensions, exact same-net ownership, SMD attribute, and full
    # land containment before this smaller geometry can be emitted.
    via_diameter, via_drill = requested_diameter, requested_drill
    process_ok, process_reason = cec_fab_profile.pofv_dimensions(
        profile, via_diameter, via_drill)
    if not process_ok:
        return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                "refused": "declared POFV geometry is invalid: %s" %
                process_reason}
    base_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}

    def rollback():
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() not in base_ids:
                _discard_items(board,[item])

    def endpoint_pad(net, point):
        rows = sorted(_pads_on_net(board, net), key=lambda row: (
            _dist(row[2], point), str(row[0]), str(row[1])))
        if not rows or _dist(rows[0][2], point) > 0.01:
            return None
        return rows[0][3]

    p_start, p_end, n_start, n_end = endpoints
    stations = (
        ("start", ((pair["p"], p_start), (pair["n"], n_start))),
        ("end", ((pair["p"], p_end), (pair["n"], n_end))),
    )
    pending_transitions = []
    reused_barrels = []
    for side, members in stations:
        signal_points = []
        for net, point in members:
            pad = endpoint_pad(net, point)
            if pad is None:
                rollback()
                return {"name": pair["name"], "p": pair["p"],
                        "n": pair["n"],
                        "refused": "%s endpoint has no exact owning pad" % side}
            if pad.IsOnLayer(layer_id):
                if (pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)
                        or pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and not pad.HasHole()):
                    rollback()
                    return {"name":pair["name"],"p":pair["p"],"n":pair["n"],
                            "refused":"endpoint has no physical native terminal access"}
                continue
            at = _v(*point)
            code = int(board.GetNetcodeFromNetname(net))
            existing = _existing_endpoint_barrel(board, pad, at, layer_id)
            if existing["status"] == "refused":
                rollback()
                return {"name": pair["name"], "p": pair["p"], "n": pair["n"],
                        "refused": existing["reason"], "endpoint_barrel": existing}
            if existing["status"] == "reused":
                reused_barrels.append(dict(existing, side=side, net=net))
                # Reused transitions still require the same reference-return
                # proof as newly emitted vias, but do not belong to rollback.
                signal_points.append(tuple(point))
                continue
            blocking, allowed = cec_fab_profile.via_at_pad_conflicts(
                board, at, _nm(via_diameter), _nm(via_drill), code)
            contained_layers = tuple(pad.GetLayerSet().CuStack())
            # KiCad collision shapes include tangency while the published
            # clearance is legal.  One database unit preserves exact-minimum
            # eligibility without admitting any physical underrun.
            exact_clearance = max(0, _nm(clearance) - 1)
            spot_evidence = {}
            spot_clear = (blocking is None and bool(allowed)
                    and cec_fr._via_spot_clear(
                        board, at, _nm(via_diameter), exact_clearance,
                        {code}, drill_nm=_nm(via_drill), net_code=code,
                        contained_layers=contained_layers, report=spot_evidence))
            if not spot_clear:
                rollback()
                return {"name": pair["name"], "p": pair["p"],
                        "n": pair["n"],
                        "refused": "%s endpoint POFV is not qualified" % side,
                        "refusal_kind": "endpoint_pofv_geometry",
                        "endpoint_qualification": {
                            "pad_containment_ok": blocking is None and bool(allowed),
                            "pad_decisions": allowed, "via_spot": spot_evidence},
                        "pofv": {"profile": profile_name, "net": net,
                                 "point_mm": list(point)}}
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(at)
            via.SetWidth(_nm(via_diameter))
            via.SetDrill(_nm(via_drill))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(code)
            board.Add(via)
            signal_points.append(tuple(point))
        if signal_points:
            # If one member already reaches the target layer through a THT
            # land it still belongs to the transition return field.
            all_points = tuple(tuple(point) for _net, point in members)
            pair_vector = (all_points[1][0] - all_points[0][0],
                           all_points[1][1] - all_points[0][1])
            start_center = ((p_start[0] + n_start[0]) / 2.0,
                            (p_start[1] + n_start[1]) / 2.0)
            end_center = ((p_end[0] + n_end[0]) / 2.0,
                          (p_end[1] + n_end[1]) / 2.0)
            axis = (end_center[0] - start_center[0],
                    end_center[1] - start_center[1])
            center = ((all_points[0][0] + all_points[1][0]) / 2.0,
                      (all_points[0][1] + all_points[1][1]) / 2.0)
            return_diameter, return_drill, _return_limits = \
                cec_fab_profile.board_legal_through_via_geometry(
                    board, 0.60, 0.30)
            pending_transitions.append({
                "side": side, "center": center,
                "pair_vector": pair_vector, "axis": axis,
                "all_points": all_points,
                "signal_at_mm": [list(point) for point in signal_points],
                "return_diameter": return_diameter,
                "return_drill": return_drill,
            })
    if not pending_transitions:
        # Native plated lands expose every enabled copper layer already.
        # Lack of a NEW signal transition is an advantage, not a refusal of
        # the requested inner-layer corridor. Keep the exact same pair/body
        # guards and independently qualify its plated reference-return cells.
        native = route_coupled_pair(board,pair,layer=str(target_layer),
            clearance=float(clearance),verbose=verbose,avoid=avoid,
            endpoints=endpoints,pair_grid=True,
            minimum_coupled_fraction=minimum_coupled_fraction,
            deadline=deadline,allow_layer_transitions=False,prefer_grid=True)
        if native.get('refused'):
            rollback()
            return dict(native,native_terminal_access=True,
                        new_signal_transition_count=0)
        import cec_pth_pair_returns
        returns = cec_pth_pair_returns.synthesize(board,pair,deadline=deadline)
        if not returns['ok']:
            rollback()
            return dict(native,refused='native plated terminal returns refused',
                        plated_terminal_returns=returns,native_terminal_access=True,
                        new_signal_transition_count=0)
        native.update(route_mode='native-terminal-face-'+native.get('route_mode','coupled'),
            native_terminal_access=True,new_signal_transition_count=0,
            plated_terminal_returns=returns)
        return native
    return_parent_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    route_options = dict(
        layer=str(target_layer), clearance=float(clearance),
        verbose=verbose, avoid=avoid, endpoints=endpoints, pair_grid=True,
        minimum_coupled_fraction=minimum_coupled_fraction,
        deadline=deadline, allow_layer_transitions=False, prefer_grid=True)
    routed, transitions = _route_with_required_pair_returns(
        board, pair, pending_transitions, route_options=route_options,
        parent_ids=return_parent_ids)
    if routed.get("refused"):
        rollback()
        return dict(routed, pofv={"profile": profile_name,
            "diameter_mm": via_diameter, "drill_mm": via_drill,
            "board_limits": via_limits,
            "ordinary_via_mm": {"diameter": ordinary_diameter, "drill": ordinary_drill},
            "qualified_process_exception": bool(via_diameter + 1e-9 < ordinary_diameter
                                                or via_drill + 1e-9 < ordinary_drill),
            "transitions": transitions})
    routed["route_mode"] = "paired-pofv-endpoint-%s" % routed.get(
        "route_mode", "coupled")
    routed["pofv"] = {"profile": profile_name,
                      "reused_barrels": reused_barrels,
                      "diameter_mm": via_diameter,
                      "drill_mm": via_drill,
                      "board_limits": via_limits,
                      "ordinary_via_mm": {
                          "diameter": ordinary_diameter,
                          "drill": ordinary_drill},
                      "qualified_process_exception": bool(
                          via_diameter + 1e-9 < ordinary_diameter
                          or via_drill + 1e-9 < ordinary_drill),
                      "transitions": transitions}
    return routed


def _route_with_required_pair_returns(board, pair, requests, *, route_options,
                                      parent_ids):
    """One bounded joint retry if the ribbon consumes its own return seats.

    The normal copper-first attempt stays preferred. Its failed transaction is
    released back to the exact endpoint/preclosure parent before reserving a
    completely native-qualified return field and rerouting around that field.
    No inherited object is moved or removed; the caller owns outer rollback.
    Both attempts share the original deadline and all route/return rules.
    """
    deadline = route_options.get("deadline")

    def release_child():
        _discard_items(board, [item for item in board.GetTracks()
            if item.m_Uuid.AsString() not in parent_ids])

    def fields(refine):
        rows = []
        for pending in requests:
            evidence = {}
            vias, status = _add_pair_transition_returns_with_land_fallback(
                board, pending["center"], pending["pair_vector"],
                route_axis=pending["axis"], signal_points=pending["all_points"],
                portal_side=pending["side"], width=float(pair["width"]),
                gap=float(pair["gap"]), clearance=float(route_options["clearance"]),
                via_diameter_mm=pending["return_diameter"],
                via_drill_mm=pending["return_drill"], return_reach_mm=1.5,
                diagnostics=evidence, deadline=deadline, refine=refine)
            row = dict(side=pending["side"], signal_at_mm=pending["signal_at_mm"],
                return_reach_mm=1.5, return_status=status,
                return_geometry=evidence.get("selected_geometry"),
                return_geometry_attempts=evidence.get("geometry_attempts", []),
                return_vias_at_mm=[[round(v.GetPosition().x/MM,6),
                                   round(v.GetPosition().y/MM,6)] for v in vias])
            if status not in ("covered", "added"):
                return rows, dict(name=pair["name"],p=pair["p"],n=pair["n"],
                    refused="routed pair has no legal return field", return_refusal=status,
                    return_evidence=dict(evidence, side=pending["side"]))
            rows.append(row)
        return rows, None

    routed = route_coupled_pair(board, pair, **route_options)
    if routed.get("refused"):
        return dict(name=pair["name"],p=pair["p"],n=pair["n"],
            refused="qualified endpoint POFV route refused",inner_refusal=routed), []
    transitions, failure = fields(False)
    if failure is None:
        return routed, transitions
    initial = dict(failure,
        inner_route_evidence={key:routed.get(key) for key in (
            "route_mode", "segments", "coupled_coverage_pct", "graph_geometry",
            "route_quality", "portal_search_phase")})
    release_child()
    if _deadline_expired(deadline):
        return dict(initial,deadline_exhausted=True), []
    seeded, seed_failure = fields(True)
    if seed_failure is not None:
        release_child()
        return dict(seed_failure, return_route_backtrack=dict(
            attempts=2, initial_failure=initial, outcome="return_seed_refused")), []
    retried = route_coupled_pair(board, pair, **route_options)
    if retried.get("refused"):
        release_child()
        return dict(name=pair["name"],p=pair["p"],n=pair["n"],
            refused="return-constrained endpoint POFV route refused",inner_refusal=retried,
            return_route_backtrack=dict(attempts=2,initial_failure=initial,
                seeded_transitions=seeded,outcome="coupled_retry_refused")), []
    verified, failure = fields(False)
    if failure is not None:
        release_child()
        return dict(failure,return_route_backtrack=dict(attempts=2,initial_failure=initial,
            seeded_transitions=seeded,outcome="return_recheck_refused")), []
    retried["return_route_backtrack"] = dict(attempts=2,initial_failure=initial,
        seeded_transitions=seeded, final_transitions=verified,
        outcome="joint_route_and_returns_qualified",final_native_refill_required=True)
    return retried, seeded


def _coupled_corridor_refusal_message(pair, clearance, reservation_nets=()):
    """Describe the attempted search, not a global no-path or fallback proof."""
    reason = ('no qualifying coupled corridor found in the attempted search '
              '(width %g mm, gap %g mm, clearance %g mm); '
              'staged fallback may be attempted' % (
                  float(pair['width']), float(pair['gap']), float(clearance)))
    if reservation_nets:
        reason += '; observed reservation conflicts: ' + ', '.join(
            sorted({str(net) for net in reservation_nets}))
    return reason


def route_coupled_pair(board, pair, *, layer="F.Cu", clearance=None, verbose=False,
                       avoid=(), endpoints=None, pair_grid=False,
                       minimum_coupled_fraction=0.0, deadline=None,
                       allow_layer_transitions=True,
                       start_prequalified=None, prefer_grid=False):
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
    if not isinstance(prefer_grid, bool):
        raise ValueError('pair grid preference must be boolean')
    if prefer_grid and (not pair_grid or allow_layer_transitions):
        raise ValueError('prepared grid requires an enabled single-layer pair search')
    # Endpoint-only POFV has already proved and emitted every required native
    # layer transition. Rebuilding remote surface portals on this same layer
    # wastes the body-route lease, especially on unequal-pitch packages. This
    # preference changes proposal ordering only; exact member, pair-gap,
    # coupling, reservation and return-field guards remain mandatory.
    clearance = _pair_clearance(board, pair, clearance)
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

    # This conventional candidate scan does not emit copper until it returns
    # an accepted route. Keep its exact foreign-shape snapshot local to this
    # invocation; portal helpers own and roll back their own transactions.
    conventional_foreign_cache = {}

    def seg_clear(a, b, partner):
        """Clear of foreign copper AND of the PARTNER member's pads (a member may run adjacent
        to its partner's TRACK at the gap, but never across its partner's PAD -- the measured
        /CAN_L-over-U2.7 short)."""
        if a == b:
            return True
        return (cec_fr._edge_leg_clear(board, _v(*a), _v(*b),
                                       width_nm // 2, edge_mm=0.5)
                and cec_fr._tap_foreign_clear(board, _v(*a), _v(*b), width_nm,
                                          lay_id, clr_nm, own,
                                          foreign_cache=conventional_foreign_cache)
                and _partner_pads_clear(
                    board, a, b, width_nm, lay_id, partner, clr_nm)
                and _partner_tracks_clear(
                    board, a, b, width_nm, lay_id, partner,
                    clearance_nm=clr_nm))

    def escape(src, dst, partner, max_radius=3.2):
        """Shortest clear monotonic pad->lane path with at most one bend.

        A route that must reverse direction during this tiny escape is not a
        precision route.  Refuse it here so the grid/fallback tier can solve the
        topology without manufacturing a connected pseudo-stub.
        """
        candidates = []
        direct = [src, dst]
        if (_polyline_is_octilinear(direct)
                and seg_clear(src, dst, partner)):
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
                points = [src, mid, dst]
                # These are necessary acceptance predicates, not heuristics.
                # Do not spend exact KiCad shape queries on a bend that the
                # same route would inevitably reject after both queries.
                quality = _escape_candidate_quality(points)
                if (quality is not None and _polyline_is_octilinear(points)
                        and seg_clear(src, mid, partner)
                        and seg_clear(mid, dst, partner)):
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
        import cec_endpoint_roadmap
        local_context = cec_endpoint_roadmap.complete_context(
            board,pair,(P_src,P_dst,N_src,N_dst))
        if local_context is None:
            local_context = cec_endpoint_roadmap.inline_context(
                board,pair,(P_src,P_dst,N_src,N_dst),
                minimum_coupled_fraction=minimum_coupled_fraction,
                clearance_mm=(clearance if clearance is not None else 0.2))
        short_pair = _route_paired_stub(
            board, pair, (P_src, P_dst, N_src, N_dst),
            layer=layer,
            clearance=(clearance if clearance is not None else 0.2),
            avoid=reservation_avoid,
            minimum_coupled_fraction=minimum_coupled_fraction,
            complete_pair_context=local_context,
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
    endpoint_pofv_refusals = []
    portal_screen_cache = {}
    grid_failure_diagnostics = []
    conventional_diagnostics = {}

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
        if endpoint_pofv_refusals:
            refusal["endpoint_pofv_fallback"] = endpoint_pofv_refusals
        if grid_failure_diagnostics:
            refusal["grid_fallback"] = grid_failure_diagnostics
        # Expiry is where the most useful frontier evidence lives. Preserve
        # the same bounded geometric fail stack as a finite refusal, including
        # nested endpoint-only routes. This is diagnostic evidence, never a
        # global no-path proof, negative-cache grant or routing admission.
        refusal["failure_certificate"] = _pair_route_failure_certificate(
            pair, (P_src, P_dst, N_src, N_dst),
            layer=layer, width=width, gap=gap,
            clearance=(clearance if clearance is not None else 0.2),
            short_pair_refusal=short_pair_refusal,
            portal_refusal=portal_refusal,
            layer_transition_refusals=layer_transition_refusals,
            endpoint_pofv_refusals=endpoint_pofv_refusals,
            conventional_diagnostics=conventional_diagnostics,
            grid_failure_diagnostics=grid_failure_diagnostics,
            corridor_rejects=_corridor_rejects, search_interrupted=True)
        return refusal
    start_spread = _dist(P_src, N_src)
    end_spread = _dist(P_dst, N_dst)
    nominal_separation = width + gap
    spread_ratio = (max(start_spread, end_spread)
                    / max(min(start_spread, end_spread), 1e-9))
    portal_warranted = (
        pair_grid and not prefer_grid
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
            portal_screen_cache=portal_screen_cache,
            start_prequalified=start_prequalified)
        portal["phase_budget_seconds"] = (
            round(shallow_budget, 6) if shallow_budget is not None else None)
        portal["phase_wall_seconds"] = round(
            time.monotonic() - shallow_started, 6)
        if not portal.get("refused"):
            portal["portal_search_phase"] = "shallow-first"
            return portal
        portal_refusal = {"shallow": portal}
        # A shallow portal search that proved exact package fan-ins but
        # exhausted its small centreline grid has already classified this as
        # a board-scale corridor problem. Escalate that same finite portal
        # domain before trying the legacy inset fan. The inset loop performs
        # many exact KiCad shape probes and could otherwise consume the entire
        # edge deadline, starving the deeper global solve that the shallow
        # certificate explicitly requested.
        if not _deadline_expired(deadline):
            # Four exact endpoint domains exist: start/end for each legal
            # polarity.  On a dense connector field those bounded fan-in
            # screens take roughly 3--4 s each even when the eventual global
            # corridor is trivial.  A 12 s cap could therefore expire after
            # proving three domains and report the untouched fourth one as a
            # placement failure.  Reserve enough time to classify the complete
            # finite endpoint set while leaving at least half of the edge-wide
            # budget for legacy and multilayer fallbacks.
            deep_deadline, deep_budget = phase_deadline(24.0, 0.50)
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
                portal_screen_cache=portal_screen_cache,
                start_prequalified=start_prequalified)
            portal["phase_budget_seconds"] = (
                round(deep_budget, 6)
                if deep_budget is not None else None)
            portal["phase_wall_seconds"] = round(
                time.monotonic() - deep_started, 6)
            if not portal.get("refused"):
                portal["portal_search_phase"] = "deep-retry"
                return portal
            portal_refusal = dict(portal_refusal or {}, deep=portal)
    start_insets = (() if prefer_grid else tuple(sorted({1.3, 2.0, 2.8, 3.6,
                                 round(start_budget, 6)})))
    end_insets = tuple(sorted({1.3, 2.0, 2.8, 3.6,
                               round(end_budget, 6)}))
    conventional_diagnostics = {
        "candidates": 0, "middle_guard_refused": 0,
        "endpoint_escape_refused": 0, "member_crossing_refused": 0,
        "pair_gap_refused": 0, "coupling_refused": 0,
        "non_octilinear_refused": 0,
        "reservation_barrier_refused": 0,
        "reservation_hits": [],
    }
    # This finite legacy fan is only one search class. Exhausting it must
    # yield to the native-layer/portal classes, not return a pair-wide timeout.
    conventional_deadline, _conventional_budget = phase_deadline(8.0, 0.20)
    for start_inset in start_insets:
      if _deadline_expired(conventional_deadline):
        break
      for end_inset in end_insets:
        if _deadline_expired(conventional_deadline):
            break
        if start_inset + end_inset >= span - 0.5:
            continue                              # clusters too close to seat a coupled run
        Se = (Sc[0] + ux * start_inset, Sc[1] + uy * start_inset)
        De = (Dc[0] - ux * end_inset, Dc[1] - uy * end_inset)
        for shift in (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.6, -2.6):
            if _deadline_expired(conventional_deadline):
                break
            conventional_diagnostics["candidates"] += 1
            po, no = sgn * off + shift, -sgn * off + shift
            Pls = (Se[0] + px * po, Se[1] + py * po)
            Ple = (De[0] + px * po, De[1] + py * po)
            Nls = (Se[0] + px * no, Se[1] + py * no)
            Nle = (De[0] + px * no, De[1] + py * no)
            # Inset and lateral shifts preserve this template's middle
            # heading. An arbitrary terminal bearing is not an octilinear
            # middle: reject it before four endpoint fans and copper probes,
            # leaving the unchanged deadline available to portal/layer solves.
            if (not _polyline_is_octilinear([Pls, Ple])
                    or not _polyline_is_octilinear([Nls, Nle])):
                conventional_diagnostics["non_octilinear_refused"] += 1
                continue
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
            if (not _polyline_is_octilinear(p_pts)
                    or not _polyline_is_octilinear(n_pts)):
                conventional_diagnostics["non_octilinear_refused"] += 1
                continue
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
    # A surface route can be sealed by the component's own force/sense or
    # protection copper even though the endpoint land explicitly supports a
    # filled/capped via-in-pad.  Try that smaller-discontinuity escape before
    # moving the pair to remote surface portals.  Eligibility is entirely
    # profile/pad/layer based and the helper owns rollback plus return vias.
    if (pair_grid and allow_layer_transitions
            and not _deadline_expired(deadline)):
        try:
            pofv_layers = tuple(
                cec_fab_profile.referenced_signal_layers(
                    board, hint=board.GetFileName() or ""))
        except Exception:                              # noqa: BLE001
            pofv_layers = ()
        pofv_layers = tuple(candidate for candidate in pofv_layers
                            if candidate != layer)
        for target_index, target_layer in enumerate(pofv_layers):
            if _deadline_expired(deadline):
                break
            if deadline is None:
                pofv_deadline, pofv_budget = None, None
            else:
                now = time.monotonic()
                remaining = max(0.0, float(deadline) - now)
                # Reserve an equal share for every remaining endpoint layer,
                # every remote-layer portal and the final grid class. Repeated
                # 75%-of-remainder grants starved the later legal layers.
                jobs_left = len(pofv_layers)-target_index + len(pofv_layers)+1
                pofv_budget = min(75.0, remaining / jobs_left)
                pofv_deadline = min(float(deadline), now + pofv_budget)
            pofv_started = time.monotonic()
            pofv_route = _route_coupled_endpoint_pofv(
                board, pair, (P_src, P_dst, N_src, N_dst),
                target_layer=target_layer,
                clearance=(clearance if clearance is not None else 0.2),
                avoid=reservation_avoid,
                minimum_coupled_fraction=minimum_coupled_fraction,
                deadline=pofv_deadline, verbose=verbose)
            pofv_route["phase_budget_seconds"] = (
                round(pofv_budget, 6) if pofv_budget is not None else None)
            pofv_route["phase_wall_seconds"] = round(
                time.monotonic() - pofv_started, 6)
            if not pofv_route.get("refused"):
                pofv_route["portal_search_phase"] = "endpoint-pofv"
                return pofv_route
            # This solver result is already bounded. Preserve it rather than
            # whitelist fields: a new post-route guard must not disappear at
            # this boundary, as return failures previously did.
            endpoint_pofv_refusals.append(dict(pofv_route,
                layer=target_layer, reason=pofv_route.get("refused")))

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
                    1, len(target_layers) - target_index + 1)
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
            pair_net_codes=(int(pc), int(nc)),
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
        octilinear = (_polyline_is_octilinear(p_pts)
                      and _polyline_is_octilinear(n_pts))
        if (p_clear and n_clear and not p_avoid and not n_avoid
                and octilinear
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
            "octilinear": bool(octilinear),
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
    _why = _coupled_corridor_refusal_message(
        pair, clearance if clearance is not None else 0.2, _corridor_rejects)
    refused = {"name": pair["name"], "p": p_net, "n": n_net,
               "refused": _why}
    if short_pair_refusal is not None:
        refused["short_pair_fallback"] = short_pair_refusal
    if portal_refusal is not None:
        refused["portal_fallback"] = portal_refusal
    if layer_transition_refusals:
        refused["layer_transition_fallback"] = layer_transition_refusals
    if endpoint_pofv_refusals:
        refused["endpoint_pofv_fallback"] = endpoint_pofv_refusals
    refused["failure_certificate"] = _pair_route_failure_certificate(
        pair, (P_src, P_dst, N_src, N_dst),
        layer=layer, width=width, gap=gap,
        clearance=(clearance if clearance is not None else 0.2),
        short_pair_refusal=short_pair_refusal,
        portal_refusal=portal_refusal,
        layer_transition_refusals=layer_transition_refusals,
        endpoint_pofv_refusals=endpoint_pofv_refusals,
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


def _pair_layer_refusal_message(rows, *, reason_chars=240):
    """Human-readable layer summary; exact attempts stay structured once.

    Formatting the entire nested layer report into a reason duplicated tens
    of thousands of characters through every upstream gate and log line.
    """
    return "layer ensemble exhausted: " + "; ".join(
        "%s: %s" % (str(row.get("layer") or "unknown"),
                     str(row.get("reason") or "refused")[:reason_chars])
        for row in rows)


def _portal_screen_should_yield(accepted, soft_deadline, *, now=None, minimum_candidates=1):
    """Yield optional beam refinement, never abandon an empty escape domain.

    Proving one escape remains work-conserving under the full hard deadline.
    Once there is a usable beam, reserve time to screen its peer and route the
    actual middle instead of spending the entire budget seeking a fourth seat.
    """
    return bool(len(accepted) >= minimum_candidates and soft_deadline is not None and
                (time.monotonic() if now is None else float(now)) >= soft_deadline)


def _fair_subdeadline(absolute_deadline, remaining_jobs, *, now=None):
    """Reserve an equal share of the remaining bounded search for each job."""
    current = time.monotonic() if now is None else float(now)
    remaining = max(0.0, float(absolute_deadline) - current)
    return min(float(absolute_deadline),
               current + remaining / max(1, int(remaining_jobs)))


def _inline_alternative_deadline(absolute_deadline, remaining_choices, *,
                                 policy='complete-attempt', max_attempt_s=10., now=None):
    """One alternative's effort, not another division of required work.

    A ten-second maximum constituent and the caller's absolute parent bound
    both apply. Nested calls inherit the absolute returned deadline; none
    can replenish it. The explicit legacy policy supports controlled replay,
    not weaker geometry, current, field or final saved-board admission.
    """
    if (type(policy)is not str or policy not in ('complete-attempt','legacy-fair')
            or type(remaining_choices)is not int or not 1<=remaining_choices<=32
            or type(max_attempt_s)not in(int,float)or not math.isfinite(max_attempt_s)
            or not 0<max_attempt_s<=10.
            or now is not None and(type(now)not in(int,float)or not math.isfinite(now))
            or absolute_deadline is not None and(type(absolute_deadline)not in(int,float)
                or not math.isfinite(absolute_deadline))):
        raise ValueError('bounded_inline_alternative_budget_policy_required')
    current=time.monotonic()if now is None else float(now)
    if absolute_deadline is None:return current+float(max_attempt_s)
    proposed=(float(absolute_deadline)if policy=='complete-attempt'else
        _fair_subdeadline(absolute_deadline,remaining_choices,now=current))
    return min(float(absolute_deadline),current+float(max_attempt_s),proposed)


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


def _pair_local_articulation_allowance(route_reports):
    """Return unavoidable repeated local length for a layered pair graph.

    A pad MST is a useful lower bound for an ordinary pair, but it assumes a
    station is entered only once.  A plated-through multidrop station whose
    incident tree edges deliberately use different layers must repeat its
    package fanout on every used layer.  Count only the additional, already
    admitted local legs beyond the shortest layer at that station.  The first
    leg remains covered by the pad MST, and trunk length can never enlarge the
    allowance.  Grouping by distinct layer also prevents duplicate reports
    from weakening the gate.
    """
    by_station = {}
    local_roles = {"terminal_stub", "junction_runway", "junction_spoke"}
    for row in route_reports or ():
        if not isinstance(row, dict):
            continue
        role = str(row.get("graph_role") or "")
        terminal = str(row.get("terminal") or "")
        layer = str(row.get("layer") or "")
        if role not in local_roles or not terminal or not layer:
            continue
        length = max(0.0, float(row.get("length_mm", 0.0) or 0.0))
        key = (role, terminal)
        # One physical local route per station/layer is authoritative.  If a
        # caller retained exploratory duplicates, the shortest is the only
        # defensible lower-bound witness.
        by_station.setdefault(key, {})[layer] = min(
            length, by_station.get(key, {}).get(layer, float("inf")))
    detail = []
    allowance = 0.0
    for (role, terminal), by_layer in sorted(by_station.items()):
        lengths = sorted(float(value) for value in by_layer.values())
        extra = sum(lengths[1:]) if len(lengths) > 1 else 0.0
        if extra <= 1e-9:
            continue
        allowance += extra
        detail.append({
            "graph_role": role,
            "terminal": terminal,
            "layers": sorted(by_layer),
            "baseline_local_length_mm": round(lengths[0], 6),
            "additional_layer_length_mm": round(extra, 6),
        })
    return round(allowance, 9), detail


def _complete_pair_candidate_detour(board,pair,*,route_reports=()):
    """Reject a complete overlong candidate while alternative search is live.

    A local leg does not own the whole pair's MST budget; leave incomplete
    flow-through/multidrop trees to transaction-end admission. Once both nets
    are connected, use that SAME admission now, not a mean-member proxy that
    can return from a shallow search and fail only in its caller.
    """
    from cec_staged_fr import fully_connected_nets
    nets={pair['p'],pair['n']}
    counts={name:0 for name in nets}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in counts:
                counts[pad.GetNetname()]+=1
    if min(counts.values())<2:
        return {'ok':True,'applicable':False,'reason':'no_complete_physical_pair_obligation'}
    complete,_incomplete=fully_connected_nets(board,nets)
    if not nets<=complete:
        return {'ok':True,'applicable':False,'reason':'partial_pair_tree'}
    result=_pair_transaction_detour(board,pair,route_reports=route_reports)
    return dict(result,applicable=True)


def _pair_transaction_detour(board, pair, *, limit=2.0,
                             minimum_span_mm=2.0, route_reports=()):
    """Reject a connected pair that is grossly longer than its pad topology.

    Coupling, gap, and skew can all look excellent on a needless perimeter
    loop.  Compare each member's complete copper length with the Euclidean pad
    MST before the precision transaction is committed.  The MST supports
    ordinary two-terminal, flow-through, and multidrop pairs with one generic
    lower bound; the generous 2x limit leaves room for legal obstacle detours.
    """
    articulation_allowance, articulation_detail = (
        _pair_local_articulation_allowance(route_reports))
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
        reference = span + articulation_allowance
        raw_ratio = (length / span) if span > 1e-9 else None
        ratio = (length / reference) if reference > 1e-9 else None
        refused = bool(span >= float(minimum_span_mm)
                       and ratio is not None
                       and ratio > float(limit) + 1e-9)
        ok = ok and not refused
        rows.append({
            "net": net_name,
            "copper_length_mm": round(length, 6),
            "endpoint_mst_mm": round(span, 6),
            "local_articulation_allowance_mm": round(
                articulation_allowance, 6),
            "detour_reference_mm": round(reference, 6),
            "raw_endpoint_mst_ratio": (
                round(raw_ratio, 6) if raw_ratio is not None else None),
            "ratio": round(ratio, 6) if ratio is not None else None,
            "refused": refused,
        })
    return {"schema": 1, "ok": ok, "limit": float(limit),
            "minimum_span_mm": float(minimum_span_mm),
            "local_articulation_allowance_mm": round(
                articulation_allowance, 6),
            "local_articulation": articulation_detail,
            "members": rows}


def _pair_detour_failure_certificate(board, pair, detour, created_ids,
                                     endpoint_stations, *, local_search=None,
                                     route_reports=(), tree_edges=()):
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
    route_legs = []
    for report in (route_reports or ()):
        route_legs.append({
            field: report.get(field) for field in (
                "graph_role", "terminal", "neighbor", "edge", "layer",
                "route_mode", "segments", "length_mm", "coupled_len_mm",
                "coupled_coverage_pct", "minimum_coupled_fraction",
                "portal_search_phase", "reused_route_template")
            if report.get(field) is not None
        })
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
        "route_legs": route_legs,
        "tree_edges": [dict(row) for row in (tree_edges or ())],
    }


def _scheduled_coupled_pairs(board, pairs):
    """Deterministic topology-constrained-first schedule for pair nets.

    Span alone is not a constraint measure.  A short point-to-point/flow-
    through pair can consume the only legal corridor of a longer multidrop
    tree even when its endpoint reservations remain clear.  Route complete
    multidrop topologies first, then flow-through packages, then ordinary
    point-to-point pairs.  Within a topology class, more physical stations and
    single-layer edges lead before the historical shorter-span tie-breaker.
    This is the pair analogue of establishing a bus backbone before drops.
    """
    rows = []
    for pair in pairs:
        flow = _flow_through_pair_legs(board, pair)
        multidrop = (_multidrop_pair_plan(board, pair)
                     if flow is None else None)
        if multidrop is not None:
            topology = "multidrop"
            topology_rank = 0
            station_count = len(multidrop.get("terminals") or ())
            constrained_edges = sum(
                1 for edge in (multidrop.get("edges") or ())
                if len(edge.get("layers") or ()) <= 1)
        elif flow is not None:
            topology = "flow-through"
            topology_rank = 1
            station_count = len(flow[1] or ()) + 2
            constrained_edges = len(flow[0] or ())
        else:
            topology = "point-to-point"
            topology_rank = 2
            station_count = len(_pair_endpoint_stations(board, pair))
            constrained_edges = 0
        span = round(_pair_route_span(board, pair), 6)
        rows.append((topology_rank, -station_count, -constrained_edges,
                     span, str(pair.get("name") or ""), pair,
                     topology, station_count, constrained_edges))
    rows.sort(key=lambda row: row[:5])
    return [row[5] for row in rows], [
        {"name": row[5].get("name"), "p": row[5].get("p"),
         "n": row[5].get("n"), "span_mm": row[3],
         "topology": row[6], "station_count": int(row[7]),
         "constrained_edge_count": int(row[8]),
         "order": index + 1,
         "ordering_policy": "topology-constrained-first"}
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


def _shared_split_support_centers(board, current_pair, future_pair):
    """Return future endpoint centres shared with a current series cell.

    Back-to-back declared pair segments commonly meet on opposite lands of
    two identical series components.  A rectangular future-launch reservation
    around one land pair is deliberately wider than the copper and therefore
    overlaps the other land pair.  Treating that synthetic overlap as an
    obstacle makes the current segment impossible even when both physical
    routes have compatible polarity. Actual foreign-pad copper still guards
    the shared cell; the caller replaces the redundant broad reservation with
    a proven outward launch when possible, and reports unqualified proposals.
    """
    if not current_pair or not future_pair:
        return ()
    current = _pair_endpoint_stations(board, current_pair)
    future = _pair_endpoint_stations(board, future_pair)
    current_refs = {
        frozenset(str(ref) for ref in station.get("physical_refs") or ())
        for station in current
        if station.get("kind") == "split-member-footprints"}
    current_refs.discard(frozenset())
    return tuple(
        tuple(float(value) for value in station["center"])
        for station in future
        if station.get("kind") == "split-member-footprints"
        and frozenset(str(ref) for ref in
                      station.get("physical_refs") or ()) in current_refs)


def _shared_series_launch_contract(board, current_pair, future_pair, station,
                                   *, launch_mm=1.0, avoid=()):
    """Reserve native outward escapes at a split two-land series station.

    A shared support is not permission to erase every future escape resource.
    Derive each outward direction from the actual opposite land, independently
    (the two components need not have equal rotations). Only a complete,
    geometrically clear two-member proposal becomes a reservation. This is a
    planning constraint, NOT routed copper or a coupled-pair qualification.
    Rectangle-only consumers conservatively decline envelopes that obstruct
    the current contacts or their outward launches. Native copper checks own
    pad clearance; pad AABBs must not be expanded by trace radius a second time.
    No board, refdes, or location exceptions are used.
    """
    launch_mm = float(launch_mm)
    if not math.isfinite(launch_mm) or not 0 < launch_mm <= 3.6:
        raise ValueError('invalid shared series launch reach')
    report = dict(ok=False, policy='native-outward-series-v1',
                  launch_mm=launch_mm, members=[], reservations=[])

    def refuse(reason):
        report['reason'] = reason
        return report

    if not current_pair or not future_pair:
        return refuse('missing paired segment identity')
    all_nets = [pair.get(member) for pair in (current_pair, future_pair)
                for member in ('p', 'n')]
    if not all(all_nets) or len(set(all_nets)) != 4:
        return refuse('series segments require four distinct nets')
    refs = set(station.get('physical_refs') or ())
    if station.get('kind') != 'split-member-footprints' or len(refs) != 2:
        return refuse('not a two-footprint split station')
    contacts_by_member = [station.get(member + '_contacts') or () for member in ('p', 'n')]
    if (any(len(contacts) != 1 for contacts in contacts_by_member)
            or {contacts[0].get('ref') for contacts in contacts_by_member} != refs):
        return refuse('ambiguous native station contacts')
    by_ref = {}
    for footprint in board.GetFootprints():
        by_ref.setdefault(str(footprint.GetReference()), []).append(footprint)
    width = float(future_pair.get('width') or .2)
    current_width = float(current_pair.get('width') or .2)
    gap = float(future_pair.get('gap') or 0)
    clearance = max(_pair_clearance(board, current_pair),
                    _pair_clearance(board, future_pair))
    if any(not math.isfinite(v) or v <= 0 for v in (width, current_width)):
        return refuse('invalid pair width')
    if not math.isfinite(gap) or gap < 0:
        return refuse('invalid pair gap')
    proposals, current_launches = [], []
    for member in ('p', 'n'):
        contacts = station.get(member + '_contacts') or ()
        if len(contacts) != 1:
            return refuse('ambiguous native station contact')
        contact = contacts[0]
        ref = str(contact.get('ref') or '')
        if ref not in refs or len(by_ref.get(ref, ())) != 1:
            return refuse('ambiguous native support footprint')
        pads = list(by_ref[ref][0].Pads())
        present = [pad for pad in pads if pad.GetNetname() == current_pair[member]]
        pending = [pad for pad in pads if pad.GetNetname() == future_pair[member]]
        if len(pads) != 2 or len(present) != 1 or len(pending) != 1:
            return refuse('support is not a unique opposite-land series connection')
        src, dst = present[0], pending[0]
        point = contact.get('point_mm') or ()
        if (len(point) != 2 or not all(math.isfinite(float(v)) for v in point)
                or dst.GetNumber() != str(contact.get('pad'))
                or dst.GetPosition() != _v(*point)):
            return refuse('station does not match the live native pad')
        if any(pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
               for pad in (src, dst)):
            return refuse('outward contract requires undrilled surface lands')
        common_layers = [layer for layer in board.GetEnabledLayers().CuStack()
                         if src.IsOnLayer(layer) and dst.IsOnLayer(layer)]
        if len(common_layers) != 1 or common_layers[0] not in (pcbnew.F_Cu, pcbnew.B_Cu):
            return refuse('support does not have one native outer copper layer')
        layer_id = common_layers[0]
        start = (dst.GetPosition().x / MM, dst.GetPosition().y / MM)
        dx = (dst.GetPosition().x - src.GetPosition().x) / MM
        dy = (dst.GetPosition().y - src.GetPosition().y) / MM
        distance = math.hypot(dx, dy)
        if distance <= 1e-9:
            return refuse('coincident opposite lands')
        finish = (start[0] + launch_mm * dx / distance,
                  start[1] + launch_mm * dy / distance)
        if not _segment_is_octilinear(start, finish):
            return refuse('outward direction is not octilinear')
        layer = board.GetLayerName(layer_id)
        if (_crosses_avoid((start, finish), _avoid_for_layer(avoid, layer), width)
                or not cec_fr._edge_leg_clear(board, _v(*start), _v(*finish), _nm(width / 2))
                or not cec_fr._tap_foreign_clear(board, _v(*start), _v(*finish),
                    _nm(width), layer_id, _nm(clearance), {dst.GetNetCode()})):
            return refuse('native outward escape is obstructed')
        radius = width / 2 + clearance
        rectangle = (min(start[0], finish[0]) - radius,
                     min(start[1], finish[1]) - radius,
                     max(start[0], finish[0]) + radius,
                     max(start[1], finish[1]) + radius,
                     'future-series:%s:%s:%s' %
                     (future_pair.get('name') or future_pair[member], ref, member), layer)
        proposals.append((rectangle, layer_id, pcbnew.SHAPE_SEGMENT(
            _v(*start), _v(*finish), _nm(width))))
        current_start = (src.GetPosition().x / MM, src.GetPosition().y / MM)
        current_finish = (current_start[0] - launch_mm * dx / distance,
                          current_start[1] - launch_mm * dy / distance)
        current_launches.append((layer, current_start, current_finish))
        report['members'].append(dict(member=member, ref=ref, net=future_pair[member],
            pad_uuid=dst.m_Uuid.AsString(), opposite_pad_uuid=src.m_Uuid.AsString(),
            start_mm=list(start), finish_mm=list(finish), layer=layer))
    # Prospective stubs may not cross one another or block either current launch.
    # Native pad clearance alone cannot check not-yet-created future tracks.
    if (proposals[0][1] == proposals[1][1] and proposals[0][2].Collide(
            proposals[1][2], _nm(max(clearance, gap)))):
        return refuse('prospective member escapes conflict')
    for layer, start, finish in current_launches:
        if _crosses_avoid((start, finish), _avoid_for_layer(
                [proposal[0] for proposal in proposals], layer), current_width):
            return refuse('rectangular projection would obstruct a current launch')
    report.update(ok=True, reason=None, reservations=[row[0] for row in proposals])
    return report


def _future_pair_launch_reservations(board, pairs, *, current_pair=None,
                                     diagnostics=None, avoid=()):
    """Compile name-agnostic F.Cu launch reservations for pending pairs.

    The remote launch of every pending pair remains reserved.  At a shared
    split-series support cell, however, the broad synthetic box is suppressed
    because it overlaps the current segment's opposite pads by construction;
    a qualified native outward contract replaces it when representable. Native
    pad copper remains mandatory; an unqualified direction is reported, not
    treated as an escape guarantee.
    """
    reservations = []
    suppressed = []
    shared_contracts = []
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
        shared_centers = _shared_split_support_centers(board, current_pair, pair)
        shared_stations = [station for station in _pair_endpoint_stations(board, pair)
                           if tuple(station['center']) in shared_centers]
        for index, endpoints in enumerate(legs):
            rows = _pair_leg_launch_reservations(
                endpoints, pair, leg_index=index)
            pa, pb, na, nb = endpoints
            if _dist(pa, na) + _dist(pb, nb) > _dist(pa, nb) + _dist(pb, na):
                na, nb = nb, na
            for row, p_point, n_point in zip(rows, (pa, pb), (na, nb)):
                # Match the actual end, never merely containment in a broad box:
                # short legs can put BOTH boxes over the same shared station.
                center = ((p_point[0] + n_point[0]) / 2,
                          (p_point[1] + n_point[1]) / 2)
                matches = [station for station in shared_stations
                           if _dist(center, station['center']) <= 1e-6
                           and all(len(station.get(member + '_contacts') or ()) == 1
                                   and _v(*station[member + '_contacts'][0]['point_mm']) == _v(*point)
                                   for member, point in (('p', p_point), ('n', n_point)))]
                if len(matches) == 1:
                    contract = _shared_series_launch_contract(
                        board, current_pair, pair, matches[0], avoid=avoid)
                    shared_contracts.append(dict(future_pair=pair.get('name'),
                        reservation=row[4], **contract))
                    if contract['ok']:
                        reservations.extend(contract['reservations'])
                    suppressed.append({
                        "reservation": row[4],
                        "future_pair": pair.get("name"),
                        "reason": "shared_split_support_exact_pads_guard",
                    })
                else:
                    reservations.append(row)
    if diagnostics is not None:
        diagnostics.update({
            "suppressed_shared_support_count": len(suppressed),
            "suppressed_shared_support": suppressed,
            "shared_series_contracts": shared_contracts,
        })
    return reservations


# ---------------------------------------------------------------------------
# the precision ladder
# ---------------------------------------------------------------------------
def _native_pair_completion(board, pair, *, max_items=8192, signal_view=None):
    """Read-only all-pad native connectivity, independent of lock bookkeeping.

    A connected but unqualified pair needs an owned repair, not a second route
    laid over its existing copper. Missing/bounded graph evidence is unknown.
    """
    if signal_view is not None:
        import cec_enrolled_pair_signal_view as enrolled_signal
        return enrolled_signal.completion(signal_view, board, pair, max_items=max_items)
    result = dict(complete=False, connected=None, nets={}, release_authority=False)
    try:
        if type(max_items) is not int or not 1 <= max_items <= 32768:
            raise ValueError('invalid_native_pair_inventory_bound')
        for name in (pair['p'], pair['n']):
            pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
                    if pad.GetNetname() == name]
            copper = [t for t in board.GetTracks() if t.GetNetname() == name]
            copper += [zone for zone in board.Zones()
                       if not zone.GetIsRuleArea() and zone.GetNetname() == name]
            items = pads + copper
            ids = {str(item.m_Uuid.AsString()) for item in items}
            if len(items) > max_items or len(ids) != len(items):
                raise ValueError('native_pair_inventory_incomplete_or_ambiguous')
            if len(pads) < 2:
                result['nets'][name] = dict(connected=False, pad_count=len(pads))
                continue
            conn = pcbnew.CONNECTIVITY_DATA()
            for item in items:
                if conn.Add(item) is not True:
                    raise ValueError('native_pair_connectivity_add_refused')
            wanted = {str(pad.m_Uuid.AsString()) for pad in pads}
            reached = {str(pads[0].m_Uuid.AsString())} | {
                str(item.m_Uuid.AsString()) for item in conn.GetConnectedItems(pads[0])}
            result['nets'][name] = dict(connected=wanted <= reached,
                pad_count=len(pads), unreachable_pad_uuids=sorted(wanted - reached),
                disconnected_copper_uuids=sorted(str(item.m_Uuid.AsString())
                    for item in copper if item.GetClass() in ('PCB_TRACK','PCB_VIA','PCB_ARC')
                    and str(item.m_Uuid.AsString()) not in reached))
        result.update(complete=True, connected=all(row['connected'] for row in result['nets'].values()))
    except Exception as exc:
        result['reason'] = str(exc)
    return result


def _preexisting_pair_receiving(board, pair, *, board_path):
    """Reuse a measured existing route, or expose its precise owned debt."""
    native = _native_pair_completion(board, pair)
    result = dict(native=native, applicable=native.get('connected') is True,
        qualified=False, release_authority=False, board_mutated=False)
    if not result['applicable']:
        return result
    if any(row.get('disconnected_copper_uuids') for row in native['nets'].values()):
        result['reason']='existing_connected_pair_has_unowned_native_copper_islands'
        return result
    try:
        import cec_constraints
        import cec_field_coupling
        physical = cec_constraints.high_speed_pair_summary(board_path or '', board=board)
        matches = [row for row in physical['pairs']
                   if {row['p'], row['n']} == {pair['p'], pair['n']}]
        if not physical['applicable'] or len(matches) != 1:
            raise ValueError('existing_native_pair_physical_contract_unavailable')
        result['physical'] = matches[0]
        field = cec_field_coupling.field_coupling_summary(board_path or '', board=board)
        blockers = [row for row in field['interactions'] if row.get('blocking')
                    and {pair['p'], pair['n']}.intersection(row['nets'])]
        result['field_blockers'] = blockers
        result['qualified'] = not matches[0]['violations'] and not blockers
        result['reason'] = ('existing_native_pair_meets_physical_contract' if result['qualified']
                            else 'existing_connected_pair_requires_owned_physical_repair')
    except Exception as exc:
        result['reason'] = 'existing_native_pair_qualification_unknown:' + str(exc)
    return result


def _qualify_pair_candidate(board, pair, rep, *, pair_pre_ids, board_path,
                             pair_avoid, endpoint_stations, future_pin_access=None):
    """Shared complete-pair checks, also used before selecting a topology.

    The checks and normalization are the existing final transaction authority.
    Callers retrying another topology must restore temporary package preclosure
    after a refusal, since this function can normalize or remove that copper.
    """
    if not rep.get('refused') and future_pin_access is not None:
        import cec_future_pin_access
        access = cec_future_pin_access.preserve(board, future_pin_access)
        rep['future_pin_access_admission'] = access
        if not access['ok']:
            rep['refused'] = 'priority pair consumed a reserved non-pair pin launch'
            rep['failure_certificate'] = dict(
                conclusion='future_pin_access_nonregression_refused',
                classification=['future_pin_access'], access=access,
                no_path_proof=False)
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
            board, include_nets=pair_nets, pair_declarations=[pair], lock=True)
        pair_created_ids = {
            track.m_Uuid.AsString() for track in board.GetTracks()
            if (track.m_Uuid.AsString() not in pair_pre_ids
                and track.GetNetname() in pair_nets)}
        local_normalization = _drop_fully_covered_tracks(
            board, pair_created_ids)
        # Package closure may be wider than its coupled trunk. The short wide
        # prefix cannot be deleted as a duplicate of the long narrow leg, but
        # the GENERATED long leg can end at their shared coverage boundary.
        # Preserve the explicit junction and every inherited copper primitive.
        from cec_copper_overlap import trim_covered_prefixes
        local_normalization['covered_prefixes'] = trim_covered_prefixes(
            board, pair_created_ids)
        pair_created_ids = {
            track.m_Uuid.AsString() for track in board.GetTracks()
            if (track.m_Uuid.AsString() not in pair_pre_ids
                and track.GetNetname() in pair_nets)}
        # A complete native tree may join a branch to the interior of
        # an earlier leg. Trim only terminal excess after every real
        # pad obligation exists, then repair an exposed degree-two
        # bend before whole-pair physics and saved-board DRC. Doing
        # this during virtual-portal construction would erase needed
        # unfinished legs, so this is intentionally a transaction-end
        # normalization, never a blanket dangling-track deletion.
        from cec_terminal_overhang import (
            trim_generated_overhangs, repair_generated_acute_corners)
        local_normalization["terminal_overhangs"] = trim_generated_overhangs(
            board, pair_created_ids, nets=pair_nets)
        clearance_resolver = cec_fr._project_netclass_resolver(board_path)
        junction_clearance = max(
            float((clearance_resolver(net) or {}).get("clearance") or 0.2)
            for net in pair_nets)
        local_normalization["acute_corners"] = repair_generated_acute_corners(
            board, pair_created_ids, nets=pair_nets,
            clearance_mm=junction_clearance, avoid=pair_avoid)
        import cec_pair_pad_guard
        post_transform_ids={track.m_Uuid.AsString() for track in board.GetTracks()
                            if track.m_Uuid.AsString() not in pair_pre_ids}
        partner_pad_clearance=cec_pair_pad_guard.created_tracks(
            board,pair,post_transform_ids,clearance_mm=junction_clearance)
        post_closure_geometry = _pair_graph_geometry(
            board, pair, pair_created_ids, physical_only=True)
        if not partner_pad_clearance['ok']:
            post_closure_geometry=dict(post_closure_geometry,ok=False,
                issues=list(post_closure_geometry.get('issues',()))+partner_pad_clearance['issues'])
        post_closure_geometry['partner_pad_clearance']=partner_pad_clearance
        missing = sorted(
            pair_nets - cec_fr.owned_locked_nets_board(board))
        if (missing or int(local.get("pair_refused", 0) or 0)
                or not post_closure_geometry["ok"]):
            # Refuse atomically: never leave a half-owned pair as an
            # obstacle for the high-effort fallback tier.
            for track in list(board.GetTracks()):
                if (track.m_Uuid.AsString() not in pair_pre_ids
                        and track.GetNetname() in pair_nets):
                    _discard_items(board,[track])
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
    if not rep.get("refused"):
        detour = _pair_transaction_detour(
            board, pair, route_reports=rep.get("legs") or ())
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
                    local_search=rep.get("local_search"),
                    route_reports=rep.get("legs"),
                    tree_edges=rep.get("tree_edges")))
            # Roll the complete pair transaction back atomically so
            # the high-effort fallback or placement repair sees open
            # routing resources, not a rejected locked perimeter wall.
            for track in list(board.GetTracks()):
                if (track.m_Uuid.AsString() not in pair_pre_ids
                        and track.GetNetname() in pair_nets):
                    _discard_items(board,[track])
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
        import cec_pair_skew
        skew_admission = cec_pair_skew.from_board(board, pair)
        rep['physical_skew_admission'] = skew_admission
        if not skew_admission['ok']:
            rep['refused'] = (
                'whole-pair copper skew %.3fmm exceeds %.3fmm' %
                (skew_admission['skew_mm'], skew_admission['limit_mm']))
            rep['failure_certificate'] = {
                'conclusion': 'exact_route_rejected_by_whole_pair_skew',
                'classification': ['whole_pair_skew'],
                'skew': skew_admission,
            }
    if not rep.get('refused'):
        pair_created_ids = {
            track.m_Uuid.AsString()
            for track in board.GetTracks()
            if (track.m_Uuid.AsString() not in pair_pre_ids
                and track.GetNetname() in pair_nets)}
        # Ownership limits mutation, not the electrical receiver's view. An
        # excellent new subpath cannot conceal an inherited uncoupled branch.
        coupling = _pair_coupling_summary(board, pair)
        member_lengths = {}
        for net_name in sorted(pair_nets):
            member_lengths[net_name] = sum(
                track.GetLength() / MM
                for track in board.GetTracks()
                if (track.GetClass() == "PCB_TRACK"
                    and track.GetNetname() == net_name
                    ))
        coupling_admission = _pair_coupling_contract(
            pair, coupling, member_lengths,
            endpoint_stations=endpoint_stations)
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
                    _discard_items(board,[track])
            rep["refused"] = (
                "precision pair coupled coverage %.1f%% is below "
                "%.1f%% and uncoupled length %.3fmm exceeds %.3fmm"
                % (coupling_admission["coupled_coverage_pct"],
                   coupling_admission[
                       "minimum_coupled_coverage_pct"],
                   coupling_admission["uncoupled_length_mm"],
                   coupling_admission[
                       "uncoupled_length_budget_mm"]))
    if not rep.get('refused'):
        import cec_pth_pair_returns
        returns = cec_pth_pair_returns.synthesize(board, pair)
        rep['plated_terminal_returns'] = returns
        if not returns['ok']:
            rep['refused'] = returns['reason']
    if not rep.get('refused') and future_pin_access is not None:
        # Package preclosure, normalization and supporting return synthesis
        # above also create copper. Recheck the final state, not just the
        # initially returned path planner result.
        import cec_future_pin_access
        access = cec_future_pin_access.preserve(board, future_pin_access)
        rep['future_pin_access_admission'] = access
        if not access['ok']:
            rep['refused'] = 'priority pair consumed a reserved non-pair pin launch'
            rep['failure_certificate'] = dict(
                conclusion='future_pin_access_nonregression_refused',
                classification=['future_pin_access'], access=access,
                no_path_proof=False)
    if not rep.get('refused'):
        # Own the aggressor/victim obligation before declaring the critical
        # route complete. A locally coupled/connected pair can still disturb
        # another net, or cut its reference plane with a supporting barrel.
        # Evaluate the final normalized native transaction on isolated actual
        # GND fills, not just its first path proposal or a stackup layer name.
        import cec_field_coupling
        field_delta = cec_field_coupling.assess_native_additions(
            board, pair_pre_ids, board_path=board_path)
        rep['native_field_admission'] = field_delta
        if field_delta['ok'] is not True:
            rep['refused'] = 'whole-pair native field delta refused: ' + str(field_delta['reason'])
            rep['failure_certificate'] = dict(
                conclusion='native_pair_field_nonregression_refused',
                classification=['aggressor_victim_field'],
                field=field_delta, no_path_proof=False)
    return rep


from cec_return_plane_preview import with_candidate_reference


@with_candidate_reference
def precision_route_board(board, *, board_path=None, kelvin_width=0.25,
                          verbose=True, do_kelvin=True, do_pairs=True,
                          avoid=(), kelvin_avoid=(), pair_grid=False,
                          existing_locked_nets=(), include_pair_names=None,
                          _pair_schedule_override=None, _group_order_retry=True,
                          _pair_search_deadline=None, _negotiated_pair_scope=None):
    """Run the precision ladder on an already-loaded board, in place.

    ``existing_locked_nets`` names fully-owned nets laid by an earlier pipeline
    stage.  A coupled pair whose two members are already in that set is reported
    as covered and is not duplicated.  This is what lets materialization route
    the pair before broad GND closure while the later route orchestrator merely
    protects that exact copper.
    """
    board_path = board_path or board.GetFileName() or ""
    derived_pairs = derive_coupled_pairs(board_path, board=board) if do_pairs else []
    if _pair_schedule_override is not None:
        _pair_schedule_override=list(_pair_schedule_override)
        if (len(_pair_schedule_override)!=len(derived_pairs)
                or len(set(_pair_schedule_override))!=len(_pair_schedule_override)
                or set(_pair_schedule_override)!={pair['name'] for pair in derived_pairs}):
            raise ValueError('internal pair schedule must name every pair exactly once')
    if _pair_search_deadline is not None and not math.isfinite(float(_pair_search_deadline)):
        raise ValueError('internal pair deadline must be finite')
    selected_names = None
    if include_pair_names is not None:
        if not do_pairs or isinstance(include_pair_names, (str, bytes)):
            raise ValueError('pair scope requires enabled pairs and a collection of exact names')
        selected_names = {str(name) for name in include_pair_names}
        known_names = {str(pair.get('name')) for pair in derived_pairs}
        unknown = selected_names - known_names
        if not selected_names or unknown:
            raise ValueError('pair scope is empty or contains unknown names: %s; known names: %s' %
                             (sorted(unknown), sorted(known_names)))
    negotiated_scope=set(_negotiated_pair_scope or ())
    if negotiated_scope and (_group_order_retry or negotiated_scope!=selected_names
                             or _pair_schedule_override is None or _pair_search_deadline is None):
        raise ValueError('negotiated launch scope requires a bounded non-recursive exact group transaction')
    pre_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
    existing_locked_nets = set(existing_locked_nets or ())

    # ---- R2 KELVIN (canonical inner-edge taps, pre-FR on the uncontended board) ----
    kelvin = {"taps": 0, "by_net": {}, "refused": {}, "segments": 0}
    if do_kelvin:
        kelvin = cec_fr.synthesize_kelvin_taps(
            board, width=kelvin_width, avoid=kelvin_avoid)
        import cec_sense_auxiliary
        kelvin['auxiliary_inputs']=cec_sense_auxiliary.construct(
            board,board_path=board_path,width_mm=kelvin_width,avoid=kelvin_avoid)
        if verbose:
            print("[precision] R2 kelvin: %d tap(s) laid %s; refused %s; "
                  "future-power obstacles=%d"
                  % (kelvin.get("taps", 0), kelvin.get("by_net", {}),
                     kelvin.get("refused", {}), len(kelvin_avoid or ())),
                  file=sys.stderr)

    # ---- R3 COUPLED PAIRS (deterministic, guarded, refuse-not-force) ----
    routed_pairs, refused_pairs = [], []
    pair_schedule = []
    created_by_pair = {}
    group_order_repair = None
    if verbose and avoid:
        print("[precision] R3 pairs: %d reserved pour corridor(s) treated as obstacles"
              % len(avoid), file=sys.stderr)
    if do_pairs:
        pairs_to_route, pair_schedule = _scheduled_coupled_pairs(
            board, derived_pairs)
        if _pair_schedule_override is not None:
            override=list(_pair_schedule_override)
            by_name={pair['name']:(pair,row) for pair,row in zip(pairs_to_route,pair_schedule)}
            pairs_to_route=[by_name[name][0] for name in override]
            pair_schedule=[dict(by_name[name][1],order=i+1,ordering_policy='bounded-shared-series-retry')
                           for i,name in enumerate(override)]
        for pair_index, pair in enumerate(pairs_to_route):
            if selected_names is not None and str(pair.get('name')) not in selected_names:
                pair_schedule[pair_index]['skipped'] = 'outside_transaction_scope'
                continue
            existing = _preexisting_pair_receiving(board, pair, board_path=board_path)
            if existing['native'].get('complete') is not True:
                refused_pairs.append(dict(name=pair['name'],p=pair['p'],n=pair['n'],
                    refused='native pair completion is unknown: ' + str(
                        existing['native'].get('reason', 'incomplete_evidence')),
                    existing_native_receiving=existing,
                    failure_certificate=dict(conclusion='native_pair_completion_unknown',
                        classification=['native_contact_evidence'],no_path_proof=False)))
                continue
            if existing['applicable']:
                if not existing['qualified']:
                    refused_pairs.append(dict(name=pair['name'],p=pair['p'],n=pair['n'],
                        refused=existing['reason'], existing_native_receiving=existing,
                        failure_certificate=dict(conclusion='connected_pair_owned_repair_required',
                            classification=['existing_pair_physical_qualification'],
                            no_path_proof=False, existing=existing)))
                    pair_schedule[pair_index]['skipped'] = 'existing_connected_pair_repair_debt'
                    continue
                routed_pairs.append({
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "route_mode": "preexisting-native-qualified", "segments": 0,
                    "existing_native_receiving": existing,
                })
                pair_schedule[pair_index]['skipped'] = 'existing_native_route_received'
                continue
            if {pair["p"], pair["n"]}.issubset(existing_locked_nets):
                refused_pairs.append(dict(name=pair['name'],p=pair['p'],n=pair['n'],
                    refused='declared locked pair does not own every native terminal',
                    existing_native_receiving=existing))
                continue
            # A bounded search space is not an operational bound when each
            # exact-copper probe is expensive.  Give every complete pair
            # transaction one shared wall-clock budget across surface,
            # portal, layer-transition, and flow-through legs.  Exhaustion is
            # a named refusal handed to the staged fallback, never a stalled
            # unattended wave.  The environment knob supports deliberate
            # high-effort runs without weakening the default fail-closed cap.
            requested_pair_budget_s = max(5.0, float(os.environ.get(
                "CEC_PRECISION_PAIR_TIMEOUT", "240")))
            import cec_operation_budget as operation_budget
            pair_budget_s = operation_budget.available_timeout(
                requested_pair_budget_s, os.environ, reserve_s=30)
            if _pair_search_deadline is not None:
                pair_budget_s=min(pair_budget_s,max(0.,float(_pair_search_deadline)-time.monotonic()))
            pair_deadline = time.monotonic() + pair_budget_s
            pair_schedule[pair_index]['budget'] = {
                'requested_s': requested_pair_budget_s, 'allowed_s': pair_budget_s,
                'completion_reserve_s': 30}
            operation_budget.progress('precision_pair_search', pair=pair['name'],
                                      allowed_s=pair_budget_s)
            if pair_budget_s <= 0:
                refused_pairs.append({
                    'name': pair['name'], 'p': pair['p'], 'n': pair['n'],
                    'refused': 'enclosing budget cannot fund pair search and completion',
                    'pair_search_budget_s': 0, 'pair_search_budget_exhausted': True})
                continue
            reservation_diagnostics = {}
            future_pairs=pairs_to_route[pair_index + 1:]
            # Inside an atomic whole-group retry, future member access is
            # qualified by actually routing that member, not by a guessed
            # rectangular surrogate. Source power and all OUTSIDE-group
            # reservations remain hard obstacles. No partial group is adopted.
            future_pair_avoid = _future_pair_launch_reservations(
                board, [pending for pending in future_pairs
                        if pending['name'] not in negotiated_scope], current_pair=pair,
                diagnostics=reservation_diagnostics, avoid=avoid)
            if negotiated_scope:
                reservation_diagnostics['atomic_future_launch_deferred']=[pending['name']
                    for pending in future_pairs if pending['name'] in negotiated_scope]
            # High-priority routing cannot consume the only sampled vertical
            # launch of an unrelated pin on the same package. Plan native-legal
            # columns before laying pair copper and retain these contracts even
            # during pair-order negotiation. No inherited route is unlocked.
            import cec_future_pin_access
            future_pin_access = cec_future_pin_access.plan(board, pair,
                board_path=board_path, excluded_nets={net for p in derived_pairs
                    for net in (p['p'],p['n'])}, deadline_monotonic=pair_deadline)
            pair_schedule[pair_index]['future_pin_access'] = future_pin_access
            if not future_pin_access['complete']:
                refused_pairs.append(dict(name=pair['name'],p=pair['p'],n=pair['n'],
                    refused='future pin-access planning budget exhausted',
                    pair_search_budget_exhausted=True,future_pin_access=future_pin_access))
                continue
            pair_avoid = (tuple(avoid or ()) + tuple(future_pair_avoid)
                          + tuple(future_pin_access['reservations']))
            pair_schedule[pair_index]["future_launch_reservations"] = len(
                future_pair_avoid)
            pair_schedule[pair_index]["future_launch_reservation_policy"] = \
                reservation_diagnostics
            pair_pre_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            endpoint_stations = _pair_endpoint_stations(board, pair)
            flow = _flow_through_pair_legs(board, pair)
            multidrop = (_multidrop_pair_plan(board, pair)
                         if flow is None else None)
            # Local package obligations precede the external trunk for *all*
            # duplicated pair lands, not just intermediate protectors. A
            # reversible terminal has the same scarce escape resources: a
            # trunk through one selected land can strand its duplicate. Let
            # the existing exact, atomic linker establish that copper first;
            # the trunk must route around it. No reference/package allowlist,
            # extra clearance exception, or late broad-router ownership.
            package_pad_preclosure = cec_fr.synthesize_same_footprint_links(
                board, include_nets={pair["p"], pair["n"]},
                pair_declarations=[pair], lock=True,deadline_monotonic=pair_deadline)
            preclosure_refused = bool(
                int(package_pad_preclosure.get("pair_refused", 0) or 0)
                or int(package_pad_preclosure.get("refused", 0) or 0))
            if preclosure_refused:
                rep = {
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "refused": "package-native pair closure refused before external routing",
                }
            elif flow is None and multidrop is None:
                rep = route_coupled_pair(
                    board, pair, verbose=verbose, avoid=pair_avoid,
                    pair_grid=pair_grid, deadline=pair_deadline)
            elif multidrop is not None:
                from cec_native_copper_snapshot import CopperSnapshot
                temporary_parent=CopperSnapshot(board,
                    {item.m_Uuid.AsString() for item in board.GetTracks()}-pair_pre_ids)
                rep = _route_multidrop_topologies(
                    board, pair, multidrop, avoid=pair_avoid, verbose=verbose,
                    deadline=pair_deadline,
                    candidate_qualifier=lambda candidate:_qualify_pair_candidate(
                        board,pair,candidate,pair_pre_ids=pair_pre_ids,
                        board_path=board_path,pair_avoid=pair_avoid,
                        endpoint_stations=endpoint_stations,
                        future_pin_access=future_pin_access),
                    restore_parent=temporary_parent.restore)
            else:
                legs, stations = flow
                from cec_native_copper_snapshot import CopperSnapshot
                temporary_parent=CopperSnapshot(board,
                    {item.m_Uuid.AsString() for item in board.GetTracks()}-pair_pre_ids)
                rep = _route_flow_bank_orders(
                    board, pair, legs, stations, avoid=pair_avoid,
                    verbose=verbose, pair_grid=pair_grid, deadline=pair_deadline,
                    candidate_qualifier=lambda candidate:_qualify_pair_candidate(
                        board,pair,candidate,pair_pre_ids=pair_pre_ids,
                        board_path=board_path,pair_avoid=pair_avoid,
                        endpoint_stations=endpoint_stations,
                        future_pin_access=future_pin_access),
                    restore_parent=temporary_parent.restore)
                if rep.get('refused'):
                    # Include the package-native pre-closure in atomic rollback.
                    for track in list(board.GetTracks()):
                        if track.m_Uuid.AsString() not in pair_pre_ids:
                            _discard_items(board,[track])
            rep = _qualify_pair_candidate(
                board, pair, rep, pair_pre_ids=pair_pre_ids,
                board_path=board_path, pair_avoid=pair_avoid,
                endpoint_stations=endpoint_stations,
                future_pin_access=future_pin_access)
            rep.setdefault("endpoint_stations", endpoint_stations)
            rep["package_pad_preclosure"] = package_pad_preclosure
            if rep.get("refused"):
                # Whole-pair quality and duplicate-pad gates can reject after
                # successful routing. Supporting return vias belong to that
                # failed transaction too, not just its two signal net names.
                rep['rollback_created_items'] = _rollback_created_tracks(board, pair_pre_ids)
                rep.setdefault("pair_search_budget_s", pair_budget_s)
                rep.setdefault("pair_search_budget_exhausted",
                               bool(rep.get("flow_leg_budget_exhausted")
                                    or rep.get("search_budget_exhausted")
                                    or _deadline_expired(pair_deadline)))
                from cec_search_completion import annotate_refusal
                rep = annotate_refusal(rep)
                refused_pairs.append(rep)
                if verbose:
                    print("[precision] R3 %s REFUSED: %s"
                          % (rep["name"], rep["refused"]), file=sys.stderr)
            else:
                rep.setdefault("pair_search_budget_s", pair_budget_s)
                routed_pairs.append(rep)
                created_by_pair[pair['name']]={item.m_Uuid.AsString() for item in board.GetTracks()}-pair_pre_ids

        if _group_order_retry and refused_pairs and created_by_pair:
            from cec_pair_order_repair import retry_groups

            def retry_order(names, deadline):
                scope=set(names);pending=iter(names)
                override=[next(pending) if pair['name'] in scope else pair['name'] for pair in pairs_to_route]
                fixed_owned=existing_locked_nets | {
                    net for row in routed_pairs if row['name'] not in scope
                    for net in (row['p'],row['n'])}
                return precision_route_board(board,board_path=board_path,
                    kelvin_width=kelvin_width,verbose=verbose,do_kelvin=False,
                    do_pairs=True,avoid=avoid,kelvin_avoid=kelvin_avoid,
                    pair_grid=pair_grid,existing_locked_nets=fixed_owned,
                    include_pair_names=names,_pair_schedule_override=override,
                    _group_order_retry=False,_pair_search_deadline=deadline,
                    _negotiated_pair_scope=names)

            routed_pairs,refused_pairs,group_order_repair=retry_groups(
                board,pairs_to_route,routed_pairs,refused_pairs,created_by_pair,pre_ids,
                route_order=retry_order)

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
                         if rep.get("route_mode") in (
                             "preexisting-locked", "preexisting-native-qualified")
                         for net in (rep["p"], rep["n"])}
    # Lock geometry first; exclude a whole net only with whole-net evidence.
    # A local Kelvin/input strap on a mixed force net cannot freeze its still
    # disconnected shunt, terminal, filter or bus-voltage consumers out of the
    # remaining stages. Native locked-subgraph ownership is conservative;
    # independently received existing pairs retain their separate authority.
    import cec_locked_net_ownership
    lock_scope=cec_locked_net_ownership.certificate(board,nets=locked_nets)
    partial_locked_nets={net for net in locked_nets
                        if not lock_scope['nets'][net]['complete']}
    locked_nets-=partial_locked_nets
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
    local_pair_return_vias = cec_fr.group_local_pair_return_vias(
        board, [
            item for item in board.GetTracks()
            if item.m_Uuid.AsString() in created_ids
            and item.GetClass() == "PCB_VIA"
            and item.GetNetname() == "GND"])
    generated_items = [
        {"uuid": t.m_Uuid.AsString(), "net": t.GetNetname(),
         "kind": t.GetClass()}
        for t in board.GetTracks()
        if t.m_Uuid.AsString() in created_ids]
    pair_nets = {net for rep in routed_pairs
                 for net in (rep.get("p"), rep.get("n")) if net}
    kelvin_nets = set((kelvin.get("by_net") or {}).keys())
    kelvin_nets.update(r['net'] for r in (kelvin.get('auxiliary_inputs') or {}).get('generated_items',()))
    route_quality = cec_route_quality.analyze_board(
        board, critical_nets=pair_nets | kelvin_nets,
        track_uuid_scope=created_ids)

    pairs_ok = (len(refused_pairs) == 0
                and route_quality.get("ok", False)
                and route_quality.get("geometry_ok", False))
    kelvin_ok = (not any((kelvin.get("refused") or {}).values())
                 and (kelvin.get('auxiliary_inputs') or {}).get('ok',True))
    report = {
        "locked_nets": sorted(locked_nets),
        "partial_locked_nets": sorted(partial_locked_nets-covered_pair_nets),
        "whole_net_locked_ownership": lock_scope,
        "locked_item_uuids": sorted(created_ids),
        # Physical reuse is completion authority even when a valid inherited
        # route has no LOCKED flags. The residual coordinator passes these
        # nets to native revalidation/exclusion, whose keepouts cover every
        # actual track, via and pad, without rewriting the source lock flags.
        "received_existing_pair_nets": sorted(covered_pair_nets),
        "n_locked_segments": n_locked,
        "n_new_locked_segments": n_new_locked,
        "generated_items": generated_items,
        "generated_item_count": len(generated_items),
        "local_pair_return_vias": local_pair_return_vias,
        "kelvin": kelvin,
        "pairs": {"routed": routed_pairs, "refused": refused_pairs,
                  "schedule": pair_schedule,
                  **({'group_order_repair':group_order_repair}
                     if group_order_repair and group_order_repair.get('attempts') else {})},
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
                    kelvin_avoid=(), pair_grid=False, include_pair_names=None):
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
        existing_locked_nets=existing_locked,
        include_pair_names=include_pair_names)
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
        report["local_pair_return_rule"] = (
            cec_fr.ensure_local_pair_return_via_rule(out_board, report))
        # Precision can add vias after the input board's zones were last
        # filled.  Preserve a reviewable refusal artifact whose plane antipads
        # match its new copper; otherwise its DRC evidence contains phantom
        # zone/via collisions and sends the next repair rung in the wrong
        # direction.
        report["zones_refilled"] = bool(cec_fr.refill_zones(out_board))
        report["out"] = out_board
        raise PrecisionRouteRefused(message, report)
    pcbnew.SaveBoard(out_board, board)
    # DRC/netclass and executable route ownership context travel with every
    # renamed board artifact.  Use the shared sidecar authority so precision
    # routing cannot silently drop qualified fab rules, pour ownership, or the
    # project filename rebind while other pipeline stages preserve them.
    report["copied_sidecars"] = cec_fr.copy_project_sidecars(
        placed_board, out_board)
    report["local_pair_return_rule"] = (
        cec_fr.ensure_local_pair_return_via_rule(out_board, report))
    # A precision transaction is not serialized until every pre-existing zone
    # has been rebuilt around the tracks and vias it just added.  Exact DRC is
    # the next pipeline boundary, so stale fill must fail here rather than be
    # misclassified as a constructive routing defect.  Fresh-load refill is
    # intentionally delegated to cec_fr.refill_zones; it also avoids pcbnew's
    # in-memory double-fill instability.
    report["zones_refilled"] = bool(cec_fr.refill_zones(out_board))
    report["zone_refill_policy"] = "fresh-load-before-exact-admission"
    report["out"] = out_board
    if not report["zones_refilled"]:
        raise PrecisionRouteRefused(
            "precision route zone refill failed before exact admission",
            report)
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
