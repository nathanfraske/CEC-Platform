"""Only actual retained fixed-owner Ground fragments acquire restoration debt."""
import copy
import pcbnew
import pytest
import cec_stationary_owner_ground_obligations as op
import cec_cell_macro_requests as compiler
import cec_cell_ground_cut_boundaries as boundaries
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_complete_macro_cell as macro
from cec_native_items import discard_items
from test_complete_macro_cell import fixture as complete_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,oldprivate,oldpacket=complete_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    capref=next(iter(oldpacket['source_plan']['selected_bypasses']))
    cap=parent.FindFootprintByReference(capref)
    old_points={tuple(p.GetPosition())for p in cap.Pads()}
    delta=pcbnew.VECTOR2I(*[(-1200000,0),(0,1200000),(1200000,0),(0,-1200000)][quarter])
    cap.Move(delta)
    for track in parent.GetTracks():
        if track.GetClass()!='PCB_TRACK':continue
        if tuple(track.GetStart())in old_points:track.SetStart(track.GetStart()+delta)
        if tuple(track.GetEnd())in old_points:track.SetEnd(track.GetEnd()+delta)
    # An old floating owner/cap island: no old Source barrel may silently
    # provide a plane return after the cap-to-owner native chain is cut.
    discard_items(parent,[t for t in parent.GetTracks()if t.GetNetname()=='GND'and t.GetClass()=='PCB_VIA'])
    field._save_field_snapshot(parent,source);parent=pcbnew.LoadBoard(str(source))
    ownerref=oldpacket['source_plan']['selected_bypasses'][capref]['owner']
    fixed=parent.FindFootprintByReference(ownerref)
    livecap=parent.FindFootprintByReference(capref)
    poses={capref:[livecap.GetPosition().x/1e6+.1,livecap.GetPosition().y/1e6+.1,
        livecap.GetOrientationDegrees()],ownerref:[
        fixed.GetPosition().x/1e6,fixed.GetPosition().y/1e6,fixed.GetOrientationDegrees()]}
    private,packet=compiler.compile(source,poses,board_hint='opaque')
    ownerref=packet['source_plan']['selected_bypasses'][capref]['owner']
    owner=parent.FindFootprintByReference(ownerref)
    ground=next(p for p in owner.Pads()if p.GetNetname()=='GND')
    cuts=boundaries.requests(parent,private,packet['source_plan'])
    return source,parent,private,packet,ground,cuts


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_fixed_ground_fragment_gets_exact_source_debt_only(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet,ground,cuts=fixture(tmp_path,monkeypatch,quarter,back)
    before=[row._source_binding(b)for b in(parent,private)]
    result=op.requests(parent,private,packet['source_plan'],cuts)
    key='ground:'+force._uid(ground)
    assert set(result)=={key}
    request=result[key];debt=request['stationary_selected_owner_native_ground_cut_debt']
    assert debt['actual_retained_source_pad_key']==list(force._item_key(ground))
    assert debt['original_fixed_owner_signal_supply_and_other_pins_not_retyped']
    assert debt['original_native_fragment_and_local_return_still_mandatory']
    assert not debt['current_authority'] and not debt['release_authority']
    assert packet['requests'][key]==request
    assert before==[row._source_binding(b)for b in(parent,private)]


@pytest.mark.parametrize('fault',['no_cut','no_motion','unrelated','bad_binding','forged_fragment','owner_moved'])
def test_no_blanket_stationary_or_same_net_pin_authority(tmp_path,monkeypatch,fault):
    source,parent,private,packet,ground,cuts=fixture(tmp_path,monkeypatch)
    proposal=copy.deepcopy(packet['source_plan']);cuts=copy.deepcopy(cuts)
    if fault=='no_cut':assert op.requests(parent,private,proposal,{})=={};return
    if fault=='no_motion':
        ref=next(iter(proposal['selected_bypasses']));old=parent.FindFootprintByReference(ref)
        live=private.FindFootprintByReference(ref);live.SetPosition(old.GetPosition());live.SetOrientationDegrees(old.GetOrientationDegrees())
        assert op.requests(parent,private,proposal,cuts)=={};return
    if fault=='unrelated':
        # A real same-net pad elsewhere is not the retained owner contact.
        pad=next(p for f in parent.GetFootprints()for p in f.Pads()if p.GetNetname()!='GND')
        for cut in cuts.values():cut['retained_source_ground_fragment']['retained_fragment_keys']=[list(force._item_key(pad))]
        assert op.requests(parent,private,proposal,cuts)=={};return
    if fault=='bad_binding':proposal['source_native_binding']='forged'
    elif fault=='forged_fragment':
        next(iter(cuts.values()))['retained_source_ground_fragment']['actual_fixed_source_contacts_not_same_net_proximity']=False
    else:private.FindFootprintByReference(ground.GetParentFootprint().GetReference()).Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError):op.requests(parent,private,proposal,cuts)


