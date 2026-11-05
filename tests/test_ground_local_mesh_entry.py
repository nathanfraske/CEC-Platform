"""Saved local GND entry never grants a smaller remote barrel or new rule."""
import copy
import json
import math

import pcbnew
import pytest

import cec_ground_local_mesh_entry as op
import cec_ground_mesh_entry as remote
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as producer
import cec_additive_route_receiving as additive
import cec_existing_local_pofv_pad_rule as rule
from cec_native_items import discard_items
from test_ground_mesh_entry import fixture as mesh_fixture
from test_field_proposals import track


def fixture(tmp_path, *, quarter=0, layer=pcbnew.F_Cu, barrier=True):
    b, source, owner, cap, via = mesh_fixture(tmp_path, quarter=quarter, layer=layer, barrier=barrier)
    settings = b.GetDesignSettings()
    settings.m_ViasMinSize = 500000
    settings.m_MinThroughDrill = 300000
    settings.m_ViasMinAnnularWidth = 100000
    settings.m_MinClearance = 0
    settings.m_HoleToHoleMin = 250000
    via.SetWidth(500000); via.SetDrill(300000)
    group = pcbnew.PCB_GROUP(b); group.SetName(rule.GROUP); b.Add(group); group.AddItem(via)
    project = json.loads(source.with_suffix('.kicad_pro').read_text())
    project['board'] = {'design_settings': {'rules': {
        'min_via_diameter': .5, 'min_through_hole_diameter': .3,
        'min_via_annular_width': .1, 'min_clearance': .2, 'min_track_width': .2,
        'min_hole_to_hole': .254}}}
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    source.with_suffix('.kicad_dru').write_text(
        '(version 1)\n(rule "CEC local POFV signal via"\n'
        ' (condition "A.Type == \'Via\' && A.memberOfGroup(\'CEC_LOCAL_POFV_SIGNAL_VIA\')")\n'
        ' (constraint via_diameter (min 0.5mm))\n'
        ' (constraint hole_size (min 0.3mm))\n'
        ' (constraint annular_width (min 0.1mm)))\n')
    additive._ground_refill(b); field._save_field_snapshot(b, source)
    b.SetFileName(str(source))
    return b, source, owner, cap, via


def construct(tmp_path, *, noncovered=False, **options):
    b, source, owner, cap, _ = fixture(tmp_path, **options)
    family = force._family(source, 'synthetic')
    proposal = op.plan(b, board_hint='synthetic', timeout_s=10.)
    assert proposal['complete'] and proposal['ops'], proposal
    if noncovered:
        pad = cap.FindPadByNumber('2'); start = tuple(pad.GetPosition())
        at = (start[0], start[1]+750000)
        proposal = copy.deepcopy(proposal)
        proposal['pad_uuid'] = force._uid(pad)
        proposal['ops'] = [('trk', start, at, 200000, pcbnew.F_Cu), ('via', at, .3, .5)]
    old = {force._uid(i) for i in b.GetTracks()}
    added = op.construct_private(b, proposal, board_hint='synthetic')
    assert len([i for i in added if i.GetClass() == 'PCB_VIA']) == 1
    child = force._copy_family(source, tmp_path/'child')
    producer.save_native_additions(child, b, {}, old, board_hint='synthetic')
    assert force._family(source, 'synthetic') == family
    return source, child, proposal, {force._uid(i) for i in added}


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_saved_local_entry_is_real_bounded_ordinary_floor_join(tmp_path, quarter, layer):
    source, child, proposal, ids = construct(tmp_path, quarter=quarter, layer=layer)
    before = force._family(source, 'synthetic')
    result = op.receive(source, child, board_hint='synthetic', timeout_s=10.)
    assert result['ok'] and result['complete'], result
    assert force._family(source, 'synthetic') == before
    b = pcbnew.LoadBoard(str(child))
    new = [i for i in b.GetTracks() if force._uid(i) in ids]
    via = next(i for i in new if i.GetClass() == 'PCB_VIA')
    assert via.GetWidth(via.TopLayer()) == 500000 and via.GetDrillValue() == 300000
    assert all(i.GetNetname() == 'GND' for i in new)
    assert sum(i.GetLength() for i in new if i.GetClass() == 'PCB_TRACK') <= 1500000
    assert not result.get('current_qualified', False) and not result.get('release_authority', False)
    # Ordinary remote entry has its own unchanged .9/.5 project geometry.
    assert not remote.receive(source, child, board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault', ['extra_via', 'foreign_via', 'underfloor', 'wrong_geometry',
    'partial_pad', 'long_path', 'unrelated_component', 'one_plane', 'width_change', 'source_overwrite'])
