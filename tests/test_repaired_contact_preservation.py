"""Actual repaired input evidence is distinct from preserved unknown debt."""
import copy
import pytest
import cec_force_sense_evidence as evidence
from test_contour_contact_preservation import native_reports


def packets(tmp_path):
    before,after,manifest=native_reports(tmp_path)
    net='RENAMED_FEED'
    for category in ('same_net_connectivity','inner_departure','clipped_isolation'):
        packet=before[category]
        for row in packet['details']:
            if row['net']!=net:continue
            row.update(ok=None,status='unknown')
            if category=='clipped_isolation':row['native'].update(ok=None,complete=False,baseline_connected=False)
            if category=='same_net_connectivity':row.update(ok=False,status='disconnected')
        before[category]=evidence._coverage(packet['details'],packet['expected'],unresolved_inputs=packet['unresolved_inputs'])
    return before,after,manifest


def test_positive_after_cohort_can_repair_unknown_before_without_global_pass(tmp_path):
    before,after,manifest=packets(tmp_path);original=copy.deepcopy((before,after))
    result=evidence.compare_repaired_preservation(before,after,repair_nets=['RENAMED_FEED'],
        modified_nets=['RENAMED_FEED'],native_copper_transforms=manifest)
    assert result['comparison_complete'] and result['same_evidence'],result
    assert result['coverage_after']['clipped_isolation']['passed']==2
    assert result['coverage_before']['clipped_isolation']['unknown']==1
    assert not result['release_authority'] and not result['full_kelvin_qualification']
    assert original==(before,after)
    assert not evidence.compare_contour_preservation(before,after,modified_nets=['RENAMED_FEED'],
        native_copper_transforms=manifest)['same_evidence']


@pytest.mark.parametrize('fault',['unlisted','counter','guard','new_model','source','policy','departure',
    'incomplete','input_open','foreign_observation','unaffected','wrong_counts','no_repaired_demand'])
def test_repair_cannot_launder_missing_changed_or_unaffected_evidence(tmp_path,fault):
    before,after,manifest=packets(tmp_path);selected=['RENAMED_FEED']
    row=next(r for r in after['clipped_isolation']['details'] if r['net']=='RENAMED_FEED')
    if fault=='unlisted':selected=['RENAMED_LOAD']
    elif fault=='counter':after['clipped_isolation']['passed']-=1
    elif fault=='guard':row['native']['numerical_guard_nm']+=1
    elif fault=='new_model':row['native']['extra_permission']=True
    elif fault=='source':row['native']['source']['uuid']='not-source'
    elif fault=='policy':after['geometry_policy']['inner_min_mm']+=.01
    elif fault=='departure':
        next(r for r in after['inner_departure']['details'] if r['net']=='RENAMED_FEED')['inner_min_mm']+=.01
    elif fault=='incomplete':row['native']['complete']=False
    elif fault=='input_open':next(r for r in after['same_net_connectivity']['details'] if r['net']=='RENAMED_FEED')['ok']=False
    elif fault=='foreign_observation':
        r=next(r for r in after['shunt_pad_omitted']['details'] if r['net']=='RENAMED_FEED')
        r['reached_authority']=[dict(r['authority_excluding_cut'][0],uuid='foreign')]
        after['shunt_pad_omitted']['reached_authority_legs']=1
    elif fault=='unaffected':next(r for r in after['inner_departure']['details'] if r['net']=='RENAMED_LOAD')['inner_min_mm']+=.01
    elif fault=='wrong_counts':manifest[0]['retired_track_uuids'].append('made-up-count')
    else:before['same_net_connectivity']=copy.deepcopy(after['same_net_connectivity'])
    result=evidence.compare_repaired_preservation(before,after,repair_nets=selected,
        modified_nets=['RENAMED_FEED'],native_copper_transforms=manifest)
    assert not result['same_evidence'],result
    assert not result['release_authority']
