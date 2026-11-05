"""Manufacturing withholding for actually fitted, still-provisional hardware."""
import json
from pathlib import Path


def evaluate(fitted_footprints, requirements):
    rows = []
    fitted = set(fitted_footprints)
    for requirement in requirements:
        matched = fitted & set(requirement['footprints'])
        if not matched:
            continue
        row = {'id': requirement['id'], 'matched_footprints': sorted(matched), 'ok': False}
        try:
            status = json.loads(Path(requirement['status_path']).read_text())
            missing = [gate for gate in requirement['required_gates']
                       if status.get('gates', {}).get(gate, {}).get('passed') is not True]
            row.update(release_status=status.get('release_status'), unpassed_gates=missing)
            if not missing and status.get('release_status') == 'RELEASED':
                verification = requirement['verify_candidate']()
                row['candidate_verification'] = verification
                row['ok'] = verification.get('ok') is True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row['error'] = str(exc)
        rows.append(row)
    return {'ok': all(r['ok'] for r in rows), 'requirements': rows,
            'scope': 'declared_fitted_hardware_qualification_not_routing'}
