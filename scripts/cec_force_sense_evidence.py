"""Bounded, read-only force/sense evidence; never a Kelvin or current certificate.

Typed resistor lineage names the real same-net copper demands, including
filtered inputs. Native demand connectivity and inner-pad departure are
separate observations. The shunt-pad-omitted graph leaves ALL track copper
intact: residual contact inside the omitted pad can over-report reachability.
Consequently neither a reached terminal nor an unchanged reached-terminal set
is a physical bypass proof or a complete Kelvin non-regression certificate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import sys
import time


MAX_BOARD_ITEMS = 8192
MAX_NET_ITEMS = 512
MAX_INPUTS = 64
MAX_PAIRS = 64
MAX_HOPS = 4
MAX_EXPANSIONS = 256
DEFAULT_TIMEOUT_S = 30.0
MAX_TIMEOUT_S = 60.0
SCOPE = "read_only_typed_lineage_native_contact_evidence_not_kelvin_qualification"


class _Unknown(RuntimeError):
    pass


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise _Unknown("deadline_exhausted")


def _pad_identity(pad):
    owner = pad.GetParentFootprint()
    point = pad.GetPosition()
    return dict(ref=str(owner.GetReference()), footprint_uuid=owner.m_Uuid.AsString(),
                pad=str(pad.GetNumber()), uuid=pad.m_Uuid.AsString(),
                net=str(pad.GetNetname()), position_nm=[int(point.x), int(point.y)])


def _key(item):
    if item.GetClass() == "PAD":
        return ("pad", json.dumps(_pad_identity(item), sort_keys=True))
    return (item.GetClass(), item.m_Uuid.AsString())


def _coverage(rows, expected, *, unresolved_inputs=0):
    observed = sum(row.get("ok") is not None for row in rows)
    passed = sum(row.get("ok") is True for row in rows)
    failed = sum(row.get("ok") is False for row in rows)
    unknown = max(0, expected-observed)
    ok = (False if failed else None if not expected or unknown or unresolved_inputs
          else True)
    return dict(ok=ok, status=("failed" if failed else "not_applicable" if not expected
                and not unresolved_inputs else "unknown" if ok is None else "verified"),
                expected=expected, checked=observed, passed=passed, failed=failed,
                unknown=unknown, unresolved_inputs=unresolved_inputs, details=rows)


def _native_graph(pads, tracks, zones, deadline, *, omit=None):
    """Native contact graph; pads are physical objects, not ref/pin-number unions."""
    import pcbnew
    _tick(deadline)
    items = [item for item in [*pads, *tracks, *zones] if _key(item) != omit]
    if len(items) > MAX_NET_ITEMS:
        raise _Unknown("native_net_item_budget_exhausted")
    if len({_key(item) for item in items}) != len(items):
        raise _Unknown("ambiguous_native_item_identity")
    # An omitted/unknown zone fill is not evidence that no route through it
    # exists. Never fill or change the caller's board to resolve that debt.
    if any(not zone.IsFilled() for zone in zones):
        raise _Unknown("native_zone_fill_unavailable")
    conn = pcbnew.CONNECTIVITY_DATA()
    for item in items:
        _tick(deadline)
        if not conn.Add(item):
            raise _Unknown("native_connectivity_rejected_item")
    _tick(deadline)
    return conn, dict(items=len(items), pads=sum(i.GetClass() == "PAD" for i in items),
        tracks=len(tracks), vias=sum(t.Type() == pcbnew.PCB_VIA_T for t in tracks),
        zones=len(zones), filled_zones=len(zones))


def _reached(graph, seed, deadline):
    _tick(deadline)
    reached = {_key(seed)} | {_key(item) for item in graph.GetConnectedItems(seed)}
    _tick(deadline)
    return reached


def audit(board, *, board_hint, deadline=None, _shard=None):
    """Observe a loaded board without adding, removing, saving or filling copper.

    The caller owns the loaded board's identity; ``replay`` additionally binds
    a saved source family and local code before loading. Deadlines are monotonic
    and cooperative between native calls; native calls have fixed item caps,
    but cannot themselves be interrupted by this in-process API.
    """
    import pcbnew
    import cec_force_current as force
    import cec_fr
    import cec_current_topology
    import cec_pair_semantics
    import cec_score
    import cec_sense_topology
    import cec_constraints
    from cec_kelvin_departure import audit_pad_departures

    # Private dispatch for the saved-family-bound shard API. A shard NEVER
    # sets complete=True; only its exact full-denominator join can do that.
    if _shard is not None and not (
            type(_shard) is tuple and (_shard in (("manifest",),("legacy",))
            or len(_shard)==3 and _shard[0]=="leg"
            and type(_shard[1]) is str and bool(_shard[1]) and _shard[2] in ("p","n"))):
        raise ValueError("exact_manifest_legacy_or_one_input_leg_shard_required")
    if not isinstance(board_hint, (str, Path)) or not str(board_hint).strip():
        raise ValueError("a nonempty bound board_hint is required")
    start = time.monotonic()
    if deadline is None:
        deadline = start + DEFAULT_TIMEOUT_S
    if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline) or deadline < 0
            or deadline > start+MAX_TIMEOUT_S):
        raise ValueError("deadline must be finite and at most 60 seconds ahead")
    result = dict(schema=1, operation="force_sense_read_only_evidence", scope=SCOPE,
        board_hint=str(board_hint), complete=False, stop=None, changed=False,
        release_authority=False, electrical_rating_qualified=False,
        kelvin_isolation_qualified=None, physical_bypass_proved=False,
        no_path_proof=False, loaded_board_identity_verified=False,
        budget=dict(max_board_items=MAX_BOARD_ITEMS, max_net_items=MAX_NET_ITEMS,
            max_inputs=MAX_INPUTS, max_pairs=MAX_PAIRS, max_hops=MAX_HOPS,
            max_expansions_per_input=MAX_EXPANSIONS, deadline_kind="cooperative_native_item_bounded"),
        lineage=dict(ok=None, status="unknown", inputs=None, resolved=0, details=[]),
        legacy_topology=dict(ok=None, status="unknown", checked=0),
        authority={}, errors=[])
    demands, departures, cuts, clipped = [], [], [], []
    expected_demands = expected_legs = 0
    unresolved = 0
    try:
        _tick(deadline)
        inner_min = cec_constraints._param("kelvin-sense-from-inner-pad", "inner_min_mm", 0.1)
        if (isinstance(inner_min, bool) or not isinstance(inner_min, (int, float))
                or not math.isfinite(inner_min) or inner_min < 0):
            raise _Unknown("invalid_kelvin_inner_min_policy")
        result["geometry_policy"] = dict(inner_min_mm=inner_min,
            inner_min_basis="cec_constraints._param(kelvin-sense-from-inner-pad,inner_min_mm,0.1)",
            max_thin_trace_width_mm=0.4,
            thin_width_basis="existing_cec_constraints._chk_kelvin_inner_implementation_convention")
        footprints, pads, tracks, zones = [], [], [], []
        count = 0
        for fp in board.GetFootprints():
            _tick(deadline)
            footprints.append(fp)
            count += 1
            if count > MAX_BOARD_ITEMS:
                raise _Unknown("board_item_budget_exhausted")
            for pad in fp.Pads():
                pads.append(pad)
                count += 1
                if count > MAX_BOARD_ITEMS:
                    raise _Unknown("board_item_budget_exhausted")
        for collection, target in ((board.GetTracks(), tracks), (board.Zones(), zones)):
            for item in collection:
                _tick(deadline)
                count += 1
                if count > MAX_BOARD_ITEMS:
                    raise _Unknown("board_item_budget_exhausted")
                # Rule areas contain no conducting material.
                if item.GetClass() == "ZONE" and item.GetIsRuleArea():
                    continue
                target.append(item)
        result["inventory"] = dict(board_items=count, footprints=len(footprints),
            pads=len(pads), tracks=len(tracks), zones=len(zones))
        refs = [str(fp.GetReference()) for fp in footprints]
        if not all(refs) or len(set(refs)) != len(refs):
            raise _Unknown("ambiguous_footprint_reference")
        inputs = sum(cec_pair_semantics.footprint_input_contract(fp) is not None
                     for fp in footprints)
        result["lineage"]["inputs"] = inputs
        if inputs > MAX_INPUTS:
            raise _Unknown("sense_input_budget_exhausted")
        with force._thermal_hint(str(board_hint)):
            _tick(deadline)
            domains = cec_current_topology.board_current_domains(board, str(board_hint))
            pairs = cec_fr._board_kelvin_pairs(board)
            _tick(deadline)
            if len(pairs) > MAX_PAIRS:
                raise _Unknown("anchor_pair_budget_exhausted")
            result["declared_pairs"] = [list(pair) for pair in pairs]
            anchor_refs = {ref for domain in domains.values() if domain.get("complete") is True
                           for ref in domain.get("authority_refs", ())}
            lineage = cec_sense_topology.board_evidence(board, anchor_pairs=pairs,
                anchor_refs=anchor_refs, max_hops=MAX_HOPS, max_expansions=MAX_EXPANSIONS)
            _tick(deadline)
        result["lineage"] = lineage
        unresolved = lineage["inputs"]-lineage["resolved"]
        lineage["status"] = ("not_applicable" if not lineage["inputs"] else
                             "unknown" if unresolved else "resolved")
        if not lineage["inputs"]:
            lineage["ok"] = None
        by_terminal, pads_by_net = defaultdict(list), defaultdict(list)
        tracks_by_net, zones_by_net = defaultdict(list), defaultdict(list)
        for pad in pads:
            by_terminal[(pad.GetParentFootprint().GetReference(), pad.GetNumber(),
                         pad.GetNetname())].append(pad)
            pads_by_net[pad.GetNetname()].append(pad)
        for track in tracks:
            tracks_by_net[track.GetNetname()].append(track)
        for zone in zones:
            zones_by_net[zone.GetNetname()].append(zone)

        def terminal(ref, pin, net):
            found = by_terminal.get((ref, pin, net), ())
            if len(found) != 1:
                raise _Unknown("missing_or_ambiguous_physical_terminal")
            return found[0]

        graph_cache = {}

        def graph(net, omit=None):
            cache_key = (net, omit)
            if cache_key not in graph_cache:
                graph_cache[cache_key] = _native_graph(pads_by_net[net], tracks_by_net[net],
                    zones_by_net[net], deadline, omit=omit)
            return graph_cache[cache_key]

        # Count all resolved demands before work starts; a late stop cannot
        # make skipped evidence disappear from the reported denominator.
        resolved_rows = [row for row in lineage["details"] if row["ok"] is True]
        expected_demands = sum(len(cec_sense_topology.placement_segments(row))
                               for row in resolved_rows)
        expected_legs = 2*len(resolved_rows)
        if _shard is not None:
            leg_inventory=[];segment_inventory=[]
            for row in resolved_rows:
                for segment in cec_sense_topology.placement_segments(row):
                    segment_inventory.append(dict(segment,input_ref=row['ref'],
                        start_pad=_pad_identity(terminal(segment['start']['ref'],segment['start']['pad'],segment['net'])),
                        end_pad=_pad_identity(terminal(segment['end']['ref'],segment['end']['pad'],segment['net']))))
                for index,leg in enumerate(('p','n')):
                    path=row['selected'][leg];net=path['anchor_net']
                    anchor=terminal(path['anchor_ref'],path['anchor_pad'],net)
                    end=(path['series'][-1] if path['series'] else None)
                    sensor=terminal(end['ref'],end['anchor_pad'],net) if end else terminal(row['ref'],row['pins'][index],net)
                    domain=domains.get(net,{})
                    leg_inventory.append(dict(input_ref=row['ref'],leg=leg,net=net,
                        source_pad=_pad_identity(anchor),sense_terminal=_pad_identity(sensor),
                        authority_excluding_cut=[_pad_identity(p) for p in pads_by_net[net]
                            if p.GetParentFootprint().GetReference() in domain.get('authority_refs',())
                            and _key(p)!=_key(anchor)]))
            if (_shard[0]=='leg' and not any((q['input_ref'],q['leg'])==_shard[1:] for q in leg_inventory)):
                raise ValueError('selected_input_leg_not_in_complete_source_lineage')
            result['shard_inventory']=dict(legs=leg_inventory,segments=segment_inventory,
                expected_demands=expected_demands,expected_legs=expected_legs,
                unresolved_inputs=unresolved,authority_domains=domains)
            result.update(shard_selector=list(_shard),shard_complete=False)
        for row in resolved_rows:
            _tick(deadline)
            selected = row["selected"]
            for segment in cec_sense_topology.placement_segments(row):
                if _shard is not None and (_shard[0]!='leg' or (row['ref'],segment['leg'])!=_shard[1:]):
                    continue
                item = dict(segment, input_ref=row["ref"], ok=None, status="unknown")
                demands.append(item)
                try:
                    a, b = [terminal(segment[end]["ref"], segment[end]["pad"], segment["net"])
                            for end in ("start", "end")]
                    conn, inventory = graph(segment["net"])
                    connected = _key(b) in _reached(conn, a, deadline)
                    item.update(ok=connected, status="connected" if connected else "disconnected",
                        start_pad=_pad_identity(a), end_pad=_pad_identity(b), native=inventory)
                except _Unknown as exc:
                    item["reason"] = str(exc)
                    _tick(deadline)
            for index, leg in enumerate(("p", "n")):
                if _shard is not None and (_shard[0]!='leg' or (row['ref'],leg)!=_shard[1:]):
                    continue
                _tick(deadline)
                path = selected[leg]
                opposite = selected["n" if leg == "p" else "p"]
                net = path["anchor_net"]
                departure = dict(input_ref=row["ref"], leg=leg, net=net, ok=None, status="unknown")
                cut = dict(input_ref=row["ref"], leg=leg, net=net, observed=False, status="unknown",
                    isolation_qualified=None, physical_bypass_proved=False,
                    tracks_clipped=False, scope="shunt_pad_omitted_native_contact_reachability")
                departures.append(departure)
                cuts.append(cut)
                isolation = dict(input_ref=row["ref"], leg=leg, net=net, ok=None, status="unknown")
                clipped.append(isolation)
                try:
                    source = terminal(path["anchor_ref"], path["anchor_pad"], net)
                    other = terminal(opposite["anchor_ref"], opposite["anchor_pad"], opposite["anchor_net"])
                    if path["series"]:
                        last = path["series"][-1]
                        sense = terminal(last["ref"], last["anchor_pad"], net)
                    else:
                        sense = terminal(row["ref"], row["pins"][index], net)
                    domain = domains.get(net)
                    if (not domain or domain.get("complete") is not True
                            or not domain.get("source_refs") or not domain.get("sink_refs")
                            or path["anchor_ref"] not in domain.get("authority_refs", ())):
                        raise _Unknown("complete_current_terminal_authority_required")
                    required_refs = set(domain["source_refs"]) | set(domain["sink_refs"])
                    present_refs = {p.GetParentFootprint().GetReference() for p in pads_by_net[net]}
                    if (required_refs != set(domain["authority_refs"])
                            or not required_refs.issubset(present_refs)):
                        raise _Unknown("current_authority_disagrees_with_native_terminals")
                    result["authority"][net] = domain
                    authority = [p for p in pads_by_net[net] if
                        p.GetParentFootprint().GetReference() in domain["authority_refs"]
                        and _key(p) != _key(source)]
                    if not authority:
                        raise _Unknown("no_authority_terminal_remaining_after_shunt_pad_cut")
                    if len(pads_by_net[net])+len(tracks_by_net[net])+len(zones_by_net[net]) > MAX_NET_ITEMS:
                        raise _Unknown("native_net_item_budget_exhausted")
                    identity = dict(source_pad=_pad_identity(source), sense_terminal=_pad_identity(sense))
                    departure.update(identity)
                    cut.update(identity)
                    thin = [t for t in tracks_by_net[net] if t.GetClass() == "PCB_TRACK"
                            and t.GetWidth() <= 400000]
                    # The existing departure helper indexes contact paths by
                    # raw UUID. Do not feed it distinct cloned objects that
                    # share that ID, even though our native graph keys pads
                    # using their complete physical identity.
                    departure_ids = [item.m_Uuid.AsString() for item in [*pads_by_net[net], *thin]]
                    if len(set(departure_ids)) != len(departure_ids):
                        raise _Unknown("ambiguous_departure_uuid_identity")
                    _tick(deadline)
                    native = audit_pad_departures(source, other.GetPosition(), thin,
                        inner_min_mm=inner_min, target_pads=[sense], connectivity_pads=pads_by_net[net],
                        connectivity_vias=[t for t in tracks_by_net[net] if t.GetClass()=='PCB_VIA'])
                    _tick(deadline)
                    # Applicability is not success. A missing source contact
                    # is unknown in this geometry check; connectivity is above.
                    departure.update(ok=native["ok"] if native["applicable"] else None,
                        status=("verified" if native["ok"] else "failed" if native["applicable"]
                                else "not_applicable"), native=native,
                        scope="thin_trace_inner_departure_to_resolved_same_net_sense_terminal",
                        max_trace_width_mm=0.4, inner_min_mm=inner_min,
                        excludes_force_bypass_and_layer_via_qualification=True)
                    conn, inventory = graph(net, _key(source))
                    reached = _reached(conn, sense, deadline)
                    cut.update(observed=True, status="observed", native=inventory,
                        authority_excluding_cut=[_pad_identity(p) for p in authority],
                        reached_authority=[_pad_identity(p) for p in authority if _key(p) in reached],
                        qualification_caveat="untrimmed_copper_can_join_inside_omitted_pad; not_a_physical_bypass_proof")
                    import cec_kelvin_copper_cut
                    proof = cec_kelvin_copper_cut.audit(board, source, sense, authority, deadline=deadline)
                    isolation.update(identity, ok=proof["ok"], native=proof,
                        status="verified" if proof["ok"] is True else "failed" if proof["ok"] is False else "unknown")
                except _Unknown as exc:
                    if departure["ok"] is None:
                        departure["reason"] = str(exc)
                    if not cut["observed"]:
                        cut["reason"] = str(exc)
                    if isolation["ok"] is None:
                        isolation["reason"] = str(exc)
                    _tick(deadline)
        _tick(deadline)
        legacy_nets = {net for pair in pairs for net in pair}
        if _shard is not None and _shard[0]!='legacy':
            pass
        elif all(len(pads_by_net[n])+len(tracks_by_net[n]) <= MAX_NET_ITEMS for n in legacy_nets):
            faults, reasons, detail, checked = cec_score.kelvin_topology_faults(board, pairs)
            _tick(deadline)
            uncovered = len(legacy_nets)-checked
            result["legacy_topology"] = dict(ok=False if faults else True if checked and not uncovered else None,
                status="partial_coverage" if checked and uncovered else "checked" if checked else "not_applicable",
                candidate_nets=len(legacy_nets), checked=checked, uncovered=uncovered,
                fault_nets=sorted(faults), reasons=reasons, details=detail,
                scope="legacy_same_net_connector_shunt_INA_triple_only")
        else:
            result["legacy_topology"]["reason"] = "native_net_item_budget_exhausted"
        if _shard is None:
            result["complete"] = True
        else:
            result["shard_complete"] = True
    except _Unknown as exc:
        result["stop"] = str(exc)
    except Exception as exc:  # Diagnostic failure never becomes positive evidence.
        result["stop"] = "native_or_authority_evidence_failure"
        result["errors"].append(dict(type=type(exc).__name__, detail=str(exc)))
    finally:
        result["same_net_connectivity"] = _coverage(demands, expected_demands, unresolved_inputs=unresolved)
        result["inner_departure"] = _coverage(departures, expected_legs, unresolved_inputs=unresolved)
        result["clipped_isolation"] = _coverage(clipped, expected_legs, unresolved_inputs=unresolved)
        checked = sum(row["observed"] for row in cuts)
        result["shunt_pad_omitted"] = dict(ok=None, isolation_qualified=None,
            status="observed" if checked == expected_legs and checked and not unresolved else
                   "not_applicable" if not expected_legs and not unresolved else "unknown",
            expected=expected_legs, checked=checked, unknown=expected_legs-checked,
            unresolved_inputs=unresolved, reached_authority_legs=sum(bool(row.get("reached_authority"))
                for row in cuts), tracks_clipped=False, physical_bypass_proved=False,
            nonregression_isolation_certificate=False, details=cuts)
        result["elapsed_s"] = round(time.monotonic()-start, 6)
        if result["stop"]:
            # Early inventory/lineage failure has an unknown denominator,
            # not a vacuous no-input board.
            for key in ("same_net_connectivity", "inner_departure", "shunt_pad_omitted", "clipped_isolation"):
                result[key]["status"] = "unknown"
                result[key]["ok"] = None
    return result


def replay(source, *, board_hint, timeout_s=DEFAULT_TIMEOUT_S):
    """Load a saved PCB once with the existing force input/code identity guard."""
    import pcbnew
    import cec_force_current as force
    if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= MAX_TIMEOUT_S):
        raise ValueError("timeout_s must be finite and in (0, 60]")
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("saved source board is absent")
    start = time.monotonic()
    before, code_before = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    result = audit(board, board_hint=board_hint, deadline=start+timeout_s)
    result.update(source=str(source), source_family_before=before, code_before=code_before,
                  source_family_after=force._family(source, board_hint), code_after=force._code_identity(),
                  code_identity_scope="all_local_scripts_python_sources",
                  source_identity_scope="existing_force_source_family_guard",
                  loaded_board_identity_verified=True)
    result["source_unchanged"] = result["source_family_before"] == result["source_family_after"]
    result["code_unchanged"] = result["code_before"] == result["code_after"]
    result["identity_stable"] = result["source_unchanged"] and result["code_unchanged"]
    if not result["identity_stable"]:
        result.update(complete=False, stop="concurrent_source_family_or_code_change")
    result["elapsed_s"] = round(time.monotonic()-start, 6)
    return result


def compare_clipped_isolation(before, after):
    """Compare the SAME scoped ``clipped_isolation`` coverage, not qualify it.

    Every supplied field, list order and scalar type remains significant,
    except two diagnostics on schema-1 native cut receipts at the exact path
    ``details[*].native``: ``elapsed_s`` and ``vertices_examined``. The latter
    counts work on the whole drill inventory, including unrelated new barrels;
    it is not a material/bound/contact result. Its value must still be a
    nonnegative integer (never bool). Time must be finite and nonnegative.

    Presence of either diagnostic is preserved, and the native receipt scope
    is checked before ignoring its value. No counters, budgets, incomplete or
    refusal fields elsewhere are dropped; in particular contacts_examined,
    approximation/guard bounds and all witnesses remain exact. Source family,
    code epoch and ownership are separate caller obligations. Equal unknown
    evidence remains unknown: this API never grants Kelvin qualification.
    """
    from cec_kelvin_copper_cut import SCOPE as cut_scope

    result = dict(schema=1, comparison="same_scope_clipped_isolation_v1",
        same_evidence=False, comparison_complete=False, differences=[], errors=[],
        ignored_diagnostic_changes=[], full_kelvin_qualification=False,
        kelvin_isolation_qualified=None, release_authority=False,
        max_nodes_per_input=262144, max_depth=64, difference_limit=64)
    diagnostics = ({}, {})
    counts = ("expected", "checked", "passed", "failed", "unknown", "unresolved_inputs")

    def path_text(path):
        return "/"+"/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path)

    def normalize(value, side):
        nodes = 0
        active = set()

        def walk(item, path=()):
            nonlocal nodes
            nodes += 1
            if nodes > result["max_nodes_per_input"] or len(path) > result["max_depth"]:
                raise ValueError("comparison_budget_exhausted:"+path_text(path))
            if type(item) in (dict, list):
                if id(item) in active:
                    raise ValueError("cyclic_evidence:"+path_text(path))
                active.add(id(item))
                try:
                    if type(item) is list:
                        return [walk(v, (*path, i)) for i, v in enumerate(item)]
                    if any(type(k) is not str for k in item):
                        raise ValueError("non_string_evidence_key:"+path_text(path))
                    native = (len(path) == 3 and path[0] == "details"
                              and type(path[1]) is int and path[2] == "native")
                    if native and (type(item.get("schema")) is not int or item["schema"] != 1
                                   or item.get("scope") != cut_scope):
                        raise ValueError("unsupported_native_cut_receipt:"+path_text(path))
                    output = {}
                    for key, child in item.items():
                        child_path = (*path, key)
                        if native and key in ("elapsed_s", "vertices_examined"):
                            valid = (type(child) is int and child >= 0 if key == "vertices_examined"
                                     else type(child) in (int, float) and math.isfinite(child) and child >= 0)
                            if not valid:
                                raise ValueError("invalid_"+key+":"+path_text(child_path))
                            diagnostics[side][child_path] = child
                            output[key] = None  # Keep presence; only the validated value is diagnostic.
                        else:
                            output[key] = walk(child, child_path)
                    return output
                finally:
                    active.remove(id(item))
            if item is None or type(item) in (bool, int, str):
                return item
            if type(item) is float and math.isfinite(item):
                return item
            raise ValueError("non_json_or_nonfinite_evidence:"+path_text(path))

        if type(value) is not dict or type(value.get("details")) is not list:
            raise ValueError("clipped_coverage_object_required")
        if any(type(value.get(k)) is not int or value[k] < 0 for k in counts):
            raise ValueError("invalid_coverage_counter")
        if value.get("ok") is not None and type(value.get("ok")) is not bool:
            raise ValueError("invalid_coverage_ok")
        if value.get("status") not in ("verified", "failed", "unknown", "not_applicable"):
            raise ValueError("invalid_coverage_status")
        return walk(value)

    difference_count = 0

    def different(path, reason):
        nonlocal difference_count
        difference_count += 1
        if len(result["differences"]) < result["difference_limit"]:
            result["differences"].append(dict(path=path_text(path), reason=reason))

    def compare(left, right, path=()):
        if type(left) is not type(right):
            different(path, "scalar_or_container_type_changed")
        elif type(left) is dict:
            for key in sorted(left.keys() | right.keys()):
                if key not in left or key not in right:
                    different((*path, key), "field_presence_changed")
                else:
                    compare(left[key], right[key], (*path, key))
        elif type(left) is list:
            if len(left) != len(right):
                different(path, "list_length_changed")
            for i, (a, b) in enumerate(zip(left, right)):
                compare(a, b, (*path, i))
        elif left != right:
            different(path, "value_changed")

    try:
        left, right = normalize(before, 0), normalize(after, 1)
        compare(left, right)
        result.update(comparison_complete=True, same_evidence=difference_count == 0,
            difference_count=difference_count, differences_truncated=difference_count > len(result["differences"]))
        result["ignored_diagnostic_changes"] = [dict(path=path_text(path), before=diagnostics[0][path],
            after=diagnostics[1][path]) for path in sorted(diagnostics[0].keys() & diagnostics[1].keys())
            if type(diagnostics[0][path]) is not type(diagnostics[1][path]) or diagnostics[0][path] != diagnostics[1][path]]
        result["coverage_before"] = {k: before[k] for k in ("ok", "status", *counts)}
        result["coverage_after"] = {k: after[k] for k in ("ok", "status", *counts)}
        result["reason"] = "same_scope_evidence_equal" if result["same_evidence"] else "same_scope_evidence_changed"
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        result["errors"].append(str(exc))
        result["reason"] = "invalid_or_unbounded_clipped_evidence"
    return result


def native_copper_transform_inventory(before,after,*,modified_nets,maximum_native_items=MAX_BOARD_ITEMS):
    """Read literal native identity deltas for the contact comparator schema.

    KiCad GetTracks() includes PCB_VIA and PCB_ARC. Accordingly a via UUID
    belongs in the parent added/retired_track_uuids AND its via subset. Derive
    that distinction from real item classes, not caller-maintained counters.
    This is only inventory: it does not authorize any addition, retirement,
    same-UUID geometry change, current budget or release. Independent saved
    source-delta receiving and fresh absolute evidence remain mandatory.
    """
    if (type(modified_nets) not in (list,tuple,set) or not 1<=len(modified_nets)<=64
            or any(type(n) is not str or not n for n in modified_nets)
            or len(set(modified_nets))!=len(modified_nets)
            or type(maximum_native_items) is not int or not 1<=maximum_native_items<=32768):
        raise ValueError('bounded_exact_native_copper_transform_scope_required')
    def inventory(board):
        items=[*board.GetTracks(),*(z for z in board.Zones() if not z.GetIsRuleArea())]
        if len(items)>maximum_native_items:raise ValueError('native_copper_transform_item_bound')
        result={}
        for item in items:
            uid=str(item.m_Uuid.AsString());kind=str(item.GetClass());net=str(item.GetNetname())
            if not uid or uid in result or kind not in ('PCB_TRACK','PCB_VIA','PCB_ARC','ZONE'):
                raise ValueError('unique_supported_native_copper_transform_identity_required')
            result[uid]=(kind,net)
        return result
    old,new=inventory(before),inventory(after);selected=set(modified_nets)
    if any(old[u]!=new[u] for u in old.keys()&new.keys()):
        raise ValueError('native_copper_transform_reused_identity_changed_class_or_net')
    removed=old.keys()-new.keys();added=new.keys()-old.keys()
    if any(old[u][1] not in selected for u in removed) or any(new[u][1] not in selected for u in added):
        raise ValueError('native_copper_identity_delta_outside_declared_nets')
    rows=[]
    for net in sorted(selected):
        row=dict(net=net,
            retired_track_uuids=sorted(u for u in removed if old[u][1]==net and old[u][0]!='ZONE'),
            added_track_uuids=sorted(u for u in added if new[u][1]==net and new[u][0]!='ZONE'),
            retired_via_uuids=sorted(u for u in removed if old[u]==('PCB_VIA',net)),
            added_via_uuids=sorted(u for u in added if new[u]==('PCB_VIA',net)),
            retired_zone_uuids=sorted(u for u in removed if old[u]==('ZONE',net)),
            added_zone_uuids=sorted(u for u in added if new[u]==('ZONE',net)))
        if any(len(v)>128 for k,v in row.items() if k!='net'):
            raise ValueError('native_copper_transform_per_net_identity_bound')
        if any(row[k] for k in ('retired_track_uuids','added_track_uuids','retired_zone_uuids','added_zone_uuids')):
            rows.append(row)
    return rows


def compare_contact_preservation(before, after, *, native_copper_transforms=()):
    """Same scoped evidence across explicitly declared native item changes.

    A track-to-filled-zone replacement changes native graph inventory counts,
    not necessarily physical demand connectivity. Check those count deltas
    exactly against a caller-received transformation manifest. All terminals,
    reachability, coverage, unknown/refusal states, authority and departures
    remain exact. Clipped isolation is independently compared by its native
    scope comparator. Equal unknown evidence does NOT qualify Kelvin routing.

    The caller must independently prove the retired/added UUIDs, native fill,
    code/source epoch, unmodified items and current widths. This comparator is
    not permission to emit copper, accept an unreceived manifest or waive DRC.
    """
    result=dict(schema=1,comparison='same_scope_contact_preservation_v1',
        same_evidence=False,comparison_complete=False,errors=[],declared_count_changes=[],
        full_kelvin_qualification=False,kelvin_isolation_qualified=None,release_authority=False)
    categories=('lineage','legacy_topology','authority','same_net_connectivity','inner_departure','shunt_pad_omitted')
    counts=('items','pads','tracks','vias','zones','filled_zones')
    try:
        if not isinstance(native_copper_transforms,(list,tuple)) or len(native_copper_transforms)>64:
            raise ValueError('contact_transform_inventory_bound')
        changes={};identities=set()
        for row in native_copper_transforms:
            if (type(row) is not dict or type(row.get('net')) is not str or not row['net']
                    or row['net'] in changes):
                raise ValueError('ambiguous_contact_transform_net')
            track_delta = 'added_track_uuids' in row
            fields = ('retired_track_uuids','added_zone_uuids') + (('added_track_uuids',) if track_delta else ())
            for key in fields:
                values=row.get(key)
                minimum=0 if key=='retired_track_uuids' or track_delta else 1
                if (type(values) is not list or not minimum<=len(values)<=128
                        or any(type(u) is not str or not u for u in values)
                        or len(set(values))!=len(values) or identities.intersection(values)):
                    raise ValueError('invalid_contact_transform_identity')
                identities.update(values)
            removed_zones=row.get('retired_zone_uuids',[])
            if (type(removed_zones) is not list or len(removed_zones)>128
                    or any(type(u) is not str or not u for u in removed_zones)
                    or len(set(removed_zones))!=len(removed_zones)
                    or identities.intersection(removed_zones)):
                raise ValueError('invalid_contact_transform_retired_zone_identity')
            identities.update(removed_zones)
            retired,added=len(row['retired_track_uuids']),len(row['added_zone_uuids'])
            incoming=len(row.get('added_track_uuids',()))
            via_delta=0
            if track_delta:
                for key,parent in (('added_via_uuids','added_track_uuids'),
                                   ('retired_via_uuids','retired_track_uuids')):
                    values=row.get(key,[])
                    if (type(values) is not list or any(type(u) is not str or not u for u in values)
                            or len(values)!=len(set(values)) or not set(values)<=set(row[parent])):
                        raise ValueError('invalid_contact_transform_via_subset')
                via_delta=len(row.get('added_via_uuids',()))-len(row.get('retired_via_uuids',()))
                if retired+added+incoming+len(removed_zones)==0:
                    raise ValueError('empty_contact_transform')
            zones=added-len(removed_zones)
            changes[row['net']]=dict(items=zones+incoming-retired,pads=0,
                tracks=incoming-retired,vias=via_delta,zones=zones,filled_zones=zones)
        def safe_copy(value):
            nodes=0;active=set()
            def walk(v,depth=0):
                nonlocal nodes
                nodes+=1
                if nodes>262144 or depth>64:raise ValueError('contact_comparison_budget_exhausted')
                if type(v) in (list,tuple,dict):
                    if id(v) in active:raise ValueError('cyclic_contact_evidence')
                    active.add(id(v))
                    try:
                        # Native lineage emits immutable tuples for some pin
                        # inventories. They serialize as JSON arrays; retain
                        # every element/order, without arbitrary type coercion.
                        if type(v) in (list,tuple):return [walk(x,depth+1) for x in v]
                        if any(type(k) is not str for k in v):raise ValueError('invalid_contact_evidence_key')
                        return {k:walk(x,depth+1) for k,x in v.items()}
                    finally:active.remove(id(v))
                if v is None or type(v) in (bool,int,str):return v
                if type(v) is float and math.isfinite(v):return v
                raise ValueError('invalid_contact_evidence_value:'+type(v).__name__)
            return walk(value)
        selected=[]
        for side,report in enumerate((before,after)):
            if (type(report) is not dict or report.get('scope')!=SCOPE
                    or report.get('complete') is not True or report.get('identity_stable') is not True):
                raise ValueError('incomplete_or_unbound_contact_replay')
            evidence=safe_copy({key:report[key] for key in categories})
            for category in ('same_net_connectivity','shunt_pad_omitted'):
                coverage=evidence[category]
                if type(coverage) is not dict or type(coverage.get('details')) is not list:
                    raise ValueError('contact_coverage_inventory_required')
                for index,row in enumerate(coverage['details']):
                    if type(row) is not dict or type(row.get('net')) is not str:
                        raise ValueError('contact_detail_identity_required')
                    native=row.get('native')
                    if native is None:continue  # Exact unknown fields still compare below.
                    if (type(native) is not dict or set(native)!=set(counts)
                            or any(type(native.get(k)) is not int or not 0<=native[k]<=MAX_NET_ITEMS for k in counts)
                            or native['items']!=native['pads']+native['tracks']+native['zones']
                            or native['filled_zones']!=native['zones'] or native['vias']>native['tracks']):
                        raise ValueError('invalid_native_contact_inventory_counts')
                    delta=changes.get(row['net'])
                    if side==1 and delta:
                        actual=dict(native)
                        for key in counts:native[key]-=delta[key]
                        if any(v<0 for v in native.values()):raise ValueError('impossible_contact_transform_counts')
                        result['declared_count_changes'].append(dict(category=category,index=index,net=row['net'],actual_after=actual,expected_delta=delta))
            selected.append(evidence)
        # JSON scalar encodings retain bool/int and field presence distinctions.
        exact=json.dumps(selected[0],sort_keys=True,allow_nan=False)==json.dumps(selected[1],sort_keys=True,allow_nan=False)
        differences=[]
        def locate(a,b,path=""):
            if len(differences)>=64:return
            if type(a) is not type(b):differences.append(dict(path=path,reason="type_changed"))
            elif type(a) is dict:
                for k in sorted(a.keys()|b.keys()):
                    if k not in a or k not in b:differences.append(dict(path=path+"/"+k,reason="field_presence_changed"))
                    else:locate(a[k],b[k],path+"/"+k)
                    if len(differences)>=64:return
            elif type(a) is list:
                if len(a)!=len(b):differences.append(dict(path=path,reason="list_length_changed",before=len(a),after=len(b)))
                for i,(x,y) in enumerate(zip(a,b)):locate(x,y,path+"/"+str(i))
            elif a!=b:differences.append(dict(path=path,reason="value_changed",before=a,after=b))
        if not exact:locate(*selected)
        result["physical_differences"]=differences
        clipped=compare_clipped_isolation(before['clipped_isolation'],after['clipped_isolation'])
        result.update(comparison_complete=clipped['comparison_complete'],same_evidence=exact and clipped['same_evidence'],clipped_isolation=clipped,
            reason='same_scope_physical_evidence_preserved' if exact and clipped['same_evidence'] else 'physical_evidence_or_declared_counts_changed')
    except (KeyError,TypeError,ValueError,RecursionError) as exc:
        result['errors'].append(str(exc));result['reason']='contact_preservation_comparison_refused'
    return result


def compare_contour_preservation(before, after, *, modified_nets,
                                 native_copper_transforms=(),
                                 rebind_covered_internal_contacts=False):
    """Rebind only absolutely verified cut proofs on declared changed nets.

    Caller must receive native source/child identity, exact item changes and
    full filled-copper enclosure first. Unchanged unknown legs use the STRICT
    preservation comparator; they cannot be rebound or upgraded. A changed
    positive leg requires fresh absolute post-change admission AND positive
    pre-change admission, with the same physical sources/authority/lineage.
    Every other contact, departure, coverage counter and refusal remains exact.
    This preserves scoped evidence, never grants global Kelvin/release status.
    """
    import copy
    result=dict(schema=1,comparison="qualified_contour_contact_preservation_v1",
        same_evidence=False,comparison_complete=False,rebound_nets=[],errors=[],
        vertex_omission_observations_rebound=[],
        full_kelvin_qualification=False,kelvin_isolation_qualified=None,release_authority=False)
    try:
        if (not isinstance(modified_nets,(list,tuple,set)) or not 1<=len(modified_nets)<=64
                or any(type(n) is not str or not n for n in modified_nets)
                or len(set(modified_nets))!=len(modified_nets)):
            raise ValueError("invalid_contour_modified_net_inventory")
        if type(rebind_covered_internal_contacts) is not bool:
            raise ValueError('explicit_internal_contact_rebinding_required')
        # This bounds and validates every field before copying or rebinding it.
        for report in (before,after):
            check=compare_contact_preservation(report,report)
            if not check["comparison_complete"] or not check["same_evidence"]:
                raise ValueError("invalid_or_unbound_contour_contact_evidence")
        selected=set(modified_nets)
        old_rows=before["clipped_isolation"]["details"]
        new_rows=after["clipped_isolation"]["details"]
        def keys(rows):
            result={}
            for index,row in enumerate(rows):
                key=(row["input_ref"],row["leg"],row["net"])
                if key in result:raise ValueError("duplicate_contour_physical_leg")
                result[key]=(index,row)
            return result
        old,new=keys(old_rows),keys(new_rows)
        if old.keys()!=new.keys():raise ValueError("contour_physical_leg_inventory_changed")
        omitted={}
        for side,report in enumerate((before,after)):
            rows=report["shunt_pad_omitted"]["details"]
            mapping=keys(rows)
            if mapping.keys()!=old.keys():raise ValueError("contour_vertex_observation_inventory_changed")
            if report["shunt_pad_omitted"].get("reached_authority_legs")!=sum(bool(r.get("reached_authority")) for r in rows):
                raise ValueError("invalid_vertex_observation_reached_counter")
            omitted[side]=mapping
        adjusted=copy.deepcopy(after)
        for net in sorted(selected):
            affected=[key for key in old if key[2]==net]
            if not affected:continue
            # Unknown and failure evidence must remain byte-for-byte strict
            # (apart from the two existing bounded work diagnostics).
            if any(old[key][1].get("ok") is not True or new[key][1].get("ok") is not True for key in affected):
                continue
            prior=admit_changed_net(before,before,net)
            fresh=admit_changed_net(before,after,net)
            if (not prior["ok"] or not fresh["ok"] or prior["expected_legs"]!=fresh["expected_legs"]
                    or prior["checked"]!=fresh["checked"]):
                raise ValueError("contour_absolute_cut_readmission_refused:"+net)
            for key in affected:
                native=old[key][1]["native"];actual=new[key][1]["native"]
                # Numerical/model/process/safety properties are not diagnostics.
                geometry_fields={"elapsed_s","vertices_examined","contacts_examined",
                    "exact_linear_refinements","baseline_geometry","upper","lower"}
                fields=(set(native)|set(actual))-geometry_fields
                if any(native.get(f)!=actual.get(f) or (f in native)!=(f in actual) for f in fields):
                    raise ValueError("contour_cut_model_or_physical_contract_changed:"+net)
                adjusted["clipped_isolation"]["details"][new[key][0]]["native"]=copy.deepcopy(native)
                if rebind_covered_internal_contacts:
                    # Additive import can add a segment whose centreline never
                    # departs the shunt land. Retain EVERY real departure and
                    # guard exactly. Both absolute clipped cuts and both inner
                    # departures already passed above; a newly added exit or
                    # any other inner contract change remains a refusal.
                    def departure(report):
                        rows=[r for r in report['inner_departure']['details']
                            if (r['input_ref'],r['leg'],r['net'])==key]
                        if len(rows)!=1 or rows[0].get('ok') is not True:
                            raise ValueError('positive_inner_departure_required')
                        return rows[0]['native']
                    first,last=departure(before),departure(after)
                    counters=('contact_count','internal_count')
                    if (any(type(r.get(k)) is not int or not 0<=r[k]<=MAX_NET_ITEMS
                            for r in (first,last) for k in counters)
                            or {k:v for k,v in first.items() if k not in counters}
                            !={k:v for k,v in last.items() if k not in counters}):
                        raise ValueError('inner_departure_contract_or_exit_changed')
                    delta=last['internal_count']-first['internal_count']
                    if delta<0 or last['contact_count']-first['contact_count']!=delta:
                        raise ValueError('internal_contact_inventory_not_additive')
                    for row in adjusted['inner_departure']['details']:
                        if (row['input_ref'],row['leg'],row['net'])==key:
                            for counter in counters:row['native'][counter]=first[counter]
                    if delta:result.setdefault('internal_contact_observations_rebound',[]).append(
                        dict(input_ref=key[0],leg=key[1],net=net,added_internal_contacts=delta,
                            basis='unchanged_real_departures_and_two_absolute_clipped_cut_passes'))
                # PAD-vertex deletion is explicitly an OBSERVATION, not a
                # geometric cut. A zone can retain copper under a removed PAD
                # node. Only this positively requalified physical leg can
                # rebind that observation; the complete source-pad subtraction
                # above remains the authority. Unknown/failing legs stay strict.
                oi,obs=omitted[0][key];ni,current=omitted[1][key]
                if obs.get("reached_authority")!=current.get("reached_authority"):
                    for observation in (obs,current):
                        if observation.get("ok") is not None or observation.get("status")!="observed":
                            raise ValueError("qualified_vertex_observation_required:"+net)
                        allowed={json.dumps(p,sort_keys=True) for p in observation["authority_excluding_cut"]}
                        reached=observation["reached_authority"]
                        identities=[json.dumps(p,sort_keys=True) for p in reached]
                        if len(identities)!=len(set(identities)) or not set(identities)<=allowed:
                            raise ValueError("vertex_observation_physical_authority_mismatch:"+net)
                    adjusted["shunt_pad_omitted"]["details"][ni]["reached_authority"]=copy.deepcopy(obs["reached_authority"])
                    adjusted["shunt_pad_omitted"]["reached_authority_legs"]-=int(bool(current["reached_authority"]))-int(bool(obs["reached_authority"]))
                    result["vertex_omission_observations_rebound"].append(dict(input_ref=key[0],leg=key[1],net=net,
                        before=obs["reached_authority"],after=current["reached_authority"],
                        basis="fresh_absolute_geometric_cut_not_PAD_vertex_deletion"))
            result["rebound_nets"].append(dict(net=net,legs=len(affected),before=prior,after=fresh))
        preserved=compare_contact_preservation(before,adjusted,native_copper_transforms=native_copper_transforms)
        result.update(comparison_complete=preserved["comparison_complete"],
            same_evidence=preserved["same_evidence"],preservation=preserved,
            reason="scoped_contour_evidence_preserved" if preserved["same_evidence"] else "unrebound_physical_evidence_changed")
        result["coverage_after"]={k:after["clipped_isolation"][k] for k in
            ("ok","status","expected","checked","passed","failed","unknown","unresolved_inputs")}
    except (KeyError,TypeError,ValueError,RecursionError) as exc:
        result["errors"].append(str(exc));result["reason"]="contour_evidence_rebinding_refused"
    return result


def compare_repaired_preservation(before,after,*,repair_nets,modified_nets,
                                  native_copper_transforms=(),repair_legs=None):
    """Receive actual repairs with absolute AFTER proof, not preserved unknowns.

    The saved-delta receiver must derive repair_nets from actual new copper
    joining previously open manufacturer-input demands. Every affected leg
    must now pass all demands, inner departure and geometric pad subtraction.
    Explicit leg scope permits a completed input without inventing a pass for
    another input sharing its rail. The default still receives whole nets.
    Model/guard/physical inventories stay fixed, unaffected evidence remains
    strict, and the raw coverage improvement is retained. No global pass.
    The older positive-contour preservation API remains unchanged.
    """
    return _compare_repaired_preservation(before,after,repair_nets=repair_nets,
        modified_nets=modified_nets,native_copper_transforms=native_copper_transforms,
        repair_legs=repair_legs)


def _compare_repaired_preservation(before,after,*,repair_nets,modified_nets,
                                  native_copper_transforms=(),repair_legs=None,
                                  _received_force_banks=None):
    """Shared strict normalizer; source-bank proof is derived by its receiver.

    The public input-lead comparator does not expose a bank-success switch.
    Only cec_force_bank_repair's exact saved/native receiver supplies that
    separate basis. Raw packets are never edited to invent an input failure.
    """
    import copy
    result=dict(comparison_complete=False,same_evidence=False,errors=[],repaired_nets=[],
        full_kelvin_qualification=False,release_authority=False,kelvin_isolation_qualified=None)
    try:
        if (type(repair_nets) not in (list,tuple) or not 1<=len(repair_nets)<=MAX_PAIRS
                or len(set(repair_nets))!=len(repair_nets)
                or any(type(n) is not str or not n for n in repair_nets)
                or not set(repair_nets)<=set(modified_nets)):
            raise ValueError('finite_received_repaired_net_inventory_required')
        for report in (before,after):
            check=compare_contact_preservation(report,report)
            if not check['comparison_complete'] or not check['same_evidence']:
                raise ValueError('complete_bound_repair_evidence_required')
            for category in ('same_net_connectivity','inner_departure','clipped_isolation'):
                packet=report[category]
                expected=_coverage(packet['details'],packet['expected'],unresolved_inputs=packet['unresolved_inputs'])
                if packet!=expected:raise ValueError('repair_coverage_does_not_match_actual_rows:'+category)
            packet=report['shunt_pad_omitted']
            if packet['reached_authority_legs']!=sum(bool(r.get('reached_authority')) for r in packet['details']):
                raise ValueError('repair_observation_coverage_counter_mismatch')
        if before.get('geometry_policy')!=after.get('geometry_policy'):
            raise ValueError('repair_geometry_policy_changed')
        def row_key(row,category):
            key=(row['input_ref'],row['leg'],row['net'])
            return key+(json.dumps((row['start'],row['end']),sort_keys=True),) if category=='same_net_connectivity' else key
        def inventory(report,category):
            rows=report[category]['details'];mapping={row_key(r,category):r for r in rows}
            if len(rows)!=len(mapping):raise ValueError('duplicate_repaired_physical_demand')
            return mapping
        adjusted=copy.deepcopy(after)
        categories=('same_net_connectivity','inner_departure','clipped_isolation','shunt_pad_omitted')
        originals={category:inventory(before,category) for category in categories}
        actuals={category:inventory(after,category) for category in categories}
        if any(originals[c].keys()!=actuals[c].keys() for c in categories):
            raise ValueError('repair_demand_or_physical_leg_inventory_changed')
        selected_legs=None
        if repair_legs is not None:
            if (type(repair_legs) not in (list,tuple) or not 1<=len(repair_legs)<=MAX_PAIRS
                    or any(type(k) not in (list,tuple) or len(k)!=3
                        or any(type(v) is not str or not v for v in k)
                        or k[1] not in ('p','n') for k in repair_legs)):
                raise ValueError('finite_exact_repaired_physical_leg_scope_required')
            selected_legs={tuple(k) for k in repair_legs}
            if (len(selected_legs)!=len(repair_legs)
                    or {k[2] for k in selected_legs}!=set(repair_nets)
                    or not selected_legs<=originals['clipped_isolation'].keys()):
                raise ValueError('repaired_leg_scope_not_exact_physical_inventory')
        for net in sorted(repair_nets):
            legs=sorted((k[0],k[1]) for k in selected_legs if k[2]==net) if selected_legs is not None else None
            fresh=admit_changed_net(before,after,net,input_legs=legs)
            if not fresh['ok'] or not fresh['applicable'] or fresh['checked']!=len(fresh['expected_legs']):
                raise ValueError('absolute_repaired_cohort_admission_refused:'+net)
            completed={key[:3] for key,r in originals['same_net_connectivity'].items()
                if r['net']==net and r.get('ok') is not True
                and actuals['same_net_connectivity'][key].get('ok') is True}
            bank=(_received_force_banks or {}).get(net)
            if bank is not None:
                if (selected_legs is not None or bank.get('native_bank_closed') is not True
                        or not bank.get('newly_connected_pairs')):
                    raise ValueError('exact_received_whole_force_bank_required:'+net)
            elif (not completed or selected_legs is not None
                    and not {k for k in selected_legs if k[2]==net}<=completed):
                raise ValueError('actual_newly_connected_input_demand_required:'+net)
            for category in categories:
                for index,row in enumerate(after[category]['details']):
                    if (row['net']!=net or selected_legs is not None
                            and (row['input_ref'],row['leg'],row['net']) not in selected_legs):continue
                    key=row_key(row,category);old=originals[category][key]
                    mutable={'ok','status','native','reason'}
                    if category=='shunt_pad_omitted':mutable={'native','reached_authority'}
                    if {k:v for k,v in old.items() if k not in mutable}!={k:v for k,v in row.items() if k not in mutable}:
                        raise ValueError('repaired_physical_policy_or_terminal_changed:'+category)
                    if category=='clipped_isolation':
                        outcomes={'ok','complete','reason','baseline_connected','baseline_geometry','upper','lower',
                            'elapsed_s','vertices_examined','contacts_examined','exact_linear_refinements',
                            'exact_linear_identity_verified'}
                        if ({k:v for k,v in old['native'].items() if k not in outcomes}
                                !={k:v for k,v in row['native'].items() if k not in outcomes}):
                            raise ValueError('repaired_cut_model_guard_or_contract_changed')
                    if category=='shunt_pad_omitted':
                        allowed={json.dumps(p,sort_keys=True) for p in row['authority_excluding_cut']}
                        reached=[json.dumps(p,sort_keys=True) for p in row['reached_authority']]
                        if len(set(reached))!=len(reached) or not set(reached)<=allowed:
                            raise ValueError('repaired_observation_wrong_physical_authority')
                    replacement=copy.deepcopy(old)
                    if category in ('same_net_connectivity','shunt_pad_omitted'):
                        # Keep actual AFTER counts; the exact saved-delta count
                        # manifest, not a repair status, must still reconcile.
                        replacement['native']=copy.deepcopy(row['native'])
                    adjusted[category]['details'][index]=replacement
            result['repaired_nets'].append(dict(net=net,absolute_after_admission=fresh,
                **(dict(force_bank_receiving=bank) if bank is not None else {})))
        if selected_legs is not None:
            # A new, absolutely proved input departure is also observable at
            # another still-open input sharing the SAME physical shunt land.
            # It is not that input's route. Retain raw AFTER failure/unknown
            # coverage, and reconcile only this positively identified peer
            # observation; no changed cut, heading, issue or old contact is
            # eligible for rebinding.
            added_tracks={u for transform in native_copper_transforms
                for u in transform.get('added_track_uuids',())}
            proved={}
            for key in selected_legs:
                row=actuals['inner_departure'][key]
                for departure in row['native']['departures']:
                    proved[(row['source_pad']['uuid'],departure['uuid'])]=departure
            observations=[]
            for index,row in enumerate(after['inner_departure']['details']):
                key=(row['input_ref'],row['leg'],row['net'])
                if key in selected_legs or key[2] not in repair_nets:continue
                old=originals['inner_departure'][key];first=old.get('native');last=row.get('native')
                if not first or not last or first==last:continue
                # Do not mask an input that acquired any source-connected
                # departure, lost an old refusal or changed physical policy.
                mutable={'applicable','contact_count','non_sense_departures','reason'}
                if (not first.get('unreachable_input_pad_uuids')
                        or first.get('unreachable_input_pad_uuids')!=last.get('unreachable_input_pad_uuids')
                        or last.get('departures') or first.get('issues')!=last.get('issues')
                        or first.get('issues')
                        or {k:v for k,v in first.items() if k not in mutable}
                            !={k:v for k,v in last.items() if k not in mutable}
                        or {k:v for k,v in old.items() if k not in ('ok','status','native')}
                            !={k:v for k,v in row.items() if k not in ('ok','status','native')}):
                    continue
                prior={d['uuid']:d for d in first.get('non_sense_departures',())}
                current={d['uuid']:d for d in last.get('non_sense_departures',())}
                if (len(current)!=len(last.get('non_sense_departures',()))
                        or len(prior)!=len(first.get('non_sense_departures',()))
                        or not prior.keys()<=current.keys()
                        or any(current[u]!=d for u,d in prior.items())):continue
                extra=set(current)-set(prior)
                if (not extra or not extra<=added_tracks
                        or last['contact_count']-first['contact_count']!=len(extra)
                        or last.get('reason')!='input_not_reached_from_source'
                        or first.get('reason') not in ('no_native_pad_contact','input_not_reached_from_source')):continue
                witness_fields={'reachable_input_pad_uuids','input_contact_paths'}
                if any((row['source_pad']['uuid'],u) not in proved
                        or {k:v for k,v in current[u].items() if k not in witness_fields}
                            !={k:v for k,v in proved[(row['source_pad']['uuid'],u)].items() if k not in witness_fields}
                        or current[u].get('reachable_input_pad_uuids') for u in extra):continue
                adjusted['inner_departure']['details'][index]=copy.deepcopy(old)
                observations.append(dict(input_ref=key[0],leg=key[1],net=key[2],
                    source_pad_uuid=row['source_pad']['uuid'],proved_other_input_departures=sorted(extra),
                    raw_after_ok=row['ok'],raw_after_status=row['status'],still_unconnected=True,
                    input_qualified=False,release_authority=False))
            result['unreached_input_peer_departure_observations']=observations
        for category in ('same_net_connectivity','inner_departure','clipped_isolation'):
            packet=adjusted[category]
            adjusted[category]=_coverage(packet['details'],packet['expected'],unresolved_inputs=packet['unresolved_inputs'])
        adjusted['shunt_pad_omitted']['reached_authority_legs']=sum(bool(r.get('reached_authority'))
            for r in adjusted['shunt_pad_omitted']['details'])
        preserved=compare_contour_preservation(before,adjusted,modified_nets=list(modified_nets),
            native_copper_transforms=native_copper_transforms,rebind_covered_internal_contacts=True)
        result.update(comparison_complete=preserved['comparison_complete'],same_evidence=preserved['same_evidence'],
            strict_unaffected_preservation=preserved,coverage_before={c:{k:before[c][k]
                for k in ('expected','checked','passed','failed','unknown')} for c in categories[:3]},
            coverage_after={c:{k:after[c][k] for k in ('expected','checked','passed','failed','unknown')}
                for c in categories[:3]})
    except (KeyError,TypeError,ValueError,RecursionError) as exc:result['errors'].append(str(exc))
    return result


def admit_changed_net(before, after, net, *, input_legs=None):
    """Require absolute post-change proof for affected typed physical legs.

    A force gap may be open before repair, so the prior geometry need not pass.
    Its complete lineage and physical terminal inventory must still be known
    and unchanged. All same-net demands on each affected filtered/direct leg
    must pass after repair. Explicit input_legs is a bounded subset of the
    independently resolved physical inventory, never a net/global waiver.
    Unaffected legs are not awarded a global pass.
    """
    import cec_sense_topology
    result = dict(ok=False, net=net, applicable=None, expected_legs=[], checked=0,
        full_kelvin_qualification=False, release_authority=False, reasons=[])
    try:
        for report in (before, after):
            if report.get("complete") is not True or report.get("identity_stable") is not True:
                raise ValueError("incomplete_or_unbound_sense_replay")
            lineage = report["lineage"]
            rows = lineage["details"]
            if (lineage["inputs"] != len(rows) or lineage["resolved"] != len(rows)
                    or any(row.get("ok") is not True for row in rows)
                    or len({row["ref"] for row in rows}) != len(rows)):
                raise ValueError("unresolved_or_incomplete_sense_inventory")
        def inventory(report):
            return {row["ref"]: {key: row[key] for key in
                    ("ref", "device", "pins", "input_nets", "selected")}
                    for row in report["lineage"]["details"]}
        if inventory(before) != inventory(after):
            raise ValueError("typed_sense_inventory_changed")
        demands = []
        for row in after["lineage"]["details"]:
            demands.extend(dict(segment, input_ref=row["ref"])
                           for segment in cec_sense_topology.placement_segments(row))
        affected = {(d["input_ref"], d["leg"]) for d in demands if d["net"] == net}
        if input_legs is not None:
            if (type(input_legs) not in (list,tuple) or not 1<=len(input_legs)<=MAX_PAIRS
                    or any(type(k) not in (list,tuple) or len(k)!=2
                        or any(type(v) is not str or not v for v in k)
                        or k[1] not in ('p','n') for k in input_legs)):
                raise ValueError('finite_exact_input_leg_admission_scope_required')
            selected={tuple(k) for k in input_legs}
            if len(selected)!=len(input_legs) or not selected<=affected:
                raise ValueError('input_leg_not_in_declared_physical_net_inventory')
            affected=selected
            result['explicit_input_leg_scope']=True
        result.update(applicable=bool(affected), expected_legs=[list(k) for k in sorted(affected)])
        if not affected:
            result.update(ok=True, reason="no_affected_typed_sense_leg")
            return result

        def one(report, category, key):
            found = [row for row in report[category]["details"]
                     if (row["input_ref"], row["leg"]) == key]
            if len(found) != 1:
                raise ValueError("missing_or_duplicate_"+category+"_leg")
            return found[0]

        def demand_key(row):
            return json.dumps({k: row[k] for k in ("input_ref", "leg", "net", "start", "end")}, sort_keys=True)

        expected = sorted(demand_key(d) for d in demands if (d["input_ref"], d["leg"]) in affected)
        checked_demands = [d for d in after["same_net_connectivity"]["details"]
                           if (d["input_ref"], d["leg"]) in affected]
        if (sorted(demand_key(d) for d in checked_demands) != expected
                or any(d.get("ok") is not True for d in checked_demands)):
            raise ValueError("affected_sense_copper_demand_not_verified")
        for key in sorted(affected):
            old = one(before, "clipped_isolation", key)
            new = one(after, "clipped_isolation", key)
            old_proof, proof = old.get("native", {}), new.get("native", {})
            declared = inventory(after)[key[0]]
            path = declared["selected"][key[1]]
            source_terminal = dict(ref=path["anchor_ref"], pad=path["anchor_pad"], net=path["anchor_net"])
            sense_terminal = (dict(ref=path["series"][-1]["ref"], pad=path["series"][-1]["anchor_pad"],
                                   net=path["anchor_net"]) if path["series"] else
                              dict(ref=key[0], pad=declared["pins"][0 if key[1] == "p" else 1],
                                   net=path["anchor_net"]))
            def physical(pad):
                return {field: pad[field] for field in
                        ("ref", "pad", "net", "uuid", "footprint_uuid", "position_nm")}
            for report, row in ((before, old), (after, new)):
                native = row.get("native", {})
                for field, wrapper, terminal in (("source", "source_pad", source_terminal),
                                                  ("sense", "sense_terminal", sense_terminal)):
                    actual = physical(native[field])
                    if (actual != physical(row[wrapper])
                            or any(actual[k] != v for k, v in terminal.items())):
                        raise ValueError("clipped_proof_does_not_match_typed_physical_leg")
                domain = report["authority"][path["anchor_net"]]
                omitted = one(report, "shunt_pad_omitted", key)
                expected_authority = sorted(json.dumps(physical(p), sort_keys=True)
                                            for p in omitted["authority_excluding_cut"])
                actual_authority = sorted(json.dumps(physical(p), sort_keys=True) for p in native["authority"])
                required_refs = set(domain["source_refs"]) | set(domain["sink_refs"])
                if (domain.get("complete") is not True or required_refs != set(domain["authority_refs"])
                        or actual_authority != expected_authority
                        or {p["ref"] for p in native["authority"]} != required_refs-{path["anchor_ref"]}
                        or any(p["net"] != path["anchor_net"] for p in native["authority"])):
                    raise ValueError("clipped_proof_does_not_match_physical_current_authority")
            for field in ("source", "sense", "authority"):
                if not old_proof.get(field) or old_proof[field] != proof.get(field):
                    raise ValueError("physical_sense_authority_inventory_changed_or_unknown")
            if (new.get("ok") is not True or proof.get("ok") is not True
                    or proof.get("complete") is not True or proof.get("tracks_clipped") is not True
                    or proof.get("exact_linear_identity_verified") is not True):
                raise ValueError("affected_copper_cut_isolation_not_verified")
            if one(after, "inner_departure", key).get("ok") is not True:
                raise ValueError("affected_inner_departure_not_verified")
            result["checked"] += 1
        result.update(ok=True, reason="affected_typed_legs_geometrically_verified")
    except (KeyError, TypeError, ValueError) as exc:
        result["reasons"].append(str(exc))
        result["reason"] = "scoped_kelvin_admission_refused"
    return result


def main(argv=None):
    import cec_force_current as force
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--board-hint", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    try:
        destination = Path(args.report).resolve()
        temporary = destination.with_name(destination.name+".tmp-"+str(os.getpid()))

        def guard():
            protected = force._protected_paths(args.board, args.board_hint)
            force._check_output(destination, protected)
            force._check_output(temporary, protected)
            if temporary.exists() or temporary.is_symlink():
                raise ValueError("report temporary path already exists")

        guard()  # Must precede loading or diagnostic work, and the eventual write.
        result = replay(args.board, board_hint=args.board_hint, timeout_s=args.timeout_s)
        guard()
        destination.parent.mkdir(parents=True, exist_ok=True)
        force._write(destination, result)
        print(json.dumps(dict(report=str(destination), complete=result["complete"],
            stop=result["stop"], identity_stable=result["identity_stable"],
            kelvin_isolation_qualified=None, release_authority=False)))
        return 0 if result["complete"] and result["identity_stable"] else 2
    except Exception as exc:
        print("force sense evidence refused: "+str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
