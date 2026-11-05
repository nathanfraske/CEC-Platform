"""Placement cannot use undersized courtyards as electrical-clearance proof."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_placement_geometry as geometry
import cec_full_pipeline as pipeline


def row(kind, ids=('p1', 'p2')):
    return {'type': kind, 'severity': 'error', 'items': [
        {'uuid': uid, 'description': 'arbitrary localized label'} for uid in ids]}


def test_pad_copper_is_gated_even_with_no_courtyard_failure():
    result = geometry.classify_drc({'violations': [row('shorting_items'), row('clearance')]}, {'p1', 'p2'})
    assert not result['ok'] and result['courtyard_count'] == 0
    assert result['pad_copper_count'] == 2 and result['violation_count'] == 2


def test_assembly_and_copper_are_distinct_and_all_findings_retained():
    result = geometry.classify_drc({'violations': [row('courtyards_overlap')] +
        [row('clearance')] * 12}, {'p1', 'p2'})
    assert result['courtyard_count'] == 1 and result['pad_copper_count'] == 12
    assert len(result['violations']) == 10 and len(result['findings']) == 13


def test_routing_findings_do_not_masquerade_as_pad_placement_failure():
    result = geometry.classify_drc({'violations': [row('clearance', ('p1', 'track')),
        row('unconnected_items'), row('silk_overlap')]}, {'p1', 'p2'})
    assert result['ok']


@pytest.mark.parametrize('data', [[], {}, {'violations': None}])
def test_malformed_native_evidence_fails_closed(data):
    with pytest.raises(ValueError):
        geometry.classify_drc(data, set())


def test_native_error_and_timeout_fail_closed():
    import cec_synth_pipeline as synth
    with mock.patch.object(geometry, 'evaluate', side_effect=TimeoutError('bounded timeout')):
        result = synth._oracle_courtyard_overlaps('unused')
    assert not result['ok'] and 'bounded timeout' in result['violations'][0]


@pytest.mark.parametrize('refs,anchors,expected', [
    (['A', 'B'], ['A', 'B'], False), (['A', 'B'], ['A'], True),
    (['A', 'A'], [], False)])
def test_only_immutable_pad_conflicts_stop_placement_search(refs, anchors, expected):
    evidence = {'findings': [{'domain': 'pad_copper', 'type': 'shorting_items',
                             'items': [{'ref': ref} for ref in refs]}]}
    assert geometry.fixed_pad_conflicts(evidence, anchors)['ok'] is expected


def test_fixed_conflict_reports_exact_evidence_without_starting_craft():
    evidence = {'findings': [{'domain': 'pad_copper', 'type': 'clearance',
        'items': [{'ref': 'A'}, {'ref': 'B'}]}]}
    with pytest.raises(pipeline.PipelineBlocked, match='joint interface ECO') as exc:
        pipeline._require_fixed_anchor_copper(SimpleNamespace(pins={'A': 'locked', 'B': 'locked'}),
                                              'unused', evidence=evidence)
    assert exc.value.failure_evidence['physical_geometry'] == evidence


def setup_resume(tmp_path, *, angle=0):
    authority = tmp_path / 'policy.json'
    authority.write_text('current')
    from cec_synth_pipeline import Placement
    source = Placement(W=25, H=15, pads_by_net={}, value={},
        pos={'CONTACT_A': (5, 8, angle, 1, 1), 'CONTACT_B': (13, 8, angle, 1, 1)})
    cfg = SimpleNamespace(board='synthetic-family', pins={}, params={})
    def bind(config, w, h):
        assert (w, h) == (25, 15)
        anchors = {'CONTACT_A': (5, 8, 0), 'CONTACT_B': (13, 8, 0)}
        config.pins.update(anchors)
        return anchors
    engine = SimpleNamespace(read_placement=mock.Mock(return_value=source),
                             _bind_declared_interface_anchors=bind)
    provenance = {'kind': 'pipeline_placement_review', 'family': cfg.board,
        'context': {'pins': {}, 'outline_mm': [25, 15]},
        'sources': [{'path': str(authority), 'sha256': pipeline.sha256_file(authority)}]}
    return cfg, engine, provenance, source


@pytest.mark.parametrize('legacy', [False, True])
def test_review_resume_rebinds_complete_row_before_any_repair(tmp_path, legacy):
    cfg, engine, provenance, source = setup_resume(tmp_path, angle=360)
    if legacy:
        provenance = {'kind': 'pipeline_placement_review'}
    report = pipeline._restore_placement_resume_context(engine, cfg, 'board', provenance)
    assert report['ok'] and set(cfg.pins) == set(source.pos)
    assert cfg.params['selected_outline_mm'] == [25, 15]


def test_resumed_row_drift_cannot_silently_drop_anchors(tmp_path):
    cfg, engine, provenance, source = setup_resume(tmp_path)
    source.pos['CONTACT_A'] = (4.4, 8, 0, 1, 1)
    with pytest.raises(pipeline.PipelineBlocked, match='mechanical anchors') as exc:
        pipeline._restore_placement_resume_context(engine, cfg, 'board', provenance)
    assert exc.value.failure_evidence['drift'][0]['ref'] == 'CONTACT_A'
    assert source.pos['CONTACT_A'] == (4.4, 8, 0, 1, 1)  # not an implicit ECO


@pytest.mark.parametrize('defect', ['family', 'source', 'outline', 'pins'])
def test_review_geometric_context_is_not_unchecked_authority(tmp_path, defect):
    cfg, engine, provenance, _ = setup_resume(tmp_path)
    if defect == 'family': provenance['family'] = 'different'
    if defect == 'source': (tmp_path/'policy.json').write_text('changed')
    if defect == 'outline': provenance['context']['outline_mm'] = [24, 15]
    if defect == 'pins': provenance['context']['pins'] = []
    with pytest.raises(ValueError):
        pipeline._restore_placement_resume_context(engine, cfg, 'board', provenance)


def test_rehydrated_materializer_normalizes_ids_before_prefix_admission(tmp_path):
    import cec_synth_pipeline as synth
    events = []
    candidate = SimpleNamespace(source_board='source')
    with mock.patch.object(synth, '_materialize_rehydrated_board',
            side_effect=lambda *args: events.append('write') or str(tmp_path/'board')), \
         mock.patch.object(synth, '_normalize_materialized_item_ids',
            side_effect=lambda *args: events.append('identities')), \
         mock.patch.object(synth, '_admit_materialized_power_prefix',
            side_effect=lambda *args: events.append('prefix')):
        synth.materialize(candidate, None, str(tmp_path/'board'))
    assert events == ['write', 'identities', 'prefix']


@pytest.mark.parametrize('gap,same_net,back,expected', [
    (-.5, False, False, False), (-.5, True, False, True),
    (-.5, False, True, True), (.2, False, False, False), (.6, False, False, True)])
def test_native_pad_gate_honors_layers_nets_and_current_custom_rules(
        tmp_path, gap, same_net, back, expected):
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    corners = [(0, 0), (20, 0), (20, 15), (0, 15), (0, 0)]
    for start, end in zip(corners, corners[1:]):
        edge = pcbnew.PCB_SHAPE()
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*start))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
        edge.SetWidth(pcbnew.FromMM(.05))
        board.Add(edge)
    nets = []
    for name in ('NET_A', 'NET_B'):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets.append(net)
    for i, x in enumerate((5., 7. + gap)):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('ARBITRARY_' + str(i))
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, 5))
        pad = pcbnew.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(2., 1.))
        pad.SetPosition(fp.GetPosition())
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(nets[0 if same_net else i])
        fp.Add(pad)
        board.Add(fp)
        if i and back:
            fp.Flip(fp.GetPosition(), False)
    path = tmp_path/'board.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix('.kicad_pro').write_text(json.dumps({
        'board': {'design_settings': {'rule_severities': {'clearance': 'error'}}},
        'net_settings': {'classes': [{'name': 'Default', 'clearance': .1}]}}))
    path.with_suffix('.kicad_dru').write_text(
        '(version 1)\n(rule "fixture clearance" (constraint clearance (min 0.5mm)))\n')
    before = path.read_bytes()
    result = geometry.evaluate(path)
    assert result['ok'] is expected
    assert result['courtyard_count'] == 0
    assert path.read_bytes() == before
    if not expected:
        assert result['pad_copper_count'] > 0
        assert {item['ref'] for row in result['findings'] for item in row['items']} == {
            'ARBITRARY_0', 'ARBITRARY_1'}


@pytest.mark.parametrize('angle', [0, 37, 90, 180, 270])
def test_native_copper_interval_follows_rotated_axis_without_aabb_inflation(angle):
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    fp = pcbnew.FOOTPRINT(board)
    fp.SetPosition(pcbnew.VECTOR2I_MM(31, -75))
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(2., 1.))
    pad.SetPosition(fp.GetPosition())
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    fp.Add(pad)
    fp.SetOrientationDegrees(angle)
    before = (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientationDegrees())
    assert geometry.footprint_copper_interval(fp, axis_angle_deg=angle) == pytest.approx([-1, 1], abs=1e-6)
    assert (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientationDegrees()) == before
