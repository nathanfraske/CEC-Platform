"""Capability-specific independent checks over actual saved families."""

from .identity import require
from .legacy import bootstrap

bootstrap()


def kelvin_pair(source, candidate, *, board_hint):
    import pcbnew
    import cec_force_sense_evidence as sense
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax

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
