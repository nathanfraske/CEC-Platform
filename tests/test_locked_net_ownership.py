"""Native connectivity, not pad contact, admits complete locked nets."""
import hashlib
import os
from unittest.mock import patch

import pcbnew
import pytest
import cec_fr
import cec_locked_net_ownership as ownership


def board():
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    net = pcbnew.NETINFO_ITEM(b, '/GENERIC_SIGNAL')
    b.Add(net)
    return b, net


def pad(b, net, x, y=5, *, layer=pcbnew.F_Cu, tht=False, footprint=None):
    fp = footprint or pcbnew.FOOTPRINT(b)
    if footprint is None:
        fp.SetReference('X'+str(len(list(b.GetFootprints()))))
        b.Add(fp)
    p = pcbnew.PAD(fp)
    p.SetNumber('1'); p.SetNet(net)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
    ls = pcbnew.LSET(); ls.AddLayer(layer)
    p.SetLayerSet(pcbnew.LSET.AllCuMask() if tht else ls)
    if tht:
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    p.SetPosition(pcbnew.VECTOR2I_MM(x, y)); fp.Add(p)
    return p


def track(b, net, start, end, *, layer=pcbnew.F_Cu, locked=True):
    t = pcbnew.PCB_TRACK(b)
    t.SetNet(net); t.SetLayer(layer); t.SetWidth(pcbnew.FromMM(.2))
    t.SetStart(pcbnew.VECTOR2I_MM(*start))
    t.SetEnd(pcbnew.VECTOR2I_MM(*end)); t.SetLocked(locked); b.Add(t)
    return t


def saved(b, tmp_path):
    path = tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(path), b, True)
    return path, pcbnew.LoadBoard(str(path))


@pytest.mark.parametrize('bridge', ['none', 'unlocked', 'locked'])
def test_separate_locked_stubs_do_not_complete_net(tmp_path, bridge):
    b, net = board()
    pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    if bridge != 'none':
        track(b, net, (3, 5), (7, 5), locked=bridge == 'locked')
    path, b = saved(b, tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = ownership.certificate(b)['nets']['/GENERIC_SIGNAL']
    assert proof['complete'] == (bridge == 'locked')
    assert ownership.revalidate_completed(b, ['/GENERIC_SIGNAL'])['completed'] == (
        [] if bridge == 'none' else ['/GENERIC_SIGNAL'])
    assert cec_fr.owned_locked_nets(str(path)) == (
        {'/GENERIC_SIGNAL'} if bridge == 'locked' else set())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_duplicate_number_is_not_a_bridge(tmp_path):
    b, net = board()
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('X'); b.Add(fp)
    pad(b, net, 2, footprint=fp); pad(b, net, 8, footprint=fp)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    _, b = saved(b, tmp_path)
    assert not ownership.owned_nets(b)


def test_track_body_touches_all_physical_pads(tmp_path):
    b, net = board()
    for x in (2, 5, 8):
        pad(b, net, x)
    track(b, net, (1, 5), (9, 5))
    _, b = saved(b, tmp_path)
    assert ownership.owned_nets(b) == {'/GENERIC_SIGNAL'}


@pytest.mark.parametrize('tht', [False, True])
def test_native_barrel_is_layer_bridge_without_gratuitous_via(tmp_path, tht):
    b, net = board()
    pad(b, net, 2); pad(b, net, 5, tht=tht); pad(b, net, 8, layer=pcbnew.B_Cu)
    track(b, net, (2, 5), (5, 5))
    track(b, net, (5, 5), (8, 5), layer=pcbnew.B_Cu)
    _, b = saved(b, tmp_path)
    assert bool(ownership.owned_nets(b)) == tht


def test_unconnected_extra_locked_copper_is_not_whole_net(tmp_path):
    b, net = board()
    pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (8, 5)); track(b, net, (12, 5), (13, 5))
    _, b = saved(b, tmp_path)
    proof = ownership.certificate(b)['nets']['/GENERIC_SIGNAL']
    assert not proof['complete'] and proof['disconnected_copper_count'] > 0
    assert ownership.revalidate_completed(b, ['/GENERIC_SIGNAL'])['demoted']


@pytest.mark.parametrize('touch_arc', [False, True])
def test_arc_is_not_its_straight_chord(tmp_path, touch_arc):
    b, net = board()
    pad(b, net, 2); pad(b, net, 8); pad(b, net, 5, 2 if touch_arc else 5)
    arc = pcbnew.PCB_ARC(b); arc.SetNet(net); arc.SetLayer(pcbnew.F_Cu)
    arc.SetStart(pcbnew.VECTOR2I_MM(2, 5)); arc.SetMid(pcbnew.VECTOR2I_MM(5, 2))
    arc.SetEnd(pcbnew.VECTOR2I_MM(8, 5)); arc.SetWidth(pcbnew.FromMM(.2))
    arc.SetLocked(True); b.Add(arc)
    _, b = saved(b, tmp_path)
    assert bool(ownership.owned_nets(b)) == touch_arc


