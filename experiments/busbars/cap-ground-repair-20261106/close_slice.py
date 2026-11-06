"""Join independently generated, exact-source nonregression evidence."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from construct import ROOT, WORK, SOURCE, SHA, VIA, HINT, force
import cec_field_coupling as field
import cec_force_sense_evidence as sense
import cec_source_retaining_ses_import as raw
import cec_source_literal_additions as literal


def main():
    record = json.loads((WORK / 'construction.json').read_text())
    candidate = Path(record['candidate'])
    assert force._hash(SOURCE) == SHA
    assert force._hash(candidate) == record['candidate_sha256']
    folder = WORK / 'checks-final'
    names = ('source-plan', 'barrel', 'ground', 'current', 'craft', 'pairs',
             'drc-source', 'drc-candidate', 'field-source', 'field-candidate')
    reports = {name: json.loads((folder / (name + '.json')).read_text()) for name in names}
    epoch = dict(source=force._hash(SOURCE), candidate=force._hash(candidate),
                 source_sidecars=force._sidecars(SOURCE),
                 candidate_sidecars=force._sidecars(candidate),
                 code_identity=force._code_identity())
    assert all(r['ok'] and r['identity'] == epoch for r in reports.values())
    for name in names:
        process = json.loads((folder / (name + '-process.json')).read_text())
        assert process['ok'] and process['returncode'] == 0
    before = reports['field-source']['result']['report']
    after = reports['field-candidate']['result']['report']
    assert field.blocker_keys(after) <= field.blocker_keys(before)
    evidence = [json.loads((WORK / 'sense-shards' / label / 'assembled.json').read_text())
                for label in ('source', 'candidate')]
    for proof, path in zip(evidence, (SOURCE, candidate)):
        assert proof['complete'] and proof['identity_stable']
        assert proof['code_before'] == proof['code_after'] == epoch['code_identity']
        assert proof['source_family_before'] == proof['source_family_after'] == force._family(path, HINT)
    comparison = sense.compare_contact_preservation(*evidence)
    assert comparison['comparison_complete'] and comparison['same_evidence']
    old = literal._inventory(raw.raw_text(SOURCE))[0]
    new = literal._inventory(raw.raw_text(candidate))[0]
    assert old.keys() == new.keys()
    changed = [uid for uid in old if old[uid][2] != new[uid][2]]
    # This particular saved correction needs no fill changes, new material,
    # track edits, moved component or outline changes.
    assert changed == [VIA]
    assert force._sidecars(SOURCE) == force._sidecars(candidate)
    test_reports = [WORK / 'regression-root.xml',
                    *sorted((WORK / 'rigid-regression').glob('case-*.xml'))]
    assert len(test_reports) == 35
    test_cases = []
    for report in test_reports:
        cases = list(ET.parse(report).getroot().iter('testcase'))
        assert cases and all(not any(c.tag in ('error', 'failure', 'skipped') for c in t) for t in cases)
        test_cases.extend((t.get('classname'), t.get('name')) for t in cases)
    assert len(test_cases) == 172 and len(set(test_cases)) == 145
    result = dict(
        schema=1, status='private_source_ground_via_repair_received_not_released',
        source=str(SOURCE), source_sha256=SHA, candidate=str(candidate),
        candidate_sha256=force._hash(candidate), identity=epoch,
        independent_nonregression_received=True,
        repair='Move the one existing partial-overlap capacitor Ground via 0.10 mm into its actual SMD pad',
        via_uuid=VIA, changed_native_node_uuids=changed,
        source_at_nm=record['source_at_nm'], target_at_nm=record['target_at_nm'],
        same_via_identity_dimensions_process_lock_and_layer_stack=True,
        all_other_opaque_native_nodes_and_sidecars_literal_unchanged=True,
        exact_saved_ground_refill_received=True,
        native_before_after=[reports['drc-' + v]['result']['counts'] for v in ('source', 'candidate')],
        craft_before_after=reports['craft']['result']['before_after'],
        field_blockers_before_after=[before['blocking_count'], after['blocking_count']],
        exact_force_sense_comparison_complete=True, exact_force_sense_evidence_preserved=True,
        clipped_legs_before_after=[r['clipped_isolation']['passed'] for r in evidence],
        current_and_ground_and_pair_nonregression_received=True,
        regression_unique_cases_passed=len(set(test_cases)),
        regression_passed_executions=len(test_cases),
        regression_reports={str(p.relative_to(ROOT)): force._hash(p) for p in test_reports},
        stages={n: dict(path=str((folder / (n + '.json')).relative_to(ROOT)),
                        sha256=force._hash(folder / (n + '.json')),
                        elapsed_s=reports[n]['elapsed_s']) for n in names},
        native_board_size_mm=[78., 87.5], new_xy_compaction=False,
        new_parts_installed=False, new_barrels=0, retired_barrels=0,
        current_qualified=False, physical_fit_qualified=False,
        fab_ready=False, release_authority=False)
    (WORK / 'slice-closeout.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('identity', 'stages', 'regression_reports')}, indent=2))


if __name__ == '__main__':
    main()
