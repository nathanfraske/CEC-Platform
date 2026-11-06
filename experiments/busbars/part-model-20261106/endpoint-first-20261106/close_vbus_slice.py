"""Join bound independent results without upgrading qualification or controls."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import cec_force_current as force
import cec_force_sense_evidence as sense

OUT = Path(__file__).parent / 'vbus-shortcut-v6'


def main():
    read = lambda path: json.loads(path.read_text())
    construction = read(OUT / 'construction.json')
    whole = read(OUT / 'whole-board-receiving.json')
    field = read(OUT / 'field-receiving-v2.json')
    shards = OUT / 'sense-sharded-v1'
    old_sense, new_sense = [read(shards / label / 'assembled.json') for label in ('source','candidate')]
    compare = sense.compare_contact_preservation(old_sense, new_sense)
    tests = read(OUT / 'regressions/result.json')
    accepted = ['fresh_exact_planar_source_cut','ground_returns','whole_current_nonregression',
                'tracecraft','paired_signal_nonregression','saved_matched_stack',
                'source_frozen_native_drc','candidate_frozen_native_drc']
    assert all(whole['stages'][k]['ok'] and whole['stages'][k]['result']['ok'] for k in accepted)
    assert whole['source_candidate_context_and_code_unchanged']
    for path, sha in whole['identity']['files'].items():
        assert force._hash(Path(path)) == sha, path
    assert force._code_identity() == whole['identity']['code_identity']
    assert field['ok'] and field['complete'] and not field['new_blockers']
    assert field['source_cut_receipt_sha256'] == force._hash(OUT / 'whole-board-receiving.json')
    assert field['identity']['code_identity'] == whole['identity']['code_identity']
    assert compare['same_evidence'] and compare['comparison_complete'] and not compare['errors']
    for label, proof in [('source',old_sense),('candidate',new_sense)]:
        board = Path(construction[label])
        assert proof['complete'] and not proof['stop'] and proof['identity_stable']
        assert proof['source_family_before'] == proof['source_family_after'] == force._family(board, 'atx-24pin-rev3')
        assert proof['code_before'] == proof['code_after'] == whole['identity']['code_identity']
        assert force._sidecars(board) == whole['identity'][label+'_sidecars']
        assert proof['sharded_replay']['full_exact_coverage_join']
    assert tests['ok'] and sum(len(r['tests']) for r in tests['batches']) == tests['collected']
    selector = ROOT / 'checkpoints/current.json'
    assert force._hash(selector) == '1798d2a9b8bfef323c08a5a1aa25ba9872333657a7234e4f8a0d1c9859c82484'
    files = ['construction.json','whole-board-receiving.json','field-receiving-v2.json',
             'source-field-v2.json','candidate-field-v2.json','sense-sharded-v1/receipt.json',
             'sense-sharded-v1/source/assembled.json','sense-sharded-v1/candidate/assembled.json',
             'regressions/result.json','visual-review/sources.json','visual-review/before-after.png']
    out = dict(schema=1, status='private_native_shortcut_received_not_released',
               source=construction['source'], source_sha256=construction['source_sha256'],
               candidate=construction['candidate'], candidate_sha256=construction['candidate_sha256'],
               independent_nonregression_received=True, accepted_original_stages=accepted,
               route_length=whole['route_length'], frozen_native_before_after=[
                   whole['stages'][k]['result']['counts'] for k in ('source_frozen_native_drc','candidate_frozen_native_drc')],
               full_current_authority_preserved=True, current_fault_objects_before_after=[2,2],
               tracecraft_before_after=whole['stages']['tracecraft']['result']['before_after'],
               force_sense_strict_preservation=compare,
               field_blockers_before_after=field['before_after_blockers'], regression_tests_passed=tests['collected'],
               evidence={name:force._hash(OUT/name) for name in files},
               timeout_resolution=dict(
                   monolithic_kelvin_failed=True, repeated_monolithic_retry=False,
                   replacement='Existing exact 16-leg sharded replays, independently bounded under ten seconds; full fresh coverage join, strict physical comparison.',
                   field_combined_chain_failed=True,
                   replacement_field='Separate successful exact-cut receipt and whole actual saved source/candidate field workers with the same source/code epoch; exact Ground refill replay.'),
               board_outline_mm=[78,87.5], board_outline_changed=False, placements_changed=False,
               new_vias=0, retired_vias=0, bar_installed=False, xy_compaction_this_slice_mm=[0,0],
               reviewed_selector=dict(path=str(selector),sha256=force._hash(selector),changed=False),
               routing_admitted=False,current_qualified=False,thermal_qualified=False,
               assembled_z_qualified=False,fab_ready=False,release_authority=False,
               remaining=['Complete a real source-qualified bar topology, joints and full-current upper feed.',
                          'Short coated power jumpers are dimensional candidates only: underside isolation, installed height and usable procurement remain unqualified.',
                          'Prove actual X/Y reduction and no assembled Z increase; no new size reduction demonstrated here.',
                          'Resolve inherited current/thermal and manufacturing qualification before release.'])
    force._write(OUT / 'slice-closeout.json', out)
    print(json.dumps(dict(ok=True, report=str(OUT/'slice-closeout.json'),sha256=force._hash(OUT/'slice-closeout.json'), tests=tests['collected'])))


if __name__ == '__main__':
    main()
