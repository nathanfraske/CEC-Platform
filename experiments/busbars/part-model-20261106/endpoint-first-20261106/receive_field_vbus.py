"""Actual saved-parent field comparison after separately received planar cut.

Experimental job composition, not a new production receiver or qualification.
Run each worker under an external ten-second deadline. Full source-cut/Ground
replay is kept separate from field computation so it cannot consume that lease.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from cec_pipeline.native import _native
p, _ = _native()
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr

OUT = Path(__file__).parent / 'vbus-shortcut-v6'
HINT = 'atx-24pin-rev3'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def context():
    record = json.loads((OUT / 'construction.json').read_text())
    paths = [Path(record[k]) for k in ('source', 'candidate')]
    identity = dict(files={str(f): force._hash(f) for f in paths},
                    source_sidecars=force._sidecars(paths[0]), candidate_sidecars=force._sidecars(paths[1]),
                    code_identity=force._code_identity())
    return paths, identity


def worker(label):
    paths, identity = context()
    started = time.monotonic()
    deadline = started + 9.2
    board_path = paths[0 if label == 'source' else 1]
    board = p.LoadBoard(str(board_path))
    need(len(list(board.GetTracks())) + len(list(board.Zones())) <= 16384, 'field_inventory_bound')
    resolver = fr._project_netclass_resolver(str(board_path))
    for item in board.GetTracks():
        if item.GetClass() in ('PCB_TRACK', 'PCB_VIA'):
            continue
        role = field.classify_net(item.GetNetname(), netclass=field._netclass_name(resolver(item.GetNetname())))
        need(not role['aggressor'] and not role['victim'], 'classified_curved_copper_unsupported')
    before = field._field_snapshot_inventory(board)
    ground_count = 0
    if label == 'candidate':
        ground_count = len(additive._ground_refill(board))
        need(field._field_snapshot_inventory(board) == before, 'saved_field_copper_not_exact_refill')
    report = field.field_coupling_summary(str(board_path), board=board, board_hint=HINT,
        _work=field._ProposalWork(deadline, 16384, 1000000, 1000000, 16384))
    need(time.monotonic() < deadline, 'field_worker_deadline')
    need(context()[1] == identity and field._field_snapshot_inventory(board) == before,
         'field_source_or_code_or_native_geometry_changed')
    result = dict(ok=True, complete=True, identity=identity, label=label,
                  ground_refill_exact=True, refilled_ground_count=ground_count,
                  report=report, elapsed_s=time.monotonic()-started)
    force._write(OUT / (label + '-field-v2.json'), result)
    print(json.dumps(dict(label=label, blocking_count=report['blocking_count'], elapsed_s=result['elapsed_s'])))


def main():
    paths, identity = context()
    proof_path = OUT / 'whole-board-receiving.json'
    whole = json.loads(proof_path.read_text())
    proof_identity = whole['identity']
    need(all(proof_identity['files'][k] == v for k,v in identity['files'].items()), 'source_cut_receipt_hash_mismatch')
    need(all(proof_identity[k] == identity[k] for k in ('source_sidecars','candidate_sidecars','code_identity')),
         'source_cut_receipt_epoch_mismatch')
    cut = whole['stages']['fresh_exact_planar_source_cut']
    need(cut['ok'] and cut['result']['ok'] and cut['result']['complete'], 'exact_planar_replay_required')
    replay = cut['result']['exact_source_cut_additions_ground_and_rule_replay']
    need(replay['ok'] and replay['complete'], 'exact_unowned_copper_ground_and_rule_replay_required')
    report = dict(schema=1, scope='experimental_composed_exact_cut_saved_parent_field_receiving',
                  ok=False, complete=False, identity=identity, source_cut_receipt=str(proof_path),
                  source_cut_receipt_sha256=force._hash(proof_path), errors=[],
                  release_authority=False, inherited_debt_qualified=False)
    try:
        for label in ('source','candidate'):
            run = subprocess.run([sys.executable, str(Path(__file__)), label],
                                 capture_output=True, text=True, timeout=9.9)
            need(run.returncode == 0, 'field_worker_failed:' + label + ':' + run.stderr[-1200:])
            print(run.stdout, end='', flush=True)
        a,b = [json.loads((OUT / (label + '-field-v2.json')).read_text()) for label in ('source','candidate')]
        need(a['identity'] == b['identity'] == identity == context()[1], 'field_epoch_changed')
        need(a['ok'] and a['complete'] and b['ok'] and b['complete'], 'incomplete_field_worker')
        old = field.blocker_keys(a['report'])
        new = field.blocker_keys(b['report'])
        rows = [r for r in b['report']['interactions'] if r.get('blocking')
                and not field.blocker_keys(dict(interactions=[r])).issubset(old)]
        report.update(ok=not rows, complete=True, new_blockers=rows,
                      before_after_blockers=[a['report']['blocking_count'],b['report']['blocking_count']],
                      before_after_interactions=[a['report']['interaction_count'],b['report']['interaction_count']],
                      new_blocker_count=len(new-old), workers=['source-field-v2.json','candidate-field-v2.json'],
                      source_candidate_and_code_unchanged=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    force._write(OUT / 'field-receiving-v2.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('identity','new_blockers')}))


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] in ('source','candidate'):
        worker(sys.argv[1])
    else:
        main()
