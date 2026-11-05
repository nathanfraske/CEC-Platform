"""Synthetic immutable budget catalog; native contacts and replay are real."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_barrel_reseat as reseat
import cec_fab_profile as fab
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,prefix='/fixture/',move_mm=.2):
    net=prefix+'SUPPLY'
    def pose(at):
        x,y=at[0]-15,at[1]-15
        for _ in range(quarter):x,y=-y,x
        return 15+x,15+y
    b=_board([(*pose(p),net) for p in ((6,10),(14,10))],edge=(0,0,30,30))
    ds=b.GetDesignSettings();ds.m_MinThroughDrill=300000
    ds.m_ViasMinSize=600000;ds.m_ViasMinAnnularWidth=150000
    for f in b.GetFootprints():
        for p in f.Pads():
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
            p.SetLayerSet(pcbnew.LSET.AllCuMask())
    def via(board,at):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(*pose(at)))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(board.GetNetcodeFromNetname(net));board.Add(v)
        return v
    old=via(b,(10,10))
    cuts=[track(b,net,pose((6,10)),pose((10,10)),width=.2),
          track(b,net,pose((10,10)),pose((14,10)),layer=pcbnew.B_Cu,width=.2)]
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'child');c=pcbnew.LoadBoard(str(child))
    cut_ids=[force._uid(t) for t in cuts];old_uid=force._uid(old)
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in set(cut_ids+[old_uid])])
    new=via(c,(10+move_mm,10));new_uid=force._uid(new)
    track(c,net,pose((6,10)),pose((10+move_mm,10)),width=.2)
    track(c,net,pose((10+move_mm,10)),pose((14,10)),layer=pcbnew.B_Cu,width=.2)
    field._save_field_snapshot(c,child)
    contract=dict(net=net,current_authority=dict(amps=.5,margin_included=True,
        geometry_margin=1.,source='component_power_budget'),
        required_by_layer_mm={fab.COPPER_LAYER_IDS[int(l)]:.2 for l in b.GetEnabledLayers().CuStack()},
        routing_layers=['F.Cu','B.Cu'],clearance_mm=.2)
    return source,child,cut_ids,old_uid,new_uid,net,contract


def receive(data,**scope):
    source,child,cuts,old,new,net,contract=data
    authority=dict(contracts={net:contract},refusals={})
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',return_value=authority):
        return reseat.receive(source,child,board_hint='synthetic',retired_track_uuids=cuts,
            retired_via_uuids=[old],timeout_s=10.,**scope)


def two_barrel_fixture(tmp_path,quarter,prefix,*,ambiguous=False):
    net=prefix+'SUPPLY'
    def pose(at):
        x,y=at[0]-15,at[1]-15
        for _ in range(quarter):x,y=-y,x
        return 15+x,15+y
    b=_board([(*pose(p),net) for p in ((6,10),(16,10))],edge=(0,0,30,30))
    ds=b.GetDesignSettings();ds.m_MinThroughDrill=300000
    ds.m_ViasMinSize=600000;ds.m_ViasMinAnnularWidth=150000
    for fp in b.GetFootprints():
        for p in fp.Pads():
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
            p.SetLayerSet(pcbnew.LSET.AllCuMask())
    def via(board,at,uid):
        v=pcbnew.PCB_VIA(board);v.m_Uuid.Clone(pcbnew.KIID(uid))
        v.SetPosition(pcbnew.VECTOR2I_MM(*pose(at)));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNetCode(board.GetNetcodeFromNetname(net));board.Add(v);return v
    # The right source sorts first, with two local candidates. Only the
    # LEFT source can force the unique full assignment in the positive case.
    old=[via(b,(8,10),'f0000000-0000-4000-8000-000000000001'),
         via(b,(12,10),'00000000-0000-4000-8000-000000000002')]
    edges=[track(b,net,pose((6,10)),pose((8,10)),width=.2),
           track(b,net,pose((8,10)),pose((12,10)),layer=pcbnew.B_Cu,width=.2),
           track(b,net,pose((12,10)),pose((16,10)),width=.2)]
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'child');c=pcbnew.LoadBoard(str(child))
    cuts=[force._uid(t) for t in edges];barrels=[force._uid(v) for v in old]
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in set(cuts+barrels)])
    first,last=(10,11) if ambiguous else (9,14)
    via(c,(first,10),'10000000-0000-4000-8000-000000000003')
    via(c,(last,10),'20000000-0000-4000-8000-000000000004')
    track(c,net,pose((6,10)),pose((first,10)),width=.2)
    track(c,net,pose((first,10)),pose((last,10)),layer=pcbnew.B_Cu,width=.2)
    track(c,net,pose((last,10)),pose((16,10)),width=.2)
    field._save_field_snapshot(c,child)
    contract=dict(net=net,current_authority=dict(amps=.5,margin_included=True,
        geometry_margin=1.,source='component_power_budget'),
        required_by_layer_mm={fab.COPPER_LAYER_IDS[int(l)]:.2 for l in b.GetEnabledLayers().CuStack()},
        routing_layers=['F.Cu','B.Cu'],clearance_mm=.2)
    return source,child,cuts,barrels,net,contract


@pytest.mark.parametrize('quarter,prefix',[(0,'/pair-a/'),(1,'/pair-renamed/'),(2,'/pair-nested/'),(3,'/pair-other/')])
@pytest.mark.parametrize('ambiguous',[False,True])
def test_only_unique_complete_two_barrel_assignment_is_received(tmp_path,quarter,prefix,ambiguous):
    source,child,cuts,barrels,net,contract=two_barrel_fixture(tmp_path,quarter,prefix,ambiguous=ambiguous)
    before=[p.read_bytes() for p in (source,child)]
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        result=reseat.receive(source,child,board_hint='synthetic',retired_track_uuids=cuts,
            retired_via_uuids=barrels,timeout_s=10.,max_reseat_mm=4. if ambiguous else 3.)
    assert result['ok'] is not ambiguous,result
    if ambiguous:
        assert 'exact_local_barrel_identity_or_geometry_ambiguous' in result['errors'][0]
    else:
        assert result['complete'] and result['unique_complete_barrel_assignment_verified']
        assert result['all_surviving_source_native_partitions_preserved']
        assert not result['barrel_ampacity_qualified'] and not result['release_authority']
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('quarter,prefix',[(0,'/a/'),(1,'/renamed/'),(2,'/different/'),(3,'/nested/')])
def test_rotated_renamed_exact_rated_barrel_reseat_preserves_full_load_and_source(tmp_path,quarter,prefix):
    data=fixture(tmp_path,quarter,prefix);before=[p.read_bytes() for p in data[:2]]
    result=receive(data)
    assert result['ok'] and result['complete'],result
    assert result['all_surviving_source_native_partitions_preserved']
    assert result['actual_barrel_reseat_matches'][0]['distance_nm']==200000
    assert not result['barrel_ampacity_qualified'] and not result['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('fault',['new_drill','new_diameter','long_move','additional_via','wrong_net',
    'lost_face','lost_branch','under_width','source_group','source_unattached','unknown_budget','below_process'])
def test_rated_barrel_reseat_refuses_geometry_or_ownership_shortcuts(tmp_path,fault):
    data=fixture(tmp_path);source,child,cuts,old,new,net,contract=data
    c=pcbnew.LoadBoard(str(child));items={force._uid(t):t for t in c.GetTracks()};v=items[new]
    if fault=='new_drill':v.SetDrill(200000)
    elif fault=='new_diameter':v.SetWidth(700000)
    elif fault=='long_move':v.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    elif fault=='additional_via':
        x=v.Duplicate();x.m_Uuid.Clone(pcbnew.KIID());x.SetPosition(pcbnew.VECTOR2I_MM(20,20));c.Add(x)
    elif fault=='wrong_net':
        c.Add(pcbnew.NETINFO_ITEM(c,'OTHER'));v.SetNetCode(c.GetNetcodeFromNetname('OTHER'))
        v.SetPosition(pcbnew.VECTOR2I_MM(10.2,12))
    elif fault=='lost_face':
        v.SetViaType(pcbnew.VIATYPE_BLIND);v.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=='lost_branch':
        discard_items(c,[t for t in c.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu])
    elif fault=='under_width':next(t for t in c.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(199999)
    elif fault in ('source_group','source_unattached','below_process'):
        b=pcbnew.LoadBoard(str(source));src=next(t for t in b.GetTracks() if force._uid(t)==old)
        if fault=='source_group':
            g=pcbnew.PCB_GROUP(b);b.Add(g);g.SetName('owned');g.AddItem(src)
        elif fault=='source_unattached':src.SetPosition(pcbnew.VECTOR2I_MM(20,20))
        else:src.SetDrill(200000)
        field._save_field_snapshot(b,source)
    elif fault=='unknown_budget':contract['required_by_layer_mm']['B.Cu']=.36
    field._save_field_snapshot(c,child)
    result=receive(data)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('vias',[[],['a','a'],['a','b','c'],True])
def test_rated_barrel_scope_is_exact_and_bounded(tmp_path,vias):
    data=fixture(tmp_path);source,child,cuts,old,new,net,contract=data
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
        return_value=dict(contracts={net:contract},refusals={})):
        result=reseat.receive(source,child,board_hint='synthetic',retired_track_uuids=cuts,retired_via_uuids=vias)
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('quarter,prefix',[(0,'/another/'),(1,'/renamed/'),(2,'/nested/'),(3,'/unrelated/')])
def test_explicit_owned_crossing_reconstruction_keeps_legacy_default_and_full_native_receiving(tmp_path,quarter,prefix):
    data=fixture(tmp_path,quarter,prefix,move_mm=3.)
    before=[p.read_bytes() for p in data[:2]]
    refused=receive(data)
    assert not refused['ok'] and 'exact_local_barrel_identity_or_geometry_ambiguous' in refused['errors'][0]
    result=receive(data,max_reseat_mm=3.5)
    assert result['ok'] and result['complete'],result
    assert result['max_reseat_mm']==3.5 and result['all_surviving_source_native_partitions_preserved']
    assert not result['barrel_ampacity_qualified'] and not result['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before
    data[-1]['required_by_layer_mm']['B.Cu']=.21
    refused=receive(data,max_reseat_mm=3.5)
    assert not refused['ok'], 'Movement scope must not authorize an undersized source branch'


@pytest.mark.parametrize('quarter,prefix',[(0,'/long-a/'),(1,'/long-renamed/'),(2,'/long-nested/'),(3,'/long-other/')])
def test_explicit_whole_branch_reseat_preserves_geometry_current_and_defaults(tmp_path,quarter,prefix):
    data=fixture(tmp_path,quarter,prefix,move_mm=10.)
    before=[p.read_bytes() for p in data[:2]]
    assert not receive(data)['ok']
    assert not receive(data,max_reseat_mm=8.)['ok']
    result=receive(data,max_reseat_mm=32.)
    assert result['ok'] and result['complete'],result
    assert result['actual_barrel_reseat_matches'][0]['distance_nm']==10000000
    assert result['all_surviving_source_native_partitions_preserved']
    assert not result['barrel_ampacity_qualified'] and not result['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before
    data[-1]['required_by_layer_mm']['B.Cu']=.21
    assert not receive(data,max_reseat_mm=32.)['ok'], 'A longer work scope must not lower the full-load floor'


@pytest.mark.parametrize('reach',[True,0,-1,32.001,float('inf'),float('nan'),None,'4'])
def test_explicit_crossing_reseat_scope_rejects_unbounded_or_untyped_values(tmp_path,reach):
    result=receive(fixture(tmp_path),max_reseat_mm=reach)
    assert not result['ok'] and 'bounded_explicit_rated_reseat_distance_required' in result['errors'][0]
