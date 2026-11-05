"""Real native moved-input evidence and failing shared-peer preservation."""
import copy
import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_macro_measurement_evidence as received
from cec_native_items import discard_items
from test_force_sense_evidence import fixture,run


def native_pair(tmp_path,angle=0):
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    domains=fixture(source,filtered=False,fault='missing_copper')
    board=pcbnew.LoadBoard(str(source))
    # Both IC inputs start open; an existing second IC has a genuinely bad
    # diagonal pickup. Terminal authority comes from the established fixture,
    # not an invented ampacity or guessed current budget.
    discard_items(board,[t for t in board.GetTracks()
        if t.GetNetname()=='RENAMED_LOAD' and t.GetWidth()==200000])
    peer=pcbnew.FOOTPRINT(board);peer.SetReference('OTHER_SENSOR');peer.SetValue('INA240A3DR')
    peer.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'));board.Add(peer)
    for pin,net,y in [('8','RENAMED_FEED',79),('1','RENAMED_LOAD',81)]:
        pad=pcbnew.PAD(peer);pad.SetNumber(pin);pad.SetNet(board.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        pad.SetPosition(pcbnew.VECTOR2I_MM(94,y));peer.Add(pad)
    def trace(a,b):
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('RENAMED_FEED'))
        track.SetLayer(pcbnew.F_Cu);track.SetWidth(200000)
        track.SetStart(pcbnew.VECTOR2I_MM(*a));track.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(track);return track
    trace((90,75),(92,77));trace((92,77),(94,79))
    pivot=pcbnew.VECTOR2I_MM(90,80);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,turn)
    pcbnew.SaveBoard(str(source),board)
    before=run(source,domains);before['identity_stable']=True
    owner=board.FindFootprintByReference('ANALOG_SENSOR')
    delta=pcbnew.VECTOR2I_MM(*{0:(1,0),90:(0,-1),180:(-1,0),270:(0,1)}[angle])
    owner.SetPosition(owner.GetPosition()+delta)
    incoming=[]
    for a,b in [((89.5,75),(89.5,78)),((89.5,78),(90.5,79)),((90.5,79),(91,79))]:
        track=trace(a,b);track.Rotate(pivot,turn);incoming.append(force._uid(track))
    pcbnew.SaveBoard(str(child),board)
    after=run(child,domains);after['identity_stable']=True
    parent,actual=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    proof=dict(ok=True,complete=True,source_candidate_families_and_code_unchanged=True,
        moved_refs=['ANALOG_SENSOR'],added_native_uuids=incoming)
    manifest=sense.native_copper_transform_inventory(parent,actual,
        modified_nets=['RENAMED_FEED','RENAMED_LOAD'])
    return parent,actual,before,after,proof,manifest


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_moved_new_input_keeps_connected_bad_peer_failed_and_unknowns_unknown(tmp_path,angle):
    parent,child,before,after,proof,manifest=native_pair(tmp_path,angle)
    original=copy.deepcopy((before,after))
    assert not sense.compare_contour_preservation(before,after,
        modified_nets=['RENAMED_FEED','RENAMED_LOAD'],native_copper_transforms=manifest)['same_evidence']
    result=received._compare_received(parent,child,before,after,proof,
        ['RENAMED_FEED','RENAMED_LOAD'],manifest)
    assert result['comparison_complete'] and result['same_evidence'],result
    assert result['derived_completed_input_legs']==[('ANALOG_SENSOR','p','RENAMED_FEED')]
    assert len(result['moved_input_position_metadata'])==2
    assert result['failed_peer_observations'][0]['existing_departure_failure_retained']
    assert result['failed_peer_observations'][0]['raw_after_ok'] is False
    assert not result['failed_peer_observations'][0]['peer_qualified']
    assert result['coverage_after']['clipped_isolation']['unknown']==2
    assert result['raw_native_evidence_retained'] and not result['full_kelvin_qualification']
    assert not result['release_authority'] and original==(before,after)


@pytest.mark.parametrize('fault',['owner','net','land_size','source_position','after_position',
    'moved_anchor_instead','unreceived_tap','after_cut','after_guard','peer_issue',
    'peer_heading','peer_contact_count','peer_reached','peer_cut','peer_guard',
    'peer_source','peer_old_observation','unrelated_unknown','witness_coordinate',
    'authority_position','forged_macro'])
