"""Capability-specific independent checks over actual saved families."""

from .identity import require
from .legacy import bootstrap

bootstrap()


def _kelvin_noninterference(source, candidate, *, board_hint):
    """Prove an unrelated track-only edit cannot alter Kelvin geometry.

    Exact native residue includes every pad, hole, via, zone, edge and setting.
    Fresh full-denominator manifests must agree on lineage and authority. This
    is preservation by non-interference, never a new absolute Kelvin pass.
    Relevant or broader edits still require physical cut replay below.
    """
    import pcbnew
    import cec_force_current as force
    import cec_force_sense_shards as shards
    import cec_additive_route_receiving as native
    import cec_copper_echo as syntax
    from .identity import digest

    if force._sidecars(source) != force._sidecars(candidate):
        return None
    families = [force._family(p, board_hint) for p in (source, candidate)]
    epoch = force._code_identity()
    parsed = [native._nodes(p) for p in (source, candidate)]
    old, new = [nodes for _, nodes in parsed]
    changed = {u for u in old.keys() | new.keys() if u not in old or u not in new
               or syntax._freeze(old[u]) != syntax._freeze(new[u])}
    if not 1 <= len(changed) <= 256 or any(
        nodes[u][0] != "segment" for nodes in (old, new) for u in changed & nodes.keys()
    ):
        return None

    def residue(root, nodes):
        ids = {id(node): uid for uid, node in nodes.items()}
        return syntax._freeze([node for node in root if ids.get(id(node)) not in changed])

    if residue(*parsed[0]) != residue(*parsed[1]):
        return None
    manifests = [shards.manifest(p, board_hint=board_hint, timeout_s=9.1)
                 for p in (source, candidate)]
    for report in manifests:
        shards._require(report, report, ("manifest",))
    keys = ("board_hint", "budget", "geometry_policy", "lineage",
            "declared_pairs", "shard_inventory")
    if any(digest(manifests[0][key]) != digest(manifests[1][key]) for key in keys):
        return None
    inventory = manifests[0]["shard_inventory"]
    if inventory["unresolved_inputs"] != 0:
        return None
    protected = set(inventory["authority_domains"])
    protected.update(row["net"] for group in ("legs", "segments") for row in inventory[group])
    protected.update(net for pair in manifests[0]["declared_pairs"] for net in pair)
    nets = set()
    for path, (_, nodes) in zip((source, candidate), parsed):
        board = pcbnew.LoadBoard(str(path))
        live = {str(t.m_Uuid.AsString()): t for t in board.GetTracks()}
        for uid in changed & nodes.keys():
            item = live.get(uid)
            require(item is not None and item.GetClass() == "PCB_TRACK" and item.GetNetname(),
                    "literal_native_track_only_kelvin_noninterference_required")
            nets.add(str(item.GetNetname()))
    if nets & protected:
        return None
    require(families == [force._family(p, board_hint) for p in (source, candidate)]
            and epoch == force._code_identity(), "kelvin_noninterference_epoch_changed")
    return dict(ok=True, complete=True, scope="exact_protected_kelvin_noninterference",
                changed_track_uuids=sorted(changed), changed_nets=sorted(nets),
                protected_nets=sorted(protected), exact_other_native_material_and_settings=True,
                manifest_sha256=[m["shard_manifest_sha256"] for m in manifests],
                full_kelvin_qualification=False, inherited_faults_qualified=False,
                source_candidate_and_code_unchanged=True, release_authority=False)


def kelvin_pair(source, candidate, *, board_hint):
    import pcbnew
    import cec_force_sense_evidence as sense
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax

    preserved = _kelvin_noninterference(source, candidate, board_hint=board_hint)
    if preserved is not None:
        return preserved

    before, after = [
        sense.replay(path, board_hint=board_hint, timeout_s=10.0)
        for path in (source, candidate)
    ]
    _, old = additive._nodes(source)
    _, new = additive._nodes(candidate)
    changed = {
        key
        for key in old.keys() | new.keys()
        if key not in old
        or key not in new
        or syntax._freeze(old[key]) != syntax._freeze(new[key])
    }
    boards = [pcbnew.LoadBoard(str(path)) for path in (source, candidate)]
    nets = sorted(
        {
            str(item.GetNetname())
            for board in boards
            for item in [*board.GetTracks(), *board.Zones()]
            if str(item.m_Uuid.AsString()) in changed and str(item.GetNetname())
        }
    )
    if nets:
        transforms = sense.native_copper_transform_inventory(
            *boards, modified_nets=nets
        )
        result = sense.compare_contour_preservation(
            before, after, modified_nets=nets, native_copper_transforms=transforms
        )
    else:
        result = sense.compare_contact_preservation(before, after)
    return dict(
        ok=result.get("comparison_complete") is True
        and result.get("same_evidence") is True,
        complete=result.get("comparison_complete") is True,
        physical_evidence=result,
        full_kelvin_qualification=False,
        release_authority=False,
    )


