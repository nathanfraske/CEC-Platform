"""Generic source-tail cleanup at exact native alternate taps."""
import math
from unittest import mock
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_rated_branch_spur_rebuild as spur
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,rotation=0,mirror=False,face=pcbnew.F_Cu,fault=None):
    net='/different/%s_%s_%s/SUPPLY'%(rotation,mirror,face)
    def xy(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    contact_x=11 if (fault or '').startswith('early_') else 12
    points=[(5,10),(15,10)]+([(contact_x,10)] if fault in ('retained_land','early_retained_land') else [])
    b=_board([(*xy(p),net) for p in points],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1');ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls)
    def via(board,p):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(p)))
        v.SetNetCode(board.GetNetcodeFromNetname(net));v.SetWidth(1200000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v);return v
    via(b,(5,10))
    old=track(b,net,xy((5,10)),xy((10,10)),layer=face)
    multiedge=fault=='multiedge' or (fault or '').startswith('early_')
    tail=track(b,net,xy((10,10)),xy((12.25,10) if multiedge else (15,10)),layer=face)
    if multiedge:track(b,net,xy((12.25,10)),xy((15,10)),layer=face)
    first,seed=force._uid(old),force._uid(tail)
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');b.Add(g);g.AddItem(tail)
    elif fault in ('retained_barrel','early_retained_barrel'):via(b,(contact_x,10))
    elif fault in ('retained_tee','early_retained_tee'):track(b,net,xy((contact_x,10)),xy((contact_x,12)),layer=face)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    trial=force._copy_family(source,tmp_path/'trial');b=pcbnew.LoadBoard(str(trial))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==first])
    tap=(13,10.01 if fault=='off_center_tap' else 10)
    if fault=='no_free_end':tap=(10,10)
    via(b,tap);incoming=track(b,net,xy((5,10)),xy(tap),layer=pcbnew.In2_Cu,width=.9)
    if fault=='incoming_seed':seed=force._uid(incoming)
    field._save_field_snapshot(b,trial)
    catalog=dict(contracts={net:dict(current_authority=dict(amps=.75,geometry_margin=1.25,
        margin_included=False,source='explicit_synthetic_load_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2,'In2.Cu':.8450747617670971},
        routing_layers=['F.Cu','In2.Cu','B.Cu'])})
    return source,trial,first,seed,net,catalog


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_alternate_native_tap_peels_only_unused_source_tail(tmp_path,rotation,mirror,face):
    source,trial,first,seed,net,catalog=fixture(tmp_path,rotation,mirror,face)
    saved=source.read_bytes();draft=trial.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        plan=spur.plan(source,trial,board_hint='synthetic',retired_track_uuids=[first],
            dangling_track_uuids=[seed],max_replacement_width_mm=1.)
        b=pcbnew.LoadBoard(str(trial));constructed=spur.materialize(b,plan)
        child=force._copy_family(source,tmp_path/'clean');field._save_field_snapshot(b,child)
        proof=rated.receive(source,child,board_hint='synthetic',
            retired_track_uuids=plan['retired_track_uuids'],allow_rated_layer_bridges=True,
            max_replacement_width_mm=1.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved']
    assert plan['additional_retired_track_uuids']==[seed]
    assert len(plan['retained_prefixes'])==1
    prefix=plan['retained_prefixes'][0]
    assert math.dist(prefix['start_nm'],prefix['end_nm'])==2e6
    assert prefix['width_nm']==200000 and prefix['layer_id']==face
    assert constructed['added_track_uuids'] and not plan['new_vias']
    assert not proof['current_authority'] and not plan['release_authority']
    assert source.read_bytes()==saved and trial.read_bytes()==draft


@pytest.mark.parametrize('fault',['retained_land','retained_barrel','retained_tee','group',
    'off_center_tap','no_free_end','incoming_seed','early_retained_land',
    'early_retained_barrel','early_retained_tee'])
def test_an_alternate_tap_never_authorizes_deleting_a_real_source_contact(tmp_path,fault):
    source,trial,first,seed,net,catalog=fixture(tmp_path,fault=fault)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            pytest.raises(ValueError):
        spur.plan(source,trial,board_hint='synthetic',retired_track_uuids=[first],
            dangling_track_uuids=[seed],max_replacement_width_mm=1.)


@pytest.mark.parametrize('rotation',[0,90])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_every_source_edge_in_a_multisegment_spur_is_retyped_and_received(tmp_path,rotation,face):
    source,trial,first,seed,net,catalog=fixture(tmp_path,rotation,True,face,'multiedge')
    saved=source.read_bytes();draft=trial.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        plan=spur.plan(source,trial,board_hint='synthetic',retired_track_uuids=[first],
            dangling_track_uuids=[seed],max_replacement_width_mm=1.)
        b=pcbnew.LoadBoard(str(trial));spur.materialize(b,plan)
        child=force._copy_family(source,tmp_path/'clean');field._save_field_snapshot(b,child)
        proof=rated.receive(source,child,board_hint='synthetic',
            retired_track_uuids=plan['retired_track_uuids'],allow_rated_layer_bridges=True,
            max_replacement_width_mm=1.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved']
    assert len(plan['additional_retired_track_uuids'])==2
    assert seed in plan['additional_retired_track_uuids']
    assert len(plan['retained_prefixes'])==1
    assert math.dist(plan['retained_prefixes'][0]['start_nm'],plan['retained_prefixes'][0]['end_nm'])==2e6
    assert source.read_bytes()==saved and trial.read_bytes()==draft


def test_source_retirement_count_still_bounds_tail_cleanup(tmp_path):
    source,trial,first,seed,net,catalog=fixture(tmp_path)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            pytest.raises(ValueError,match='work_bound'):
        spur.plan(source,trial,board_hint='synthetic',retired_track_uuids=[first],
            dangling_track_uuids=[seed],max_replacement_width_mm=1.,max_retired_tracks=1)
