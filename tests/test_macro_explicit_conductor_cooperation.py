"""Explicit ordinary barrel motion is reconstructed and independently replayed."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
from test_complete_macro_cell import fixture
from test_field_proposals import track


def ordinary_frame(tmp_path,monkeypatch,back=False):
    source,parent,unused,initial=fixture(tmp_path,monkeypatch,back=back)
    name='renamed_independent_scalar';parent.Add(pcbnew.NETINFO_ITEM(parent,name))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for index,x in enumerate((22,26)):
        fp=pcbnew.FOOTPRINT(parent);fp.SetReference('fixed_terminal_'+str(index));parent.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(parent.FindNet(name))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,24));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.PAD.PTHMask());fp.Add(pad)
    via=pcbnew.PCB_VIA(parent);via.SetNet(parent.FindNet(name));via.SetPosition(pcbnew.VECTOR2I_MM(24,24))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    track(parent,name,(22,24),(24,24),width=.2,layer=face)
    track(parent,name,(24,24),(26,24),width=.2,layer=face)
    field._save_field_snapshot(parent,source)
    eligible=ordinary.eligible_nets
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *args:eligible(*args)|{name})
    options=dict(ordinary_via_poses=[dict(uuid=force._uid(via),position_nm=[24000000,24750000])])
    return source,pcbnew.LoadBoard(str(source)),initial['source_plan']['poses'],force._uid(via),options


@pytest.mark.parametrize('back',[False,True])
def test_explicit_ordinary_axis_survives_compilation_construction_and_independent_saved_receiving(tmp_path,monkeypatch,back):
    source,parent,poses,via,options=ordinary_frame(tmp_path,monkeypatch,back)
    raw=source.read_bytes();private,packet=compiler.compile(source,poses,board_hint='opaque',**options)
    assert packet['explicit_native_macro_options']==options
    assert packet['transport']['explicit_source_typed_ordinary_barrel_motion'][0]['uuid']==via
    additive._ground_refill(private);native=compiler.native_pose_screen(parent,private,packet)
    assert native['ok'],native
    proof=macro.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    candidate=force._copy_family(source,tmp_path/'ordinary-barrel-child');field._save_field_snapshot(private,candidate)
    received=macro.receive(source,candidate,board_hint='opaque',**options)
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert not macro.receive(source,candidate,board_hint='opaque')['ok']
    assert source.read_bytes()==raw and not received['release_authority']


@pytest.mark.parametrize('fault',['coordinate','identity','drop','extra_option'])
def test_caller_packet_cannot_forge_or_hide_explicit_barrel_motion(tmp_path,monkeypatch,fault):
    source,parent,poses,via,options=ordinary_frame(tmp_path,monkeypatch)
    private,packet=compiler.compile(source,poses,board_hint='opaque',**options);packet=copy.deepcopy(packet)
    if fault=='coordinate':packet['explicit_native_macro_options']['ordinary_via_poses'][0]['position_nm'][0]+=1
    elif fault=='identity':packet['explicit_native_macro_options']['ordinary_via_poses'][0]['uuid']='missing'
    elif fault=='drop':packet.pop('explicit_native_macro_options')
    else:packet['explicit_native_macro_options']['invented_authority']=True
    additive._ground_refill(private)
    result=macro.screen(source,private,packet,board_hint='opaque')
    assert not result['complete'] and result['errors'] and not result['routing_admitted']


@pytest.mark.parametrize('back',[False,True])
def test_pre_refill_collision_report_keeps_authored_net_and_exact_foreign_object(tmp_path,monkeypatch,back):
    source,parent,poses,via,options=ordinary_frame(tmp_path,monkeypatch,back)
    private,packet=compiler.compile(source,poses,board_hint='opaque',**options)
    assert compiler.pre_refill_barrel_screen(private,packet)['ok']
    face=pcbnew.In2_Cu;foreign=track(private,'GND',(23,24.75),(25,24.75),width=.2,layer=face)
    actual=next(t for t in private.GetTracks() if force._uid(t)==via);name=actual.GetNetname()
    result=compiler.pre_refill_barrel_screen(private,packet)
    assert not result['ok'] and result['pre_refill_literal_authored_nets_not_normalized']
    assert any(q.get('uuid')==force._uid(foreign) for row in result['refusals']
        for q in row['diagnostics'].get('blockers',[]))
    assert actual.GetNetname()==name and not result['routing_admitted']
