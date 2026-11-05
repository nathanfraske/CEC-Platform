"""Make topology-local bypass copper an input to prospective power planning.

This uses the ordinary admitted local-cell constructor, not a second router.
Existing copper is never ripped up. Exact replay and filled reference-plane
proof are mandatory consumers; a planner success alone is not admission.
"""
from pathlib import Path


class LocalCellsRefused(RuntimeError):
    def __init__(self, report):
        self.report = report
        failures = [{key: row.get(key) for key in ('owner', 'pin', 'cap', 'reason')}
                    for row in report.get('refused') or ()]
        super().__init__('pre-freeze local cells refused: %s' %
                         (failures or report.get('reason') or 'missing admission'))


def prepare(source, params):
    """Return a private, stage-admitted local-copper board and its receipt."""
    import cec_decoupler_cell

    if not params.get('pourfirst_local_pi', True):
        return str(source), dict(schema=1, applicable=False, skipped='disabled')
    target = Path(source).with_name(Path(source).stem + '.local-pi.kicad_pcb')
    report = cec_decoupler_cell.synthesize_pre_route(
        str(source), str(target),
        ground_reach_mm=float(params.get('decoupler_ground_reach_mm', 1.5)),
        ground_pin_max_mm=float(params.get('decoupler_ground_pin_max_mm', 2.5)),
        repair_existing_copper=False)
    report = dict(report, applicable=True)
    if (report.get('ok') is not True or report.get('priority_complete') is not True
            or report.get('rolled_back')):
        raise LocalCellsRefused(report)
    return str(target), report


def identities(report):
    """Only explicitly generated copper belongs in the exact handoff."""
    return {str(row['uuid']) for row in report.get('generated_items') or ()
            if row.get('uuid')}


def replay_for_measurement(board, board_path, params):
    """Measure the exact certified future local copper, not a new search.

    Only the disposable native board is changed. The exact power certificate
    must bind the current PCB bytes, and the copper handoff separately binds
    every relevant terminal's geometry. Legacy states retain their old path.
    """
    import hashlib
    import json
    import cec_power_local_replay

    path = params.get('pourfirst_state')
    if not path:
        return dict(applicable=False, reason='no_power_authority')
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    local = state.get('pre_freeze_local_pi') or {}
    if not local.get('applicable'):
        return dict(applicable=False, reason='no_early_local_cells')
    if (state.get('placement_scope') != 'complete'
            or (state.get('exact_admission') or {}).get('passed') is not True
            or (state.get('exact_admission_context') or {}).get('board_sha256') !=
                hashlib.sha256(Path(board_path).read_bytes()).hexdigest()):
        return dict(applicable=False, reason='local_power_composition_not_bound')
    if local.get('ok') is not True or local.get('rolled_back'):
        raise LocalCellsRefused(local)
    receipt = cec_power_local_replay.replay(board, state['local_copper_contract'])
    return dict(receipt, applicable=True, source='exact_admitted_power_composition')


def finish_reference_planes(board, board_path, report):
    """Prove these precise local returns on real filled reference planes."""
    import cec_ground_plane

    if not report.get('applicable'):
        return dict(schema=1, applicable=False, ok=True)
    if report.get('ok') is not True or report.get('rolled_back'):
        raise LocalCellsRefused(report)
    required = cec_ground_plane.required_vias_from_ground_report(report)
    if not required:
        return dict(schema=1, applicable=False, ok=True, reason='no_local_plane_entries')
    result = cec_ground_plane.fill_board(
        board, board_path=board_path, required_via_uuids=required)
    if result.get('ok') is not True:
        raise RuntimeError('pre-freeze local return-plane proof refused: %s' %
                           result.get('reasons'))
    return result
