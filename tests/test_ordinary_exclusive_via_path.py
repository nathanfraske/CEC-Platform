"""Whole obsolete ordinary multilayer leaves, never permissive via deletion."""
import math
import time

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as receiving
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, quarter=0, mirrored=False, fault=None):
    def transform(point):
        x, y = point[0] - 15, point[1] - 15
        if mirrored:
            x = -x
        angle = quarter * math.pi / 2
        return (round(15 + x * math.cos(angle) - y * math.sin(angle), 6),
                round(15 + x * math.sin(angle) + y * math.cos(angle), 6))
    net = '/RENAMED_%s/CONTROL' % quarter
    if fault == 'power':
        net = '+5V'
    if fault == 'pair':
        net = '/USB_D_P'
    b = _board([(*transform((5, 10)), net), (*transform((20, 10)), net)],
               edge=(0, 0, 30, 30))
    for fp in b.GetFootprints():
        pad = list(fp.Pads())[0]; pad.SetPadName('1')
        if fp.GetReference() == 'X2':
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
    old = [track(b, net, transform((5, 10)), transform((10, 10)), layer=pcbnew.F_Cu),
           track(b, net, transform((10, 10)), transform((20, 10)), layer=pcbnew.B_Cu)]
    via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I_MM(*transform((10, 10))))
    via.SetNetCode(b.GetNetcodeFromNetname(net)); via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    b.Add(via)
    if fault == 'locked':
        via.SetLocked(True)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(b); group.SetName('REAL_OWNER'); b.Add(group); group.AddItem(via)
    elif fault == 'factory':
        b.GetDesignSettings().m_ViasMinSize = 600000
        b.GetDesignSettings().m_MinThroughDrill = 300000
        via.SetWidth(350000); via.SetDrill(250000)
    elif fault == 'surviving_branch':
        track(b, net, transform((10, 10)), transform((10, 8)), layer=pcbnew.F_Cu)
    elif fault == 'land':
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('OTHER_OWNER')
        pad = pcbnew.PAD(fp); pad.SetPadName('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        pad.SetPosition(via.GetPosition()); pad.SetNetCode(via.GetNetCode())
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
        fp.Add(pad); b.Add(fp)
    source = tmp_path / 'source' / 'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(b, source)
    child = force._copy_family(source, tmp_path / 'candidate')
    native = pcbnew.LoadBoard(str(child)); ids = {force._uid(t) for t in old}
    via_id = force._uid(via)
    discard_items(native, [t for t in native.GetTracks() if force._uid(t) in ids | {via_id}])
    for a, z in (((5, 10), (5, 12)), ((5, 12), (12, 12))):
        track(native, net, transform(a), transform(z), layer=pcbnew.F_Cu)
    for a, z in (((12, 12), (20, 12)), ((20, 12), (20, 10))):
        track(native, net, transform(a), transform(z), layer=pcbnew.B_Cu)
    replacement = pcbnew.PCB_VIA(native)
    replacement.SetPosition(pcbnew.VECTOR2I_MM(*transform((12, 12))))
    replacement.SetNetCode(native.GetNetcodeFromNetname(net)); replacement.SetWidth(600000)
    replacement.SetDrill(300000); replacement.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    replacement.SetViaType(pcbnew.VIATYPE_THROUGH); native.Add(replacement)
    field._save_field_snapshot(native, child)
    final = additive.finalize_private(source, child, tmp_path / 'final')['board']
    return source, final, sorted(ids), via_id


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirrored', [False, True])
def test_complete_rotated_mirrored_leaf_is_received_without_source_mutation(tmp_path, quarter, mirrored):
    source, child, tracks, via = fixture(tmp_path, quarter, mirrored)
    before = [source.read_bytes(), force.Path(child).read_bytes()]
    result = receiving.receive(source, child, retired_track_uuids=tracks,
        retired_via_uuids=[via], board_hint='synthetic')
    assert result['ok'] and result['complete'], result
    assert result['retired_via_uuids'] == [via]
    assert result['all_prior_surviving_copper_junctions_preserved']
    assert result['exclusive_retired_via_ownership'][0]['source_contact_track_uuids'] == tracks
    assert not result['release_authority'] and not result['power_authority']
    assert [source.read_bytes(), force.Path(child).read_bytes()] == before
    assert not additive.receive(source, child)['ok']


@pytest.mark.parametrize('fault', ['locked', 'group', 'factory', 'surviving_branch', 'land', 'power', 'pair'])
def test_owned_or_unqualified_barrels_cannot_be_subtracted(tmp_path, fault):
    source, child, tracks, via = fixture(tmp_path, fault=fault)
    result = receiving.receive(source, child, retired_track_uuids=tracks,
        retired_via_uuids=[via], board_hint='synthetic')
    assert not result['ok'] and not result['complete'] and result['errors'], result


@pytest.mark.parametrize('scope', [[], ['duplicate', 'duplicate'], [True], ['a', 'b', 'c', 'd', 'e']])
def test_via_scope_is_exact_typed_and_bounded(tmp_path, scope):
    source, child, tracks, via = fixture(tmp_path)
    result = receiving.receive(source, child, retired_track_uuids=tracks,
        retired_via_uuids=scope, board_hint='synthetic')
    assert not result['ok'] and result['errors'], result


def test_locked_permission_and_typed_cut_chain_do_not_broaden_scope(tmp_path):
    source, child, tracks, via = fixture(tmp_path, fault='locked')
    result = chain.receive(source, child, board_hint='synthetic', per_phase_leases=True,
        phases=[dict(kind='ordinary_exclusive_via_path', candidate=str(child),
            retired_track_uuids=tracks, allow_locked_track_uuids=[],
            retired_via_uuids=[via], allow_locked_via_uuids=[via])])
    assert result['ok'] and result['complete'], result
    assert result['retired_via_uuids'] == [via]
    assert result['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert not result['release_authority'] and not result['current_authority']


def test_missing_one_departure_cannot_grant_exclusive_barrel_authority(tmp_path):
    source, child, tracks, via = fixture(tmp_path)
    parent = pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError, match='surviving_or_unowned_contact'):
        receiving._exclusive_retired_vias(parent, {via}, retired_tracks={tracks[0]},
            nets=receiving.eligible_nets(parent, source, 'synthetic'), unlock=set(),
            deadline=time.monotonic() + 10.)
