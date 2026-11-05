"""An error-named orphan is not a pad, plane connection or reserved portal."""
import copy
from unittest import mock

import pcbnew
import pytest

import cec_native_isolated_vias as isolated
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive


def fixture(*, locked=False):
    b = pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(b, '/ARBITRARY_RAIL'); b.Add(net)
    other = pcbnew.NETINFO_ITEM(b, '/ARBITRARY_FOREIGN'); b.Add(other)
    via = pcbnew.PCB_VIA(b); via.SetNet(net)
    via.SetPosition(pcbnew.VECTOR2I_MM(10, 10)); via.SetWidth(600000)
    via.SetDrill(300000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetLocked(locked); b.Add(via)
    # Real terminals, well away from the orphan, give the saved receiver actual
    # pad partitions to protect as well as retained route identities.
    for index, rail in enumerate((net, other)):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('ANCHOR'+str(index)); b.Add(fp)
        pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('1'); pad.SetNet(rail)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        face = pcbnew.LSET(); face.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(face)
        pad.SetPosition(pcbnew.VECTOR2I_MM(30+index*3, 30))
    return b, via, net, other


def route(b, net, layer, *, y=10):
    t = pcbnew.PCB_TRACK(b); t.SetNet(net); t.SetLayer(layer)
    t.SetWidth(200000); t.SetStart(pcbnew.VECTOR2I_MM(9, y))
    t.SetEnd(pcbnew.VECTOR2I_MM(11, y)); b.Add(t)
    return t


def drc(via, kind='shorting_items'):
    return {'violations': [{'type': kind, 'items': [{'uuid': force._uid(via)}]}]}


def test_proved_isolated_barrel_retirement_has_no_current_or_release_authority():
    b, via, net, other = fixture()
    before = field._field_snapshot_inventory(b)
    q = isolated.plan(b, [force._uid(via)])
    assert field._field_snapshot_inventory(b) == before
    assert set(q['witnesses'][0]['copper_layers']) == set(map(int, b.GetEnabledLayers().CuStack()))
    assert not q['current_qualified'] and not q['routing_admitted'] and not q['release_authority']
    r = isolated.apply(b, q)
    assert r['removed'] == 1 and list(b.GetTracks()) == []


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                                 pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu])
def test_actual_contact_on_any_enabled_layer_is_never_orphan(layer):
    b, via, net, other = fixture()
    route(b, net, layer)
    before = field._field_snapshot_inventory(b)
    with pytest.raises(ValueError, match='same_net_pad_or_route_contact'):
        isolated.plan(b, [force._uid(via)])
    assert before == field._field_snapshot_inventory(b)


@pytest.mark.parametrize('pth,layer', [(True, pcbnew.F_Cu), (False, pcbnew.F_Cu),
                                      (False, pcbnew.B_Cu)])
def test_real_pad_and_through_hole_contacts_are_not_inferred_from_footprint_face(pth, layer):
    b, via, net, other = fixture()
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('OWNER'); b.Add(fp)
    pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('X'); pad.SetNet(net)
    pad.SetPosition(via.GetPosition()); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
    if pth:
        pad.SetLayerSet(pcbnew.LSET.AllCuMask()); pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4, .4))
    else:
        layers = pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers)
    with pytest.raises(ValueError, match='same_net_pad_or_route_contact'):
        isolated.plan(b, [force._uid(via)])


def test_even_unfilled_same_net_authored_zone_reserves_the_barrel():
    b, via, net, other = fixture()
    z = pcbnew.ZONE(b); z.SetNet(net); z.SetLayer(pcbnew.In2_Cu)
    z.Outline().NewOutline()
    for xy in ((8, 8), (12, 8), (12, 12), (8, 12)):
        z.Outline().Append(pcbnew.VECTOR2I_MM(*xy))
    b.Add(z)
    assert not z.IsFilled()
    with pytest.raises(ValueError, match='authored_zone_reservation'):
        isolated.plan(b, [force._uid(via)])


def test_foreign_short_is_not_same_net_connectivity_and_does_not_waive_its_gate():
    b, via, net, other = fixture()
    foreign = route(b, other, pcbnew.In2_Cu)
    result = isolated.discover_from_drc(b, drc(via))
    assert result['complete'] and result['plan']['via_uuids'] == [force._uid(via)]
    isolated.apply(b, result['plan'])
    assert [force._uid(t) for t in b.GetTracks()] == [force._uid(foreign)]
    assert not result['release_authority']


def test_groups_reservations_and_locked_source_scope_require_explicit_ownership():
    b, via, net, other = fixture(locked=True); uid = force._uid(via)
    with pytest.raises(ValueError, match='locked_orphan_scope'):
        isolated.plan(b, [uid])
    with pytest.raises(ValueError, match='reserved_native_barrel'):
        isolated.plan(b, [uid], allow_locked_uuids=[uid], protected_uuids=[uid])
    q = isolated.plan(b, [uid], allow_locked_uuids=[uid])
    assert q['witnesses'][0]['locked']
    g = pcbnew.PCB_GROUP(b); g.SetName('EXPLICIT_FUTURE_PORTAL'); g.AddItem(via); b.Add(g)
    with pytest.raises(ValueError, match='grouped_native_barrel'):
        isolated.plan(b, [uid], allow_locked_uuids=[uid])


def test_discovery_skips_connected_source_and_requires_current_native_uuid():
    b, via, net, other = fixture()
    route(b, net, pcbnew.In3_Cu)
    result = isolated.discover_from_drc(b, drc(via))
    assert result['complete'] and result['plan'] is None and len(result['refused']) == 1
    result = isolated.discover_from_drc(b, {'violations': [{'type': 'shorting_items', 'items': [{'uuid': 'STALE'}]}]})
    assert result['complete'] and result['plan'] is None


