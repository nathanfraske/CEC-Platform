"""Finite, source-native-warning-driven contained-barrel finishing stage."""
import argparse
import json
import math
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_contained_one_face_barrel_retirement as retirement
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_stage_admission as admission


def run(source, outdir, *, board_hint, expected_source_sha256, reporting_build,
        allow_locked_source=False, allow_grouped_source=False,
        maximum_barrels=8, sense_timeout_s=40., allow_leaf_cleanup=False):
    if (type(board_hint) is not str or not board_hint
            or type(expected_source_sha256) is not str or len(expected_source_sha256) != 64
            or type(allow_locked_source) is not bool or type(allow_grouped_source) is not bool
            or type(allow_leaf_cleanup) is not bool
            or type(maximum_barrels) is not int or not 1 <= maximum_barrels <= 8
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0 < sense_timeout_s <= 60.
            or reporting_build is None):
        raise ValueError('bounded_explicit_source_contained_barrel_stage_required')
    source = Path(source).resolve(); outdir = Path(outdir).resolve()
    if force._hash(source) != expected_source_sha256 or outdir.exists():
        raise ValueError('exact_unchanged_source_and_fresh_output_required')
    outdir.mkdir(parents=True)
    started = time.monotonic(); epoch = force._code_identity(); family = force._family(source, board_hint)
    result = dict(schema=1, source=str(source), source_sha256=expected_source_sha256,
        candidate=str(source), candidate_sha256=expected_source_sha256, code_identity=epoch,
        ok=False, complete=False, changed=False, errors=[], source_requests=[], refused_requests=[],
        source_selected=False, routing_admitted=False, fab_ready=False, release_authority=False,
        maximum_barrels=maximum_barrels,allow_leaf_cleanup=allow_leaf_cleanup,
        allow_locked_source=allow_locked_source,allow_grouped_source=allow_grouped_source)
    def observe(path, label):
        dest = outdir/(label+'.drc.json')
        # kicad-cli may create a .kicad_prl even during read-only diagnosis.
        # Observe a byte-identical, complete private family; never let that
        # cache write mutate the source or the saved receiving candidate.
        shadow = force._copy_family(path, outdir/(label+'-native-input'))
        proof = native.run(shadow, dest, reporting_build=reporting_build, timeout_s=10.)
        proof['literal_observed_original'] = dict(path=str(path), sha256=force._hash(path),
            exact_board_bytes_match=force._hash(shadow)==force._hash(path),
            original_native_rules_and_project_match=all(force._hash(shadow.with_suffix(ext))
                == force._hash(path.with_suffix(ext)) for ext in ('.kicad_pro','.kicad_dru')))
        result.setdefault('native_producers', {})[label] = proof
        if (not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']
                or not proof['literal_observed_original']['exact_board_bytes_match']
                or not proof['literal_observed_original']['original_native_rules_and_project_match']):
            raise ValueError('uncapped_complete_native_contained_barrel_inventory_required')
        return json.loads(dest.read_text())
    try:
        first = observe(source, 'source')
        if first['unconnected_items']:
            raise ValueError('contained_barrel_finishing_requires_zero_open_source')
        requested = sorted({i['uuid'] for row in first['violations'] if row['type']=='via_dangling'
                            for i in row['items']})
        result['native_dangling_source_uuids'] = requested
        board = pcbnew.LoadBoard(str(source)); live = {force._uid(t):t for t in board.GetTracks()}
        accepted = []; accepted_leaves = []
        for uid in requested[:maximum_barrels]:
            if uid not in live or live[uid].GetClass() != 'PCB_VIA':
                raise ValueError('native_dangling_warning_must_identify_actual_source_barrel')
            kwargs = dict(allow_locked_via_uuids=[uid] if allow_locked_source else [],
                          allow_grouped_via_uuids=[uid] if allow_grouped_source else [])
            try:
                leaves = retirement.attached_short_leaf_uuids(board,[uid]) if allow_leaf_cleanup else []
                if leaves:
                    kwargs.update(leaf_track_uuids=leaves,
                        allow_locked_leaf_track_uuids=leaves if allow_locked_source else [],
                        allow_grouped_leaf_track_uuids=leaves if allow_grouped_source else [])
                proof = retirement.plan(board, [uid], **kwargs)
                result['source_requests'].append(proof)
                accepted.append(uid);accepted_leaves.extend(leaves)
            except (ValueError, RuntimeError, TypeError, KeyError) as exc:
                result['refused_requests'].append(dict(uuid=uid, refusal=type(exc).__name__+':'+str(exc)))
        result['native_request_inventory_complete'] = len(requested) <= maximum_barrels
        if accepted:
            proposal = retirement.plan(board, accepted,
                allow_locked_via_uuids=accepted if allow_locked_source else [],
                allow_grouped_via_uuids=accepted if allow_grouped_source else [],
                leaf_track_uuids=accepted_leaves,
                allow_locked_leaf_track_uuids=accepted_leaves if allow_locked_source else [],
                allow_grouped_leaf_track_uuids=accepted_leaves if allow_grouped_source else [])
            result['construction'] = proposal; retirement.subtract(board, proposal)
            additive._ground_refill(board)
            child = force._copy_family(source, outdir/'UNADMITTED-contained-one-face-barrels')
            field._save_field_snapshot(board, child)
            result['unadmitted_diagnostic_candidate'] = str(child)
            last = observe(child, 'candidate')
            result['new_native_fault_ids'] = sorted({admission._canonical_identity(v) for v in last['violations']}
                - {admission._canonical_identity(v) for v in first['violations']})
            if last['unconnected_items'] or result['new_native_fault_ids']:
                raise ValueError('contained_barrel_new_native_fault_or_open')
            left = {i['uuid'] for row in last['violations'] if row['type']=='via_dangling' for i in row['items']}
            if left & set(accepted): raise ValueError('selected_native_dangling_barrel_was_not_retired')
            proof = retirement.receive(source, child, proposal,
                board_hint=board_hint, sense_timeout_s=sense_timeout_s)
            result['independent_whole_source_receiving'] = proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('contained_barrel_whole_source_receiving_refused:'+str(proof['errors']))
            result.update(candidate=str(child), candidate_sha256=force._hash(child), changed=True,
                          retired_native_dangling_barrels=len(accepted),
                          retired_pad_free_source_leaf_tracks=len(accepted_leaves))
        result.update(ok=True, complete=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    stable = epoch == force._code_identity() and family == force._family(source, board_hint)
    result['source_family_and_code_unchanged'] = stable
    if not stable:
        result.update(ok=False, complete=False)
        result['errors'].append('contained_barrel_source_or_code_changed')
    if not result['ok']:
        result.update(candidate=str(source),candidate_sha256=expected_source_sha256,changed=False)
    result['wall_elapsed_s'] = time.monotonic()-started
    force._write(outdir/'stage.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):parser.add_argument('--'+key,type=Path,required=True)
    for key in ('board-hint','expected-source-sha256'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--allow-locked-source',action='store_true')
    parser.add_argument('--allow-grouped-source',action='store_true')
    parser.add_argument('--allow-leaf-cleanup',action='store_true')
    parser.add_argument('--maximum-barrels',type=int,default=8)
    args=parser.parse_args()
    result=run(args.source,args.out,board_hint=args.board_hint,
        expected_source_sha256=args.expected_source_sha256,reporting_build=args.reporting_build,
        allow_locked_source=args.allow_locked_source,allow_grouped_source=args.allow_grouped_source,
        allow_leaf_cleanup=args.allow_leaf_cleanup,maximum_barrels=args.maximum_barrels)
    print(json.dumps({key:result.get(key) for key in ('ok','complete','changed','candidate',
        'retired_native_dangling_barrels','refused_requests','errors')}),flush=True)


if __name__ == '__main__':main()
