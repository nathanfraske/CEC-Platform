"""Complete compiler carries isolated supply ports without losing joins."""
import pcbnew
import json
import copy
import pytest
import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
import cec_source_reference_group_transport as reference
from test_isolated_selected_bypass_supply_transport_20261026 import fixture as base,HINT
from test_field_proposals import track


def fixture(tmp_path,back=False):
    parent,child,source,ids,remote,gid=base(tmp_path,back=back)
    for fp in parent.GetFootprints():
        fp.SetLocked(False)
        for p in fp.Pads():p.SetDrillSize(pcbnew.VECTOR2I(0,0))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    # Keep the original mixed locked neckdown scope; split only its ungrouped
    # full-width tail into three real Source strokes, making five in total.
    tail=next(t for t in parent.GetTracks()if force._uid(t)==ids[-1])
    parent.Remove(tail)
    for a,z in [((11,10),(11.3,10)),((11.3,10),(11.7,10)),((11.7,10),(12,10))]:
        t=track(parent,'+3V3',a,z,width=.5,layer=face);t.SetLocked(True)
    main=track(parent,'+3V3',(30,25),(30,30),width=.5,layer=face)
    cap=parent.FindFootprintByReference('C_RENAMED');cap.SetReference('C8');cap.Reference().SetVisible(False)
    court=pcbnew.B_CrtYd if back else pcbnew.F_CrtYd
    opposite=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    group=pcbnew.PCB_GROUP(parent);group.SetName(reference.PREFIX+cap.GetReference())
    parent.Add(group);group.AddItem(cap)
    points=[(10.5,8.5),(13.5,8.5),(13.5,12.5),(10.5,12.5)]
    for a,z in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(cap);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(court)
        line.SetStart(pcbnew.VECTOR2I_MM(*a));line.SetEnd(pcbnew.VECTOR2I_MM(*z));cap.Add(line)
    chain=cap.GetCourtyard(cap.GetLayer()).COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        guide=pcbnew.PCB_SHAPE(parent);guide.SetShape(pcbnew.SHAPE_T_SEGMENT);guide.SetLayer(opposite)
        guide.SetStart(pcbnew.VECTOR2I(*a));guide.SetEnd(pcbnew.VECTOR2I(*z));guide.SetWidth(150000)
        parent.Add(guide);group.AddItem(guide)
    text=pcbnew.PCB_TEXT(parent);text.SetText(cap.GetReference());text.SetLayer(opposite)
    text.SetMirrored(opposite==pcbnew.B_SilkS);text.SetTextSize(pcbnew.VECTOR2I_MM(1.,1.))
    text.SetTextThickness(150000);text.SetTextPos(cap.GetPosition());text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    parent.Add(text);group.AddItem(text);group.SetLocked(True);cap.SetLocked(False)
    field._save_field_snapshot(parent,source)
    pro=source.with_suffix('.kicad_pro');data=json.loads(pro.read_text())
    data['net_settings']['classes'][0].update(via_diameter=.9,via_drill=.5)
    pro.write_text(json.dumps(data))
    return source,force._uid(group),force._uid(main)


@pytest.mark.parametrize('back',[False,True])
def test_full_compiler_large_pose_preserves_isolated_ports_and_future_demands(tmp_path,back):
    source,gid,main=fixture(tmp_path,back)
    before=source.read_bytes()
    posed,packet=compiler.compile(source,{'RENAMED_MONITOR':[21.,9.,0.],'C8':[24.,10.5,0.]},
        board_hint=HINT,max_shift_mm=24.,allow_owned_locked_escapes=True,rebuild_projected_ground=True,
        reference_group_uuids=[gid],compilation_phase_timeouts_s=[10.,10.,10.])
    assert packet and source.read_bytes()==before
    proof=packet['transport']['rigid_isolated_selected_bypass_supply_components'][0]
    assert len(proof['track_uuids'])==5 and proof['delta_nm']==[12000000,0]
    assert proof['unchanged_full_rail_current_contract']['current_authority']['amps']>0
    assert main not in packet['retired_track_uuids']
    requests=packet['requests'];retained={k:r for k,r in requests.items()if k.startswith('retained:')}
    assert len(retained)==3
    assert sum(r['kind']=='local_supply'for r in requests.values())==1
    assert sum(r['kind']=='ground'for r in requests.values())==2
    for request in retained.values():
        assert request['net']=='+3V3' and request['width_nm'] in(200000,500000)
        at=pcbnew.VECTOR2I(*request['b']['at_nm'])
        assert all(next(t for t in posed.GetTracks()if force._uid(t)==u).GetEffectiveShape(
            proof['layer_id']).Collide(at,0)for u in request['b']['native_uuids'])
    # A separate fresh public compile is the same independent Source
    # reconstruction used by saved receiving; no producer proof is forwarded.
    again,fresh=compiler.compile(source,packet['source_plan']['poses'],board_hint=HINT,
        max_shift_mm=24.,allow_owned_locked_escapes=True,rebuild_projected_ground=True,
        reference_group_uuids=[gid],compilation_phase_timeouts_s=[10.,10.,10.])
    assert fresh['requests']==requests
    assert fresh['transport']['rigid_isolated_selected_bypass_supply_components']==[proof]
    assert not packet['routing_admitted']and not packet['saved_candidate_authorized']


@pytest.mark.parametrize('fault',['partial','delta','retired','width','new_contact'])
def test_projection_never_accepts_partial_or_forged_carried_component(tmp_path,fault):
    source,gid,main=fixture(tmp_path)
    posed,packet=compiler.compile(source,{'RENAMED_MONITOR':[21.,9.,0.],'C8':[24.,10.5,0.]},
        board_hint=HINT,max_shift_mm=24.,allow_owned_locked_escapes=True,rebuild_projected_ground=True,
        reference_group_uuids=[gid],compilation_phase_timeouts_s=[10.,10.,10.])
    parent=pcbnew.LoadBoard(str(source));transport=copy.deepcopy(packet['transport'])
    proof=transport['rigid_isolated_selected_bypass_supply_components'][0]
    uid=proof['track_uuids'][0];row=next(q for q in proof['tracks']if q['uuid']==uid)
    port=dict(at_nm=row['source_nm'][0],layers=[proof['layer_id']],native_uuids=[uid]);retired=set()
    if fault=='partial':proof['track_uuids'].pop();proof['tracks']=[q for q in proof['tracks']if q['uuid']in proof['track_uuids']]
    elif fault=='delta':proof['delta_nm'][0]+=1
    elif fault=='retired':retired.add(uid)
    elif fault=='width':next(t for t in posed.GetTracks()if force._uid(t)==uid).SetWidth(row['width_nm']+1)
    else:track(posed,'+3V3',(22,10),(22,10.8),width=.2,layer=proof['layer_id'])
    with pytest.raises(ValueError):compiler._project_port(parent,posed,port,transport,retired)
