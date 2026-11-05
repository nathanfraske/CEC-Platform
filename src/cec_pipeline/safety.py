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

    def faults(result):
        return set(map(str, assembly.failure_reasons(result)))

    complete = all(type(row.get("ok")) is bool for row in (before, after))
    new = sorted(faults(after) - faults(before))
    return dict(
        ok=complete and not new,
        complete=complete,
        new_faults=new,
        before=before,
        after=after,
        assembly_qualified=after.get("ok") is True,
        inherited_faults_qualified=False,
        release_authority=False,
    )