def test_saved_complete_macro_cannot_accept_unrestored_stationary_ground(tmp_path,monkeypatch):
    source,parent,private,packet,ground,cuts=fixture(tmp_path,monkeypatch)
    child=force._copy_family(source,tmp_path/'unrestored-child')
    macro.save_private(private,child,packet)
    result=macro.receive(source,child,board_hint='opaque')
    assert not result['ok'] and not result['complete'] and result['errors']


def test_converter_never_gains_low_power_ground_entry_from_a_cut(tmp_path,monkeypatch):
    from test_stationary_power_stage_owner import stage_fixture
    source,parent,private,packet,ground,cuts=fixture(tmp_path,monkeypatch)
    stage,poses,owner,cap,model=stage_fixture(monkeypatch,'TPS2121RUXR')
    path=tmp_path/'converter.kicad_pcb';field._save_field_snapshot(stage,path)
    before,after=[pcbnew.LoadBoard(str(path))for _ in range(2)]
    proposal=escape.prepare(before,poses,board_hint='opaque')
    escape.apply_private(after,proposal)
    # Even the existence of a genuine native cut elsewhere cannot promote
    # a converter to the low-power selected-owner Ground policy.
    assert op.requests(before,after,proposal,cuts)=={}


@pytest.mark.parametrize('timeout',[0,-1,11,True,float('nan')])
def test_inventory_lease_always_bounded(timeout):
    with pytest.raises(ValueError):op.requests(None,None,{}, {},timeout_s=timeout)


def test_strict_merge_absent_and_identical_contracts_preserve_all_fields():
    one={'ground:a':dict(kind='ground',net='GND',reach_mm=.8,
        a=dict(pad_uuid='a',at_nm=[1,2],layers=[0]))}
    debt={'ground:b':dict(kind='ground',net='GND',reach_mm=4.,
        stationary_selected_owner_native_ground_cut_debt=dict(current_authority=False))}
    before=copy.deepcopy((one,debt))
    assert op.merge(one,{})==one and op.merge({},debt)==debt
    assert op.merge(one,debt)=={**one,**debt}
    assert op.merge(one,copy.deepcopy(one))==one
    assert (one,debt)==before


@pytest.mark.parametrize('field,value',[('reach_mm',4.1),('net','other'),('kind','local_supply'),
    ('a',dict(pad_uuid='other',at_nm=[1,2],layers=[0])),('new_field',False)])
def test_strict_merge_conflict_never_overwrites_existing_contract(field,value):
    one={'ground:a':dict(kind='ground',net='GND',reach_mm=.8,
        a=dict(pad_uuid='a',at_nm=[1,2],layers=[0]))}
    debt=copy.deepcopy(one);debt['ground:a'][field]=value;before=copy.deepcopy((one,debt))
    with pytest.raises(ValueError,match='conflicts_with_existing'):op.merge(one,debt)
    assert (one,debt)==before


@pytest.mark.parametrize('existing,debts',[([],{}),({},[]),(None,{})])
def test_strict_merge_requires_typed_maps(existing,debts):
    with pytest.raises(ValueError):op.merge(existing,debts)
