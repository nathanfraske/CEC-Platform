"""Join only fresh same-epoch independent saved-prefix evidence."""
import json
from pathlib import Path
import sys

from output_prefix import ROOT, WORK, SOURCE, SHA, CUTS, HINT
import cec_force_current as force
import cec_field_coupling as field
import cec_force_sense_evidence as sense
import cec_source_retaining_ses_import as raw
import cec_source_literal_additions as literal


def main():
    revision = sys.argv[1]
    assert revision and len(revision) <= 32 and all(c.isalnum() or c in '-_' for c in revision)
    record = json.loads((WORK/'output-prefix-construction.json').read_text())
    candidate = Path(record['candidate']); out = WORK/'output-prefix-v1'
    folder = out/('checks-'+revision)
    names = ('reflow','seat','ground','current','craft','pairs','drc-source',
             'drc-candidate','field-source','field-candidate')
    reports = {name:json.loads((folder/(name+'.json')).read_text()) for name in names}
    epoch = dict(source=force._hash(SOURCE), candidate=force._hash(candidate),
        source_sidecars=force._sidecars(SOURCE), candidate_sidecars=force._sidecars(candidate),
        code_identity=force._code_identity())
    assert epoch['source']==SHA and epoch['candidate']==record['candidate_sha256']
    assert all(r['ok'] and r['identity']==epoch for r in reports.values())
    assert epoch['source_sidecars']==epoch['candidate_sidecars']
    for name in names:
        process=json.loads((folder/(name+'-process.json')).read_text())
        assert process['ok'] and process['returncode']==0
    before,after=[reports['field-'+name]['result']['report'] for name in ('source','candidate')]
    assert field.blocker_keys(after)<=field.blocker_keys(before)
    evidence=[json.loads((out/('sense-shards-'+revision)/name/'assembled.json').read_text())
        for name in ('source','candidate')]
    for proof,path in zip(evidence,(SOURCE,candidate)):
        assert proof['complete'] and proof['identity_stable']
        assert proof['code_before']==proof['code_after']==epoch['code_identity']
        assert proof['source_family_before']==proof['source_family_after']==force._family(path,HINT)
    comparison=sense.compare_contact_preservation(*evidence)
    assert comparison['comparison_complete'] and comparison['same_evidence']
    old,new=[literal._inventory(raw.raw_text(path))[0] for path in (SOURCE,candidate)]
    assert old.keys()-new.keys()==set(CUTS)
    assert new.keys()-old.keys()==set(record['added_track_uuids'])
    changed=[u for u in old.keys()&new.keys() if old[u][2]!=new[u][2]]
    import pcbnew
    b=pcbnew.LoadBoard(str(SOURCE))
    ground={force._uid(z) for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
    assert set(changed)<=ground
    assert abs(record['old_length_mm']-record['new_length_mm'])<1e-8
    result=dict(schema=1,status='private_full_current_prefix_received_not_released',
        source=str(SOURCE),source_sha256=SHA,candidate=str(candidate),candidate_sha256=epoch['candidate'],
        identity=epoch,independent_nonregression_received=True,
        operation='Translate one B.Cu 45-degree OUT diagonal 0.10 mm left and compensate its two horizontal legs',
        retired_track_uuids=CUTS,added_track_uuids=record['added_track_uuids'],
        changed_existing_ground_fill_uuids=sorted(changed),
        all_other_native_nodes_and_project_sidecars_literal_unchanged=True,
        width_nm=record['width_nm'],length_mm_before_after=[record['old_length_mm'],record['new_length_mm']],
        native_before_after=[reports['drc-'+v]['result']['counts'] for v in ('source','candidate')],
        craft_before_after=reports['craft']['result']['before_after'],
        field_blockers_before_after=[before['blocking_count'],after['blocking_count']],
        exact_force_sense_comparison_complete=True,exact_force_sense_evidence_preserved=True,
        clipped_legs_before_after=[r['clipped_isolation']['passed'] for r in evidence],
        current_and_ground_and_pair_nonregression_received=True,
        projected_future_C55_seat_checks_pass=True,seat_is_not_installed=True,
        seven_component_repack_saved=False,
        stages={n:dict(path=str((folder/(n+'.json')).relative_to(ROOT)),
            sha256=force._hash(folder/(n+'.json')),elapsed_s=reports[n]['elapsed_s']) for n in names},
        native_board_size_mm=[78.,87.5],new_xy_compaction=False,new_parts_installed=False,
        new_barrels=0,retired_barrels=0,current_qualified=False,physical_fit_qualified=False,
        fab_ready=False,release_authority=False)
    target=WORK/('slice-closeout-'+revision+'.json')
    assert not target.exists()
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('identity','stages')},indent=2))


if __name__=='__main__': main()
