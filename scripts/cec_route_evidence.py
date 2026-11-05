"""Content-bound reuse of completed placement-route measurements.

Certificates transport evidence, never grant board admission. Any dependency
change or incomplete certificate falls back to an ordinary fresh measurement.
There is no persistent cache, geometry rounding, or product-specific rule.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.kicad_prl',
            '.pourplan.json', '.railreport.json', '.cellreport.json',
            '.pourfirst-state.json', '.authored-prefix.json', '.power-prefix.json',
            '.priority-replacements.json', '.route-lineage.json')
ENVELOPE = 'baseline_certificate'
TRANSPORT_FIELDS = frozenset((ENVELOPE, 'operation_evidence', 'measurement_process',
                              'recovered_from', 'baseline_reuse'))
# These are execution observations, not inputs to a route solve. Other CEC
# variables, including solver effort and recipe overrides, remain binding.
OBSERVATION_ENV = frozenset(('CEC_OPERATION_PROGRESS', 'CEC_OPERATION_STACKS',
    'CEC_OPERATION_OWNER_PID', 'CEC_JOB_DEADLINE_EPOCH', 'CEC_OPERATION_DEADLINE_EPOCH'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def files(paths):
    """Missing optional dependencies are explicit, so additions invalidate."""
    result = {}
    for label, path in sorted(paths.items()):
        path = Path(path)
        result[str(label)] = (hashlib.sha256(path.read_bytes()).hexdigest()
                              if path.is_file() else None)
    return result


def artifact_paths(board):
    board = Path(board).resolve()
    result = {suffix: board.with_suffix(suffix) for suffix in SUFFIXES}
    skeleton = board.with_suffix('.pourfirst-skeleton.kicad_pcb')
    result.update({'skeleton'+suffix: skeleton.with_suffix(suffix) for suffix in SUFFIXES})
    state = board.with_suffix('.pourfirst-state.json')
    if state.is_file():
        data = json.loads(state.read_text())
        if data.get('skeleton'):
            actual = Path(data['skeleton'])
            if not actual.is_absolute():
                actual = state.parent/actual
            result.update({'referenced-skeleton'+suffix: actual.with_suffix(suffix)
                           for suffix in SUFFIXES})
    return result


def referenced_files(value):
    """Capture explicit file-valued recipe inputs as well as their names."""
    result = {}
    def visit(item):
        if isinstance(item, dict):
            for child in item.values(): visit(child)
        elif isinstance(item, (tuple, list)):
            for child in item: visit(child)
        elif isinstance(item, str) and item and len(item) < 4096:
            try:
                path = Path(item)
                if not path.is_absolute(): path = ROOT/path
                if path.is_file(): result[str(path.resolve())] = path
            except (OSError, ValueError):
                pass
    visit(value)
    return files(result)


def context(board, policy, *, source_paths=(), environ=None):
    import pcbnew
    environment = dict(os.environ if environ is None else environ)
    environment = {key: value for key, value in environment.items()
                   if ((key.startswith('CEC_') and key not in OBSERVATION_ENV)
                       or key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
                                  'CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES',
                                  'PYTHONHASHSEED','PYTHONPATH'))}
    runtime = {'python':sys.version, 'kicad':pcbnew.GetBuildVersion()}
    for package in ('numpy','scipy','torch'):
        try: runtime[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: runtime[package] = None
    sections = {
        'artifact': files(artifact_paths(board)),
        'sources': files({str(Path(path).resolve()):path for path in source_paths
                          if Path(path).resolve() != Path(board).resolve()}),
        'policy': policy,
        'referenced_inputs': referenced_files((policy, environment)),
        'environment': environment,
        'engine': files({str(path.relative_to(ROOT)):path
                         for path in sorted((ROOT/'scripts').glob('*.py'))}),
        'runtime': runtime,
    }
    # Hash environment/config values rather than disclosing arbitrary env
    # contents in a public evidence report.
    hashes = {key:digest(value) for key,value in sections.items()}
    return {'sha256':digest(hashes), 'sections':hashes}


def baseline_context(cfg, board, *, allow_authored_prefix=False,
                     allow_unbound_power_authority=False):
    if not getattr(cfg, 'sch', None) or not Path(board).is_file():
        return None  # No trustworthy source authority; reuse is unavailable.
    params = dict(cfg.params or {})
    # Excluding an already-rejected future move does not change the measured
    # incumbent. All other configuration values remain conservatively bound.
    params.pop('placement_route_excluded_move_signatures', None)
    params.pop('placement_probe_history', None)
    config = {key:getattr(cfg,key,None) for key in
              ('board','board_key','profile','pins','dir','sch','net','pcb','bom_csv')}
    config['net'] = config.get('net') or None
    return context(board, {'config':config,'params':params,
        'allow_authored_prefix':bool(allow_authored_prefix),
        'allow_unbound_power_authority':bool(allow_unbound_power_authority),
        'purpose':'placement-route-baseline'}, source_paths=source_files(cfg,board))


def source_files(cfg, board):
    """Declared hierarchy, including nested sheets outside the root folder."""
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    # Scheduling receipts change which future proposal is sampled, not the
    # incumbent's physical route measurement. Do not self-invalidate it when
    # recording a completed batch of unsuccessful probes.
    paths = {path for path in pipeline._source_files(cfg,board)
             if not path.name.endswith('.placement-search.json')}
    pending, visited = [Path(cfg.sch).resolve()], set()
    while pending:
        path = pending.pop()
        if path in visited: continue
        visited.add(path)
        # Missing declared children cannot produce a reuse certificate.
        tree = synth.parse_sexpr(path.read_text(encoding='utf-8'))
        paths.add(path)
        for sheet in synth._kids(tree, 'sheet'):
            for prop in synth._kids(sheet, 'property'):
                if len(prop) >= 3 and prop[1] == 'Sheetfile':
                    pending.append((path.parent/prop[2]).resolve())
    return sorted(paths)


def clean(evidence):
    return {key:copy.deepcopy(value) for key,value in evidence.items()
            if key not in TRANSPORT_FIELDS}


def seal(evidence, authority):
    result = clean(evidence)
    if not authority or not result or result.get('error'):
        return result
    result[ENVELOPE] = {'schema':1, 'purpose':'placement-route-baseline',
        'complete':True, 'context':copy.deepcopy(authority), 'evidence_sha256':digest(result)}
    return result


def verify(evidence, authority):
    evidence = evidence if isinstance(evidence,dict) else {}
    certificate = evidence.get(ENVELOPE)
    certificate = certificate if isinstance(certificate,dict) else {}
    reason = 'matched'
    changed = []
    if not authority:
        reason = 'context_unavailable'
    elif (certificate.get('schema') != 1 or certificate.get('complete') is not True
          or certificate.get('purpose') != 'placement-route-baseline'):
        reason = 'certificate_missing_or_incomplete'
    elif (not clean(evidence) or evidence.get('error')
          or certificate.get('evidence_sha256') != digest(clean(evidence))):
        reason = 'evidence_changed_or_failed'
    elif certificate.get('context') != authority:
        reason = 'context_changed'
        old = (certificate.get('context') or {}).get('sections') or {}
        changed = sorted(key for key,value in authority['sections'].items()
                         if old.get(key) != value)
    return {'used':reason=='matched', 'reason':reason, 'changed_sections':changed,
            'context_sha256':(authority or {}).get('sha256')}
