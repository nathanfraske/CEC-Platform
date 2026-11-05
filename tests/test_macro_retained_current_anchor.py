"""Old barrel/keeper contact is a mandatory replacement path, not motion."""
import copy,json,time
import pcbnew,pytest
import cec_additive_route_receiving as additive
import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_priority_reconstruction as pending
import cec_native_construction_frame as frame
from cec_native_items import discard_items
from test_macro_priority_reconstruction import aggregate_case


def keeper_case(tmp_path,monkeypatch):
    source,parent,_,previous,_=aggregate_case(tmp_path,monkeypatch)
    barrel=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetNetname()=='RAIL')
    surface=next(p for f in parent.GetFootprints()for p in f.Pads()
        if p.GetNetname()=='RAIL'and f.GetReference()in previous['source_plan']['selected_bypasses'])
    face=pcbnew.F_Cu if surface.IsOnLayer(pcbnew.B_Cu)else pcbnew.B_Cu
    cuts=set(previous['retired_track_uuids'])
    tail=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='RAIL'
        and t.IsOnLayer(face)and force._uid(t)in cuts)
    fixed=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='RAIL'
        and t.IsOnLayer(face)and force._uid(t)not in cuts)
    at=barrel.GetPosition();tail.SetEnd(pcbnew.VECTOR2I(at.x-200000,at.y))
    fixed.SetStart(tail.GetEnd());fixed.SetEnd(pcbnew.VECTOR2I(at.x-2000000,at.y));fixed_id=force._uid(fixed)
    additive._ground_refill(parent);field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source));proposal=compiler.escape.prepare(parent,
        previous['source_plan']['poses'],board_hint='opaque')
    candidate,transport=compiler._frame(parent,source,proposal,timeout_s=9.)
    retired={force._uid(t)for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'
        and t.GetNetname()=='RAIL'and force._uid(t)!=fixed_id}
    changes={q['uuid']:q for q in transport['changes']};actual={force._uid(t):t for t in candidate.GetTracks()}
    extras=[]
    for t in parent.GetTracks():
        uid=force._uid(t)
        if uid not in retired:continue
        change=changes.get(uid,dict(uuid=uid,net='RAIL',source_nm=[list(t.GetStart()),list(t.GetEnd())],
            candidate_nm=[list(actual[uid].GetStart()),list(actual[uid].GetEnd())]))
        plan=pending.full.plan(parent,source,board_hint='opaque',retired_track_uuids=[uid])
        extras.append(dict(change=change,authority=dict(kind=pending.KIND,native_source_uuid=uid,source_plan=plan)))
    cut=frame.clone(candidate,time.monotonic()+9.)
    discard_items(cut,[t for t in cut.GetTracks()if force._uid(t)in retired])
    demands,records=pending.components.requests(parent,cut,extras,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+9.)
    with force._thermal_hint('opaque'):contract=pending.cells._supply_current_widths(parent,'RAIL')
    for request in demands.values():request['unchanged_full_rail_current_contract']=contract
    packet=json.loads(json.dumps(dict(scope='source_typed_complete_native_macro_requests',source=str(source),
        source_sha256=force._hash(source),code_identity=force._code_identity(),source_plan=proposal,transport=transport,
        additional_source_boundary_ownership=extras,additional_source_cut_components=records,
        retired_track_uuids=sorted(retired),requests=demands)))
    return source,parent,candidate,packet,transport,fixed_id


def test_unchanged_rated_keeper_contact_requires_its_mandatory_replacement_path(tmp_path,monkeypatch):
    source,parent,candidate,packet,transport,keeper=keeper_case(tmp_path,monkeypatch)
    before=source.read_bytes();binding=frame.binding(candidate,time.monotonic()+9.)
    result=pending.inspect(parent,candidate,transport,packet,board_hint='opaque',timeout_s=9.)
    assert keeper not in result['track_uuids']and keeper not in result['barrel_uuids']
    contacts=[c for b in result['retained_source_supply_barrels']for c in b['complete_old_contacts']]
    assert any(c['source_uuid']==keeper and c.get('unchanged_retained_rated_component_anchor')for c in contacts)
    assert source.read_bytes()==before and frame.binding(candidate,time.monotonic()+9.)==binding
    assert not result['routing_admitted']and not result['current_qualified']


@pytest.mark.parametrize('fault',['request_missing','keeper_moved','keeper_width','keeper_group'])
def test_keeper_must_remain_exact_and_every_same_component_port_mandatory(tmp_path,monkeypatch,fault):
    source,parent,candidate,packet,transport,keeper=keeper_case(tmp_path,monkeypatch)
    packet=copy.deepcopy(packet)
    item=next(t for t in candidate.GetTracks()if force._uid(t)==keeper)
    if fault=='request_missing':
        key=next(k for k,r in packet['requests'].items()if any(keeper in r[e].get('native_uuids',[])for e in('a','b')))
        del packet['requests'][key]
    elif fault=='keeper_moved':item.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='keeper_width':item.SetWidth(item.GetWidth()-1)
    else:
        group=pcbnew.PCB_GROUP(candidate);group.SetName('invented_keeper_group');candidate.Add(group);group.AddItem(item)
    with pytest.raises(ValueError):pending.inspect(parent,candidate,transport,packet,board_hint='opaque',timeout_s=9.)