def test_stale_or_forged_plan_refuses_before_any_destruction():
    b, via, net, other = fixture(); uid = force._uid(via)
    q = isolated.plan(b, [uid]); forged = copy.deepcopy(q)
    forged['current_qualified'] = True
    with pytest.raises(ValueError, match='stale_or_forged'):
        isolated.apply(b, forged)
    via.SetPosition(pcbnew.VECTOR2I_MM(11, 10))
    with pytest.raises(ValueError, match='stale_or_forged'):
        isolated.apply(b, q)
    assert len(list(b.GetTracks())) == 1


def test_incomplete_batch_does_not_destroy_an_earlier_proved_orphan():
    b, via, net, other = fixture(); uid = force._uid(via)
    with pytest.raises(ValueError):
        isolated.plan(b, [uid, 'STALE'])
    assert len(list(b.GetTracks())) == 1


@pytest.mark.parametrize('kwargs', [
    {'via_uuids': []}, {'via_uuids': ['A', 'A']}, {'via_uuids': ['A'], 'timeout_s': True},
    {'via_uuids': ['A'], 'timeout_s': 0}, {'via_uuids': ['A'], 'timeout_s': 11},
    {'via_uuids': ['A'], 'timeout_s': float('nan')},
    {'via_uuids': ['A'], 'allow_locked_uuids': ['OTHER']},
    {'via_uuids': [str(i) for i in range(65)]},
])
def test_invalid_or_unbounded_policies_do_not_mutate_source(kwargs):
    b, via, net, other = fixture()
    with pytest.raises(ValueError):
        isolated.plan(b, **kwargs)
    assert len(list(b.GetTracks())) == 1


@pytest.mark.parametrize('kwargs', [{'authorize_source_locked': 1}, {'max_vias': True},
                                  {'max_vias': 0}, {'max_vias': 65}])
def test_discovery_policy_requires_strict_bounded_types(kwargs):
    b, via, net, other = fixture()
    with pytest.raises(ValueError):
        isolated.discover_from_drc(b, drc(via), **kwargs)


def test_discovery_budget_is_no_partial_retirement_permission():
    b, via, net, other = fixture()
    second = pcbnew.PCB_VIA(b); second.SetNet(net); second.SetPosition(pcbnew.VECTOR2I_MM(20, 20))
    second.SetWidth(600000); second.SetDrill(300000)
    second.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(second)
    raw = drc(via); raw['violations'].extend(drc(second)['violations'])
    result = isolated.discover_from_drc(b, raw, max_vias=1)
    assert not result['complete'] and result['plan'] is None and result['errors']
    with mock.patch.object(isolated.time, 'monotonic', side_effect=[0., 20.]):
        result = isolated.discover_from_drc(b, raw, timeout_s=1.)
    assert not result['complete'] and result['plan'] is None
    assert len(list(b.GetTracks())) == 2


def test_saved_retirement_replays_exact_delta_and_preserves_all_other_partitions(tmp_path):
    b, via, net, other = fixture(locked=True)
    route(b, other, pcbnew.In2_Cu, y=12)
    source = tmp_path/'source.kicad_pcb'
    # Freeze a loaded native source, not an unsaved synthetic board's default
    # serialization representatives. Foreign-contact proof has its separate
    # read-only test; a synthetic short can be re-netted on initial load.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source), b)
    parent = pcbnew.LoadBoard(str(source)); uid = force._uid(via)
    q = isolated.plan(parent, [uid], allow_locked_uuids=[uid])
    candidate = force._copy_family(source, tmp_path/'candidate')
    isolated.apply(parent, q); additive._ground_refill(parent)
    field._save_field_snapshot(parent, candidate)
    result = isolated.receive(source, candidate, q)
    assert result['ok'], result['errors']
    assert result['all_surviving_native_terminal_and_conductor_partitions_preserved']
    assert result['source_unchanged'] and not result['release_authority']
    child = pcbnew.LoadBoard(str(candidate)); next(iter(child.GetTracks())).SetWidth(210000)
    field._save_field_snapshot(child, candidate)
    refused = isolated.receive(source, candidate, q)
    assert not refused['ok'] and 'exact_native_refill_replay' in refused['errors'][0]


def test_production_cleanup_finds_error_named_orphan_without_via_dangling(tmp_path):
    import cec_certificate_repair as repair
    b, via, net, other = fixture(locked=True)
    foreign = route(b, other, pcbnew.In2_Cu, y=12)
    uid = force._uid(via); foreign_uid = force._uid(foreign)
    source = tmp_path/'worker.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source), b)
    with mock.patch.object(repair, '_run_drc', return_value=drc(via, 'unconnected_items')):
        changed, report = repair._drc_dangling_cleanup_worker(str(source), 2)
    assert changed and report['removed_count'] == 1
    assert report['removed'][0]['uuid'] == uid
    assert report['native_orphan_proofs'][0]['witnesses'][0]['native_isolation_proved']
    assert report['full_board_admission_still_required']
    saved = pcbnew.LoadBoard(str(source))
    assert [(force._uid(t), str(t.GetNetname())) for t in saved.GetTracks()] == [(foreign_uid, '/ARBITRARY_FOREIGN')]


def test_production_cleanup_does_not_remove_connected_error_named_barrel(tmp_path):
    import cec_certificate_repair as repair
    b, via, net, other = fixture(locked=True)
    route(b, net, pcbnew.In3_Cu)
    source = tmp_path/'worker.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source), b)
    original = source.read_bytes()
    with mock.patch.object(repair, '_run_drc', return_value=drc(via)):
        changed, report = repair._drc_dangling_cleanup_worker(str(source), 2)
    assert not changed and report['removed_count'] == 0
    assert original == source.read_bytes()
