"""Exact Source-owned fine dogbones must survive independent saved receiving."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_existing_local_pofv_pad_rule as rule
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as ground
from test_existing_local_pofv_pad_rule import case


def fixture(tmp_path,angle=0,face=pcbnew.F_Cu):
    board,source,pad=case(tmp_path,angle,face)
    other=next(p for f in board.GetFootprints() for p in f.Pads() if p.GetNumber()=='2')
    edge=pcbnew.PCB_TRACK(board);edge.SetLayer(face);edge.SetNet(pad.GetNet());edge.SetWidth(200000)
    edge.SetStart(pad.GetPosition());edge.SetEnd(other.GetPosition());board.Add(edge)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(board);zone.SetLayer(layer);zone.SetNet(pad.GetNet());outline=zone.Outline();outline.NewOutline()
        for xy in ((1,1),(39,1),(39,39),(1,39)):outline.Append(*[round(v*1e6) for v in xy])
        board.Add(zone)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    dx,dy=((0,-750000),(-750000,0),(0,750000),(750000,0))[angle//90]
    at=list(pad.GetPosition()+pcbnew.VECTOR2I(dx,dy))
    args=dict(board_hint='synthetic',pad_uuid=force._uid(pad),reach_mm=1.,
        use_existing_local_pad_rule=True,dogbone_position_nm=at)
    return board,source,pad,args


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_new_local_dogbone_shortens_a_real_return_with_no_changed_source_copper_or_rules(tmp_path,angle,face):
    board,source,pad,args=fixture(tmp_path,angle,face);raw=source.read_bytes();sidecars=force._sidecars(source)
    q=ground.plan(source,**args)
    assert q['source_return_witness_mm']==pytest.approx(2.2)
    assert q['dogbone_position_nm']==args['dogbone_position_nm']
    assert len(q['ops'])==2 and q['ops'][0][0]=='trk' and q['ops'][1][0]=='via'
    child=Path(ground.write_private(q,tmp_path/'short-local-dogbone')['candidate'])
    received=ground.receive(source,child,**args)
    assert received['ok'] and received['complete'],received['errors']
    assert received['saved_return_witness_mm']==pytest.approx(.75)
    assert received['shortened_return_witness_mm']==pytest.approx(1.45)
    assert received['all_source_known_returns']['ok'] and received['every_source_native_partition_identical']
    assert not received['current_qualified'] and not received['fab_ready'] and not received['release_authority']
    assert source.read_bytes()==raw and force._sidecars(source)==sidecars


@pytest.mark.parametrize('fault',['bool_coordinate','float_coordinate','too_far',
    'missing_coordinate','extra_coordinate','noncanonical','in_pad','partial_pad','foreign',
    'track_root_option','missing_rule'])
def test_exact_dogbone_geometry_cannot_be_a_floor_or_copper_waiver(tmp_path,fault):
    board,source,pad,args=fixture(tmp_path)
    if fault=='bool_coordinate':args['dogbone_position_nm'][0]=True
    elif fault=='float_coordinate':args['dogbone_position_nm'][0]=float(args['dogbone_position_nm'][0])
    elif fault=='too_far':args['dogbone_position_nm'][1]-=1000000
    elif fault=='missing_coordinate':args['dogbone_position_nm'].pop()
    elif fault=='extra_coordinate':args['dogbone_position_nm'].append(0)
    elif fault=='noncanonical':args['dogbone_position_nm'][0]+=1
    elif fault=='in_pad':args['dogbone_position_nm']=list(pad.GetPosition())
    elif fault=='partial_pad':args['dogbone_position_nm']=list(pad.GetPosition()+pcbnew.VECTOR2I(0,-250000))
    elif fault=='foreign':
        t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet('obstruction'));t.SetWidth(200000);t.SetLayer(pcbnew.In3_Cu)
        at=pcbnew.VECTOR2I(*args['dogbone_position_nm']);t.SetStart(at-pcbnew.VECTOR2I(500000,0))
        t.SetEnd(at+pcbnew.VECTOR2I(500000,0));board.Add(t);field._save_field_snapshot(board,source)
    elif fault=='track_root_option':args['prefer_source_track_root']=True
    else:source.with_suffix('.kicad_dru').unlink()
    raw=source.read_bytes()
    with pytest.raises(ValueError):ground.plan(source,**args)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['barrel_position','stub_width','stub_layer','membership','source_trace','extra_trace'])
def test_saved_completion_rejects_changed_copper_membership_and_source_delta(tmp_path,fault):
    board,source,pad,args=fixture(tmp_path);q=ground.plan(source,**args)
    private=ground.construct(q);old={force._uid(t) for t in board.GetTracks()}
    via=next(t for t in private.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t) not in old)
    edge=next(t for t in private.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t) not in old)
    if fault=='barrel_position':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='stub_width':edge.SetWidth(199999)
    elif fault=='stub_layer':edge.SetLayer(pcbnew.B_Cu)
    elif fault=='membership':next(g for g in private.Groups() if g.GetName()==rule.GROUP).RemoveItem(via)
    elif fault=='source_trace':next(t for t in private.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t) in old).Move(pcbnew.VECTOR2I(1,0))
    else:
        extra=pcbnew.PCB_TRACK(private);extra.SetNet(pad.GetNet());extra.SetWidth(200000)
        extra.SetStart(pcbnew.VECTOR2I_MM(3,3));extra.SetEnd(pcbnew.VECTOR2I_MM(4,3));private.Add(extra)
    additive._ground_refill(private);child=force._copy_family(source,tmp_path/'bad-child');field._save_field_snapshot(private,child)
    received=ground.receive(source,child,**args)
    assert not received['ok'] and not received['complete'] and received['errors']


def test_dogbone_constructor_rederives_the_whole_plan_not_a_worker_point(tmp_path):
    board,source,pad,args=fixture(tmp_path);q=ground.plan(source,**args);q=copy.deepcopy(q)
    q['dogbone_position_nm'][0]+=1
    with pytest.raises(ValueError,match='explicit_source_local_ground_dogbone_is_not_native_clear'):
        ground.construct(q)


def test_dogbone_constructor_rejects_forged_copper_even_with_unchanged_valid_point(tmp_path):
    board,source,pad,args=fixture(tmp_path);q=copy.deepcopy(ground.plan(source,**args))
    q['ops'][0][3]-=1
    with pytest.raises(ValueError,match='stale_or_forged'):ground.construct(q)
