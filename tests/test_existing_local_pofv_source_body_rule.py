"""Native track-body ownership is explicit; it is not a floor waiver."""
import json
import math
import os
from pathlib import Path

import pcbnew
import pytest

import cec_existing_local_pofv_pad_rule as rule
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native
from test_existing_local_pofv_pad_rule import case


def body_case(tmp_path, angle=0, mirror=False, face=pcbnew.F_Cu,
              profile='jlcpcb_6l_pofv_signal'):
    board, source, pad = case(tmp_path, angle, face, profile)
    center = pad.GetPosition()
    c, s = round(math.cos(math.radians(angle))), round(math.sin(math.radians(angle)))
    sign = -1 if mirror else 1

    def point(x, y=0):
        x *= sign
        return center + pcbnew.VECTOR2I(c*x-s*y, s*x+c*y)

    track = pcbnew.PCB_TRACK(board)
    track.SetNet(pad.GetNet()); track.SetLayer(face); track.SetWidth(200000)
    track.SetStart(center); track.SetEnd(point(1200000)); board.Add(track)
    return board, source, pad, track, point(750000, 1)


def seat(board, pad, track, at, **kwargs):
    return fr._via_spot_clear(board, at, 300000, 200000, {pad.GetNetCode()},
        drill_nm=200000, net_code=pad.GetNetCode(),
        local_pofv_source_track_body=dict(pad=pad, track=track), **kwargs)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('profile', ['jlcpcb_6l_pofv_signal', 'jlcpcb_6l_pofv_high_current'])
def test_real_native_subinterval_uses_only_existing_rule(tmp_path, angle, mirror, face, profile):
    b, source, pad, track, at = body_case(tmp_path, angle, mirror, face, profile)
    before = source.read_bytes(), force._sidecars(source), rule._floors(b)
    assert not fr._via_spot_clear(b, at, 300000, 200000, {pad.GetNetCode()},
        drill_nm=200000, net_code=pad.GetNetCode())
    detail = {}
    assert seat(b, pad, track, at, report=detail), detail
    proof = detail['existing_native_local_pad_rule']
    scope = proof['bounded_source_smd_track_body']
    assert scope['track_uuid'] == force._uid(track)
    assert scope['layer_id'] == face and scope['via_axis_nm'] == list(at)
    assert scope['actual_native_track_required']
    assert not proof['fabrication_or_current_or_release_qualified']
    assert before == (source.read_bytes(), force._sidecars(source), rule._floors(b))


@pytest.mark.parametrize('fault', ['missing_track', 'wrong_track_net', 'wrong_face',
    'no_owned_start', 'too_far', 'outside_body', 'outside_interval', 'noncanonical',
    'fractional_projection', 'partial_overlap', 'contained_pad', 'changed_pad',
    'DNP', 'missing_rule', 'missing_group', 'locked_group', 'profile', 'floor',
    'wrong_pad', 'missing_drill', 'undersized_drill', 'no_saved_source'])
def test_body_context_cannot_be_nearness_or_a_detached_proposal(tmp_path, fault):
    b, source, pad, track, at = body_case(tmp_path)
    center = pad.GetPosition()
    if fault == 'missing_track':
        detached = pcbnew.PCB_TRACK(b)
        detached.SetNet(track.GetNet()); detached.SetLayer(track.GetLayer())
        detached.SetStart(track.GetStart()); detached.SetEnd(track.GetEnd()); detached.SetWidth(track.GetWidth())
        track = detached
    elif fault == 'wrong_track_net': track.SetNet(b.FindNet('obstruction'))
    elif fault == 'wrong_face': track.SetLayer(pcbnew.B_Cu)
    elif fault == 'no_owned_start': track.SetStart(center + pcbnew.VECTOR2I(300000, 0))
    elif fault == 'too_far':
        track.SetEnd(center + pcbnew.VECTOR2I(2000000, 0)); at = center + pcbnew.VECTOR2I(1600000, 1)
    elif fault == 'outside_body': at += pcbnew.VECTOR2I(0, 100000)
    elif fault == 'outside_interval': at = track.GetEnd() + pcbnew.VECTOR2I(1, 0)
    elif fault == 'noncanonical': track.SetEnd(track.GetEnd() + pcbnew.VECTOR2I(0, 1))
    elif fault == 'fractional_projection':
        track.SetEnd(center + pcbnew.VECTOR2I(1200000, 1200000)); at = center + pcbnew.VECTOR2I(750000, 750001)
    elif fault == 'partial_overlap': at = center + pcbnew.VECTOR2I(250000, 0)
    elif fault == 'contained_pad': at = center
    elif fault == 'changed_pad': pad.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'DNP': pad.GetParentFootprint().SetAttributes(pad.GetParentFootprint().GetAttributes() | pcbnew.FP_DNP)
    elif fault == 'missing_rule': source.with_suffix('.kicad_dru').unlink()
    elif fault == 'missing_group':
        group = next(g for g in b.Groups() if g.GetName() == rule.GROUP)
        for item in list(group.GetItems()): group.RemoveItem(item)
        b.Remove(group)
    elif fault == 'locked_group': next(g for g in b.Groups() if g.GetName() == rule.GROUP).SetLocked(True)
    elif fault == 'profile':
        props = b.GetProperties(); props['CEC_FAB_PROFILE'] = 'unknown'; b.SetProperties(props)
    elif fault == 'floor': b.GetDesignSettings().m_ViasMinSize += 1
    elif fault == 'wrong_pad': pad = next(p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber() == '3')
    elif fault == 'no_saved_source': b.SetFileName('')
    before = source.read_bytes(), rule._floors(b)
    if fault in ('missing_drill', 'undersized_drill'):
        assert not fr._via_spot_clear(b, at, 300000, 200000, {pad.GetNetCode()},
            drill_nm=None if fault == 'missing_drill' else 100000, net_code=pad.GetNetCode(),
            local_pofv_source_track_body=dict(pad=pad, track=track))
    else:
        assert not seat(b, pad, track, at)
    assert before == (source.read_bytes(), rule._floors(b))