@pytest.mark.parametrize('via_type', ['through', 'blind'])
def test_actual_via_span_not_all_enabled_layers(tmp_path, via_type):
    b, net = board()
    pad(b, net, 2); pad(b, net, 8, layer=pcbnew.B_Cu)
    track(b, net, (2, 5), (5, 5)); track(b, net, (5, 5), (8, 5), layer=pcbnew.B_Cu)
    via = pcbnew.PCB_VIA(b); via.SetNet(net)
    via.SetViaType(pcbnew.VIATYPE_THROUGH if via_type == 'through' else pcbnew.VIATYPE_BLIND)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu if via_type == 'through' else pcbnew.In1_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(5, 5)); via.SetWidth(pcbnew.FromMM(.5))
    via.SetDrill(pcbnew.FromMM(.2)); via.SetLocked(True); b.Add(via)
    _, b = saved(b, tmp_path)
    assert bool(ownership.owned_nets(b)) == (via_type == 'through')


def test_missing_net_and_track_only_net_do_not_qualify(tmp_path):
    b, net = board()
    track(b, net, (2, 5), (8, 5))
    _, b = saved(b, tmp_path)
    assert not ownership.owned_nets(b)
    proof = ownership.revalidate_completed(b, ['/GENERIC_SIGNAL', 'MISSING'])
    assert proof['completed'] == [] and len(proof['demoted']) == 2


def test_native_evidence_errors_propagate(tmp_path):
    b, net = board(); pad(b, net, 2); track(b, net, (2, 5), (8, 5))
    _, b = saved(b, tmp_path)
    with patch.object(pcbnew.CONNECTIVITY_DATA, 'GetConnectedItems', side_effect=RuntimeError('native error')):
        with pytest.raises(RuntimeError, match='native error'):
            ownership.owned_nets(b)


def test_route_boundary_demotes_stale_claim_before_backend(tmp_path):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    path, _b = saved(b, tmp_path)
    with patch.object(cec_fr, 'ensure_jar', side_effect=RuntimeError('stop before backend')):
        result = cec_fr.route_once(str(path), str(tmp_path/'out.kicad_pcb'),
                                   completed_nets=['/GENERIC_SIGNAL'])
    assert result.params['completed_net_revalidation']['demoted'] == ['/GENERIC_SIGNAL']
    assert result.params['completed_nets'] == []


def test_zone_bridge_needs_full_board_not_locked_ownership(tmp_path):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    for start, end in (((0, 0), (10, 0)), ((10, 0), (10, 10)),
                       ((10, 10), (0, 10)), ((0, 10), (0, 0))):
        edge = pcbnew.PCB_SHAPE(b); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetStart(pcbnew.VECTOR2I_MM(*start))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*end)); b.Add(edge)
    zone = pcbnew.ZONE(b); zone.SetNet(net); zone.SetLayer(pcbnew.F_Cu)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.Outline(); outline.NewOutline()
    for x, y in ((1, 1), (9, 1), (9, 9), (1, 9)):
        outline.Append(int(pcbnew.FromMM(x)), int(pcbnew.FromMM(y)))
    b.Add(zone); pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    _, b = saved(b, tmp_path)
    assert not ownership.owned_nets(b)
    assert ownership.revalidate_completed(b, ['/GENERIC_SIGNAL'])['completed'] == ['/GENERIC_SIGNAL']
    before = tmp_path/'before.kicad_pcb'; after = tmp_path/'after.kicad_pcb'
    pcbnew.SaveBoard(str(before), b, True)
    for _ in range(3):
        ownership.certificate(b)
        ownership.revalidate_completed(b, ['/GENERIC_SIGNAL'])
    pcbnew.SaveBoard(str(after), b, True)
    assert before.read_bytes() == after.read_bytes()


