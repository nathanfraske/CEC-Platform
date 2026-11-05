"""Source-owned via tees keep every real port and cannot borrow power authority."""
import json
import math
from pathlib import Path

import pcbnew
import pytest
import cec_additive_pair_repair as additions
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_barrel_reseat as endpoint
import cec_source_literal_retirement as literal_cut
import cec_source_ordinary_barrel_kernel as operation
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, *, quarter=0, name='/a/RENAMED', inner=False, foreign_zone=False):
    b = _board([], edge=(0, 0, 25, 25)); b.SetCopperLayerCount(6)
    b.Add(pcbnew.NETINFO_ITEM(b, name))
    layer = pcbnew.In2_Cu if inner else pcbnew.B_Cu
    track(b, name, (6, 8), (10, 8))
    track(b, name, (10, 8), (10, 12))
    track(b, name, (10, 8), (14, 8), layer=layer)
    track(b, name, (5, 8), (6, 8))
    track(b, name, (10, 12), (10, 13))
    track(b, name, (14, 8), (15, 8), layer=layer)
    via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I_MM(10, 8))
    via.SetWidth(600000); via.SetDrill(300000); via.SetNet(b.FindNet(name))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    b.Add(via)
    if quarter:
        for t in b.GetTracks():
            t.Rotate(pcbnew.VECTOR2I_MM(12, 12), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
    if foreign_zone:
        import cec_zone_fill as filler
        b.Add(pcbnew.NETINFO_ITEM(b, 'UNRELATED_POWER'))
        zone = pcbnew.ZONE(b); zone.SetNet(b.FindNet('UNRELATED_POWER')); zone.SetLayer(pcbnew.B_Cu)
        zone.SetLocalClearance(200000); zone.SetMinThickness(100000)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        zone.Outline().NewOutline()
        for x, y in ((18, 18), (24, 18), (24, 24), (18, 24)):
            zone.Outline().Append(x*1000000, y*1000000)
        b.Add(zone); selected = pcbnew.ZONES(); selected.append(zone)
        filler.compile_selected(b, selected, initialize_selected=True)
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(b, source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {'classes': [
        {'name': 'Default', 'track_width': .2, 'clearance': .2, 'via_diameter': .6, 'via_drill': .3}]}}))
    return source, force._uid(via), layer


def saved(tmp_path, **options):
    source, uid, layer = fixture(tmp_path, **options)
    q = operation.plan(source, via_uuid=uid, board_hint='synthetic')
    child = force._copy_family(source, tmp_path/'child')
    b = pcbnew.LoadBoard(str(source)); retired = set(q['retired_track_uuids']) | {uid}
    discard_items(b, [t for t in b.GetTracks() if force._uid(t) in retired])
    literal_cut.write_native_projection(source, child, retired, b)
    old = {force._uid(t) for t in b.GetTracks()}
    quarter = options.get('quarter', 0)
    def rotate(xy):
        angle = math.radians(-quarter*90); x, y = xy[0]-12, xy[1]-12
        return round(12+x*math.cos(angle)-y*math.sin(angle), 6), round(12+x*math.sin(angle)+y*math.cos(angle), 6)
    for face, points in ((pcbnew.F_Cu, [(6, 8), (9.5, 8), (10, 8.5)]),
                        (pcbnew.F_Cu, [(10, 12), (10, 8.5)]),
                        (layer, [(14, 8), (10.5, 8), (10, 8.5)])):
        for a, z in zip(points, points[1:]):
            track(b, q['net'], rotate(a), rotate(z), layer=face)
    via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I_MM(*rotate((10, 8.5))))
    via.SetWidth(600000); via.SetDrill(300000); via.SetNetCode(b.GetNetcodeFromNetname(q['net']))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetViaType(pcbnew.VIATYPE_THROUGH); b.Add(via)
    additions.save_native_additions(child, b, {}, old, board_hint='synthetic')
    return source, child, uid


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('inner', [False, True])
def test_real_multiface_tee_saved_replay_in_renamed_cardinal_frames(tmp_path, quarter, inner):
    source, child, uid = saved(tmp_path, quarter=quarter, name='/renamed_'+str(quarter), inner=inner)
    original = source.read_bytes()
    with pytest.raises(ValueError, match='centre_ending_chain'):
        endpoint.plan(pcbnew.LoadBoard(str(source)), source, via_uuid=uid, board_hint='synthetic')
    proof = operation.receive(source, child, via_uuid=uid, board_hint='synthetic')
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_actual_Source_departures_restored']
    assert proof['independent_existing_ordinary_receiving']['all_prior_native_terminal_partitions_preserved']
    assert not proof['release_authority'] and not proof['current_authority']
    assert source.read_bytes() == original


