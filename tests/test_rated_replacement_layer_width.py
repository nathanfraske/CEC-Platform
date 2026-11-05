"""A thin rated source branch may need a thicker authorized-layer rebuild."""
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
    # Explicit synthetic load catalog, never an inference from real refdes.
    net='/renamed/%s_%s_%s/SUPPLY'%(rotation,mirror,face)
    def pose(at):
        x,y=at[0]-15,at[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return (round(15+x*math.cos(a)-y*math.sin(a),6),
                round(15+x*math.sin(a)+y*math.cos(a),6))
    b=_board([(*pose(p),net) for p in ((5,10),(10,10))],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1')
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    original=track(b,net,pose((5,10)),pose((10,10)),layer=face)
    uid=force._uid(original)
    for xy in ((5,10),(10,10)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*pose(xy)))
        v.SetNetCode(b.GetNetcodeFromNetname(net));v.SetWidth(1200000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'private');b=pcbnew.LoadBoard(str(child))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    track(b,net,pose((5,10)),pose((10,10)),layer=pcbnew.In2_Cu,width=.9)
    field._save_field_snapshot(b,child)
    catalog=dict(contracts={net:dict(
        current_authority=dict(amps=.75,margin_included=False,geometry_margin=1.25,
            source='explicit_synthetic_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2,'In2.Cu':.8450747617670971},
        routing_layers=['F.Cu','In2.Cu','B.Cu'])})
    return source,child,uid,net,catalog


def receive(source,child,uid,catalog,**kwargs):
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        return rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**kwargs)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_full_unchanged_load_width_on_inner_layer_is_explicitly_received(tmp_path,rotation,mirror,face):
    source,child,uid,net,catalog=fixture(tmp_path,rotation,mirror,face)
    saved=source.read_bytes()
    legacy=receive(source,child,uid,catalog)
    assert not legacy['ok'] and 'full_load_planar' in legacy['errors'][0],legacy
    proof=receive(source,child,uid,catalog,max_replacement_width_mm=1.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved']
    assert proof['main_force_copper_poses_and_power_fills_exact']
    assert proof['source_small_branch_eligibility_unchanged']
    assert proof['max_replacement_width_mm']==1.
    assert not proof['rated_replacement_via_uuids']
    assert not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['narrow','ceiling','source_wide','source_inner','group',
    'unauthorized_layer','changed_current','layer_netclass','open','untyped_extra'])
def test_wider_work_scope_never_relaxes_source_load_ownership_or_saved_receiving(tmp_path,fault):
    source,child,uid,net,catalog=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child));options=dict(max_replacement_width_mm=1.)
    edge=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='narrow':edge.SetWidth(845074)
    elif fault=='ceiling':options['max_replacement_width_mm']=.85
    elif fault=='unauthorized_layer':catalog['contracts'][net]['routing_layers']=['F.Cu','B.Cu']
    elif fault=='open':edge.Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='untyped_extra':
        b.Add(pcbnew.NETINFO_ITEM(b,'/OTHER_POWER'))
        track(b,'/OTHER_POWER',(20,20),(22,20),width=1.)
    if fault in ('source_wide','source_inner','group'):
        old=pcbnew.LoadBoard(str(source));t=next(t for t in old.GetTracks() if force._uid(t)==uid)
        if fault=='source_wide':t.SetWidth(500000)
        elif fault=='source_inner':t.SetLayer(pcbnew.In2_Cu)
        else:
            g=pcbnew.PCB_GROUP(old);g.SetName('PROTECTED');old.Add(g);g.AddItem(t)
        field._save_field_snapshot(old,source)
    field._save_field_snapshot(b,child)
    patched=dict(return_value=catalog)
    if fault=='changed_current':
        import copy
        changed=copy.deepcopy(catalog);changed['contracts'][net]['current_authority']['amps']=.7
        patched=dict(side_effect=[catalog,changed])
    with mock.patch.object(rated.topology,'distributed_supply_contracts',**patched), \
            mock.patch.object(rated.fr,'_project_netclass_resolver',return_value=lambda n:
                dict(track_width=.2,track_width_by_layer_mm={'In2.Cu':.95})
                    if fault=='layer_netclass' else dict(track_width=.2)), \
            mock.patch.object(rated.ordinary,'eligible_nets',return_value=set()):
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**options)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('value',[True,False,0,-1,5.001,float('inf'),float('nan'),'1'])
def test_replacement_work_policy_is_finite_explicit_and_not_a_boolean(value):
    with pytest.raises(ValueError,match='replacement_width'):
        rated.replacement_width_mm(value,allow_rated_layer_bridges=True)


def test_widened_ceiling_requires_explicit_layer_bridge_scope():
    with pytest.raises(ValueError,match='replacement_width'):
        rated.replacement_width_mm(1.)


def test_cut_chain_retypes_wider_reconstruction_from_actual_saved_source(tmp_path):
    source,child,uid,net,catalog=fixture(tmp_path)
    phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],
        allow_rated_layer_bridges=True,max_replacement_width_mm=1.)]
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert proof['ok'] and proof['complete'],proof
    assert proof['phase_receiving'][0]['proof']['max_replacement_width_mm']==1.
    assert not proof['current_authority'] and not proof['release_authority']


@pytest.mark.parametrize('bad',[True,.85,6.])
def test_worker_cannot_claim_a_received_wide_layer_without_valid_independent_scope(tmp_path,bad):
    source,child,uid,net,catalog=fixture(tmp_path)
    phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],
        allow_rated_layer_bridges=True,max_replacement_width_mm=bad)]
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('pieces',[9,12,16,24,32])
def test_explicit_segment_budget_receives_a_complete_fragmented_source_branch(tmp_path,pieces):
    source,child,uid,net,catalog=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    retired=[]
    for i in range(pieces):
        t=track(b,net,(5+5*i/pieces,10),(5+5*(i+1)/pieces,10));retired.append(force._uid(t))
    field._save_field_snapshot(b,source)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        legacy=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=retired,
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.)
        proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=retired,
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.,max_retired_tracks=32)
        assert not legacy['ok'] and proof['ok'] and proof['complete'],(legacy,proof)
        phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=retired,
            allow_rated_layer_bridges=True,max_replacement_width_mm=1.,max_retired_tracks=32)]
        full=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert full['ok'] and full['complete'],full
    assert proof['source_proposal']['max_retired_tracks']==32


@pytest.mark.parametrize('value',[True,False,0,-1,33,32.,float('inf'),'32'])
def test_retirement_budget_is_finite_explicit_and_not_a_boolean(value):
    with pytest.raises(ValueError,match='retirement_count'):
        rated.retirement_count(value)
