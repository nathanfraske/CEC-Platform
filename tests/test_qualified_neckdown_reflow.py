"""Qualified escape shortening is literal Source replay, not a group waiver."""
import json
import pcbnew
import pytest
import cec_qualified_neckdown_reflow as reflow
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
from cec_native_items import discard_items
from test_pad_mediated_neckdown_throat import fixture
from test_smd_macro_transport import inventory


def source(tmp_path,*,fault=None,quarter=0,back=False):
    b,prefix=fixture();net=prefix.GetNet();discard_items(b,[prefix])
    points=[(9.6,10),(9.6,10.3),(9.8,10.3),(9.8,10)]
    group=pcbnew.PCB_GROUP(b);group.SetName('not endpoint scope' if fault=='group' else fr.ENDPOINT_NECKDOWN_GROUP);b.Add(group)
    ids=[]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);t.SetLocked(True);b.Add(t);group.AddItem(t);ids.append(force._uid(t))
    if fault=='side_contact':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(9.6,10.3));t.SetEnd(pcbnew.VECTOR2I_MM(9.3,10.3))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);b.Add(t)
    plan=dict(track_uuids=ids,vertices_nm=[[9600000,10000000],[9700000,10000000],[9750000,10000000],[9800000,10000000]])
    origin=pcbnew.VECTOR2I_MM(10,10);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    for fp in b.GetFootprints():fp.Rotate(origin,angle)
    for t in b.GetTracks():t.Rotate(origin,angle)
    for at in plan['vertices_nm']:
        x,y=at[0]-10000000,at[1]-10000000
        for _ in range(quarter):x,y=y,-x
        at[:]=[x+10000000,y+10000000]
    if back:
        layers=pcbnew.LSET()
        for layer in (pcbnew.B_Cu,pcbnew.B_Mask,pcbnew.B_Paste):layers.AddLayer(layer)
        for fp in b.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():p.SetLayerSet(layers)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu if t.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(name='Default',track_width=1.,clearance=.15)]))))
    return path,pcbnew.LoadBoard(str(path)),plan


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_shorter_source_locked_chain_keeps_every_native_contact_and_replays_exactly(tmp_path,quarter,back):
    path,b,plan=source(tmp_path,quarter=quarter,back=back);before=inventory(b)
    proof=reflow.apply(path,b,board_hint='opaque_synthetic',**plan)
    assert proof['source_length_mm']>.79 and proof['candidate_length_mm']==.2
    assert proof['every_original_native_partition_preserved'] and not proof['routing_admitted']
    assert set(before)==set(inventory(b)) and all(t.IsLocked() for t in b.GetTracks() if force._uid(t) in plan['track_uuids'])
    target=force._copy_family(path,tmp_path/'child');field._save_field_snapshot(b,target)
    received=reflow.receive(path,target,plan,board_hint='opaque_synthetic')
    assert received['ok'] and received['exact_saved_source_reconstruction'] and not received['current_qualified']


@pytest.mark.parametrize('fault',['group','side_contact','source_width','angle','longer','lost_land','order','board_property'])
def test_false_scope_noncanonical_or_lost_contact_refuses_without_mutation(tmp_path,fault):
    path,b,plan=source(tmp_path,fault=fault)
    if fault=='source_width':next(t for t in b.GetTracks() if force._uid(t)==plan['track_uuids'][0]).SetWidth(210000)
    if fault=='angle':plan['vertices_nm'][1][1]+=1
    if fault=='longer':plan['vertices_nm'][1:3]=[[9600000,11000000],[9800000,11000000]]
    if fault=='lost_land':plan['vertices_nm'][0]=[9300000,10000000]
    if fault=='order':plan['track_uuids'][0],plan['track_uuids'][1]=plan['track_uuids'][1],plan['track_uuids'][0]
    if fault=='board_property':
        props=b.GetProperties();props['UNRELATED_SOURCE_PROPERTY']='changed';b.SetProperties(props)
    before=inventory(b)
    with pytest.raises(ValueError):reflow.apply(path,b,board_hint='opaque_synthetic',**plan)
    assert inventory(b)==before


@pytest.mark.parametrize('fault',['footprint','board_property'])
def test_saved_receiver_refuses_unrelated_source_geometry(tmp_path,fault):
    path,b,plan=source(tmp_path);reflow.apply(path,b,board_hint='opaque_synthetic',**plan)
    if fault=='footprint':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    else:
        props=b.GetProperties();props['UNRELATED_SOURCE_PROPERTY']='changed';b.SetProperties(props)
    target=force._copy_family(path,tmp_path/'child');field._save_field_snapshot(b,target)
    proof=reflow.receive(path,target,plan,board_hint='opaque_synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']
