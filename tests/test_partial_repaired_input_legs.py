"""Shared rails do not require unfinished inputs to receive a false pass."""
import copy
import pcbnew
import pytest
import cec_force_sense_evidence as evidence
import cec_received_route_evidence as received
from test_force_sense_evidence import fixture, run


def shared_native_reports(tmp_path,retained_stub=True):
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    domains=fixture(source,filtered=False,fault='missing_copper')
    board=pcbnew.LoadBoard(str(source))
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('OTHER_SENSOR')
    owner.SetValue('INA240A3DR')
    owner.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    board.Add(owner)
    for pin,net,y in [('8','RENAMED_FEED',79),('1','RENAMED_LOAD',81)]:
        pad=pcbnew.PAD(owner);pad.SetNumber(pin);pad.SetNet(board.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        pad.SetPosition(pcbnew.VECTOR2I_MM(94,y));owner.Add(pad)
    # Keep the source's actual shunt departure fixed; only its open tail is
    # completed. Changing an unrelated input's departure observation must
    # still be refused by the strict unaffected comparator.
    if retained_stub:
        stub=pcbnew.PCB_TRACK(board);stub.SetNet(board.FindNet('RENAMED_FEED'))
        stub.SetStart(pcbnew.VECTOR2I_MM(90,75));stub.SetEnd(pcbnew.VECTOR2I_MM(90,77))
        stub.SetWidth(pcbnew.FromMM(.2));stub.SetLayer(pcbnew.F_Cu);board.Add(stub)
    pcbnew.SaveBoard(str(source),board)
    before=run(source,domains);before['identity_stable']=True
    track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('RENAMED_FEED'))
    track.SetStart(pcbnew.VECTOR2I_MM(90,77 if retained_stub else 75));track.SetEnd(pcbnew.VECTOR2I_MM(90,79))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(pcbnew.F_Cu);board.Add(track)
    uid=track.m_Uuid.AsString();pcbnew.SaveBoard(str(child),board)
    after=run(child,domains);after['identity_stable']=True
    manifest=[dict(net='RENAMED_FEED',retired_track_uuids=[],added_zone_uuids=[],added_track_uuids=[uid])]
    assert before['clipped_isolation']['expected']==after['clipped_isolation']['expected']==4
    assert before['clipped_isolation']['unknown']==3
    assert after['clipped_isolation']['unknown']==2
    return before,after,manifest


def test_completed_native_input_is_received_without_laundering_same_net_unknown(tmp_path):
    before,after,manifest=shared_native_reports(tmp_path);original=copy.deepcopy((before,after))
    # The legacy whole-net API still correctly refuses an unfinished cohort.
    assert not evidence.compare_repaired_preservation(before,after,
        repair_nets=['RENAMED_FEED'],modified_nets=['RENAMED_FEED'],
        native_copper_transforms=manifest)['same_evidence']
    result=evidence.compare_repaired_preservation(before,after,
        repair_nets=['RENAMED_FEED'],modified_nets=['RENAMED_FEED'],
        native_copper_transforms=manifest,repair_legs=[('ANALOG_SENSOR','p','RENAMED_FEED')])
    assert result['comparison_complete'] and result['same_evidence'],result
    assert result['coverage_after']['clipped_isolation']['unknown']==2
    assert result['coverage_after']['clipped_isolation']['passed']==2
    assert result['repaired_nets'][0]['absolute_after_admission']['expected_legs']==[['ANALOG_SENSOR','p']]
    assert not result['release_authority'] and not result['full_kelvin_qualification']
    assert original==(before,after)


def test_source_derived_scope_keeps_unfinished_shared_cohort_strict(tmp_path):
    before,after,manifest=shared_native_reports(tmp_path)
    result=received._compare_input_repairs(before,after,
        [('ANALOG_SENSOR','p','RENAMED_FEED')],['RENAMED_FEED'],manifest)
    assert result['same_evidence'],result
    assert result['derived_input_scope']=='newly_connected_legs_only'
    assert not result['whole_cohort_admission_attempts'][0]['ok']
    assert result['coverage_after']['clipped_isolation']['unknown']==2