@pytest.mark.parametrize('fault', ['extra_exemption', 'pad_context', 'contained_context',
    'dogbone_context', 'existing_hole', 'native_padstack', 'extra_key'])
def test_body_context_is_exclusive(tmp_path, fault):
    b, source, pad, track, at = body_case(tmp_path)
    context = dict(pad=pad, track=track)
    kwargs = {}
    codes = {pad.GetNetCode()}
    if fault == 'extra_exemption': codes.add(b.FindNet('obstruction').GetNetCode())
    elif fault == 'pad_context': kwargs['local_pofv_pad'] = pad
    elif fault == 'contained_context': kwargs['local_pofv_contained_pad'] = pad
    elif fault == 'dogbone_context': kwargs['local_pofv_dogbone'] = dict(pad=pad, start=pad.GetPosition(), layer=pad.GetLayer())
    elif fault == 'existing_hole': kwargs['existing_via_uuid'] = 'not-a-source-hole'
    elif fault == 'native_padstack': kwargs['native_padstack_via'] = next(v for v in b.GetTracks() if v.GetClass() == 'PCB_VIA')
    else: context['waive_board_minimum'] = True
    assert not fr._via_spot_clear(b, at, 300000, 200000, codes,
        drill_nm=200000, net_code=pad.GetNetCode(), local_pofv_source_track_body=context, **kwargs)


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
    pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu])
def test_positive_body_owner_still_checks_every_copper_face(tmp_path, layer):
    b, source, pad, track, at = body_case(tmp_path)
    assert seat(b, pad, track, at)
    other = pcbnew.PCB_TRACK(b); other.SetNet(b.FindNet('obstruction')); other.SetLayer(layer)
    other.SetWidth(200000); other.SetStart(at - pcbnew.VECTOR2I(0, 500000))
    other.SetEnd(at + pcbnew.VECTOR2I(0, 500000)); b.Add(other)
    detail = {}
    assert not seat(b, pad, track, at, report=detail)
    assert detail['reason'] == 'foreign copper excludes via land'
    assert detail['blockers'] and detail['blockers'][0]['net'] == 'obstruction'


@pytest.mark.parametrize('at_same_origin', [False, True])
def test_body_owner_never_grants_hole_spacing_exception(tmp_path, at_same_origin):
    b, source, pad, track, at = body_case(tmp_path)
    via = pcbnew.PCB_VIA(b); via.SetPosition(at if at_same_origin else at + pcbnew.VECTOR2I(150000, 0))
    via.SetNet(pad.GetNet()); via.SetWidth(300000); via.SetDrill(200000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(via)
    detail = {}; assert not seat(b, pad, track, at, report=detail)
    assert detail['reason'] == ('existing via occupies drill origin' if at_same_origin else 'existing via violates drill spacing')


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_saved_native_rule_still_requires_real_membership_and_body_owner(tmp_path, face):
    b, source, pad, track, at = body_case(tmp_path, face=face)
    assert seat(b, pad, track, at)
    via = pcbnew.PCB_VIA(b); via.SetPosition(at); via.SetNet(pad.GetNet())
    via.SetWidth(300000); via.SetDrill(200000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(via)
    assert fab.local_pofv_via_decision(b, via, allow_source_track_body=True)[0]
    group = next(g for g in b.Groups() if g.GetName() == rule.GROUP); group.AddItem(via)
    child = force._copy_family(source, tmp_path/'body-member'); field._save_field_snapshot(b, child)
    build = os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build: pytest.skip('native factory control needs the explicit native reporting build')
    def faults(path, name):
        out = tmp_path/(name+'.json')
        r = native.run(path, out, reporting_build=Path(build), timeout_s=10.)
        assert r['ok'] and r['complete'] and not r['native_inventory']['potentially_truncated']
        return {q['type'] for q in json.loads(out.read_text())['violations']
            if q['type'] in ('via_diameter', 'drill_out_of_range', 'annular_width')
            and any(i.get('uuid') == force._uid(via) for i in q['items'])}
    assert not faults(child, 'with-member')
    loaded = pcbnew.LoadBoard(str(child)); actual = next(v for v in loaded.GetTracks() if force._uid(v) == force._uid(via))
    next(g for g in loaded.Groups() if g.GetName() == rule.GROUP).RemoveItem(actual)
    outside = force._copy_family(child, tmp_path/'outside-member'); field._save_field_snapshot(loaded, outside)
    assert faults(outside, 'without-member') == {'via_diameter', 'drill_out_of_range', 'annular_width'}