def test_moved_input_receiver_refuses_changed_physical_contracts_and_peer_laundering(tmp_path,fault):
    parent,child,before,after,proof,manifest=native_pair(tmp_path)
    owner=child.FindFootprintByReference('ANALOG_SENSOR')
    clip=next(r for r in after['clipped_isolation']['details']
        if r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')
    peer=next(r for r in after['inner_departure']['details']
        if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')
    peer_cut=next(r for r in after['clipped_isolation']['details']
        if r['input_ref']=='OTHER_SENSOR' and r['leg']=='p')
    if fault=='owner':owner.SetValue('different-part')
    elif fault=='net':next(iter(owner.Pads())).SetNet(child.FindNet('FILTERED_POS'))
    elif fault=='land_size':next(iter(owner.Pads())).SetSize(pcbnew.VECTOR2I_MM(.7,.6))
    elif fault=='source_position':
        next(r for r in before['same_net_connectivity']['details']
            if r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')['start_pad']['position_nm'][0]+=1
    elif fault=='after_position':clip['sense_terminal']['position_nm'][0]+=1
    elif fault=='moved_anchor_instead':proof['moved_refs']=['MEASUREMENT_ANCHOR']
    elif fault=='unreceived_tap':proof['added_native_uuids']=[]
    elif fault=='after_cut':clip['native']['ok']=False
    elif fault=='after_guard':clip['native']['numerical_guard_nm']+=1
    elif fault=='peer_issue':peer['native']['issues']=[]
    elif fault=='peer_heading':peer['native']['departures'][0]['transverse_error_nm']+=1
    elif fault=='peer_contact_count':peer['native']['contact_count']+=1
    elif fault=='peer_reached':peer['native']['non_sense_departures'][0]['reachable_input_pad_uuids']=['a-peer']
    elif fault=='peer_cut':peer_cut['native']['ok']=False
    elif fault=='peer_guard':peer_cut['native']['numerical_guard_nm']+=1
    elif fault=='peer_source':peer['source_pad']['uuid']='another-shunt'
    elif fault=='peer_old_observation':peer['native']['non_sense_departures'][0]['uuid']='not-received'
    elif fault=='unrelated_unknown':
        next(r for r in after['clipped_isolation']['details']
            if r['input_ref']=='OTHER_SENSOR' and r['leg']=='n')['native']['numerical_guard_nm']+=1
    elif fault=='witness_coordinate':
        next(r for r in after['inner_departure']['details']
            if r['input_ref']=='ANALOG_SENSOR' and r['leg']=='p')['native']['departures'][0]['contact_exit_mm'][0]+=.1
    elif fault=='authority_position':clip['native']['authority'][0]['position_nm'][0]+=1
    else:proof['ok']=False
    try:
        result=received._compare_received(parent,child,before,after,proof,
            ['RENAMED_FEED','RENAMED_LOAD'],manifest)
    except ValueError:return
    assert not result['same_evidence'],result


def test_public_saved_receiver_owns_macro_and_raw_replays_before_any_normalization(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    fixture(source,filtered=False);child.write_bytes(source.read_bytes())
    called=[]
    monkeypatch.setattr(received.macro,'receive',lambda *a,**k:dict(ok=False,complete=False,errors=['refused']))
    monkeypatch.setattr(received.sense,'replay',lambda *a,**k:called.append('untrusted'))
    result=received.receive(source,child,board_hint='opaque')
    assert not result['ok'] and not result['complete'] and not called
    assert result['errors']==['ValueError:independent_saved_macro_replay_refused']


@pytest.mark.parametrize('fault',['source_path','board_hint','family_before','family_after',
    'code_before','code_after','complete','identity_stable'])
def test_public_replay_binding_is_checked_before_comparison_even_with_worker_success(tmp_path,monkeypatch,fault):
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    domains=fixture(source,filtered=False);child.write_bytes(source.read_bytes())
    code=force._code_identity();reports=[]
    for path in (source,child):
        report=run(path,domains);family=force._family(path,'opaque')
        report.update(source=str(path.resolve()),board_hint='opaque',identity_stable=True,
            source_family_before=family,source_family_after=family,code_before=code,code_after=code)
        reports.append(report)
    target=reports[1]
    if fault=='source_path':target['source']=str(source)
    elif fault=='board_hint':target['board_hint']='wrong'
    elif fault.startswith('family_'):target['source_'+fault]={'forged':True}
    elif fault.startswith('code_'):target[fault]={'forged':True}
    else:target[fault]=False
    monkeypatch.setattr(received.macro,'receive',lambda *a,**k:dict(ok=True,complete=True))
    iterator=iter(reports);monkeypatch.setattr(received.sense,'replay',lambda *a,**k:next(iterator))
    monkeypatch.setattr(received,'_compare_received',lambda *a,**k:pytest.fail('unbound packet reached normalization'))
    result=received.receive(source,child,board_hint='opaque')
    assert not result['ok']and not result['complete']
    assert result['errors']==['ValueError:fresh_same_epoch_raw_macro_evidence_required']
