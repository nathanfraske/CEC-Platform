"""Explicit Source-owned resistor Ground shortening is not an RC alias."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_control_shunt_ground_return_axes as axes
import cec_smd_macro_transport as transport
import cec_cell_macro_requests as compiler
from cec_native_items import discard_items
from test_programming_resistor_placement import fixture


def case(tmp_path,monkeypatch,turn=0,back=False,monitor=False):
    b,owner,fp,root,tree,_=fixture(tmp_path,monkeypatch,monitor_pin='6'if monitor else None)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(properties)
    fp.SetPosition(pcbnew.VECTOR2I_MM(30,30));fp.SetOrientationDegrees(90*turn)
    if back:fp.Flip(fp.GetPosition(),False)
    u=((1,0),(0,1),(-1,0),(0,-1))[turn];v=(-u[1],u[0])
    g=next(p for p in fp.Pads()if p.GetNetname()=='GND')
    s=next(p for p in fp.Pads()if p.GetNetname()!='GND')
    g.SetPosition(pcbnew.VECTOR2I_MM(30,30));s.SetPosition(pcbnew.VECTOR2I_MM(30+v[0]*1.2,30+v[1]*1.2))
    discard_items(b,list(b.GetTracks()))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(30+u[0]*1.33,30+u[1]*1.33))
    via.SetNetCode(g.GetNetCode());via.SetWidth(900000);via.SetDrill(500000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);b.Add(via)
    tail=pcbnew.PCB_TRACK(b);tail.SetStart(g.GetPosition());tail.SetEnd(via.GetPosition());tail.SetLayer(face)
    tail.SetWidth(500000);tail.SetNetCode(g.GetNetCode());b.Add(tail)
    Path(b.GetFileName()).with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name='Default',track_width=.22,clearance=.2,via_diameter=.6,via_drill=.3),
            dict(name='Ground',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_patterns=[dict(pattern='GND',netclass='Ground')]))))
    field._save_field_snapshot(b,Path(b.GetFileName()))
    posed=pcbnew.LoadBoard(b.GetFileName());after=posed.FindFootprintByReference(fp.GetReference())
    after.SetPosition(pcbnew.VECTOR2I(*(fp.GetPosition()[k]+v[k]*500000 for k in(0,1))))
    newg=next(p for p in after.Pads()if force._uid(p)==force._uid(g))
    request=dict(owner_pad_uuid=force._uid(g),position_nm=[newg.GetPosition()[k]+u[k]*789000 for k in(0,1)])
    proposal=dict(poses={fp.GetReference():[after.GetPosition().x/1e6,after.GetPosition().y/1e6,after.GetOrientationDegrees()]},board_hint=str(root))
    return b,posed,proposal,request,via,tail,tree


@pytest.mark.parametrize('monitor',[False,True])
@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_native_resistor_return_keeps_class_barrel_and_shortens(tmp_path,monkeypatch,monitor,turn,back):
    b,posed,p,r,via,tail,_=case(tmp_path,monkeypatch,turn,back,monitor)
    before=force._hash(b.GetFileName());binding=axes.row._source_binding(b)
    derived=axes.derive(b,posed,p,[r],timeout_s=9.)
    assert len(derived)==1 and 'source_programming_resistor'in derived[0]and 'source_control_shunt'not in derived[0]
    model=derived[0]['source_programming_resistor']['source_proof']['manufacturer']
    assert model['role']==('grounded_voltage_monitor_divider_lower'if monitor else 'output_current_limit_programming')
    result=transport.apply(b,posed,source_path=Path(b.GetFileName()),board_hint=p['board_hint'],
        source_control_ground_return_axes=[copy.deepcopy(r)],timeout_s=9.)
    record=next(q for q in result['source_process_barrel_motion']if q['uuid']==force._uid(via))
    assert record['owner_footprint_uuids']==[derived[0]['source_programming_resistor']['resistor_uuid']]
    assert record['source_control_shunt_return_axis']==derived[0]
    assert result['explicitly_reproved_private_signal_return_reseats']==[]and result['new_barrels_created']==0
    assert compiler._retained_ground_dogbones(b,posed,result)==[dict(uuid=force._uid(tail),
        via_uuid=force._uid(via),owner_pad_uuid=r['owner_pad_uuid'],source_factory_pickup_retained_not_retired=True)]
    saved={force._uid(t):t for t in posed.GetTracks()};v=saved[force._uid(via)]
    assert list(v.GetPosition())==r['position_nm']and v.GetWidth(v.TopLayer())==900000 and v.GetDrillValue()==500000
    assert saved[force._uid(tail)].GetWidth()==500000 and saved[force._uid(tail)].GetLength()==789000
    assert before==force._hash(b.GetFileName())and binding==axes.row._source_binding(b)


@pytest.mark.parametrize('fault',['legacy_RC','mixed_requests','caller_role','bool_coordinate','remote','notshorter',
    'unknown_owner','thin_tail','small_via','branched','peer_pad','unknown_part','owner_moved','unmoved','wrong_pad'])
def test_raw_or_weakened_context_never_grants_resistor_barrel_motion(tmp_path,monkeypatch,fault):
    b,posed,p,r,via,tail,_=case(tmp_path,monkeypatch)
    kw=dict(source_control_ground_return_axes=[r]);owner=posed.FindFootprintByReference('U_program')
    if fault=='legacy_RC':kw=dict(local_signal_return_via_poses=[dict(r,uuid=force._uid(via))])
    elif fault=='mixed_requests':kw['local_signal_return_via_poses']=[dict(r,uuid=force._uid(via))]
    elif fault=='caller_role':r['allow_resistor']=True
    elif fault=='bool_coordinate':r['position_nm'][0]=True
    elif fault=='remote':r['position_nm'][0]+=1000000
    elif fault=='notshorter':r['position_nm'][0]+=600000
    elif fault=='unknown_owner':b.FindFootprintByReference('U_program').SetField('MPN','unknown')
    elif fault=='thin_tail':tail.SetWidth(220000)
    elif fault=='small_via':via.SetWidth(600000);via.SetDrill(300000)
    elif fault=='branched':
        t=pcbnew.PCB_TRACK(b);t.SetStart(via.GetPosition());t.SetEnd(via.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
        t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000);t.SetNetCode(via.GetNetCode());b.Add(t)
        posed.Add(pcbnew.PCB_TRACK(t))
    elif fault=='peer_pad':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('extra');b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetPosition(via.GetPosition());pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNetCode(via.GetNetCode());fp.Add(pad)
        posed.Add(pcbnew.FOOTPRINT(fp))
    elif fault=='unknown_part':b.FindFootprintByReference('R_program').SetField('MPN','unknown')
    elif fault=='owner_moved':owner.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unmoved':posed=pcbnew.LoadBoard(b.GetFileName())
    else:r['owner_pad_uuid']=force._uid(b.FindFootprintByReference('U_program').FindPadByNumber('12'))
    before=axes.row._source_binding(posed)
    with pytest.raises(ValueError):transport.apply(b,posed,source_path=Path(b.GetFileName()),board_hint=p['board_hint'],
        timeout_s=9.,**kw)
    assert before==axes.row._source_binding(posed)


def test_default_and_frame_delegate_identity_only_requests_to_fresh_native_consumer(tmp_path,monkeypatch):
    b,posed,p,r,via,tail,_=case(tmp_path,monkeypatch)
    assert axes.derive(b,posed,p,[],timeout_s=9.)==[]
    import inspect
    assert inspect.signature(transport.apply).parameters['source_control_ground_return_axes'].default==()
    frame=inspect.getsource(compiler._frame)
    assert 'source_control_ground_return_axes=control_shunt_ground_return_axes'in frame
    assert 'derive(parent,private,proposal,control_shunt_ground_return_axes'not in frame
