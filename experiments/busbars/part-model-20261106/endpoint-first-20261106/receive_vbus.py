"""Independent whole-board checks for the private source-owned VBUS shortcut.

The explicit pilot paths are construction context, not general pipeline rules.
Every physical computation uses an existing board-agnostic receiver. Each
stage has its own ten-second lease; failures remain visible and block receipt.
"""
import json
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from cec_pipeline.native import _native
p, _ = _native()
from cec_pipeline import pairs
import cec_force_current as force
import cec_full_current_planar_reflow as reflow
import cec_current_debt as current
import cec_ground_return_preservation as returns
import cec_route_quality as craft
import cec_assembly_envelope as assembly
import cec_force_sense_evidence as sense
import cec_native_drc_runner as drc

OUT = Path(__file__).parent / 'vbus-shortcut-v6'
TABLE = ROOT / 'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table'
BUILD = Path('/home/codex/.cache/cec/native-drc-10.0.5')
COVER = ROOT / 'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
CONTRACT = ROOT / 'beta/assembly/hub-atx-stack.json'
HINT = 'atx-24pin-rev3'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    record = json.loads((OUT / 'construction.json').read_text())
    source, candidate = [Path(record[k]).resolve(strict=True) for k in ('source', 'candidate')]
    def identity():
        return dict(files={str(f): force._hash(f) for f in (source, candidate, COVER, CONTRACT, TABLE)},
                    source_sidecars=force._sidecars(source), candidate_sidecars=force._sidecars(candidate),
                    code_identity=force._code_identity())
    initial = identity()
    need(force._hash(source) == record['source_sha256'], 'source_hash_changed')
    need(force._hash(candidate) == record['candidate_sha256'], 'candidate_hash_changed')
    parent, child = [p.LoadBoard(str(f)) for f in (source, candidate)]
    out = dict(schema=1, scope='private_full_current_shortcut_whole_board_receiving',
               identity=initial, stages={}, errors=[], ok=False, complete=False,
               routing_admitted=False, current_qualified=False, release_authority=False)
    report = OUT / 'whole-board-receiving.json'
    def stage(name, fn):
        def expired(*_):
            raise TimeoutError('independent_stage_exceeded_ten_seconds')
        old = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, 10.)
        started = time.monotonic()
        try:
            value = fn()
            need(isinstance(value, dict), 'structured_stage_result_required')
            need(value.get('ok') is True and value.get('complete') is not False,
                 'receiver_refused:' + str(value.get('errors', value.get('reason', ''))))
            out['stages'][name] = dict(ok=True, result=value, elapsed_s=time.monotonic()-started)
            return value
        except Exception as exc:
            error = type(exc).__name__ + ':' + str(exc)
            out['errors'].append(name + ':' + error)
            out['stages'][name] = dict(ok=False, error=error, elapsed_s=time.monotonic()-started)
            return None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            force._write(report, out)
            print(json.dumps(dict(stage=name, ok=out['stages'][name]['ok'],
                                  elapsed_s=out['stages'][name]['elapsed_s'])), flush=True)

    stage('fresh_exact_planar_source_cut', lambda: reflow.receive(
        source, candidate, board_hint=HINT, retired_track_uuids=record['retired_track_uuids'], timeout_s=9.5))
    stage('ground_returns', lambda: returns.receive(parent, child, timeout_s=9.))
    stage('whole_current_nonregression', lambda: current.receive(source, candidate, board_hint=HINT))
    def quality():
        a, b = craft.analyze_board(parent), craft.analyze_board(child)
        need(b['issue_count'] <= a['issue_count'] and b['non_octilinear_count'] <= a['non_octilinear_count'],
             'whole_board_tracecraft_regression')
        return dict(ok=True, before_after=[a['issue_count'], b['issue_count']],
                    non_octilinear_before_after=[a['non_octilinear_count'], b['non_octilinear_count']])
    stage('tracecraft', quality)
    stage('paired_signal_nonregression', lambda: pairs.receive(source, candidate, timeout_s=8.))
    def stack():
        contract = json.loads(CONTRACT.read_text())
        fit, _ = assembly.evaluate(candidate, COVER, contract)
        vents = assembly.vent_reservations(child, assembly.facing_vents(fit, contract, 'carrier'))
        need(fit['ok'] and all(row['ok'] for row in vents), 'paired_body_or_vent_screen_refused')
        return dict(ok=True, body_checks=len(fit['checks']), vents=vents,
                    missing=fit['missing'], contacts=fit['contacts'], hardware=fit['hardware'],
                    assembled_height_qualified=False, no_new_part_or_placement=True)
    stage('saved_matched_stack', stack)
    def native(board, label):
        path = OUT / (label + '-frozen-native-drc.json')
        producer = drc.run(board, path, reporting_build=BUILD, timeout_s=9., footprint_table=TABLE)
        need(producer.get('ok') and producer.get('complete'), 'native_drc_unavailable')
        data = json.loads(path.read_text())
        counts = dict(errors=sum(v.get('severity') == 'error' for v in data['violations']),
                      warnings=sum(v.get('severity') == 'warning' for v in data['violations']),
                      opens=len(data['unconnected_items']))
        need(counts['errors'] == 0 and counts['opens'] == 0, 'native_errors_or_opens:' + str(counts))
        return dict(ok=True, counts=counts, producer=producer, report_sha256=force._hash(path))
    stage('source_frozen_native_drc', lambda: native(source, 'source'))
    stage('candidate_frozen_native_drc', lambda: native(candidate, 'candidate'))
    proofs = {}
    def replay(label, board):
        value = sense.replay(board, board_hint=HINT, timeout_s=9.)
        need(value.get('complete') is True, 'absolute_copper_replay_incomplete')
        proofs[label] = value
        force._write(OUT / (label + '-force-sense.json'), value)
        return dict(ok=True, complete=True, proof_sha256=force._hash(OUT / (label + '-force-sense.json')),
                    absolute_proof_not_global_qualification=True)
    stage('source_force_sense_replay', lambda: replay('source', source))
    stage('candidate_force_sense_replay', lambda: replay('candidate', candidate))
    def compare_sense():
        need(set(proofs) == {'source', 'candidate'}, 'both_fresh_absolute_proofs_required')
        result = sense.compare_contact_preservation(proofs['source'], proofs['candidate'])
        need(result.get('comparison_complete') and result.get('same_evidence'),
             'strict_force_sense_evidence_changed:' + str(result.get('errors')))
        return dict(ok=True, result=result, untouched_force_sense_evidence_exact=True)
    stage('strict_force_sense_preservation', compare_sense)
    out['source_candidate_context_and_code_unchanged'] = initial == identity()
    if not out['source_candidate_context_and_code_unchanged']:
        out['errors'].append('source_candidate_context_or_code_changed')
    out['complete'] = True
    out['ok'] = not out['errors'] and all(s['ok'] for s in out['stages'].values())
    old = {force._uid(t): t for t in parent.GetTracks()}
    new = {force._uid(t): t for t in child.GetTracks()}
    before = sum(old[u].GetLength() for u in record['retired_track_uuids']) / 1e6
    after = sum(new[u].GetLength() for u in record['added_track_uuids']) / 1e6
    out['route_length'] = dict(before_mm=before, after_mm=after, decrease_mm=before-after,
                               decrease_percent=100*(before-after)/before)
    out['limits'] = ['No bus bar installed; board outline and component placements unchanged.',
                     'Independent nonregression does not qualify inherited current or thermal debt.',
                     'Field-coupling source-cut receiving remains separate and required.']
    force._write(report, out)
    print(json.dumps(dict(ok=out['ok'], errors=out['errors'], route_length=out['route_length'], report=str(report))))


if __name__ == '__main__':
    main()
