"""Bounded additive, trace-rated force repair; never an ordinary Kelvin router.

``diagnose`` is read-only. ``propose`` runs a private, supervised candidate and
returns its path ONLY as a proposal: the caller owns atomic promotion. Every
original serialized primitive (including UUID, locks, pads, groups and filled
zones) must survive exactly. No pruning, resizing, placement, rule mutation,
via-current assumption, pour-capacity credit or parallel-current sharing is
authorized here. Fully owned nets must be supplied explicitly by the caller;
saved/enclosing pour-first ownership is additionally enforced.

This first constructive portfolio is deliberately planar and full-width.
Guarded native canonical/optional maze paths join authority pads or already
rated tracks. A failure is a bounded search refusal, NOT a physical no-path
certificate. The diagnostic unit-cost minimum vertex cut identifies thin
conductors in the trace graph; it is NOT an electrical current allocation.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from contextlib import contextmanager
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import time


SCHEMA = 1
SCOPE = "full_width_trace_only_no_via_zone_or_parallel_capacity_credit"
# A proposal contact-interiority guard, not a current-carrying neckdown size.
SURFACE_CONTACT_INSET_NM = 50_000
SIDECARS = (".kicad_pro", ".kicad_prl", ".kicad_dru", ".pourplan.json",
            ".railreport.json", ".cellreport.json", ".pourfirst-state.json",
            ".priority-replacements.json", ".route-lineage.json",
            ".authored-prefix.json", ".power-prefix.json")
MAX_UNFAMILIAR_SIDECARS = 64
MAX_SAVED_FAMILY_BYTES = 64*1024*1024


class SavedFamilyRefused(ValueError):
    def __init__(self, reason, **evidence):
        self.reason = reason
        self.evidence = dict(reason=reason, **evidence)
        super().__init__(reason + ": " + json.dumps(evidence, sort_keys=True))


def _bounded_digest(path, limit):
    digest, used = hashlib.sha256(), 0
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(min(1024*1024, max(1, limit-used+1)))
            if not chunk:
                return digest.hexdigest(), used
            used += len(chunk)
            if used > limit:
                raise SavedFamilyRefused("saved_family_storage_budget_exceeded",
                    path=str(path), byte_limit=limit, bytes_observed=used)
            digest.update(chunk)


def _family_file_hashes(paths):
    """Preflight the whole byte inventory, then stream under one shared cap."""
    paths = sorted(set(map(Path, paths)))
    total = sum(path.stat().st_size for path in paths if path.is_file())
    if total > MAX_SAVED_FAMILY_BYTES:
        raise SavedFamilyRefused("saved_family_storage_budget_exceeded",
            byte_limit=MAX_SAVED_FAMILY_BYTES, inventory_bytes=total)
    result, remaining = {}, MAX_SAVED_FAMILY_BYTES
    for path in paths:
        if path.is_file():
            result[str(path)], used = _bounded_digest(path, remaining)
            remaining -= used
        else:
            result[str(path)] = None
    return result


def _hash(path):
    path = Path(path)
    return _bounded_digest(path, MAX_SAVED_FAMILY_BYTES)[0] if path.is_file() else None


def _companion_inventory(path):
    """Enumerate without hashing, so the complete family can be preflighted."""
    source = Path(path).resolve()
    prefix = str(source.with_suffix(""))
    companions = {ext: source.with_suffix(ext) for ext in SIDECARS}
    unfamiliar = 0
    for name in glob.iglob(glob.escape(prefix)+".*"):
        item = Path(name)
        if item == source:
            continue
        ext = str(item)[len(prefix):]
        if ext not in companions:
            unfamiliar += 1
            if unfamiliar > MAX_UNFAMILIAR_SIDECARS:
                raise ValueError("saved-family unfamiliar companion bound exceeded")
            companions[ext] = item
    metadata = {}
    for ext, item in sorted(companions.items()):
        # One non-following metadata read, not four remote filesystem trips.
        # The complete inventory is still independently rechecked after the
        # bounded byte hashes. Neither an alias nor a disappearing unfamiliar
        # companion becomes a known absence through this optimization.
        try:
            status = item.lstat()
        except FileNotFoundError:
            if ext not in SIDECARS:
                raise ValueError("saved-family companion disappeared during inventory")
            metadata[ext] = None
            continue
        if stat.S_ISLNK(status.st_mode):
            raise ValueError("saved-family companion alias forbidden: " + str(item))
        if not stat.S_ISREG(status.st_mode):
            raise ValueError("saved-family companion is not a regular file: " + str(item))
        if status.st_nlink != 1:
            raise ValueError("saved-family companion alias forbidden: " + str(item))
        metadata[ext] = (status.st_dev, status.st_ino, status.st_size,
                         status.st_mtime_ns, status.st_ctime_ns)
    return companions, metadata


def _sidecars(path):
    """Opaque, alias-free saved-family inventory, including known absences.

    Unfamiliar same-stem companions are preserved, not interpreted. Their
    appearance/removal changes the inventory and invalidates older evidence.
    A hardlink/symlink or non-file companion is not portable private ownership.
    """
    source = Path(path).resolve()
    companions, metadata = _companion_inventory(source)
    hashes = _family_file_hashes([source, *companions.values()])
    if _companion_inventory(source) != (companions, metadata):
        raise ValueError("saved-family companion changed during inventory")
    return {ext: hashes[str(item)] for ext, item in sorted(companions.items())}


def _family(path, board_hint=None):
    import cec_board_policy
    import cec_facts
    import cec_operation_budget
    path = Path(path).resolve()
    companions, metadata = _companion_inventory(path)
    files = [path, *companions.values()]
    # Constraint parameters can override their Python registry defaults.
    # Bind even absence: later compilation must invalidate older evidence.
    files.append((Path(cec_facts.COMPILED_ROOT) / "params.json").resolve())
    # The dimension resolver permits one differently named sibling project.
    # Bind its identity even for read-only diagnosis; constructive admission
    # refuses that fallback until a complete project-family rebinding exists.
    if not path.with_suffix(".kicad_pro").is_file():
        files.extend(path.parent.glob("*.kicad_pro"))
    policy = cec_board_policy.policy_path(path, board_hint=(
        board_hint or os.environ.get("CEC_THERMAL_BOARD_HINT")))
    if policy:
        files.append(Path(policy).resolve())
    # The thermal hint is sometimes a different saved PCB, not a logical
    # board ID. Overlay reads its nets/profile. Include absent path-like hints
    # too, so appearance cannot silently change authority during a proposal.
    hints = [board_hint, os.environ.get("CEC_THERMAL_BOARD_HINT")]
    hints.extend(value for key, value in os.environ.items()
                 if key.startswith("CEC_")
                 and key not in cec_operation_budget.DIAGNOSTIC_OUTPUT_ENV_KEYS)
    for value in hints:
        if not value:
            continue
        raw = str(value)
        if raw.lstrip().startswith(("{", "[")):
            continue  # Structured policy values are not single file paths.
        declared = Path(raw)
        try:
            exists = declared.is_file()
        except OSError:
            exists = False
        if (exists or "/" in raw or "\\" in raw
                or declared.suffix in {".kicad_pcb", ".kicad_pro", ".json", ".yaml", ".toml"}):
            files.append(declared.resolve())
    # An enclosing freeze is authority even when it lives outside the family.
    external = os.environ.get("CEC_POURFIRST_STATE")
    if external:
        files.append(Path(external).resolve())
    hashes = _family_file_hashes(files)
    if _companion_inventory(path) != (companions, metadata):
        raise ValueError("saved-family companion changed during inventory")
    return hashes


def _code_identity():
    # Native routing/scoring import many local modules lazily. The first slice
    # deliberately overbinds the local Python tree instead of claiming that a
    # short hand-maintained list is a complete geometry/admission closure.
    root = Path(__file__).resolve().parent
    return {str(path.relative_to(root)): _hash(path)
            for path in sorted(root.rglob("*.py"))}


def _protected_paths(source, hint=None):
    root = Path(__file__).resolve().parent
    return set(_family(source, hint)) | {str(path.resolve()) for path in root.rglob("*.py")}


def _check_output(path, protected, *, candidate_directory=None):
    destination = Path(path).resolve()
    # Reserve the namespace, not just files present at the earlier snapshot.
    # Otherwise a new report named board.future-authority.json would become a
    # saved-family member only after source_unchanged had already been checked.
    for item in protected:
        source = Path(item).resolve()
        if source.suffix.lower() != ".kicad_pcb" or not destination.is_relative_to(source.parent):
            continue
        relative = destination.relative_to(source.parent).parts
        if relative and os.path.normcase(relative[0]).startswith(os.path.normcase(source.stem+".")):
            raise ValueError("report destination is protected saved-family namespace: " + str(destination))
    if str(destination) in protected:
        raise ValueError("report destination is protected input/authority/code: " + str(destination))
    # Resolving catches symlinks, but another directory entry may still name
    # the same inode. Never let a report alias an authority through a hardlink.
    if destination.exists():
        for item in protected:
            try:
                aliased = destination.samefile(item)
            except FileNotFoundError:
                continue  # Absent authority paths remain protected by name.
            if aliased:
                raise ValueError("report destination is protected input/authority/code: " + str(destination))
    if candidate_directory is not None and destination.is_relative_to(Path(candidate_directory).resolve()):
        raise ValueError("report destination is inside private candidate family: " + str(destination))


def _check_proposal_directory(directory, protected):
    destination = Path(directory).resolve()
    _check_output(destination, protected)
    # The supervisor writes failure receipts even when the native worker
    # cannot start. Reserve the entire output tree before either writer runs,
    # including currently absent paths explicitly declared as authority.
    if any(Path(item).resolve().is_relative_to(destination) for item in protected):
        raise ValueError("proposal directory contains protected input/authority/code: " + str(destination))


def _write(path, value):
    import cec_operation_budget
    cec_operation_budget.write_json(path, value)


@contextmanager
def _thermal_hint(hint):
    key = "CEC_THERMAL_BOARD_HINT"
    previous = os.environ.get(key)
    if hint:
        os.environ[key] = str(hint)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def _uid(item):
    return str(item.m_Uuid.AsString())


def _point(item):
    point = item.GetPosition()
    return [int(point.x), int(point.y)]


def _pad_row(pad):
    return dict(uuid=_uid(pad), ref=str(pad.GetParentFootprint().GetReference()),
                pad=str(pad.GetNumber()), position_nm=_point(pad))


def _item_key(item):
    # Cloned footprint children can share UUIDs; physical terminal identity
    # must not silently merge two disconnected source/sink lands.
    if item.GetClass() == "PAD":
        return ("pad", str(item.GetParentFootprint().GetReference()),
                str(item.GetNumber()), *_point(item), _uid(item))
    return ("copper", _uid(item))


def _authority_pads(board, net, domain):
    refs = set(domain.get("source_refs") or ()) | set(domain.get("sink_refs") or ())
    return sorted((pad for fp in board.GetFootprints()
                   if str(fp.GetReference()) in refs for pad in fp.Pads()
                   if str(pad.GetNetname()) == net), key=_item_key)


def _components(pads, items):
    """A private native graph, no mutation or discarded SWIG objects."""
    import pcbnew
    conn = pcbnew.CONNECTIVITY_DATA()
    for item in [*pads, *items]:
        if not conn.Add(item):
            raise RuntimeError("native rated connectivity rejected " + _uid(item))
    remaining = {_item_key(pad): pad for pad in pads}
    components, members = [], []
    while remaining:
        seed = remaining[min(remaining)]
        connected = {_item_key(seed)} | {_item_key(item) for item in conn.GetConnectedItems(seed)}
        own = sorted(set(remaining) & connected)
        components.append([_pad_row(remaining[key]) for key in own])
        members.append(connected)
        for key in own:
            remaining.pop(key)
    return dict(available=bool(pads), connected=bool(pads) and len(components) == 1,
                components=components, authority_pad_count=len(pads)), members


def _collides(first, second, layers=None):
    common = set(first.GetLayerSet().CuStack()) & set(second.GetLayerSet().CuStack())
    if layers is not None:
        common &= set(layers)
    return any(first.GetEffectiveShape(layer).Collide(
        second.GetEffectiveShape(layer), 0) for layer in common)


def _minimum_cut(pads, tracks, thin, rated, *, max_items=256):
    """Exact unit-cost thin-conductor vertex cut on native shape contacts.

    Native connectivity supplies the terminal partition independently. Cut
    construction is bounded; unavailable cut detail never grants ownership.
    """
    nodes = [*pads, *tracks]
    if len(nodes) > max_items:
        return dict(available=False, reason="cut_graph_item_budget", limit=max_items)
    if rated["connected"]:
        return dict(available=True, reason="rated_path_exists", thin_cut_uuids=[], value=0)
    if not pads:
        return dict(available=False, reason="no_authority_pads")
    thin = set(thin)
    adjacency = []
    for i, first in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            if _collides(first, nodes[j]):
                adjacency.append((i, j))
    inf = len(thin) + 1
    best = None
    # All source AND sink terminals must inhabit one rated component. A cut
    # separating any terminal from the first witnesses failure of that claim.
    for target in range(1, len(pads)):
        size = 2 * len(nodes)
        capacity = [{} for _ in range(size)]

        def edge(a, b, value):
            capacity[a][b] = capacity[a].get(b, 0) + value
            capacity[b].setdefault(a, 0)

        for i, item in enumerate(nodes):
            edge(2*i, 2*i+1, 1 if _uid(item) in thin else inf)
        for a, b in adjacency:
            edge(2*a+1, 2*b, inf)
            edge(2*b+1, 2*a, inf)
        source, sink, total = 0, 2*target+1, 0
        while total < inf:
            parent = {source: None}
            queue = deque([source])
            while queue and sink not in parent:
                current = queue.popleft()
                for nxt, value in capacity[current].items():
                    if value and nxt not in parent:
                        parent[nxt] = current
                        queue.append(nxt)
            if sink not in parent:
                break
            amount, node = inf, sink
            while parent[node] is not None:
                amount = min(amount, capacity[parent[node]][node])
                node = parent[node]
            node = sink
            while parent[node] is not None:
                previous = parent[node]
                capacity[previous][node] -= amount
                capacity[node][previous] += amount
                node = previous
            total += amount
        if total >= inf:
            continue
        reached, queue = {source}, deque([source])
        while queue:
            for nxt, value in capacity[queue.popleft()].items():
                if value and nxt not in reached:
                    reached.add(nxt)
                    queue.append(nxt)
        cut = sorted(_uid(item) for i, item in enumerate(nodes)
                     if _uid(item) in thin and 2*i in reached and 2*i+1 not in reached)
        row = dict(available=True, value=total, thin_cut_uuids=cut,
                   terminal_a=_pad_row(pads[0]), terminal_b=_pad_row(pads[target]),
                   reason="thin_conductor_cut" if total else "trace_graph_already_open")
        if best is None or (total, cut) < (best["value"], best["thin_cut_uuids"]):
            best = row
    return dict(best or dict(available=False, reason="native_shape_graph_disagreement"),
                cost_basis="one_per_undersized_conductor_not_amps",
                physical_no_path_proof=False)


def _graph(board, net, domain, contract, project, *, native_enclosure_proposals=(),
           include_bypass_terminals=False):
    import pcbnew
    import cec_fab_profile as fab
    pads = _authority_pads(board, net, domain)
    if type(include_bypass_terminals) is not bool:
        raise ValueError("explicit_boolean_bypass_terminal_mode_required")
    bypass = None
    if include_bypass_terminals:
        import cec_force_bypass_terminals as terminals
        bypass = terminals.select(board, net)
        selected = set(bypass["pad_uuids"])
        by_key = {_item_key(p):p for p in pads}
        by_key.update({_item_key(p):p for fp in board.GetFootprints() for p in fp.Pads()
                       if _uid(p) in selected})
        pads = [by_key[k] for k in sorted(by_key)]
    required = {}
    for layer, width in contract["required_by_layer_mm"].items():
        required[layer] = max(float(width), float(project.get("track_width") or 0),
                             float((project.get("track_width_by_layer_mm") or {}).get(layer) or 0))
    tracks, kept, thin, excluded = [], [], [], []
    for item in board.GetTracks():
        if str(item.GetNetname()) != net:
            continue
        if item.GetClass() == "PCB_VIA":
            excluded.append(dict(uuid=_uid(item), reason="via_capacity_not_credited"))
            continue
        if item.Type() not in (pcbnew.PCB_TRACE_T, pcbnew.PCB_ARC_T):
            excluded.append(dict(uuid=_uid(item), reason="unsupported_copper_kind"))
            continue
        layer = fab.COPPER_LAYER_IDS.get(int(item.GetLayer()), board.GetLayerName(item.GetLayer()))
        need = required.get(layer)
        if need is None or not math.isfinite(need) or need <= 0:
            raise ValueError("missing current width for " + str(layer))
        tracks.append(item)
        if item.GetWidth() < math.ceil(need * 1e6):
            thin.append(dict(uuid=_uid(item), layer=layer, actual_mm=item.GetWidth()/1e6,
                             required_mm=need, locked=bool(item.IsLocked()),
                             start_nm=[item.GetStart().x, item.GetStart().y],
                             end_nm=[item.GetEnd().x, item.GetEnd().y]))
        else:
            kept.append(item)
    # Opt-in to an independent contour owner's receiving, never to arbitrary
    # zone area or a caller's cached 'ok' flag. Each prior track-shaped resident
    # subset must be re-proved inside ACTUAL native filled copper on this board
    # and independently satisfy this checker's current/project width authority.
    # Default additive force repair remains unchanged and creates no zones.
    enclosure_evidence = []
    if native_enclosure_proposals:
        import cec_rectilinear_copper as contour
        if (not isinstance(native_enclosure_proposals,(tuple,list))
                or len(native_enclosure_proposals)>64):
            raise ValueError("native_enclosure_receipt_inventory_bound")
        seen={_uid(t) for t in board.GetTracks()}
        enclosure_deadline=time.monotonic()+2.0
        for request in native_enclosure_proposals:
            if not isinstance(request,dict) or not isinstance(request.get("proposal"),dict):
                raise ValueError("invalid_native_enclosure_request")
            proposal=request["proposal"]
            if proposal.get("net")!=net:
                continue
            remaining=enclosure_deadline-time.monotonic()
            if remaining<=0:
                raise ValueError("native_enclosure_graph_deadline")
            witness,proof=contour.enclosed_track_witnesses(board,proposal,
                request.get("zone_uuid"),timeout_s=min(2.0,remaining),
                regional_source=request.get("regional_source"))
            for item in witness:
                uid=_uid(item)
                if uid in seen:
                    raise ValueError("ambiguous_native_enclosure_witness_identity")
                seen.add(uid)
                layer=fab.COPPER_LAYER_IDS.get(int(item.GetLayer()),board.GetLayerName(item.GetLayer()))
                need=required.get(layer)
                if need is None or item.GetWidth()<math.ceil(need*1e6):
                    raise ValueError("native_enclosure_witness_below_current_width")
                tracks.append(item)
                kept.append(item)
            enclosure_evidence.append(proof)
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and str(zone.GetNetname()) == net:
            excluded.append(dict(uuid=_uid(zone), reason="zone_capacity_not_credited"))
    proof, members = _components(pads, kept)
    trace_proof, _ = _components(pads, tracks)
    result = dict(required_by_layer_mm=required, rated_connectivity=proof,
                trace_connectivity=trace_proof, undersized_segments=thin,
                excluded_capacity=excluded,
                cut=_minimum_cut(pads, tracks, [_row["uuid"] for _row in thin], proof))
    if bypass is not None:
        result["bypass_terminal_selection"] = bypass
    if enclosure_evidence:
        result["native_enclosure_evidence"] = enclosure_evidence
        result["enclosure_basis"] = ("exact_real_source_tracks_retained_without_extra_zone_capacity"
            if any(row.get('retained_native_track_material_used') for row in enclosure_evidence)
            else "replayed_full_native_track_envelopes_inside_filled_copper_no_new_capacity")
    return result, (pads, kept, members)


def _ownership(board_path, immutable_nets):
    """Explicit whole-net ownership is distinct from locked-item prefixes."""
    import cec_fr
    owners = {str(net): ["caller_fully_owned_net"] for net in immutable_nets}
    paths = [Path(board_path).with_suffix(".pourfirst-state.json")]
    if os.environ.get("CEC_POURFIRST_STATE"):
        paths.append(Path(os.environ["CEC_POURFIRST_STATE"]))
    for path in dict.fromkeys(paths):
        if not path.exists():
            if str(path) == os.environ.get("CEC_POURFIRST_STATE"):
                raise ValueError("declared pour-first authority is absent: " + str(path))
            continue
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            raise ValueError("invalid pour-first ownership: " + str(path))
        if "frozen_nets" in state and (not isinstance(state["frozen_nets"], list)
                or any(not isinstance(net, str) or not net for net in state["frozen_nets"])):
            raise ValueError("invalid frozen_nets ownership: " + str(path))
        for net in cec_fr._frozen_power_state_parts(state)[2]:
            owners.setdefault(str(net), []).append("pour_first:" + str(path))
    return owners


def _project_authority(board_path):
    import cec_route_dimensions
    expected = Path(board_path).resolve().with_suffix(".kicad_pro")
    try:
        resolved = cec_route_dimensions.project_path(board_path)
    except cec_route_dimensions.DimensionContractError as exc:
        return dict(ok=False, reason="project_authority_ambiguous_or_invalid", error=str(exc))
    exact = resolved is None or resolved.resolve() == expected
    return dict(ok=exact, resolved=str(resolved.resolve()) if resolved else None,
                expected=str(expected),
                reason=None if exact else "project_authority_outside_board_family")


def force_route_operation_admission(board, requested_nets, *, board_hint,
                                    immutable_nets, authority_path=None,
                                    complete_frozen_prefix=False, include_bypass_terminals=False):
    """Typed capability adapter; caller must NOT prune before this operator.

    Pass fully-owned pair/power nets, NOT every net containing a locked prefix.
    ``authority_path`` identifies the saved family when board_hint is a logical
    design ID. A complete domain and established current-width basis are
    necessary; capability never claims geometric routability or qualification.
    """
    import cec_current_topology as topology
    if type(complete_frozen_prefix) is not bool:
        raise ValueError('explicit_boolean_frozen_prefix_completion_mode_required')
    if type(include_bypass_terminals) is not bool:
        raise ValueError('explicit_boolean_bypass_terminal_mode_required')
    requested = sorted({str(net) for net in requested_nets if net})
    if isinstance(immutable_nets, (str, bytes, dict)):
        raise ValueError("immutable_nets must be an explicit collection of net names")
    source = authority_path or str(board.GetFileName() or board_hint)
    project = _project_authority(source)
    domains = topology.board_current_domains(board, board_hint=board_hint)
    contracts = topology.route_width_contracts(board, board_hint=board_hint)
    owners = _ownership(source, immutable_nets)
    refusals = {}
    frozen_completion = {}
    for net in requested:
        domain = domains.get(net) or {}
        if net in owners:
            if complete_frozen_prefix:
                import cec_frozen_prefix_completion as completion
                frozen_completion[net] = completion.allowance(board, source, net, owners[net])
            if not frozen_completion.get(net, {}).get('eligible'):
                refusals[net] = dict(reason="immutable_net_addition_forbidden", owners=owners[net],
                    frozen_completion=frozen_completion.get(net))
                continue
        if not project["ok"]:
            refusals[net] = dict(project)
        elif (domain.get("complete") is not True or not domain.get("source_refs")
              or not domain.get("sink_refs") or domain.get("missing_refs")):
            refusals[net] = dict(reason="complete_current_domain_required", domain=domain)
        elif net not in contracts:
            refusals[net] = dict(reason="current_width_authority_unavailable", domain=domain)
    return dict(schema=SCHEMA, operation="force_current_additive", eligible=not refusals,
                requested_nets=requested, eligible_nets=sorted(set(requested)-set(refusals)),
                unsupported_nets=sorted(refusals), refusals=refusals,
                fully_owned_nets=sorted(owners),
                incomplete_frozen_prefix_additions=frozen_completion,
                complete_frozen_prefix_mode=complete_frozen_prefix,
                include_bypass_terminals_mode=include_bypass_terminals,
                project_authority=project,
                reason="force_current_capable" if not refusals else "force_current_ownership_or_authority_refusal",
                retryable=False, physical_feasibility="not_assessed", release_authority=False,
                qualification_scope=SCOPE)


def _terminal_launch_pockets(board, net, domain, required_by_layer_mm, source, *, deadline):
    """Read-only, bounded refusal evidence; never a route or rating exception."""
    import pcbnew
    import cec_fab_profile as fab
    import cec_fr
    import cec_terminal_launch_pocket as pocket
    enabled = set(board.GetEnabledLayers().CuStack())
    pads = [pad for pad in _authority_pads(board, net, domain)
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not pad.HasHole()
            and len(set(pad.GetLayerSet().CuStack()) & enabled) == 1]
    pads.sort(key=lambda pad: json.dumps(_pad_row(pad), sort_keys=True))
    spec = cec_fr._project_netclass_resolver(source)(net) or {}
    clearance = math.ceil(max(float(spec.get("clearance") or 0),
                             board.GetDesignSettings().m_MinClearance/1e6)*1e6)
    rows = []
    for pad in pads[:2]:
        layer = next(iter(set(pad.GetLayerSet().CuStack()) & enabled))
        name = fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer))
        width = required_by_layer_mm.get(name)
        if type(width) not in (float, int) or not math.isfinite(width) or width <= 0:
            rows.append(dict(terminal=_pad_row(pad), status="unknown", certified=None,
                             reason="rated_width_authority_unavailable"))
            continue
        try:
            rows.append(pocket.audit(board, pad, layer, width_nm=math.ceil(width*1e6),
                clearance_nm=clearance, contact_inset_nm=SURFACE_CONTACT_INSET_NM,
                deadline=deadline))
        except ValueError as exc:
            rows.append(dict(terminal=_pad_row(pad), status="unknown", certified=None,
                reason="launch_pocket_contract_outside_supported_bounds", detail=str(exc)))
    return dict(scope="bounded_planar_authority_terminal_refusal_diagnostic",
        selected_terminal_count=len(rows), eligible_terminal_count=len(pads),
        terminal_inventory_truncated=len(pads)>2, max_terminals=2, rows=rows,
        current_authority=dict(net=net, amps=domain.get("amps"),
            source=domain.get("source"), required_by_layer_mm=required_by_layer_mm),
        certified_pocket_count=sum(row.get("certified") is True for row in rows),
        electrical_capacity_qualified=False, physical_no_path_proof=False,
        release_authority=False)


def diagnose(board_path, requested_nets, *, board_hint=None, include_launch_pockets=False):
    """Read-only native capacity/cut evidence for explicit complete domains."""
    import pcbnew
    import cec_current_topology as topology
    import cec_constraints
    import cec_fr
    started, source = time.monotonic(), str(Path(board_path).resolve())
    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or board_hint or source
    before, code = _family(source, hint), _code_identity()
    with _thermal_hint(hint):
        board = pcbnew.LoadBoard(source)
        domains = topology.board_current_domains(board, board_hint=hint)
        contracts = topology.route_width_contracts(board, board_hint=hint)
        resolver = cec_fr._project_netclass_resolver(source)
        results = {}
        launch_deadline = time.monotonic()+3
        for net in sorted(set(requested_nets)):
            domain = domains.get(net) or {}
            if (domain.get("complete") is not True or not domain.get("source_refs")
                    or not domain.get("sink_refs") or domain.get("missing_refs")):
                results[net] = dict(qualified=False, reason="complete_current_domain_required", domain=domain)
                continue
            if net not in contracts:
                results[net] = dict(qualified=False, reason="current_width_authority_unavailable", domain=domain)
                continue
            graph, _ = _graph(board, net, domain, contracts[net], resolver(net) or {})
            native = topology.authority_connectivity(board, net, board_hint=hint)
            width = cec_constraints.CHECKERS["trace-width-high-current"](
                board, source, {"current_domain_include_nets": [net]})
            qualified = (native.get("connected") is True and width[0] is True
                         and graph["rated_connectivity"]["connected"] is True)
            results[net] = dict(graph, domain=domain, width_contract=contracts[net],
                native_connectivity=native,
                current_width=dict(ok=width[0], detail=width[1], evidence=width[2] if len(width)>2 else None),
                qualified=qualified, reason="rated_input_prefix" if qualified else "rated_force_path_unproven")
            if include_launch_pockets and not qualified:
                results[net]["terminal_launch_pockets"] = _terminal_launch_pockets(
                    board, net, domain, graph["required_by_layer_mm"], source,
                    deadline=launch_deadline)
    after, code_after = _family(source, hint), _code_identity()
    return dict(schema=SCHEMA, operation="force_current_diagnosis", qualification_scope=SCOPE,
                source=source, source_family_before=before, source_family_after=after,
                source_unchanged=before == after, code_before=code, code_after=code_after,
                code_unchanged=code == code_after, domains=results,
                elapsed_s=round(time.monotonic()-started, 6), release_authority=False,
                physical_no_path_proof=False)


def _preservation_snapshot(path):
    """All original native geometry/metadata, not just a locked-net subset."""
    import cec_copper_echo as sexpr
    root = sexpr._parse(sexpr._TOKEN.findall(Path(path).read_text()))
    by_id, fixed = {}, []
    for node in root[1:]:
        if not isinstance(node, list):
            fixed.append(sexpr._freeze([node]))
            continue
        fields = {child[0]: child for child in node[1:] if isinstance(child, list) and child}
        uid = fields.get("uuid")
        if uid and len(uid) == 2:
            key = uid[1].strip('"')
            if key in by_id:
                raise ValueError("duplicate original native UUID")
            by_id[key] = (node[0], sexpr._freeze(node))
        elif node[0] not in {"generator", "generator_version", "version"}:
            fixed.append(sexpr._freeze(node))
    return by_id, Counter(fixed)


def preservation(source, candidate, *, net, allow_ground_refill=False):
    """Only requested-net segments; optional independently replayed GND fill."""
    import cec_copper_echo as sexpr
    old, fixed = _preservation_snapshot(source)
    new, new_fixed = _preservation_snapshot(candidate)
    missing = sorted(set(old)-set(new))
    modified = sorted(uid for uid in old.keys() & new.keys() if old[uid] != new[uid])
    added = sorted(set(new)-set(old))
    _, rows, _ = sexpr._read(candidate)
    new_rows = {row["uuid"].strip('"'): row for row in rows}
    illegal = [uid for uid in added if new[uid][0] != "segment"
               or uid not in new_rows or new_rows[uid]["net"].strip('"') != net]
    old_sidecars, new_sidecars = _sidecars(source), _sidecars(candidate)
    changed_sidecars = sorted(ext for ext in old_sidecars.keys() | new_sidecars.keys()
        if old_sidecars.get(ext) != new_sidecars.get(ext)
        or (ext in old_sidecars) != (ext in new_sidecars))
    if type(allow_ground_refill) is not bool:
        raise ValueError("explicit_force_ground_refill_mode_required")
    allowed_ground, ground_receiving = [], None
    if allow_ground_refill and modified and not (missing or illegal or fixed != new_fixed or changed_sidecars):
        # A track-only transaction may alter existing ground antipads, not
        # unrelated power fill, outlines, settings or primitive ownership.
        # Independently reconstruct the source plus its exact additions and
        # replay only ground fill; an arbitrary changed ground polygon cannot
        # acquire permission from its name or from unchanged DRC counts.
        import cec_additive_route_receiving as additive
        ground_receiving = additive.receive(source, candidate, timeout_s=10.)
        if ground_receiving.get("ok") is True and ground_receiving.get("complete") is True:
            allowed_ground = sorted(row["uuid"] for row in
                ground_receiving["allowed_original_changes"] if row["kind"] == "existing_ground_fill")
    forbidden_modified = sorted(set(modified)-set(allowed_ground))
    return dict(ok=not (missing or forbidden_modified or illegal or fixed != new_fixed or changed_sidecars),
                original_items=len(old), missing_uuids=missing, modified_uuids=modified,
                added_uuids=added, illegal_additions=illegal,
                forbidden_modified_uuids=forbidden_modified,
                allowed_ground_fill_uuids=allowed_ground, ground_refill_receiving=ground_receiving,
                board_settings_unchanged=fixed == new_fixed, changed_sidecars=changed_sidecars,
                source_sidecars=old_sidecars, candidate_sidecars=new_sidecars,
                contract=("all_original_primitives_exact_except_independently_replayed_ground_fill"
                    if allow_ground_refill else "all_original_uuid_primitives_and_sidecars_exact"))


def _finalize_current_segments(board, source, candidate):
    """Finalize additive tracks without reopening any protected power owner.

    The constructor adds only constant-width straight tracks. It owns no new
    pad, barrel, power zone or contour. Recompiling every existing zone can
    reject a valid prefix because an unrelated historic overlapping fill
    requires its own source-preserving owner; it can also mutate old power
    evidence. Use the same independently received ground-only transaction
    as other additive constructors. Current, Kelvin, DRC and final saved
    identity gates still apply separately and never become optional.
    """
    import cec_additive_route_receiving as additive
    import cec_field_coupling as field
    ground = additive._ground_refill(board)
    field._save_field_snapshot(board, candidate)
    replay = additive.receive(source, candidate, timeout_s=10.)
    if replay.get("ok") is not True or replay.get("complete") is not True:
        raise ValueError("force_exact_additive_ground_refill_not_received:"+str(replay.get("errors")))
    return dict(stable=True, scope="exact_additive_tracks_ground_only_native_replay",
        ground_refilled=ground, receiving=replay, protected_power_fill_recompiled=False,
        current_qualified=False, release_authority=False)


def _copy_family_file(source, destination, byte_limit):
    """Bound actual writes too, if an opaque source grows after preflight."""
    used = 0
    with Path(source).open("rb") as src, Path(destination).open("xb") as dst:
        while True:
            chunk = src.read(min(1024*1024, max(1, byte_limit-used+1)))
            if not chunk:
                break
            used += len(chunk)
            if used > byte_limit:
                raise SavedFamilyRefused("saved_family_storage_budget_exceeded",
                    path=str(source), byte_limit=byte_limit, bytes_observed=used)
            dst.write(chunk)
    shutil.copystat(source, destination)
    return used


def _copy_family(source, directory):
    source = Path(source).resolve()
    companions, board_hash = _sidecars(source), _hash(source)
    project = _project_authority(source)
    if not project["ok"]:
        raise ValueError(project["reason"])
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    destination = directory / source.name
    remaining = MAX_SAVED_FAMILY_BYTES-_copy_family_file(source, destination, MAX_SAVED_FAMILY_BYTES)
    for ext, digest in companions.items():
        companion = source.with_suffix(ext)
        if digest is not None:
            remaining -= _copy_family_file(companion, destination.with_suffix(ext), remaining)
    if (_sidecars(source) != companions or _sidecars(destination) != companions
            or _hash(source) != board_hash or _hash(destination) != board_hash):
        raise ValueError("saved-family changed during private copy")
    return destination


def _leaf_obstacles(board, net, domain, graph):
    """Protect measurement/local pads and their thin branches as same-net obstacles.

    Flood only through thin conductors, stopping at rated copper/authority
    pads. This may conservatively fence an entire thin trunk; it does not
    authorize guessing where its authored Kelvin tap should move.
    """
    bypass_ids = set(graph.get("bypass_terminal_selection", {}).get("pad_uuids", ()))
    pads = [pad for fp in board.GetFootprints()
            if str(fp.GetReference()) not in set(domain["authority_refs"])
            for pad in fp.Pads() if str(pad.GetNetname()) == net and _uid(pad) not in bypass_ids]
    thin_ids = {row["uuid"] for row in graph["undersized_segments"]}
    thin = [track for track in board.GetTracks() if _uid(track) in thin_ids]
    protected, pending = list(pads), list(pads)
    while pending:
        item = pending.pop()
        touching = [track for track in thin if _collides(item, track)]
        ids = {_uid(track) for track in touching}
        thin = [track for track in thin if _uid(track) not in ids]
        protected.extend(touching)
        pending.extend(touching)
    return protected


def _anchors(pads, kept, members):
    items = {_item_key(item): item for item in [*pads, *kept]}
    result = []
    for component, ids in enumerate(members):
        unique = {}
        for key in sorted(ids & items.keys()):
            item = items[key]
            if item.GetClass() == "PAD":
                points = [item.GetPosition()]
            else:
                a, b = item.GetStart(), item.GetEnd()
                # A midpoint is native copper access, never an off-shape arc chord.
                points = [a, b]
                if item.GetClass() == "PCB_TRACK":
                    import pcbnew
                    points.append(pcbnew.VECTOR2I((a.x+b.x)//2, (a.y+b.y)//2))
            for point in points:
                layers = tuple(int(layer) for layer in item.GetLayerSet().CuStack())
                unique[(point.x, point.y, layers)] = dict(
                    component=component, point=[point.x, point.y], layers=layers, uuid=_uid(item),
                    kind="pad_center" if item.GetClass() == "PAD" else "rated_track",
                    pad=_pad_row(item) if item.GetClass() == "PAD" else None)
        result.extend(unique[key] for key in sorted(unique))
    return result


def _spread_points(points, center, limit):
    """Bounded deterministic spatial diversity, not a nearest-corner monopoly."""
    remaining = {tuple(point) for point in points}
    selected = []
    while remaining and len(selected) < limit:
        if not selected:
            point = min(remaining, key=lambda p: (math.dist(p, center), p))
        else:
            point = min(remaining, key=lambda p: (
                -min(math.dist(p, old) for old in selected), math.dist(p, center), p))
        selected.append(point)
        remaining.remove(point)
    return [list(point) for point in selected]


def _native_track_rule_areas(board, *, cache=None):
    """Native track permissions, independent of net and copper clearance.

    The force transaction never moves a footprint or edits a rule area, so its
    caller-owned cache is valid while additive tracks are constructed. Native
    holes/curves stay native; absent or invalid polygon evidence cannot clear a
    path. This does not replace saved-board DRC.
    """
    key = ("force_native_track_rule_areas",)
    if cache is not None and key in cache:
        return cache[key]
    try:
        enabled = set(board.GetEnabledLayers().CuStack())
        candidates = list(board.Zones())
        for fp in board.GetFootprints():
            candidates.extend(fp.Zones())
        if len(candidates) > 4096:
            raise ValueError("native_track_rule_area_inventory_budget")
        rows, seen = [], {}
        for zone in candidates:
            layers = tuple(sorted(set(zone.GetLayerSet().CuStack()) & enabled))
            if not layers or not zone.GetIsRuleArea() or not zone.GetDoNotAllowTracks():
                continue
            native = zone.Outline()
            if native.OutlineCount() <= 0 or native.Area() <= 0:
                raise ValueError("native_track_rule_area_empty_geometry")
            uid = _uid(zone)
            signature = (native.Format(), layers)
            if not uid or uid in seen and seen[uid] != signature:
                raise ValueError("native_track_rule_area_ambiguous_identity")
            if uid in seen:
                continue
            seen[uid] = signature
            rows.append(dict(zone=zone, shape=native, layers=layers,
                identity=dict(kind="native_track_rule_area", uuid=uid,
                    name=str(zone.GetZoneName()),
                    layers=[str(board.GetLayerName(layer)) for layer in layers])))
    except (AttributeError, TypeError, RuntimeError) as exc:
        raise ValueError("native_track_rule_area_geometry_unavailable") from exc
    if cache is not None:
        cache[key] = rows
    return rows


def _native_track_rule_hits(board, shape, layer, *, cache=None):
    """Test the entire actual-width capsule, including round endpoint caps."""
    return [dict(row["identity"]) for row in _native_track_rule_areas(board, cache=cache)
            if layer in row["layers"] and row["shape"].Collide(shape, 0)]


def _launch_refusal(board, point, layer, width, clearance_nm, leaves, nc, cache):
    """Necessary full-width endpoint guard shared by both access menus."""
    import pcbnew
    import cec_fr
    if not cec_fr._edge_leg_clear(board, point, point, math.ceil(width/2)):
        return "outline"
    if _native_track_rule_hits(board, pcbnew.SHAPE_SEGMENT(point, point, width), layer, cache=cache):
        return "native_track_rule_area"
    zones, copper = cec_fr._foreign_shape_indexes(board, layer, {nc}, cache=cache)
    if not cec_fr._snapshot_foreign_clear(point, point, width, clearance_nm, zones, copper):
        return "foreign_copper_or_hole"
    if any(leaf.IsOnLayer(layer) and leaf.GetEffectiveShape(layer).Collide(
            pcbnew.SHAPE_SEGMENT(point, point, width), 0) for leaf in leaves):
        return "same_net_monitor_or_local_branch"
    return None


def _screen_anchors(board, anchors, graph, allowed_layers, *, clearance_nm, leaves, nc, deadline):
    """Screen legacy endpoints before either menu spends a route attempt."""
    import pcbnew
    import cec_fab_profile as fab
    result, cache, rows = [], {}, []
    count = 0

    def receipt(stop, bound=None):
        return dict(rows=rows, checked=count, input_anchors=len(anchors),
            retained_anchor_layers=len(result), rejected_anchor_layers=len(rows),
            stop=stop, bound=bound, inventory_complete=stop == "complete",
            scope="full_width_legacy_endpoint_disks_not_path_feasibility",
            physical_no_path_proof=False)

    for anchor in anchors:
        for layer in anchor["layers"]:
            name = fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer))
            if name not in allowed_layers:
                continue
            if time.monotonic() >= deadline or count >= 2048:
                return result, receipt("bounded_endpoint_budget",
                    "deadline" if time.monotonic() >= deadline else "endpoint_limit")
            count += 1
            width = math.ceil(graph["required_by_layer_mm"][name]*1e6)
            reason = _launch_refusal(board, pcbnew.VECTOR2I(*anchor["point"]), layer, width,
                                     clearance_nm, leaves, nc, cache)
            if reason is None:
                result.append(dict(anchor, layers=(layer,)))
            else:
                row = dict(anchor=anchor, layer=name, width_mm=width/1e6, reason=reason)
                if reason == "native_track_rule_area":
                    point = pcbnew.VECTOR2I(*anchor["point"])
                    row["rule_area_hits"] = _native_track_rule_hits(board,
                        pcbnew.SHAPE_SEGMENT(point, point, width), layer, cache=cache)
                rows.append(row)
    return result, receipt("complete")


def _surface_anchors(board, pads, members, graph, allowed_layers, *, clearance_nm,
                     leaves, deadline, contact_inset_nm=SURFACE_CONTACT_INSET_NM, max_points=9):
    """Sample real pad material, then screen the unchanged full-width launch.

    The inset is a geometric search/contact guard, NOT a neckdown allowance or
    terminal ampacity model. Independent saved-copper contact replay is required
    before admitting any proposal that uses one of these anchors.
    """
    import pcbnew
    import cec_fr
    import cec_fab_profile as fab
    import cec_pad_surface_access as surface
    result, evidence, caches = [], [], {}
    enabled = set(board.GetEnabledLayers().CuStack())
    # Bound the expansion before generating its Cartesian pair portfolio.
    for pad in pads[:128]:
        component = next(i for i, ids in enumerate(members) if _item_key(pad) in ids)
        for layer in sorted(set(pad.GetLayerSet().CuStack()) & enabled):
            layer_name = fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer))
            if layer_name not in allowed_layers:
                continue
            if time.monotonic() >= deadline or len(result) >= 256:
                return result, dict(rows=evidence, stop="bounded_surface_budget",
                    physical_no_path_proof=False, release_authority=False)
            width = math.ceil(graph["required_by_layer_mm"][layer_name]*1e6)
            sampled = surface.sample(pad, layer, contact_inset_nm=contact_inset_nm,
                                     deadline=deadline)
            points, refused = [], Counter()
            for coords in sampled["points"]:
                if time.monotonic() >= deadline:
                    refused["deadline"] += 1
                    break
                point = pcbnew.VECTOR2I(*coords)
                reason = _launch_refusal(board, point, layer, width, clearance_nm,
                                         leaves, pad.GetNetCode(), caches)
                if reason is None:
                    points.append(coords)
                else:
                    refused[reason] += 1
            selected = _spread_points(points, _point(pad), min(max_points, 256-len(result)))
            evidence.append(dict(pad=_pad_row(pad), layer=layer_name, width_mm=width/1e6,
                sampling={key: value for key, value in sampled.items() if key != "points"},
                full_width_clear_samples=len(points), refusals=dict(refused),
                selected_points_nm=selected, contact_inset_nm=contact_inset_nm,
                scope="geometric_contact_only_not_terminal_ampacity"))
            result.extend(dict(component=component, point=point, layers=(int(layer),),
                uuid=_uid(pad), pad=_pad_row(pad), kind="pad_surface",
                contact_inset_nm=contact_inset_nm) for point in selected)
            # A required full-width cap can overlap a finite pad patch while
            # its CENTER lies outside the pad. Only expand terminals whose
            # interior-center menu was blocked; keep the cheap existing menu.
            if not points and time.monotonic() < deadline and len(result) < 256:
                if not 2*(contact_inset_nm+1) <= width <= surface.MAX_CAP_WIDTH_NM:
                    evidence[-1]["exterior_caps"] = dict(stop="unsupported_width_range",
                        width_nm=width, physical_no_path_proof=False)
                    continue
                caps = surface.sample_caps(pad, layer, width,
                    contact_inset_nm=contact_inset_nm, deadline=deadline)
                clear, cap_refused = {}, Counter()
                for cap in caps["contacts"]:
                    if time.monotonic() >= deadline:
                        cap_refused["deadline"] += 1
                        break
                    coords = cap["center_nm"]
                    reason = _launch_refusal(board, pcbnew.VECTOR2I(*coords), layer,
                        width, clearance_nm, leaves, pad.GetNetCode(), caches)
                    if reason is None:
                        clear[tuple(coords)] = cap["witness_nm"]
                    else:
                        cap_refused[reason] += 1
                selected_caps = _spread_points(clear, _point(pad), min(max_points, 256-len(result)))
                evidence[-1]["exterior_caps"] = dict(
                    sampling={key: value for key, value in caps.items() if key != "contacts"},
                    full_width_clear_samples=len(clear), refusals=dict(cap_refused),
                    selected_contacts=[dict(center_nm=center,
                        witness_nm=clear[tuple(center)]) for center in selected_caps])
                result.extend(dict(component=component, point=center, layers=(int(layer),),
                    uuid=_uid(pad), pad=_pad_row(pad), kind="pad_cap",
                    contact_point_nm=clear[tuple(center)], contact_width_nm=width,
                    contact_inset_nm=contact_inset_nm) for center in selected_caps)
    return result, dict(rows=evidence, stop="sampled_portfolio_complete",
        pad_inventory_truncated=len(pads)>128,
        physical_no_path_proof=False, release_authority=False)


def _anchor_pairs(board, anchors, allowed_layers, *, diverse=False, require_surface=False,
                  deadline=None, evidence=None, max_anchors=512, max_pair_checks=32768,
                  max_per_group=64):
    """Fair physical-terminal pairing; extra samples cannot consume every slot."""
    import cec_fab_profile as fab
    from bisect import insort
    if (type(max_anchors) is not int or not 2 <= max_anchors <= 512
            or type(max_pair_checks) is not int or not 1 <= max_pair_checks <= 32768
            or type(max_per_group) is not int or not 1 <= max_per_group <= 64):
        raise ValueError("anchor-pair bounds exceeded")
    groups, buckets = {}, {}
    for anchor in anchors:
        buckets.setdefault((anchor["component"], anchor.get("kind") in {"pad_surface", "pad_cap"}), []).append(anchor)
    # Round-robin components and surface/legacy menus before the hard cap.
    selected = []
    for index in range(max((len(rows) for rows in buckets.values()), default=0)):
        for key in sorted(buckets):
            if index < len(buckets[key]):
                selected.append(buckets[key][index])
                if len(selected) == max_anchors:
                    break
        if len(selected) == max_anchors:
            break
    identities = {id(anchor): json.dumps({"uuid": anchor["uuid"],
        "pad": anchor.get("pad")}, sort_keys=True) for anchor in selected}
    checked, stop = 0, "complete"
    rank = lambda row: (row[0], row[1], row[2], row[3])
    for i, left in enumerate(selected):
        for right in selected[i+1:]:
            if deadline is not None and time.monotonic() >= deadline:
                stop = "deadline"
                break
            if checked >= max_pair_checks:
                stop = "pair_check_budget"
                break
            checked += 1
            if require_surface and not any(anchor.get("kind") in {"pad_surface", "pad_cap"}
                                           for anchor in (left, right)):
                continue
            if left["component"] == right["component"]:
                continue
            for layer in sorted(set(left["layers"]) & set(right["layers"])):
                name = fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer))
                if name not in allowed_layers:
                    continue
                row = (math.dist(left["point"], right["point"]),
                       left["point"], right["point"], layer, left, right)
                # Composite identity matters for cloned pad UUIDs. Keep a
                # physical terminal pair together, but try other pairs before
                # spending the whole route budget on its shifted samples.
                key = tuple(sorted(identities[id(anchor)] for anchor in (left, right))) + (layer,)
                rows = groups.setdefault(key, [])
                insort(rows, row, key=rank)
                if len(rows) > max_per_group:
                    rows.pop()
        if stop != "complete":
            break
    if evidence is not None:
        evidence.update(input_anchors=len(anchors), retained_anchors=len(selected),
            checked_pairs=checked, retained_pairs=sum(len(rows) for rows in groups.values()),
            max_pair_checks=max_pair_checks, max_per_terminal_pair=max_per_group,
            stop=stop, anchor_inventory_truncated=len(selected)<len(anchors),
            physical_no_path_proof=False)
    if not diverse:
        return sorted((row for rows in groups.values() for row in rows),
                      key=lambda row: (row[0], row[1], row[2], row[3]))
    ordered = sorted(groups.values(), key=lambda rows: rows[0][:4])
    return [rows[index] for index in range(max((len(rows) for rows in ordered), default=0))
            for rows in ordered if index < len(rows)]


def _anchor_item_key(anchor):
    """Rebind history after a native merge; component indexes are epoch-local."""
    pad = anchor.get("pad")
    if pad:
        return ("pad", pad["ref"], pad["pad"], *pad["position_nm"], pad["uuid"])
    return ("copper", anchor["uuid"])


def _component_pair_for(left, right, lookup):
    a, b = lookup.get(_anchor_item_key(left)), lookup.get(_anchor_item_key(right))
    return None if a is None or b is None else tuple(sorted((a, b)))


def _component_attempt_counts(members, attempts):
    lookup = {key: index for index, keys in enumerate(members) for key in keys}
    counts, collapsed, unmapped = Counter(), 0, 0
    for attempt in attempts:
        pair = _component_pair_for(attempt["start"], attempt["end"], lookup)
        if pair is None:
            unmapped += 1
        elif pair[0] == pair[1]:
            collapsed += 1
        else:
            counts[pair] += 1
    return counts, lookup, collapsed, unmapped


def _component_fair_pairs(candidates, members, attempts, *, limit, deadline):
    """Give every retained component pair a turn before repeat alternatives.

    Terminal/layer diversity inside a pair stays in the supplied menu order.
    Prior attempts are rebound by physical identity, so merging/reindexing
    components cannot give the nearest family a fresh monopolizing budget.
    Eligibility is a retained shared-layer anchor pair, NOT proven reachability.
    """
    counts, lookup, _, _ = _component_attempt_counts(members, attempts)
    queues = {}
    for row in candidates:
        if time.monotonic() >= deadline:
            return
        pair = _component_pair_for(row[4], row[5], lookup)
        if pair is not None and pair[0] != pair[1]:
            queues.setdefault(pair, deque()).append(row)
    for _ in range(limit):
        if not queues or time.monotonic() >= deadline:
            return
        pair = min(queues, key=lambda key: (counts[key], queues[key][0][:4], key))
        row = queues[pair].popleft()
        if not queues[pair]:
            del queues[pair]
        counts[pair] += 1
        yield row


def _component_pair_coverage(graph, members, attempts, candidates_by_phase, *,
                             attempt_start, inventory_complete):
    """Bounded retained-menu coverage, including unresolved/unattempted pairs."""
    counts, lookup, collapsed, unmapped = _component_attempt_counts(members, attempts)
    current, _, _, _ = _component_attempt_counts(members, attempts[attempt_start:])
    retained, unmapped_candidates = {}, 0
    for phase, candidates in candidates_by_phase.items():
        for row in candidates:
            pair = _component_pair_for(row[4], row[5], lookup)
            if pair is None:
                unmapped_candidates += 1
            elif pair[0] != pair[1]:
                retained.setdefault(pair, Counter())[phase] += 1
    rows = [dict(components=list(pair), retained_candidates=dict(phases),
                 attempts=counts[pair], attempts_this_epoch=current[pair],
                 inherited_attempts=counts[pair]-current[pair],
                 tested=counts[pair] > 0)
            for pair, phases in sorted(retained.items())]
    complete = bool(candidates_by_phase) and inventory_complete and not unmapped_candidates
    return dict(scope="retained_shared_layer_anchor_pairs_not_proven_reachability",
        components=graph["rated_connectivity"]["components"],
        component_count=len(members), demand_pair_count=len(members)*(len(members)-1)//2,
        retained_eligible_pair_count=len(rows), tested_pair_count=sum(row["tested"] for row in rows),
        untested_pair_count=sum(not row["tested"] for row in rows),
        component_pairs=rows, pair_inventory_complete=complete,
        pairs_without_retained_candidates=len(members)*(len(members)-1)//2-len(rows),
        missing_pair_scope="no_retained_screened_anchor_pair_not_no_path" if complete
                           else "inventory_incomplete_unknown",
        pair_inventory_scope="retained_screened_menus_not_exhaustive_surface_access",
        collapsed_attempts=collapsed, unmapped_attempts=unmapped,
        unmapped_candidates=unmapped_candidates, attempts_this_epoch=len(attempts)-attempt_start,
        physical_no_path_proof=False)


def _surface_contact_admission(board, plan, net, *, added_uuids,
                               required_by_layer_mm,
                               contact_inset_nm=SURFACE_CONTACT_INSET_NM):
    """Re-prove selected contacts on saved native copper, not planner booleans."""
    import pcbnew
    import cec_pad_surface_access as surface
    pads = {json.dumps(_pad_row(pad), sort_keys=True): pad
            for fp in board.GetFootprints() for pad in fp.Pads()}
    tracks = {_uid(track): track for track in board.GetTracks()}
    rows, errors, claimed, rule_hits, rule_cache = [], [], [], [], {}
    actual = set(added_uuids)
    if (len(plan["created_uuids"]) != len(set(plan["created_uuids"]))
            or set(plan["created_uuids"]) != actual):
        errors.append("created_ledger_does_not_match_serialized_additions")
    for attempt in plan["attempts"]:
        if attempt.get("accepted_plan") is not True:
            if attempt.get("created_uuids"):
                errors.append("unaccepted_attempt_claims_additions")
            continue
        added = attempt.get("created_uuids", ())
        claimed.extend(added)
        layer = board.GetLayerID(attempt["layer"])
        width = attempt.get("width_nm")
        required = required_by_layer_mm.get(attempt["layer"])
        if (type(width) is not int or width <= 0 or required is None
                or width < math.ceil(required*1e6)):
            errors.append("missing_or_undersized_integer_width_authority")
            continue
        segments = [tracks.get(uid) for uid in added]
        if not segments or any(item is None or item.GetClass() != "PCB_TRACK"
                or item.GetNetname() != net or item.GetLayer() != layer
                or item.GetWidth() < width for item in segments):
            errors.append("missing_or_wrong_incident_segment")
        else:
            for item in segments:
                hits = _native_track_rule_hits(board, item.GetEffectiveShape(layer), layer,
                                              cache=rule_cache)
                rule_hits.extend(dict(hit, segment_uuid=_uid(item)) for hit in hits)
            if rule_hits:
                errors.append("saved_segment_intersects_track_rule_area")
            chain = [([item.GetStart().x, item.GetStart().y],
                      [item.GetEnd().x, item.GetEnd().y]) for item in segments]
            if (chain[0][0] != attempt["start"]["point"] or chain[-1][1] != attempt["end"]["point"]
                    or any(first[1] != second[0] for first, second in zip(chain, chain[1:]))):
                errors.append("saved_path_does_not_match_anchor_ledger")
        for anchor in (attempt["start"], attempt["end"]):
            kind = anchor.get("kind")
            if kind == "rated_track":
                item = tracks.get(anchor["uuid"])
                if (item is None or item.GetClass() not in {"PCB_TRACK", "PCB_ARC"}
                        or item.GetNetname() != net or item.GetLayer() != layer
                        or item.GetWidth() < width):
                    errors.append("invalid_rated_track_anchor")
                else:
                    a, b = item.GetStart(), item.GetEnd()
                    points = [[a.x, a.y], [b.x, b.y]]
                    if item.GetClass() == "PCB_TRACK":
                        points.append([(a.x+b.x)//2, (a.y+b.y)//2])
                    if anchor["point"] not in points:
                        errors.append("rated_anchor_not_on_declared_access_point")
                continue
            pad = pads.get(json.dumps(anchor.get("pad"), sort_keys=True))
            if kind == "pad_center":
                if (pad is None or str(pad.GetNetname()) != net or not pad.IsOnLayer(layer)
                        or anchor["point"] != _point(pad)):
                    errors.append("invalid_center_anchor")
                continue
            if kind not in {"pad_surface", "pad_cap"}:
                errors.append("unknown_anchor_kind")
                continue
            point, inset = anchor["point"], anchor["contact_inset_nm"]
            witness = anchor.get("contact_point_nm") if kind == "pad_cap" else point
            try:
                contact = (surface.cap_contact(pad, layer, point, witness, width,
                    contact_inset_nm=inset) if kind == "pad_cap" else
                    surface.contact(pad, layer, point, contact_inset_nm=inset)) if pad else None
            except (ValueError, TypeError, KeyError):
                contact = dict(ok=False, reason="invalid_cap_contact_declaration")
            incident = []
            for uid in attempt.get("created_uuids", ()):
                item = tracks.get(uid)
                if (item is None or item.GetClass() != "PCB_TRACK"
                        or item.GetNetname() != net or item.GetLayer() != layer
                        or item.GetWidth() < max(2*inset, width)):
                    continue
                endpoints = ([item.GetStart().x, item.GetStart().y],
                             [item.GetEnd().x, item.GetEnd().y])
                if point in endpoints:
                    incident.append(uid)
            # The exact saved segment endpoint and integer width own the cap.
            # Exterior centers additionally replay full containment of a
            # distinct native interior disk. Mere pad overlap is not evidence.
            valid = bool(pad is not None and str(pad.GetNetname()) == net
                         and inset == contact_inset_nm
                         and contact and contact.get("ok") is True and incident
                         and (kind != "pad_cap" or anchor.get("contact_width_nm") == width))
            rows.append(dict(pad=anchor["pad"], layer=attempt["layer"], point_nm=point,
                anchor_kind=kind, contact_point_nm=witness,
                contact_inset_nm=inset, native_contact=contact, incident_new_segments=incident,
                ok=valid, contact_basis="fixed_search_margin_not_electrical_rating",
                scope="geometric_contact_only_not_terminal_ampacity"))
    if len(claimed) != len(set(claimed)) or set(claimed) != actual:
        errors.append("accepted_attempt_ledger_does_not_cover_additions_exactly")
    return dict(ok=not errors and all(row["ok"] for row in rows), contacts=rows,
                ledger_errors=sorted(set(errors)), added_uuids=sorted(actual),
                native_track_rule_area_hits=rule_hits,
                applicable=bool(rows),
                terminal_ampacity_certified=False, release_authority=False)


def _preferred_phase_deadline(deadline, *, now, share=.5):
    """Reserve actual wall time, not just attempt slots, for native contacts.

    Unused preferred time is reclaimed by the fallback under the same outer
    deadline. Exhaustion remains an unproved search, never a no-path proof.
    """
    if (any(type(v) not in (int, float) or not math.isfinite(v)
            for v in (deadline, now, share)) or deadline < 0 or now < 0
            or not .05 <= share <= .95):
        raise ValueError('bounded_preferred_force_phase_share_required')
    return min(deadline, now + max(0., deadline-now)*share)


def _force_channel_policy(maze_margin_mm, perimeter_channels):
    """Finite search room is geometry, never copper or clearance permission."""
    if (type(maze_margin_mm) not in (int, float) or not math.isfinite(maze_margin_mm)
            or not .25 <= maze_margin_mm <= 12. or type(perimeter_channels) is not bool):
        raise ValueError('bounded_explicit_force_channel_policy_required')
    return dict(maze_margin_mm=float(maze_margin_mm), perimeter_channels=perimeter_channels,
        unchanged_current_width_and_clearance=True, physical_no_path_proof=False)


def _construct(board, source, net, domain, contract, *, max_pairs, max_bridges,
               deadline, allow_maze, include_bypass_terminals=False,
               preferred_phase_share=.5, maze_margin_mm=2., perimeter_channels=False):
    import pcbnew
    import cec_fr
    import cec_fab_profile as fab
    spec = cec_fr._project_netclass_resolver(source)(net) or {}
    channel_policy = _force_channel_policy(maze_margin_mm, perimeter_channels)
    nc = board.GetNetcodeFromNetname(net)
    clearance = max(float(spec.get("clearance") or 0),
                    float(board.GetDesignSettings().m_MinClearance)/1e6)
    allowed_layers = set(contract["routing_layers"])
    attempts, created, bridge_count, access, pairing = [], [], 0, [], []
    endpoint_screening = []
    phase_budgets = []
    _preferred_phase_deadline(deadline, now=time.monotonic(), share=preferred_phase_share)
    coverage, candidates_by_phase, inventory_complete = [], {}, False
    reason = "bounded_no_legal_rated_path"
    while bridge_count < max_bridges and len(attempts) < max_pairs:
        if time.monotonic() >= deadline:
            reason = "deferred_budget"
            break
        graph, native = _graph(board, net, domain, contract, spec,
                               include_bypass_terminals=include_bypass_terminals)
        if graph["rated_connectivity"]["connected"]:
            reason = "rated_path_constructed"
            break
        pads, kept, members = native
        raw_anchors = _anchors(pads, kept, members)
        leaves = _leaf_obstacles(board, net, domain, graph)
        anchors, screening = _screen_anchors(board, raw_anchors, graph, allowed_layers,
            clearance_nm=math.ceil(clearance*1e6), leaves=leaves, nc=nc, deadline=deadline)
        endpoint_screening.append(dict(screening, component_epoch=len(coverage)))
        if time.monotonic() >= deadline:
            reason = "deferred_budget"
        attempt_start = len(attempts)
        pair_evidence = dict(phase="center")
        phase_start = time.monotonic()
        phase_deadline = _preferred_phase_deadline(deadline, now=phase_start,
            share=preferred_phase_share)
        phase_budgets.append(dict(component_epoch=len(coverage), phase='center',
            start_monotonic=phase_start, deadline_monotonic=phase_deadline,
            global_deadline_monotonic=deadline, preferred_share=preferred_phase_share,
            additional_wall_budget_granted=False, physical_no_path_proof=False))
        center_candidates = _anchor_pairs(board, anchors, allowed_layers,
            deadline=phase_deadline, evidence=pair_evidence)
        pairing.append(pair_evidence)
        candidates_by_phase = {"center": center_candidates}
        inventory_complete = (screening["inventory_complete"]
                              and pair_evidence["stop"] == "complete"
                              and not pair_evidence["anchor_inventory_truncated"])

        def portfolios():
            nonlocal phase_deadline
            # Preserve the cheap successful old menu. Reserve half the remaining
            # pair budget for actual-pad alternatives if center plans refuse.
            # The reserve shares ONE current-component ledger with the center
            # prefix: distant demand pairs outrank repeats from nearby families.
            yield from _component_fair_pairs(center_candidates, members, attempts,
                limit=max(1, (max_pairs-len(attempts))//2), deadline=phase_deadline)
            if time.monotonic() >= deadline or len(attempts) >= max_pairs:
                return
            phase_deadline = deadline
            fallback_start = time.monotonic()
            sampling_deadline = _preferred_phase_deadline(deadline, now=fallback_start)
            phase_budgets.append(dict(component_epoch=len(coverage), phase='surface',
                start_monotonic=fallback_start, deadline_monotonic=deadline,
                sampling_deadline_monotonic=sampling_deadline,
                global_deadline_monotonic=deadline, unused_preferred_time_reclaimed=True,
                additional_wall_budget_granted=False, physical_no_path_proof=False))
            surface, sampled = _surface_anchors(board, pads, members, graph, allowed_layers,
                clearance_nm=math.ceil(clearance*1e6), leaves=leaves, deadline=sampling_deadline)
            sampled["legacy_endpoint_screen"] = screening
            access.append(sampled)
            tried = {(tuple(row["start"]["point"]), tuple(row["end"]["point"]), row["layer"])
                     for row in attempts}
            pair_evidence = dict(phase="surface")
            candidates = _anchor_pairs(board, [*anchors, *surface], allowed_layers, diverse=True,
                require_surface=True, deadline=deadline, evidence=pair_evidence)
            pairing.append(pair_evidence)
            candidates_by_phase["surface"] = candidates
            remaining = []
            # Prefer a surface alternative within each pair, but a pair with
            # no retained surface sample must not vanish from the reserve.
            # Only its already-screened center options may fill the reserve;
            # never restore a legacy endpoint that failed a necessary guard.
            for menu in (candidates, center_candidates):
                for row in menu:
                    name = fab.COPPER_LAYER_IDS.get(row[3], board.GetLayerName(row[3]))
                    key = (tuple(row[1]), tuple(row[2]), name)
                    if key not in tried:
                        tried.add(key)
                        remaining.append(row)
            yield from _component_fair_pairs(remaining, members, attempts,
                limit=max_pairs-len(attempts), deadline=deadline)
        changed = False
        foreign_cache, identified_indexes = {}, {}
        for distance, start, end, layer, left, right in portfolios():
            if len(attempts) >= max_pairs or time.monotonic() >= deadline:
                if time.monotonic() >= deadline:
                    reason = "deferred_budget"
                break
            layer_name = fab.COPPER_LAYER_IDS.get(layer, board.GetLayerName(layer))
            width = math.ceil(graph["required_by_layer_mm"][layer_name]*1e6)
            blocked = Counter()
            leaf_hits = set()
            track_rule_hits = {}

            def leg_ok(a, b, half):
                if not cec_fr._edge_leg_clear(board, a, b, math.ceil(width/2)):
                    blocked["outline"] += 1
                    return False
                # The router's half-width is integer-truncated for odd widths;
                # permission/leaf guards own the actual emitted width, not 2*half.
                shape = pcbnew.SHAPE_SEGMENT(a, b, width)
                hits = _native_track_rule_hits(board, shape, layer, cache=foreign_cache)
                if hits:
                    blocked["native_track_rule_area"] += 1
                    track_rule_hits.update((hit["uuid"], hit) for hit in hits)
                    return False
                for leaf in leaves:
                    if leaf.IsOnLayer(layer) and leaf.GetEffectiveShape(layer).Collide(shape, 0):
                        blocked["same_net_monitor_or_local_branch"] += 1
                        leaf_hits.add(_uid(leaf))
                        return False
                return True

            legs = cec_fr._guarded_lastmile_legs(
                board, pcbnew.VECTOR2I(*start), pcbnew.VECTOR2I(*end), width,
                layer, math.ceil(clearance*1e6), nc, leg_ok,
                allow_maze=allow_maze, maze_margin_mm=channel_policy['maze_margin_mm'],
                perimeter_channels=channel_policy['perimeter_channels'], foreign_cache=foreign_cache,
                deadline_monotonic=phase_deadline,
                max_length_nm=max(distance*2, distance+4e6))
            row = dict(start=left, end=right, layer=layer_name, width_mm=width/1e6,
                       width_nm=width,
                       search_deadline_monotonic=phase_deadline,
                       global_deadline_monotonic=deadline,
                       search_phase='center' if phase_deadline < deadline else 'surface',
                       component_epoch=len(coverage),
                       component_pair=sorted((left["component"], right["component"])),
                       accepted_plan=legs is not None, blockers=dict(blocked),
                       protected_leaf_uuids=sorted(leaf_hits),
                       native_track_rule_area_hits=[track_rule_hits[key]
                                                   for key in sorted(track_rule_hits)])
            if legs is None:
                # These are exact sampled obstruction identities, not a claim
                # that endpoint rays or the direct chord exhaust legal space.
                if layer not in identified_indexes:
                    identified_indexes[layer] = cec_fr._identified_foreign_shape_indexes(board, layer, {nc})
                zones, copper = identified_indexes[layer]
                row["obstruction_witness"] = {
                    "scope": "direct_segment_and_endpoint_disks_not_global_no_path",
                    "direct_blockers": cec_fr._snapshot_foreign_blockers(
                        pcbnew.VECTOR2I(*start), pcbnew.VECTOR2I(*end), width,
                        math.ceil(clearance*1e6), zones, copper),
                    "endpoints": [dict(point_nm=point,
                        edge_clear=cec_fr._edge_leg_clear(
                            board, pcbnew.VECTOR2I(*point), pcbnew.VECTOR2I(*point), width//2),
                        blockers=cec_fr._snapshot_foreign_blockers(
                            pcbnew.VECTOR2I(*point), pcbnew.VECTOR2I(*point), width,
                            math.ceil(clearance*1e6), zones, copper)) for point in (start, end)],
                }
            attempts.append(row)
            if not legs:
                continue
            added = []
            for a, b in legs:
                item = pcbnew.PCB_TRACK(board)
                item.SetStart(a); item.SetEnd(b); item.SetWidth(width)
                item.SetLayer(layer); item.SetNetCode(nc); item.SetLocked(True)
                board.Add(item)
                created.append(_uid(item))
                added.append(_uid(item))
            row["created_uuids"] = added
            changed = True
            bridge_count += 1
            break
        epoch = _component_pair_coverage(graph, members, attempts, candidates_by_phase,
            attempt_start=attempt_start, inventory_complete=inventory_complete)
        epoch.update(epoch=len(coverage),
            stop="native_merge" if changed else "deadline" if time.monotonic() >= deadline
                 else "pair_attempt_budget" if len(attempts) >= max_pairs else "retained_portfolio_exhausted")
        coverage.append(epoch)
        if not changed:
            break
    graph, (_, _, members) = _graph(board, net, domain, contract, spec,
                                   include_bypass_terminals=include_bypass_terminals)
    if graph["rated_connectivity"]["connected"]:
        reason = "rated_path_constructed"
    return dict(reason=reason, attempts=attempts, created_uuids=created,
                channel_search_policy=channel_policy,
                phase_wall_budgets=phase_budgets,
                terminal_access=access, pairing=pairing,
                endpoint_screening=endpoint_screening,
                component_pair_coverage=dict(epochs=coverage,
                    final=_component_pair_coverage(graph, members, attempts, candidates_by_phase,
                        attempt_start=len(attempts), inventory_complete=inventory_complete),
                    final_scope="last_epoch_retained_pairs_rebound_to_final_native_components",
                    max_pairs=max_pairs, attempted_pairs=len(attempts),
                    remaining_pair_budget=max_pairs-len(attempts)),
                bridge_count=bridge_count, rated_after=graph,
                connected=graph["rated_connectivity"]["connected"],
                scope=SCOPE, physical_no_path_proof=False)


def _propose_worker(source, directory, net, *, board_hint, immutable_nets,
                    timeout_s=45.0, max_pairs=16, max_bridges=4, allow_maze=False,
                    complete_frozen_prefix=False, include_bypass_terminals=False,
                    maze_margin_mm=2., perimeter_channels=False):
    """Internal native worker. Public callers use the supervised ``propose``."""
    import pcbnew
    import cec_constraints
    import cec_current_topology as topology
    import cec_fr
    import cec_operation_budget
    import cec_score
    import cec_stage_admission
    import cec_force_sense_evidence
    directory, source = Path(directory), str(Path(source).resolve())
    start = time.monotonic()
    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or board_hint or source
    protected = _protected_paths(source, hint)
    _check_proposal_directory(directory, protected)
    _check_output(directory / "receipt.json", protected)
    _check_output(directory / "diagnosis.json", protected)
    report = dict(schema=SCHEMA, operation="force_current_additive", net=net,
                  accepted=False, changed=False, connected=False, retryable=False,
                  physical_feasibility="not_assessed", release_authority=False,
                  qualification_scope=SCOPE, source_family_before=_family(source, hint),
                  code_before=_code_identity(), candidate=None,
                  code_identity_scope="all_local_scripts_python_conservative")
    candidate = None
    candidate_epoch = None
    sense_before = None

    def sense_replay(path):
        # Reuse the operation's nonrenewable lease; never grant another 30 s.
        available = cec_operation_budget.available_timeout(
            max(0, timeout_s-(time.monotonic()-start)), os.environ, reserve_s=1)
        if available <= 0:
            raise RuntimeError("sense_replay_operation_budget_exhausted")
        return cec_force_sense_evidence.replay(path, board_hint=hint, timeout_s=min(60, available))

    try:
        with _thermal_hint(hint):
            report['channel_search_policy'] = _force_channel_policy(maze_margin_mm, perimeter_channels)
            board = pcbnew.LoadBoard(source)
            capability = force_route_operation_admission(
                board, [net], board_hint=hint, immutable_nets=immutable_nets,
                authority_path=source, complete_frozen_prefix=complete_frozen_prefix,
                include_bypass_terminals=include_bypass_terminals)
            report["capability"] = capability
            if not capability["eligible"]:
                report["reason"] = capability["refusals"][net]["reason"]
                return report
            diagnosis = diagnose(source, [net], board_hint=hint)
            _write(directory / "diagnosis.json", diagnosis)
            report["diagnosis"] = str(directory / "diagnosis.json")
            domain_result = diagnosis["domains"][net]
            bypass_input = None
            if include_bypass_terminals:
                bypass_input, _ = _graph(board, net, domain_result["domain"],
                    domain_result["width_contract"], cec_fr._project_netclass_resolver(source)(net) or {},
                    include_bypass_terminals=True)
                report["input_bypass_tree"] = bypass_input
            if domain_result["qualified"] and (bypass_input is None or
                    bypass_input["rated_connectivity"]["connected"]):
                sense_before = sense_replay(source)
                report["scoped_kelvin"] = cec_force_sense_evidence.admit_changed_net(
                    sense_before, sense_before, net)
                report["sense_before"] = sense_before
                report.update(accepted=report["scoped_kelvin"]["ok"], connected=True,
                              reason="qualified_input_prefix" if report["scoped_kelvin"]["ok"]
                                     else "force_kelvin_admission_refused",
                              existing_copper_unchanged=True, placement_unchanged=True,
                              current_width=domain_result["current_width"])
                return report
            remaining = cec_operation_budget.available_timeout(
                max(0, timeout_s-(time.monotonic()-start)), os.environ, reserve_s=5)
            if remaining <= 0:
                report["reason"] = "deferred_budget"
                return report
            candidate = _copy_family(source, directory / "candidate")
            board = pcbnew.LoadBoard(str(candidate))
            plan = _construct(board, str(candidate), net, domain_result["domain"],
                              domain_result["width_contract"], max_pairs=max_pairs,
                              max_bridges=max_bridges, deadline=time.monotonic()+remaining,
                              allow_maze=allow_maze, include_bypass_terminals=include_bypass_terminals,
                              maze_margin_mm=maze_margin_mm, perimeter_channels=perimeter_channels)
            report["plan"] = plan
            report["candidate"] = str(candidate)
            report["candidate_changed"] = bool(plan["created_uuids"])
            report["physical_feasibility"] = "bounded_portfolio_assessed_not_global"
            # Retain the exact child even when its partial plan is refused.
            if plan["created_uuids"]:
                pcbnew.SaveBoard(str(candidate), board, True)
            report["preservation"] = preservation(source, candidate, net=net)
            report["surface_contacts"] = _surface_contact_admission(
                pcbnew.LoadBoard(str(candidate)), plan, net,
                added_uuids=report["preservation"]["added_uuids"],
                required_by_layer_mm=domain_result["required_by_layer_mm"])
            report["existing_copper_unchanged"] = report["preservation"]["ok"]
            report["placement_unchanged"] = report["preservation"]["ok"]
            if report["surface_contacts"]["ok"] is not True:
                report["reason"] = "force_contact_admission_refused"
                return report
            if not plan["connected"] or not plan["created_uuids"]:
                remaining = cec_operation_budget.available_timeout(
                    min(3.0, max(0, timeout_s-(time.monotonic()-start))),
                    os.environ, reserve_s=1)
                report["terminal_launch_pockets"] = _terminal_launch_pockets(
                    board, net, domain_result["domain"],
                    domain_result["required_by_layer_mm"], str(candidate),
                    deadline=time.monotonic()+max(0, remaining))
                report["reason"] = plan["reason"]
                return report
            report["exact_refill"] = _finalize_current_segments(board, source, candidate)
            # Every admission term must describe this ONE saved artifact,
            # not individually stable but different sequential snapshots.
            candidate_epoch = _family(candidate, hint)
            report["candidate_family_verified"] = candidate_epoch
            exact = pcbnew.LoadBoard(str(candidate))
            width = cec_constraints.CHECKERS["trace-width-high-current"](
                exact, str(candidate), {"current_domain_include_nets": [net]})
            report["current_width"] = dict(ok=width[0], detail=width[1],
                evidence=width[2] if len(width)>2 else None)
            report["authority_proof"] = topology.authority_connectivity(exact, net, board_hint=hint)
            rated, _ = _graph(exact, net, domain_result["domain"], domain_result["width_contract"],
                              cec_fr._project_netclass_resolver(str(candidate))(net) or {},
                              include_bypass_terminals=include_bypass_terminals)
            report["rated_proof"] = rated
            report["preservation"] = preservation(source, candidate, net=net, allow_ground_refill=True)
            report["surface_contacts"] = _surface_contact_admission(exact, plan, net,
                added_uuids=report["preservation"]["added_uuids"],
                required_by_layer_mm=domain_result["required_by_layer_mm"])
            report["existing_copper_unchanged"] = report["preservation"]["ok"]
            report["placement_unchanged"] = report["preservation"]["ok"]
            before = cec_score.score(source)
            after = cec_score.score(str(candidate))
            report["whole_board_admission"] = cec_stage_admission.evaluate(before, after)
            # Bind native Kelvin inventory, including renamed force/sense nets.
            pairs = cec_fr._board_kelvin_pairs(exact)
            old_topology = cec_score.kelvin_topology_faults(pcbnew.LoadBoard(source), pairs)
            new_topology = cec_score.kelvin_topology_faults(exact, pairs)
            identities = lambda rows: {json.dumps(row, sort_keys=True, default=str) for row in rows}
            new_faults = sorted(identities(new_topology[2])-identities(old_topology[2]))
            direct_coverage = bool(old_topology[3] and new_topology[3])
            coverage_preserved = new_topology[3] >= old_topology[3]
            report["kelvin_topology"] = dict(pairs=[list(pair) for pair in pairs],
                new_faults=new_faults, before_checked=old_topology[3], after_checked=new_topology[3],
                no_new_reported_faults=not new_faults, coverage_preserved=coverage_preserved,
                ok=(not new_faults and coverage_preserved) if direct_coverage else None,
                scope="legacy_direct_same_net_cut_vertex_non_regression_only",
                full_kelvin_qualification=False)
            report["qualification_gaps"] = (["direct_kelvin_check_not_exercised"]
                                             if pairs and not direct_coverage else [])
            sense_before, sense_after = sense_replay(source), sense_replay(candidate)
            report["sense_before"], report["sense_after"] = sense_before, sense_after
            report["scoped_kelvin"] = cec_force_sense_evidence.admit_changed_net(sense_before, sense_after, net)
            report["sense_candidate_identity_matches"] = sense_after.get("source_family_before") == candidate_epoch
            if not report["scoped_kelvin"]["ok"]:
                report["qualification_gaps"].append("affected_typed_kelvin_leg_not_verified")
            accepted = (width[0] is True and report["authority_proof"].get("connected") is True
                        and rated["rated_connectivity"]["connected"] is True
                        and report["preservation"]["ok"] is True
                        and report["whole_board_admission"]["accepted"] is True and not new_faults
                        and coverage_preserved
                        and report["scoped_kelvin"]["ok"] is True
                        and report["sense_candidate_identity_matches"] is True
                        and report["surface_contacts"]["ok"] is True
                        and report["exact_refill"].get("stable") is True)
            report.update(accepted=accepted, changed=accepted,
                          connected=report["authority_proof"].get("connected") is True,
                          reason="admitted_additive_rated_path" if accepted else "force_candidate_admission_refused")
    except Exception as exc:  # A failed native/authority proof never becomes permission.
        report.update(reason="force_current_evidence_failure", error=repr(exc), accepted=False, changed=False)
    finally:
        report.update(source_family_after=_family(source, hint), code_after=_code_identity(),
                      elapsed_s=round(time.monotonic()-start, 6))
        if candidate is not None:
            report["candidate_sha256"] = _hash(candidate)
            if candidate_epoch is not None:
                report["candidate_family_after"] = _family(candidate, hint)
                report["candidate_family_unchanged"] = report["candidate_family_after"] == candidate_epoch
                if report["candidate_family_unchanged"] is not True:
                    report.update(accepted=False, changed=False, reason="concurrent_candidate_family_change")
        report["source_unchanged"] = report["source_family_before"] == report["source_family_after"]
        report["code_unchanged"] = report["code_before"] == report["code_after"]
        if not report["source_unchanged"] or not report["code_unchanged"]:
            report.update(accepted=False, changed=False, reason="concurrent_authority_or_code_change")
        _write(directory / "receipt.json", report)
    return report


def propose(source, directory, net, *, board_hint, immutable_nets,
            timeout_s=45.0, max_pairs=16, max_bridges=4, allow_maze=False,
            complete_frozen_prefix=False, include_bypass_terminals=False,
            maze_margin_mm=2., perimeter_channels=False):
    """Supervised private proposal; no output ever replaces the input board.

    ``directory`` must be fresh. Rejected child artifacts and diagnostic logs
    remain available there. There is one nonrenewable supervisor lease, never
    an identical fast/exact retry. An accepted no-op has candidate=None.
    """
    import cec_operation_budget
    channel_policy = _force_channel_policy(maze_margin_mm, perimeter_channels)
    if not math.isfinite(float(timeout_s)) or timeout_s <= 0:
        raise ValueError("timeout_s must be finite and positive")
    if type(complete_frozen_prefix) is not bool:
        raise ValueError('explicit_boolean_frozen_prefix_completion_mode_required')
    if type(include_bypass_terminals) is not bool:
        raise ValueError('explicit_boolean_bypass_terminal_mode_required')
    if not 1 <= int(max_pairs) <= 64 or not 1 <= int(max_bridges) <= 16:
        raise ValueError("force portfolio bounds exceeded")
    source = str(Path(source).resolve())
    directory = Path(directory).resolve()
    _check_proposal_directory(directory, _protected_paths(source, board_hint))
    directory.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, str(Path(__file__).resolve()), "worker", source,
               "--directory", str(directory), "--net", net,
               "--board-hint", str(board_hint), "--timeout-s", str(timeout_s),
               "--max-pairs", str(max_pairs), "--max-bridges", str(max_bridges),
               "--maze-margin-mm", str(channel_policy['maze_margin_mm']),
               "--immutable-nets-json", json.dumps(sorted(set(immutable_nets)))]
    if perimeter_channels:
        command.append('--perimeter-channels')
    if allow_maze:
        command.append("--allow-maze")
    if complete_frozen_prefix:
        command.append('--complete-frozen-prefix')
    if include_bypass_terminals:
        command.append('--include-bypass-terminals')
    try:
        cec_operation_budget.run(command, directory / "supervisor",
            operation="force_current_additive", timeout=timeout_s)
        return json.loads((directory / "receipt.json").read_text())
    except cec_operation_budget.OperationFailure as exc:
        budget = exc.failure_evidence["status"] in {"operation_budget_exhausted", "campaign_budget_exhausted"}
        report = dict(schema=SCHEMA, accepted=False, changed=False, connected=False,
            reason="deferred_budget" if budget else "force_current_worker_failed", retryable=False,
            physical_feasibility="inconclusive", release_authority=False,
            operation_failure=exc.failure_evidence, evidence_directory=str(directory))
        _write(directory / "receipt.json", report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("diagnose", "propose", "worker"))
    parser.add_argument("board")
    parser.add_argument("--net", action="append", required=True)
    parser.add_argument("--board-hint")
    parser.add_argument("--directory")
    parser.add_argument("--report")
    parser.add_argument("--immutable-nets-json", default="[]")
    parser.add_argument("--timeout-s", type=float, default=45)
    parser.add_argument("--max-pairs", type=int, default=16)
    parser.add_argument("--max-bridges", type=int, default=4)
    parser.add_argument("--allow-maze", action="store_true")
    parser.add_argument('--maze-margin-mm', type=float, default=2.,
                        help='bounded .25..12 mm search window; does not relax conductor rules')
    parser.add_argument('--perimeter-channels', action='store_true',
                        help='search existing native board-edge channels under the same wall budget')
    parser.add_argument('--complete-frozen-prefix', action='store_true',
                        help='additive completion only; retain every prelaid frozen primitive and sidecar')
    parser.add_argument('--include-bypass-terminals', action='store_true',
                        help='include typed surface rail-to-return capacitors at unchanged full-load width')
    parser.add_argument("--terminal-launch-pockets", action="store_true",
                        help="include bounded planar pocket evidence on unqualified diagnosis")
    args = parser.parse_args(argv)
    def guard_report():
        protected = _protected_paths(args.board, args.board_hint)
        candidate_directory = Path(args.directory)/"candidate" if args.directory else None
        destination = Path(args.report).resolve()
        temporary = destination.with_name(destination.name+".tmp-"+str(os.getpid()))
        _check_output(destination, protected, candidate_directory=candidate_directory)
        _check_output(temporary, protected, candidate_directory=candidate_directory)
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("report temporary path already exists")

    if args.report:
        try:
            guard_report()
        except ValueError as exc:
            parser.error(str(exc))
    if args.mode == "diagnose":
        result = diagnose(args.board, args.net, board_hint=args.board_hint,
                          include_launch_pockets=args.terminal_launch_pockets)
    else:
        if len(args.net) != 1 or not args.directory:
            parser.error("a proposal needs exactly one --net and a fresh --directory")
        function = _propose_worker if args.mode == "worker" else propose
        result = function(args.board, args.directory, args.net[0], board_hint=args.board_hint,
            immutable_nets=json.loads(args.immutable_nets_json), timeout_s=args.timeout_s,
            max_pairs=args.max_pairs, max_bridges=args.max_bridges, allow_maze=args.allow_maze,
            complete_frozen_prefix=args.complete_frozen_prefix,
            include_bypass_terminals=args.include_bypass_terminals,
            maze_margin_mm=args.maze_margin_mm, perimeter_channels=args.perimeter_channels)
    if args.report:
        try:
            guard_report()
        except ValueError as exc:
            parser.error(str(exc))
        _write(args.report, result)
        print(json.dumps(dict(report=str(Path(args.report).resolve()),
            elapsed_s=result.get("elapsed_s"), reason=result.get("reason"),
            accepted=result.get("accepted"), source_unchanged=result.get("source_unchanged"))))
    elif args.mode != "worker":
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
