"""DRAFT native Source ownership tests; no mocked ownership/verdict.

Synthetic export comes from the existing canonical control-shunt fixture.
Full saved macro/native/current/field replay is an independent integration
requirement, not inferred from these ownership/transport unit checks.
"""
import copy,json,math
from pathlib import Path
import pcbnew
import pytest
import cec_control_shunt_ground_return_axes as op
import cec_control_shunt_placement as control
import cec_force_current as force
import cec_field_coupling as field
import cec_smd_macro_transport as transport
import cec_fr as fr
from test_control_shunt_placement import fixture as source_fixture


def case(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,g,root,_=source_fixture(tmp_path,monkeypatch)
    b.SetCopperLayerCount(6)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(properties)
    fp=g.GetParentFootprint();fp.SetPosition(pcbnew.VECTOR2I_MM(30,30))
    fp.SetOrientationDegrees(turn*90)
    if back:fp.Flip(fp.GetPosition(),False)
    u=((1,0),(0,1),(-1,0),(0,-1))[turn];v=(-u[1],u[0])
    g.SetPosition(pcbnew.VECTOR2I_MM(30,30))
    signal=next(p for p in fp.Pads()if force._uid(p)!=force._uid(g))
    signal.SetPosition(pcbnew.VECTOR2I_MM(30+v[0]*1.2,30+v[1]*1.2))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(30+u[0]*1.33,30+u[1]*1.33))
    via.SetWidth(900000);via.SetDrill(500000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNetCode(g.GetNetCode());b.Add(via)
    tail=pcbnew.PCB_TRACK(b);tail.SetStart(g.GetPosition());tail.SetEnd(via.GetPosition())
    tail.SetLayer(face);tail.SetWidth(500000);tail.SetNetCode(g.GetNetCode());b.Add(tail)
    # Literal saved project class, not a mocked resolver/threshold.
    Path(b.GetFileName()).with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{
        'classes':[{'name':'Default','clearance':.2,'track_width':.22,'via_diameter':.6,'via_drill':.3},
                   {'name':'Ground','clearance':.2,'track_width':.5,'via_diameter':.9,'via_drill':.5}],
        'netclass_patterns':[{'pattern':'GND','netclass':'Ground'}]}}))
    field._save_field_snapshot(b,Path(b.GetFileName()))
    posed=pcbnew.LoadBoard(b.GetFileName());new=posed.FindFootprintByReference(fp.GetReference())
    new.SetPosition(pcbnew.VECTOR2I(*(fp.GetPosition()[k]+v[k]*500000 for k in(0,1))))
    newg=next(p for p in new.Pads()if force._uid(p)==force._uid(g))
    point=[newg.GetPosition()[k]+u[k]*789000 for k in(0,1)]
    proposal=dict(poses={fp.GetReference():[new.GetPosition().x/1e6,new.GetPosition().y/1e6,new.GetOrientationDegrees()]},board_hint=str(root))
    request=dict(owner_pad_uuid=force._uid(g),position_nm=point)
    return b,posed,proposal,request,via,tail


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fresh_canonical_control_and_native_exclusive_source_return(tmp_path,monkeypatch,turn,back):
    b,posed,p,r,via,tail=case(tmp_path,monkeypatch,turn,back)
    old=control.row._source_binding(b)
    rows=op.derive(b,posed,p,[r],timeout_s=10.)
    assert len(rows)==1 and rows[0]['uuid']==force._uid(via)
    assert rows[0]['source_tail_uuid']==force._uid(tail)
    assert rows[0]['maximum_return_nm']==800000 and rows[0]['source_full_width_nm']==500000
    assert rows[0]['source_control_shunt']['source_proof']['kind']=='source_control_shunt_ground'
    assert not rows[0]['source_control_shunt']['bypass_owner']
    assert old==control.row._source_binding(b)
    # Existing real native transport, not a fabricated movement proof.
    q=transport.apply(b,posed,source_path=Path(b.GetFileName()),board_hint=p['board_hint'],
        local_signal_return_via_poses=[{k:rows[0][k]for k in('uuid','owner_pad_uuid','position_nm')}])
    op.apply_and_promote(q,rows)
    proof=next(z for z in q['source_process_barrel_motion']if z['uuid']==force._uid(via))
    assert proof['source_control_shunt_return_axis']==rows[0]
    assert not proof['original_barrel_geometry_count_and_relative_owner_seat_preserved']
    assert proof['original_barrel_geometry_and_count_preserved']
    assert q['explicitly_reproved_private_signal_return_reseats']==[]
    live=next(t for t in posed.GetTracks()if force._uid(t)==force._uid(via))
    assert list(live.GetPosition())==r['position_nm']
    assert live.GetWidth(0)==900000 and live.GetDrillValue()==500000


