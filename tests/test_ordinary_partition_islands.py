"""Ordinary retained partitions must retain physical islands, never owners."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_native_fill_geometry as fill
import cec_ordinary_route_receiving as ordinary
from test_native_zone_islands import fixture


def track(board,net,start,end,face=pcbnew.F_Cu):
    item=pcbnew.PCB_TRACK(board);item.SetNet(net);item.SetLayer(face)
    item.SetWidth(200000);item.SetStart(pcbnew.VECTOR2I(*start));item.SetEnd(pcbnew.VECTOR2I(*end))
    board.Add(item);return item


def clone(board,tmp_path):
    path=tmp_path/'partition.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    return pcbnew.LoadBoard(str(path))


def retained(parent,child,retired):
    first=ordinary._partition(parent,time.monotonic()+5.,retired_uuids={force._uid(retired)})
    last=ordinary._partition(child,time.monotonic()+5.,retained_keys=set().union(*first))
    return all(any(p<=q for q in last)for p in first)


@pytest.mark.parametrize('replacement',['absent','wrong_face','third_island','true_retention'])
def test_source_bridge_cannot_be_replaced_by_zone_owner_alias(tmp_path,replacement):
    parent,zone=fixture()
    # Three literal islands under one zone owner; only the first two were
    # originally joined. A replacement reaching the third is not retention.
    shape=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    third=fill.reconstruct([[[[12000000,0],[16000000,0],[16000000,4000000],[12000000,4000000]]]],time.monotonic()+5.)
    shape.Append(third);zone.Outline().RemoveAllContours();zone.Outline().Append(shape)
    zone.SetFilledPolysList(pcbnew.F_Cu,shape);zone.SetIsFilled(True)
    old=track(parent,zone.GetNet(),(500000,500000),(6500000,500000))
    child=clone(parent,tmp_path)
    item=next(t for t in child.GetTracks()if force._uid(t)==force._uid(old));child.Remove(item)
    if replacement in ('wrong_face','true_retention'):
        track(child,child.FindNet('GND'),(500000,500000),
            (6500000,500000),
            pcbnew.B_Cu if replacement=='wrong_face'else pcbnew.F_Cu)
    # Route around island2 so no incidental real copper retains its contact.
    if replacement=='third_island':
        for a,b in [((500000,500000),(500000,5000000)),((500000,5000000),(12500000,5000000)),((12500000,5000000),(12500000,500000))]:
            track(child,child.FindNet('GND'),a,b)
    assert retained(parent,child,old)==(replacement=='true_retention')


def test_hole_cannot_restore_retained_contact(tmp_path):
    parent,zone=fixture(hole=True)
    # The isolated conductor sits in the true void. Only the retired edge
    # made it part of island1, so owner-wide zone connectivity would lie.
    track(parent,zone.GetNet(),(2000000,2000000),(2100000,2000000))
    old=track(parent,zone.GetNet(),(500000,500000),(2000000,2000000))
    # Preserve exact hole representation across the native saved fixture.
    shape=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();shape.Fracture(False)
    zone.SetFilledPolysList(pcbnew.F_Cu,shape);parent=clone(parent,tmp_path)
    old=next(t for t in parent.GetTracks()if force._uid(t)==force._uid(old))
    child=clone(parent,tmp_path);child.Remove(next(t for t in child.GetTracks()if force._uid(t)==force._uid(old)))
    assert not retained(parent,child,old)


def test_multiface_zone_is_not_a_plated_barrel(tmp_path):
    parent,zone=fixture();shape=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.B_Cu)
    zone.SetLayerSet(layers);zone.SetFilledPolysList(pcbnew.F_Cu,shape)
    zone.SetFilledPolysList(pcbnew.B_Cu,shape);zone.SetIsFilled(True)
    track(parent,zone.GetNet(),(500000,500000),(700000,500000),pcbnew.B_Cu)
    via=pcbnew.PCB_VIA(parent);via.SetNet(zone.GetNet());via.SetPosition(pcbnew.VECTOR2I(500000,500000))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    child=clone(parent,tmp_path);child.Remove(next(t for t in child.GetTracks()if force._uid(t)==force._uid(via)))
    assert not retained(parent,child,via)


def test_duplicate_zone_identity_is_unknown_not_retention():
    board,zone=fixture();board.Add(pcbnew.ZONE(zone))
    with pytest.raises(ValueError,match='ambiguous_native_parent_identity'):
        ordinary._partition(board,time.monotonic()+5.)


def test_changed_fill_cannot_rebind_to_another_island(tmp_path):
    parent,zone=fixture();first=ordinary._partition(parent,time.monotonic()+5.)
    child=clone(parent,tmp_path);z=list(child.Zones())[0]
    moved=fill.reconstruct([[[[20000000,0],[24000000,0],[24000000,4000000],[20000000,4000000]]]],time.monotonic()+5.)
    z.SetFilledPolysList(pcbnew.F_Cu,moved);z.SetIsFilled(True)
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):
        ordinary._partition(child,time.monotonic()+5.,retained_keys=set().union(*first))
