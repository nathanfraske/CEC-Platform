"""Finite existing-contact proposals cannot create component/stack authority."""
from unittest.mock import patch

import pcbnew
import pytest

import cec_certified_island_access as access


def fixture(*, angle=0, flipped=False, plated=False):
    from test_local_copper_cell import native_cell
    board, fps, internal, external, pad, track = native_cell(names=('RENAMED_A','RENAMED_B'))
    # A whole native-connected island: local aliases, then a remote existing
    # barrel beyond the local witness radius but within the pair route bound.
    track((8,6),(15,6))
    remote = pad('OTHER_COMPONENT',18,8)
    if plated:
        carrier=pad('PLATED_ACCESS',15,6);barrel=next(iter(carrier.Pads()))
        barrel.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        barrel.SetSize(pcbnew.VECTOR2I_MM(1,1))
        barrel.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        barrel.SetLayerSet(pcbnew.LSET.AllCuMask())
    else:
        barrel=pcbnew.PCB_VIA(board);barrel.SetPosition(pcbnew.VECTOR2I_MM(15,6))
        barrel.SetWidth(pcbnew.FromMM(.6));barrel.SetDrill(pcbnew.FromMM(.3))
        barrel.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        barrel.SetNet(internal[0].GetNet());board.Add(barrel)
    origin=pcbnew.VECTOR2I_MM(20,20)
    if flipped:
        for fp in board.GetFootprints():fp.Flip(origin,False)
        for item in board.GetTracks():item.Flip(origin,False)
    if angle:
        for fp in board.GetFootprints():fp.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        for item in board.GetTracks():item.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    first=next(iter(fps[0].Pads()));last=next(iter(remote.Pads()))
    sources=[(p,p.GetPosition().x,p.GetPosition().y)for p in (first,last)]
    return board,sources,barrel,external


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('flipped',[False,True])
@pytest.mark.parametrize('plated',[False,True])
def test_reserved_existing_access_is_same_native_component_and_source_exact(angle,flipped,plated):
    import cec_local_copper_cell as cell
    board,sources,barrel,external=fixture(angle=angle,flipped=flipped,plated=plated)
    before=cell.copper_inventory(board)
    kwargs=dict(limit=3,max_mm=25,max_shift_mm=4,class_width_nm=250000)
    legacy=access.plan(board,sources[0][0].GetNetCode(),sources,**kwargs)
    assert legacy==access.plan(board,sources[0][0].GetNetCode(),sources,
        existing_access_shift_mm=None,**kwargs)
    uid=barrel.m_Uuid.AsString()
    assert all(e['uuid']!=uid for row in legacy['candidates']for e in row['endpoints'])
    # Private native graph, never a cached or net-normalizing graph.
    with patch.object(pcbnew.BOARD,'BuildConnectivity',side_effect=AssertionError('mutation')), \
         patch.object(pcbnew.BOARD,'GetConnectivity',side_effect=AssertionError('cached')):
        got=access.plan(board,sources[0][0].GetNetCode(),sources,
            existing_access_shift_mm=16,**kwargs)
    assert got['candidates'][0]['endpoints'][0]['uuid']==uid
    assert len(got['candidates'])<=3
    assert got['existing_access_tier']['routing_authority'] is False
    assert got['existing_access_tier']['pair_distance_bound_mm']==25
    assert all(e['uuid']!=external.m_Uuid.AsString()for row in got['candidates']for e in row['endpoints'])
    assert cell.copper_inventory(board)==before


@pytest.mark.parametrize('budget',[False,True,0,-1,float('nan'),float('inf'),81,'16'])
def test_invalid_explicit_budget_refuses(budget):
    board,sources,_,_=fixture()
    with pytest.raises(ValueError,match='bounded island'):
        access.plan(board,sources[0][0].GetNetCode(),sources,existing_access_shift_mm=budget)


def test_budgets_stale_source_and_unconnected_same_net_remain_bounded():
    board,sources,barrel,_=fixture();code=sources[0][0].GetNetCode();uid=barrel.m_Uuid.AsString()
    for kwargs in (dict(max_mm=2),dict(existing_access_shift_mm=6)):
        args=dict(limit=3,max_mm=25,max_shift_mm=4,existing_access_shift_mm=16);args.update(kwargs)
        got=access.plan(board,code,sources,**args)
        assert all(e['uuid']!=uid for row in got['candidates']for e in row['endpoints'])
    assert access.plan(board,code,sources,limit=0,existing_access_shift_mm=16)['candidates']==[]
    assert access.plan(board,code,sources,max_items=1,existing_access_shift_mm=16)['refusal']=='island_inventory_budget_exhausted'
    assert access.plan(board,code,[(sources[0][0],0,0),sources[1]],existing_access_shift_mm=16)['refusal']=='source_point_not_live'
    # Move the existing via off all tracks: same net alone is not authority.
    barrel.SetPosition(pcbnew.VECTOR2I_MM(14,7))
    got=access.plan(board,code,sources,max_shift_mm=4,existing_access_shift_mm=16)
    assert all(e['uuid']!=uid for row in got['candidates']for e in row['endpoints'])


def test_nonplated_invalid_annulus_and_partial_stack_are_not_existing_access():
    board,sources,barrel,_=fixture(plated=True)
    assert access._existing_full_stack_contact(board,barrel)
    barrel.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    assert not access._existing_full_stack_contact(board,barrel)
    barrel.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    barrel.SetLayerSet(pcbnew.PAD.SMDMask())
    assert not access._existing_full_stack_contact(board,barrel)
    barrel.SetLayerSet(pcbnew.LSET.AllCuMask())
    barrel.SetDrillSize(pcbnew.VECTOR2I_MM(2,2))
    assert not access._existing_full_stack_contact(board,barrel)
    board,sources,barrel,_=fixture()
    barrel.SetViaType(pcbnew.VIATYPE_BLIND)
    assert not access._existing_full_stack_contact(board,barrel)


def test_partial_enabled_stack_is_not_access_even_with_two_faces():
    board,sources,barrel,_=fixture(plated=True)
    board.SetCopperLayerCount(6)
    assert access._existing_full_stack_contact(board,barrel)
    # A plated pad with outer-face material alone is not proof of access to
    # the complete actual six-layer stack.
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.B_Cu)
    barrel.SetLayerSet(layers)
    assert not access._existing_full_stack_contact(board,barrel)


def test_wrong_net_does_not_gain_existing_access_tier():
    board,sources,barrel,_=fixture();uid=barrel.m_Uuid.AsString()
    other=pcbnew.NETINFO_ITEM(board,'/NOT_THE_ISLAND');board.Add(other);barrel.SetNet(other)
    got=access.plan(board,sources[0][0].GetNetCode(),sources,max_shift_mm=4,existing_access_shift_mm=16)
    assert all(e['uuid']!=uid for row in got['candidates']for e in row['endpoints'])
