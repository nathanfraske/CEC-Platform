#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own the local IC-power-pin -> bypass-cap -> GND-entry cell.

Placement already assigns a distinct value-qualified capacitor to each audited
device supply pin. This routing pass turns that ownership into copper before
the broad router runs:

* shortest guarded local supply link;
* immediate GND return at the capacitor;
* via in pad only for a fabrication profile that explicitly permits POFV;
* otherwise the shortest legal dogbone;
* all-or-nothing rollback for each local cell; and
* exact per-terminal admission for the board-wide GND-access reservation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import heapq
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache

import pcbnew

import cec_constraints
import cec_fab_profile
import cec_fr
import cec_stage_admission
import cec_search_budget
import cec_return_escape
import cec_device_power_roles
from cec_native_items import discard_items


MM = 1_000_000
DEFAULT_LOCAL_CELL_WORK_LIMIT = 4096
DEFAULT_RAIL_COMPLETION_WORK_LIMIT = 262144
ENDPOINT_NECKDOWN_GROUP = cec_fr.ENDPOINT_NECKDOWN_GROUP
ENDPOINT_NECKDOWN_RULE_BEGIN = cec_fr.ENDPOINT_NECKDOWN_RULE_BEGIN
ENDPOINT_NECKDOWN_RULE_END = cec_fr.ENDPOINT_NECKDOWN_RULE_END


def _group_endpoint_neckdowns(board, items, full_width):
    """Put only generated sub-class endpoint tracks in a named rule group."""
    return cec_fr.group_endpoint_neckdowns(board, items, full_width)


def _admit_link_neckdowns(board, items, full_width, *, persist_group):
    """Qualification is mandatory even when a read-only probe omits groups.

    Group creation can return partial success. Never treat its rejected copper
    as a constructed link, or leave rejected trial items on the native board.
    """
    narrow = [item for item in items
              if item.GetClass() in ("PCB_TRACK", "PCB_ARC")
              and item.GetWidth() < full_width]
    qualified, rejected = cec_fr._qualified_endpoint_neckdown_tracks(
        board, items, full_width)
    complete = {t.m_Uuid.AsString() for t in qualified} == {
        t.m_Uuid.AsString() for t in narrow}
    evidence = {"qualified": complete and not rejected,
                "tracks": len(qualified), "rejected": rejected}
    if not evidence["qualified"]:
        discard_items(board, items)
        return False, evidence
    if persist_group:
        evidence.update(_group_endpoint_neckdowns(board, items, full_width) or {})
    return True, evidence


def _ensure_endpoint_neckdown_rule(board_path, report):
    """Install the narrow-track exception only for the generated PCB group.

    The Power netclass remains at its trunk width.  KiCad evaluates custom
    rules in reverse order, so this final, group-qualified rule overrides that
    floor only for endpoint tracks which the guarded generator explicitly put
    in ``CEC_LOCAL_ENDPOINT_NECKDOWN``.  No net name, reference, or board
    coordinate is baked into the exception.
    """
    return cec_fr.ensure_endpoint_neckdown_rule(board_path, report)


def _missing_assignment_report(row):
    """Preserve why one bypass requirement has no one-to-one assignment."""
    nearest_ref = row.get("nearest_ref")
    nearest_mm = row.get("nearest_mm")
    limit_mm = row.get("max_mm")
    report = {
        "owner": row.get("ref"), "pin": row.get("pin"),
        "rail": row.get("rail"), "cap": nearest_ref,
        "return_rail": row.get("return_rail") or "GND",
        "owner_return_pin": row.get("return_pin"),
        "status": "refused",
        "nearest_compatible_ref": nearest_ref,
        "nearest_compatible_mm": (round(float(nearest_mm), 3)
                                  if nearest_mm is not None else None),
        "assignment_limit_mm": (round(float(limit_mm), 3)
                                if limit_mm is not None else None),
    }
    if nearest_ref is None or nearest_mm is None:
        report["reason"] = "no compatible local bypass capacitor"
        report["assignment_failure"] = "no_compatible_component"
    elif (limit_mm is not None
          and not cec_constraints._within_physical_distance_limit(
              nearest_mm, limit_mm)):
        report["reason"] = "nearest compatible capacitor outside assignment limit"
        report["assignment_failure"] = "compatible_component_out_of_range"
        report["assignment_gap_mm"] = round(
            float(nearest_mm) - float(limit_mm), 3)
    else:
        # A compatible part exists inside the radius but bipartite ownership
        # assigned it to another requirement.  Moving this package cannot
        # manufacture another distinct capacitor.
        report["reason"] = "compatible in-limit capacitor already owned"
        report["assignment_failure"] = "distinct_component_contention"
        report["assignment_gap_mm"] = 0.0
    return report


def _ordered_assigned_cells(board, assignment):
    """Return a serialization-independent local-cell reservation order.

    KiCad preserves footprint insertion order, but that order is not electrical
    authority and can change after an otherwise lossless save.  A simple
    package usually exposes an easy plane portal which a denser neighbouring
    package can then share.  Reserve those portal-forming cells first, followed
    by natural owner/pin order; ordinary rail/GND cells precede a same-owner
    rail-to-rail EMC cell.  Every generation and audit stage consumes this one
    order so a board cannot pass merely because pcbnew rewrote its file.
    """
    def natural(value):
        return tuple(int(part) if part.isdigit() else part.lower()
                     for part in re.split(r"(\d+)", str(value)))

    def key(row):
        requirement = row.get("requirement") or {}
        owner_ref = str(requirement.get("ref") or "")
        owner = board.FindFootprintByReference(owner_ref)
        pad_count = len(list(owner.Pads())) if owner is not None else 1 << 20
        rail_to_rail = ((requirement.get("return_rail") or "GND") != "GND")
        return (pad_count, natural(owner_ref), rail_to_rail,
                natural(requirement.get("pin") or ""),
                natural(row.get("cap_ref") or ""))

    return sorted((assignment.get("assigned") or {}).values(), key=key)


def _owner_ground_contract(owner):
    """Use selected manufacturer metadata, never a ground-tied pin heuristic.

    Missing metadata remains explicitly unresolved. A contradictory selected
    package/MPN is an error, not permission to fall back to a net-name guess.
    """
    if owner is None or not hasattr(owner, "GetValue"):
        return None
    return cec_device_power_roles.footprint_contract(owner)


def _owner_ground_pads(owner):
    """Actual grounded return pins for covered packages.

    The existing native-net-only scope for uncovered devices is retained,
    but it does not acquire manufacturer-role qualification. Control,
    address, reference and signal pins tied to GND are not device returns
    when an authoritative pin table is available. A power-return pin may
    be grounded (for example a comparator's negative supply).
    """
    if owner is None:
        return []
    model = _owner_ground_contract(owner)
    return [pad for pad in owner.Pads()
            if pad.GetNetname() == "GND" and pad.GetNetCode() > 0
            and (model is None or model["pins"].get(str(pad.GetPadName()))
                 in ("ground", "power_return"))]


def _owner_return_role_evidence(owner, return_rail):
    if return_rail != "GND":
        return {"scope": "explicit-rail-to-rail-contract",
                "manufacturer_ground_role_qualified": None}
    model = _owner_ground_contract(owner)
    return {"scope": "manufacturer-pin-functions" if model else "native-net-only-unresolved",
            "device_package": model["device_package"] if model else None,
            "source": model["source"] if model else None,
            "manufacturer_ground_role_qualified": model is not None,
            "current_or_fabrication_qualification": False}


def _cell_return_pads(requirement, owner, cap):
    """Resolve the capacitor and owner terminals for the second loop leg.

    Most bypass cells return to the owner's nearest actual ground-return pad,
    not its nearest pin tied to GND. Device-specific
    EMC contracts may instead name another supply pin (for example the NXP
    TJA1051/3 VIO-to-VCC capacitor).  Keeping the topology in the requirement
    prevents a generic ground-return generator from silently rewriting a
    rail-to-rail bypass into the wrong circuit.
    """
    return_rail = requirement.get("return_rail") or "GND"
    cap_return = next((pad for pad in cap.Pads()
                       if pad.GetNetname() == return_rail), None) \
        if cap is not None else None
    owner_returns = (_owner_ground_pads(owner) if return_rail == "GND" else
                     [pad for pad in owner.Pads()
                      if pad.GetNetname() == return_rail and pad.GetNetCode() > 0]
                     if owner is not None else [])
    if cap_return is not None:
        owner_returns = [pad for pad in owner_returns
                         if pad.GetNetCode() == cap_return.GetNetCode()]
    # An explicit return must belong to this actual package and eligible pin
    # set. Refuse a bad contract instead of silently replacing its endpoint.
    explicit = requirement.get("return_pad")
    pin = requirement.get("return_pin")
    if explicit is not None:
        owner_returns = [pad for pad in owner_returns
                         if pad.m_Uuid.AsString() == explicit.m_Uuid.AsString()]
    if pin is not None:
        owner_returns = [pad for pad in owner_returns
                         if str(pad.GetPadName()) == str(pin)]
    return return_rail, cap_return, owner_returns


@lru_cache(maxsize=32)
def _literal_netclass_table(payload):
    """Parse only byte-identical Source context; callers read it afresh.

    Cache no path/mtime guess or native default. The bounded byte-key cache
    avoids repeated JSON parsing inside local route geometry queries.
    """
    from cec_route_dimensions import NetclassTable, DimensionContractError
    try:
        data=json.loads(payload)
        settings=data['net_settings']
        if type(settings)is not dict:raise ValueError('net_settings_not_an_object')
        table=NetclassTable(settings,source='exact_saved_source_project')
        if not table.classes:raise ValueError('no_authored_netclasses')
        return table
    except (KeyError,ValueError,TypeError)as exc:
        raise DimensionContractError('unreadable_saved_local_cell_geometry:'+str(exc))from exc


def _netclass(board, net):
    # LoadBoard does not attach a project. GetNetClassSlow can therefore
    # return an unrelated process-wide Default, even for a literal .5-mm
    # Power assignment. A saved exact sibling, never a neighbouring/newest
    # project, owns local geometry when it exists. This supplies no current
    # role, load, branch-sharing, POFV exception or copper-cut authority.
    from pathlib import Path
    import cec_route_dimensions as dimensions
    name=board.GetFileName()
    project=Path(name).with_suffix('.kicad_pro')if name else None
    if project is not None and project.is_file():
        payload=project.read_bytes()
        if len(payload)>4194304:
            raise dimensions.DimensionContractError('bounded_saved_local_cell_project_required')
        table=_literal_netclass_table(payload)
        spec={**table.classes.get('Default',{}),**table.resolve(net)}
        for key in('track_width','clearance','via_diameter','via_drill'):
            value=spec.get(key)
            if (type(value)not in(int,float)or not math.isfinite(value)
                    or value<0 or key!='clearance'and value==0):
                raise dimensions.DimensionContractError('positive_saved_local_cell_dimension_required:'+key)
        compiled=dimensions.compile_spec(spec,limits=dimensions.board_limits(board))
        return dict(width=math.ceil(compiled['track_width']*MM),
            clearance=max(math.ceil(spec['clearance']*MM),int(board.GetDesignSettings().m_MinClearance)),
            via_dia=compiled['via_diameter'],via_drill=compiled['via_drill'])
    try:
        klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
        return {
            "width": klass.GetTrackWidth(),
            "clearance": klass.GetClearance(),
            "via_dia": klass.GetViaDiameter() / MM,
            "via_drill": klass.GetViaDrill() / MM,
        }
    except Exception:                                    # noqa: BLE001
        return {
            "width": pcbnew.FromMM(0.25),
            "clearance": pcbnew.FromMM(0.20),
            "via_dia": 0.6, "via_drill": 0.3,
        }


def _supply_current_widths(board, net):
    """Existing sustained-current authority, not a new per-device budget.

    A class width is only a geometric minimum. In particular a service rail
    with a small netclass can still have an executable multi-amp contract.
    Keep the same margin/profile authority as final current-width receiving.
    GND entry sizing remains owned by its separate injection/plane checks.
    """
    import cec_current_topology as topology
    from cec_route_dimensions import current_trace_widths
    hint=os.environ.get('CEC_THERMAL_BOARD_HINT') or str(board.GetFileName() or '')
    # Use the same executable net/domain binding as current-width receiving.
    # Static rail tables alone omit hierarchy-bound and topology-declared
    # intermediate supplies. An incomplete domain still grants no authority;
    # conflicting static/domain declarations raise instead of falling back.
    authority=topology.current_contract_for_net(net,hint,
        topology.board_current_domains(board,board_hint=hint)) if hint else None
    if authority is None:return None
    profile=cec_fab_profile.active_profile_name(board,hint=hint)
    if not profile:raise ValueError('supply_current_fabrication_profile_required')
    layers=tuple(cec_fab_profile.enabled_copper_layers(board))
    widths=current_trace_widths(authority,layers,profile,rise_c=30.)
    return dict(current_authority=authority,profile=profile,
        required_by_layer_nm={board.GetLayerID(name):math.ceil(value*MM)
            for name,value in widths.items()},release_authority=False,
        barrel_capacity_qualified=False)


def _board_legal_through_via_geometry(board, diameter_mm, drill_mm):
    """Compatibility wrapper for the shared board-rule authority."""
    return cec_fab_profile.board_legal_through_via_geometry(
        board, diameter_mm, drill_mm)


