"""Real native three-edge RC contacts; only external canonical export is stubbed.

The imported fixture supplies a fresh complete manufacturer/canonical RC node,
not a cached observer verdict. These tests never admit a cut or saved repair.
"""
import copy
import hashlib

import pcbnew
import pytest

import cec_measurement_filter_span as op
import cec_force_current as force
from test_measurement_filter_span import fixture


def elbow(tmp_path, monkeypatch, *, quarter=0, mirror=False, translate=(0, 0), renamed=False):
    f = fixture(tmp_path, monkeypatch); b = f['board']
    for track in f['tracks']:
        b.Remove(track)
    paths = [
        ((10, 10), (10, 11.1)),                         # retained input launch
        ((10, 11.1), (10.08, 11.1044)),                 # short retained seed
        ((10.08, 11.1044), (10.48, 11.1044)),           # left outer
        ((10.48, 11.1044), (10.48, 11.3044)),           # middle
        ((10.48, 11.3044), (13.78, 11.3044)),           # right outer
        ((13.78, 11.3044), (14.1275, 12.1044)),         # retained right seed
        ((14.1275, 12.1044), (12, 14)),
        ((12, 14), (12, 18)),
        ((12, 18), (12, 20)),
        ((12, 18), (10, 18)),
    ]
    tracks = []
    for a, z in paths:
        track = pcbnew.PCB_TRACK(b); track.SetLayer(pcbnew.F_Cu)
        track.SetNet(f['root'].GetNet()); track.SetWidth(250000); track.SetLocked(True)
        track.SetStart(pcbnew.VECTOR2I_MM(*a)); track.SetEnd(pcbnew.VECTOR2I_MM(*z))
        b.Add(track); tracks.append(track)
    if renamed:
        refs = {fp.GetReference(): 'new-'+str(i) for i, fp in enumerate(b.GetFootprints())}
        for fp in b.GetFootprints():
            fp.SetReference(refs[fp.GetReference()])
        text = f['schematic'].read_text()
        for old, new in refs.items():
            text = text.replace('"'+old+'"', '"'+new+'"')
        f['schematic'].write_text(text)
        def names(value):
            for i, entry in enumerate(value):
                if type(entry) is list:
                    names(entry)
                elif type(entry) is str and entry in refs:
                    value[i] = refs[entry]
        names(f['tree'])
        for domain in f['domains'].values():
            for key in ('source_refs', 'sink_refs', 'authority_refs'):
                domain[key] = [refs[ref] for ref in domain[key]]
    for fp in b.GetFootprints():
        if mirror:
            for pad in fp.Pads():
                pad.SetPosition(pcbnew.VECTOR2I(40000000-pad.GetPosition().x, pad.GetPosition().y))
        fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        fp.Move(pcbnew.VECTOR2I(*translate))
    for track in tracks:
        if mirror:
            track.SetStart(pcbnew.VECTOR2I(40000000-track.GetStart().x, track.GetStart().y))
            track.SetEnd(pcbnew.VECTOR2I(40000000-track.GetEnd().x, track.GetEnd().y))
        track.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        track.Move(pcbnew.VECTOR2I(*translate))
    f.update(tracks=tracks, cuts=tracks[2:5], span=tracks[3])
    save(f)
    return f


def save(f):
    pcbnew.SaveBoard(str(f['source']), f['board'])


def observe(f, **kwargs):
    args = dict(board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        span_uuids=[force._uid(t) for t in reversed(f['cuts'])],
        expected_source_sha256=force._hash(f['source']))
    args.update(kwargs)
    return op.plan_elbow(f['board'], f['source'], **args)