@pytest.mark.parametrize('fault',['remote','notshorter','duplicate','boolcoordinate','extra','wrongpad',
    'source_role','foreign_ground_contact','branched','thin','via_below_class','unmoved','dnp','locked'])
def test_bad_source_or_serialized_request_never_owns_return(tmp_path,monkeypatch,fault):
    b,posed,p,r,via,tail=case(tmp_path,monkeypatch);requests=[r]
    if fault=='remote':r['position_nm'][0]+=1000000
    elif fault=='notshorter':r['position_nm'][0]+=600000
    elif fault=='duplicate':requests.append(copy.deepcopy(r))
    elif fault=='boolcoordinate':r['position_nm'][0]=True
    elif fault=='extra':r['allow_locked']=True
    elif fault=='wrongpad':r['owner_pad_uuid']=force._uid(next(pad for f in b.GetFootprints()for pad in f.Pads()if pad.GetNetname()!='GND'))
    elif fault=='source_role':next(f for f in b.GetFootprints()if not any(force._uid(z)==r['owner_pad_uuid']for z in f.Pads())).SetField('MPN','unknown')
    elif fault=='foreign_ground_contact':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('extra_same_ground_land');b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        pad.SetPosition(via.GetPosition());pad.SetNetCode(via.GetNetCode());fp.Add(pad)
    elif fault=='branched':
        t=pcbnew.PCB_TRACK(b);t.SetStart(via.GetPosition());t.SetEnd(via.GetPosition()+pcbnew.VECTOR2I_MM(0,1))
        t.SetLayer(0);t.SetWidth(500000);t.SetNetCode(via.GetNetCode());b.Add(t)
    elif fault=='thin':tail.SetWidth(220000)
    elif fault=='via_below_class':via.SetWidth(600000);via.SetDrill(300000)
    elif fault=='unmoved':posed=pcbnew.LoadBoard(b.GetFileName())
    elif fault=='dnp':tail.GetBoard().FindFootprintByReference(next(f.GetReference()for f in b.GetFootprints()if any(force._uid(z)==r['owner_pad_uuid']for z in f.Pads()))).SetDNP(True)
    elif fault=='locked':next(f for f in b.GetFootprints()if any(force._uid(z)==r['owner_pad_uuid']for z in f.Pads())).SetLocked(True)
    before=control.row._source_binding(b)
    with pytest.raises(ValueError):op.derive(b,posed,p,requests,timeout_s=10.)
    assert before==control.row._source_binding(b)


def test_default_unchanged_and_final_deadline_no_budget_reset(tmp_path,monkeypatch):
    b,posed,p,r,_,_=case(tmp_path,monkeypatch)
    assert op.derive(b,posed,p,[],timeout_s=10.)==[]
    clock=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    old=control.plan
    def slow(*args,**kw):
        q=old(*args,**kw);clock[0]=11.;return q
    monkeypatch.setattr(control,'plan',slow)
    with pytest.raises(ValueError,match='deadline'):op.derive(b,posed,p,[r],timeout_s=10.)