@pytest.mark.parametrize('name', ['+3V3', 'GND', '/USB_D_P', '/USB_D_N', '/SENSEC1_HI',
                                  '/SENSEC2_LO', '/SB_SENSE0', '/CLOCK'])
def test_power_pairs_Kelvin_and_quiet_inputs_cannot_become_ordinary_tee_scope(tmp_path, name):
    source, uid, _ = fixture(tmp_path, name=name)
    with pytest.raises(ValueError):
        operation.plan(source, via_uuid=uid, board_hint='synthetic')


@pytest.mark.parametrize('fault', ['part', 'sidecar', 'extra', 'width', 'drill', 'diameter',
    'face', 'missing_port', 'unchanged_axis', 'remote_axis', 'foreign_net', 'retained_copper'])
def test_saved_candidate_cannot_silently_change_ports_material_rules_or_geometry(tmp_path, fault):
    source, child, uid = saved(tmp_path)
    b = pcbnew.LoadBoard(str(child)); old = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    incoming = [t for t in b.GetTracks() if force._uid(t) not in old]
    via = next(t for t in incoming if t.GetClass() == 'PCB_VIA')
    traces = [t for t in incoming if t.GetClass() == 'PCB_TRACK']
    if fault == 'sidecar': child.with_suffix('.kicad_pro').write_text('{}')
    elif fault == 'part':
        f = pcbnew.FOOTPRINT(b); f.SetReference('UNOWNED'); b.Add(f)
    elif fault == 'extra': track(b, via.GetNetname(), (20, 20), (21, 20))
    elif fault == 'width': traces[0].SetWidth(199999)
    elif fault == 'drill': via.SetDrill(300001)
    elif fault == 'diameter': via.SetWidth(600001)
    elif fault == 'face': traces[0].SetLayer(pcbnew.In3_Cu)
    elif fault == 'missing_port': discard_items(b, [max(traces, key=lambda t: t.GetLength())])
    elif fault == 'unchanged_axis': via.SetPosition(pcbnew.VECTOR2I_MM(10, 8))
    elif fault == 'remote_axis': via.Move(pcbnew.VECTOR2I_MM(3, 0))
    elif fault == 'retained_copper':
        next(t for t in b.GetTracks() if force._uid(t) in old).SetWidth(200001)
    else:
        b.Add(pcbnew.NETINFO_ITEM(b, 'other')); via.SetNet(b.FindNet('other'))
    if fault != 'sidecar': pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), b)
    proof = operation.receive(source, child, via_uuid=uid, board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'], proof


@pytest.mark.parametrize('fault', ['via_group', 'track_group', 'pad', 'barrel', 'saved_floor', 'long_leg'])
def test_Source_native_contacts_must_really_be_exclusive_and_full_saved_rule_sized(tmp_path, fault):
    source, uid, _ = fixture(tmp_path)
    b = pcbnew.LoadBoard(str(source)); via = next(t for t in b.GetTracks() if force._uid(t) == uid)
    if fault.endswith('group'):
        g = pcbnew.PCB_GROUP(b); g.SetName('actual other owner')
        contact_ids = operation.plan(source, via_uuid=uid, board_hint='synthetic')['retired_track_uuids']
        g.AddItem(via if fault == 'via_group' else next(t for t in b.GetTracks() if force._uid(t) == contact_ids[0]))
        b.Add(g)
    elif fault == 'pad':
        f = pcbnew.FOOTPRINT(b); p = pcbnew.PAD(f); p.SetPosition(via.GetPosition())
        p.SetNet(via.GetNet()); p.SetSize(pcbnew.VECTOR2I_MM(1, 1)); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); f.Add(p); b.Add(f)
    elif fault == 'barrel':
        other = pcbnew.PCB_VIA(b); other.SetPosition(via.GetPosition()); other.SetNet(via.GetNet())
        other.SetWidth(600000); other.SetDrill(300000); other.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        other.SetViaType(pcbnew.VIATYPE_THROUGH); b.Add(other)
    elif fault == 'saved_floor':
        data = json.loads(source.with_suffix('.kicad_pro').read_text())
        data['board'] = {'design_settings': {'rules': {'min_via_diameter': .8}}}
        source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    else:
        track(b, via.GetNetname(), (10, 8), (22, 8))
    field._save_field_snapshot(b, source)
    with pytest.raises(ValueError):
        operation.plan(source, via_uuid=uid, board_hint='synthetic')