def add_track(f, a, z, *, net=None, width=250000):
    t = pcbnew.PCB_TRACK(f['board']); t.SetNet(net or f['root'].GetNet())
    t.SetLayer(pcbnew.F_Cu); t.SetWidth(width)
    t.SetStart(pcbnew.VECTOR2I_MM(*a)); t.SetEnd(pcbnew.VECTOR2I_MM(*z))
    f['board'].Add(t)
    return t


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_native_renamed_translated_cardinal_elbow_is_observation_only(tmp_path, monkeypatch, quarter, mirror):
    f = elbow(tmp_path, monkeypatch, quarter=quarter, mirror=mirror,
        translate=(1234567, -2345678), renamed=True)
    raw = f['source'].read_bytes(); binding = op.row._source_binding(f['board'])
    q = observe(f)
    assert q['complete'] and q['scope'] == 'source_rc_filter_internal_elbow_observation'
    assert q['middle_span_uuid'] == force._uid(f['span'])
    assert set(q['internal_span_uuids']) == {force._uid(t) for t in f['cuts']}
    assert sorted(len(p['contacts']) for p in q['retained_ports']) == [1, 2]
    assert q['redundant_contact']['upper_minus_middle_lower_empty'] is True
    assert q['redundant_contact']['lower_contours'] and q['redundant_contact']['upper_contours']
    assert len(q['retained_components']) == 2
    assert not set(q['retained_components'][0]) & set(q['retained_components'][1])
    assert sorted(map(len, q['retained_terminal_uuids'])) == [1, 2]
    assert len(q['Source_node_observation']['node_pad_uuids']) == 3
    assert q['source_width_nm'] == 250000 and q['clearance_nm'] == 200000
    assert all(r['locked'] for r in q['source_cut_processes'])
    for port in q['retained_ports']:
        for contact in port['contacts']:
            assert contact['lower_contours'] and contact['upper_contours']
            assert contact['source_node'][0] == 'segment' and contact['width_nm'] == 250000
            assert contact['locked'] and contact['layer'] == pcbnew.F_Cu
    assert not any(q[k] for k in ('retirement_authority', 'current_authority',
        'kelvin_qualified', 'route_admission', 'release_authority'))
    assert q['saved_independent_source_cut_additions_and_absolute_measurement_receiving_required']
    assert f['source'].read_bytes() == raw and op.row._source_binding(f['board']) == binding