def test_saved_local_entry_rejects_scope_or_source_changes(tmp_path, fault):
    source, child, proposal, ids = construct(tmp_path, noncovered=fault == 'width_change')
    b = pcbnew.LoadBoard(str(child)); new = [i for i in b.GetTracks() if force._uid(i) in ids]
    via = next(i for i in new if i.GetClass() == 'PCB_VIA')
    if fault == 'extra_via':
        other = via.Duplicate(); other.m_Uuid.Clone(pcbnew.KIID()); other.Move(pcbnew.VECTOR2I_MM(1, 0)); b.Add(other)
    elif fault == 'foreign_via': via.SetNet(b.FindNet('+3V3'))
    elif fault == 'underfloor': via.SetWidth(499999)
    elif fault == 'wrong_geometry': via.SetWidth(600000)
    elif fault == 'partial_pad':
        p = b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR').FindPadByNumber('7')
        via.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(.1, 0))
    elif fault == 'long_path': via.Move(pcbnew.VECTOR2I_MM(3, 0))
    elif fault == 'unrelated_component': track(b, 'GND', (25, 25), (26, 25), width=.5)
    elif fault == 'one_plane': next(z for z in b.Zones() if z.GetNetname() == 'GND').UnFill()
    elif fault == 'width_change':
        next(i for i in new if i.GetClass() == 'PCB_TRACK').SetWidth(199999)
    else: next(i for i in b.GetTracks() if force._uid(i) not in ids and i.GetClass() == 'PCB_TRACK').SetWidth(123456)
    if fault == 'foreign_via':
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), b)
    else:
        field._save_field_snapshot(b, child)
    result = op.receive(source, child, board_hint='synthetic', timeout_s=10.)
    assert not result['ok'] and not result['complete'], result


@pytest.mark.parametrize('fault', ['unknown_owner', 'regulator', 'underfloor_rule', 'missing_rule', 'one_plane'])
def test_source_needs_positive_owner_exact_saved_rule_and_all_planes(tmp_path, fault):
    b, source, owner, cap, via = fixture(tmp_path)
    if fault == 'unknown_owner': owner.SetValue('UNMODELED_PART')
    elif fault == 'regulator': owner.SetValue('TPS2121RUXR')
    elif fault == 'underfloor_rule': b.GetDesignSettings().m_MinThroughDrill = 300001
    elif fault == 'missing_rule': source.with_suffix('.kicad_dru').unlink()
    else: discard_items(b, [next(z for z in b.Zones() if z.GetNetname() == 'GND')])
    field._save_field_snapshot(b, source)
    before = field._field_snapshot_inventory(b)
    q = op.plan(b, board_hint='synthetic', timeout_s=2.)
    assert not q['complete'], q
    assert field._field_snapshot_inventory(b) == before


@pytest.mark.parametrize('value', [0, -1, True, float('nan'), 10.0001])
def test_local_work_budget_is_explicitly_bounded(tmp_path, value):
    b, *_ = fixture(tmp_path)
    with pytest.raises(ValueError): op.plan(b, board_hint='synthetic', timeout_s=value)


def test_stale_proposal_cannot_overwrite_source(tmp_path):
    b, source, *_ = fixture(tmp_path)
    q = op.plan(b, board_hint='synthetic', timeout_s=10.); assert q['complete'], q
    old = next(t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK'); old.SetWidth(123456)
    before = field._field_snapshot_inventory(b)
    with pytest.raises(ValueError): op.construct_private(b, q, board_hint='synthetic')
    assert field._field_snapshot_inventory(b) == before


def test_actual_noncovered_fine_lead_has_a_full_width_terminal_throat(tmp_path):
    source, child, proposal, ids = construct(tmp_path, noncovered=True)
    result = op.receive(source, child, board_hint='synthetic', timeout_s=10.)
    assert result['ok'] and result['complete'], result
    b = pcbnew.LoadBoard(str(child))
    incoming = [i for i in b.GetTracks() if force._uid(i) in ids]
    assert len(incoming) == 2
    assert next(i for i in incoming if i.GetClass() == 'PCB_TRACK').GetWidth() == 200000


def test_new_barrel_is_not_permitted_when_retained_tracks_supply_the_join(tmp_path):
    b, source, owner, cap, rootvia = fixture(tmp_path, barrier=False)
    # Source already has a literal full-class path to its existing root.
    # No producer search result is used as authority for this negative.
    p = cap.FindPadByNumber('2').GetPosition(); r = rootvia.GetPosition()
    track(b, 'GND', (p.x/1e6, p.y/1e6), (p.x/1e6, r.y/1e6), width=.5)
    track(b, 'GND', (p.x/1e6, r.y/1e6), (r.x/1e6, r.y/1e6), width=.5)
    additive._ground_refill(b); field._save_field_snapshot(b, source)
    assert not op.plan(b, board_hint='synthetic', timeout_s=10.)['complete']
    old = {force._uid(i) for i in b.GetTracks()}
    via = pcbnew.PCB_VIA(b); via.SetNet(b.FindNet('GND'))
    via.SetPosition(rootvia.GetPosition()+pcbnew.VECTOR2I_MM(2, 0))
    via.SetWidth(500000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(via)
    child = force._copy_family(source, tmp_path/'redundant-child')
    producer.save_native_additions(child, b, {}, old, board_hint='synthetic')
    result = op.receive(source, child, board_hint='synthetic', timeout_s=10.)
    assert not result['ok'] and not result['complete'], result
