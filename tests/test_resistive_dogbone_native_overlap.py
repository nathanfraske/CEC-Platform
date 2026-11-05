"""A contained turn/barrel overlap is not an electrical branch junction."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_resistive_monitor_branch as branch
from test_resistive_monitor_branch import fixture


def native_dogbone(tmp_path,*,other_face_turn=False):
    source,b,top,_,_,domains,old,trunk,_=fixture(tmp_path)
    for item in list(b.GetTracks()):
        if force._uid(item) in old:b.Remove(item)
    net=b.FindNet('arbitrary_rail')
    def track(a,z,layer):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetWidth(200000);t.SetLayer(layer)
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);return t
    first=track((10,10),(10,10.865),pcbnew.F_Cu)
    tail=track((10,10.865),(10.135,11),pcbnew.F_Cu)
    via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetPosition(pcbnew.VECTOR2I_MM(10.135,11))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    child=track((10.135,11),(20,11),pcbnew.B_Cu)
    last=track((20,11),(20,12),pcbnew.B_Cu)
    inset=None
    if other_face_turn:
        inset=track((10.135,11),(10.235,11.1),pcbnew.B_Cu)
        child.SetStart(pcbnew.VECTOR2I_MM(10.235,11.1));child.SetEnd(pcbnew.VECTOR2I_MM(20,11.1))
        last.SetStart(pcbnew.VECTOR2I_MM(20,11.1))
    bus=pcbnew.PCB_VIA(b);bus.SetNet(net);bus.SetPosition(pcbnew.VECTOR2I_MM(20,12))
    bus.SetWidth(900000);bus.SetDrill(500000);bus.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    bus.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(bus)
    items=[first,tail,via,child,last]
    if inset:items.append(inset)
    field._save_field_snapshot(b,source)
    return source,b,top,domains,items,bus,track


@pytest.mark.parametrize('other_face_turn',[False,True])
def test_native_contained_dogbone_has_one_real_layer_transition_not_a_fork(tmp_path,other_face_turn):
    source,b,top,domains,items,bus,_=native_dogbone(tmp_path,other_face_turn=other_face_turn);original=source.read_bytes()
    q=branch.plan(b,force._uid(top.FindPadByNumber('1')))
    assert set(q['native_removed_material_uuids'])=={force._uid(t) for t in items}
    assert force._uid(bus) not in q['native_removed_material_uuids']
    assert len(q['native_contained_turn_barrel_bundles'])==1
    assert bool(q['native_contained_turn_barrel_bundles'][0]['other_face_contained_track_uuids'])==other_face_turn
    assert not q['native_contained_turn_barrel_bundles'][0]['barrel_ampacity_or_release_qualification']
    r=branch.inventory(b,source,domains)
    assert r['complete'] and set(r['uuids'])=={force._uid(t) for t in items if t.GetClass()=='PCB_TRACK'},r
    assert r['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['fork','same_layer','not_contained','unqualified_via','other_pad'])
def test_true_junctions_or_unqualified_overlaps_are_not_fully_classified(tmp_path,fault):
    source,b,top,domains,items,_,track=native_dogbone(tmp_path)
    first,tail,via,child,last=items
    if fault=='fork':track((10.135,11),(10.135,15),pcbnew.B_Cu)
    elif fault=='same_layer':child.SetLayer(pcbnew.F_Cu)
    elif fault=='not_contained':via.SetWidth(500000)
    elif fault=='unqualified_via':via.SetWidth(400000);via.SetDrill(150000)
    else:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('not_a_known_load');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNet(b.FindNet('arbitrary_rail'));p.SetNumber('1')
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.2,.2));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(10.3,11));fp.Add(p)
    field._save_field_snapshot(b,source)
    r=branch.inventory(b,source,domains)
    assert force._uid(tail) not in r['uuids'] and force._uid(child) not in r['uuids'],r


def test_native_overlap_rule_is_rotation_and_back_side_invariant(tmp_path):
    source,b,top,domains,items,_,_=native_dogbone(tmp_path)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    q=branch.plan(b,force._uid(top.FindPadByNumber('1')))
    assert set(q['native_removed_material_uuids'])=={force._uid(t) for t in items}


def test_contained_other_face_turn_cannot_hide_an_extra_native_departure(tmp_path):
    source,b,top,domains,items,_,track=native_dogbone(tmp_path,other_face_turn=True)
    track((10.235,11.1),(10.235,15),pcbnew.B_Cu)
    field._save_field_snapshot(b,source)
    q=branch.inventory(b,source,domains)
    assert force._uid(items[1]) not in q['uuids'] and force._uid(items[3]) not in q['uuids']
