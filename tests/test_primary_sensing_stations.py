"""Primary sensing repair carries the already guarded complete native station."""
import copy
import math

import pytest

import cec_terminal_range as reach
import cec_placement_dependencies as dependencies
from test_terminal_range import native_fixture
from test_early_terminal_reach import bound_craft


def station_fixture(tmp_path,flipped=False):
    import pcbnew
    source,board,candidate,rows,details=native_fixture(tmp_path,flipped)
    owner_pad=next(p for p in board.FindFootprintByReference('owner').Pads()
                   if p.GetNumber()=='7')
    for ref,position,net in [('detector',(33,13),'renamed_a'),
                             ('detector_bypass',(34,15),'supply')]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*position))
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,.5));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(*position));fp.Add(pad);board.Add(fp)
        if flipped:fp.Flip(fp.GetPosition(),False)
        candidate.P[ref]=(*position,fp.GetOrientationDegrees())
        if flipped:candidate.back_refs.add(ref)
    pcbnew.SaveBoard(str(source),board,True)
    craft=bound_craft(source,candidate,rows,details)
    craft['decoupler']['details'].append(dict(status='assigned',owner_ref='detector',
                                             cap_ref='detector_bypass'))
    point=owner_pad.GetPosition()
    craft['detection_cell']=dict(ok=True,details=[dict(refs=['owner','detector'],
        net='renamed_a',distance_mm=math.dist((point.x/1e6,point.y/1e6),(33,13)),limit_mm=8.,
        terminal_pairs=[[dict(ref='owner',pad='7',net='renamed_a'),
                         dict(ref='detector',pad='1',net='renamed_a')]])])
    return source,candidate,craft


@pytest.mark.parametrize('flipped',[False,True])
def test_primary_native_repair_keeps_detector_and_all_bypasses_rigid(tmp_path,flipped):
    source,candidate,craft=station_fixture(tmp_path,flipped)
    before=source.read_bytes();poses=copy.deepcopy(candidate.P)
    context=dependencies.from_board(source,craft=craft)
    assert context['ok'],context
    moves=reach.from_craft_evidence(candidate,craft,dependency_context=context)
    assert moves
    for move in moves:
        assert set(move['placements'])=={'owner','bypass','detector','detector_bypass'}
        assert dependencies.check_positions(context,dict(candidate.P,**move['placements']))['ok']
        for left in move['placements']:
            for right in move['placements']:
                assert math.dist(move['placements'][left][:2],move['placements'][right][:2])==pytest.approx(
                    math.dist(poses[left][:2],poses[right][:2]))
    assert source.read_bytes()==before and candidate.P==poses


@pytest.mark.parametrize('fault',['fixed_detector','fixed_detector_bypass','wrong_hash',
    'stale_native_pose','unbound_context','missing_group_member'])
def test_incomplete_or_unbound_station_never_falls_back_to_split_cell(tmp_path,fault):
    source,candidate,craft=station_fixture(tmp_path)
    context=dependencies.from_board(source,craft=craft);fixed=[]
    if fault=='fixed_detector':fixed=['detector']
    elif fault=='fixed_detector_bypass':fixed=['detector_bypass']
    elif fault=='wrong_hash':context['board_sha256']='0'*64
    elif fault=='stale_native_pose':context['relation_guard']['positions']['detector']=(1,1,0)
    elif fault=='unbound_context':context.pop('relation_guard')
    else:context['groups'].append(('owner','missing'))
    assert not reach.from_craft_evidence(candidate,craft,dependency_context=context,immutable=fixed)


def test_production_reuses_exact_round_dependency_context():
    import inspect
    import cec_synth_pipeline as synth
    assert 'dependency_context=station_context' in inspect.getsource(synth.repair_placement_craft)
