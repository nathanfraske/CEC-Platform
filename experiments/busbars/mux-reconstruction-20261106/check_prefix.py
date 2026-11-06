"""Independent saved prefix receivers, separate ten-second processes."""
import importlib.util
import json
from pathlib import Path
import sys
import time
from output_prefix import ROOT, WORK, SOURCE, SHA, CUTS, HINT
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]


def main():
    import pcbnew as p
    import cec_force_current as force
    name = sys.argv[1]
    record = json.loads((WORK / 'output-prefix-construction.json').read_text())
    candidate = Path(record['candidate'])
    revision = sys.argv[2] if len(sys.argv) > 2 else ''
    assert len(revision) <= 32 and all(c.isalnum() or c in '-_' for c in revision)
    out = WORK / 'output-prefix-v1' / ('checks-' + revision if revision else 'checks')
    out.mkdir(exist_ok=True)
    target = out / (name + '.json')
    assert not target.exists(), 'fresh_independent_stage_required'
    epoch = dict(source=force._hash(SOURCE), candidate=force._hash(candidate),
                 source_sidecars=force._sidecars(SOURCE),
                 candidate_sidecars=force._sidecars(candidate),
                 code_identity=force._code_identity())
    assert epoch['source'] == SHA and epoch['candidate'] == record['candidate_sha256']
    start = time.monotonic()
    if name == 'reflow':
        import cec_full_current_planar_reflow as reflow
        result = reflow.receive(SOURCE, candidate, board_hint=HINT,
                               retired_track_uuids=CUTS, max_source_track_mm=9., timeout_s=9.)
    elif name == 'seat':
        import cec_fr as fr
        import cec_fab_profile as fab
        study = json.loads((ROOT / 'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json').read_text())
        board = p.LoadBoard(str(candidate))
        fps = {f.GetReference(): f for f in board.GetFootprints()}
        for ref, at in study['proposed_poses'].items():
            fps[ref].SetOrientationDegrees(at[2]); fps[ref].SetPosition(p.VECTOR2I(*at[:2]))
        via = p.PCB_VIA(board); via.SetPosition(p.VECTOR2I_MM(20.5, 50.54))
        via.SetWidth(500000); via.SetDrill(300000); via.SetLayerPair(p.F_Cu, p.B_Cu)
        via.SetNetCode(board.GetNetcodeFromNetname('GND')); board.Add(via)
        process = fab.local_pofv_via_decision(board, via)
        detail = {}
        clear = fr._via_spot_clear(board, via.GetPosition(), via.GetWidth(via.TopLayer()),
            200000, {via.GetNetCode()}, drill_nm=via.GetDrillValue(), net_code=via.GetNetCode(),
            existing_via_uuid=force._uid(via), native_padstack_via=via, report=detail)
        result = dict(ok=bool(process[0] and clear), full_pad_containment=process,
            all_layer_clear=clear, guard=detail, at_nm=list(via.GetPosition()),
            original_power_fills_retained=True, no_source_tracks_temporarily_omitted=True,
            board_saved=False, actual_cohort_not_yet_constructed=True)
    else:
        # Reuse the exact established independent physical checks, not their
        # prior reports. Only the producer-specific barrel checks are excluded.
        import cec_field_coupling as field
        if name == 'ground':
            import cec_ground_return_preservation as returns
            result = returns.receive(p.LoadBoard(str(SOURCE)), p.LoadBoard(str(candidate)), timeout_s=8.5)
        elif name == 'current':
            import cec_current_debt as debt
            result = debt.receive(SOURCE, candidate, board_hint=HINT)
        elif name == 'craft':
            import cec_route_quality as craft
            a, z = [craft.analyze_board(p.LoadBoard(str(v))) for v in (SOURCE, candidate)]
            result = dict(ok=z['issue_count'] <= a['issue_count'] and z['non_octilinear_count'] <= a['non_octilinear_count'],
                          before_after=[a['issue_count'], z['issue_count']],
                          non_octilinear_before_after=[a['non_octilinear_count'], z['non_octilinear_count']])
        elif name == 'pairs':
            from cec_pipeline import pairs
            result = pairs.receive(SOURCE, candidate, timeout_s=8.)
        elif name.startswith('drc-'):
            import cec_native_drc_runner as drc
            path = SOURCE if name == 'drc-source' else candidate
            raw = out / (name + '-native.json')
            result = drc.run(path, raw, reporting_build=Path('/home/codex/.cache/cec/native-drc-10.0.5'),
                timeout_s=8.5, footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
            if result.get('ok') and result.get('complete'):
                data = json.loads(raw.read_text())
                counts = dict(errors=sum(v.get('severity') == 'error' for v in data['violations']),
                              warnings=sum(v.get('severity') == 'warning' for v in data['violations']), opens=len(data['unconnected_items']))
                result = dict(ok=counts['errors'] == counts['opens'] == 0, counts=counts, producer=result)
        elif name.startswith('field-'):
            import cec_additive_route_receiving as additive
            path = SOURCE if name == 'field-source' else candidate
            board = p.LoadBoard(str(path))
            before = field._field_snapshot_inventory(board)
            if path == candidate:
                additive._ground_refill(board)
                assert field._field_snapshot_inventory(board) == before, 'saved_fill_not_exact'
            result = dict(ok=True, report=field.field_coupling_summary(str(path), board=board, board_hint=HINT,
                _work=field._ProposalWork(start + 9., 16384, 1000000, 1000000, 16384)))
        else:
            raise ValueError('unknown_check')
    assert epoch == dict(source=force._hash(SOURCE), candidate=force._hash(candidate),
        source_sidecars=force._sidecars(SOURCE), candidate_sidecars=force._sidecars(candidate),
        code_identity=force._code_identity())
    report = dict(stage=name, identity=epoch, result=result, ok=result.get('ok') is True,
                  elapsed_s=time.monotonic() - start, release_authority=False)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(stage=name, ok=report['ok'], errors=result.get('errors'),
        counts=result.get('counts'), elapsed_s=report['elapsed_s'])))


if __name__ == '__main__':
    main()
