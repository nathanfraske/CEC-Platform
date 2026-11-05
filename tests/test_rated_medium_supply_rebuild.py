"""Explicit finite medium-supply scope keeps aggregate domains excluded."""
import math
from unittest import mock
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,rotation=0,mirror=False,face=pcbnew.F_Cu):
    net='/renamed/%s_%s_%s/DISTRIBUTED_LOAD'%(rotation,mirror,face)
    def xy(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*xy(p),net) for p in ((5,10),(10,10))],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1')
        ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls)
    old=track(b,net,xy((5,10)),xy((10,10)),layer=face,width=.5);uid=force._uid(old)
    for point in ((5,10),(10,10)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)))
        v.SetNetCode(b.GetNetcodeFromNetname(net));v.SetWidth(1200000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'private');b=pcbnew.LoadBoard(str(child))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    track(b,net,xy((5,10)),xy((10,10)),layer=other,width=.5)
    field._save_field_snapshot(b,child)
    catalog=dict(contracts={net:dict(current_authority=dict(amps=3.,geometry_margin=1.25,
        margin_included=False,source='explicit_synthetic_load_catalog'),
        required_by_layer_mm={'F.Cu':.4773698,'B.Cu':.4773698,'In2.Cu':5.719034},
        routing_layers=['F.Cu','In2.Cu','B.Cu'])})
    return source,child,uid,net,catalog


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_complete_source_medium_supply_has_explicit_bounded_reconstruction_scope(tmp_path,rotation,mirror,face):
    source,child,uid,net,catalog=fixture(tmp_path,rotation,mirror,face)
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        legacy=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.)
        assert not legacy['ok'],legacy
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.,max_source_width_mm=1.)
        phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.,max_source_width_mm=1.)]
        composed=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert proof['ok'] and proof['complete'] and composed['ok'] and composed['complete'],(proof,composed)
    assert proof['source_distributed_load_ownership_unchanged']
    assert not proof['source_small_branch_eligibility_unchanged']
    assert proof['all_surviving_native_partitions_preserved']
    assert proof['main_force_copper_poses_and_power_fills_exact']
    assert not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['source_below_floor','source_above_ceiling','source_group',
    'source_inner','domain_owned','incoming_below_floor','inner_insufficient','changed_current'])
def test_medium_work_scope_is_not_an_aggregate_force_or_underrated_route_waiver(tmp_path,fault):
    source,child,uid,net,catalog=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));edge=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='source_below_floor':edge.SetWidth(477369)
    elif fault=='source_above_ceiling':edge.SetWidth(1000001)
    elif fault=='source_inner':edge.SetLayer(pcbnew.In2_Cu)
    elif fault=='source_group':
        group=pcbnew.PCB_GROUP(b);group.SetName('OTHER_OWNER');b.Add(group);group.AddItem(edge)
    field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(child));edge=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='incoming_below_floor':edge.SetWidth(477369)
    elif fault=='inner_insufficient':edge.SetLayer(pcbnew.In2_Cu);edge.SetWidth(1000000)
    field._save_field_snapshot(b,child)
    options=dict(return_value=catalog)
    if fault=='domain_owned':options=dict(return_value=dict(contracts={},refused={net:'aggregate_current_domain_owned'}))
    elif fault=='changed_current':
        import copy
        changed=copy.deepcopy(catalog);changed['contracts'][net]['current_authority']['amps']=2.5
        options=dict(side_effect=[catalog,changed])
    with mock.patch.object(rated.topology,'distributed_supply_contracts',**options):
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_source_width_mm=1.,max_replacement_width_mm=1.)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('value',[True,False,0,-1,1.000001,float('inf'),float('nan'),'1'])
def test_source_width_work_scope_is_finite_numeric_and_explicit(value):
    with pytest.raises(ValueError,match='source_width'):
        rated.source_width_mm(value)
