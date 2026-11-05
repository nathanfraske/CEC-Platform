"""Real refill changes island hashes, never physical Source obligations."""
import time
from unittest.mock import patch

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_force_current as force
import cec_field_coupling as field
import cec_native_partition_pair as paired
import cec_rated_barrel_reseat as reseat
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_rated_barrel_contact_fault_repair import case,receive


def ground_case(tmp_path,quarter=0,face=pcbnew.F_Cu):
    data=case(tmp_path,quarter,prefix=f'/ground-{quarter}-{int(face)}/')
    source,child,cuts,old,new,net,contract=data
    child_routes=pcbnew.LoadBoard(str(child))
    board=pcbnew.LoadBoard(str(source));board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('GROUND_ANCHOR');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.6,1.6));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
    pad.SetLayerSet(pcbnew.LSET.AllCuMask());pad.SetPosition(pcbnew.VECTOR2I_MM(20,15))
    pad.SetNet(board.FindNet('GND'));fp.Add(pad)
    z=pcbnew.ZONE(board);z.SetLayer(face);z.SetNet(board.FindNet('GND'))
    z.Outline().NewOutline()
    for at in ((2,2),(28,2),(28,28),(2,28)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
    board.Add(z);additive._ground_refill(board);field._save_field_snapshot(board,source)
    # Copy the whole Source GND owner/anchor once. Only the exact fixture cut
    # is reconstructed, using already independently created native offers.
    target=force._copy_family(source,tmp_path/'real-Ground-child')
    child_board=pcbnew.LoadBoard(str(target));removed=set(cuts)|{old}
    discard_items(child_board,[t for t in child_board.GetTracks() if force._uid(t) in removed])
    for item in child_routes.GetTracks():
        t=item.Duplicate();child_board.Add(t);t.SetNet(child_board.FindNet(net))
    additive._ground_refill(child_board);field._save_field_snapshot(child_board,target)
    return source,target,cuts,old,new,net,contract


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_regenerated_Ground_antipad_preserves_every_actual_native_component(tmp_path,quarter,face):
    data=ground_case(tmp_path,quarter,face)
    before=[p.read_bytes() for p in data[:2]]
    parent,child=[pcbnew.LoadBoard(str(p)) for p in data[:2]]
    # The old single-board keys really DO differ. That API intentionally
    # refuses changed fill; a barrel-reseat receiver must use paired islands.
    import cec_ordinary_route_receiving as ordinary
    cut=set(data[2])|{data[3]}
    first=ordinary._partition(parent,time.monotonic()+5.,retired_uuids=cut)
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):
        ordinary._partition(child,time.monotonic()+5.,retained_keys=set().union(*first))
    proof=receive(data)
    assert proof['ok'] and proof['complete'],proof
    evidence=proof['paired_native_partition_preservation']
    assert evidence['available'] and evidence['preserved']
    assert evidence['overlap_token_count']>=1 and evidence['exact_positive_native_island_overlap']
    assert not evidence['whole_zone_uuid_connectivity_credit']
    assert proof['all_surviving_source_native_partitions_preserved']
    assert not proof['barrel_ampacity_qualified'] and not proof['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('fault',['split','lost_source_island','changed_zone_face','foreign_net_bridge'])
def test_refill_is_not_permission_to_split_lose_or_teleport_a_Source_ground_island(tmp_path,fault):
    data=ground_case(tmp_path)
    parent=pcbnew.LoadBoard(str(data[0]));child=pcbnew.LoadBoard(str(data[1]))
    zone=next(iter(child.Zones()));shape=zone.GetFilledPolysList(zone.GetLayer()).CloneDropTriangulation()
    cut=pcbnew.SHAPE_POLY_SET();cut.NewOutline()
    for at in ((14,1),(16,1),(16,29),(14,29)):cut.Append(pcbnew.VECTOR2I_MM(*at))
    if fault in ('split','foreign_net_bridge'):
        shape.BooleanSubtract(cut);zone.SetFilledPolysList(zone.GetLayer(),shape)
        zone.SetIsFilled(True);zone.CacheTriangulation(zone.GetLayer())
        if fault=='foreign_net_bridge':
            t=pcbnew.PCB_TRACK(child);t.SetNet(child.FindNet(data[5]));t.SetLayer(zone.GetLayer())
            t.SetStart(pcbnew.VECTOR2I_MM(13,20));t.SetEnd(pcbnew.VECTOR2I_MM(17,20));t.SetWidth(400000);child.Add(t)
    elif fault=='lost_source_island':
        # A positively typed Source island cannot disappear merely because
        # it shares the retained zone owner's UUID with another island.
        source_zone=next(iter(parent.Zones()));source_shape=source_zone.GetFilledPolysList(source_zone.GetLayer()).CloneDropTriangulation()
        source_shape.BooleanSubtract(cut);source_zone.SetFilledPolysList(source_zone.GetLayer(),source_shape)
        source_zone.SetIsFilled(True);source_zone.CacheTriangulation(source_zone.GetLayer())
        # Deliberately malformed/degraded private fill fixtures are not
        # construction products. Read the exact saved failure back below;
        # never loosen the production snapshot writer for a negative case.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(data[0]),parent)
        assert next(iter(pcbnew.LoadBoard(str(data[0])).Zones())).GetFilledPolysList(pcbnew.F_Cu).OutlineCount()>=2
        half=pcbnew.SHAPE_POLY_SET();half.NewOutline()
        for at in ((16,1),(29,1),(29,29),(16,29)):half.Append(pcbnew.VECTOR2I_MM(*at))
        shape.BooleanIntersection(half);zone.SetFilledPolysList(zone.GetLayer(),shape)
        zone.SetIsFilled(True);zone.CacheTriangulation(zone.GetLayer())
    else:zone.SetLayer(pcbnew.B_Cu)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(data[1]),child)
    if fault in ('split','foreign_net_bridge'):
        assert next(iter(pcbnew.LoadBoard(str(data[1])).Zones())).GetFilledPolysList(pcbnew.F_Cu).OutlineCount()>=2
    before=[p.read_bytes() for p in data[:2]]
    proof=receive(data)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('bad',[dict(available=False,preserved=True),
    dict(available=True,preserved=False),dict(available=True),{}])
def test_unknown_or_demoted_paired_result_never_falls_back_to_old_zone_identity(tmp_path,bad):
    data=ground_case(tmp_path)
    with patch.object(paired,'compare',return_value=bad):result=receive(data)
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('name',['compare','_inventory','_positive_overlap'])
def test_typed_chain_cache_cannot_borrow_a_proof_from_a_replaced_native_partition_engine(name):
    assert chain._cache_key([],[],{},'synthetic',[]) is not None
    with patch.object(paired,name):
        assert chain._cache_key([],[],{},'synthetic',[]) is None