def test_import_reopens_stale_claim_after_fill(tmp_path):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    path, _b = saved(b, tmp_path); out = str(tmp_path/'imported.kicad_pcb')
    env = {key: '0' for key in ('CEC_POWER_PICKUP', 'CEC_LASTMILE', 'CEC_LASTMILE_FINAL',
        'CEC_ZONE_CLEANUP', 'CEC_ZONE_ISLAND_BRIDGE', 'CEC_INNER_GND')}
    with patch.dict(os.environ, env), patch.object(pcbnew, 'ImportSpecctraSES', return_value=True):
        cec_fr.import_ses(str(path), 'mock.ses', out, fill_zones=False,
                         fix_annular=False, kelvin_taps=False, completed_nets=['/GENERIC_SIGNAL'])
    report = cec_fr._IMPORT_REPORTS.pop(out)
    assert report['completed_nets'] == []
    assert report['completed_net_revalidation']['demoted'] == ['/GENERIC_SIGNAL']
    assert all(t.IsLocked() for t in pcbnew.LoadBoard(out).GetTracks())


def test_reconcile_preserves_bridge_between_locked_pad_escapes(tmp_path):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    source, b = saved(b, tmp_path)
    bridge = track(b, b.FindNet('/GENERIC_SIGNAL'), (3, 5), (7, 5), locked=False)
    uid = bridge.m_Uuid.AsString()
    target = tmp_path/'bridged.kicad_pcb'; pcbnew.SaveBoard(str(target), b, True)
    before = target.read_bytes(); source_before = source.read_bytes()
    report = cec_fr.reconcile_locked_nets(str(target), source_path=str(source))
    assert report == {} and target.read_bytes() == before and source.read_bytes() == source_before
    assert uid in {t.m_Uuid.AsString() for t in pcbnew.LoadBoard(str(target)).GetTracks()}
    assert ownership.revalidate_completed(pcbnew.LoadBoard(str(target)), ['/GENERIC_SIGNAL'])['completed']


@pytest.mark.parametrize('source_authority', [False, True])
def test_reconcile_whole_net_requires_new_item_provenance(tmp_path, source_authority):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (8, 5))
    authored = track(b, net, (3, 5), (3, 6), locked=False).m_Uuid.AsString()
    source, b = saved(b, tmp_path); source_before = source.read_bytes()
    new = track(b, b.FindNet('/GENERIC_SIGNAL'), (7, 5), (7, 6), locked=False).m_Uuid.AsString()
    target = tmp_path/'candidate.kicad_pcb'; pcbnew.SaveBoard(str(target), b, True)
    proof = {}
    report = cec_fr.reconcile_locked_nets(str(target),
        source_path=str(source) if source_authority else None, evidence=proof)
    ids = {t.m_Uuid.AsString() for t in pcbnew.LoadBoard(str(target)).GetTracks()}
    assert authored in ids and (new in ids) != source_authority
    assert bool(report) == source_authority and source.read_bytes() == source_before
    assert proof['delta']['nonexact_source_authority'] == source_authority


@pytest.mark.parametrize('difference', ['none', 'layer', 'net', 'width', 'near'])
def test_reconcile_echo_identity_is_exact(tmp_path, difference):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (3, 5)); track(b, net, (7, 5), (8, 5))
    second_net = pcbnew.NETINFO_ITEM(b, 'ANOTHER_NET'); b.Add(second_net)
    track(b, second_net, (12, 5), (13, 5))
    echo = track(b, second_net if difference == 'net' else net,
                 (3, 5), (2.005 if difference == 'near' else 2, 5),
                 locked=False, layer=pcbnew.B_Cu if difference in ('layer', 'net') else pcbnew.F_Cu)
    if difference == 'width':
        echo.SetWidth(pcbnew.FromMM(.3))
    uid = echo.m_Uuid.AsString(); path, _ = saved(b, tmp_path)
    report = cec_fr.reconcile_locked_nets(str(path))
    ids = {t.m_Uuid.AsString() for t in pcbnew.LoadBoard(str(path)).GetTracks()}
    assert (uid not in ids) == (difference == 'none')
    assert report == ({'_echoes': 1} if difference == 'none' else {})
    assert cec_fr.reconcile_locked_nets(str(path)) == {}


def test_reconcile_preserves_group_owned_additions(tmp_path):
    b, net = board(); pad(b, net, 2); pad(b, net, 8)
    track(b, net, (2, 5), (8, 5)); source, b = saved(b, tmp_path)
    new = track(b, b.FindNet('/GENERIC_SIGNAL'), (2, 5), (8, 5), locked=False)
    group = pcbnew.PCB_GROUP(b); group.SetName('owned-generated-cell'); b.Add(group); group.AddItem(new)
    target = tmp_path/'grouped.kicad_pcb'; pcbnew.SaveBoard(str(target), b, True)
    before = target.read_bytes(); proof = {}
    assert cec_fr.reconcile_locked_nets(str(target), source_path=str(source), evidence=proof) == {}
    assert len(proof['delta']['group_owned_retained']) == 1 and target.read_bytes() == before
