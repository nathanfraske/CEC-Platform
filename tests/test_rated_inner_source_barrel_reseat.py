"""Opt-in actual inner branch scope still owns the full unchanged load."""
from unittest.mock import patch
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_barrel_reseat as reseat
import cec_fab_profile as fab
from test_rated_barrel_reseat import fixture


OPTIONS=dict(max_source_width_mm=1.,max_source_track_mm=16.,
    allow_rated_source_inner_layers=True,max_source_barrel_diameter_mm=1.5,
    max_replacement_width_mm=1.)


def case(tmp_path,quarter=0,prefix='/renamed/'):
    data=fixture(tmp_path,quarter,prefix)
    source,child,cuts,old,new,net,contract=data
    for path,uid in ((source,old),(child,new)):
        b=pcbnew.LoadBoard(str(path));b.SetCopperLayerCount(6)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_VIA' and force._uid(t)==uid:t.SetWidth(1200000)
            elif t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu:
                t.SetLayer(pcbnew.In2_Cu);t.SetWidth(845000)
        field._save_field_snapshot(b,path)
    contract['required_by_layer_mm']={fab.COPPER_LAYER_IDS[int(l)]:.2
        for l in b.GetEnabledLayers().CuStack()}
    contract['required_by_layer_mm']['In2.Cu']=.845
    contract['routing_layers']=['F.Cu','In2.Cu','B.Cu']
    return data


def receive(data,options=None):
    source,child,cuts,old,_,net,contract=data
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        return reseat.receive(source,child,board_hint='synthetic',
            retired_track_uuids=cuts,retired_via_uuids=[old],**(OPTIONS if options is None else options))


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('prefix',['/renamed/','/unrelated/board/'])
def test_rotated_full_inner_supply_and_unchanged_large_barrel_replay(tmp_path,quarter,prefix):
    data=case(tmp_path,quarter,prefix);saved=[p.read_bytes() for p in data[:2]]
    proof=receive(data)
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_proposal']['allow_rated_source_inner_layers']
    assert proof['actual_barrel_reseat_matches'][0]['actual_native_candidate_contact_web'][
        'source_required_local_web_nm']==845000
    assert proof['all_surviving_source_native_partitions_preserved']
    assert not proof['current_authority'] and not proof['barrel_ampacity_qualified']
    assert [p.read_bytes() for p in data[:2]]==saved
    assert not receive(data,{})['ok']


@pytest.mark.parametrize('fault',['source_floor','candidate_floor','source_group','source_face',
    'forbidden_plane','barrel_ceiling','default_inner','source_width_cap','replacement_width_cap',
    'changed_barrel','geometry_move','unknown_current','boolean_option'])
def test_inner_source_scope_never_waives_physical_width_roles_or_source_geometry(tmp_path,fault):
    data=case(tmp_path);source,child,cuts,old,new,net,contract=data
    options=dict(OPTIONS)
    if fault in ('source_floor','source_group','source_face','forbidden_plane'):
        b=pcbnew.LoadBoard(str(source));t=next(i for i in b.GetTracks()
            if i.GetClass()=='PCB_TRACK' and i.GetLayer()==pcbnew.In2_Cu)
        if fault=='source_floor':t.SetWidth(844999)
        elif fault=='source_group':
            g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
        else:
            t.SetLayer(pcbnew.In1_Cu)
            if fault=='forbidden_plane':
                contract['routing_layers'].append('In1.Cu');contract['required_by_layer_mm']['In1.Cu']=.845
                b.Add(pcbnew.NETINFO_ITEM(b,'GND'));z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In1_Cu)
                z.SetNetCode(b.GetNetcodeFromNetname('GND'));z.Outline().NewOutline()
                for point in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(pcbnew.VECTOR2I_MM(*point))
                b.Add(z)
        field._save_field_snapshot(b,source)
    elif fault in ('candidate_floor','changed_barrel','geometry_move'):
        b=pcbnew.LoadBoard(str(child))
        if fault=='candidate_floor':
            next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'
                and t.GetLayer()==pcbnew.In2_Cu).SetWidth(844999)
        else:
            v=next(t for t in b.GetTracks() if force._uid(t)==new)
            if fault=='changed_barrel':v.SetWidth(1300000)
            else:v.SetPosition(pcbnew.VECTOR2I_MM(12,10))
        field._save_field_snapshot(b,child)
    elif fault=='barrel_ceiling':options['max_source_barrel_diameter_mm']=1.
    elif fault=='default_inner':options['allow_rated_source_inner_layers']=False
    elif fault=='source_width_cap':options['max_source_width_mm']=.35
    elif fault=='replacement_width_cap':options['max_replacement_width_mm']=.35
    elif fault=='boolean_option':options['allow_rated_source_inner_layers']=1
    else:contract['current_authority']['amps']=0
    result=receive(data,options)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('value',[True,False,0,-1,2.000001,float('inf'),float('nan'),'1.5'])
def test_barrel_diameter_scope_is_finite_numeric_and_explicit(value):
    with pytest.raises(ValueError):reseat.source_barrel_diameter_mm(value)
