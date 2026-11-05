"""Native saved-refill regression, not current or route authority.

The previous exact-fill-key comparison falsely refused valid Ground refills.
Fresh positive island overlaps preserve every old component and still reject
real splits or lost native material. Both direct and public callers run.
"""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_force_crossface_receiving as cross
import cec_native_partition_pair as paired
import cec_native_fill_geometry as fill
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_field_coupling as field
from cec_native_items import discard_items
from test_field_refill_proposals import ground_fixture, signature
from test_field_proposals import track
from test_additive_route_receiving import barrel
from test_native_partition_pair import board, clone, setfill, SPLIT


@pytest.fixture(params=['direct_paired', 'planned_public_helper'])
def preserve(request):
    if request.param == 'planned_public_helper':
        return cross.preserve_native_partitions
    def direct(parent, child, retired_track_uuids, timeout_s=10.):
        proof = paired.compare(parent, child, retired_uuids=retired_track_uuids,
                               timeout_s=timeout_s)
        if not proof['preserved']:
            raise ValueError('original_retained_native_force_partition_lost')
        return proof
    return direct


def refill_case(tmp_path, turn=0, face=pcbnew.F_Cu):
    source, parent = ground_fixture(tmp_path)
    # Exact physical terminal identities are retained; this comparison does
    # not classify CONTROL as power or grant current/clearance qualification.
    old = next(t for t in parent.GetTracks() if t.GetNetname() == '/CONTROL')
    old.SetLayer(face)
    cut = force._uid(old)
    center = pcbnew.VECTOR2I_MM(15, 15)
    angle = pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T)
    for item in [*parent.GetTracks(), *parent.GetFootprints(),
                 *parent.Zones(), *parent.GetDrawings()]:
        item.Rotate(center, angle)
    additive._ground_refill(parent)
    field._save_field_snapshot(parent, source)
    child = clone(parent)
    removed = next(t for t in child.GetTracks() if force._uid(t) == cut)
    start, end, width = removed.GetStart(), removed.GetEnd(), removed.GetWidth()
    discard_items(child, [removed])
    replacement = pcbnew.PCB_TRACK(child)
    replacement.SetNetCode(child.GetNetcodeFromNetname('/CONTROL'))
    replacement.SetLayer(face); replacement.SetWidth(width)
    replacement.SetStart(start); replacement.SetEnd(end); child.Add(replacement)
    via = barrel(child, (12, 14), diameter=.8, drill=.4)
    via.Rotate(center, angle)
    # Actual native Ground refill, not a fabricated clipped polygon or flag.
    before = [fill.identity(z.GetFilledPolysList(l), time.monotonic()+2.)
              for z in parent.Zones() for l in z.GetLayerSet().CuStack()]
    additive._ground_refill(child)
    after = [fill.identity(z.GetFilledPolysList(l), time.monotonic()+2.)
             for z in child.Zones() for l in z.GetLayerSet().CuStack()]
    assert before != after
    return parent, child, cut


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_real_new_rail_barrel_ground_refill_preserves_all_old_parts(
        tmp_path, preserve, turn, face):
    parent, child, cut = refill_case(tmp_path, turn, face)
    before = [signature(b) for b in (parent, child)]
    proof = preserve(parent, child, [cut], timeout_s=10.)
    assert proof['available'] and proof['preserved']
    assert proof['exact_positive_native_island_overlap']
    assert proof['overlap_token_count'] > 0
    assert not proof['whole_zone_uuid_connectivity_credit']
    assert not proof['current_capacity_qualified']
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert before == [signature(b) for b in (parent, child)]


def test_old_exact_fill_identity_refusal_is_not_a_lost_physical_component(tmp_path):
    parent, child, cut = refill_case(tmp_path)
    parts = ordinary._partition(parent, time.monotonic()+5., retired_uuids={cut})
    with pytest.raises(ValueError, match='surviving_source_conductor_missing'):
        ordinary._partition(child, time.monotonic()+5.,
                            retained_keys=set().union(*parts))
    assert paired.compare(parent, child, retired_uuids=[cut])['preserved']


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('fault', ['lost_pad', 'lost_copper_only_tee'])
def test_every_old_pad_and_copper_only_material_is_still_mandatory(
        preserve, face, fault):
    parent, zone = board(face, solid=True)
    if fault == 'lost_pad':
        fp = pcbnew.FOOTPRINT(parent); fp.SetReference('RENAMED_TERMINAL')
        p = pcbnew.PAD(fp); p.SetNumber('A'); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I(400000,400000))
        layers=pcbnew.LSET(); layers.AddLayer(face); p.SetLayerSet(layers)
        p.SetPosition(pcbnew.VECTOR2I(500000,500000)); p.SetNet(zone.GetNet())
        fp.Add(p); parent.Add(fp); uid=force._uid(fp)
    else:
        item=track(parent,'GND',(2,1),(2,2),layer=face)
        uid=force._uid(item)
    child=clone(parent)
    candidates=(child.GetFootprints() if fault=='lost_pad' else child.GetTracks())
    discard_items(child,[i for i in candidates if force._uid(i)==uid])
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):
        preserve(parent,child,[],timeout_s=10.)


@pytest.mark.parametrize('fault', ['split', 'unfilled', 'erased', 'lost_island'])
def test_real_island_damage_or_unknown_fill_cannot_pass(preserve, fault):
    parent, zone = board(solid=fault!='lost_island')
    child=clone(parent); target=next(iter(child.Zones()))
    if fault=='split': setfill(target,SPLIT)
    elif fault=='unfilled': target.UnFill()
    elif fault=='erased':
        target.SetFilledPolysList(target.GetLayer(),pcbnew.SHAPE_POLY_SET())
    else: setfill(target,[SPLIT[0]])
    before=[signature(b)for b in(parent,child)]
    with pytest.raises((ValueError,RuntimeError)):
        preserve(parent,child,[],timeout_s=10.)
    assert before==[signature(b)for b in(parent,child)]


def test_partition_helper_is_not_permission_for_new_foreign_copper(tmp_path,preserve):
    # A new-only island has no old comparison identity. The WHOLE receiver
    # must still refuse a non-owned foreign-net delta before current checks.
    parent,zone=board(solid=True);old=track(parent,'/RAIL',(2,7),(3,7),width=.5)
    cut=force._uid(old); child=clone(parent)
    discard_items(child,[t for t in child.GetTracks()if force._uid(t)==cut])
    track(child,'/RAIL',(2,7),(3,7),width=.5)
    track(child,'/FOREIGN',(8,8),(9,8),width=.5)
    assert preserve(parent,child,[cut],timeout_s=10.)['preserved']
    source=tmp_path/'source.kicad_pcb'; candidate=tmp_path/'candidate.kicad_pcb'
    field._save_field_snapshot(parent,source);field._save_field_snapshot(child,candidate)
    result=cross.receive(source,candidate,[cut],board_hint='opaque',sense_timeout_s=1.)
    assert not result['ok'] and not result['complete']
    assert any('bounded_same_net_fresh_force_conductors_required'in e
               for e in result['errors']),result


@pytest.mark.parametrize('timeout',[True,0.,-1.,10.0001,float('nan')])
def test_no_invalid_or_extended_comparison_lease(preserve,timeout):
    parent,_=board();child=clone(parent)
    with pytest.raises(ValueError):preserve(parent,child,[],timeout_s=timeout)
