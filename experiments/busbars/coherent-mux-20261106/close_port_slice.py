"""Join independent source-bound evidence without granting fabrication release."""
import json
from pathlib import Path
from repair_port import ROOT,WORK,SOURCE,SOURCE_SHA,force
import cec_field_coupling as field
import cec_force_sense_evidence as sense
import cec_source_retaining_ses_import as raw
import cec_source_literal_additions as literal

OUT=WORK/'port-repaired-v1'


def main():
    record=json.loads((OUT/'construction.json').read_text())
    candidate=Path(record['candidate'])
    assert force._hash(SOURCE)==SOURCE_SHA and force._hash(candidate)==record['candidate_sha256']
    names=('barrel','ground','current','craft','pairs','drc-source','drc-candidate','field-source','field-candidate')
    reports={name:json.loads((OUT/(name+'.json')).read_text())for name in names}
    epoch=reports['barrel']['identity']
    assert all(r['ok']and r['identity']==epoch for r in reports.values())
    assert epoch==dict(source=force._hash(SOURCE),candidate=force._hash(candidate),
        source_sidecars=force._sidecars(SOURCE),candidate_sidecars=force._sidecars(candidate),
        code_identity=force._code_identity())
    before=reports['field-source']['result']['report'];after=reports['field-candidate']['result']['report']
    assert field.blocker_keys(after)<=field.blocker_keys(before),'new_field_blocker'
    evidence=[json.loads((OUT/'sense-shards'/label/'assembled.json').read_text())for label in('source','candidate')]
    for proof,path in zip(evidence,(SOURCE,candidate)):
        assert proof['complete']and proof['identity_stable']
        assert proof['code_before']==proof['code_after']==force._code_identity()
        assert proof['source_family_before']==proof['source_family_after']==force._family(path,'atx-24pin-rev3')
    comparison=sense.compare_contact_preservation(*evidence)
    assert comparison['comparison_complete']and comparison['same_evidence']
    old=literal._inventory(raw.raw_text(SOURCE))[0];new=literal._inventory(raw.raw_text(candidate))[0]
    retired=set(record['retired_track_uuids'])|{record['source_via_uuid']}
    assert old.keys()-new.keys()==retired
    assert new.keys()-old.keys()==set(record['added_native_uuids'])
    # Literal opaque preservation is stronger than a moved-body bbox screen.
    changed=[]
    for uid in old.keys()&new.keys():
        if old[uid][2]!=new[uid][2]:
            assert literal.kind(old[uid][2])=='zone','unowned_source_node_changed'
            changed.append(uid)
    assert force._sidecars(SOURCE)==force._sidecars(candidate)
    result=dict(schema=1,status='private_corrective_port_nonregression_received_not_released',
        source=str(SOURCE),source_sha256=SOURCE_SHA,candidate=str(candidate),
        candidate_sha256=force._hash(candidate),identity=epoch,
        independent_nonregression_received=True,
        repair='Replace one partial SMD-pad-overlapping ordinary signal via with a separate factory-size via and guarded 45-degree dogbone',
        same_via_diameter_drill_and_layer_stack=True,
        all_footprints_outlines_and_non_ground_source_nodes_literal_preserved=True,
        exact_saved_ground_refill_received=True,changed_ground_fill_uuids=sorted(changed),
        native_before_after=[reports['drc-'+v]['result']['counts']for v in('source','candidate')],
        craft_before_after=reports['craft']['result']['before_after'],
        field_blockers_before_after=[before['blocking_count'],after['blocking_count']],
        exact_force_sense_comparison_complete=True,exact_force_sense_evidence_preserved=True,
        clipped_legs_before_after=[r['clipped_isolation']['passed']for r in evidence],
        current_and_ground_and_pair_nonregression_received=True,
        stages={n:dict(path=str((OUT/(n+'.json')).relative_to(ROOT)),sha256=force._hash(OUT/(n+'.json')),
            elapsed_s=reports[n]['elapsed_s'])for n in names},
        native_board_size_mm=[78.,87.5],new_xy_compaction=False,new_parts_installed=False,
        current_qualified=False,physical_fit_qualified=False,fab_ready=False,release_authority=False)
    (OUT/'slice-closeout.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k not in('identity','stages')},indent=2))


if __name__=='__main__':main()
