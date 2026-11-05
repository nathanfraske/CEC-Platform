"""Observed exact obstacle identities are diagnostics, never route authority."""
import json
from unittest import mock

import pcbnew
import pytest

import cec_fr as fr


def fixture(*, turn=0, layer=pcbnew.F_Cu, blocked=True):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    signal = pcbnew.NETINFO_ITEM(board, '/unrelated/supply-or-signal')
    foreign = pcbnew.NETINFO_ITEM(board, 'renamed_foreign')
    board.Add(signal)
    board.Add(foreign)
    obstacle = None
    if blocked:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('ARBITRARY_OWNER')
        board.Add(fp)
        obstacle = pcbnew.PAD(fp)
        obstacle.SetNumber('opaque-pad')
        obstacle.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        obstacle.SetShape(pcbnew.PAD_SHAPE_RECT)
        obstacle.SetSize(pcbnew.VECTOR2I_MM(1, 30))
        mask = pcbnew.LSET()
        mask.AddLayer(layer)
        obstacle.SetLayerSet(mask)
        obstacle.SetNet(foreign)
        fp.Add(obstacle)
        obstacle.SetPosition(pcbnew.VECTOR2I_MM(15, 15))
        fp.Rotate(pcbnew.VECTOR2I_MM(15, 15), pcbnew.EDA_ANGLE(90*turn, pcbnew.DEGREES_T))
    for a, b in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetWidth(50000)
        edge.SetLayer(pcbnew.Edge_Cuts)
        board.Add(edge)
    def rotate(point):
        x, y = point
        for _ in range(turn):
            x, y = 30-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    return board, signal.GetNetCode(), obstacle, rotate((5,15)), rotate((25,15)), layer


def route(context, *, diagnostics=None, caller=None):
    board, code, _, start, end, layer = context
    return fr._guarded_profiled_lastmile_legs(board, start, end, 500000, layer,
        200000, code, caller or (lambda a,b,r:fr._edge_leg_clear(board,a,b,r)),
        allow_maze=False, canonical_only=True, search_diagnostics=diagnostics)


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_observed_full_width_refusal_names_actual_rotated_native_pad(turn, layer):
    context = fixture(turn=turn, layer=layer)
    before = [(str(p.m_Uuid.AsString()), tuple(p.GetPosition()), p.GetNetCode())
        for fp in context[0].GetFootprints() for p in fp.Pads()]
    diagnostics = {}
    assert route(context, diagnostics=diagnostics) is None
    evidence = diagnostics['observed_segment_refusals']
    assert evidence['scope'] == 'observed_proposals_not_exhaustive_path_or_min_cut_proof'
    assert evidence['release_authority'] is False
    assert 1 <= len(evidence['samples']) <= evidence['sample_limit'] == 6
    hits = [hit for row in evidence['samples'] for hit in row.get('native_blockers', [])]
    assert str(context[2].m_Uuid.AsString()) in {hit['uuid'] for hit in hits}
    assert all(row['width_nm'] == 500000 and row['clearance_nm'] == 200000
        for row in evidence['samples'])
    assert len(json.dumps(diagnostics)) < 32768
    assert not list(context[0].GetTracks())
    assert before == [(str(p.m_Uuid.AsString()), tuple(p.GetPosition()), p.GetNetCode())
        for fp in context[0].GetFootprints() for p in fp.Pads()]


def test_disabled_diagnostics_do_no_identity_queries_and_still_refuse():
    context = fixture()
    with mock.patch.object(fr, '_snapshot_foreign_blockers', side_effect=AssertionError('not routing authority')) as query:
        assert route(context) is None
    query.assert_not_called()


def test_optional_diagnostics_preserve_successful_native_path_exactly():
    context = fixture(blocked=False)
    def signature(legs):
        return [(tuple(a), tuple(b), width) for a,b,width in legs]
    without = route(context)
    diagnostics = {}
    with_diagnostics = route(context, diagnostics=diagnostics)
    assert signature(without) == signature(with_diagnostics)
    assert not diagnostics


def test_unknown_diagnostic_geometry_cannot_waive_native_collision():
    context = fixture()
    diagnostics = {}
    with mock.patch.object(fr, '_snapshot_foreign_blockers', side_effect=RuntimeError('unknown diagnostic')):
        assert route(context, diagnostics=diagnostics) is None
    assert diagnostics['observed_segment_refusals']['samples']
    assert all(row.get('geometry_status') == 'unknown'
        for row in diagnostics['observed_segment_refusals']['samples'])


def test_caller_refusal_does_not_claim_foreign_obstruction_or_skip_predicate():
    context = fixture(blocked=False)
    diagnostics = {}
    with mock.patch.object(fr, '_snapshot_foreign_blockers') as query:
        assert route(context, diagnostics=diagnostics, caller=lambda *args:False) is None
    query.assert_not_called()
    evidence = diagnostics['observed_segment_refusals']
    assert set(evidence['events']) == {'caller_predicate'}
    assert all('native_blockers' not in row for row in evidence['samples'])
