"""Bounded exact-finalist diagnostics; never placement or release authority."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile


def compare_keys(fields, baseline, candidate):
    """Explain the existing lexicographic decision, not a new scoring policy."""
    fields, baseline, candidate = tuple(fields), tuple(baseline), tuple(candidate)
    if (len(fields) != len(baseline) or len(fields) != len(candidate)
            or len(set(fields)) != len(fields)
            or not all(isinstance(v, (int, float)) and math.isfinite(v)
                       for v in baseline + candidate)):
        raise ValueError('ranking fields and finite key values must align')
    changes = [dict(index=i, field=name, baseline=before, candidate=after,
                    direction='improved' if after < before else 'worsened')
               for i, (name, before, after) in enumerate(zip(fields, baseline, candidate))
               if before != after]
    return dict(schema=1, ordering='lexicographic-lower-is-better',
                fields=list(fields), baseline_key=list(baseline),
                candidate_key=list(candidate),
                relation=('improved' if candidate < baseline else
                          'worsened' if candidate > baseline else 'equal'),
                decisive_change=changes[0] if changes else None, changes=changes)


def identity(path):
    path = Path(path)
    try:
        return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    except OSError as exc:
        return dict(path=str(path), sha256=None, error=str(exc))


def retain(baseline, candidate, receipt, evidence, root, *, limit=2,
           minimum_free_gib=16, max_bytes=64 * 1024**2):
    """Keep measured files before temporary cleanup, within explicit budgets.

    The supplied identities were captured before analysis. Recheck both before
    and after copying. Failure to store diagnostics never promotes a candidate.
    A missing operation directory intentionally leaves only inline key evidence.
    """
    refused = dict(schema=1, retained=False, release_authority=False,
                   promotion_allowed=False)
    if root is None:
        return dict(refused, reason='no_durable_operation_directory')
    root = Path(root)
    target = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        if len(list(root.glob('finalist-*'))) >= max(0, int(limit)):
            return dict(refused, reason='diagnostic_artifact_budget_exhausted')
        sources = []
        for role, expected in (('baseline', baseline), ('candidate', candidate)):
            path = Path(expected['path'])
            if not expected.get('sha256') or identity(path)['sha256'] != expected['sha256']:
                return dict(refused, reason='measured_board_unavailable_or_changed', role=role)
            for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru',
                           '.pourfirst-state.json', '.pourplan.json', '.cellreport.json'):
                source = path.with_suffix(suffix)
                if source.is_file():
                    sources.append((role, source, identity(source)['sha256']))
        payload = json.dumps(dict(receipt=receipt, candidate_evidence=evidence),
                             indent=2, allow_nan=False).encode('utf-8')
        size = len(payload) + sum(path.stat().st_size for _, path, _ in sources)
        if size > max_bytes:
            return dict(refused, reason='diagnostic_byte_budget', bytes=size)
        if shutil.disk_usage(root).free - size < minimum_free_gib * 1024**3:
            return dict(refused, reason='diagnostic_storage_floor', bytes=size)
        target = Path(tempfile.mkdtemp(prefix='finalist-', dir=root))
        records = []
        for role, source, digest in sources:
            destination = target / role / source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(source, destination)
            if (identity(source)['sha256'] != digest
                    or identity(destination)['sha256'] != digest):
                raise OSError('diagnostic file changed during capture')
            records.append(dict(role=role, source=str(source), path=str(destination),
                                sha256=digest))
        for role, expected in (('baseline', baseline), ('candidate', candidate)):
            if identity(expected['path'])['sha256'] != expected['sha256']:
                raise OSError(role + ' board changed during capture')
        (target / 'evidence.json').write_bytes(payload)
        report = dict(refused, retained=True, kind='exact-finalist-diagnostic',
                      directory=str(target), files=records,
                      evidence=str(target / 'evidence.json'), bytes=size)
        (target / 'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    except (OSError, ValueError, TypeError) as exc:
        # Retain any incomplete private capture for forensics; never call it
        # verified and never let diagnostic I/O change the selection decision.
        return dict(refused, reason='diagnostic_capture_failed', error=str(exc),
                    directory=str(target) if target else None)