def test_default_single_span_rejects_same_outer_overlap_and_keeps_middle_semantics(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    args = dict(board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        expected_source_sha256=force._hash(f['source']))
    with pytest.raises(ValueError, match='unowned_interior_contact'):
        op.plan(f['board'], f['source'], span_uuid=force._uid(f['cuts'][2]), **args)
    q = op.plan(f['board'], f['source'], span_uuid=force._uid(f['span']), **args)
    assert q['scope'] == 'source_rc_filter_internal_span_observation'
    assert len(q['retained_endcaps']) == 2 and 'internal_span_uuids' not in q


@pytest.mark.parametrize('fault', ['duplicate', 'partial', 'extra', 'missing', 'malformed', 'string',
    'width', 'lock', 'layer', 'group', 'noncanonical', 'not_short_middle', 'cut', 'stale'])
def test_exact_complete_source_cut_and_process_required(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); ids = [force._uid(t) for t in f['cuts']]
    args = {}
    if fault == 'duplicate': ids[1] = ids[0]
    elif fault == 'partial': ids.pop()
    elif fault == 'extra': ids.append(force._uid(f['tracks'][0]))
    elif fault == 'missing': ids[1] = '00000000-0000-0000-0000-000000000000'
    elif fault == 'malformed': ids[0] = 'not-an-identity'
    elif fault == 'string': ids = ','.join(ids)
    elif fault == 'width': f['cuts'][0].SetWidth(300000)
    elif fault == 'lock': f['cuts'][0].SetLocked(False)
    elif fault == 'layer': f['cuts'][0].SetLayer(pcbnew.B_Cu)
    elif fault == 'group':
        g = pcbnew.PCB_GROUP(f['board']); f['board'].Add(g); g.AddItem(f['cuts'][0])
    elif fault == 'noncanonical':
        t = f['cuts'][0]; t.SetStart(t.GetStart()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'not_short_middle':
        f['cuts'][0].SetStart(f['cuts'][0].GetEnd()-pcbnew.VECTOR2I(100000, 0))
    elif fault == 'cut': f['board'].Remove(f['span'])
    elif fault == 'stale': args['expected_source_sha256'] = '0'*64
    save(f)
    with pytest.raises(ValueError): observe(f, span_uuids=ids, **args)


@pytest.mark.parametrize('fault', ['third_contact', 'end_branch', 'nearby_not_joined', 'points_into_cut',
    'pad', 'barrel', 'fill', 'foreign', 'bypass_loop', 'orphan', 'unsupported_overlap'])
def test_real_native_contacts_not_bbox_or_component_count_permission(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch)
    if fault == 'third_contact': add_track(f, (12, 11.3044), (12, 14))
    elif fault == 'end_branch': add_track(f, (10.08, 11.1044), (9, 11.1044))
    elif fault == 'nearby_not_joined':
        # It touches the cap but is NOT the seed's literal endpoint neighbor.
        add_track(f, (10.14, 10.9), (10.14, 10))
    elif fault == 'points_into_cut':
        t = f['tracks'][0]; t.SetStart(pcbnew.VECTOR2I_MM(10.2, 10.9))
    elif fault == 'pad': f['root'].SetPosition(pcbnew.VECTOR2I_MM(12, 11.3044))
    elif fault == 'barrel':
        v = pcbnew.PCB_VIA(f['board']); v.SetNet(f['root'].GetNet()); v.SetWidth(600000)
        v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetPosition(pcbnew.VECTOR2I_MM(12, 11.3044)); f['board'].Add(v)
    elif fault == 'fill':
        z = pcbnew.ZONE(f['board']); z.SetNet(f['root'].GetNet()); z.SetLayer(pcbnew.F_Cu)
        z.Outline().NewOutline()
        for p in [(11, 11), (13, 11), (13, 12), (11, 12)]:
            z.Outline().Append(*[int(x*1e6) for x in p])
        f['board'].Add(z)
    elif fault == 'foreign':
        add_track(f, (12, 11), (12, 11.6), net=f['owner'].FindPadByNumber('6').GetNet())
    elif fault == 'bypass_loop': add_track(f, (10, 10), (12, 14))
    elif fault == 'orphan': add_track(f, (50, 50), (51, 50))
    elif fault == 'unsupported_overlap':
        # Keep a canonical three-edge chain, but its outer caps no longer meet.
        f['cuts'][1].SetEnd(f['cuts'][1].GetEnd()+pcbnew.VECTOR2I(0, 100000))
        f['cuts'][2].SetStart(f['cuts'][2].GetStart()+pcbnew.VECTOR2I(0, 100000))
        f['cuts'][2].SetEnd(f['cuts'][2].GetEnd()+pcbnew.VECTOR2I(0, 100000))
        f['tracks'][5].SetStart(f['tracks'][5].GetStart()+pcbnew.VECTOR2I(0, 100000))
    save(f)
    with pytest.raises(ValueError): observe(f)


@pytest.mark.parametrize('seconds', [True, 0, -1, 10.01, float('nan'), float('inf')])
def test_explicit_constituent_deadline_range_is_unchanged(tmp_path, monkeypatch, seconds):
    f = elbow(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='bounded_named'): observe(f, timeout_s=seconds)


def test_middle_canonical_observer_uses_only_remaining_lease(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); actual = op.plan; calls = []
    def capture(*args, **kwargs):
        calls.append(kwargs.copy())
        return actual(*args, **kwargs)
    monkeypatch.setattr(op, 'plan', capture)
    observe(f)
    assert len(calls) == 1 and 0 < calls[0]['timeout_s'] < 10
    assert calls[0]['span_uuid'] == force._uid(f['span'])


def test_final_contact_work_cannot_outlive_constituent_deadline(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); actual = op._elbow_contours
    def late(*args, **kwargs):
        result = actual(*args, **kwargs)
        monkeypatch.setattr(op.time, 'monotonic', lambda: args[1]+1.)
        return result
    monkeypatch.setattr(op, '_elbow_contours', late)
    with pytest.raises(ValueError, match='deadline'): observe(f)


@pytest.mark.parametrize('fault', ['source', 'schematic', 'exporter', 'native', 'code'])
def test_source_and_proof_drift_during_geometry_cannot_be_rebound(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); actual = op.plan
    def changed(*args, **kwargs):
        q = actual(*args, **kwargs)
        if fault == 'source': f['source'].write_text(f['source'].read_text()+'\n')
        elif fault == 'schematic': f['schematic'].write_text(f['schematic'].read_text()+'\n')
        elif fault == 'exporter':
            from pathlib import Path
            Path(q['source_context']['exporter']['exporter']).write_bytes(b'changed tool')
        elif fault == 'native': f['owner'].SetValue('changed')
        elif fault == 'code':
            identity = copy.deepcopy(q['code_identity']); identity['changed'] = 'not source'
            monkeypatch.setattr(op.force, '_code_identity', lambda: identity)
        return q
    monkeypatch.setattr(op, 'plan', changed)
    with pytest.raises(ValueError, match='source_family_code_or_export_changed'): observe(f)


def test_fresh_canonical_export_each_call_ignores_no_source_role(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); actual = op.source_roles._export; calls = []
    def fresh(*args):
        tree, proof = actual(*args)
        calls.append(1)
        proof['netlist_sha256'] = hashlib.sha256(str(len(calls)).encode()).hexdigest()
        return tree, proof
    monkeypatch.setattr(op.source_roles, '_export', fresh)
    first = observe(f); second = observe(f)
    assert len(calls) == 2
    assert first['source_cut_nodes'] == second['source_cut_nodes']
    assert (first['Source_node_observation']['source_context']['exporter']['netlist_sha256']
        != second['Source_node_observation']['source_context']['exporter']['netlist_sha256'])
    # A real canonical role change is not a generated clock/hash difference.
    f['schematic'].write_text(f['schematic'].read_text().replace('(pin input ', '(pin output '))
    with pytest.raises(ValueError): observe(f)


def test_no_geometry_or_current_override_is_accepted(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    with pytest.raises(TypeError): observe(f, current=0.001)
    with pytest.raises(TypeError): observe(f, allow_third_contact=True)


def test_native_positive_sliver_is_not_waived_by_area_tolerance(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); actual = op._elbow_intersection
    outer_ids = {force._uid(f['cuts'][0]), force._uid(f['cuts'][2])}
    def with_sliver(a, b, outside=False):
        polygon = actual(a, b, outside)
        if outside and {force._uid(a), force._uid(b)} == outer_ids:
            sliver = pcbnew.SHAPE_POLY_SET(); sliver.NewOutline()
            for x, y in [(50000000, 50000000), (50000100, 50000000), (50000000, 50000100)]:
                sliver.Append(x, y)
            assert op._elbow_positive(sliver)
            polygon.BooleanAdd(sliver)
            assert polygon.OutlineCount() == 2
        return polygon
    monkeypatch.setattr(op, '_elbow_intersection', with_sliver)
    with pytest.raises(ValueError, match='redundant_cap_contact_required'): observe(f)


def test_actual_cut_clearance_cannot_inherit_smaller_middle_item_gap(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); actual = op.fr._foreign_clearance_resolver
    outer_uid = force._uid(f['cuts'][0])
    def resolver(board):
        resolve = actual(board)
        return lambda item, layer: 300000 if force._uid(item) == outer_uid else resolve(item, layer)
    monkeypatch.setattr(op.fr, '_foreign_clearance_resolver', resolver)
    q = observe(f)
    assert q['clearance_nm'] == 300000 and q['cut_native_item_clearance_nm'][outer_uid] == 300000
