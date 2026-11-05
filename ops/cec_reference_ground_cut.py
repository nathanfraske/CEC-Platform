"""Construct one explicitly selected, reference-backed shared Ground cut.

Agent construction tool, not automatic admission. No refdes/board/coordinate lookup,
nearest-via substitution, rule waiver or final fab authority. Independent
whole-parent current/field/native/clipped-Kelvin/stack receiving is required.
"""
import argparse
import json
import re
from pathlib import Path

import cec_swig_guard;cec_swig_guard.pin()
import wx;quiet=wx.LogNull()
import cec_field_coupling as field
import cec_force_current as force
import cec_reference_backed_ground_cut as operation


def run(source,out,*,board_hint,expected_source_sha256,retired_track_uuids,allow_locked_track_uuids=()):
    source,out=Path(source).resolve(),Path(out).resolve()
    operation._settings(retired_track_uuids,allow_locked_track_uuids,board_hint,10.)
    if (type(expected_source_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',expected_source_sha256)
            or force._hash(source)!=expected_source_sha256):
        raise ValueError('literal_expected_source_sha256_required')
    if out.exists():raise ValueError('fresh_private_reference_ground_cut_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    tool=Path(__file__).resolve();tool_hash=force._hash(tool)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,
        input_sha256={str(tool):tool_hash},records=[],routing_admitted=False,fab_ready=False,release_authority=False)
    out.mkdir(parents=True,exist_ok=False)
    try:
        proposal=operation.plan(source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
            allow_locked_track_uuids=allow_locked_track_uuids)
        board=operation.construct(source,proposal)
        child=force._copy_family(source,out/'UNADMITTED-reference-ground-cut')
        field._save_field_snapshot(board,child)
        receiving=operation.receive(source,child,proposal,board_hint=board_hint)
        r.update(ok=receiving['ok'],complete=receiving['complete'],changed=receiving['ok'],errors=receiving['errors'],
            candidate=str(child),candidate_sha256=force._hash(child),records=[dict(plan=proposal)],
            independent_saved_receiving=receiving)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=(epoch==force._code_identity() and family==force._family(source,board_hint)
        and force._hash(tool)==tool_hash)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False);r['errors'].append('reference_ground_cut_input_epoch_changed')
    force._write(out/'stage.json',r)
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out'):parser.add_argument('--'+key,type=Path,required=True)
    for key in ('board-hint','expected-source-sha256'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--retired-track-uuid',action='append',required=True)
    parser.add_argument('--allow-locked-track-uuid',action='append',default=[])
    args=parser.parse_args()
    r=run(args.source,args.out,board_hint=args.board_hint,expected_source_sha256=args.expected_source_sha256,
        retired_track_uuids=args.retired_track_uuid,allow_locked_track_uuids=args.allow_locked_track_uuid)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
