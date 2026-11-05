"""One saved-family, private PTH pair-return proposal; never promotion/release.

The existing plated-terminal constructor owns placement and its ordinary
netclass via geometry. This wrapper owns bounded execution and independent
saved/refilled admission. No signal, pad, power fill, or retained via may move.
Only explicitly listed GND vias and native-derived GND fill may be added.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import cec_force_current as force
import cec_kelvin_branch_repair as family

SCOPE = "private_pth_pair_ground_return_addition_not_release"
MAX_TERMINALS = 8
MAX_SITES = 4096
MAX_GROUND_ITEMS = 512
MAX_ADDED_RETURNS = 2 * MAX_TERMINALS
RETURN_REACH_MM = 1.5
# The unchanged constructor tests five radii (0.90..1.50, step .15) at 16
# angles for each single plated terminal. A complete code closure binds this
# conservative preflight bound; no call is made when the caller lacks it.
SITES_PER_TERMINAL = 80


class Refusal(RuntimeError):
    pass


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise Refusal("pth_return_deadline_exhausted")


def _uuid(item):
    return item.m_Uuid.AsString()


def _via(item, board):
    return dict(uuid=_uuid(item), kind=item.GetClass(), net=item.GetNetname(),
        at_nm=list(item.GetPosition()), via_type=int(item.GetViaType()),
        drill_nm=int(item.GetDrillValue()), locked=bool(item.IsLocked()),
        layers=[int(item.TopLayer()),int(item.BottomLayer())],
        widths_nm={str(int(layer)):int(item.GetWidth(layer))
                   for layer in board.GetEnabledLayers().CuStack()})


def _pair_row(summary, pair):
    matches = [r for r in summary.get("pairs",[]) if
               (r.get("kind"),r.get("p"),r.get("n")) == (pair["kind"],pair["p"],pair["n"])]
    if summary.get("applicable") is not True or len(matches) != 1:
        raise Refusal("complete_physical_pair_evidence_required")
    return matches[0]


def _ground_terminals(board, deadline):
    """Complete source-retained physical inventory, never a net-name waiver."""
    import cec_force_sense_evidence as sense
    import cec_kelvin_copper_cut as copper
    result, count = [], 0
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            _tick(deadline)
            count += 1
            if count > copper.MAX_ITEMS:
                raise Refusal("ground_terminal_inventory_budget_exhausted")
            if pad.GetNetname() == "GND":
                result.append(sense._pad_identity(pad))
    if (not result or len(result) > MAX_GROUND_ITEMS
            or len({row["uuid"] for row in result}) != len(result)):
        raise Refusal("complete_retained_physical_ground_terminal_inventory_required")
    return sorted(result,key=lambda row:row["uuid"])


def _select(board, source, net, max_sites, deadline):
    import pcbnew
    import cec_constraints as constraints
    import cec_fab_profile as fab
    import cec_precision_route as precision
    import cec_force_sense_evidence as sense
    import cec_pth_pair_returns as returns
    _tick(deadline)
    pairs = [p for p in precision.derive_coupled_pairs(str(source),board=board)
             if net in (p["p"],p["n"])]
    if len(pairs) != 1:
        raise Refusal("unique_complete_coupled_pair_required")
    pair = pairs[0]
    summary = constraints.high_speed_pair_summary(str(source),board=board)
    row = _pair_row(summary,pair)
    if (not row.get("violations") or any(not v.startswith("filled adjacent-GND coverage ")
                                        for v in row["violations"])):
        raise Refusal("isolated_reference_coverage_defect_required")
    profile_name = fab.active_profile_name(board,hint=str(source))
    profile = fab.get_profile(profile_name) if profile_name else None
    if not profile:
        raise Refusal("declared_reference_profile_required")
    roles = dict(zip(fab.COPPER_LAYERS,profile["roles"]))
    references = []
    for signal in row["layers"]:
        i = fab.COPPER_LAYERS.index(signal)
        reference = next((fab.COPPER_LAYERS[j] for j in (i-1,i+1)
                          if 0 <= j < len(fab.COPPER_LAYERS)
                          and roles.get(fab.COPPER_LAYERS[j]) == "GND"),None)
        if "SIG" not in roles.get(signal,"") or reference is None:
            raise Refusal("used_signal_layer_lacks_declared_ground_reference")
        references.append(dict(signal=int(board.GetLayerID(signal)),
                               reference=int(board.GetLayerID(reference))))
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() in (pair["p"],pair["n"]) and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    if not 1 <= len(pads) <= MAX_TERMINALS or len({_uuid(p) for p in pads}) != len(pads):
        raise Refusal("bounded_unique_plated_terminal_inventory_required")
    if any(not p.HasHole() for p in pads):
        raise Refusal("plated_terminal_requires_native_hole")
    site_bound = SITES_PER_TERMINAL*len(pads)
    if site_bound > max_sites:
        raise Refusal("pth_return_site_budget_insufficient")
    # The added conductor is GND. Signal-pair sizing is not its netclass,
    # fabrication authority, or permission for a local compact exception.
    ground = returns.ground_return_contract(board)
    _tick(deadline)
    return dict(pair=pair, profile=profile_name, references=references,
        terminals=sorted((sense._pad_identity(p) for p in pads),key=lambda p:p["uuid"]),
        retained_ground_terminals=_ground_terminals(board,deadline),
        ground_return_contract=ground,
        via_diameter_nm=ground["diameter_nm"],via_drill_nm=ground["drill_nm"],
        via_limits=ground["board_limits_mm"],clearance_nm=math.ceil(precision._pair_clearance(
            board,pair,ground["clearance_nm"]/1e6)*1e6),
        return_reach_mm=RETURN_REACH_MM,constructor_site_upper_bound=site_bound),summary


def _ground_fills(path):
    """Full native serializations; only filled_polygon is derived GND data."""
    import pcbnew
    import cec_copper_echo as sexpr
    board = pcbnew.LoadBoard(str(path))
    ground = {_uuid(z) for z in board.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()}
    root = sexpr._parse(sexpr._TOKEN.findall(Path(path).read_text()))
    result = {}
    for node in root[1:]:
        if not isinstance(node,list) or not node or node[0] != "zone":
            continue
        fields = {c[0]:c for c in node[1:] if isinstance(c,list) and c}
        uid = fields.get("uuid",[None,None])[1]
        uid = uid.strip('"') if isinstance(uid,str) else None
        if uid not in ground:
            continue
        fill = [c for c in node[1:] if isinstance(c,list) and c and c[0] == "filled_polygon"]
        definition = [c for c in node if not (isinstance(c,list) and c and c[0] == "filled_polygon")]
        result[uid] = dict(definition=sexpr._freeze(definition),
            fill_sha256=hashlib.sha256(repr(sexpr._freeze(fill)).encode()).hexdigest())
    if set(result) != ground:
        raise Refusal("ground_zone_serialization_identity_unavailable")
    return result


def preservation(source, candidate, ledger, *, board_hint, allow_ground_refill=False):
    """Independent exact retained-object check, not permission to edit a fill."""
    import pcbnew
    old,fixed = force._preservation_snapshot(source)
    new,new_fixed = force._preservation_snapshot(candidate)
    old_ground,new_ground = _ground_fills(source),_ground_fills(candidate)
    expected = {v["uuid"] for v in ledger.get("added_vias",[])}
    actual = set(new)-set(old)
    errors = []
    if not expected or len(expected) != len(ledger.get("added_vias",[])) or actual != expected:
        errors.append("added_via_uuid_ledger_disagrees_with_saved_delta")
    if set(old)-set(new):
        errors.append("retained_item_removed")
    changed_fills = []
    for uid in old.keys() & new.keys():
        if old[uid] == new[uid]:
            continue
        if (allow_ground_refill and uid in old_ground and uid in new_ground
                and old_ground[uid]["definition"] == new_ground[uid]["definition"]):
            changed_fills.append(dict(uuid=uid,before_sha256=old_ground[uid]["fill_sha256"],
                                      after_sha256=new_ground[uid]["fill_sha256"]))
        else:
            errors.append("retained_geometry_or_protected_fill_changed")
    if fixed != new_fixed or family._sidecars(source) != family._sidecars(candidate):
        errors.append("board_settings_or_sidecars_changed")
    if ledger.get("source_family") != family._family(source,board_hint) or ledger.get("source_sha256") != force._hash(source):
        errors.append("source_bound_ledger_changed")
    board = pcbnew.LoadBoard(str(candidate))
    by_id = {_uuid(t):t for t in board.GetTracks()}
    for row in ledger.get("added_vias",[]):
        item = by_id.get(row["uuid"])
        if (item is None or item.GetClass() != "PCB_VIA" or new.get(row["uuid"],(None,))[0] != "via"
                or _via(item,board) != row or row["net"] != "GND"
                or row["via_type"] != pcbnew.VIATYPE_THROUGH
                or row["layers"] != [pcbnew.F_Cu,pcbnew.B_Cu]
                or row["drill_nm"] != ledger["selection"]["via_drill_nm"]
                or set(row["widths_nm"].values()) != {ledger["selection"]["via_diameter_nm"]}):
            errors.append("serialized_addition_not_exact_ordinary_ground_via")
    try:
        ground_geometry = _saved_ground_geometry(board,ledger["selection"],list(expected))
    except Exception as exc:
        ground_geometry = dict(ok=False,reason=str(exc))
    if ground_geometry.get("ok") is not True:
        errors.append("saved_ground_netclass_geometry_unproved")
    return dict(ok=not errors,errors=sorted(set(errors)),added_uuids=sorted(actual),
        removed_uuids=sorted(set(old)-set(new)),derived_ground_fill_changes=changed_fills,
        saved_ground_geometry=ground_geometry,
        contract="all_retained_geometry_and_non_ground_fill_exact_only_native_ground_refill_allowed")


def _saved_ground_geometry(board, selection, added):
    """Receiving-side actual saved geometry check, not a builder assertion."""
    import pcbnew
    import cec_route_dimensions as dimensions
    import cec_pth_pair_returns as returns
    # Resolve the saved GND class independently of selected/claimed dimensions.
    spec = dimensions.project_resolver(board.GetFileName(),board=board)("GND")
    contract = returns.ground_return_contract(board)
    if (contract != selection.get("ground_return_contract") or spec["name"] != contract["netclass"]
            or selection["clearance_nm"] < contract["clearance_nm"]):
        raise Refusal("saved_ground_dimension_authority_changed")
    minimum_diameter = max(math.ceil(spec["via_diameter"]*1e6),contract["diameter_nm"])
    minimum_drill = max(math.ceil(spec["via_drill"]*1e6),contract["drill_nm"])
    annular = max(math.ceil(dimensions.board_limits(board)["annular"]*1e6),contract["annular_min_nm"])
    tracks = {_uuid(t):t for t in board.GetTracks()}
    rows = []
    if not added or len(set(added)) != len(added):
        raise Refusal("complete_saved_ground_addition_inventory_required")
    for uid in added:
        via = tracks.get(uid)
        if (via is None or via.GetClass() != "PCB_VIA" or via.GetNetname() != "GND"
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or (via.TopLayer(),via.BottomLayer()) != (pcbnew.F_Cu,pcbnew.B_Cu)):
            raise Refusal("saved_ground_via_identity_missing")
        actual = _via(via,board)
        if (actual["drill_nm"] < minimum_drill or any(width < minimum_diameter
                or width-actual["drill_nm"] < 2*annular for width in actual["widths_nm"].values())):
            raise Refusal("saved_ground_via_below_independently_resolved_minima")
        rows.append(actual)
    return dict(ok=True,net="GND",netclass=spec["name"],project_sha256=contract["project_sha256"],
        minimum_diameter_nm=minimum_diameter,minimum_drill_nm=minimum_drill,
        minimum_annular_nm=annular,clearance_nm=selection["clearance_nm"],
        checked_vias=rows,scope="saved_ground_owned_dimensions_not_builder_ledger_or_local_waiver")


def _ground_network(board, selection, added, deadline):
    """Bounded native saved-copper paths to retained, physically present pads.

    Query each via directly. Expanding by returned zone UUID would merge
    disconnected islands (or layers) of a single zone and is forbidden here.
    The native graph has no drill subtraction. Its supported lower-topology
    domain therefore requires foreign bores to miss all GND copper, and every
    GND bore to have an intact annulus/barrel. Removing such disjoint bores
    cannot split a component: the retained annulus connects their boundary.
    Terminals wholly inside a bore are not physical witnesses. This is neither
    an impedance/current rating nor permission to change reference coverage.
    """
    import pcbnew
    import cec_kelvin_copper_cut as cut
    from shapely.ops import unary_union

    work = cut._Work(deadline)
    try:
        manifest = _ground_terminals(board,deadline)
        if manifest != selection.get("retained_ground_terminals"):
            raise Refusal("retained_ground_terminal_identity_changed")
        if not 1 <= len(added) <= MAX_ADDED_RETURNS or len(set(added)) != len(added):
            raise Refusal("bounded_unique_added_return_inventory_required")
        pads, tracks, zones, layers = cut._inventory(board,work)
        ground = [i for i in pads+tracks+zones if i.GetNetname() == "GND"]
        if not ground or len(ground) > MAX_GROUND_ITEMS:
            raise Refusal("ground_connectivity_inventory_budget_exhausted")
        by_id = {_uuid(i):i for i in ground}
        if len(by_id) != len(ground):
            raise Refusal("ambiguous_ground_conductor_identity")
        if any(t.GetClass() not in ("PCB_TRACK","PCB_ARC","PCB_VIA") for t in tracks):
            raise Refusal("unsupported_ground_inventory_track_type")
        for uid in added:
            item = by_id.get(uid)
            if item is None or item.GetClass() != "PCB_VIA":
                raise Refusal("saved_ground_via_identity_missing")

        drilled = []
        for item in pads+tracks:
            work.tick()
            if cut._simple_drill(item,layers):
                drilled.append(item)
        if len({_uuid(i) for i in drilled}) != len(drilled):
            raise Refusal("ambiguous_ground_inventory_drill_identity")
        ground_drilled = [i for i in drilled if i.GetNetname() == "GND"]
        foreign_drilled = [i for i in drilled if i.GetNetname() != "GND"]
        native_holes = {_uuid(i):i.GetEffectiveHoleShape() for i in drilled}
        shapes, physical_pads = {}, {}
        ordinary = {pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                    pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL}
        for item in ground:
            work.tick()
            uid, kind = _uuid(item), item.GetClass()
            active = [layer for layer in layers if item.IsOnLayer(layer)]
            if not active:
                raise Refusal("ground_conductor_enabled_layer_missing")
            if kind == "PAD":
                if (item.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)
                        or any(item.GetShape(layer) not in ordinary for layer in active)):
                    raise Refusal("unsupported_ground_pad_geometry")
                if item.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                    if item.HasHole() or len(active) != 1 or not item.FlashLayer(active[0]):
                        raise Refusal("unsupported_ground_multiface_or_drilled_smd")
                elif not item.HasHole():
                    raise Refusal("ground_plated_terminal_hole_missing")
            barrel = kind == "PCB_VIA" or kind == "PAD" and item.HasHole()
            if barrel and (set(active) != set(layers)
                           or any(not item.FlashLayer(layer) for layer in layers)):
                raise Refusal("unsupported_ground_barrel_layer_support")
            per_layer = {}
            for layer in active:
                work.tick()
                if kind == "ZONE":
                    if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                        raise Refusal("ground_native_zone_fill_unavailable")
                    native = item.GetFilledPolysList(layer)
                    # Native triangulation handles saved slit/weakly-simple
                    # fills. Never replace them with a bbox or GEOS repair.
                    for index in range(native.OutlineCount()):
                        for chain in [native.Outline(index),*[native.Hole(index,j)
                                      for j in range(native.HoleCount(index))]]:
                            work.tick()
                            work.vertices += chain.PointCount()
                            if chain.ArcCount() or chain.PointCount() < 3:
                                raise Refusal("unsupported_ground_fill_contour")
                            if work.vertices > cut.MAX_VERTICES:
                                raise Refusal("ground_connectivity_vertex_budget_exhausted")
                    per_layer[layer] = native
                else:
                    per_layer[layer] = item.GetEffectiveShape(layer)
                    if per_layer[layer] is None:
                        raise Refusal("ground_native_conductor_shape_unavailable")
                    if barrel and not cut._shape(item,layer,False,work).covers(cut._hole(item,True,work)):
                        raise Refusal("ground_bore_not_enclosed_by_native_annulus")
                    if kind == "PAD":
                        physical_pads.setdefault(uid,[]).append(cut._shape(item,layer,False,work))
            shapes[uid] = per_layer
            if kind == "ZONE":
                item.CacheBoundingBox()
                item.CacheTriangulation()

        for index, item in enumerate(ground_drilled):
            for other in ground_drilled[:index]:
                work.contact()
                if native_holes[_uuid(item)].Collide(native_holes[_uuid(other)],0):
                    raise Refusal("overlapping_ground_bores_unsupported")
        for hole in foreign_drilled:
            native = native_holes[_uuid(hole)]
            for per_layer in shapes.values():
                for shape in per_layer.values():
                    work.contact()
                    if shape.Collide(native,0):
                        raise Refusal("foreign_bore_intersects_ground_copper")

        # A pad name/object inside a bore is not a retained physical terminal.
        voids = [cut._hole(i,True,work) for i in ground_drilled]
        void = unary_union(voids) if voids else None
        terminals = {uid for uid,parts in physical_pads.items()
                     if any(not (part.difference(void) if void is not None else part).is_empty
                            for part in parts)}
        work.tick()
        if not terminals:
            raise Refusal("retained_ground_terminal_physical_copper_unproved")
        conn = pcbnew.CONNECTIVITY_DATA()
        for item in ground:
            work.tick()
            if not conn.Add(item):
                raise Refusal("ground_native_connectivity_rejected_item")
        witnesses = []
        manifest_by_id = {row["uuid"]:row for row in manifest}
        for uid in added:
            work.tick()
            reached = {_uuid(i) for i in conn.GetConnectedItems(by_id[uid])}
            work.tick()
            if uid not in reached or not reached <= set(by_id):
                raise Refusal("ground_native_connectivity_inventory_inconsistent")
            reached_terminals = reached & terminals
            if not reached_terminals:
                raise Refusal("added_return_ground_terminal_path_unproved")
            witnesses.append(dict(via_uuid=uid,retained_terminals=[manifest_by_id[t]
                for t in sorted(reached_terminals)],connected_uuids=sorted(reached)))
        if _ground_terminals(board,deadline) != manifest:
            raise Refusal("retained_ground_terminal_identity_changed")
        return dict(ok=True,complete=True,witnesses=witnesses,
            retained_ground_terminals=manifest,inventory_uuids=sorted(by_id),
            enabled_copper_layers=list(layers),drill_inventory_uuids=sorted(native_holes),
            supported_holes="disjoint_ground_through_bores_inside_intact_annuli_foreign_bores_disjoint",
            native_queries=len(added),contacts_examined=work.contacts,vertices_examined=work.vertices,
            scope="saved_native_ground_paths_to_retained_physical_terminals_not_electrical_rating")
    except cut.Unknown as exc:
        raise Refusal("ground_connectivity_unknown:"+str(exc)) from exc
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal("ground_native_connectivity_evidence_unavailable:"+repr(exc)) from exc


def _saved_contacts(board, selection, added, deadline):
    import pcbnew
    import cec_pth_pair_returns as returns
    import cec_force_sense_evidence as sense
    import cec_fr
    ground_geometry = _saved_ground_geometry(board,selection,added)
    pads = {p.m_Uuid.AsString():p for fp in board.GetFootprints() for p in fp.Pads()}
    tracks = {_uuid(t):t for t in board.GetTracks()}
    rows, witnessed = [],set()
    for terminal in selection["terminals"]:
        _tick(deadline)
        pad = pads.get(terminal["uuid"])
        if pad is None or sense._pad_identity(pad) != terminal:
            raise Refusal("saved_plated_terminal_identity_changed")
        for layers in selection["references"]:
            signal,reference = layers["signal"],layers["reference"]
            if not pad.IsOnLayer(signal):
                continue
            polygons = [z.GetFilledPolysList(reference) for z in board.Zones()
                        if z.GetNetname() == "GND" and not z.GetIsRuleArea()
                        and z.IsOnLayer(reference) and z.IsFilled()]
            cells = [c for c in returns.reference_cells(board,pad.GetNetname(),signal,reference,polygons,
                     reach_mm=selection["return_reach_mm"]) if c["pad_uuid"] == terminal["uuid"]]
            if len(cells) != 1:
                raise Refusal("saved_plated_terminal_reference_contact_unproved")
            witnesses = cells[0]["returns"]
            witnessed.update(r["uuid"] for r in witnesses)
            rows.append(dict(terminal=terminal,**layers,returns=witnesses))
    if not rows or not set(added) <= witnessed:
        raise Refusal("added_return_not_bound_to_actual_terminal_reference_contact")
    # Recheck process/copper/rule/drill guards against the final saved epoch,
    # treating each new via as a replacement only for its exact own identity.
    site_guards = []
    for uid in added:
        _tick(deadline)
        via = tracks.get(uid)
        if via is None or via.GetClass() != "PCB_VIA" or via.GetNetname() != "GND":
            raise Refusal("saved_ground_via_identity_missing")
        site = returns.ground_site_guard(board,via.GetPosition(),via.GetWidth(via.TopLayer()),
            via.GetDrillValue(),selection["ground_return_contract"],
            existing_via_uuid=uid,deadline=deadline)
        if site.get("ok") is not True:
            raise Refusal("saved_ground_via_fabrication_site_refused:"+str(site.get("reason")))
        site_guards.append(dict(uuid=uid,**site))
        if not cec_fr._via_spot_clear(board,via.GetPosition(),selection["via_diameter_nm"],
                selection["clearance_nm"],{via.GetNetCode()},drill_nm=selection["via_drill_nm"],
                net_code=via.GetNetCode(),existing_via_uuid=uid):
            raise Refusal("saved_ground_via_native_guard_refused")
    ground_network = _ground_network(board,selection,added,deadline)
    return dict(ok=True,terminals=rows,added_vias_witnessed=sorted(set(added)&witnessed),
                ground_geometry=ground_geometry,
                saved_fabrication_site_guards=site_guards,
                retained_ground_network=ground_network,
                scope="saved_native_plated_terminal_and_filled_reference_contact")


def _kelvin_admission(before, after):
    """Replay every known typed force/sense leg, not the unrelated CAN net."""
    import cec_force_sense_evidence as evidence
    reports = []
    for value in (before,after):
        if value.get("complete") is not True or value.get("identity_stable") is not True:
            raise Refusal("complete_bound_kelvin_replay_required")
        lineage = value.get("lineage",{})
        if (lineage.get("inputs") != len(lineage.get("details",[]))
                or lineage.get("resolved") != lineage.get("inputs")):
            raise Refusal("complete_kelvin_lineage_inventory_required")
        expected = 2*lineage["inputs"]
        cut = value.get("clipped_isolation",{})
        if (cut.get("expected") != expected or len(cut.get("details",[])) != expected
                or cut.get("unknown") != 0 or cut.get("unresolved_inputs") != 0
                or expected and cut.get("ok") is not True):
            raise Refusal("retained_kelvin_isolation_not_fully_verified")
    nets = {r["net"] for r in before["clipped_isolation"]["details"]}
    if nets != {r["net"] for r in after["clipped_isolation"]["details"]}:
        raise Refusal("retained_kelvin_net_inventory_changed")
    # The no-input case is explicitly known and is never called whole-board
    # Kelvin qualification. The shared validator still binds typed inventory.
    for net in sorted(nets) or ["GND"]:
        report = evidence.admit_changed_net(before,after,net)
        reports.append(report)
        if report.get("ok") is not True:
            raise Refusal("retained_kelvin_scoped_admission_refused")
    return dict(ok=True,checked_legs=after["clipped_isolation"]["checked"],
                per_net=reports,full_kelvin_qualification=False)


def _pair_admission(before, after, selection):
    target = _pair_row(after,selection["pair"])
    previous = _pair_row(before,selection["pair"])
    def rows(report):
        return {(r["kind"],r["p"],r["n"]):r for r in report["pairs"]}
    old,new = rows(before),rows(after)
    ok = (before.get("profile") == after.get("profile") == selection["profile"]
          and set(old) == set(new) and not target["violations"]
          and target["reference_coverage_pct"] > previous["reference_coverage_pct"]
          and all(set(row["violations"]) <= set(old[key]["violations"])
                  and row["reference_coverage_pct"] >= old[key]["reference_coverage_pct"]
                  for key,row in new.items()))
    return dict(ok=ok,before=previous,after=target,
                reason="complete_pair_and_reference_improved" if ok else "pair_or_reference_admission_refused")


def _validate_options(board_hint,net,immutable_nets,timeout_s,max_sites):
    if (not isinstance(board_hint,(str,Path)) or not str(board_hint).strip()
            or not isinstance(net,str) or not net or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300
            or type(max_sites) is not int or not 1 <= max_sites <= MAX_SITES
            or not isinstance(immutable_nets,(list,tuple,set,frozenset))
            or any(not isinstance(n,str) or not n for n in immutable_nets)):
        raise ValueError("invalid bounded PTH return proposal options")


def _worker(source,directory,net,*,board_hint,immutable_nets,timeout_s=60,max_sites=2048):
    import pcbnew
    import cec_constraints as constraints
    import cec_force_sense_evidence as evidence
    import cec_operation_budget as budget
    import cec_pth_pair_returns as returns
    import cec_score
    import cec_stage_admission
    import cec_zone_fill
    _validate_options(board_hint,net,immutable_nets,timeout_s,max_sites)
    source,directory = Path(source).resolve(),Path(directory).resolve()
    hint = str(board_hint);start=time.monotonic();deadline=start+timeout_s
    protected=set(family._family(source,hint))|force._protected_paths(source,hint)
    force._check_proposal_directory(directory,protected);family._receipt_output(directory,protected)
    report=dict(schema=1,operation="pth_pair_return_repair",scope=SCOPE,source=str(source),net=net,
        accepted=False,changed=False,candidate_changed=False,candidate=None,retryable=False,
        release_authority=False,full_kelvin_qualification=False,electrical_rating_qualified=False,
        no_path_proof=False,source_family_before=family._family(source,hint),code_before=force._code_identity(),
        environment_before=family._environment(hint),options=dict(board_hint=hint,immutable_nets=sorted(immutable_nets),
            timeout_s=timeout_s,max_sites=max_sites))
    candidate=None;epoch=None
    def replay(path):
        _tick(deadline)
        remaining=budget.available_timeout(deadline-time.monotonic(),os.environ,reserve_s=1)
        if remaining <= 0:
            raise Refusal("pth_return_deadline_exhausted")
        value=evidence.replay(path,board_hint=hint,timeout_s=min(60,remaining))
        if (value.get("source_family_before") != force._family(path,hint)
                or value.get("code_before") != report["code_before"]):
            raise Refusal("kelvin_replay_epoch_disagrees_with_operation")
        return value
    try:
        family._ownership(source,"GND",immutable_nets)
        with force._thermal_hint(hint):
            board=pcbnew.LoadBoard(str(source))
            selection,pair_before=_select(board,source,net,max_sites,deadline)
            for member in (selection["pair"]["p"],selection["pair"]["n"]):
                family._ownership(source,member,immutable_nets)
            report.update(selection=selection,pair_before=pair_before)
            before=replay(source);report["sense_before"]=before
            _kelvin_admission(before,before)
            if family._family(source,hint) != report["source_family_before"]:
                raise Refusal("source_family_changed_before_construction")
            candidate=family._copy(source,directory/"candidate")
            board=pcbnew.LoadBoard(str(candidate));original={_uuid(t) for t in board.GetTracks()}
            _tick(deadline)
            construction=returns.synthesize(board,selection["pair"],return_reach_mm=RETURN_REACH_MM,deadline=deadline)
            report.update(construction=construction,candidate=str(candidate))
            added=[t for t in board.GetTracks() if _uuid(t) not in original]
            if not construction.get("ok") or not added:
                raise Refusal("bounded_existing_pth_return_constructor_refused")
            _tick(deadline)
            ledger=dict(schema=1,source_family=report["source_family_before"],source_sha256=force._hash(source),
                        selection=selection,added_vias=[_via(t,board) for t in added])
            report["ledger"]=ledger
            pcbnew.SaveBoard(str(candidate),board,True);report["candidate_changed"]=True
            report["prefill_preservation"]=preservation(source,candidate,ledger,board_hint=hint)
            if not report["prefill_preservation"]["ok"]:
                raise Refusal("constructor_modified_retained_geometry")
            report["prefill_candidate_sha256"]=force._hash(candidate)
            _tick(deadline)
            # Reload the serialized proposal before deriving the only fill
            # change permission. Prospective constructor planes cannot escape.
            board=pcbnew.LoadBoard(str(candidate))
            report["exact_refill"]=cec_zone_fill.fill_with_report(board)
            pcbnew.SaveBoard(str(candidate),board,True)
            epoch=family._family(candidate,hint);report["candidate_family_verified"]=epoch
            report["preservation"]=preservation(source,candidate,ledger,board_hint=hint,allow_ground_refill=True)
            report["ground_fill_ledger"]=report["preservation"]["derived_ground_fill_changes"]
            if report["preservation"]["ok"] is not True or report["exact_refill"].get("stable") is not True:
                raise Refusal("final_refill_or_exact_preservation_refused")
            exact=pcbnew.LoadBoard(str(candidate))
            report["saved_return_contacts"]=_saved_contacts(exact,selection,[r["uuid"] for r in ledger["added_vias"]],deadline)
            report["pair_after"]=constraints.high_speed_pair_summary(str(candidate),board=exact)
            report["pair_admission"]=_pair_admission(pair_before,report["pair_after"],selection)
            _tick(deadline);metrics_before=cec_score.score(str(source))
            _tick(deadline);metrics_after=cec_score.score(str(candidate))
            report["whole_board_admission"]=cec_stage_admission.evaluate(metrics_before,metrics_after)
            after=replay(candidate);report["sense_after"]=after
            report["kelvin_admission"]=_kelvin_admission(before,after)
            _tick(deadline)
            accepted=(report["pair_admission"]["ok"] is True
                      and report["whole_board_admission"]["accepted"] is True)
            report.update(accepted=accepted,changed=accepted,
                reason="private_pth_return_addition_admitted" if accepted else "pth_return_candidate_admission_refused")
    except (Refusal,family.Refusal) as exc:
        report["reason"]=str(exc)
    except Exception as exc:
        report.update(reason="pth_return_evidence_failure",error=repr(exc))
    finally:
        report.update(source_family_after=family._family(source,hint),code_after=force._code_identity(),
                      environment_after=family._environment(hint),elapsed_s=round(time.monotonic()-start,6))
        report["source_unchanged"]=report["source_family_before"]==report["source_family_after"]
        report["code_unchanged"]=report["code_before"]==report["code_after"]
        report["environment_unchanged"]=report["environment_before"]==report["environment_after"]
        if candidate is not None:
            report["candidate_sha256"]=force._hash(candidate)
            if epoch is not None:
                report["candidate_family_unchanged"]=epoch==family._family(candidate,hint)
                if report["candidate_family_unchanged"] is not True:
                    report.update(accepted=False,changed=False,reason="concurrent_candidate_family_change")
        if not all(report[key] for key in ("source_unchanged","code_unchanged","environment_unchanged")):
            report.update(accepted=False,changed=False,reason="concurrent_source_or_code_change")
        family._receipt_output(directory,protected,report)
    return report


def propose(source,directory,net,*,board_hint,immutable_nets,timeout_s=60,max_sites=2048):
    """One bounded private proposal, retaining causal refused scratch evidence."""
    import cec_operation_budget as budget
    _validate_options(board_hint,net,immutable_nets,timeout_s,max_sites)
    source,directory=Path(source).resolve(),Path(directory).resolve()
    protected=set(family._family(source,board_hint))|force._protected_paths(source,board_hint)
    force._check_proposal_directory(directory,protected)
    family._ownership(source,"GND",immutable_nets)
    directory.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,str(Path(__file__).resolve()),"worker",str(source),"--directory",str(directory),
        "--net",net,"--board-hint",str(board_hint),"--immutable-nets-json",json.dumps(sorted(immutable_nets)),
        "--timeout-s",str(timeout_s),"--max-sites",str(max_sites)]
    try:
        budget.run(command,directory/"supervisor",operation="pth_pair_return_repair",timeout=timeout_s)
        return json.loads((directory/"receipt.json").read_text())
    except budget.OperationFailure as exc:
        result=dict(schema=1,accepted=False,changed=False,release_authority=False,retryable=False,
                    reason="pth_return_worker_stopped",operation_failure=exc.failure_evidence,
                    no_path_proof=False,evidence_directory=str(directory))
        family._receipt_output(directory,protected,result)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("propose","worker"));parser.add_argument("source")
    parser.add_argument("--directory",required=True);parser.add_argument("--net",required=True)
    parser.add_argument("--board-hint",required=True);parser.add_argument("--immutable-nets-json",required=True)
    parser.add_argument("--timeout-s",type=float,default=60);parser.add_argument("--max-sites",type=int,default=2048)
    args=parser.parse_args(argv)
    result=(propose if args.mode=="propose" else _worker)(args.source,args.directory,args.net,
        board_hint=args.board_hint,immutable_nets=json.loads(args.immutable_nets_json),
        timeout_s=args.timeout_s,max_sites=args.max_sites)
    if args.mode=="propose":
        print(json.dumps({k:result.get(k) for k in ("accepted","reason","candidate","source_unchanged",
                                                   "code_unchanged","elapsed_s")},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