def _hole_to_hole_clear(board, position, drill_mm, *, tolerance_mm=0.0005,
                        ignore_via_uuids=()):
    """Check the net-independent finished-hole edge clearance.

    Same-net copper is allowed to overlap, so the copper spot guard cannot
    enforce drill spacing.  Include every existing via and drilled footprint
    pad using the board's resolved fabrication-profile floor.
    """
    try:
        minimum = float(board.GetDesignSettings().m_HoleToHoleMin) / MM
    except Exception:                                    # noqa: BLE001
        minimum = 0.25
    candidate_radius = float(drill_mm) / 2.0
    conflicts = []
    ignore_via_uuids = set(ignore_via_uuids)

    def consider(point, other_drill_mm, identity):
        center = math.hypot(
            point.x - position.x, point.y - position.y) / MM
        edge = center - candidate_radius - float(other_drill_mm) / 2.0
        if edge + float(tolerance_mm) < minimum:
            conflicts.append({
                "item": identity, "center_mm": round(center, 4),
                "edge_mm": round(edge, 4),
                "minimum_mm": round(minimum, 4),
            })

    for item in board.GetTracks():
        if item.GetClass() == "PCB_VIA":
            if item.m_Uuid.AsString() in ignore_via_uuids:
                continue
            consider(item.GetPosition(), item.GetDrillValue() / MM,
                     "via:%s" % item.m_Uuid.AsString())
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() not in (
                    pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            drill = pad.GetDrillSize()
            other = max(drill.x, drill.y) / MM
            if other > 0:
                consider(pad.GetPosition(), other, "%s.%s" % (
                    footprint.GetReference(), pad.GetPadName()))
    return not conflicts, conflicts


def _shortest_track_path_mm(board, left, right, *, snap_mm=0.000001):
    """Return explicit-copper path length between two pads, excluding zones.

    No coarse endpoint or land expansion is permitted. A 60 um grid can
    fabricate a short supply/shared-return path across an actual copper gap,
    even when native connectivity sees a separate long detour. The 1 nm
    native-coordinate floor is shared by every caller, not only GND lookup.

    A global connectivity answer is insufficient for bypass ownership: both
    pads can be connected through a distant plane entry and still form a poor
    high-frequency loop.  This compact graph follows routed track/arc endpoints
    and through vias.  Zones are deliberately excluded so only a visible local
    link can satisfy the supply-path contract.
    """
    if not math.isfinite(snap_mm) or not 0 < snap_mm <= 0.000001:
        raise ValueError("local copper proof requires native-resolution snapping")
    if left.GetNetCode() <= 0 or left.GetNetCode() != right.GetNetCode():
        return None
    snap = max(1, pcbnew.FromMM(snap_mm))
    prepared = _explicit_track_graph(board, left.GetNetCode(), (left, right), snap)
    return _query_explicit_track_path_mm(prepared, left, right, snap)


def _explicit_track_graph(board, net_code, pad_seeds, snap):
    """Build one invocation-local explicit graph; never a reusable approval.

    A queried VIA adds no pad-centre seed: every real via is already present
    on its enabled copper faces. Consequently one PAD -> VIA observation may
    reuse this exact graph for its several target barrels. PAD -> PAD callers
    must still seed BOTH queried lands, and all later calls rebuild geometry.
    No persistent board cache, native connectivity, fill, or capacity credit.
    """

    def key(point, layer):
        return (int(round(point.x / snap)), int(round(point.y / snap)),
                int(layer))

    graph = {}
    points = {}

    def add_node(node, point):
        graph.setdefault(node, [])
        points.setdefault(node, point)

    def edge(a, b, cost):
        graph.setdefault(a, []).append((b, float(cost)))
        graph.setdefault(b, []).append((a, float(cost)))

    segments = []
    for item in board.GetTracks():
        if item.GetNetCode() != net_code:
            continue
        if item.GetClass() == "PCB_VIA":
            point = item.GetPosition()
            nodes = []
            for layer in item.GetLayerSet().CuStack():
                if not board.IsLayerEnabled(layer):
                    continue
                node = key(point, layer)
                add_node(node, point); nodes.append(node)
            for node in nodes[1:]:
                edge(nodes[0], node, 0.0)
            continue
        start, end, layer = item.GetStart(), item.GetEnd(), item.GetLayer()
        a, b = key(start, layer), key(end, layer)
        add_node(a, start); add_node(b, end)
        try:
            length = item.GetLength() / MM
        except Exception:                                # noqa: BLE001
            length = math.hypot(end.x - start.x, end.y - start.y) / MM
        segments.append((a, b, start, end, length, item.GetClass()))

    # Exact collinear reuse can leave a queried land on the INTERIOR of a
    # retained stroke, without a redundant endpoint-bearing new segment.
    # Seed only these two real pad centres on their actual enabled copper
    # faces. The straight-edge splitter below must still prove exact native
    # centreline incidence; this is neither a land expansion nor an arc or
    # cross-layer shortcut. Off-centre/custom lands may not contain their
    # nominal origin, and NPTH declarations are not electrical copper.
    for pad in pad_seeds:
        if (pad.GetClass() != 'PAD' or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
                or pad.GetNetCode() != net_code):
            continue
        point = pad.GetPosition()
        for layer in pad.GetLayerSet().CuStack():
            if (board.IsLayerEnabled(layer) and pad.IsOnLayer(layer)
                    and pad.GetEffectiveShape(layer).Collide(point, 0)):
                add_node(key(point, layer), point)

    # Routed tees often terminate at the exact centreline interior of an
    # existing segment. The endpoint-only graph previously reported these
    # real local links as disconnected and encouraged duplicate stub copper.
    # Split straight-track graph edges at EXISTING native endpoint/via nodes;
    # no land expansion, copper-gap snapping or mid-arc shortcut is inferred.
    # X-sorted node indexes avoid an all-track/all-node quadratic scan.
    from bisect import bisect_left, bisect_right
    by_layer = {}
    for node, point in points.items():
        by_layer.setdefault(node[2], []).append((point.x, node))
    indexes = {}
    for layer, rows in by_layer.items():
        rows.sort()
        indexes[layer] = ([x for x, _ in rows], [node for _, node in rows])
    checks = 0
    for a, b, start, end, length, kind in segments:
        if kind != 'PCB_TRACK' or start == end:
            edge(a, b, length)
            continue
        xs, nodes = indexes[a[2]]
        first = bisect_left(xs, min(start.x, end.x))
        last = bisect_right(xs, max(start.x, end.x))
        dx, dy = end.x-start.x, end.y-start.y
        cuts = []
        for node in nodes[first:last]:
            checks += 1
            if checks > 131072:
                return None  # bounded, conservative unknown; not a no-path proof
            point = points[node]
            if not min(start.y, end.y) <= point.y <= max(start.y, end.y):
                continue
            px, py = point.x-start.x, point.y-start.y
            if px*dy == py*dx:
                cuts.append((px*dx+py*dy, node))
        cuts.sort()
        for (_, left_node), (_, right_node) in zip(cuts, cuts[1:]):
            s, t = points[left_node], points[right_node]
            edge(left_node, right_node, math.hypot(t.x-s.x, t.y-s.y)/MM)

    return graph, points


def _query_explicit_track_path_mm(prepared, left, right, snap):
    """Run the original target-specific search, without changing its graph.

    Keep the original insertion order, 1e-12 relax rule, zero-cost native land
    HitTests, target pop/early-stop and via identity ties. In particular, do
    NOT substitute a minimum of precomputed distances or share results across
    different terminals. The cheap Python adjacency copy protects the prepared
    invocation-local graph even when a query raises or has no real path.
    """
    if (prepared is None or left.GetNetCode() <= 0
            or left.GetNetCode() != right.GetNetCode()):
        return None
    original, points = prepared
    graph = {node: list(neighbors) for node, neighbors in original.items()}

    def edge(a, b, cost):
        graph.setdefault(a, []).append((b, float(cost)))
        graph.setdefault(b, []).append((a, float(cost)))

    source, target = ("pad", "source"), ("pad", "target")
    graph[source], graph[target] = [], []
    for node, point in points.items():
        layer = node[2]
        if left.IsOnLayer(layer) and left.HitTest(point, snap):
            edge(source, node, 0.0)
        if right.IsOnLayer(layer) and right.HitTest(point, snap):
            edge(target, node, 0.0)
    serial = 0
    queue = [(0.0, serial, source)]
    best = {source: 0.0}
    while queue:
        distance, _serial, node = heapq.heappop(queue)
        if distance != best.get(node):
            continue
        if node == target:
            return distance
        for neighbor, cost in graph.get(node, ()):
            candidate = distance + cost
            if candidate + 1e-12 < best.get(neighbor, float("inf")):
                best[neighbor] = candidate
                serial += 1
                heapq.heappush(queue, (candidate, serial, neighbor))
    return None


def _pad_identity(pad):
    """Return JSON-safe endpoint ownership for refusal certificates."""
    ref = None
    try:
        parent = pad.GetParentFootprint()
        ref = parent.GetReference() if parent is not None else None
    except Exception:                                  # noqa: BLE001
        try:
            parent = pad.GetParent()
            ref = parent.GetReference() if parent is not None else None
        except Exception:                              # noqa: BLE001
            pass
    return {"kind": "pad", "ref": ref,
            "pad": str(pad.GetPadName())}


def _existing_supply_column(board, pad, spec, clearance):
    """Re-prove one existing exact pad-centre barrel without another drill.

    Multiple bypass values can share the same assigned supply pin. Native
    identity, through-layer span, dimensions and all-layer collision guards
    must pass; a nearby, wrong-net, duplicate or unqualified barrel is not an
    excuse to broaden the via spot exemption.
    """
    at = pad.GetPosition()
    columns = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA'
               and t.GetPosition() == at]
    if len(columns) != 1:
        return None
    via = columns[0]
    if (via.GetNetCode() != pad.GetNetCode() or pad.GetNetCode() <= 0
            or int(via.GetViaType()) != int(pcbnew.VIATYPE_THROUGH)
            or not any(via.IsOnLayer(layer) for layer in pad.GetLayerSet().CuStack())):
        return None
    diameter, drill = via.GetWidth(pcbnew.F_Cu)/MM, via.GetDrillValue()/MM
    ordinary_diameter, ordinary_drill, limits = _board_legal_through_via_geometry(
        board, float(spec['via_dia']), float(spec['via_drill']))
    qualified_local, _reason = cec_fab_profile.local_pofv_via_decision(board, via)
    if (not qualified_local and (diameter+1e-9 < ordinary_diameter
                                 or drill+1e-9 < ordinary_drill
                                 or diameter+1e-9 < drill+2*limits['board_min_annular_mm'])):
        return None
    if not cec_fr._edge_leg_clear(board, at, at, pcbnew.FromMM(diameter)//2):
        return None
    if not cec_fr._via_spot_clear(
            board, at, pcbnew.FromMM(diameter), clearance, {pad.GetNetCode()},
            drill_nm=pcbnew.FromMM(drill), net_code=pad.GetNetCode(),
            contained_layers=tuple(pad.GetLayerSet().CuStack()),
            existing_via_uuid=via.m_Uuid.AsString()):
        return None
    return dict(uuid=via.m_Uuid.AsString(), diameter_mm=diameter,
                drill_mm=drill, qualified_local_pofv=bool(qualified_local))


def _retained_supply_throat_ops(board, owner_pad, cap_pad, class_width,
                                clearance, common, spec, current_widths, *,
                                deadline_monotonic=None, max_length_nm=None,
                                allow_maze=False, refine_maze=False):
    """Reach a live full-width cross-layer throat without duplicating a via.

    The entire new copper is a bounded manufacturer-supply-pin prefix, not a
    narrow trunk. Every new leg still carries the unchanged whole-net current
    on its actual copper face. The exact existing pad-centre POFV and its
    other-layer full current/class-width continuation are re-proved first.
    There is no current-width exception, even for an aggregate source domain.
    This grants no barrel ampacity or fabrication/release qualification.
    """
    if not current_widths:
        return None, None
    authority = current_widths.get('current_authority') or {}
    amps = authority.get('amps')
    if (isinstance(amps, bool) or not isinstance(amps, (int, float))
            or not math.isfinite(amps) or amps <= 0):
        return None, None
    net = str(owner_pad.GetNetname())
    if owner_pad.GetNetCode() <= 0 or net != str(cap_pad.GetNetname()):
        return None, None
    tracks = list(board.GetTracks())
    enabled = set(board.GetEnabledLayers().CuStack())
    plane_layers = {board.GetLayerID(name) for name in cec_fr.plane_layers(board)}
    for launch, landing in ((owner_pad, cap_pad), (cap_pad, owner_pad)):
        if launch.GetParentFootprint().IsDNP() or landing.GetParentFootprint().IsDNP():
            continue
        contract = cec_device_power_roles.footprint_contract(launch.GetParentFootprint())
        if (not contract or contract['pins'].get(str(launch.GetNumber()))
                not in ('power_input', 'power_output')
                or launch.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or launch.HasHole()):
            continue
        column = _existing_supply_column(board, landing, spec, clearance)
        if not column or not column['qualified_local_pofv']:
            continue
        via = next(t for t in tracks if t.m_Uuid.AsString() == column['uuid'])
        for layer in common:
            if cec_search_budget.exhausted(deadline_monotonic):
                return None, None
            required = max(class_width, current_widths['required_by_layer_nm'][int(layer)])
            if not cec_fr._profiled_pofv_full_width_throat(
                    board, via, layer, required, tracks):
                continue
            # The existing classifier proves a layer-transition throat. Also
            # rederive the current floor on that actual outgoing copper face,
            # rather than applying a thick outer-layer floor to an inner one.
            throats = [t for t in tracks if t.GetClass() == 'PCB_TRACK'
                and t.GetNetCode() == launch.GetNetCode() and t.GetLayer() != layer
                and t.GetLayer() in enabled - plane_layers and via.IsOnLayer(t.GetLayer())
                and t.GetWidth() >= max(class_width,
                    current_widths['required_by_layer_nm'][int(t.GetLayer())])
                and via.GetPosition() in (t.GetStart(), t.GetEnd())]
            if not throats:
                continue
            escape = cec_fr._pad_local_escape(launch, required, clearance,
                int(board.GetDesignSettings().m_TrackMinWidth))
            if not escape:
                continue
            local_width, budget = escape
            local_width = max(local_width,
                current_widths['required_by_layer_nm'][int(layer)])
            if local_width >= min(launch.GetSize().x, launch.GetSize().y):
                continue
            budget = min(budget, 1500000,
                max_length_nm if max_length_nm is not None else 1500000)
            if math.dist(tuple(launch.GetPosition()), tuple(via.GetPosition())) > budget:
                continue
            # Cheap canonical paths go first; fallback receives the SAME finite
            # work/wall lease. A refused five-fragment prefix must not displace
            # a later candidate satisfying the existing four-fragment bound.
            legs = cec_fr._guarded_profiled_lastmile_legs(
                board, launch.GetPosition(), via.GetPosition(), local_width, layer,
                clearance, launch.GetNetCode(),
                lambda a, b, half: cec_fr._edge_leg_clear(board, a, b, half),
                allow_maze=allow_maze, deadline_monotonic=deadline_monotonic,
                max_length_nm=budget, refine_maze=refine_maze,
                endpoint_detail_grid_mm=.1 if refine_maze else None,
                path_validator=lambda path: len(path) <= 4,
                compact_phase_jogs=True)
            if not legs or len(legs) > 4:
                continue
            ops = [('trk', a, b, w, layer) for a, b, w in legs]
            return ops, dict(launch_pad_uuid=launch.m_Uuid.AsString(),
                landing_pad_uuid=landing.m_Uuid.AsString(),
                retained_via_uuid=column['uuid'], live_pofv_local_geometry=True,
                retained_full_width_track_uuids=sorted(t.m_Uuid.AsString() for t in throats),
                prefix_width_nm=local_width, required_surface_width_nm=required,
                max_prefix_nm=budget, layer=board.GetLayerName(layer),
                barrel_capacity_qualified=False, release_authority=False)
    return None, None


def _pofv_supply_bridge_ops(board, owner_pad, cap_pad, width, clearance,
                            net_code, bridge_layers, spec, *, ops_ok=None,
                            deadline_monotonic=None, pofv_geometry=None,
                            max_length_nm=None, allow_maze=True):
    """Bridge an assigned supply cell through two qualified POFV pad seats.

    This is the low-inductance fallback for adjacent fine-pitch power pins
    whose package row cannot fit another face-layer via dogbone.  It is
    available only when the declared fabrication profile explicitly supports
    plated-over filled vias.  Board minima, process dimensions, pad-local
    containment, hole spacing, edge clearance, and the inner route are all
    proven before any copper is returned to the caller.
    A complete-candidate predicate is applied inside the search: a connected
    but over-budget path must not hide a later qualified layer/seat pair.
    """
    max_length_nm = cec_fr._checked_route_length_nm(max_length_nm)
    profile_name = cec_fab_profile.active_profile_name(board)
    profile = (cec_fab_profile.get_profile(profile_name)
               if profile_name else None)
    preferred = pofv_geometry or cec_fab_profile.preferred_pofv_geometry(profile)
    if not preferred or not bridge_layers:
        return None, None
    # A filled/capped via wholly contained by the assigned endpoint pad is an
    # endpoint-limited local interconnect, not a trunk-layer transition.  Use
    # the declared POFV geometry clamped to board minima (the same exception
    # already enforced for immediate decoupler GND returns).  The independent
    # conformance gate exempts it only after proving exact same-net pad
    # containment; an ordinary off-pad via still owes the full netclass size.
    requested_diameter = float(preferred[0])
    requested_drill = float(preferred[1])
    _ordinary_diameter, _ordinary_drill, board_limits = \
        _board_legal_through_via_geometry(
            board, requested_diameter, requested_drill)
    # Do not clamp a profile-qualified POFV to the ordinary through-via land
    # rule: that would make it larger than the fine-pitch pad it must be fully
    # contained by.  The release gates already model this exact exception and
    # suppress ordinary diameter/annular findings only after proving profile,
    # dimensions, and same-net full-land containment.  Every non-contained or
    # off-pad via remains subject to the normal board/netclass minima.
    diameter, drill = requested_diameter, requested_drill
    process_ok, _process_reason = cec_fab_profile.pofv_dimensions(
        profile, diameter, drill)
    if not process_ok:
        return None, None
    positions = [owner_pad.GetPosition(), cap_pad.GetPosition()]
    pads = [owner_pad, cap_pad]
    pofv_allowed = []
    for pad, position in zip(pads, positions):
        contained = set(pad.GetLayerSet().CuStack())
        pofv_allowed.append(bool(
            cec_fr._edge_leg_clear(
                board, position, position,
                pcbnew.FromMM(diameter) // 2)
            and _hole_to_hole_clear(board, position, drill)[0]
            and cec_fr._via_spot_clear(
                board, position, pcbnew.FromMM(diameter), clearance,
                {net_code}, drill_nm=pcbnew.FromMM(drill),
                net_code=net_code, contained_layers=contained)))
    try:
        minimum_hole = board.GetDesignSettings().m_HoleToHoleMin / MM
    except Exception:                                   # noqa: BLE001
        minimum_hole = 0.25
    ordinary_diameter, ordinary_drill, _ordinary_limits = \
        _board_legal_through_via_geometry(
            board, float(spec["via_dia"]), float(spec["via_drill"]))
    # A new ordinary off-pad transition owes the complete source/class copper
    # web, not just the preferred netclass via diameter. Existing columns are
    # immutable debt and pad-contained POFV keeps its separate live process
    # proof; neither grants current/barrel qualification here.
    ordinary_diameter = max(ordinary_diameter, ordinary_drill + width / MM)
    reused_columns = {}

    def endpoint_escape(pad):
        try:
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                # noqa: BLE001
            return None
        try:
            board_min = board.GetDesignSettings().m_TrackMinWidth
        except Exception:                                # noqa: BLE001
            board_min = pcbnew.FromMM(0.20)
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= width:
            return None
        local_width = min(width, max(int(board_min), minor // 2))
        budget = pcbnew.FromMM(max(0.6, min(1.5, 1.5 * width / MM)))
        return local_width, budget

    def endpoint_seats(index):
        """Return one low-inductance endpoint seat with an explicit via mode.

        A narrow IC land may be unable to contain the selected POFV even when
        its assigned capacitor land can.  Requiring the same via style at both
        ends unnecessarily refuses an otherwise ordinary professional escape.
        Prefer an in-pad POFV whenever it is qualified; otherwise use the same
        bounded, guarded dogbone sweep as the generic bridge engine, with an
        ordinary board-legal through via off the pad.
        """
        pad, position = pads[index], positions[index]
        # A native plated through-hole land already spans the copper stack.
        # Do not add an adjacent drilled dogbone merely because this endpoint
        # is not a separate PCB_VIA. This is geometric contact reuse only:
        # the existing connector barrel gains no ampacity/release credit.
        # Require the actual plated attribute, a real drill and every enabled
        # copper face; an NPTH, surface land or partial-layer pad is not a
        # transition witness.
        enabled = tuple(board.GetEnabledLayers().CuStack())
        hole = pad.GetDrillSize()
        if (int(pad.GetAttribute()) == int(pcbnew.PAD_ATTRIB_PTH)
                and hole.x > 0 and hole.y > 0 and pad.GetNetCode() == net_code
                and enabled and all(pad.IsOnLayer(layer) for layer in enabled)):
            return [((position.x, position.y), [], 'existing-plated-pad')]
        existing = _existing_supply_column(board, pad, spec, clearance)
        if existing is not None:
            reused_columns[index] = existing
            # Existing copper belongs to the preceding cell/source, not to
            # this transaction. No new via op, UUID or hole is created.
            return [((position.x, position.y), [], 'existing-via')]
        if pofv_allowed[index]:
            return [((position.x, position.y), [
                ("via", position, drill, diameter)], "pofv")]
        layers = sorted(set(pad.GetLayerSet().CuStack()))
        if not layers:
            return []
        layer = layers[0]
        escape = endpoint_escape(pad)
        rows = []
        for off in (0.55, 0.8, 1.2, 1.6, 2.0, 2.5):
            for angle in (0, 90, 180, 270, 45, 135, 225, 315):
                if cec_search_budget.exhausted(deadline_monotonic):
                    return rows
                radians = math.radians(angle)
                seat = pcbnew.VECTOR2I(
                    int(position.x + math.cos(radians) * pcbnew.FromMM(off)),
                    int(position.y + math.sin(radians) * pcbnew.FromMM(off)))
                other = positions[1-index]
                remaining_stub = (None if max_length_nm is None else
                    max_length_nm-math.hypot(other.x-seat.x, other.y-seat.y))
                if (remaining_stub is not None and (remaining_stub < 0 or math.hypot(
                        seat.x-position.x, seat.y-position.y) > remaining_stub + 1e-3)):
                    continue
                if not cec_fr._edge_leg_clear(
                        board, seat, seat,
                        pcbnew.FromMM(ordinary_diameter) // 2):
                    continue
                if not _hole_to_hole_clear(
                        board, seat, ordinary_drill)[0]:
                    continue
                legs = cec_fr._guarded_profiled_lastmile_legs(
                    board, position, seat, width, layer, clearance, net_code,
                    lambda a, b, half: cec_fr._edge_leg_clear(
                        board, a, b, half),
                    start_escape=escape, allow_maze=False,
                    deadline_monotonic=deadline_monotonic,
                    max_length_nm=remaining_stub)
                if not legs:
                    continue
                if not cec_fr._via_spot_clear(
                        board, seat, pcbnew.FromMM(ordinary_diameter),
                        clearance, {net_code},
                        drill_nm=pcbnew.FromMM(ordinary_drill),
                        net_code=net_code):
                    continue
                ops = [("trk", a, b, leg_width, layer)
                       for a, b, leg_width in legs]
                ops.append(("via", seat, ordinary_drill,
                            ordinary_diameter))
                rows.append(((seat.x, seat.y), ops, "dogbone"))
                # Preserve a deterministic but useful directional choice set.
                # The complete bridge ranking below selects on total copper.
                if len(rows) >= 16:
                    return rows
        return rows

    seats_a = endpoint_seats(0)
    seats_b = endpoint_seats(1)
    if not seats_a or not seats_b:
        return None, None
    pair_rows = cec_fr._ranked_bridge_seat_pairs(
        [(point, ops) for point, ops, _mode in seats_a],
        [(point, ops) for point, ops, _mode in seats_b],
        pcbnew.FromMM(minimum_hole + ordinary_drill))
    modes = {
        (point[0], point[1], tuple(
            (op[0], op[1].x, op[1].y) for op in ops if op[0] == "via")):
        mode for point, ops, mode in seats_a + seats_b}
    for layer in bridge_layers:
        for (left, left_ops), (right, right_ops) in pair_rows:
            if cec_search_budget.exhausted(deadline_monotonic):
                return None, None
            start = pcbnew.VECTOR2I(int(left[0]), int(left[1]))
            end = pcbnew.VECTOR2I(int(right[0]), int(right[1]))
            remaining_middle = (None if max_length_nm is None else
                max_length_nm-cec_fr._planar_ops_length_nm(left_ops+right_ops))
            if (remaining_middle is not None and (remaining_middle < 0 or math.hypot(
                    end.x-start.x, end.y-start.y) > remaining_middle + 1e-3)):
                continue
            legs = cec_fr._guarded_profiled_lastmile_legs(
                board, start, end, width, layer, clearance, net_code,
                lambda a, b, half: cec_fr._edge_leg_clear(
                    board, a, b, half),
                allow_maze=allow_maze, maze_margin_mm=2.0,
                deadline_monotonic=deadline_monotonic,
                max_length_nm=remaining_middle)
            if not legs:
                continue
            ops = list(left_ops)
            ops.extend(("trk", a, b, leg_width, layer)
                       for a, b, leg_width in legs)
            ops.extend(right_ops)
            if ops_ok is not None and not ops_ok(ops):
                continue
            def seat_mode(point, endpoint_ops):
                key = (point[0], point[1], tuple(
                    (op[0], op[1].x, op[1].y)
                    for op in endpoint_ops if op[0] == "via"))
                return modes.get(key, "unknown")
            endpoint_modes = [seat_mode(left, left_ops),
                              seat_mode(right, right_ops)]
            via_rows = [op for op in ops if op[0] == "via"]
            via_diameters = [op[3] for op in via_rows] + [
                row['diameter_mm'] for row in reused_columns.values()]
            via_drills = [op[2] for op in via_rows] + [
                row['drill_mm'] for row in reused_columns.values()]
            return ops, {
            "fab_profile": profile_name,
            "diameter_mm": round(max(via_diameters, default=0.), 3),
            "drill_mm": round(max(via_drills, default=0.), 3),
            "reused_endpoint_via_uuids": sorted(row['uuid'] for row in reused_columns.values()),
            "requested_diameter_mm": round(requested_diameter, 3),
            "requested_drill_mm": round(requested_drill, 3),
            "netclass_via_diameter_mm": round(
                float(spec.get("via_dia") or 0.0), 3),
            "netclass_via_drill_mm": round(
                float(spec.get("via_drill") or 0.0), 3),
            "endpoint_modes": endpoint_modes,
            "endpoint_limited_local_via": "pofv" in endpoint_modes,
            "qualified_process_exception": bool(
                "pofv" in endpoint_modes and (
                    diameter + 1e-9 < _ordinary_diameter
                    or drill + 1e-9 < _ordinary_drill)),
            "board_limits": board_limits,
        }
    return None, None


def _local_supply_limit_mm(direct_mm, class_width_mm=0.25,
                           clearance_mm=0.20):
    """Maximum local bypass path including one obstacle-escape throat.

    A ratio-only bound is too tight when a fine-pitch pad is already close to
    its capacitor: the guarded path may need to go around one adjacent land by
    one full netclass width plus clearance.  The additive term stays bounded,
    so a remote dogleg cannot become acceptable merely because its endpoints
    are farther apart.
    """
    direct_mm = float(direct_mm)
    quantization_mm = 0.05
    # A canonical dogbone plus 45-degree inner-layer bridge can add just over
    # 35% when the only legal via seat is on the far side of a narrow package
    # pin.  Forty percent is still a strict local bound, but admits that real
    # geometry instead of failing on grid-scale differences (the U11 case was
    # 4.559 mm against 4.448 mm at the old ratio).
    return max(direct_mm + 0.35,
               direct_mm * 1.40 + quantization_mm,
               direct_mm + float(class_width_mm) + float(clearance_mm)
               + quantization_mm)


def _whole_current_endpoint_escapes(board, endpoint_pads, *, net_code, layer,
        class_width_nm, clearance_nm, current_widths):
    """Existing bounded native pad budgets, clamped to the ENTIRE rail load.

    None denotes a retained full-width native port, never a fictitious pad.
    Typed endpoint authority and exact saved receiving belong to the caller.
    """
    if len(endpoint_pads)!=2 or not current_widths or layer not in current_widths['required_by_layer_nm']:
        raise ValueError('whole_current_native_endpoint_context_required')
    authority=current_widths.get('current_authority') or {}
    if (any(type(authority.get(k)) not in (int,float) or not math.isfinite(authority[k])
            or authority[k]<=0 for k in ('amps','geometry_margin'))
            or type(authority.get('margin_included')) is not bool):
        raise ValueError('whole_current_positive_unchanged_source_authority_required')
    minimum=max(board.GetDesignSettings().m_TrackMinWidth,
        current_widths['required_by_layer_nm'][layer])
    result=[]
    for pad in endpoint_pads:
        if pad is None:
            result.append(None);continue
        if pad.GetNetCode()!=net_code or not pad.IsOnLayer(layer):
            raise ValueError('whole_current_exact_same_net_surface_pad_required')
        raw=cec_fr._pad_local_escape(pad,class_width_nm,clearance_nm,
            board.GetDesignSettings().m_TrackMinWidth)
        result.append((max(minimum,raw[0]),raw[1]) if raw and minimum<class_width_nm else None)
    return tuple(result)


def _canonical_whole_rail_surface(board, start, end, common, *, net_code,
        class_width_nm, clearance_nm, current_widths, deadline_monotonic,
        max_length_nm, foreign_cache, endpoint_pads=None):
    """Cheap read-only full-width surface candidates before column search.

    This is not an endpoint neckdown or a current allocation. Every leg uses
    the actual face's unchanged current/class floor and native copper/edge
    guards. Exhaustion remains unproved; no material is added here.
    """
    if not current_widths or net_code <= 0:
        return None
    floors = current_widths['required_by_layer_nm']
    for layer in common:
        if int(layer) not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        width = max(class_width_nm, floors[int(layer)],int(board.GetDesignSettings().m_TrackMinWidth))
        for points in cec_fr._canonical_45_xy_paths(tuple(start), tuple(end)):
            if cec_search_budget.exhausted(deadline_monotonic):
                return None
            if sum(math.dist(a, b) for a, b in zip(points, points[1:])) > max_length_nm:
                continue
            vectors = [pcbnew.VECTOR2I(*v) for v in points]
            menus = [[(a, b, width) for a, b in zip(vectors, vectors[1:])]]
            if endpoint_pads is not None:
                # Reuse the existing bounded native endpoint policy only for
                # the class preference. Whole-rail current remains on EVERY
                # emitted section; these are not lower-current consumer leaves.
                escapes = _whole_current_endpoint_escapes(board,endpoint_pads,
                    net_code=net_code,layer=int(layer),class_width_nm=width,
                    clearance_nm=clearance_nm,current_widths=current_widths)
                if any(escapes):
                    menus.append(cec_fr._profiled_lastmile_path(vectors, width, *escapes))
            for legs in menus:
                if (legs and all(w>=max(floors[int(layer)],int(board.GetDesignSettings().m_TrackMinWidth)) and
                        cec_fr._edge_leg_clear(board, a, b,
                            math.ceil(w / 2) + clearance_nm)
                        and cec_fr._tap_foreign_clear(board, a, b, w, layer,
                            clearance_nm, {net_code}, foreign_cache=foreign_cache)
                        for a, b, w in legs)):
                    return legs, int(layer), width
    return None


def _add_supply_link(board, owner_pad, cap_pad, *, lock, diagnostics=None,
                     group_neckdowns=True, link_role="supply",
                     search_timeout_s=10.0, search_work_limit=None,
                     pofv_geometry=None, refine_maze=False, rail_completion=False):
    """Use the same bounded work across placement probes and construction.

    A sub-second CPU race used to change the physical admission key under
    contention. Work is now bounded by candidate/maze expansion checkpoints;
    the larger wall guard only cancels an unhealthy operation. Neither limit
    proves a path impossible. All existing native copper checks still apply.
    """
    if (type(rail_completion) is not bool
            or rail_completion and (link_role != 'supply'
                or type(search_timeout_s) not in (int, float)
                or not math.isfinite(search_timeout_s)
                or not 0 < search_timeout_s <= 10.)):
        raise ValueError('explicit_supply_rail_completion_context_required')
    if type(refine_maze) is not bool or (refine_maze and (
            type(search_timeout_s) not in (int, float)
            or not math.isfinite(search_timeout_s)
            or not 0 < search_timeout_s <= 10.)):
        raise ValueError('bounded_explicit_supply_maze_refinement_required')
    if search_work_limit is None:
        # Whole-rail completion walks retained island ports and all-layer
        # via channels, unlike a local owner/cap feasibility probe. A small
        # local-cell allowance exhausted before those channels were visited.
        # Fund that explicit construction role without changing geometry,
        # current authority, the <=10 s wall guard, or an enclosing budget.
        search_work_limit = (DEFAULT_RAIL_COMPLETION_WORK_LIMIT if rail_completion
            else DEFAULT_LOCAL_CELL_WORK_LIMIT)
    deadline = (None if search_timeout_s is None else
                time.monotonic() + max(.01, float(search_timeout_s)))
    tiers = []
    shared_stop = None
    with cec_search_budget.scoped(search_work_limit) as budget:
        for allow_maze in ((True,) if link_role == 'shared-ground-entry' else (False, True)):
            detail = {}
            before_work = budget.used
            remaining = budget.limit - budget.used
            # Native via/channel enumeration can consume the entire lease
            # before the maze ever runs. Reserve half of the remaining work
            # for fallback, without resetting the shared outer budget or its
            # wall deadline. Unused cheap-search work stays available later.
            tier_limit = max(1, remaining if allow_maze else remaining // 2)
            with cec_search_budget.scoped(tier_limit) as tier_budget:
                result, error = _add_supply_link_impl(
                    board, owner_pad, cap_pad, lock=lock, diagnostics=detail,
                    group_neckdowns=group_neckdowns, link_role=link_role,
                    search_timeout_s=search_timeout_s, pofv_geometry=pofv_geometry,
                    allow_maze=allow_maze, deadline_monotonic=deadline,
                    refine_maze=refine_maze, rail_completion=rail_completion)
                cec_search_budget.stop_status()
            tiers.append(dict(tier='maze' if allow_maze else 'native-channels',
                              ok=result is not None, error=error,
                              work_used=budget.used-before_work,
                              tier_work=tier_budget.report()))
            if diagnostics is not None:
                diagnostics.update(detail)
            shared_stop = cec_search_budget.stop_status()
            # Sample each cheap guarded layer/via topology before expensive
            # queue expansion. All tiers share ONE work/wall lease; exhausting
            # an earlier search never masquerades as geometric impossibility.
            if result is not None or shared_stop is not None:
                break
            if (tier_budget.stop_reason != 'work_limit'
                    and error not in ('no guarded local supply path within locality bound',
                                      'no guarded local shared-ground path')):
                break
    if result is not None:
        result['search_work'] = budget.report()
        result['search_tiers'] = tiers
    if diagnostics is not None:
        diagnostics.setdefault('search', {}).update(budget.report())
        diagnostics['search']['tiers'] = tiers
        if shared_stop is not None:
            diagnostics['search']['shared_stop'] = shared_stop
        if error is not None and shared_stop is not None:
            diagnostics['conclusion'] = 'search_budget_exhausted'
    if error is not None and shared_stop is not None:
        error = 'local supply search budget exhausted without a path'
    return result, error


def _add_supply_link_impl(board, owner_pad, cap_pad, *, lock, diagnostics=None,
                          group_neckdowns=True, link_role="supply",
                          search_timeout_s=10.0, pofv_geometry=None,
                          allow_maze=True, deadline_monotonic=None,refine_maze=False,
                          rail_completion=False):
    # Reuse exact foreign-copper shapes throughout this one link search.
    # Candidate via seats and maze legs see an immutable board until a winner
    # is accepted, so rebuilding every pad/track shape for every seat is pure
    # quadratic work.  Keep the cache local: an accepted link mutates the
    # board before the next bypass cell is evaluated.
    foreign_cache = {}
    search_started = time.monotonic()
    search_deadline = (
        None if search_timeout_s is None
        else search_started + max(0.01, float(search_timeout_s)))
    if deadline_monotonic is not None:
        search_deadline = (deadline_monotonic if search_deadline is None else
                           min(search_deadline, deadline_monotonic))
    net = owner_pad.GetNetname()
    if net != cap_pad.GetNetname():
        if diagnostics is not None:
            diagnostics.update({
                "schema": 1, "conclusion": "owner_cap_rail_mismatch",
                "owner": _pad_identity(owner_pad),
                "cap": _pad_identity(cap_pad)})
        return None, "owner/cap rail mismatch"
    direct = math.hypot(
        owner_pad.GetPosition().x - cap_pad.GetPosition().x,
        owner_pad.GetPosition().y - cap_pad.GetPosition().y) / MM
    path_before = _shortest_track_path_mm(board, owner_pad, cap_pad)
    common = sorted(
        set(owner_pad.GetLayerSet().CuStack()) &
        set(cap_pad.GetLayerSet().CuStack()) &
        set(board.GetEnabledLayers().CuStack()))
    if not common:
        if diagnostics is not None:
            diagnostics.update({
                "schema": 1, "conclusion": "no_common_copper_layer",
                "owner": _pad_identity(owner_pad),
                "cap": _pad_identity(cap_pad)})
        return None, "owner/cap have no common copper layer"
    spec = _netclass(board, net)
    try:
        board_min = board.GetDesignSettings().m_TrackMinWidth
    except Exception:                                    # noqa: BLE001
        board_min = pcbnew.FromMM(0.20)
    # The electrical class owns the body of the link.  A previous version used
    # half the smaller endpoint land as the width of the *entire* route.  That
    # made a fine-pitch bypass connection turn a multi-amp rail into a long,
    # locked bottleneck.  Keep only a bounded endpoint escape narrow and
    # require a class-width throat between the lands, matching final signoff.
    class_width = max(int(board_min), int(spec["width"]))
    width = class_width
    current_widths=(_supply_current_widths(board,net) if link_role=='supply' else None)
    if rail_completion and current_widths is None:
        return None, 'whole-rail completion requires unchanged source current authority'
    if current_widths is not None:
        width=max(width,max(current_widths['required_by_layer_nm'][int(lay)] for lay in common))
        if diagnostics is not None:diagnostics['existing_supply_current_width_contract']=current_widths
    clearance = max(pcbnew.FromMM(0.20), int(spec["clearance"]))
    local_limit = _local_supply_limit_mm(
        direct, width / MM, clearance / MM)
    if path_before is not None and path_before <= local_limit + 1e-9:
        return {
            "status": "covered-local", "items": [],
            "length_mm": round(path_before, 3),
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    def escape(pad):
        # Use the same land-major/clearance-aware escape geometry as routing
        # and independent neckdown receiving. A copied width-only budget
        # forced a flare inside elongated package lands, even though the
        # shared bounded classifier permits the actual land exit.
        # A whole-rail join has no per-consumer neckdown allowance. Its
        # generic fallback must carry the complete source/class width all the
        # way to the land; geometric endpoint qualification is not a current
        # exception. Positively typed full-current/class-only prefixes remain
        # owned by the separate retained-throat constructor above.
        return (None if rail_completion else
                cec_fr._pad_local_escape(pad,width,clearance,int(board_min)))

    start_escape = escape(owner_pad)
    end_escape = escape(cap_pad)
    locality_rejections = []

    def _legs_length_mm(legs):
        return sum(math.hypot(b.x - a.x, b.y - a.y) / MM
                   for a, b, _leg_width in legs)

    def _ops_length_mm(ops):
        return sum(math.hypot(op[2].x - op[1].x,
                              op[2].y - op[1].y) / MM
                   for op in (ops or ()) if op[0] != "via")

    def _within_locality(kind, candidate_length):
        if candidate_length <= local_limit + 1e-9:
            return True
        locality_rejections.append({
            "kind": kind,
            "length_mm": round(candidate_length, 3),
            "max_local_mm": round(local_limit, 3),
        })
        return False

    net_code = owner_pad.GetNetCode()
    start, end = owner_pad.GetPosition(), cap_pad.GetPosition()
    if rail_completion:
        # Existing-column walks must not consume the entire short lease
        # before even testing a direct full-width outer-face connection.
        # Use the same scoped work/deadline and receive every added leg via
        # the established constructor. Local bypass/ground policy is unchanged.
        cheap = _canonical_whole_rail_surface(board, start, end, common,
            net_code=net_code, class_width_nm=class_width,
            clearance_nm=clearance, current_widths=current_widths,
            deadline_monotonic=search_deadline, max_length_nm=local_limit * MM,
            foreign_cache=foreign_cache, endpoint_pads=(owner_pad, cap_pad))
        if diagnostics is not None:
            diagnostics['whole_rail_surface_precheck'] = dict(
                tested_before_retained_columns=True, found=cheap is not None,
                source_current_or_clearance_changed=False, new_vias=0,
                bounded_class_only_launches_never_below_full_current=True)
        if cheap:
            legs, layer, full_width = cheap
            items = []
            for a, b, leg_width in legs:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(a); track.SetEnd(b); track.SetWidth(leg_width)
                track.SetLayer(layer); track.SetNetCode(net_code)
                track.SetLocked(bool(lock)); board.Add(track); items.append(track)
            admitted, neckdown = _admit_link_neckdowns(board, items,
                full_width, persist_group=group_neckdowns)
            if admitted:
                return dict(status='linked-full-current-surface', layer=layer,
                    width_mm=full_width / MM, items=items, vias=0,
                    all_sections_at_unchanged_whole_current_floor=True,
                    length_mm=round(_legs_length_mm(legs), 6),
                    direct_mm=round(direct, 3), max_local_mm=round(local_limit, 3),
                    endpoint_neckdown=neckdown, route_context='rail-island'), None
            # The established receiver already discards refused items.
            # Do not delete their native/SWIG objects a second time.
            locality_rejections.append(dict(kind='full-current-surface', **neckdown))
    if rail_completion and not cec_search_budget.exhausted(search_deadline):
        # A real opposite-face source trunk may lie beside this isolated
        # capacitor. Try a bounded native full-current column before walking
        # every retained portal. No local bypass or current-rating credit.
        import cec_native_bus_column as native_column
        remaining=2. if search_deadline is None else min(2.,search_deadline-time.monotonic())
        hint=os.environ.get('CEC_THERMAL_BOARD_HINT') or str(board.GetFileName() or '')
        if remaining>0 and board.GetFileName() and hint:
            column=native_column.construct(board,owner_pad,cap_pad,
                source=board.GetFileName(),board_hint=hint,timeout_s=remaining)
            if diagnostics is not None:
                diagnostics['native_source_bus_column_precheck']=dict(found=column is not None,
                    source_current_or_class_changed=False,local_bypass_loop_qualified=False)
            if column is not None:return column,None
    if link_role == 'supply' and current_widths is not None:
        ops, throat = _retained_supply_throat_ops(board, owner_pad, cap_pad,
            class_width, clearance, common, spec, current_widths,
            deadline_monotonic=search_deadline, max_length_nm=local_limit * MM,
            allow_maze=allow_maze, refine_maze=refine_maze)
        if ops:
            items = []
            for _kind, a, b, leg_width, layer in ops:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(a); track.SetEnd(b)
                track.SetWidth(leg_width); track.SetLayer(layer)
                track.SetNetCode(net_code); track.SetLocked(bool(lock))
                board.Add(track); items.append(track)
            admitted, endpoint_neckdown = _admit_link_neckdowns(board, items,
                throat['required_surface_width_nm'], persist_group=group_neckdowns)
            if admitted:
                return dict(status='linked-retained-plated-throat', layer=throat['layer'],
                    width_mm=throat['required_surface_width_nm']/MM,
                    neckdown_widths_mm=sorted({t.GetWidth()/MM for t in items}),
                    length_mm=round(_ops_length_mm(ops), 6), endpoint_neckdown=endpoint_neckdown,
                    retained_plated_throat=throat, items=items, direct_mm=round(direct, 3),
                    max_local_mm=round(local_limit, 3)), None
            locality_rejections.append(dict(kind='retained-plated-throat', **endpoint_neckdown))
    # The best source-native supply access is not always at the SMD pad
    # centre. An existing nearby plated transition can expose another face
    # without another via, redundant dogbone or a narrowed power body. This
    # search re-proves its source-current contact graph and uses the SAME
    # finite work/wall lease as the face and fresh-transition alternatives.
    if link_role == 'supply' and current_widths is not None:
        import cec_retained_supply_port as retained_ports
        if rail_completion:
            ops, ports = retained_ports.plan_rail(board, owner_pad, cap_pad,
                width_nm=class_width, clearance_nm=clearance,
                current_widths=current_widths, spec=spec,
                deadline_monotonic=search_deadline, allow_maze=allow_maze)
        else:
            ops, ports = retained_ports.plan(board, owner_pad, cap_pad,
                width_nm=class_width, clearance_nm=clearance,
                current_widths=current_widths, spec=spec,
                deadline_monotonic=search_deadline, max_length_nm=local_limit * MM,
                allow_maze=allow_maze)
        if ops and (rail_completion or _within_locality(
                'retained-plated-ports', _ops_length_mm(ops))):
            items = []
            for _kind, a, b, leg_width, layer in ops:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(a); track.SetEnd(b); track.SetWidth(leg_width)
                track.SetLayer(layer); track.SetNetCode(net_code)
                track.SetLocked(bool(lock)); board.Add(track); items.append(track)
            admitted, endpoint_neckdown = _admit_link_neckdowns(
                board, items, class_width, persist_group=group_neckdowns)
            if admitted:
                return dict(status='linked-retained-plated-ports',
                    layer=ports['layer'], width_mm=ports['width_nm'] / MM,
                    length_mm=round(_ops_length_mm(ops), 6), vias=0,
                    retained_source_ports=ports, endpoint_neckdown=endpoint_neckdown,
                    direct_mm=round(direct, 3), max_local_mm=round(local_limit, 3),
                    route_context='rail-island' if rail_completion else 'local-bypass',
                    items=items), None

    for layer in common:
        # A PTH mask can reach multiple enabled copper thicknesses. The
        # planar proposal must carry the full current on THIS layer, not
        # inherit the thinnest inner-layer width on thick outer copper. Keep
        # the conservative all-common-layer width for mixed-layer fallbacks.
        layer_width = max(class_width, current_widths['required_by_layer_nm'][int(layer)]) \
            if current_widths is not None else width
        layer_start_escape = (None if rail_completion else
            cec_fr._pad_local_escape(owner_pad, layer_width, clearance, int(board_min)))
        layer_end_escape = (None if rail_completion else
            cec_fr._pad_local_escape(cap_pad, layer_width, clearance, int(board_min)))
        path = cec_fr._guarded_profiled_lastmile_legs(
            board, start, end, layer_width, layer, clearance, net_code,
            lambda a, b, half: cec_fr._edge_leg_clear(
                board, a, b, half),
            start_escape=layer_start_escape,
            end_escape=layer_end_escape,
            foreign_cache=foreign_cache,
            allow_maze=allow_maze,
            deadline_monotonic=search_deadline,
            max_length_nm=local_limit*MM,
            minimize_escape=current_widths is not None,refine_maze=refine_maze,
            path_validator=(lambda legs: all(leg_width >= layer_width
                for _a, _b, leg_width in legs)) if rail_completion else None)
        if not path:
            continue
        path_length = _legs_length_mm(path)
        if not _within_locality("same-layer", path_length):
            continue
        items = []
        for a, b, leg_width in path:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(a); track.SetEnd(b)
            track.SetWidth(leg_width); track.SetLayer(layer)
            track.SetNetCode(net_code); track.SetLocked(bool(lock))
            board.Add(track); items.append(track)
        admitted, endpoint_neckdown = _admit_link_neckdowns(
            board, items, layer_width, persist_group=group_neckdowns)
        if not admitted:
            locality_rejections.append({"kind": "same-layer-neckdown",
                                        **endpoint_neckdown})
            continue
        return {
            "status": "linked", "layer": board.GetLayerName(layer),
            "width_mm": round(layer_width / MM, 3),
            "neckdown_widths_mm": sorted({
                round(item.GetWidth() / MM, 3) for item in items
                if item.GetWidth() < layer_width}),
            "length_mm": round(path_length, 3),
            "endpoint_neckdown": endpoint_neckdown,
            "items": items,
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    def _shared_ground_neckdown():
        """Try the explicitly bounded fine-pitch GND bridge in place."""
        if link_role != "shared-ground-entry":
            return None
        endpoint_minor = min(
            owner_pad.GetSize().x, owner_pad.GetSize().y,
            cap_pad.GetSize().x, cap_pad.GetSize().y)
        local_width = min(width, max(int(board_min), int(endpoint_minor)))
        if local_width >= width:
            return None
        for layer in common:
            path = cec_fr._guarded_profiled_lastmile_legs(
                board, start, end, local_width, layer, clearance,
                net_code,
                lambda a, b, half: cec_fr._edge_leg_clear(
                    board, a, b, half),
                foreign_cache=foreign_cache,
                allow_maze=allow_maze,
                deadline_monotonic=search_deadline,
                max_length_nm=local_limit*MM)
            if not path:
                continue
            path_length = _legs_length_mm(path)
            if not _within_locality(
                    "shared-ground-neckdown", path_length):
                continue
            items = []
            for a, b, leg_width in path:
                item = pcbnew.PCB_TRACK(board)
                item.SetStart(a); item.SetEnd(b)
                item.SetWidth(leg_width); item.SetLayer(layer)
                item.SetNetCode(net_code); item.SetLocked(bool(lock))
                board.Add(item); items.append(item)
            admitted, endpoint_neckdown = _admit_link_neckdowns(
                board, items, width, persist_group=group_neckdowns)
            if not admitted:
                locality_rejections.append({"kind": "shared-ground-neckdown",
                                            **endpoint_neckdown})
                continue
            return {
                "status": "shared-ground-neckdown",
                "role": link_role,
                "layer": board.GetLayerName(layer),
                "width_mm": round(local_width / MM, 3),
                "class_width_mm": round(width / MM, 3),
                "length_mm": round(path_length, 3),
                "endpoint_neckdown": endpoint_neckdown,
                "items": items,
                "direct_mm": round(direct, 3),
                "max_local_mm": round(local_limit, 3),
            }
        return None

    # Ground siblings on the same fine-pitch package should take the short,
    # same-layer guarded bridge before the generic via/inner-layer maze.  The
    # old ordering spent minutes exploring multilayer seats for a connection
    # that is electrically and geometrically just one 0.5 mm segment.
    shared_ground = _shared_ground_neckdown()
    if shared_ground is not None:
        return shared_ground, None
    if link_role == "shared-ground-entry":
        if diagnostics is not None:
            diagnostics.update({
                "schema": 1,
                "conclusion": "no_guarded_local_shared_ground_path",
                "owner": _pad_identity(owner_pad),
                "cap": _pad_identity(cap_pad),
                "locality": {
                    "direct_mm": round(direct, 3),
                    "max_local_mm": round(local_limit, 3),
                    "rejected_candidates": locality_rejections,
                },
            })
        return None, "no guarded local shared-ground path"

    # Adjacent fine-pitch power pins can be individually escapable yet unable
    # to support two class-width face-layer throats at once.  The generic
    # last-mile engine already owns a guarded two-via bridge for exactly that
    # topology; use it here with the *assigned* owner/cap pair rather than
    # falling back to the older nearest-load heuristic.  Plane layers are
    # excluded from routing, via geometry satisfies both netclass and board
    # minima, and every stub/via/inner leg receives the same edge and foreign-
    # copper checks as the same-layer path above.
    all_cu = set(board.GetEnabledLayers().CuStack())
    plane_ids = {board.GetLayerID(name) for name in cec_fr.plane_layers(board)}
    plane_ids.discard(-1)
    bridge_layers = [
        layer for layer in all_cu
        if layer not in set(common) and layer not in plane_ids
        and not any(role in board.GetLayerName(layer).upper()
                    for role in ("GND", "PWR"))
        and (current_widths is None or
            current_widths['required_by_layer_nm'].get(int(layer),math.inf)<=width)]
    bridge_layers.sort(key=lambda layer: (
        0 if "SIG" in board.GetLayerName(layer).upper() else
        1 if board.GetLayerName(layer).upper().startswith("IN") else
        2 if layer == pcbnew.B_Cu else 3,
        layer))
    diameter, drill, board_limits = _board_legal_through_via_geometry(
        board, float(spec["via_dia"]), float(spec["via_drill"]))
    # Contained POFV is a process/clearance permission, not permission to
    # undersize a newly introduced supply transition. The historical
    # fallback could bypass the full-web geometry compiled by the assigned
    # bridge and choose a small endpoint POFV instead. Hold the complete
    # source/class copper web through every fallback too. Retained columns
    # are handled separately above; this does not assign them ampacity.
    required_new_web = width if current_widths is not None else 0
    if required_new_web:
        diameter_nm = max(pcbnew.FromMM(diameter),
            pcbnew.FromMM(drill) + required_new_web)
        diameter = (diameter_nm + 1) / MM

    def _bridge_ops_ok(stage_name, candidate):
        return (_within_locality(stage_name, _ops_length_mm(candidate))
            and (not rail_completion or all(op[0] == "via" or op[3] >= max(
                class_width, current_widths['required_by_layer_nm'][int(op[4])])
                for op in candidate))
            and all(op[0] != "via" or
                pcbnew.FromMM(op[3]) - pcbnew.FromMM(op[2]) >= required_new_web
                for op in candidate))

    ops = None
    bridge_meta = None
    bridge_mode = None

    if bridge_layers:
        ops, bridge_meta = _pofv_supply_bridge_ops(
            board, owner_pad, cap_pad, width, clearance, net_code,
            bridge_layers, spec,
            ops_ok=lambda candidate: _bridge_ops_ok(
                "via-in-pad-bridge", candidate),
            deadline_monotonic=search_deadline, pofv_geometry=pofv_geometry,
            max_length_nm=local_limit*MM, allow_maze=allow_maze)
        if ops and _bridge_ops_ok("via-in-pad-bridge", ops):
            bridge_mode = "via-in-pad-bridge"
        else:
            ops = None
            bridge_meta = None
            # The shared endpoint search deliberately bounds local supply
            # webs to 2 mm. Larger power trunks need their rated bus/forest
            # constructor; never silently lower the demanded web to fit.
            ops = None if required_new_web > 2000000 else cec_fr._lastmile_bridge(
                board, (start.x, start.y),
                set(owner_pad.GetLayerSet().CuStack()),
                (end.x, end.y), set(cap_pad.GetLayerSet().CuStack()),
                width, net_code, bridge_layers, clearance,
                drill=drill, dia=diameter, seat_limit=48,
                leg_ok=lambda a, b, half: cec_fr._edge_leg_clear(
                    board, a, b, half),
                start_escape=start_escape, end_escape=end_escape,
                allow_maze=allow_maze, maze_margin_mm=2.0,
                foreign_cache=foreign_cache,
                deadline_monotonic=search_deadline,
                max_length_nm=local_limit*MM,
                minimum_local_via_web_nm=required_new_web,
                ops_ok=lambda candidate: _bridge_ops_ok(
                    "via-bridge", candidate))
            if ops and _bridge_ops_ok("via-bridge", ops):
                bridge_mode = "via-bridge"
            else:
                ops = None
    if ops:
        items = []
        used_layers = set()
        neckdowns = set()
        copper_length = 0.0
        via_count = 0
        via_diameters = []
        via_drills = []
        for op in ops:
            if op[0] == "via":
                _, at, op_drill, op_diameter = op
                item = pcbnew.PCB_VIA(board)
                item.SetPosition(at)
                item.SetDrill(pcbnew.FromMM(op_drill))
                item.SetWidth(pcbnew.FromMM(op_diameter))
                item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                item.SetNetCode(net_code); item.SetLocked(bool(lock))
                board.Add(item); items.append(item); via_count += 1
                via_diameters.append(float(op_diameter))
                via_drills.append(float(op_drill))
                continue
            _, a, b, leg_width, layer = op
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(a); item.SetEnd(b)
            item.SetWidth(leg_width); item.SetLayer(layer)
            item.SetNetCode(net_code); item.SetLocked(bool(lock))
            board.Add(item); items.append(item); used_layers.add(layer)
            copper_length += math.hypot(
                b.x - a.x, b.y - a.y) / MM
            if leg_width < width:
                neckdowns.add(round(leg_width / MM, 3))
        admitted, endpoint_neckdown = _admit_link_neckdowns(
            board, items, width, persist_group=group_neckdowns)
        if not admitted:
            if diagnostics is not None:
                diagnostics.update({"schema": 1,
                    "conclusion": "local_bridge_neckdown_rejected",
                    "owner": _pad_identity(owner_pad),
                    "cap": _pad_identity(cap_pad),
                    "endpoint_neckdown": endpoint_neckdown})
            return None, "local bridge endpoint neckdown qualification failed"
        return {
            "status": bridge_mode or "via-bridge",
            "layers": [board.GetLayerName(layer)
                       for layer in sorted(used_layers)],
            "width_mm": round(width / MM, 3),
            "neckdown_widths_mm": sorted(neckdowns),
            "length_mm": round(copper_length, 3),
            "vias": via_count,
            "via_diameter_mm": round(max(via_diameters, default=float(
                (bridge_meta or {}).get('diameter_mm') or 0.)), 3),
            "via_drill_mm": round(max(via_drills, default=float(
                (bridge_meta or {}).get('drill_mm') or 0.)), 3),
            "reused_endpoint_via_uuids": (bridge_meta or {}).get(
                'reused_endpoint_via_uuids', []),
            "board_limits": ((bridge_meta or {}).get("board_limits")
                             or board_limits),
            "via_in_pad": bridge_mode == "via-in-pad-bridge",
            "fab_profile": ((bridge_meta or {}).get("fab_profile")),
            "qualified_process_exception": bool(
                (bridge_meta or {}).get("qualified_process_exception")),
            "endpoint_limited_local_via": bool(
                (bridge_meta or {}).get("endpoint_limited_local_via")),
            "endpoint_modes": ((bridge_meta or {}).get("endpoint_modes")),
            "endpoint_neckdown": endpoint_neckdown,
            "items": items,
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    if diagnostics is not None:
        certificate = cec_fr._lastmile_refusal_certificate(
            board, start, end, width, clearance, net_code,
            sorted(set(common) | set(bridge_layers)),
            endpoint_a=_pad_identity(owner_pad),
            endpoint_b=_pad_identity(cap_pad), maze_searched=allow_maze,
            maze_margin_mm=2.0, start_escape=start_escape,
            end_escape=end_escape)
        certificate["search"]["via_bridge"] = bool(bridge_layers)
        certificate["search"]["via_bridge_layers"] = [
            board.GetLayerName(layer) for layer in bridge_layers]
        search_elapsed_s = max(0.0, time.monotonic() - search_started)
        search_exhausted = bool(
            search_deadline is not None
            and time.monotonic() >= search_deadline)
        certificate["search"]["budget_s"] = (
            None if search_timeout_s is None
            else float(search_timeout_s))
        certificate["search"]["elapsed_s"] = round(search_elapsed_s, 6)
        certificate["search"]["budget_exhausted"] = search_exhausted
        certificate["locality"] = {
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
            "rejected_candidates": locality_rejections,
        }
        diagnostics.update(certificate)
    if (search_deadline is not None
            and time.monotonic() >= search_deadline):
        return None, "local supply search budget exhausted without a path"
    return None, "no guarded local supply path within locality bound"


def audit_supply_access_board(board, *, max_assignment_mm=3.5):
    """Prove each selected bypass cell has a legal local rail launch.

    This is a read-only placement oracle even though it reuses the exact
    generator: every trial segment is removed immediately.  A distance-only
    bypass check can pass while foreign pads or package geometry make the
    owner-to-cap link impossible; discovering that after global routing is too
    late for a professional flow.  Reusing ``_add_supply_link`` keeps the
    preflight and eventual copper construction identical by construction.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in _ordered_assigned_cells(board, assignment):
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned.get("cap_ref"))
        cap_rail = next(
            (pad for pad in cap.Pads()
             if pad.GetNetname() == requirement.get("rail")), None) \
            if cap else None
        row = {
            "owner": requirement.get("ref"),
            "pin": requirement.get("pin"),
            "rail": requirement.get("rail"),
            "cap": assigned.get("cap_ref"),
            "placement_distance_mm": round(
                float(assigned.get("distance_mm") or 0.0), 3),
        }
        if requirement.get("pad") is None or cap_rail is None:
            row.update({"status": "refused",
                        "reason": "missing owner or capacitor rail pad"})
            rows.append(row)
            continue
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        diagnostic = {}
        supply, error = _add_supply_link(
            board, requirement["pad"], cap_rail, lock=True,
            diagnostics=diagnostic, group_neckdowns=False)
        generated = [
            item for item in list(board.GetTracks())
            if item.m_Uuid.AsString() not in before]
        discard_items(board, generated)
        row.update({
            "status": "accessible" if error is None else "refused",
            "reason": error,
            "supply": ({key: value for key, value in supply.items()
                        if key != "items"} if supply else None),
            "trial_item_count": len(generated),
            "certificate": diagnostic or None,
        })
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    return {
        "schema": 1, "ok": not refused,
        "requirements": len(assignment.get("requirements") or ()),
        "accessible": len(rows) - len(refused),
        "refused": refused, "cells": rows,
    }


def supply_access_reservations_board(board, *, max_assignment_mm=3.5,
                                     ground_reach_mm=1.5):
    """Return exact, read-only copper primitives for future bypass cells.

    Broad power objects are planned before the local PI materializer, but that
    ordering must not let a pour consume the only legal supply bridge,
    capacitor GND return, owner GND return, or shared-entry via column.  Run
    the *same collective, all-or-nothing synthesizer* used by production,
    serialize its exact track/via geometry, then remove every trial item.
    Pour planning can reserve the complete cells without guessing at a
    component-sized halo or baking in a board-specific coordinate.

    The historical function name is retained for API compatibility; its
    contract now deliberately covers the complete local PI cell.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    report = synthesize_board(
        board, board_path=getattr(board, "GetFileName", lambda: "")(),
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True,
        assignment=assignment, group_neckdowns=False)
    ground_report = synthesize_ground_plane_access_board(
        board, board_path=getattr(board, "GetFileName", lambda: "")(),
        reach_mm=ground_reach_mm, lock=True,
        group_neckdowns=False)
    generated = [item for item in list(board.GetTracks())
                 if item.m_Uuid.AsString() not in before]
    provenance = {
        row.get("uuid"): row
        for row in report.get("generated_items") or () if row.get("uuid")}
    # The global GND-portal pass runs after the bypass-cell pass and therefore
    # contributes generated vias/tracks that are absent from the first
    # provenance table.  Preserve their owning footprint/pad explicitly.  A
    # lost owner used to become ``?`` in the pour planner, creating a real
    # future-copper obstacle that placement could neither identify nor move.
    for terminal in ground_report.get("terminals") or ():
        owner = str(terminal.get("ref") or "")
        if not owner:
            continue
        for uuid in terminal.get("generated_item_uuids") or ():
            provenance.setdefault(uuid, {
                "uuid": uuid,
                "owner": owner,
                "cap": None,
                "pad": str(terminal.get("pad") or ""),
                "purpose": "ground_plane_access",
            })
    primitives = []
    try:
        for item in generated:
            source = provenance.get(item.m_Uuid.AsString(), {})
            common = {
                "net": item.GetNetname(),
                "net_code": int(item.GetNetCode()),
                "owner": source.get("owner"),
                "cap": source.get("cap"),
                "pad": source.get("pad"),
                "purpose": source.get("purpose", "bypass_cell"),
            }
            if item.GetClass() == "PCB_VIA":
                at = item.GetPosition()
                primitives.append(dict(
                    common, kind="via",
                    at_mm=[at.x / MM, at.y / MM],
                    diameter_mm=item.GetWidth(pcbnew.F_Cu) / MM,
                    drill_mm=item.GetDrillValue() / MM,
                    layer_ids=sorted(
                        int(layer) for layer in item.GetLayerSet().CuStack())))
            else:
                start, end = item.GetStart(), item.GetEnd()
                primitives.append(dict(
                    common, kind="track", layer_id=int(item.GetLayer()),
                    start_mm=[start.x / MM, start.y / MM],
                    end_mm=[end.x / MM, end.y / MM],
                    width_mm=item.GetWidth() / MM))
    finally:
        discard_items(board, generated)
    result = _report_only(report)
    result.update({
        "ok": bool(report.get("ok") and ground_report.get("ok")),
        "read_only": True,
        "trial_item_count": len(generated),
        "primitives": primitives,
        "ground_access": _report_only(ground_report),
        "refused": (list(report.get("refused") or ()) + [{
            **row, "stage": "ground_plane_access"}
            for row in ground_report.get("refused") or ()]),
    })
    return result


def _reservation_file_worker(board_path, report_path, *, max_assignment_mm,
                             ground_reach_mm):
    board = pcbnew.LoadBoard(board_path)
    report = supply_access_reservations_board(
        board, max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(report, sink, indent=2, sort_keys=True)


def supply_access_reservations_file(board_path, *, max_assignment_mm=3.5,
                                    ground_reach_mm=1.5, timeout=180):
    """Probe complete-cell reservations in a disposable pcbnew process.

    Removing trial tracks invalidates child proxies in KiCad's deprecated
    SWIG API.  A planner that keeps using that BOARD can consequently fault
    during an unrelated later operation.  The file boundary makes rollback
    literal (the source is never saved) and exits without running unsafe SWIG
    finalizers after the JSON evidence is durable.
    """
    fd, report_path = tempfile.mkstemp(
        prefix="cec-cell-reservations-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--reservation-worker",
        "--board", os.path.abspath(board_path), "--report", report_path,
        "--max-assignment-mm", str(float(max_assignment_mm)),
        "--ground-reach-mm", str(float(ground_reach_mm)),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=float(timeout))
        if completed.returncode:
            raise RuntimeError(
                "cell reservation worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout or
                     "no diagnostic")[-1600:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def _straight_filled_return_mm(board, pad, via, *, include_native_tracks=False):
    """Prove a direct return through actual fill/track copper, never outlines.

    Include native pad copper at the endpoints so thermal relief gaps are not
    mistaken for a disconnected pad. The complete direct path must exist;
    membership of two points in one zone object is not evidence. This proves
    locality, not neck width or impedance; those retain independent gates.
    Straight native source capsules may provide the same local copper even
    when a graph has no explicit endpoint at a via's interior body contact.
    """
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    from shapely import make_valid
    if type(include_native_tracks) is not bool:
        raise ValueError('explicit_native_track_body_return_observation_required')

    def polygons(poly):
        rows = []
        for index in range(poly.OutlineCount()):
            ring = poly.Outline(index)
            shell = [(ring.CPoint(i).x/MM, ring.CPoint(i).y/MM)
                     for i in range(ring.PointCount())]
            holes = []
            for h in range(poly.HoleCount(index)):
                ring = poly.Hole(index, h)
                holes.append([(ring.CPoint(i).x/MM, ring.CPoint(i).y/MM)
                              for i in range(ring.PointCount())])
            if len(shell) >= 3:
                shape = Polygon(shell, holes)
                # KiCad may fracture a polygon into a self-touching outline
                # to encode holes. Preserve those cutouts with make_valid.
                rows.append(shape if shape.is_valid else make_valid(shape))
        return rows

    p, v = pad.GetPosition(), via.GetPosition()
    a, b = (p.x/MM, p.y/MM), (v.x/MM, v.y/MM)
    strip = LineString([a, b])
    tracks=list(board.GetTracks()) if include_native_tracks else []
    if len(tracks)>16384:return None
    left,right=sorted((int(p.x),int(v.x)));top,bottom=sorted((int(p.y),int(v.y)))
    for layer in pad.GetLayerSet().CuStack():
        if not via.IsOnLayer(layer):
            continue
        fills = []
        for zone in board.Zones():
            if (not zone.GetIsRuleArea() and zone.IsFilled()
                    and zone.GetNetCode() == pad.GetNetCode()
                    and zone.IsOnLayer(layer)):
                fills.extend(polygons(zone.GetFilledPolysList(layer)))
        for track in tracks:
            if (track.GetClass()!='PCB_TRACK' or track.GetNetCode()!=pad.GetNetCode()
                    or not track.IsOnLayer(layer) or track.GetWidth()<=0):
                continue
            box=track.GetBoundingBox()
            if box.GetRight()<left or box.GetLeft()>right or box.GetBottom()<top or box.GetTop()>bottom:
                continue
            poly=pcbnew.SHAPE_POLY_SET()
            track.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_INSIDE)
            fills.extend(polygons(poly))
        if not fills:
            continue
        fills.extend(polygons(pad.GetEffectivePolygon(layer)))
        fills.append(Point(b).buffer(via.GetWidth(layer)/MM/2))
        if unary_union(fills).covers(strip):
            return math.dist(a, b)
    return None


def _return_path_aabb_lower_bound_mm(pad, via):
    """Conservative XY cost floor, never a connectivity or return witness.

    Every explicit path has nonnegative arc/segment length and plated jumps
    change Z only. Pad/target nodes may be anywhere within their real native
    bounds (including the observer's 1nm HitTest tolerance); overcover each
    bound by2nm before taking its separation. The filled straight-path proof
    is also no shorter than this floor. Unsupported mock objects get zero,
    retaining the original exhaustive observation instead of guessing.
    """
    try:
        a,b=pad.GetBoundingBox(),via.GetBoundingBox()
        dx=max(int(a.GetX())-int(b.GetRight())-4,int(b.GetX())-int(a.GetRight())-4,0)
        dy=max(int(a.GetY())-int(b.GetBottom())-4,int(b.GetY())-int(a.GetBottom())-4,0)
        return math.hypot(dx,dy)/MM
    except (AttributeError,TypeError,ValueError):
        return 0.


def _existing_return(board, pad, reach_mm, *, rebuild=True,allow_native_track_body=False):
    """Prove locality from live geometry, not KiCad's global graph cache.

    The explicit-copper path and actual filled-polygon proofs below consume
    no CONNECTIVITY_DATA. Rebuilding it before each lookup was pure overhead,
    multiplied by every cell ordering/rollback and placement microvariant.
    Keep ``rebuild`` as an API-compatible no-op for existing callers. Each
    lookup still reads the current board items; no proof survives a mutation.
    Native connectivity rebuilds at transaction/final admission stay intact.
    """
    if type(allow_native_track_body) is not bool:
        raise ValueError('explicit_native_track_body_return_observation_required')
    pos = pad.GetPosition()
    candidates = []
    for ordinal,item in enumerate(board.GetTracks()):
        if (item.GetClass() != "PCB_VIA" or item.GetNetname() != "GND"
                or item.GetNetCode() != pad.GetNetCode()):
            continue
        # The real explicit graph starts/ends on the native pad/via metal,
        # not necessarily their centres. A long SMD land may have a tiny
        # outside-pad return to a separated ordinary barrel whose centre is
        # farther than reach_mm. Centre distance is NOT a lower bound for
        # that established graph metric; use only the native-envelope floor
        # already used by the exact observation ordering below. This filter
        # grants no path credit: the unchanged copper observer still has to
        # prove a path inside the unchanged reach, with every native guard
        # and factory/process check left to its receiving owner.
        lower = _return_path_aabb_lower_bound_mm(pad, item)
        if lower > reach_mm + 1e-9:
            continue
        candidates.append((lower,ordinal,item))
    best=None
    # Only these same-net native VIAs are targets. Unlike a second PAD they
    # contribute no additional graph seed, so graph construction is identical
    # for the whole immutable query. Never retain it beyond this invocation.
    prepared=None; prepared_once=False
    for lower,ordinal,item in sorted(candidates,key=lambda row:row[:2]):
        # Only skip work after a real explicit/filled proof establishes a
        # strictly smaller answer. Equal-cost candidates still receive full
        # observation, preserving the original source-order tie winner.
        if best is not None and lower>best[0]+1e-12:
            break
        # No coarse endpoint snapping for this proof: nearby disconnected
        # stubs must not become a fictional short path around a real detour.
        if not prepared_once:
            prepared = _explicit_track_graph(board, pad.GetNetCode(), (pad,), 1)
            prepared_once = True
        path = _query_explicit_track_path_mm(prepared, pad, item, 1)
        if allow_native_track_body:
            # A pad translated onto the retained track body may still
            # contain its OLD endpoint. That explicit graph cost is real,
            # but need not be the shortest real return anymore. Compare the
            # independently proved straight native-copper path even when
            # the old endpoint path is already inside the observation bound.
            # Its centre-to-axis length cannot improve an equal/shorter
            # explicit witness, especially the already proved zero case.
            distance=math.dist(tuple(pos),tuple(item.GetPosition()))/MM
            if path is None or distance<path:
                direct=_straight_filled_return_mm(board,pad,item,include_native_tracks=True)
                if direct is not None:path=direct if path is None else min(path,direct)
        elif path is None or path > reach_mm + 1e-9:
            path = _straight_filled_return_mm(board, pad, item,include_native_tracks=False)
        if path is not None and path <= reach_mm + 1e-9:
            # Every supported explicit-copper/filled-return cost is
            # nonnegative. The first proved zero is therefore exactly the
            # same first minimum the old full scan returned; no distant via
            # can improve it. Do not rebuild the same whole-net path graph
            # for every remaining barrel once this physical lower bound wins.
            if path == 0.0:
                return path, item
            if best is None or (path,ordinal)<best[:2]:best=(path,ordinal,item)
    return None if best is None else (best[0],best[2])


def _shared_ground_return(board, pad, portal_pad, reach_mm):
    """Prove a bounded explicit-copper path to a peer's local GND via.

    The cell generator can legitimately use one qualified via for two nearby
    ground lands when a guarded same-net link joins them.  Final audit used to
    forget that topology and demanded a second via inside ``reach_mm`` of the
    linked land.  Keep this proof deliberately stricter than global
    connectivity: zones are excluded, the peer must itself own an immediate
    via, and the visible track path must fit the same bounded-locality rule
    used by the generator.
    """
    portal_return = _existing_return(board, portal_pad, reach_mm)
    if portal_return is None:
        return None
    direct = math.hypot(
        pad.GetPosition().x - portal_pad.GetPosition().x,
        pad.GetPosition().y - portal_pad.GetPosition().y) / MM
    path = _shortest_track_path_mm(board, pad, portal_pad)
    spec = _netclass(board, "GND")
    local_limit = _local_supply_limit_mm(
        direct, float(spec["width"]) / MM,
        max(pcbnew.FromMM(0.20), int(spec["clearance"])) / MM)
    if path is None or path > local_limit + 1e-9:
        return None
    return {
        "status": "shared-ground-entry",
        "path_mm": round(path, 3),
        "direct_mm": round(direct, 3),
        "max_local_mm": round(local_limit, 3),
        "portal_via_distance_mm": round(portal_return[0], 3),
        "via_uuid": portal_return[1].m_Uuid.AsString(),
        "shared_with": _pad_identity(portal_pad),
    }


def _ground_terminal_layer(pad):
    """Use a surface land's copper membership, not its generic item layer.

    Native PAD.GetLayer() can report F.Cu even for a B.Cu-only SMD land. A
    dogbone on that reported layer is not connected to the actual terminal.
    Keep existing multilayer-terminal handling outside this unique-SMD case.
    """
    surface = cec_return_escape.smd_surface_layer(pad)
    if surface is not None:
        return surface
    return pad.GetLayer()


def qualified_via_in_pad_return(row):
    """Keep return topology independent of whether copper was just created."""
    row = row or {}
    return (row.get('status') == 'via-in-pad'
            or (row.get('status') == 'covered'
                and row.get('return_topology') == 'via-in-pad'
                and row.get('topology_qualified') is True
                and bool(row.get('via_uuid'))))


def _existing_return_topology(board, pad, via):
    """Requalify a reused physical land; proximity alone is not via-in-pad."""
    layer = cec_return_escape.smd_surface_layer(pad)
    if (layer is None or via.GetViaType() != pcbnew.VIATYPE_THROUGH
            or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
            or not via.IsOnLayer(layer)):
        return {}
    ok, reason = cec_fab_profile.via_pad_decision(
        board, pad, via.GetPosition(), via.GetWidth(layer),
        via.GetDrillValue(), via.GetNetCode())
    if not ok:
        return {}
    return dict(return_topology='via-in-pad', topology_qualified=True,
        topology_evidence=dict(schema=1, source='native_reused_return_land',
            pad=_pad_identity(pad), via_uuid=via.m_Uuid.AsString(),
            fab_profile=cec_fab_profile.board_profile_name(board),
            diameter_mm=via.GetWidth(layer) / MM, drill_mm=via.GetDrillValue() / MM,
            reason=reason))


def _routed_return_evidence(board, pad, observed):
    """Describe an actual local return; never invent a constructed VIP.

    The saved observer grants the narrow VIP metric only after re-proving
    the entire supported uniform through stack and every actual pad overlap.
    Unknown/custom stacks retain their measured ordinary return, without VIP
    qualification. Whole-board DRC/current/plane receiving remains separate.
    """
    if observed is None:
        return None
    distance, via = observed
    proof = dict(status='covered', distance_mm=round(distance, 3),
        via_uuid=str(via.m_Uuid.AsString()), observed_saved_copper=True,
        topology_qualified=False)
    try:
        uid = proof['via_uuid']
        if (not math.isfinite(distance) or distance < 0 or not uid
                or uid == '00000000-0000-0000-0000-000000000000'
                or sum(str(item.m_Uuid.AsString()) == uid
                    for item in board.GetTracks()) != 1):
            raise ValueError('unique_actual_saved_return_barrel_identity_required')
        faces = tuple(board.GetEnabledLayers().CuStack())
        if (not 2 <= len(faces) <= 64 or via.GetClass() != 'PCB_VIA'
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or via.Padstack().Mode() != pcbnew.PADSTACK.MODE_NORMAL
                or via.GetNetCode() <= 0 or via.GetNetCode() != pad.GetNetCode()
                or any(not via.IsOnLayer(face) for face in faces)):
            raise ValueError('unsupported_saved_return_stack_or_net')
        widths = {int(via.GetWidth(face)) for face in faces}
        drill = int(via.GetDrillValue())
        if len(widths) != 1 or not 0 < drill < min(widths):
            raise ValueError('uniform_positive_saved_return_stack_required')
        width = next(iter(widths)); at = via.GetPosition()
        blocking, _ = cec_fab_profile.via_at_pad_conflicts(
            board, at, width, drill, via.GetNetCode())
        if blocking is not None:
            raise ValueError('saved_return_pad_process_conflict')
        # The legacy collision helper deliberately uses one pad face and
        # catches shape exceptions. That alone cannot qualify arbitrary saved
        # objects. Re-read all actual copper faces here, without that fallback.
        checked = []
        for fp in board.GetFootprints():
            for other in fp.Pads():
                for face in faces:
                    if not other.IsOnLayer(face):
                        continue
                    shape = other.GetEffectiveShape(face)
                    if shape is None:
                        raise ValueError('saved_return_native_pad_shape_unavailable')
                    if not shape.Collide(at, (width+1)//2):
                        continue
                    accepted, reason = cec_fab_profile.via_pad_decision(
                        board, other, at, width, drill, via.GetNetCode())
                    if not accepted:
                        raise ValueError('saved_return_all_face_pad_process_conflict:'+reason)
                    checked.append(dict(pad=_pad_identity(other), layer_id=int(face)))
        topology = _existing_return_topology(board, pad, via)
        if topology.get('topology_qualified') is not True:
            raise ValueError('saved_return_full_native_owner_land_not_qualified')
        proof.update(topology, all_enabled_face_widths_uniform=True,
            all_actual_pad_face_overlaps_requalified=checked)
    except Exception as exc:
        # This is absence of permission to use the VIP proximity metric,
        # never a fabrication pass or permission to erase an observed fault.
        proof['topology_observation_refusal'] = type(exc).__name__+':'+str(exc)
    return proof


def _ground_obstruction_evidence(diagnostic):
    """Retain measured blockers from every bounded ground-return geometry.

    A pad-center assembly exclusion is not the cause of every failed dogbone.
    Looking only at that first failure concealed inherited locked conductors
    in later legal launch rays and sent the coordinator to the wrong stage.
    This is sampled evidence, not authority to alter a blocker or no-path proof.
    """
    tiers=[('ordinary',diagnostic)]
    for index,attempt in enumerate((diagnostic.get('compact_dogbone_attempts') or ())[:2]):
        detail=attempt.get('evidence') or {}
        if attempt.get('error') and detail.get('search_exhausted') is True:
            tiers.append(('compact-'+str(index),detail))
    measured={};visited=0;truncated=0
    for name,detail in tiers:
        seats=[('pad-center',(detail.get('pad_center') or {}).get('copper_admission') or {})]
        seats.extend(('dogbone',seat.get('copper_admission') or {})
                     for seat in (detail.get('dogbone_candidates') or ())[:16])
        truncated+=int(detail.get('dogbone_candidates_truncated') or 0)
        for origin,admission in seats:
            if admission.get('ok') is not False:
                continue
            visited+=1
            for blocker in (admission.get('blockers') or ())[:16]:
                # UUID where available; exact recorded native/recipe identity
                # otherwise. Never resolve a net-name into a guessed object.
                key=json.dumps(blocker,sort_keys=True,separators=(',',':'))
                entry=measured.setdefault(key,dict(blocker=blocker,observed_in=[]))
                entry['observed_in'].append(dict(tier=name,origin=origin,
                    at_mm=admission.get('at_mm'),layer=admission.get('layer')))
    rows=[measured[key] for key in sorted(measured)][:128]
    protected=sorted({row['blocker']['uuid'] for row in measured.values()
        if row['blocker'].get('locked') and row['blocker'].get('uuid')
        and row['blocker'].get('kind') in ('track','via','zone')})
    return dict(blocking_native_objects=rows,measured_blocker_objects=len(measured),
        measured_failed_sites=visited,
        blocker_evidence_truncated=max(0,len(measured)-len(rows)),
        ground_seat_samples_truncated=truncated,
        protected_blocker_uuids=protected,
        repair_stage=('upstream_owned_copper_replan' if protected
                      else 'local_ground_access_placement_or_route'),
        no_path_proof=False,blocker_mutation_authorized=False)


def _add_ground_return(board, pad, *, board_path, reach_mm, lock, diagnostics=None,
                       pofv_geometry=None, extended_ordinary_reach=False):
    if (type(extended_ordinary_reach) is not bool or extended_ordinary_reach and
            (type(reach_mm) not in (int,float) or not math.isfinite(reach_mm) or not 1.5<reach_mm<=3.)):
        raise ValueError('explicit_bounded_ordinary_ground_shortcut_reach_required')
    covered = _existing_return(board, pad, reach_mm)
    if covered is not None:
        existing_via = covered[1]
        blocking, _allowed = cec_fab_profile.via_at_pad_conflicts(
            board, existing_via.GetPosition(),
            existing_via.GetWidth(pcbnew.F_Cu),
            existing_via.GetDrillValue(), existing_via.GetNetCode())
        if blocking is not None:
            return None, (
                "existing immediate GND return is not fabrication-qualified: "
                "%s" % blocking)
        return {
            "status": "covered", "distance_mm": round(covered[0], 3),
            "via_uuid": existing_via.m_Uuid.AsString(), "items": [],
            **_existing_return_topology(board, pad, existing_via),
        }, None

    reused = _reconnect_existing_ground_via(board, pad, reach_mm=reach_mm, lock=lock)
    if reused is not None:
        return reused, None

    # A multi-rail IC can assign several bypass cells to different supply
    # pins while exposing adjacent same-net GND lands.  Earlier cells may
    # already have created a fabrication-qualified immediate return on one of
    # those lands.  Requiring every sibling land to grow another barrel can
    # make an otherwise excellent QFN cell impossible at fine pitch and is
    # electrically worse than a short, visible link to the existing portal.
    # Reuse only a pad on the *same footprint*, prove that the peer already
    # owns a local via, and generate the link through the same guarded,
    # locality-bounded shared-ground primitive used by owner/cap pairs.
    try:
        parent = pad.GetParentFootprint()
        pad_uuid = pad.m_Uuid.AsString()
    except Exception:                                  # noqa: BLE001
        parent = None
        pad_uuid = None
    sibling_portals = []
    if parent is not None:
        for peer in _owner_ground_pads(parent):
            try:
                if (peer.m_Uuid.AsString() == pad_uuid
                        or peer.GetNetCode() != pad.GetNetCode()
                        or peer.GetNetname() != pad.GetNetname()):
                    continue
            except Exception:                          # noqa: BLE001
                continue
            # The target-pad lookup at function entry already rebuilt the
            # graph. Rebuilding the complete board once per sibling turned a
            # small QFN pad scan into minutes of duplicate native work.
            portal = _existing_return(
                board, peer, reach_mm, rebuild=False)
            if portal is None:
                continue
            distance = math.hypot(
                peer.GetPosition().x - pad.GetPosition().x,
                peer.GetPosition().y - pad.GetPosition().y) / MM
            # Reuse is an *immediate* package portal, not a license to route
            # across the IC to whichever sibling happened to be processed
            # first.  A remote portal must not preempt a legal local dogbone
            # on this pad or trigger an expensive multilayer search.
            if distance > float(reach_mm) + 1e-9:
                continue
            sibling_portals.append((
                distance, str(peer.GetPadName()), peer, portal))
    for distance, _pin_sort, peer, portal in sorted(
            sibling_portals, key=lambda row: (row[0], row[1])):
        ground_link, link_error = _add_supply_link(
            board, pad, peer, lock=lock,
            link_role="shared-ground-entry",
            **({"pofv_geometry": pofv_geometry} if pofv_geometry is not None else {}))
        if link_error is not None:
            continue
        clean_link = {
            key: value for key, value in (ground_link or {}).items()
            if key != "items"}
        return {
            "status": "shared-owner-ground-entry",
            "distance_mm": round(float(
                clean_link.get("length_mm", distance)), 3),
            "via_uuid": portal[1].m_Uuid.AsString(),
            "shared_with": _pad_identity(peer),
            "shared_link": clean_link,
            "items": list((ground_link or {}).get("items") or ()),
        }, None
    gnd_code = pad.GetNetCode()
    pos = pad.GetPosition()
    layer = _ground_terminal_layer(pad)
    # The pad/track/zone geometry is immutable throughout one return-seat
    # search.  Share a caller-owned exact spatial snapshot across every ray
    # and candidate via; a successful mutation returns immediately, and a
    # second pad in the coupled cell receives a fresh snapshot that includes
    # the first pad's new copper.
    foreign_cache = {}
    profile_name = cec_fab_profile.active_profile_name(
        board, hint=board_path)
    profile = (cec_fab_profile.get_profile(profile_name)
               if profile_name else None)
    pofv = pofv_geometry or cec_fab_profile.preferred_pofv_geometry(profile)
    pofv_refusal = "board has no declared POFV profile"
    import cec_existing_local_pofv_pad_rule as saved_pad_rule
    local_pad_rule=saved_pad_rule.resolve(board,pad)
    if pofv:
        requested_diameter, requested_drill = pofv
        ordinary_diameter, ordinary_drill, board_limits = \
            _board_legal_through_via_geometry(
                board, requested_diameter, requested_drill)
        # The exact existing saved native pad rule, when present, governs
        # this in-pad construction. Ordinary/dogbone defaults remain exact.
        diameter, drill = (saved_pad_rule.geometry(local_pad_rule,pofv)
            if local_pad_rule else (ordinary_diameter,ordinary_drill))
        process_ok, process_reason = cec_fab_profile.pofv_dimensions(
            profile, diameter, drill)
        edge_clear = cec_fr._edge_leg_clear(
            board, pos, pos, pcbnew.FromMM(diameter) // 2)
        hole_clear, hole_conflicts = _hole_to_hole_clear(
            board, pos, drill)
        spot_report = {} if diagnostics is not None else None
        spot_clear = process_ok and cec_fr._via_spot_clear(
            board, pos, pcbnew.FromMM(diameter),
            pcbnew.FromMM(0.20), {gnd_code},
            drill_nm=pcbnew.FromMM(drill),
            net_code=gnd_code, contained_layers={layer},
            foreign_cache=foreign_cache, report=spot_report,
            local_pofv_pad=pad if local_pad_rule else None)
        if diagnostics is not None:
            diagnostics.update(schema=1, terminal=_pad_identity(pad),
                               pad_center={"process_ok": process_ok,
                                           "process_reason": process_reason,
                                           "edge_clear": edge_clear,
                                           "hole_clear": hole_clear,
                                           "hole_conflicts": hole_conflicts,
                                           "copper_admission": spot_report})
        if process_ok and edge_clear and hole_clear and spot_clear:
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pos)
            via.SetDrill(pcbnew.FromMM(drill))
            via.SetWidth(pcbnew.FromMM(diameter))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(gnd_code); via.SetLocked(bool(lock))
            board.Add(via)
            return {
                "status": "via-in-pad", "distance_mm": 0.0,
                "via_uuid": via.m_Uuid.AsString(), "items": [via],
                "fab_profile": profile_name,
                "diameter_mm": round(diameter, 3),
                "drill_mm": round(drill, 3),
                "requested_diameter_mm": round(requested_diameter, 3),
                "requested_drill_mm": round(requested_drill, 3),
                "endpoint_limited_local_via": True,
                "qualified_process_exception": bool(
                    diameter + 1e-9 < ordinary_diameter
                    or drill + 1e-9 < ordinary_drill),
                "board_limits": board_limits,
                "existing_native_local_pad_rule": local_pad_rule,
            }, None
        if not process_ok:
            pofv_refusal = process_reason
        elif not edge_clear:
            pofv_refusal = "board-edge clearance blocks the pad center"
        elif not hole_clear:
            pofv_refusal = "drill clearance blocks the pad center: %s" % (
                hole_conflicts[:2],)
        else:
            pofv_refusal = "pad-center via barrel or land is obstructed"

    # A component land is copper AREA, not a single legal drilling point.
    # Reuse the shared native contained-seat portfolio before spending the
    # separated-dogbone tier. Its geometry is clamped to ordinary BOARD
    # floors: a saved centre-only local rule is NOT borrowed off-centre.
    # No tiny redundant stub is needed when the whole land contains the via.
    declared=cec_fab_profile.board_profile_name(board)
    if declared and declared==profile_name and pad.GetNetname()=='GND':
        import cec_native_contained_via_events as contained
        spec=_netclass(board,'GND')
        width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']),200000)
        gap=max(int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']),200000)
        deadline=time.monotonic()+1.5
        seats=cec_fr._local_pofv_inset_seats(board,pos,layer,width,gnd_code,gap,
            profile=profile,leg_ok=lambda a,b,r:cec_fr._edge_leg_clear(board,a,b,r+gap),
            limit=4,foreign_cache=foreign_cache,deadline_monotonic=deadline,
            max_length_nm=math.floor(float(reach_mm)*MM),
            via_guard=lambda at,hole,dia:_hole_to_hole_clear(board,at,hole/MM)[0])
        if diagnostics is not None:
            diagnostics['contained_off_center_via']=dict(proposed=len(seats),
                ordinary_board_floors_unchanged=True,centre_only_local_rule_borrowed=False,
                extra_stub_required=False)
        for xy,operations in seats:
            at=pcbnew.VECTOR2I(*xy);via_ops=[op for op in operations if op[0]=='via']
            if len(via_ops)!=1:continue
            _,_,hole,dia=via_ops[0]
            if not contained.contains(pad,at,pcbnew.FromMM(dia)):continue
            via=pcbnew.PCB_VIA(board);via.SetPosition(at)
            via.SetWidth(pcbnew.FromMM(dia));via.SetDrill(pcbnew.FromMM(hole))
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(gnd_code)
            via.SetLocked(bool(lock));board.Add(via)
            try:
                valid,why=cec_fab_profile.local_pofv_via_decision(board,via,reach_mm=float(reach_mm))
            except Exception:
                discard_items(board,[via]);raise
            if not valid:
                discard_items(board,[via]);continue
            return dict(status='via-in-pad',distance_mm=math.dist(tuple(pos),xy)/MM,
                via_uuid=via.m_Uuid.AsString(),items=[via],fab_profile=profile_name,
                diameter_mm=dia,drill_mm=hole,contained_off_center=True,
                strict_native_full_land_containment=True,no_added_stub=True,
                ordinary_board_floors_unchanged=True,centre_only_local_rule_borrowed=False,
                existing_native_local_pad_rule=None,local_pofv_qualification=why,
                saved_current_native_return_and_factory_receiving_still_required=True),None

    # A separate exact saved-pad-rule tier may have legal boundary seats
    # that neither an in-pad circle nor the ordinary fixed-radius stencil
    # can represent. It freshly proves the actual source Ground/control
    # role and native process; absence of that rule grants no smaller via.
    # Ordinary and compact defaults below remain unchanged.
    if local_pad_rule and board_path is not None and float(reach_mm)<=1.50:
        import cec_source_rule_ground_boundary as source_boundary
        detail={} if diagnostics is not None else None
        result,error=source_boundary.construct(board,pad,board_path=board_path,
            reach_mm=float(reach_mm),lock=lock,diagnostics=detail,timeout_s=3.)
        if diagnostics is not None:
            diagnostics['source_rule_boundary_dogbone']=dict(error=error,evidence=detail)
        if result is not None:
            return result,None

    spec = _netclass(board, "GND")
    diameter, drill, board_limits = _board_legal_through_via_geometry(
        board, max(0.6, float(spec["via_dia"])),
        max(0.3, float(spec["via_drill"])))
    # The same declared filled/capped process also qualifies an immediately
    # adjacent SMD dogbone. A narrow land need not contain the whole via, but
    # partial overlaps remain forbidden. Never infer this permission from a
    # filename/profile hint, and never change ordinary routing/stitching sizes.
    declared = cec_fab_profile.board_profile_name(board)
    compact_profile = (cec_fab_profile.get_profile(declared) if declared else None)
    compact_geometries = ((pofv_geometry,) if pofv_geometry is not None else
        cec_fab_profile.local_pofv_geometry_candidates(compact_profile,board=board))
    compact_attempts = []
    if (compact_profile and compact_profile.get("pofv")
            and int(pad.GetAttribute()) == int(pcbnew.PAD_ATTRIB_SMD)
            and cec_return_escape.smd_surface_layer(pad) is not None):
        for compact_diameter, compact_drill in compact_geometries:
            compact_diameter,compact_drill,_limits=_board_legal_through_via_geometry(
                board,compact_diameter,compact_drill)
            process_ok, reason = cec_fab_profile.pofv_dimensions(
                compact_profile, compact_diameter, compact_drill)
            if not process_ok:
                continue
            detail = {} if diagnostics is not None else None
            result, error = _add_ground_dogbone(
                board, pad, diameter=compact_diameter, drill=compact_drill,
                board_limits=board_limits, profile_name=declared,
                reach_mm=min(float(reach_mm), 1.50), lock=lock,
                diagnostics=detail, foreign_cache=foreign_cache,
                pofv_refusal=pofv_refusal, qualified_compact=True)
            if diagnostics is not None:
                compact_attempts.append(dict(diameter_mm=compact_diameter,
                    drill_mm=compact_drill, error=error, evidence=detail))
                diagnostics["compact_dogbone_attempts"] = compact_attempts
            if result is not None:
                return result, None
    return _add_ground_dogbone(
        board, pad, diameter=diameter, drill=drill, board_limits=board_limits,
        profile_name=profile_name, reach_mm=reach_mm, lock=lock,
        diagnostics=diagnostics, foreign_cache=foreign_cache,
        pofv_refusal=pofv_refusal,extended_ordinary_reach=extended_ordinary_reach)


def _reconnect_existing_ground_via(board, pad, *, reach_mm, lock):
    """Short guarded copper to a REAL qualified barrel, never duplicate holes.

    Proximity is only a proposal: revalidate the existing through-via on every
    layer and prove an explicit full-class path inside the unchanged immediate
    return limit. Foreign force copper, holes, process and edge rules remain
    in force. This tier neither modifies a via nor assumes a ground plane is
    globally connected; saved-board receiving still owns that proof.
    """
    layer=cec_return_escape.smd_surface_layer(pad)
    if layer is None or pad.GetNetname()!='GND' or pad.GetNetCode()<=0:
        return None
    spec=_netclass(board,'GND')
    width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']),200000)
    gap=max(int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']),200000)
    at=pad.GetPosition();code=pad.GetNetCode();cache={}
    profile_name=cec_fab_profile.board_profile_name(board)
    profile=cec_fab_profile.get_profile(profile_name) if profile_name else None
    candidates=[]
    for via in board.GetTracks():
        if (via.GetClass()!='PCB_VIA' or via.GetNetCode()!=code
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
            continue
        distance=math.dist(tuple(at),tuple(via.GetPosition()))/MM
        if distance<=float(reach_mm):candidates.append((distance,via.m_Uuid.AsString(),via))
    for distance,uid,via in sorted(candidates)[:12]:
        dia=via.GetWidth(layer);drill=via.GetDrillValue()
        ordinary_dia,ordinary_drill,_limits=_board_legal_through_via_geometry(
            board,dia/MM,drill/MM)
        if (dia+1<pcbnew.FromMM(ordinary_dia) or drill+1<pcbnew.FromMM(ordinary_drill)):
            if not profile or not cec_fab_profile.pofv_dimensions(profile,dia/MM,drill/MM)[0]:
                continue
        if (not cec_fr._edge_leg_clear(board,via.GetPosition(),via.GetPosition(),dia/2+gap)
                or not cec_fr._via_spot_clear(board,via.GetPosition(),dia,gap,{code},
                    drill_nm=drill,net_code=code,existing_via_uuid=uid,foreign_cache=cache)):
            continue
        for path in cec_fr._canonical_45_xy_paths(tuple(at),tuple(via.GetPosition())):
            length=sum(math.dist(a,b) for a,b in zip(path,path[1:]))/MM
            if length>float(reach_mm)+1e-9:continue
            if not all(cec_fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width/2+gap)
                    and cec_fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),
                        width,layer,gap,{code},foreign_cache=cache) for a,b in zip(path,path[1:])):
                continue
            made=[]; original={t.m_Uuid.AsString() for t in board.GetTracks()}
            try:
                for a,b in zip(path,path[1:]):
                    if a==b:continue
                    track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I(*a))
                    track.SetEnd(pcbnew.VECTOR2I(*b));track.SetWidth(width);track.SetLayer(layer)
                    track.SetNetCode(code);track.SetLocked(bool(lock));board.Add(track);made.append(track)
                proof=_existing_return(board,pad,reach_mm)
            except Exception:
                # Native insertion/proof may throw after attaching an item.
                # Keep the retained barrel and remove EVERY trial addition.
                discard_items(board,[t for t in board.GetTracks() if t.m_Uuid.AsString() not in original])
                raise
            if proof is None:
                discard_items(board,made);continue
            return dict(status='reused-ground-barrel',distance_mm=round(proof[0],6),
                via_uuid=uid,items=made,existing_barrel_unchanged=True,
                **_existing_return_topology(board,pad,via))
    return None


def _add_ground_dogbone(board, pad, *, diameter, drill, board_limits,
                        profile_name, reach_mm, lock, diagnostics,
                        foreign_cache, pofv_refusal, qualified_compact=False,
                        extended_ordinary_reach=False):
    """One bounded geometry domain; no pad/width/clearance exceptions here.

    Compact process geometry needs an actual short SMD copper owner before
    adoption. Rejected native trials are destroyed before testing another seat.
    The file-stage wrapper owns and independently revalidates generated POFV
    vias before adding their exact-object fabrication rule.
    """
    if (type(extended_ordinary_reach) is not bool or extended_ordinary_reach and
            (qualified_compact or type(reach_mm) not in (int,float) or not math.isfinite(reach_mm)
             or not 1.5<reach_mm<=3.)):
        raise ValueError('extended_ground_shortcut_is_bounded_ordinary_geometry_only')
    gnd_code = pad.GetNetCode()
    pos, layer = pad.GetPosition(), _ground_terminal_layer(pad)
    spec = _netclass(board, "GND")
    if qualified_compact:
        declared = cec_fab_profile.board_profile_name(board)
        process = cec_fab_profile.get_profile(declared) if declared else None
        valid, _reason = cec_fab_profile.pofv_dimensions(process, diameter, drill)
        if (not valid or not process or not process.get("pofv")
                or int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD)
                or cec_return_escape.smd_surface_layer(pad) is None
                or gnd_code <= 0 or pad.GetNetname() != "GND"
                or not math.isfinite(float(reach_mm))
                or not 0 < float(reach_mm) <= 1.50):
            return None, "compact ground dogbone has no qualified local process domain"
    pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
    try:
        board_min_nm = int(board.GetDesignSettings().m_TrackMinWidth)
    except Exception:                                    # noqa: BLE001
        board_min_nm = pcbnew.FromMM(0.20)
    class_width_nm = max(board_min_nm, int(spec["width"]))
    class_width = class_width_nm / MM
    # A GND dogbone is a current-return structure, not an arbitrary signal
    # escape.  The old fixed 0.30 mm ceiling made *every* dogbone violate a
    # wider GND netclass even when the full class width fit comfortably.  Try
    # the electrical-authority width first.  Only when the endpoint land is
    # genuinely narrower may the guarded search use a pad-limited local
    # neckdown; unlike the former ``pad_minor / 2`` heuristic, the fallback
    # consumes the available land width and is placed in the exact endpoint
    # exception group for independent signoff.
    endpoint_width_nm = min(
        class_width_nm,
        max(board_min_nm, pcbnew.FromMM(pad_minor)))
    stub_widths_nm = [class_width_nm]
    if endpoint_width_nm < class_width_nm:
        stub_widths_nm.append(endpoint_width_nm)
    start_radius = max(
        0.45, pad_minor / 2.0 + diameter / 2.0 + 0.20)
    radii = sorted({
        round(value, 3) for value in
        (start_radius, start_radius + 0.20, start_radius + 0.40,
         min(reach_mm, start_radius + 0.65))
        if value <= reach_mm + 1e-9})
    # The historical stencil ends at start_radius+0.65 even if the caller
    # requests a larger reach. Preserve that whole near tier exactly. Only
    # an explicit ordinary-via shortcut may search the remaining finite
    # radius bands; these are NOT immediate/POFV dogbone qualification.
    outer_radii=([r for r in (1.5,2.,2.5,3.,float(reach_mm))
        if max(radii,default=0.)<r<=reach_mm] if extended_ordinary_reach else [])
    outer_radii=sorted(set(outer_radii))
    tested_sites = 0
    rejected_seats = []
    dogbone_rejections = {
        "stub_foreign_clearance": 0,
        "stub_edge_clearance": 0,
        "via_edge_clearance": 0,
        "via_spot_clearance": 0,
        "via_pad_qualification": 0,
        "via_hole_clearance": 0,
        "stub_pair_overlap": 0,
    }
    escape_context = cec_return_escape.capture(
        board, pad, reach_mm=reach_mm, diameter_mm=diameter,
        netclass=_netclass, foreign_cache=foreign_cache)
    angles = (0, 180, 90, 270, 45, 135, 225, 315)
    if not qualified_compact:
        angles += (22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5)
    sites = [(radius, ((pos.x + math.cos(math.radians(angle))*radius*MM)/MM,
                       (pos.y + math.sin(math.radians(angle))*radius*MM)/MM))
             for radius in radii
             for angle in angles]
    sites += [(radius,((pos.x+dx*radius*MM/math.hypot(dx,dy))/MM,
                      (pos.y+dy*radius*MM/math.hypot(dx,dy))/MM))
              for radius in outer_radii
              for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))]
    for stub_width_nm in stub_widths_nm:
        ranked = cec_return_escape.ranked_sites(
            escape_context, (pos.x/MM, pos.y/MM), sites, diameter_mm=diameter,
            width_mm=stub_width_nm/MM, layer=int(layer),
            clearance_mm=max(.20, float(spec['clearance'])/MM))
        if extended_ordinary_reach:
            ranked=sorted(ranked,key=lambda row:row[0] in outer_radii)
        for radius, at_mm, escape_report in ranked:
            at = pcbnew.VECTOR2I(round(at_mm[0]*MM), round(at_mm[1]*MM))
            tested_sites += 1
            via_diagnostic = {} if diagnostics is not None else None
            checks = (
                    ("stub_foreign_clearance", cec_fr._tap_foreign_clear(
                        board, pos, at, stub_width_nm,
                        layer, pcbnew.FromMM(0.20), {gnd_code},
                        foreign_cache=foreign_cache)),
                    ("stub_edge_clearance", cec_fr._edge_leg_clear(
                        board, pos, at, stub_width_nm // 2)),
                    ("via_edge_clearance", cec_fr._edge_leg_clear(
                        board, at, at, pcbnew.FromMM(diameter) // 2)),
                    ("via_spot_clearance", cec_fr._via_spot_clear(
                        board, at, pcbnew.FromMM(diameter),
                        pcbnew.FromMM(0.20), {gnd_code},
                        drill_nm=pcbnew.FromMM(drill), net_code=gnd_code,
                        foreign_cache=foreign_cache, report=via_diagnostic)),
                    # Same-net copper is exempt from the ordinary
                    # spot-clearance guard, but a standard dogbone barrel may
                    # still graze the edge of its source pad.  That is neither
                    # a legal separated dogbone nor a fully-contained,
                    # profile-qualified POFV seat.
                    ("via_pad_qualification",
                     cec_fab_profile.via_at_pad_conflicts(
                         board, at, pcbnew.FromMM(diameter),
                         pcbnew.FromMM(drill), gnd_code,
                         pad_cache=foreign_cache)[0] is None),
                    ("via_hole_clearance", _hole_to_hole_clear(
                        board, at, drill)[0]),
                    ("stub_pair_overlap", cec_fr._tap_pair_overlap_clear(
                        board, pos, at, stub_width_nm,
                        layer, gnd_code, set())),
            )
            failed = [name for name, ok in checks if not ok]
            if failed:
                for name in failed:
                    dogbone_rejections[name] += 1
                if diagnostics is not None:
                    rejected_seats.append({
                        "at_mm": [at.x / MM, at.y / MM],
                        "radius_mm": radius,
                        "width_mm": stub_width_nm / MM,
                        "failed_checks": failed,
                        "copper_admission": via_diagnostic,
                    })
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(at)
            via.SetDrill(pcbnew.FromMM(drill))
            via.SetWidth(pcbnew.FromMM(diameter))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(gnd_code); via.SetLocked(bool(lock))
            board.Add(via)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pos); track.SetEnd(at)
            track.SetWidth(stub_width_nm)
            track.SetLayer(layer); track.SetNetCode(gnd_code)
            track.SetLocked(bool(lock)); board.Add(track)
            if qualified_compact:
                try:
                    local_ok, local_reason = cec_fab_profile.local_pofv_via_decision(
                        board, via, reach_mm=min(float(reach_mm), 1.50))
                except Exception:
                    discard_items(board, [track, via])
                    raise
                if not local_ok:
                    discard_items(board, [track, via])
                    dogbone_rejections["live_local_pofv_qualification"] = (
                        dogbone_rejections.get("live_local_pofv_qualification", 0) + 1)
                    continue
            admitted, endpoint_neckdown = _admit_link_neckdowns(
                board, [track, via], class_width_nm, persist_group=True)
            if not admitted:
                dogbone_rejections["endpoint_neckdown_qualification"] = (
                    dogbone_rejections.get("endpoint_neckdown_qualification", 0) + 1)
                continue
            return {
                    "status": ("ordinary-ground-shortcut" if extended_ordinary_reach and radius>1.5 else "dogbone"),
                    "distance_mm": round(radius, 3),
                    "via_uuid": via.m_Uuid.AsString(),
                    "items": [track, via], "fab_profile": profile_name,
                    "diameter_mm": round(diameter, 3),
                    "drill_mm": round(drill, 3),
                    "width_mm": round(stub_width_nm / MM, 3),
                    "class_width_mm": round(class_width, 3),
                    "endpoint_neckdown": endpoint_neckdown,
                    "board_limits": board_limits,
                    **({"extended_ordinary_reach_mm":float(reach_mm),
                        "immediate_return_qualified":False,
                        "new_via_is_not_a_compact_process_exception":True}
                       if extended_ordinary_reach else {}),
                    **({"endpoint_limited_local_via": True,
                        "qualified_process_exception": True,
                        "local_pofv_qualification": local_reason}
                       if qualified_compact else {}),
                    "neighbour_escape": dict(escape_report,
                        initially_blocked_ports=escape_context['initially_blocked_ports'],
                        unresolved_surface_ports=escape_context.get('unresolved_surface_ports', 0),
                        omitted_ports=escape_context['omitted_ports']),
            }, None
    if diagnostics is not None:
        # Aggregate rejection counts cannot tell placement that a clear pin
        # escape ends at a barrel blocked by a power polygon. Keep a bounded
        # set of the closest-to-legal *measured* seats and their native objects.
        unique_seats = {}
        for seat in sorted(rejected_seats, key=lambda row: (
                len(row["failed_checks"]),
                "stub_foreign_clearance" in row["failed_checks"],
                row["radius_mm"], row["at_mm"], -row["width_mm"])):
            unique_seats.setdefault(tuple(seat["at_mm"]), seat)
        seats = list(unique_seats.values())[:16]
        diagnostics.update(dogbone_candidates=seats,
            dogbone_candidates_truncated=max(0, len(unique_seats)-len(seats)))
        diagnostics.update(
            conclusion="no_legal_immediate_ground_return",
            dogbone_sites=tested_sites, dogbone_rejections=dogbone_rejections,
            search_exhausted=True)
        diagnostics.update(_ground_obstruction_evidence(diagnostics))
    return None, (
        "no legal immediate GND return: via-in-pad %s; "
        "%d dogbone sites rejected (%s)" %
        (pofv_refusal, tested_sites, ", ".join(
            "%s=%d" % pair for pair in dogbone_rejections.items()
            if pair[1])))


def _add_ground_return_pair(board, owner_pad, cap_pad, *, board_path,
                            reach_mm, lock, group_neckdowns=True, diagnostics=None,
                            pofv_geometry=None):
    """Give both local GND pads an immediate entry, sharing one when needed.

    Fine-pitch IC ground lands often cannot physically contain the board-legal
    POFV diameter and can be boxed in by adjacent pins.  When either the owner
    or capacitor pad has a legal immediate via, a short guarded same-net link
    to that via is a lower-inductance and manufacturable fallback.  Both
    independent-via and shared-entry forms remain all-or-nothing at the caller.
    """
    snapshot = _cell_trial_snapshot(board)

    def attempt(cap_first):
        order = (("cap", cap_pad), ("owner", owner_pad)) if cap_first else (
            ("owner", owner_pad), ("cap", cap_pad))
        result = {}
        errors = {}
        for name, pad in order:
            detail = {} if diagnostics is not None else None
            result[name], errors[name] = _add_ground_return(
                board, pad, board_path=board_path,
                reach_mm=reach_mm, lock=lock,
                **({"pofv_geometry": pofv_geometry} if pofv_geometry is not None else {}),
                **({"diagnostics": detail} if detail is not None else {}))
            if diagnostics is not None:
                diagnostics.setdefault("attempts", []).append({
                    "order": "capacitor-first" if cap_first else "owner-first",
                    "terminal": name, "error": errors[name], "evidence": detail})
        if diagnostics is not None:
            # Inner ordering retries also retire temporary UUIDs. Classify
            # them while still live, before rollback removes their evidence.
            provisional = {item.m_Uuid.AsString() for item in board.GetTracks()}-snapshot[0]
            _cell_blocker_provenance(diagnostics, snapshot[0], provisional)
        if errors["owner"] is None and errors["cap"] is None:
            return result["owner"], result["cap"], None, None

        link_error = None
        if (errors["owner"] is None) != (errors["cap"] is None):
            ground_link, link_error = _add_supply_link(
                board, owner_pad, cap_pad, lock=lock,
                group_neckdowns=group_neckdowns,
                link_role="shared-ground-entry", pofv_geometry=pofv_geometry)
            if link_error is None:
                # The guarded direct link is itself the missing pad's proof of
                # access to the already-qualified local via.  Re-probing for a
                # second via made success depend on the via centre also being
                # inside ``reach_mm`` (1.503 mm was rejected against 1.500 mm)
                # even though the short visible copper path had just passed
                # the stricter local-link guard.  Record the shared portal
                # explicitly instead of demanding redundant barrels.
                covered_name = ("owner" if errors["owner"] is None
                                else "cap")
                shared_name = "cap" if covered_name == "owner" else "owner"
                covered = result[covered_name] or {}
                result[shared_name] = {
                    "status": "shared-ground-entry",
                    "distance_mm": ground_link.get("length_mm"),
                    "via_uuid": covered.get("via_uuid"),
                    "shared_with": covered_name,
                    "items": [],
                }
                errors[shared_name] = None
                clean_link = {
                    key: value for key, value in ground_link.items()
                    if key != "items"}
                clean_link["status"] = "shared-ground-entry"
                clean_link["seat_order"] = (
                    "capacitor-first" if cap_first else "owner-first")
                clean_link["portal_owner"] = covered_name
                return (result["owner"], result["cap"],
                        clean_link, None)
            else:
                link_error = "guarded shared-entry link: %s" % link_error
        else:
            link_error = "neither pad has a legal immediate via"
        reasons = []
        if errors["owner"]:
            reasons.append("owner GND: %s" % errors["owner"])
        if errors["cap"]:
            reasons.append("capacitor GND: %s" % errors["cap"])
        if link_error:
            reasons.append(link_error)
        return (result.get("owner"), result.get("cap"), None,
                "; ".join(reasons))

    owner_first = attempt(False)
    if owner_first[3] is None:
        return owner_first

    # Ground entries are a coupled cell.  A greedy first via can consume the
    # only barrel seat available to the other pad even though the reverse
    # ordering closes both.  Roll back only this pair's trial copper and prove
    # the reciprocal order before declaring a geometric refusal.
    _rollback_cell_trial(board, snapshot)
    cap_first = attempt(True)
    if cap_first[3] is None:
        if cap_first[2] is None:
            cap_first = (cap_first[0], cap_first[1], {
                "status": "independent-ground-entries",
                "seat_order": "capacitor-first",
            }, None)
        return cap_first
    return (cap_first[0], cap_first[1], None,
            "owner-first failed: %s; capacitor-first failed: %s" %
            (owner_first[3], cap_first[3]))


def _report_only(value):
    """Remove live pcbnew objects from persistent/inter-process evidence.

    Generator return dictionaries use ``items`` internally for transactional
    rollback.  Those SWIG objects are neither deterministic evidence nor
    picklable, and must never cross a worker or JSON boundary.
    """
    if isinstance(value, dict):
        return {
            key: _report_only(item)
            for key, item in value.items() if key != "items"
        }
    if isinstance(value, list):
        return [_report_only(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_report_only(item) for item in value)
    return value


def _point_segment_distance_mm(point, start, end):
    px, py = point.x / MM, point.y / MM
    ax, ay = start.x / MM, start.y / MM
    bx, by = end.x / MM, end.y / MM
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segments_distance_mm(a, b, c, d):
    """Exact minimum centreline distance between two finite segments."""
    def orient(p, q, r):
        return ((q.x - p.x) * (r.y - p.y) -
                (q.y - p.y) * (r.x - p.x))

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 == 0 or o2 == 0 or (o1 < 0) != (o2 < 0)) and
            (o3 == 0 or o4 == 0 or (o3 < 0) != (o4 < 0))):
        return 0.0
    return min(
        _point_segment_distance_mm(a, c, d),
        _point_segment_distance_mm(b, c, d),
        _point_segment_distance_mm(c, a, b),
        _point_segment_distance_mm(d, a, b),
    )


def ripup_foreign_local_copper(board, *, max_assignment_mm=3.5,
                               ground_reach_mm=1.5,
                               protected_nets=(), demotable_nets=(),
                               assignment=None):
    """Clear only unlocked, non-priority copper from bypass-cell channels.

    This is used solely when continuing a previously routed seed.  Component
    geometry is unchanged; old ordinary routing is allowed to surrender the
    small supply/return neighborhood so the priority cell can be rebuilt
    first.  Locked nets, explicitly protected nets, same-cell GND/rail copper,
    and wide current trunks are never removed.  The residual router owns the
    exact named nets removed here.
    """
    assignment = assignment or cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    demotable = set(demotable_nets or ())
    protected = set(protected_nets or ()) - demotable
    protected.update(
        item.GetNetname() for item in board.GetTracks()
        if (item.IsLocked() and item.GetNetname()
            and item.GetNetname() not in demotable))
    regions = []
    for assigned in _ordered_assigned_cells(board, assignment):
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned.get("cap_ref"))
        owner = board.FindFootprintByReference(requirement.get("ref"))
        if cap is None or owner is None or requirement.get("pad") is None:
            continue
        cap_rail = next((pad for pad in cap.Pads()
                         if pad.GetNetname() == requirement.get("rail")), None)
        return_rail, cap_gnd, owner_gnds = _cell_return_pads(
            requirement, owner, cap)
        if return_rail != "GND":
            continue
        if cap_rail is None or cap_gnd is None or not owner_gnds:
            continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        regions.append({
            "owner": requirement.get("ref"),
            "cap": assigned.get("cap_ref"),
            "allowed_nets": {"GND", requirement.get("rail")},
            "ground_points": (
                owner_gnd.GetPosition(), cap_gnd.GetPosition()),
            "supply_segment": (
                requirement["pad"].GetPosition(),
                cap_rail.GetPosition()),
        })

    selected = []
    blocked = []
    ground_radius = min(2.0, max(0.9, float(ground_reach_mm) + 0.35))
    supply_radius = 0.45
    for item in list(board.GetTracks()):
        net = item.GetNetname()
        if not net:
            continue
        if (item.IsLocked() and net not in demotable) or net in protected:
            continue
        try:
            item_radius = (item.GetWidth(pcbnew.F_Cu)
                           if item.GetClass() == "PCB_VIA" else
                           item.GetWidth()) / MM / 2.0
        except Exception:                               # noqa: BLE001
            item_radius = 0.30
        hit = None
        for region in regions:
            if net in region["allowed_nets"]:
                continue
            if item.GetClass() == "PCB_VIA":
                point = item.GetPosition()
                close_ground = any(
                    math.hypot(point.x - ground.x,
                               point.y - ground.y) / MM
                    <= ground_radius + item_radius
                    for ground in region["ground_points"])
                close_supply = _point_segment_distance_mm(
                    point, *region["supply_segment"]
                ) <= supply_radius + item_radius
            else:
                start, end = item.GetStart(), item.GetEnd()
                close_ground = any(
                    _point_segment_distance_mm(ground, start, end)
                    <= ground_radius + item_radius
                    for ground in region["ground_points"])
                close_supply = _segments_distance_mm(
                    start, end, *region["supply_segment"]
                ) <= supply_radius + item_radius
            if close_ground or close_supply:
                hit = region
                break
        if hit is None:
            continue
        # A wide current trunk is placement authority, not ordinary residual
        # routing.  Report it but never silently tear it up.
        if item.GetClass() != "PCB_VIA" and item.GetWidth() >= pcbnew.FromMM(1.0):
            blocked.append({
                "uuid": item.m_Uuid.AsString(), "net": net,
                "kind": item.GetClass(), "owner": hit["owner"],
                "cap": hit["cap"], "reason": "wide_current_trunk",
            })
            continue
        selected.append((item, hit))

    removed = []
    for item, region in selected:
        removed.append({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "owner": region["owner"],
            "cap": region["cap"],
        })
        discard_items(board, [item])
    return {
        "schema": 1,
        "removed_count": len(removed),
        "removed_items": removed,
        "removed_nets": sorted({row["net"] for row in removed}),
        "protected_nets": sorted(protected),
        "demotable_nets": sorted(demotable),
        "blocked_count": len(blocked),
        "blocked_items": blocked,
        "ground_radius_mm": ground_radius,
        "supply_radius_mm": supply_radius,
    }


def ripup_foreign_ground_access_copper(board, targets, *, reach_mm=1.5,
                                        protected_nets=(),
                                        demotable_nets=()):
    """Clear bounded ordinary copper around named, proven-blocked GND pads."""
    demotable = set(demotable_nets or ())
    protected = set(protected_nets or ()) - demotable
    protected.update(
        item.GetNetname() for item in board.GetTracks()
        if (item.IsLocked() and item.GetNetname()
            and item.GetNetname() not in demotable))
    # Resolve the ENTIRE physical target inventory before selecting/removing
    # copper. FindPadByNumber is not an identity when a package has multiple
    # physical Ground lands carrying the same logical pin number.
    footprints = list(board.GetFootprints())
    pads_by_uuid = {}
    for footprint in footprints:
        for pad in footprint.Pads():
            pads_by_uuid.setdefault(pad.m_Uuid.AsString(), []).append(pad)
    points = []; seen = set()
    for target in targets or ():
        if (not isinstance(target, dict) or type(target.get('ref')) is not str
                or not target['ref'] or type(target.get('pad')) not in (str, int)
                or not str(target['pad'])):
            raise ValueError('literal_ground_ripup_target_identity_required')
        ref, number = target['ref'], str(target['pad'])
        owners = [fp for fp in footprints if fp.GetReference() == ref]
        if len(owners) != 1:
            raise ValueError('unique_ground_ripup_footprint_required')
        candidates = [p for p in owners[0].Pads() if p.GetNumber() == number]
        if 'pad_uuid' in target:
            uid = target['pad_uuid']
            if type(uid) is not str or not uid:
                raise ValueError('exact_ground_ripup_physical_uuid_required')
            candidates = [p for p in candidates if p.m_Uuid.AsString() == uid]
        elif len(candidates) != 1:
            raise ValueError('ambiguous_ground_ripup_requires_physical_pad_uuid')
        if len(candidates) != 1:
            raise ValueError('ground_ripup_uuid_ref_and_number_must_match')
        pad = candidates[0]; uid = pad.m_Uuid.AsString()
        if len(pads_by_uuid[uid]) != 1 or uid in seen or pad.GetNetname() != 'GND':
            raise ValueError('unique_actual_ground_ripup_land_required')
        seen.add(uid)
        points.append((ref, number, uid, pad.GetPosition()))

    radius = min(2.0, max(0.9, float(reach_mm) + 0.35))
    selected, blocked = [], []
    for item in list(board.GetTracks()):
        net = item.GetNetname()
        if (not net or net == "GND"
                or (item.IsLocked() and net not in demotable)
                or net in protected):
            continue
        item_radius = ((item.GetWidth(pcbnew.F_Cu)
                        if item.GetClass() == "PCB_VIA" else
                        item.GetWidth()) / MM / 2.0)
        hit = None
        for ref, number, pad_uuid, point in points:
            distance = (math.hypot(
                item.GetPosition().x - point.x,
                item.GetPosition().y - point.y) / MM
                if item.GetClass() == "PCB_VIA" else
                _point_segment_distance_mm(
                    point, item.GetStart(), item.GetEnd()))
            if distance <= radius + item_radius:
                hit = (ref, number, pad_uuid)
                break
        if hit is None:
            continue
        if (item.GetClass() != "PCB_VIA" and
                item.GetWidth() >= pcbnew.FromMM(1.0)):
            blocked.append({
                "uuid": item.m_Uuid.AsString(), "net": net,
                "kind": item.GetClass(), "ref": hit[0], "pad": hit[1],
                "pad_uuid": hit[2],
                "reason": "wide_current_trunk",
            })
            continue
        selected.append((item, hit))

    removed = []
    for item, hit in selected:
        removed.append({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "ref": hit[0], "pad": hit[1],
            "pad_uuid": hit[2],
        })
        discard_items(board, [item])
    return {
        "schema": 1, "target_count": len(points),
        "missing_targets": [], "radius_mm": radius,
        "physical_targets": [dict(ref=ref, pad=number, pad_uuid=uid)
            for ref, number, uid, _ in points],
        "removed_count": len(removed), "removed_items": removed,
        "removed_nets": sorted({row["net"] for row in removed}),
        "protected_nets": sorted(protected),
        "demotable_nets": sorted(demotable),
        "blocked_count": len(blocked), "blocked_items": blocked,
    }


def _ripup_file_worker(board_path, report_path, *, max_assignment_mm,
                        ground_reach_mm, protected_nets,
                        demotable_nets=(), ground_targets=()):
    """One-process pcbnew mutation boundary for routed-seed local rip-up."""
    board = pcbnew.LoadBoard(board_path)
    report = (ripup_foreign_ground_access_copper(
        board, ground_targets, reach_mm=ground_reach_mm,
        protected_nets=protected_nets,
        demotable_nets=demotable_nets) if ground_targets else
        ripup_foreign_local_copper(
            board, max_assignment_mm=max_assignment_mm,
            ground_reach_mm=ground_reach_mm,
            protected_nets=protected_nets,
            demotable_nets=demotable_nets))
    pcbnew.SaveBoard(board_path, board)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(report, sink, indent=2, sort_keys=True)


def _ripup_file_subprocess(board_path, *, max_assignment_mm,
                           ground_reach_mm, protected_nets,
                           demotable_nets=(), ground_targets=()):
    """Run destructive pcbnew child removal in an isolated interpreter.

    KiCad's deprecated SWIG API invalidates unrelated child proxies after a
    Remove().  The process boundary is therefore part of correctness: the
    synthesis pass always loads a fresh board object after rip-up.
    """
    serialized_targets = [json.dumps(target, sort_keys=True)
                          for target in ground_targets or ()]
    _parse_ground_ripup_targets([], serialized_targets)
    fd, report_path = tempfile.mkstemp(
        prefix="cec-decoupler-ripup-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--ripup-worker",
        "--board", os.path.abspath(board_path),
        "--report", report_path,
        "--max-assignment-mm", str(float(max_assignment_mm)),
        "--ground-reach-mm", str(float(ground_reach_mm)),
    ]
    for net in sorted(set(protected_nets or ())):
        command.extend(["--protected-net", net])
    for net in sorted(set(demotable_nets or ())):
        command.extend(["--demotable-net", net])
    for target in serialized_targets:
        command.extend([
            "--target-ground-json", target])
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=10)
        if completed.returncode:
            raise RuntimeError(
                "local rip-up worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout)[-1000:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def _ground_probe_file_worker(board_path, report_path, *, reach_mm):
    board = pcbnew.LoadBoard(board_path)
    report = synthesize_ground_plane_access_board(
        board, board_path=board_path, reach_mm=reach_mm, lock=True)
    payload = {
        "schema": 1,
        "refused": [
            {"ref": row.get("ref"), "pad": str(row.get("pad")),
             "reason": row.get("reason")}
            for row in report.get("refused") or ()],
    }
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2, sort_keys=True)


def _ground_probe_file_subprocess(board_path, *, reach_mm):
    fd, report_path = tempfile.mkstemp(
        prefix="cec-ground-access-probe-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--ground-probe-worker",
        "--board", os.path.abspath(board_path), "--report", report_path,
        "--ground-reach-mm", str(float(reach_mm)),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError(
                "ground-access probe exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout)[-1000:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def _cell_trial_snapshot(board):
    return ({item.m_Uuid.AsString() for item in board.GetTracks()},
            {group.m_Uuid.AsString(): {item.m_Uuid.AsString() for item in group.GetItems()}
             for group in board.Groups()})


def _rollback_cell_trial(board, snapshot):
    """Discard only this transaction's copper and groups, never inherited items."""
    tracks, groups = snapshot
    added = [item for item in board.GetTracks() if item.m_Uuid.AsString() not in tracks]
    discard_items(board, added)
    new_groups = [g for g in board.Groups() if g.m_Uuid.AsString() not in groups]
    for group in new_groups:
        for member in list(group.GetItems()):
            group.RemoveItem(member)
    discard_items(board, new_groups)
    if _cell_trial_snapshot(board) != snapshot:
        raise RuntimeError('local-cell rollback changed inherited copper or group membership')
    board.BuildConnectivity()
    return dict(copper=len(added), groups=len(new_groups))


def _cell_blocker_provenance(diagnostic, inherited, provisional):
    """Separate inherited locked authority from this attempt's temporary copper."""
    def visit(value):
        if isinstance(value, dict):
            uid = value.get('uuid')
            if uid in provisional:
                value['ownership_origin'] = 'tentative_cell_copper'
            elif uid in inherited:
                value['ownership_origin'] = 'inherited_copper'
            protected = value.get('protected_blocker_uuids')
            if protected is not None:
                tentative = sorted((set(protected) & provisional)
                                   | set(value.get('tentative_blocker_uuids') or ()))
                value['tentative_blocker_uuids'] = tentative
                value['protected_blocker_uuids'] = sorted(set(protected)-provisional)
                if tentative and not value['protected_blocker_uuids']:
                    value['repair_stage'] = 'coupled_cell_replan'
            for item in list(value.values()):
                visit(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                visit(item)
    visit(diagnostic)


def _construct_coupled_cell(board, owner_pad, cap_pad, owner_return_pad,
                            cap_return_pad, *, return_rail, board_path,
                            ground_reach_mm, lock, group_neckdowns):
    """Bounded joint construction, with no mutation retained from failed orders.

    Retain the original preferred supply-first solution whenever it works.
    Otherwise try return-first, then the explicitly permitted smaller local
    POFV alternative. Ordinary vias and inherited locked copper are unchanged.
    The same routine serves production and the collective feasibility audit.
    """
    profile_name = cec_fab_profile.active_profile_name(board, hint=board_path)
    profile = cec_fab_profile.get_profile(profile_name) if profile_name else None
    geometries = cec_fab_profile.local_pofv_geometry_candidates(profile) or (None,)
    snapshot = _cell_trial_snapshot(board)
    attempts = []
    for geometry in geometries:
        for order in ('supply-first', 'return-first'):
            values = dict(supply=None, return_supply=None, owner_ground=None,
                          ground=None, ground_link=None, error=None)
            diagnostic = {}
            def supply_step():
                values['supply'], values['error'] = _add_supply_link(
                    board, owner_pad, cap_pad, lock=lock, diagnostics=diagnostic,
                    group_neckdowns=group_neckdowns, pofv_geometry=geometry)
            def return_step():
                detail = {}
                if return_rail == 'GND':
                    (values['owner_ground'], values['ground'], values['ground_link'],
                     values['error']) = _add_ground_return_pair(
                        board, owner_return_pad, cap_return_pad, board_path=board_path,
                        reach_mm=ground_reach_mm, lock=lock, group_neckdowns=group_neckdowns,
                        diagnostics=detail, pofv_geometry=geometry)
                    if values['error'] is not None:
                        diagnostic['ground_return'] = detail
                else:
                    values['return_supply'], values['error'] = _add_supply_link(
                        board, owner_return_pad, cap_return_pad, lock=lock,
                        diagnostics=detail, group_neckdowns=group_neckdowns,
                        pofv_geometry=geometry)
                    if values['error'] is not None:
                        diagnostic['return_link'] = detail
            try:
                first, second = ((supply_step, return_step) if order == 'supply-first'
                                 else (return_step, supply_step))
                first()
                if values['error'] is None:
                    second()
                provisional = {item.m_Uuid.AsString() for item in board.GetTracks()}-snapshot[0]
                _cell_blocker_provenance(diagnostic, snapshot[0], provisional)
                clean = _report_only(values)
                attempt = dict(order=order, pofv_geometry_mm=geometry,
                               ok=values['error'] is None, error=values['error'],
                               diagnostic=diagnostic)
                attempts.append(attempt)
                if values['error'] is None:
                    clean['cell_search'] = dict(schema=1, selected_order=order,
                        selected_pofv_geometry_mm=geometry, attempts=attempts,
                        exhausted=False, attempt_limit=2*len(geometries))
                    return clean
            except BaseException:
                _rollback_cell_trial(board, snapshot)
                raise
            attempt['rollback'] = _rollback_cell_trial(board, snapshot)
    clean['certificate'] = dict(diagnostic, cell_search=dict(schema=1,
        selected_order=None, attempts=attempts, exhausted=True,
        attempt_limit=2*len(geometries), exhaustion_is_no_path_proof=False))
    return clean


def synthesize_board(board, *, board_path="", max_assignment_mm=3.5,
                     ground_reach_mm=1.5, lock=True, assignment=None,
                     group_neckdowns=True):
    """Lay every assigned device bypass cell in place, atomically per cell."""
    assignment = assignment or cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    generated = []
    missing = [_missing_assignment_report(row)
               for row in assignment.get("missing") or ()]
    for assigned in _ordered_assigned_cells(board, assignment):
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(requirement["ref"])
        owner_pad = requirement["pad"]
        cap_rail = next(
            (pad for pad in cap.Pads()
             if pad.GetNetname() == requirement["rail"]), None)
        return_rail, cap_gnd, owner_gnd_pads = _cell_return_pads(
            requirement, owner, cap)
        row = {
            "owner": requirement["ref"], "pin": requirement["pin"],
            "rail": requirement["rail"], "cap": assigned["cap_ref"],
            "return_rail": return_rail,
            "owner_return_pin": requirement.get("return_pin"),
            "owner_return_role_evidence": _owner_return_role_evidence(owner, return_rail),
            "placement_distance_mm": round(
                float(assigned["distance_mm"]), 3),
        }
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        if cap_rail is None or cap_gnd is None or not owner_gnd_pads:
            row.update({
                "status": "refused",
                "reason": ("assigned capacitor lacks rail/return pad or owner "
                           "has no return pin")})
            rows.append(row)
            continue
        owner_gnd = min(owner_gnd_pads, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        row["owner_ground_pin"] = owner_gnd.GetPadName()
        row["ground_pin_distance_mm"] = round(math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM, 3)
        constructed = _construct_coupled_cell(
            board, owner_pad, cap_rail, owner_gnd, cap_gnd,
            return_rail=return_rail, board_path=board_path,
            ground_reach_mm=ground_reach_mm, lock=lock,
            group_neckdowns=group_neckdowns)
        supply, return_supply = constructed['supply'], constructed['return_supply']
        owner_ground, ground = constructed['owner_ground'], constructed['ground']
        ground_link, error = constructed['ground_link'], constructed['error']
        diagnostic = constructed.get('certificate')
        if constructed.get('cell_search'):
            row['cell_search'] = constructed['cell_search']
        if error is not None:
            row.update({"status": "refused", "reason": error,
                        "certificate": diagnostic or None,
                        "supply": _report_only(supply),
                        "return_supply": _report_only(return_supply),
                        "ground_return": _report_only(ground),
                        "owner_ground_return": _report_only(owner_ground),
                        "ground_link": _report_only(ground_link)})
            rows.append(row)
            continue
        created = [
            item for item in board.GetTracks()
            if item.m_Uuid.AsString() not in before]
        generated.extend({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "owner": requirement["ref"],
            "cap": assigned["cap_ref"],
        } for item in created)
        row.update({
            "status": "owned", "supply": {
                key: value for key, value in supply.items()
                if key != "items"},
            "return_supply": ({
                key: value for key, value in return_supply.items()
                if key != "items"} if return_supply else None),
            "ground_return": ({
                key: value for key, value in ground.items()
                if key != "items"} if ground else None),
            "owner_ground_return": ({
                key: value for key, value in owner_ground.items()
                if key != "items"} if owner_ground else None),
            "ground_link": ground_link,
            "generated": len(created),
        })
        rows.append(row)
    rows.extend(missing)
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        item.get("uuid") for item in generated
        if item.get("kind") == "PCB_VIA" and item.get("net") == "GND"
        and item.get("uuid")})
    supply_nets = sorted({
        item.get("net") for item in generated
        if item.get("net") and item.get("net") != "GND"})
    return {
        "schema": 1, "ok": not refused,
        "requirements": len(assignment.get("requirements") or ()),
        "owned": sum(row.get("status") == "owned" for row in rows),
        "refused": refused, "cells": rows,
        "generated_items": generated,
        "generated_item_count": len(generated),
        "required_via_uuids": required_vias,
        "protected_nets": (["GND"] if required_vias else []),
        "partial_supply_nets": supply_nets,
    }


def audit_pre_route_cells_board(board, *, board_path="",
                                max_assignment_mm=3.5,
                                ground_reach_mm=1.5):
    """Read-only exact feasibility proof for the complete cell population.

    Cell feasibility is collective: an individually legal same-net via can
    consume the drill-spacing budget needed by the next bypass cell.  Run the
    real all-or-nothing generator in its deterministic assignment order, then
    remove every trial item.  Placement admission therefore sees precisely
    the conflicts that the production pre-route stage would encounter.
    """
    snapshot = _cell_trial_snapshot(board)
    try:
        report = synthesize_board(
            board, board_path=board_path,
            max_assignment_mm=max_assignment_mm,
            ground_reach_mm=ground_reach_mm, lock=True)
    finally:
        rollback = _rollback_cell_trial(board, snapshot)
    report = dict(report)
    report.update({"read_only": True,
                   "trial_item_count": rollback['copper'],
                   "trial_group_count": rollback['groups']})
    return report


def synthesize_ground_returns_board(
        board, *, board_path="", max_assignment_mm=3.5,
        ground_reach_mm=1.5, ground_pin_max_mm=2.5, lock=True):
    """Reserve bypass and IC ground entries before the global router.

    This is intentionally a separate priority stage.  Waiting until detailed
    routing is complete lets unrelated inner-layer copper occupy the through-
    via barrel at the only useful point.  Ground returns are laid first and the
    GND net is protected; local supply links remain for the post-route cell
    finish so shared power nets are not excluded from the global router.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows, generated = [], []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in _ordered_assigned_cells(board, assignment):
        req = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(req["ref"])
        return_rail, cap_gnd, owner_gnds = _cell_return_pads(
            req, owner, cap)
        row = {"owner": req["ref"], "pin": req["pin"],
               "rail": req["rail"], "cap": assigned["cap_ref"],
               "return_rail": return_rail,
               "owner_return_pin": req.get("return_pin"),
               "owner_return_role_evidence": _owner_return_role_evidence(owner, return_rail),
               "placement_distance_mm": round(
                   float(assigned["distance_mm"]), 3)}
        if return_rail != "GND":
            # This priority stage owns plane entries only.  The complete-cell
            # stage lays both explicit rail legs transactionally before
            # final admission; fabricating a GND via here would change the
            # device-specific circuit.
            row.update({"status": "owned", "generated": 0,
                        "deferred": "rail-to-rail local return"})
            rows.append(row)
            continue
        if cap_gnd is None or not owner_gnds:
            row.update({"status": "refused",
                        "reason": "missing capacitor or owner GND pad"})
            rows.append(row); continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        ground_gap = math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM
        row.update({"owner_ground_pin": owner_gnd.GetPadName(),
                    "ground_pin_distance_mm": round(ground_gap, 3)})
        if ground_gap > ground_pin_max_mm + 1e-9:
            row.update({"status": "refused",
                        "reason": "cap-to-owner GND gap %.3fmm exceeds %.3fmm" %
                                  (ground_gap, ground_pin_max_mm)})
            rows.append(row); continue
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        owner_return, cap_return, ground_link, error = (
            _add_ground_return_pair(
                board, owner_gnd, cap_gnd, board_path=board_path,
                reach_mm=ground_reach_mm, lock=lock))
        if error is not None:
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in before:
                    discard_items(board, [item])
            row.update({"status": "refused", "reason": error,
                        "owner_ground_return": _report_only(owner_return),
                        "ground_return": _report_only(cap_return),
                        "ground_link": _report_only(ground_link)})
            rows.append(row); continue
        created = [item for item in board.GetTracks()
                   if item.m_Uuid.AsString() not in before]
        generated.extend({"uuid": item.m_Uuid.AsString(),
                          "net": item.GetNetname(),
                          "kind": item.GetClass(),
                          "owner": req["ref"],
                          "cap": assigned["cap_ref"]}
                         for item in created)
        row.update({
            "status": "owned", "generated": len(created),
            "owner_ground_return": {
                key: value for key, value in owner_return.items()
                if key != "items"},
            "ground_return": {
                key: value for key, value in cap_return.items()
                if key != "items"},
            "ground_link": ground_link,
        })
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        entry.get("via_uuid")
        for row in rows if row.get("status") == "owned"
        for entry in (row.get("owner_ground_return"),
                      row.get("ground_return"))
        if isinstance(entry, dict) and entry.get("via_uuid")
    })
    return {"schema": 1, "ok": not refused,
            "requirements": len(assignment.get("requirements") or ()),
            "owned": len(rows) - len(refused), "refused": refused,
            "cells": rows, "generated_items": generated,
            "generated_item_count": len(generated),
            "required_via_uuids": required_vias,
            "protected_nets": (["GND"] if generated else [])}


def synthesize_ground_plane_access_board(
        board, *, board_path="", reach_mm=1.5, lock=True,
        group_neckdowns=True):
    """Give every surface GND pad a guarded portal to a dedicated plane.

    Protecting GND at net scope is valid only when every surface terminal has
    plane access.  Reserving just the bypass-cell returns and then excluding
    GND from the residual router can strand unrelated connector, protection,
    and filter pads.  Reuse the same qualified POFV-or-dogbone primitive for
    all SMD GND pads before signal routing and publish the exact via UUID set
    that the subsequent plane-fill stage must prove connected.
    """
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            try:
                surface = (int(pad.GetAttribute()) ==
                           int(pcbnew.PAD_ATTRIB_SMD))
            except Exception:                           # noqa: BLE001
                surface = False
            if surface and pad.GetNetname() == "GND":
                position = pad.GetPosition()
                pads.append((footprint.GetReference(), pad.GetPadName(),
                             position.x, position.y, pad))
    pads.sort(key=lambda row: (row[0], str(row[1]), row[2], row[3]))

    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    rows = []
    live_rows = []
    for reference, number, _x, _y, pad in pads:
        result, error = _add_ground_return(
            board, pad, board_path=board_path,
            reach_mm=reach_mm, lock=lock)
        row = {"ref": reference, "pad": str(number)}
        if error is not None:
            row.update({"status": "refused", "reason": error})
        else:
            row.update(_report_only(result))
            row["generated_item_uuids"] = sorted(
                item.m_Uuid.AsString()
                for item in (result.get("items") or ()))
        rows.append(row)
        live_rows.append((row, pad))

    # A separate barrel per land is preferred, but dense packages can make
    # that geometrically impossible.  Complete a refused terminal through the
    # nearest already-qualified GND portal when a short guarded pad-to-pad link
    # fits the same return budget.  This is the generic shared-entry pattern
    # used by professional layouts for adjacent ground lands; it remains
    # all-or-nothing and cannot turn a distant plane connection into a local
    # return by label alone.
    portals = [(row, pad) for row, pad in live_rows
               if row.get("status") != "refused" and row.get("via_uuid")]
    for row, pad in live_rows:
        if row.get("status") != "refused":
            continue
        position = pad.GetPosition()
        candidates = []
        # Candidate discovery reads the current explicit copper/fills, not a
        # global connectivity cache. Even one rebuild per terminal is wasted;
        # every lookup re-proves locality after any preceding mutation.
        for portal_row, portal_pad in portals:
            if portal_pad is pad:
                continue
            covered = _existing_return(
                board, portal_pad, reach_mm, rebuild=False)
            if covered is None:
                continue
            via_position = covered[1].GetPosition()
            via_distance = math.hypot(
                via_position.x - position.x,
                via_position.y - position.y) / MM
            if via_distance <= reach_mm + 1e-9:
                candidates.append((
                    via_distance, portal_row.get("ref") or "",
                    str(portal_row.get("pad") or ""), portal_row,
                    portal_pad))
        candidates.sort(key=lambda item: item[:3])
        independent_refusal = row.get("reason")
        shared_failures = []
        for _distance, _ref, _number, portal_row, portal_pad in candidates:
            attempt_before = {
                item.m_Uuid.AsString() for item in board.GetTracks()}
            owner_return, _portal_return, ground_link, error = (
                _add_ground_return_pair(
                    board, pad, portal_pad, board_path=board_path,
                    reach_mm=reach_mm, lock=lock,
                    group_neckdowns=group_neckdowns))
            if error is None:
                row.clear()
                row.update({
                    "ref": _pad_identity(pad).get("ref"),
                    "pad": str(pad.GetPadName()),
                    "status": "shared-ground-entry",
                    "distance_mm": owner_return.get("distance_mm"),
                    "via_uuid": owner_return.get("via_uuid"),
                    "shared_with": {
                        "ref": portal_row.get("ref"),
                        "pad": portal_row.get("pad"),
                    },
                    "ground_link": _report_only(ground_link),
                    "independent_refusal": independent_refusal,
                })
                row["generated_item_uuids"] = sorted(
                    item.m_Uuid.AsString()
                    for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in attempt_before)
                portals.append((row, pad))
                break
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in attempt_before:
                    discard_items(board, [item])
            shared_failures.append({
                "ref": portal_row.get("ref"),
                "pad": portal_row.get("pad"), "reason": error})
        if row.get("status") == "refused":
            row["shared_entry_candidates"] = len(candidates)
            row["shared_entry_failures"] = shared_failures[:8]

    generated = [
        item for item in board.GetTracks()
        if item.m_Uuid.AsString() not in before]
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        row.get("via_uuid") for row in rows
        if row.get("via_uuid")})
    return {
        "schema": 1,
        "ok": not refused,
        "pads": len(rows),
        "covered": sum(row.get("status") == "covered" for row in rows),
        "via_in_pad": sum(
            row.get("status") == "via-in-pad" for row in rows),
        "dogbones": sum(row.get("status") == "dogbone" for row in rows),
        "shared_entries": sum(
            row.get("status") == "shared-ground-entry" for row in rows),
        "refused": refused,
        "terminals": rows,
        "generated_item_count": len(generated),
        "generated_items": [{
            "uuid": item.m_Uuid.AsString(),
            "net": item.GetNetname(),
            "kind": item.GetClass(),
        } for item in generated],
        "required_via_uuids": required_vias,
        "protected_nets": (["GND"] if rows and not refused else []),
    }


def _drc_regressed_except(before, after, allowed_types=()):
    """Compare structural DRC by type while naming stage-deferred classes."""
    allowed = set(allowed_types)
    keys = set(before.drc_types) | set(after.drc_types)
    return any(
        kind not in allowed
        and after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)
        for kind in keys)


def _drc_regression(before, after, allowed_types=()):
    """Return the exact unexpected DRC delta for blocker provenance."""
    allowed = set(allowed_types)
    keys = set(before.drc_types) | set(after.drc_types)
    return {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in sorted(keys)
        if (kind not in allowed and
            after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0))
    }


def _stage_drc_regression(before, after, *, allowed_types=(),
                          generated_nets=()):
    """Return only DRC growth attributable to this generated-net stage.

    KiCad may report one of several already-overlapping violations depending
    on insertion/UUID order.  Adding many same-net vias made an unchanged
    SENSE crossing alternate between ``tracks_crossing`` and ``clearance``;
    a type-counter-only gate therefore accepted or rolled back byte-equivalent
    GND synthesis nondeterministically.  The stage still fails closed when the
    total nondeferred count grows, when a novel locus names a net this stage
    generated, or when a new locus is not attributable from available
    evidence.  A one-for-one reclassification wholly among untouched nets is
    retained as telemetry rather than mislabeled as generated geometry.
    """
    allowed = set(allowed_types)
    positive = _drc_regression(before, after, allowed)
    if not positive:
        return {}
    before_count = sum(
        int(count) for kind, count in before.drc_types.items()
        if kind not in allowed)
    after_count = sum(
        int(count) for kind, count in after.drc_types.items()
        if kind not in allowed)
    if after_count > before_count:
        return positive

    import collections
    before_loci = collections.Counter(
        (str(row.get("type") or ""), str(row.get("where") or ""))
        for row in getattr(before, "drc_loci", ())
        if str(row.get("type") or "") not in allowed)
    after_loci = collections.Counter(
        (str(row.get("type") or ""), str(row.get("where") or ""))
        for row in getattr(after, "drc_loci", ())
        if str(row.get("type") or "") not in allowed)
    novel = list((after_loci - before_loci).elements())
    positive_total = sum(positive.values())
    if len(novel) < positive_total:
        return positive
    markers = tuple("[%s]" % str(net) for net in generated_nets if net)
    for kind, where in novel:
        if not where or any(marker in where for marker in markers):
            return positive
    return {}


def _score_summary(metrics):
    summary = cec_stage_admission.snapshot(metrics)
    summary.update({
        "drc_types": dict(metrics.drc_types),
        "drc_loci": list(getattr(metrics, "drc_loci", ())),
    })
    return summary


def synthesize_ground_returns(source, destination, *, max_assignment_mm=3.5,
                              ground_reach_mm=1.5,
                              ground_pin_max_mm=2.5):
    """Transactional file wrapper for the pre-route ground-return stage."""
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    board = pcbnew.LoadBoard(destination)
    report = synthesize_ground_returns_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm,
        ground_pin_max_mm=ground_pin_max_mm, lock=True)
    pcbnew.SaveBoard(destination, board)
    after = cec_score.score(destination)
    # A reserved GND barrel is intentionally dangling until the later plane
    # fill/global-route stage connects it on an inner GND layer.  Admit only
    # that named, expected pre-route class; every geometry, clearance, short,
    # pair, or connectivity regression still rolls the transaction back.
    deferred_types = {"via_dangling"}
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets={"GND"})
    admission = cec_stage_admission.evaluate(
        before, after, allowed_new_drc_types=deferred_types)
    regression = (not report.get("ok")
                  or bool(stage_drc_regression)
                  or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = (
            "one or more complete local cells refused"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    return report


def _prune_ground_access_drc_groups(board, report, before_drc, after_drc):
    """Remove only generated terminal groups named by a new exact DRC.

    Board-wide GND access is a collection of independent local portals, not
    one indivisible route.  The historical file transaction discarded every
    legal portal when one generated dogbone touched a protected pour.  Decode
    the UUID-backed DRC identities and roll back the complete terminal group
    (via plus its incident stub/link) for each implicated generated item.

    Existing-source DRC is debt-neutral here: only identities absent from the
    input artifact can reject a generated group.  Any unattributed new fault
    remains for the wrapper's full-board fail-closed gate and therefore can
    never be hidden by this selective admission.
    """
    import cec_certificate_repair

    before_identities = set(
        cec_certificate_repair._structural_drc_identities(before_drc))
    after_identities = set(
        cec_certificate_repair._structural_drc_identities(after_drc))
    new_identities = sorted(after_identities - before_identities)
    generated = {
        str(item.get("uuid") or "")
        for item in (report.get("generated_items") or ())
        if item.get("uuid")
    }
    implicated = set()
    kinds_by_uuid = {}
    for identity in new_identities:
        try:
            row = json.loads(identity)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, list) or len(row) < 3 or row[1] != "uuid":
            continue
        kind = str(row[0] or "")
        for uid in row[2] if isinstance(row[2], list) else ():
            uid = str(uid or "")
            if uid in generated:
                implicated.add(uid)
                kinds_by_uuid.setdefault(uid, set()).add(kind)

    rejected_groups = []
    remove_uuids = set()
    for terminal in report.get("terminals") or ():
        group = {
            str(uid) for uid in (terminal.get("generated_item_uuids") or ())
            if uid
        }
        hits = sorted(group & implicated)
        if not hits:
            continue
        remove_uuids.update(group)
        kinds = sorted({kind for uid in hits
                        for kind in kinds_by_uuid.get(uid, ())})
        rejected_groups.append({
            "ref": str(terminal.get("ref") or ""),
            "pad": str(terminal.get("pad") or ""),
            "generated_item_uuids": sorted(group),
            "implicated_item_uuids": hits,
            "drc_types": kinds,
        })
        terminal["pre_admission_status"] = terminal.get("status")
        terminal["status"] = "refused"
        terminal["reason"] = (
            "terminal-local GND access rejected by exact full-board DRC: %s"
            % (", ".join(kinds) or "unclassified structural fault"))
        terminal["generated_item_uuids"] = []

    # Defensive fallback for a producer bug which emitted a generated UUID
    # without attaching it to its terminal row.  Remove that primitive too;
    # the still-live new identity will make the wrapper roll back the entire
    # transaction if a dependent item was not attributable.
    remove_uuids.update(implicated)
    for item in list(board.GetTracks()):
        if item.m_Uuid.AsString() in remove_uuids:
            discard_items(board, [item])

    live_route = {
        item.m_Uuid.AsString(): item for item in board.GetTracks()
    }
    live = {
        item.m_Uuid.AsString(): item for item in board.GetTracks()
        if item.m_Uuid.AsString() in generated
    }
    report["generated_items"] = [{
        "uuid": uid, "net": item.GetNetname(), "kind": item.GetClass(),
    } for uid, item in sorted(live.items())]
    report["generated_item_count"] = len(live)
    report["required_via_uuids"] = sorted({
        str(row.get("via_uuid"))
        for row in (report.get("terminals") or ())
        if row.get("status") != "refused"
        and str(row.get("via_uuid") or "") in live_route
    })
    refused = [row for row in (report.get("terminals") or ())
               if row.get("status") == "refused"]
    report["refused"] = refused
    report["ok"] = not refused
    report["protected_nets"] = (["GND"] if report["ok"] else [])
    report["exact_group_admission"] = {
        "schema": 1,
        "before_structural_drc_identities": sorted(before_identities),
        "after_structural_drc_identities": sorted(after_identities),
        "new_structural_drc_identities": new_identities,
        "implicated_generated_item_uuids": sorted(implicated),
        "removed_generated_item_uuids": sorted(remove_uuids),
        "rejected_terminal_groups": rejected_groups,
    }
    return report


def synthesize_ground_plane_access(source, destination, *, reach_mm=1.5,
                                   repair_existing_copper=False,
                                   protected_nets=(), demotable_nets=()):
    """Transactionally reserve complete SMD GND access before net protection."""
    import cec_certificate_repair
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    drc_dir = tempfile.mkdtemp(prefix="cec-ground-access-drc-")
    before_drc_path = os.path.join(drc_dir, "before.json")
    after_drc_path = os.path.join(drc_dir, "after-bulk.json")
    final_drc_path = os.path.join(drc_dir, "after-admission.json")
    before_drc = cec_certificate_repair._run_drc(
        source, before_drc_path)
    before = cec_score.score(source, drc_json=before_drc_path)
    probe = ({"schema": 1, "skipped": "not_requested", "refused": []}
             if not repair_existing_copper else
             _ground_probe_file_subprocess(
                 destination, reach_mm=reach_mm))
    ripup = ({"schema": 1, "skipped": "not_requested",
              "removed_count": 0, "removed_nets": []}
             if not probe.get("refused") else
             _ripup_file_subprocess(
                 destination, max_assignment_mm=3.5,
                 ground_reach_mm=reach_mm,
                 protected_nets=protected_nets,
                 demotable_nets=demotable_nets,
                 ground_targets=probe["refused"]))
    board = pcbnew.LoadBoard(destination)
    report = synthesize_ground_plane_access_board(
        board, board_path=destination, reach_mm=reach_mm, lock=True)
    report["endpoint_neckdown_reconcile"] = \
        cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=cec_fr._project_netclass_resolver(
                destination))
    pcbnew.SaveBoard(destination, board)
    rule_report = report
    recovered = report["endpoint_neckdown_reconcile"]
    if recovered.get("min_width_mm") is not None:
        rule_report = {**report, "endpoint_neckdown": recovered}
    report["endpoint_neckdown_rule"] = \
        _ensure_endpoint_neckdown_rule(destination, rule_report)
    after_drc = cec_certificate_repair._run_drc(
        destination, after_drc_path)
    _prune_ground_access_drc_groups(
        board, report, before_drc, after_drc)
    pcbnew.SaveBoard(destination, board)
    # The local PI transaction can add through vias on any input, not only an
    # already-routed seed.  A saved KiCad zone retains its previous fill until
    # it is explicitly refilled; scoring newly-added foreign-net vias against
    # that stale fill reports false via-to-plane clearance/hole-clearance
    # regressions.  Refill after every successful cell mutation so placement,
    # fresh production, and routed-repair paths all admit the same physical
    # board state.
    if report.get("ok") and report.get("generated_item_count"):
        try:
            cec_fr.refill_zones(destination)
        except Exception as exc:                         # noqa: BLE001
            report["zone_refill_error"] = "%s: %s" % (
                type(exc).__name__, exc)
            report["ok"] = False
    final_drc = cec_certificate_repair._run_drc(
        destination, final_drc_path)
    after = cec_score.score(destination, drc_json=final_drc_path)
    deferred_types = {"via_dangling"}
    repair_deferred_opens = bool(
        repair_existing_copper and ripup.get("removed_count"))
    if repair_deferred_opens:
        deferred_types.add("track_dangling")
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets={"GND"})
    exact_new_identities = sorted(
        set(cec_certificate_repair._structural_drc_identities(final_drc))
        - set(cec_certificate_repair._structural_drc_identities(before_drc)))
    partial_admission = bool(
        not report.get("ok") and report.get("generated_item_count")
        and not exact_new_identities)
    report["partial_admission"] = partial_admission
    allowed_open_nets = set(ripup.get("removed_nets") or ())
    admission = cec_stage_admission.evaluate(
        before, after,
        allow_unconnected_growth=repair_deferred_opens,
        allowed_new_unconnected_nets=allowed_open_nets,
        allowed_new_drc_types=deferred_types)
    regression = (
        (not report.get("ok") and not partial_admission)
        or bool(stage_drc_regression)
        or bool(exact_new_identities)
        or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
        "priority_complete": bool(report.get("ok") and not regression),
        "repair_probe": probe,
        "local_ripup": ripup,
        "deferred_ripup_opens": bool(
            repair_deferred_opens and
            after.unconnected > before.unconnected),
        "before_structural_drc_identities": sorted(
            cec_certificate_repair._structural_drc_identities(before_drc)),
        "after_structural_drc_identities": sorted(
            cec_certificate_repair._structural_drc_identities(final_drc)),
        "new_structural_drc_identities": exact_new_identities,
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = (
            "one or more SMD GND terminals lack guarded plane access"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    shutil.rmtree(drc_dir, ignore_errors=True)
    return report


def _retain_rejected_cell_family(destination, report):
    """Bind failed measurements to their actual child, never to the rollback."""
    rejected = os.path.splitext(destination)[0] + "-rejected.kicad_pcb"
    try:
        shutil.copy2(destination, rejected)
        cec_fr.copy_project_sidecars(destination, rejected)
        with open(rejected, "rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report["rejected_artifact"] = {
            "board": os.path.abspath(rejected), "sha256": digest,
            "scope": "rejected-local-cell-diagnostic",
            "release_authority": False, "checkpoint_authority": False,
            "score": report["after"],
            "zones_refilled": (report.get("zone_refill") or {}).get("ok") is True}
    except (OSError, ValueError) as exc:
        report["rejected_artifact_error"] = "%s: %s" % (
            type(exc).__name__, exc)


def synthesize_pre_route(source, destination, *, max_assignment_mm=3.5,
                         ground_reach_mm=1.5,
                         ground_pin_max_mm=2.5,
                         repair_existing_copper=False,
                         protected_nets=(), demotable_nets=()):
    """Transactionally own complete local bypass cells before global routing.

    Supply links and both immediate GND entries are local, topology-critical
    copper.  Deferring the rail side until after the broad router allowed
    ordinary routes to occupy the only guarded launch, producing failures that
    no amount of final-wave effort could repair.  This wrapper admits the
    complete cell early while allowing only the explicitly temporary dangling
    GND-via DRC class; the following dedicated-plane stage must consume those
    exact via UUIDs.
    """
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    ripup = ({"schema": 1, "skipped": "not_requested",
              "removed_count": 0, "removed_nets": []}
             if not repair_existing_copper else
             _ripup_file_subprocess(
                 destination, max_assignment_mm=max_assignment_mm,
                 ground_reach_mm=ground_reach_mm,
                 protected_nets=protected_nets,
                 demotable_nets=demotable_nets))
    board = pcbnew.LoadBoard(destination)
    report = synthesize_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True)
    # Local PI synthesis may legitimately choose a filled/capped dogbone that
    # is smaller than the board-wide via minimum.  The geometry is legal only
    # under the selected fab profile and only for the exact generated barrel.
    # Establish that object ownership before the transaction's DRC admission;
    # deferring it to a later router phase made a valid cell roll itself back.
    _generated_via_ids = {
        str(item.get("uuid"))
        for item in (report.get("generated_items") or ())
        if item.get("kind") == "PCB_VIA" and item.get("uuid")}
    _generated_vias = [
        item for item in board.GetTracks()
        if item.GetClass() == "PCB_VIA"
        and item.m_Uuid.AsString() in _generated_via_ids]
    _local_pofv = cec_fr.group_local_pofv_signal_vias(
        board, _generated_vias)
    if _local_pofv:
        report["local_pofv_signal_vias"] = _local_pofv
    report["endpoint_neckdown_reconcile"] = \
        cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=cec_fr._project_netclass_resolver(
                destination))
    pcbnew.SaveBoard(destination, board)
    rule_report = report
    recovered = report["endpoint_neckdown_reconcile"]
    if recovered.get("min_width_mm") is not None:
        rule_report = {**report, "endpoint_neckdown": recovered}
    report["endpoint_neckdown_rule"] = \
        _ensure_endpoint_neckdown_rule(destination, rule_report)
    report["pofv_rule"] = cec_fr.ensure_local_pofv_signal_via_rule(
        destination, report)
    # Fresh placements and routed seeds have the same saved-zone lifecycle:
    # every generated PI via must be incorporated into a new zone fill before
    # exact DRC admission.  Conditioning this on local rip-up mode left fresh
    # production boards scored against stale plane copper.
    # A partially refused trial also needs fresh fill for truthful failure
    # evidence. Its incomplete cell set still cannot pass stage admission.
    if report.get("generated_item_count"):
        try:
            cec_fr.refill_zones(destination)
            report["zone_refill"] = {"attempted": True, "ok": True}
        except Exception as exc:                         # noqa: BLE001
            report["zone_refill_error"] = "%s: %s" % (
                type(exc).__name__, exc)
            report["zone_refill"] = {
                "attempted": True, "ok": False,
                "error": report["zone_refill_error"]}
            report["ok"] = False
    after = cec_score.score(destination)
    repair_deferred_opens = bool(
        repair_existing_copper and ripup.get("removed_count"))
    deferred_types = {"via_dangling"}
    if repair_deferred_opens:
        # The local transaction intentionally tears up ordinary residual nets
        # so priority power-integrity cells can own their escape first.  These
        # exact named nets are handed to the immediately following router;
        # dangling fragments are therefore stage-local, never release waivers.
        deferred_types.add("track_dangling")
    generated_nets = {
        str(item.get("net")) for item in report.get("generated_items", ())
        if item.get("net")}
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets=generated_nets)
    allowed_open_nets = set(ripup.get("removed_nets") or ())
    admission = cec_stage_admission.evaluate(
        before, after,
        allow_unconnected_growth=repair_deferred_opens,
        allowed_new_unconnected_nets=allowed_open_nets,
        allowed_new_drc_types=deferred_types)
    regression = (not report.get("ok")
                  or bool(stage_drc_regression)
                  or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
        "priority_complete": bool(report.get("ok") and not regression),
        "ground_pin_max_mm": float(ground_pin_max_mm),
        "local_ripup": ripup,
        "deferred_ripup_opens": bool(
            repair_deferred_opens and
            after.unconnected > before.unconnected),
    })
    if regression:
        # Retain the measured family before restoring the working parent.
        # This diagnostic has no checkpoint or release authority.
        _retain_rejected_cell_family(destination, report)
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["priority_complete"] = False
        report["reason"] = (
            "one or more complete local cells refused"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    return report


def audit_board(board, *, board_path="", max_assignment_mm=3.5,
                ground_reach_mm=1.5, ground_pin_max_mm=2.5,
                include_return_topology=False):
    """Measure the completed IC-pin/cap/ground-return cell on final copper."""
    if type(include_return_topology) is not bool:
        raise ValueError('explicit_saved_return_topology_observation_required')
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in _ordered_assigned_cells(board, assignment):
        req = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(req["ref"])
        cap_rail = next((pad for pad in cap.Pads()
                         if pad.GetNetname() == req["rail"]), None)
        return_rail, cap_gnd, owner_gnds = _cell_return_pads(
            req, owner, cap)
        row = {"owner": req["ref"], "pin": req["pin"],
               "rail": req["rail"], "cap": assigned["cap_ref"],
               "return_rail": return_rail,
               "owner_return_pin": req.get("return_pin"),
               "owner_return_role_evidence": _owner_return_role_evidence(owner, return_rail),
               "placement_distance_mm": round(
                   float(assigned["distance_mm"]), 3)}
        if include_return_topology:
            row['source_requirement_id'] = req['id']
        if cap_rail is None or cap_gnd is None or not owner_gnds:
            row.update({"status": "refused",
                        "reason": "missing rail/return pad geometry"})
            rows.append(row); continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        direct = math.hypot(
            req["pad"].GetPosition().x - cap_rail.GetPosition().x,
            req["pad"].GetPosition().y - cap_rail.GetPosition().y) / MM
        supply_path = _shortest_track_path_mm(board, req["pad"], cap_rail)
        supply_spec = _netclass(board, req["rail"])
        supply_limit = _local_supply_limit_mm(
            direct, float(supply_spec["width"]) / MM,
            max(pcbnew.FromMM(0.20),
                int(supply_spec["clearance"])) / MM)
        return_gap = math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM
        reasons = []
        reason_details = []
        def refuse(code, message, severity=1):
            # Independent physical faults must retain independent identities.
            # A repaired return must not rename a still-missing supply path.
            reasons.append(message)
            reason_details.append(dict(code=code,message=message,severity=severity))
        if supply_path is None:
            refuse('local_supply_missing',"no explicit local supply copper")
        elif supply_path > supply_limit + 1e-9:
            refuse('local_supply_length_excess',
                "supply copper %.3fmm exceeds local limit %.3fmm" %
                (supply_path,supply_limit),supply_path-supply_limit)
        cap_return = owner_return = cap_shared = owner_shared = None
        return_path = return_limit = None
        if return_rail == "GND":
            cap_return = _existing_return(board, cap_gnd, ground_reach_mm,allow_native_track_body=True)
            owner_return = _existing_return(
                board, owner_gnd, ground_reach_mm,allow_native_track_body=True)
            cap_shared = (None if cap_return is not None else
                          _shared_ground_return(
                              board, cap_gnd, owner_gnd, ground_reach_mm))
            owner_shared = (None if owner_return is not None else
                            _shared_ground_return(
                                board, owner_gnd, cap_gnd,
                                ground_reach_mm))
            if cap_return is None and cap_shared is None:
                refuse('capacitor_ground_return_missing',
                    "capacitor GND has no connected via within %.2fmm" %
                    ground_reach_mm)
            if owner_return is None and owner_shared is None:
                refuse('owner_ground_return_missing',
                    "owner GND pin has no connected via within %.2fmm" %
                    ground_reach_mm)
            if return_gap > ground_pin_max_mm + 1e-9:
                refuse('owner_cap_ground_gap_excess',
                    "cap-to-owner GND gap %.3fmm exceeds %.3fmm" %
                    (return_gap, ground_pin_max_mm),return_gap-ground_pin_max_mm)
        else:
            return_direct = return_gap
            return_path = _shortest_track_path_mm(
                board, owner_gnd, cap_gnd)
            return_spec = _netclass(board, return_rail)
            return_limit = _local_supply_limit_mm(
                return_direct, float(return_spec["width"]) / MM,
                max(pcbnew.FromMM(0.20),
                    int(return_spec["clearance"])) / MM)
            if return_path is None:
                refuse('local_return_missing',
                    "no explicit local %s return copper" % return_rail)
            elif return_path > return_limit + 1e-9:
                refuse('local_return_length_excess',
                    "%s return copper %.3fmm exceeds local limit %.3fmm" %
                    (return_rail, return_path, return_limit),return_path-return_limit)
        row.update({
            "status": "owned" if not reasons else "refused",
            "reason": "; ".join(reasons) if reasons else None,
            "reason_details": reason_details,
            "supply_path_mm": (round(supply_path, 3)
                               if supply_path is not None else None),
            "supply_local_limit_mm": round(supply_limit, 3),
            "return_pin_distance_mm": round(return_gap, 3),
            "ground_pin_distance_mm": (round(return_gap, 3)
                                       if return_rail == "GND" else None),
            "owner_ground_pin": (owner_gnd.GetPadName()
                                 if return_rail == "GND" else None),
            "owner_return_pin": owner_gnd.GetPadName(),
            "return_path_mm": (round(return_path, 3)
                               if return_path is not None else None),
            "return_local_limit_mm": (round(return_limit, 3)
                                      if return_limit is not None else None),
            "cap_ground_return_mm": (round(cap_return[0], 3)
                                     if cap_return else
                                     (cap_shared.get("path_mm")
                                      if cap_shared else None)),
            "owner_ground_return_mm": (round(owner_return[0], 3)
                                       if owner_return else
                                       (owner_shared.get("path_mm")
                                        if owner_shared else None)),
            "cap_ground_return_status": ((
                "immediate-via" if cap_return else
                ("shared-ground-entry" if cap_shared else "missing"))
                if return_rail == "GND" else None),
            "owner_ground_return_status": ((
                "immediate-via" if owner_return else
                ("shared-ground-entry" if owner_shared else "missing"))
                if return_rail == "GND" else None),
            "cap_ground_return_evidence": cap_shared,
            "owner_ground_return_evidence": owner_shared,
        })
        if include_return_topology:
            row.update(supply=dict(status='observed-saved-local-supply',
                path_mm=supply_path, local_limit_mm=supply_limit,
                current_or_fabrication_qualified=False),
                ground_return=_routed_return_evidence(board, cap_gnd, cap_return),
                owner_ground_return=_routed_return_evidence(board, owner_gnd, owner_return),
                actual_saved_copper_only=True)
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    return {"schema": 1, "ok": not refused,
            "requirements": len(assignment.get("requirements") or ()),
            "owned": len(rows) - len(refused), "refused": refused,
            "cells": rows, "ground_reach_mm": ground_reach_mm,
            "ground_pin_max_mm": ground_pin_max_mm}


def synthesize(source, destination, *, max_assignment_mm=3.5,
               ground_reach_mm=1.5, ground_pin_max_mm=2.5):
    """Apply the cell finish transactionally against full-board signoff metrics."""
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    board = pcbnew.LoadBoard(destination)
    report = synthesize_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True)
    _generated_via_ids = {
        str(item.get("uuid"))
        for item in (report.get("generated_items") or ())
        if item.get("kind") == "PCB_VIA" and item.get("uuid")}
    _generated_vias = [
        item for item in board.GetTracks()
        if item.GetClass() == "PCB_VIA"
        and item.m_Uuid.AsString() in _generated_via_ids]
    _local_pofv = cec_fr.group_local_pofv_signal_vias(
        board, _generated_vias)
    if _local_pofv:
        report["local_pofv_signal_vias"] = _local_pofv
    report["endpoint_neckdown_reconcile"] = \
        cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=cec_fr._project_netclass_resolver(
                destination))
    pcbnew.SaveBoard(destination, board)
    rule_report = report
    recovered = report["endpoint_neckdown_reconcile"]
    if recovered.get("min_width_mm") is not None:
        rule_report = {**report, "endpoint_neckdown": recovered}
    report["endpoint_neckdown_rule"] = \
        _ensure_endpoint_neckdown_rule(destination, rule_report)
    report["pofv_rule"] = cec_fr.ensure_local_pofv_signal_via_rule(
        destination, report)
    try:
        cec_fr.refill_zones(destination)
    except Exception as error:                            # noqa: BLE001
        report["refill_error"] = "%s: %s" % (type(error).__name__, error)
    after = cec_score.score(destination)
    audit = audit_board(
        pcbnew.LoadBoard(destination), board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm,
        ground_pin_max_mm=ground_pin_max_mm)
    admission = cec_stage_admission.evaluate(before, after)
    regression = not admission["accepted"]
    report.update({
        "before": admission["before"],
        "after": admission["after"],
        "admission": admission,
        "audit": audit, "rolled_back": bool(regression),
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = admission["decision"]
    else:
        report["ok"] = bool(report.get("ok") and audit.get("ok"))
    return report


def _parse_ground_ripup_targets(legacy_tokens, json_tokens):
    """Transport physical identities without selecting a native land here."""
    targets = []
    for token in legacy_tokens:
        if type(token) is not str or ':' not in token:
            raise ValueError('--target-ground requires REF:PAD')
        ref, pad = token.rsplit(':', 1)
        if not ref or not pad:
            raise ValueError('--target-ground requires nonempty REF:PAD')
        targets.append(dict(ref=ref, pad=pad))
    for token in json_tokens:
        target = json.loads(token)
        if (not isinstance(target, dict) or type(target.get('ref')) is not str
                or not target['ref'] or type(target.get('pad')) not in (str, int)
                or not str(target['pad']) or 'pad_uuid' in target
                and (type(target['pad_uuid']) is not str or not target['pad_uuid'])):
            raise ValueError('--target-ground-json requires literal ref/pad[/pad_uuid]')
        targets.append(target)
    return targets


def _main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ripup-worker", action="store_true")
    parser.add_argument("--ground-probe-worker", action="store_true")
    parser.add_argument("--reservation-worker", action="store_true")
    parser.add_argument("--board")
    parser.add_argument("--report")
    parser.add_argument("--max-assignment-mm", type=float, default=3.5)
    parser.add_argument("--ground-reach-mm", type=float, default=1.5)
    parser.add_argument("--protected-net", action="append", default=[])
    parser.add_argument("--demotable-net", action="append", default=[])
    parser.add_argument("--target-ground", action="append", default=[])
    parser.add_argument("--target-ground-json", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.board or not args.report:
        parser.error("private worker requires --board --report")
    if args.reservation_worker:
        _reservation_file_worker(
            args.board, args.report,
            max_assignment_mm=args.max_assignment_mm,
            ground_reach_mm=args.ground_reach_mm)
    elif args.ground_probe_worker:
        _ground_probe_file_worker(
            args.board, args.report, reach_mm=args.ground_reach_mm)
    elif args.ripup_worker:
        try:
            targets = _parse_ground_ripup_targets(args.target_ground, args.target_ground_json)
        except (ValueError, TypeError) as exc:
            parser.error(str(exc))
        _ripup_file_worker(
            args.board, args.report,
            max_assignment_mm=args.max_assignment_mm,
            ground_reach_mm=args.ground_reach_mm,
            protected_nets=args.protected_net,
            demotable_nets=args.demotable_net,
            ground_targets=targets)
    else:
        parser.error("private worker mode is required")
    # pcbnew SWIG may dereference invalidated child proxies during interpreter
    # teardown after Remove().  All durable outputs are already closed; bypass
    # Python finalizers at this private process boundary.
    os._exit(0)


if __name__ == "__main__":
    _main()
