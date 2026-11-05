"""Typed current reconstruction reaches priority without ordinary aliases."""
import copy,json
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_force_current as force
import cec_macro_priority_preflight as priority
from test_macro_priority_reconstruction import aggregate_case


def pending_case(tmp_path,monkeypatch,quarter=0,back=False):
    # Claims come from real stock singleton current/component constructors;
    # this bounded fixture is a priority-handoff unit, not saved admission.
    source,parent,uncut,packet,transport=aggregate_case(tmp_path,monkeypatch,quarter,back)
    assert json.loads(json.dumps(transport,allow_nan=False))==packet['transport']
    return source,parent,uncut,packet,transport


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_full_current_pending_source_restoration_is_not_unplanned_priority_motion(tmp_path,monkeypatch,quarter,back):
    source,parent,uncut,packet,transport=pending_case(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes()
    strict=priority.inspect(parent,uncut,transport,board_hint='opaque',timeout_s=9.)
    assert not strict['ok']and strict['moved_priority_source_conductor_uuids']
    received=priority.inspect(parent,uncut,transport,board_hint='opaque',timeout_s=9.,
        source_reconstruction_packet=packet)
    assert not received['moved_priority_source_conductor_uuids'],received
    # Pending role proof cannot waive the fixture's real geometric conflicts.
    assert received['conflicts']==strict['conflicts']
    assert received['ok']==(not received['conflicts'])
    proof=received['independently_typed_pending_full_current_reconstruction']
    assert proof and proof['track_uuids']and proof['barrel_uuids']
    assert received['moving_land_or_barrel_count']==strict['moving_land_or_barrel_count']
    assert source.read_bytes()==raw
    assert not any(received[k]for k in('routing_admitted','release_authority','current_or_clearance_qualified'))


@pytest.mark.parametrize('fault',['missing_request','request_width','request_endpoint','missing_component',
    'contract','ordinary_label','unretired','barrel_drill','barrel_inner_width','wrong_owner'])
def test_source_packet_claims_never_supply_priority_reconstruction_authority(tmp_path,monkeypatch,fault):
    source,parent,uncut,packet,transport=pending_case(tmp_path,monkeypatch)
    packet=copy.deepcopy(packet)
    current=[r for r in packet['additional_source_boundary_ownership']
        if r.get('authority',{}).get('kind')=='unchanged_full_current_source_edge']
    assert current
    keys=[k for c in packet['additional_source_cut_components']
        if c['net']=='RAIL'for k in c['request_ids']]
    if fault=='missing_request':packet['requests'].pop(keys[0])
    elif fault=='request_width':packet['requests'][keys[0]]['width_nm']-=1
    elif fault=='request_endpoint':packet['requests'][keys[0]]['a']['at_nm'][0]+=1
    elif fault=='missing_component':packet['additional_source_cut_components']=[c for c in packet['additional_source_cut_components']if c['net']!='RAIL']
    elif fault=='contract':current[0]['authority']['source_plan']['contract']['current_authority']['amps']*=.5
    elif fault=='ordinary_label':current[0]['authority']['kind']='positive_source_ordinary'
    elif fault=='unretired':packet['retired_track_uuids'].remove(current[0]['change']['uuid'])
    else:
        rows=[q for q in transport['source_process_barrel_motion']if
            next(t for t in parent.GetTracks()if force._uid(t)==q['uuid']).GetNetname()=='RAIL']
        assert len(rows)==1;via=next(t for t in uncut.GetTracks()if force._uid(t)==rows[0]['uuid'])
        if fault=='barrel_drill':via.SetDrill(via.GetDrillValue()+1)
        elif fault=='barrel_inner_width':
            via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM);via.SetWidth(pcbnew.In2_Cu,via.GetWidth(pcbnew.In2_Cu)+1)
        else:
            packet['transport']['source_process_barrel_motion']=copy.deepcopy(packet['transport']['source_process_barrel_motion'])
            row=next(q for q in packet['transport']['source_process_barrel_motion']if q['uuid']==rows[0]['uuid'])
            row['source_owner_pad_uuids']=['00000000-0000-0000-0000-000000000000']
    with pytest.raises(ValueError):
        priority.inspect(parent,uncut,transport,board_hint='opaque',timeout_s=9.,source_reconstruction_packet=packet)
