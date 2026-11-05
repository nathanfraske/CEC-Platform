"""Source reach may grow, but every electrical and ownership gate stays."""
from unittest.mock import patch
import math
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
from test_rated_branch_repair import fixture,bridge_fixture
from test_field_proposals import track
from cec_native_items import discard_items


@pytest.mark.parametrize('reach,span', [(12.,16.), (24.,32.)])
@pytest.mark.parametrize('angle,prefix',[(0,'/supply_a/'),(90,'/different/'),(180,'/rail/'),(270,'/last/')])
def test_explicit_source_span_is_not_a_board_or_orientation_exception(tmp_path,angle,prefix,reach,span):
    source,child,uid,net,scalar,catalog=fixture(tmp_path,rotation=angle,prefix=prefix)
    def xy(at):
        a=math.radians(angle);x,y=at[0]-15,at[1]-15
        return pcbnew.VECTOR2I_MM(round(15+x*math.cos(a)-y*math.sin(a),6),
            round(15+x*math.sin(a)+y*math.cos(a),6))
    parent=pcbnew.LoadBoard(str(source))
    edge=next(t for t in parent.GetTracks() if force._uid(t)==uid)
    end=5+reach
    edge.SetEnd(xy((end,10)))
    parent.FindFootprintByReference('X2').SetPosition(xy((end,10)))
    field._save_field_snapshot(parent,source)
    final=pcbnew.LoadBoard(str(child));final.FindFootprintByReference('X2').SetPosition(xy((end,10)))
    old=[t for t in final.GetTracks() if t.GetNetname()==net]
    discard_items(final,old)
    for a,b in (((5,10),(5.5,10.5)),((5.5,10.5),(end-.5,10.5)),((end-.5,10.5),(end,10))):
        t=track(final,net,(0,0),(1,1));t.SetStart(xy(a));t.SetEnd(xy(b))
    field._save_field_snapshot(final,child)
    before=[p.read_bytes() for p in (source,child)]
    with patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        assert not rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])['ok']
        if reach>16:
            assert not rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],max_source_track_mm=16.)['ok']
        accepted=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],max_source_track_mm=span)
        assert accepted['ok'] and accepted['complete'],accepted
        assert accepted['source_proposal']['max_source_track_mm']==span
        assert accepted['restored_source_boundaries'][0]['external_boundary_count']==2
        phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],max_source_track_mm=span)]
        replay=chain.receive(source,child,board_hint='synthetic',phases=phases)
        assert replay['ok'] and replay['complete'],replay
    assert not accepted['source_proposal']['inferred_branch_load'] and not accepted['current_authority']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('span',[0,33,True,None,float('inf'),float('nan'),'16'])
def test_span_is_strict_finite_numeric_policy(tmp_path,span):
    source,child,uid,_,_,catalog=fixture(tmp_path)
    with patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],max_source_track_mm=span)
    assert not proof['ok'] and proof['errors']


@pytest.mark.parametrize('fault',['trunk','group','no_contract','too_long'])
def test_larger_span_cannot_claim_force_copper_or_unknown_load(tmp_path,fault):
    source,child,uid,_,_,catalog=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    t=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='trunk':t.SetWidth(500000)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    elif fault=='too_long':t.SetEnd(pcbnew.VECTOR2I_MM(22,10))
    elif fault=='no_contract':catalog={'contracts':{}}
    field._save_field_snapshot(b,source)
    with patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],max_source_track_mm=16.)
    assert not proof['ok'] and proof['errors']


@pytest.mark.parametrize('span',[16.,24.,32.])
def test_explicit_span_changes_only_finite_source_reach_not_authority(span):
    assert rated.source_span_mm(span)==span
    assert rated.plan.__kwdefaults__['max_source_track_mm']==8.
    assert rated.receive.__kwdefaults__['max_source_track_mm']==8.


def pofv_fixture(tmp_path,diameter=.5,drill=.3):
    source,_,uid,net,scalar,catalog=bridge_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));props=b.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'qualified-local-vias')
    b=pcbnew.LoadBoard(str(child));discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    t=track(b,net,(5,10),(10,10));t.SetLayer(pcbnew.In2_Cu)
    vias=[]
    for xy in ((5,10),(10,10)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy));v.SetWidth(round(diameter*1e6))
        v.SetDrill(round(drill*1e6));v.SetNetCode(b.GetNetcodeFromNetname(net))
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v);vias.append(v)
    rated.fr.group_local_pofv_signal_vias(b,vias)
    field._save_field_snapshot(b,child);rated.additive.bind_local_via_rule(b,child)
    return source,child,uid,catalog


def test_local_via_exception_keeps_full_width_boundary_and_exact_factory_process(tmp_path):
    source,child,uid,catalog=pofv_fixture(tmp_path);saved=source.read_bytes()
    with patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        default=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],allow_rated_layer_bridges=True)
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,allow_qualified_local_vias=True)
        assert proof['ok'],proof['errors']
        assert not default['ok'] and proof['ok'],(default,proof)
        phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,allow_qualified_local_vias=True)]
        replay=chain.receive(source,child,board_hint='synthetic',phases=phases)
        assert replay['ok'] and replay['complete'],replay
    assert len(proof['qualified_local_rated_vias'])==2 and not proof['new_barrel_ampacity_credited']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['small_annulus','native_drill_floor','unowned','profile_absent','partial_pad','no_bridge_mode','nonboolean'])
def test_process_exception_cannot_waive_capacity_geometry_or_ownership(tmp_path,fault):
    # The process may support 0.25 mm, but this native test board explicitly
    # requires 0.30 mm. A POFV rule must not waive the board absolute floor.
    source,child,uid,catalog=pofv_fixture(tmp_path,
        diameter=.35 if fault=='small_annulus' else .5,
        drill=.25 if fault=='native_drill_floor' else .3)
    b=pcbnew.LoadBoard(str(child));v=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA')
    if fault=='unowned':v.Move(pcbnew.VECTOR2I_MM(0,3))
    elif fault=='partial_pad':v.Move(pcbnew.VECTOR2I_MM(.25,0))
    elif fault=='profile_absent':
        for path in (source,child):
            item=pcbnew.LoadBoard(str(path));props=item.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l'
            item.SetProperties(props);field._save_field_snapshot(item,path)
        b=pcbnew.LoadBoard(str(child))
    field._save_field_snapshot(b,child)
    with patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=fault!='no_bridge_mode',
            allow_qualified_local_vias=1 if fault=='nonboolean' else True)
    assert not proof['ok'] and proof['errors'],proof