def complete_shared_reports(tmp_path,angle):
    """Two renamed packages, one existing input and one actual new tap."""
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    domains=fixture(source,filtered=False,fault='missing_copper')
    board=pcbnew.LoadBoard(str(source));net=board.FindNet('RENAMED_FEED')
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('OTHER_SENSOR')
    owner.SetValue('INA240A3DR');board.Add(owner)
    owner.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    for pin,name,y in [('8','RENAMED_FEED',79),('1','RENAMED_LOAD',81)]:
        pad=pcbnew.PAD(owner);pad.SetNumber(pin);pad.SetNet(board.FindNet(name))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        pad.SetPosition(pcbnew.VECTOR2I_MM(94,y));owner.Add(pad)
    for a,z in [((90,75),(90,77)),((90,77),(92,79)),((92,79),(94,79))]:
        track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(pcbnew.FromMM(.2));track.SetStart(pcbnew.VECTOR2I_MM(*a))
        track.SetEnd(pcbnew.VECTOR2I_MM(*z));board.Add(track)
    pivot=pcbnew.VECTOR2I_MM(90,80);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,turn)
    pcbnew.SaveBoard(str(source),board)
    before=run(source,domains);before['identity_stable']=True
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
    track.SetWidth(pcbnew.FromMM(.2));track.SetStart(pcbnew.VECTOR2I_MM(90,75))
    track.SetEnd(pcbnew.VECTOR2I_MM(90,79));track.Rotate(pivot,turn);board.Add(track)
    pcbnew.SaveBoard(str(child),board)
    after=run(child,domains);after['identity_stable']=True
    manifest=[dict(net='RENAMED_FEED',retired_track_uuids=[],added_zone_uuids=[],
        added_track_uuids=[track.m_Uuid.AsString()])]
    return before,after,manifest


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_new_native_tap_refreshes_existing_qualified_peer_only_after_whole_cohort_proof(tmp_path,angle):
    before,after,manifest=complete_shared_reports(tmp_path,angle)
    result=received._compare_input_repairs(before,after,
        [('ANALOG_SENSOR','p','RENAMED_FEED')],['RENAMED_FEED'],manifest)
    assert result['comparison_complete'] and result['same_evidence'],result
    assert result['derived_input_scope']=='absolutely_verified_whole_cohorts'
    assert result['whole_cohort_admission_attempts'][0]['checked']==2
    assert result['coverage_before']['clipped_isolation']['passed']==2
    assert result['coverage_after']['clipped_isolation']['passed']==3
    assert result['coverage_after']['clipped_isolation']['unknown']==1
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('fault',['cut','guard','departure','terminal','counts','unrelated_unknown'])
def test_refresh_never_masks_a_changed_or_unqualified_peer_or_unrelated_input(tmp_path,fault):
    before,after,manifest=complete_shared_reports(tmp_path,0)
    peer=next(r for r in after['clipped_isolation']['details']
        if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')
    if fault=='cut':peer['native']['ok']=False
    elif fault=='guard':peer['native']['numerical_guard_nm']+=1
    elif fault=='departure':
        next(r for r in after['inner_departure']['details']
            if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')['ok']=False
    elif fault=='terminal':peer['native']['source']['uuid']='wrong-physical-shunt'
    elif fault=='counts':manifest[0]['added_track_uuids']=[]
    else:
        next(r for r in after['clipped_isolation']['details']
            if r['input_ref']=='OTHER_SENSOR' and r['leg']=='n')['native']['numerical_guard_nm']+=1
    result=received._compare_input_repairs(before,after,
        [('ANALOG_SENSOR','p','RENAMED_FEED')],['RENAMED_FEED'],manifest)
    assert not result['same_evidence'],result
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('fault',[None,'unreceived_uuid','wrong_source','heading','new_issue',
    'unknown_cut','new_guard','old_contact_changed','input_now_reached'])
def test_peer_observation_requires_same_native_shunt_and_absolutely_proved_added_departure(tmp_path,fault):
    before,after,manifest=shared_native_reports(tmp_path,retained_stub=False)
    peer=next(r for r in after['inner_departure']['details']
        if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')
    witness=peer['native']['non_sense_departures'][0]
    if fault=='unreceived_uuid':manifest[0]['added_track_uuids']=['not-received']
    elif fault=='wrong_source':peer['source_pad']['uuid']='different-shunt'
    elif fault=='heading':witness['transverse_error_nm']+=1
    elif fault=='new_issue':peer['native']['issues'].append({'reason':'unsafe'})
    elif fault=='unknown_cut':
        next(r for r in after['clipped_isolation']['details']
            if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')['native']['numerical_guard_nm']+=1
    elif fault=='new_guard':peer['inner_min_mm']+=.01
    elif fault=='old_contact_changed':
        next(r for r in before['inner_departure']['details']
            if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')['native']['contact_count']=1
    elif fault=='input_now_reached':peer['native']['unreachable_input_pad_uuids']=[]
    result=evidence.compare_repaired_preservation(before,after,
        repair_nets=['RENAMED_FEED'],modified_nets=['RENAMED_FEED'],
        native_copper_transforms=manifest,repair_legs=[('ANALOG_SENSOR','p','RENAMED_FEED')])
    assert result['same_evidence']==(fault is None),result
    if fault is None:
        assert result['unreached_input_peer_departure_observations'][0]['still_unconnected']
        assert not result['unreached_input_peer_departure_observations'][0]['input_qualified']
        assert result['coverage_after']['clipped_isolation']['unknown']==2
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('fault',['unknown_selected','unlisted','duplicate','empty','wrong_net',
    'unknown_guard','unknown_geometry','unselected_upgrade','selected_guard','departure','missing_demand'])
def test_partial_scope_never_waives_unknown_or_changed_physical_evidence(tmp_path,fault):
    before,after,manifest=shared_native_reports(tmp_path)
    selected=[('ANALOG_SENSOR','p','RENAMED_FEED')]
    unknown=next(r for r in after['clipped_isolation']['details']
        if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')
    repaired=next(r for r in after['clipped_isolation']['details']
        if r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')
    if fault=='unknown_selected':selected=[('OTHER_SENSOR','p','RENAMED_FEED')]
    elif fault=='unlisted':selected=[('MADE_UP','p','RENAMED_FEED')]
    elif fault=='duplicate':selected*=2
    elif fault=='empty':selected=[]
    elif fault=='wrong_net':selected=[('ANALOG_SENSOR','p','RENAMED_LOAD')]
    elif fault=='unknown_guard':unknown['native']['numerical_guard_nm']+=1
    elif fault=='unknown_geometry':unknown['native']['baseline_geometry']={'made_up':True}
    elif fault=='unselected_upgrade':
        unknown.update(ok=True,status='pass');unknown['native'].update(ok=True,complete=True)
        packet=after['clipped_isolation']
        after['clipped_isolation']=evidence._coverage(packet['details'],packet['expected'],
            unresolved_inputs=packet['unresolved_inputs'])
    elif fault=='selected_guard':repaired['native']['numerical_guard_nm']+=1
    elif fault=='departure':
        next(r for r in after['inner_departure']['details']
            if r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')['ok']=False
    else:
        after['same_net_connectivity']['details']=[r for r in after['same_net_connectivity']['details']
            if not (r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')]
    result=evidence.compare_repaired_preservation(before,after,repair_nets=['RENAMED_FEED'],
        modified_nets=['RENAMED_FEED'],native_copper_transforms=manifest,repair_legs=selected)
    assert not result['same_evidence'],result
    assert not result['release_authority'] and not result['full_kelvin_qualification']