@pytest.mark.parametrize('extra', [{'retired_track_uuids': []}, {'allow_owned_locked': True},
    {'position_nm': [1, 2]}, {'timeout_s': 30}, {'current_amps': .01}])
def test_typed_phase_accepts_only_one_Source_identity_not_producer_permissions(tmp_path, extra):
    import root_receive_local_transaction_20261022 as transaction
    row = dict(kind='source_ordinary_barrel_kernel', candidate=str(tmp_path/'child.kicad_pcb'),
               candidate_sha256='a'*64, via_uuid='real-source-via')
    row.update(extra)
    with pytest.raises(ValueError):
        transaction.validate_phases([row])


def test_actual_phase_dispatch_freshly_recompiles_the_Source_kernel(tmp_path):
    import root_receive_local_transaction_20261022 as transaction
    source, child, uid = saved(tmp_path, inner=True)
    row = dict(kind='source_ordinary_barrel_kernel', candidate=str(child),
               candidate_sha256=force._hash(child), via_uuid=uid)
    transaction.validate_phases([row])
    received, result = transaction.receive_phase(source, source, row, 'synthetic')
    assert received == child.resolve()
    assert result['ok'] and result['complete'], result


def test_late_existing_receiver_cannot_return_a_timed_out_success(tmp_path, monkeypatch):
    source, child, uid = saved(tmp_path)
    real = operation.ordinary.receive
    def expired(*args, **kwargs):
        result = real(*args, **kwargs)
        monkeypatch.setattr(operation.time, 'monotonic', lambda: 1e12)
        return result
    monkeypatch.setattr(operation.ordinary, 'receive', expired)
    proof = operation.receive(source, child, via_uuid=uid, board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and 'deadline' in str(proof['errors'])


def test_foreign_fill_only_tampering_is_not_a_barrel_reseating_permission(tmp_path):
    source, child, uid = saved(tmp_path, foreign_zone=True)
    b = pcbnew.LoadBoard(str(child)); zone = next(iter(b.Zones()))
    poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
    for x, y in ((19, 18), (24, 18), (24, 24), (19, 24)):
        poly.Append(x*1000000, y*1000000)
    zone.SetFilledPolysList(pcbnew.B_Cu, poly)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), b)
    proof = operation.receive(source, child, via_uuid=uid, board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'], proof


def test_a_prior_plan_does_not_authorize_a_later_higher_Source_project_floor(tmp_path):
    source, child, uid = saved(tmp_path)
    old = operation.plan(source, via_uuid=uid, board_hint='synthetic')
    data = json.loads(source.with_suffix('.kicad_pro').read_text())
    data['board'] = {'design_settings': {'rules': {'min_via_diameter': .8}}}
    source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    proof = operation.receive(source, child, via_uuid=uid, board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and old['drill_nm'] == 300000
    assert 'full_saved_Source' in str(proof['errors'])
