"""Saved native contours, not counters or a caller-supplied success flag."""
import copy
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as evidence
import cec_rectilinear_copper as owner
import cec_field_coupling as field
from root_native_kelvin_contour_scope_20261012 import positive_contour_scope
from root_native_positive_contour_receiving_20261012 import receive
from root_native_publication_safety_20261012 import require_saved_grade
from test_force_sense_evidence import fixture
from test_native_publication_safety import fixture as grade_fixture


def native_contours(tmp_path, *, angle=0, missing=None):
    source = tmp_path / 'source.kicad_pcb'; child = tmp_path / 'child.kicad_pcb'
    domains = fixture(source, filtered=True, angle=angle)
    board = pcbnew.LoadBoard(str(source))
    if missing == 'RENAMED_FEED':
        # Keep the wide contour source, but actually disconnect its input
        # terminal in BOTH saved boards. A positive-looking zone cannot
        # upgrade that inherited unknown physical cut.
        pad = next(iter(board.FindFootprintByReference('POWER_IN').Pads()))
        pad.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I_MM(2, 0))
    elif missing:
        from cec_native_items import discard_items
        tracks = [t for t in board.GetTracks() if t.GetNetname() == missing]
        discard_items(board, [max(tracks, key=lambda t: t.GetLength())])
    for start, end in [((0, 0), (200, 0)), ((200, 0), (200, 200)),
                       ((200, 200), (0, 200)), ((0, 200), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*start)); edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    field._save_field_snapshot(board, source)
    tracks = [t for t in board.GetTracks() if t.GetNetname() == 'RENAMED_FEED']
    track = max(tracks, key=lambda t: t.GetLength()); uid = force._uid(track)
    plan = owner.plan(board, [uid], clearance_nm=200000, min_thickness_nm=100000,
        required_width_nm=500000, allow_locked_track_uuids=[uid],
        contour_style='chamfer45', retire_source_tracks=False)
    emitted = owner.materialize(board, plan, allow_locked_track_uuids=[uid])
    owner.fill(board, plan, emitted['zone_uuid'], timeout_s=10.)
    field._save_field_snapshot(board, child)
    return source, child, domains, [dict(plan=plan, materialized=emitted)]


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_saved_positive_cohort_is_requalified_on_cardinally_rotated_native_boards(tmp_path, angle):
    source, child, domains, plans = native_contours(tmp_path, angle=angle)
    original = (source.read_bytes(), child.read_bytes())
    with patch('cec_current_topology.board_current_domains', return_value=domains):
        before = evidence.replay(source, board_hint='explicit-fixture', timeout_s=10.)
        selected = positive_contour_scope(before)
        proof = receive(source, child, plans, board_hint='explicit-fixture')
    assert selected['permitted_nets'] == ['RENAMED_FEED', 'RENAMED_LOAD']
    assert not selected['frozen_nets']
    assert proof['ok'] is True and proof['complete'] is True, proof
    assert proof['physical_kelvin_preservation']['rebound_nets'][0]['after']['checked'] == 1
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert original == (source.read_bytes(), child.read_bytes())


def test_an_unaffected_actual_unknown_net_stays_frozen_and_unknown(tmp_path):
    source, child, domains, plans = native_contours(tmp_path, missing='RENAMED_LOAD')
    with patch('cec_current_topology.board_current_domains', return_value=domains):
        before = evidence.replay(source, board_hint='explicit-fixture', timeout_s=10.)
        selected = positive_contour_scope(before)
        proof = receive(source, child, plans, board_hint='explicit-fixture')
    assert selected['permitted_nets'] == ['RENAMED_FEED']
    assert selected['frozen_nets'] == ['RENAMED_LOAD']
    assert proof['ok'] and proof['complete'], proof
    assert proof['physical_kelvin_preservation']['coverage_after']['unknown'] == 1
    assert proof['unknown_evidence_qualified'] is False


@pytest.mark.parametrize('fault', ['missing_zone', 'duplicate_zone', 'retired_plan',
    'wrong_net', 'wrong_plan_hash', 'empty_plans', 'unlisted_track', 'moved_pad', 'changed_unknown'])
def test_a_declared_pass_cannot_hide_unreceived_or_unqualified_native_changes(tmp_path, fault):
    source, child, domains, plans = native_contours(tmp_path,
        missing='RENAMED_FEED' if fault == 'changed_unknown' else None)
    plans = copy.deepcopy(plans)
    if fault == 'missing_zone': plans[0]['materialized']['zone_uuid'] = 'not-in-saved-board'
    elif fault == 'duplicate_zone': plans.append(copy.deepcopy(plans[0]))
    elif fault == 'retired_plan': plans[0]['plan']['retire_source_tracks'] = True
    elif fault == 'wrong_net': plans[0]['plan']['net'] = 'RENAMED_LOAD'
    elif fault == 'wrong_plan_hash': plans[0]['plan']['plan_sha256'] = 'forged'
    elif fault == 'empty_plans': plans.clear()
    elif fault in ('unlisted_track', 'moved_pad'):
        board = pcbnew.LoadBoard(str(child))
        if fault == 'unlisted_track':
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(board.FindNet('RENAMED_FEED')); track.SetLayer(pcbnew.F_Cu)
            track.SetStart(pcbnew.VECTOR2I_MM(140, 140)); track.SetEnd(pcbnew.VECTOR2I_MM(141, 140))
            track.SetWidth(200000); board.Add(track)
        else:
            fp = board.FindFootprintByReference('POWER_IN')
            pad = next(iter(fp.Pads())); pad.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I_MM(1, 0))
        field._save_field_snapshot(board, child)
    with patch('cec_current_topology.board_current_domains', return_value=domains):
        proof = receive(source, child, plans, board_hint='explicit-fixture')
    assert proof['ok'] is False and proof['complete'] is False and proof['errors'], proof
    assert not proof['release_authority']


@pytest.mark.parametrize('fault', ['missing_scope', 'wrong_hash', 'success_flag'])
def test_publication_cannot_authorize_changed_evidence_from_worker_json(fault):
    grade = grade_fixture()
    grade['clipped_kelvin_comparison']['same_evidence'] = False
    grade['positive_contour_receiving'] = dict(ok=True, complete=True, release_authority=False)
    kwargs = {}
    if fault == 'wrong_hash':
        kwargs = dict(contour_construction={'source_sha256': 'wrong', 'candidate_sha256': 'candidate'},
                      board_hint='explicit-fixture')
    elif fault == 'success_flag': grade['clipped_kelvin_comparison']['fresh_requalified'] = True
    with pytest.raises(ValueError):
        require_saved_grade(grade, epoch={'digest': 'same'}, source_sha256='source',
                            candidate_sha256='candidate', **kwargs)
