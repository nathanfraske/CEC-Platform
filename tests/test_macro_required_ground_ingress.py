"""Future Ground clearance is conditional on an actual new saved column."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_macro_ground_ingress as ingress
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items
from test_complete_macro_cell import fixture
from test_field_proposals import track


def source_frame(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,unused,initial=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    selected=initial['source_plan']['selected_bypasses'];cap=next(iter(selected));owner=selected[cap]['owner']
    fp=parent.FindFootprintByReference(owner)
    pad=next(p for p in fp.Pads() if p.GetNetname()=='GND')
    # This Source owner has a real longer Ground return, not a private
    # barrel that simply follows it and makes the promised hole redundant.
    discard_items(parent,[t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA'
        and tuple(t.GetPosition())==tuple(pad.GetPosition())])
    at=[v+500000 for v in pad.GetPosition()];name='source_owned_control_aperture'
    parent.Add(pcbnew.NETINFO_ITEM(parent,name));face=pcbnew.In2_Cu
    for i,sign in enumerate((-1,1)):
        other=pcbnew.FOOTPRINT(parent);other.SetReference('fixed_native_control_'+str(i));parent.Add(other)
        terminal=pcbnew.PAD(other);terminal.SetNumber('1');terminal.SetNet(parent.FindNet(name))
        terminal.SetPosition(pcbnew.VECTOR2I(at[0]+sign*3000000,at[1]));terminal.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        terminal.SetShape(pcbnew.PAD_SHAPE_CIRCLE);terminal.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        terminal.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));terminal.SetLayerSet(pcbnew.PAD.PTHMask());other.Add(terminal)
    obstruction=track(parent,name,((at[0]-3000000)/1e6,at[1]/1e6),
        ((at[0]+3000000)/1e6,at[1]/1e6),width=.2,layer=face)
    field._save_field_snapshot(parent,source)
    eligible=ordinary.eligible_nets
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:eligible(*a,**k)|{name})
    return source,initial['source_plan']['poses'],force._uid(pad),force._uid(obstruction)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_owned_foreign_lead_can_fund_only_a_mandatory_real_ground_entry(tmp_path,monkeypatch,quarter,back):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes()
    with pytest.raises(ValueError,match='does_not_block_actual_future_native_copper'):
        compiler.compile(source,poses,board_hint='opaque',additional_obstacle_track_uuids=[obstruction])
    private,packet=compiler.compile(source,poses,board_hint='opaque',
        additional_obstacle_track_uuids=[obstruction],required_ground_pad_entries=[pad])
    required=packet['required_projected_ground_entries']
    assert len(required)==1 and required[0]['pad_uuid']==pad and required[0]['mandatory_new_saved_barrel']
    assert packet['requests']['ground:'+pad]['required_projected_ground_entry']==required[0]
    assert compiler.packet_options(packet)['required_ground_pad_entries']==[pad]
    evidence=next(q for q in packet['additional_source_boundary_ownership'] if q['change']['uuid']==obstruction)
    contacts=evidence['source_native_obstacle_ownership']['literal_foreign_native_conflicts']
    assert any(q.get('mandatory_projected_ground_entry')==required[0] for q in contacts)
    assert not any(force._uid(t)==required[0]['proposal_column_uuid'] for t in private.GetTracks())
    assert source.read_bytes()==raw and packet['no_new_copper_or_barrels_constructed']


@pytest.mark.parametrize('fault',['missing','role','point','diameter','source','duplicate'])
def test_promised_column_rederives_source_role_land_process_and_identity(tmp_path,monkeypatch,fault):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch)
    private,packet=compiler.compile(source,poses,board_hint='opaque',
        additional_obstacle_track_uuids=[obstruction],required_ground_pad_entries=[pad])
    q=copy.deepcopy(packet['required_projected_ground_entries'][0])
    if fault=='missing':q['pad_uuid']='no-such-pad'
    elif fault=='role':q['source_role']={'kind':'net_name_only'}
    elif fault=='point':q['point_nm'][0]+=1
    elif fault=='diameter':q['diameter_nm']-=1
    elif fault=='source':q['source_sha256']='not-the-source'
    else:
        p=next(p for f in private.GetFootprints() for p in f.Pads() if force._uid(p)==pad)
        v=pcbnew.PCB_VIA(private);v.SetNet(p.GetNet());v.SetPosition(p.GetPosition())
        v.SetWidth(350000);v.SetDrill(250000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);private.Add(v)
    with pytest.raises((ValueError,KeyError)):
        ingress.rederive(private,q)


@pytest.mark.parametrize('fault',['none','wrong_point','wrong_drill','wrong_diameter','two'])
def test_alternate_or_missing_ground_copper_cannot_pay_for_a_promised_column(fault):
    proof=dict(point_nm=[1000000,2000000],drill_nm=250000,diameter_nm=350000)
    op=['via',[1000000,2000000],.25,.35];ops=[op]
    if fault=='none':ops=[['trk',[1000000,2000000],[1500000,2000000],200000,0]]
    elif fault=='wrong_point':op[1][0]+=1
    elif fault=='wrong_drill':op[2]=.2
    elif fault=='wrong_diameter':op[3]=.3
    else:ops.append(copy.deepcopy(op))
    assert not ingress.required_ops(proof,ops)
    assert ingress.required_ops(proof,[['via',[1000000,2000000],.25,.35]])


@pytest.mark.parametrize('back',[False,True])
def test_complete_cell_build_and_saved_receiving_reobserve_the_exact_new_column(tmp_path,monkeypatch,back):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch,back=back)
    options=dict(required_ground_pad_entries=[pad],additional_obstacle_track_uuids=[obstruction])
    private,packet=compiler.compile(source,poses,board_hint='opaque',**options);additive._ground_refill(private)
    screen=macro.screen(source,private,packet,board_hint='opaque')
    assert screen['complete'],(screen.get('errors'),screen.get('empty_obligations'))
    escape.construct_private(private,screen['packet'],screen['selection']);additive._ground_refill(private)
    old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    incoming=[t for t in private.GetTracks() if force._uid(t) not in old and t.GetClass()=='PCB_VIA']
    fr.group_local_pofv_signal_vias(private,incoming)
    child=force._copy_family(source,tmp_path/'required-ground-child');field._save_field_snapshot(private,child)
    result=macro.receive(source,child,board_hint='opaque',**options)
    assert result['ok'] and result['actual_required_projected_ground_entries'][0]['pad_uuid']==pad,result['errors']
    new_via=next(t for t in private.GetTracks() if force._uid(t)==result['actual_required_projected_ground_entries'][0]['via_uuid'])
    discard_items(private,[new_via]);field._save_field_snapshot(private,child)
    assert not macro.receive(source,child,board_hint='opaque',**options)['ok']


@pytest.mark.parametrize('value',[None,True,{},['missing','missing'],list(map(str,range(5)))])
def test_required_column_requests_have_a_finite_unique_id_scope(tmp_path,monkeypatch,value):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch)
    with pytest.raises(ValueError):compiler.compile(source,poses,board_hint='opaque',required_ground_pad_entries=value)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_required_entry_has_native_construction_even_if_generic_return_prefers_reuse(tmp_path,monkeypatch,quarter,back):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch,quarter,back)
    private,packet=compiler.compile(source,poses,board_hint='opaque',
        additional_obstacle_track_uuids=[obstruction],required_ground_pad_entries=[pad])
    additive._ground_refill(private);before=escape.row._source_binding(private)
    # The old first-success return heuristic is not authority for this
    # mandatory Source-owned column. Its reuse/coverage preference must not
    # suppress an independently qualified exact new entry.
    monkeypatch.setattr(escape.cell,'_add_ground_return',lambda *a,**k:({'items':[]},None))
    requests={'ground:'+pad:packet['requests']['ground:'+pad]}
    choices=escape.menus(private,requests,board_path='opaque',board_hint='opaque')
    values=choices['domains']['ground:'+pad]
    assert len(values)==1 and ingress.required_ops(packet['required_projected_ground_entries'][0],values[0]['ops'])
    assert choices['diagnostics']['ground:'+pad]['required_ground_entry_offer']['found']
    assert escape.row._source_binding(private)==before


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
def test_required_entry_is_not_constructed_through_native_foreign_copper(tmp_path,monkeypatch,face):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch)
    private,packet=compiler.compile(source,poses,board_hint='opaque',
        additional_obstacle_track_uuids=[obstruction],required_ground_pad_entries=[pad])
    additive._ground_refill(private);proof=packet['required_projected_ground_entries'][0]
    x,y=[v/1e6 for v in proof['point_nm']]
    track(private,'source_owned_control_aperture',(x-.5,y),(x+.5,y),width=.2,layer=face)
    before=escape.row._source_binding(private)
    ops,detail=ingress.entry_ops(private,proof)
    assert not ops and not detail['found'] and not detail['no_path_proof']
    assert escape.row._source_binding(private)==before
