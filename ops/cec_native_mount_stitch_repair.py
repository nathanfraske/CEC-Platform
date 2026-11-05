"""Apply the existing factory radial-stitch actuator to a private saved family.

Only the declared mechanical satellite-pad positions may differ. The primary
bore, contact land, all footprint poses and every routed conductor are exact.
Fresh native/typed/assembly receiving is still required before selection.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet = wx.LogNull()
import pcbnew
import cec_fab_check as factory
import cec_fab_native_geometry as native
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_mounting_contract as mounts


def propose(source, out, *, board_hint, allow_locked_mount_uuids=()):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('fresh private mount-repair directory required')
    epoch = force._code_identity()
    family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source))
    selected = fab.board_profile_name(board)
    if not selected:
        raise ValueError('saved declared fabrication profile required')
    rules = factory.profile_rules(factory.PROFILES['jlcpcb'], factory.board_outer_copper_oz(source),
                                  fab.get_profile(selected))
    before = field._field_snapshot_inventory(board)
    poses = {force._uid(fp): (tuple(fp.GetPosition()), fp.GetOrientationDegrees(),
             int(fp.GetLayer()), fp.IsLocked()) for fp in board.GetFootprints()}
    old_holes = native.audit_holes(board, rules, board_path=source)
    result = mounts.repair_native_mount_fields(board, rules, board_path=source,
        allow_locked_footprint_uuids=allow_locked_mount_uuids)
    if not result['complete'] or not result['applied_count']:
        raise ValueError('no complete eligible stitch repair: ' + str(result))
    changed = {row['uuid'] for detail in result['details'] for row in detail.get('changes', [])}
    after = field._field_snapshot_inventory(board)
    def without_repaired_pads(inventory):
        return {key: value for key, value in inventory.items()
                if not (key[0] == 'pad' and key[2] in changed)}
    if without_repaired_pads(before) != without_repaired_pads(after):
        raise ValueError('mount repair changed unrelated native material')
    before_pads = {key[2]: (key, value) for key, value in before.items() if key[0] == 'pad' and key[2] in changed}
    after_pads = {key[2]: (key, value) for key, value in after.items() if key[0] == 'pad' and key[2] in changed}
    if set(before_pads) != changed or set(after_pads) != changed:
        raise ValueError('mount repair replaced a terminal identity')
    for uid in changed:
        key, value = before_pads[uid]
        new_key, new_value = after_pads[uid]
        if key[:4] != new_key[:4] or value != new_value:
            raise ValueError('mount repair changed satellite dimensions, nets or layer spans')
    if poses != {force._uid(fp): (tuple(fp.GetPosition()), fp.GetOrientationDegrees(),
                 int(fp.GetLayer()), fp.IsLocked()) for fp in board.GetFootprints()}:
        raise ValueError('mount repair changed a footprint pose or lock')
    new_holes = native.audit_holes(board, rules, board_path=source)
    if not old_holes['complete'] or not new_holes['complete']:
        raise ValueError('complete independent drill audit required')
    def pair_id(row):
        return tuple(sorted((row['left']['uuid'], row['right']['uuid'])))
    old_pairs = {pair_id(row) for row in old_holes['findings']}
    if any(pair_id(row) not in old_pairs for row in new_holes['findings']):
        raise ValueError('stitch repair introduces a new factory hole conflict')
    if len(new_holes['findings']) >= len(old_holes['findings']):
        raise ValueError('stitch repair does not reduce factory hole conflicts')
    candidate = force._copy_family(source, out)
    field._save_field_snapshot(board, candidate)
    if epoch != force._code_identity() or family != force._family(source, board_hint):
        raise ValueError('source family or engine changed during mount repair')
    receipt = dict(schema=1, scope='private_native_mechanical_stitch_positions_only',
                   source=str(source), source_sha256=force._hash(source), candidate=str(candidate),
                   candidate_sha256=force._hash(candidate), proposed=True,
                   repair=result, changed_pad_uuids=sorted(changed),
                   factory_hole_findings_before=len(old_holes['findings']),
                   factory_hole_findings_after=len(new_holes['findings']),
                   exact_routed_copper=True, footprint_poses_exact=True,
                   primary_bores_and_contact_lands_exact=True,
                   code_identity=epoch, helper_sha256=force._hash(Path(__file__)),
                   native_drc_receiving_pending=True, clipped_kelvin_receiving_pending=True,
                   matched_assembly_receiving_pending=True,
                   routing_admitted=False, fab_ready=False, release_authority=False)
    force._write(out / 'mount-stitch-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--board-hint', required=True)
    parser.add_argument('--allow-locked-mount-uuid', action='append', default=[])
    args = parser.parse_args()
    result = propose(args.source, args.out, board_hint=args.board_hint,
                     allow_locked_mount_uuids=args.allow_locked_mount_uuid)
    print(json.dumps({key: value for key, value in result.items() if key in (
        'candidate', 'candidate_sha256', 'factory_hole_findings_before', 'factory_hole_findings_after',
        'primary_bores_and_contact_lands_exact')}), flush=True)
