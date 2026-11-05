"""Bounded two-call saved-request replay; never run a full pipeline wave.

Run only after implementation edits stop: a live code edit must invalidate
the invocation's reuse. --inspect-only verifies the historical request and
captures dependencies without launching native work or writing an artifact.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cec_full_pipeline as pipeline
import cec_fiducial_reuse as reuse
import cec_route_evidence
import cec_synth_pipeline as synth


def request(directory):
    operation = json.loads((directory / 'operation.json').read_text())
    command = list(operation['command'])
    for flag in ('--params-file', '--config-file', '--report'):
        command[command.index(flag) + 1] = '<operation-local-file>'
    return {'command': command,
            'requested_timeout_s': operation['requested_timeout_s'],
            'params': json.loads((directory / 'params.json').read_text()),
            'config': json.loads((directory / 'config.json').read_text())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', required=True, type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    source = args.source_run.resolve() / '02-placement' / 'board.kicad_pcb'
    operations = sorted(source.parent.glob('operation-fiducial-repair-*'),
        key=lambda directory: json.loads((directory / 'operation.json').read_text())
        .get('last_progress', {}).get('timestamp', 0))
    if len(operations) != 2:
        raise ValueError('exactly two saved fiducial operations required')
    requests = [request(directory) for directory in operations]
    if requests[0] != requests[1]:
        raise ValueError('saved effective requests differ')
    reports = [json.loads((directory / 'report.json').read_text()) for directory in operations]
    receipts = [json.loads((directory / 'operation.json').read_text()) for directory in operations]
    if reports[0] != reports[1]:
        raise ValueError('saved fiducial reports differ')
    if not all(reuse._successful_noop(dict(report, process_isolated=True,
            operation_evidence=receipt)) for report, receipt in zip(reports, receipts)):
        raise ValueError('saved calls were not successful completed no-ops')
    checkpoint = json.loads((source.parent / 'checkpoints' / 'slot-0' /
                             'board.placement-checkpoint.json').read_text())
    changed_sources = [row['path'] for row in checkpoint['sources']
        if not Path(row['path']).is_file() or pipeline.sha256_file(row['path']) != row['sha256']]
    changed_artifacts = [row['name'] for row in checkpoint['artifacts']
        if not (source.parent / row['name']).is_file()
        or pipeline.sha256_file(source.parent / row['name']) != row['sha256']]
    if changed_sources or changed_artifacts:
        raise ValueError('saved source/authority changed: ' + repr(
            {'sources': changed_sources, 'artifacts': changed_artifacts}))
    effective = requests[0]
    board_name = effective['command'][effective['command'].index('--board-name') + 1]
    cfg = synth.Config.load(board_name)
    cfg.params = effective['params']
    for key, value in effective['config'].items():
        setattr(cfg, key, value)
    reconsider_all = '--reconsider-all' in effective['command']
    initial_source = reuse.capture(cfg, source, reconsider_all=reconsider_all)
    evidence = {'source': str(source), 'saved_effective_requests_identical': True,
        'saved_request_sha256': pipeline.digest_value(effective),
        'saved_reports_identical': True,
        'historical_elapsed_s': [receipt['elapsed_s'] for receipt in receipts],
        'checkpoint_source_count': len(checkpoint['sources']),
        'checkpoint_artifact_count': len(checkpoint['artifacts']),
        'source_context': initial_source, 'calls': []}
    if args.inspect_only:
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return
    if args.out_dir is None:
        parser.error('--out-dir is required for a native replay')
    work = args.out_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    board = work / source.name
    for path in set(cec_route_evidence.artifact_paths(source).values()) | {
            source.with_suffix(suffix) for suffix in reuse.EXTRA_SIDECARS}:
        if path.is_file() and path.parent == source.parent:
            shutil.copy2(path, work / path.name)
    if pipeline.sha256_file(board) != initial_source['board_sha256']:
        raise ValueError('native replay copy differs')
    # Preserve the saved operation options but cap this disposable experiment.
    os.environ['CEC_JOB_DEADLINE_EPOCH'] = str(min(time.time() + 120,
        float(os.environ.get('CEC_JOB_DEADLINE_EPOCH', time.time() + 120))))
    cache = reuse.SameRunNoopReuse()
    initial_work = reuse.capture(cfg, board, reconsider_all=reconsider_all)
    try:
        for index in range(2):
            if reuse.capture(cfg, source, reconsider_all=reconsider_all) != initial_source:
                raise ValueError('source/authority changed; do not launch another operation')
            started = time.monotonic()
            result = pipeline._transactional_fiducial_edge_repair(
                cfg, board, reconsider_all=reconsider_all, reuse=cache)
            evidence['calls'].append({'wall_s': round(time.monotonic() - started, 6),
                                      'result': result})
            pipeline.atomic_json(work / ('call-%d.json' % (index + 1)), result)
            if reuse.capture(cfg, board, reconsider_all=reconsider_all) != initial_work:
                raise ValueError('working dependencies changed; no repeat permitted')
            if index == 0 and not result['fiducial_reuse'].get('eligible'):
                raise ValueError('first operation cannot seed a successful stable no-op')
            if index == 1 and not result['fiducial_reuse'].get('used'):
                raise ValueError('second operation did not reuse')
        evidence['source_unchanged'] = (
            reuse.capture(cfg, source, reconsider_all=reconsider_all) == initial_source)
        evidence['working_dependencies_unchanged'] = (
            reuse.capture(cfg, board, reconsider_all=reconsider_all) == initial_work)
        evidence['native_worker_count'] = len(list(work.glob('operation-fiducial-repair-*')))
        evidence['ok'] = (evidence['source_unchanged']
                          and evidence['working_dependencies_unchanged']
                          and evidence['native_worker_count'] == 1)
    except Exception as exc:
        evidence.update(ok=False, error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        pipeline.atomic_json(work / 'replay.json', evidence)
    print(json.dumps({'report': str(work / 'replay.json'), 'ok': evidence['ok'],
        'first_call_s': evidence['calls'][0]['wall_s'],
        'second_call_s': evidence['calls'][1]['wall_s'],
        'native_worker_count': evidence['native_worker_count']}, indent=2))


if __name__ == '__main__':
    main()