def _assembly_faults(result):
    """Receive the native assembly schema, retaining identity AND severity.

    Higher signed margins are safer. Missing dimensions are unknown, not
    inherited physical debt. No fallback from an opaque FAIL to a category
    name can authorize a changed assembly.
    """
    import math

    def need(value):
        require(value, "complete_typed_native_assembly_evidence_required")

    def finite(value):
        need(type(value) in (int, float) and math.isfinite(value))
        return float(value)

    def literal(value):
        need(type(value) is str and bool(value))
        return value

    def rows(value):
        need(type(value) is list and len(value) <= 16384)
        return value

    def boolean(value):
        need(type(value) is bool)
        return value

    # Reject invalid numeric evidence even outside the failed-row subset.
    def numeric_tree(value, depth=0):
        need(depth <= 32)
        if type(value) is float:
            need(math.isfinite(value))
        elif type(value) is dict:
            for child in value.values():
                numeric_tree(child, depth + 1)
        elif type(value) in (list, tuple):
            for child in value:
                numeric_tree(child, depth + 1)

    need(type(result) is dict)
    numeric_tree(result)
    need(type(result.get("schema")) is int and result["schema"] == 1)
    need(result.get("applicable") is True and result.get("authority_unchanged") is True)
    need(result.get("complete", True) is True and result.get("timed_out", False) is False)
    need(result.get("source_unchanged", True) is True)
    overall = boolean(result.get("ok"))
    faults = {}

    def add(key, severity=()):
        need(key not in faults)
        faults[key] = tuple(severity)

    for row in rows(result.get("missing")):
        need(type(row) is dict and row.get("side") in ("carrier", "cover"))
        add(("missing", row["side"], literal(row.get("ref")), literal(row.get("footprint"))))
    kinds = {"body_to_laminate", "body_to_laminate_edge_clearance", "vent_to_laminate",
             "opposing_bodies", "opposing_body_edge_clearance"}
    for row in rows(result.get("violations")):
        need(type(row) is dict and row.get("kind") in kinds and row.get("ok") is False)
        refs = tuple(literal(ref) for ref in rows(row.get("refs")))
        need(len(refs) == 2)
        margin = finite(row.get("margin_mm"))
        need(margin < -1e-8)
        add(("clearance", row["kind"], *refs), (margin,))

    for index, group in enumerate(rows(result.get("contacts"))):
        need(type(group) is dict)
        contacts = rows(group.get("contacts"))
        need(bool(contacts))
        ids = set()
        failures = 0
        distances = []
        for row in contacts:
            need(type(row) is dict)
            pin = literal(row.get("id"))
            need(pin not in ids)
            ids.add(pin)
            distance = finite(row.get("distance_mm"))
            need(distance >= 0)
            distances.append(distance)
            role = boolean(row.get("role_ok"))
            good = boolean(row.get("ok"))
            need(not good or role)
            if not good:
                failures += 1
                # The immutable contract fixes mating-pair order; pin IDs
                # remain actual numbered contacts, never nearest-pad matches.
                add(("contact", str(index), pin), (-distance, int(role)))
        need(boolean(group.get("ok")) == (failures == 0))
        need(type(group.get("mismatched")) is int and group["mismatched"] == failures)
        need(finite(group.get("max_offset_mm")) == max(distances))

    for row in rows(result.get("hardware")):
        need(type(row) is dict)
        anchors = tuple(literal(ref) for ref in rows(row.get("anchor_pair")))
        need(len(anchors) == 2)
        conflicts = rows(row.get("conflicts"))
        need(boolean(row.get("ok")) == (not conflicts))
        for conflict in conflicts:
            need(type(conflict) is list and len(conflict) == 2
                 and conflict[0] in ("carrier", "cover"))
            add(("hardware", *anchors, conflict[0], literal(conflict[1])))

    for row in rows(result.get("vent_reservations")):
        need(type(row) is dict and row.get("receiver") in ("carrier", "cover"))
        ref = literal(row.get("ref"))
        hits = rows(row.get("copper_hits"))
        covers = boolean(row.get("native_rule_covers"))
        need(boolean(row.get("ok")) == (not hits and covers))
        if not covers:
            add(("vent_rule", row["receiver"], ref))
        for hit in hits:
            add(("vent_copper", row["receiver"], ref, literal(hit)))

    vertical = result.get("vertical")
    need(type(vertical) is dict and vertical.get("complete") is True
         and vertical.get("missing") == [])
    vertical_ok = []
    for name, dimensions in (("vent", ("worst_margin_mm",)),
                             ("engagement", ("under_insertion_margin_mm", "over_insertion_margin_mm"))):
        row = vertical.get(name)
        need(type(row) is dict)
        margins = tuple(finite(row.get(key)) for key in dimensions)
        good = boolean(row.get("ok"))
        need(good == all(margin >= -1e-9 for margin in margins))
        vertical_ok.append(good)
        for key, margin in zip(dimensions, margins):
            if margin < -1e-9:
                add(("vertical", name, key), (margin,))
    need(boolean(vertical.get("ok")) == all(vertical_ok))
    need(overall == (not faults))
    return faults


def assembly_pair(source, candidate):
    import cec_assembly_envelope as assembly

    old_policy = assembly.declared_policy(str(source))
    new_policy = assembly.declared_policy(str(candidate))
    require(old_policy == new_policy, "declared_assembly_contract_changed")
    if old_policy is None:
        return dict(
            ok=True,
            complete=True,
            scope="no_declared_cross_board_assembly_contract",
            assembly_qualified=False,
            release_authority=False,
        )
    before = assembly.candidate_check(str(source))
    after = assembly.candidate_check(str(candidate))
    require(
        type(before) is dict and type(after) is dict,
        "complete_declared_assembly_evidence_required",
    )

    try:
        old, last = [_assembly_faults(result) for result in (before, after)]
    except (ValueError, TypeError, KeyError) as exc:
        return dict(ok=False, complete=False, errors=[str(exc)], before=before, after=after,
                    assembly_qualified=False, inherited_faults_qualified=False, release_authority=False)
    new = sorted(last.keys() - old.keys())
    worse = sorted(key for key in old.keys() & last.keys()
                   if len(old[key]) != len(last[key])
                   or any(b < a for a, b in zip(old[key], last[key])))
    return dict(
        ok=not new and not worse,
        complete=True,
        new_faults=new,
        worsened_faults=worse,
        before=before,
        after=after,
        assembly_qualified=after.get("ok") is True,
        inherited_faults_qualified=False,
        release_authority=False,
    )
