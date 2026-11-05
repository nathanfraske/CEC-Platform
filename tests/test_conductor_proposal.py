import math
import pytest
from cec_conductor_proposal import normalize_terminal_paths


def cleaned(plan, contacts=(), fixed=(), layer_key=str):
    parts, report = normalize_terminal_paths(plan,
        anchored_at=lambda p, tag: (*p, layer_key(tag)) in contacts,
        fixed_points=fixed, layer_key=layer_key)
    return [s for _, s in parts], report


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('offset', [(0, 0), (113, -54)])
def test_offset_pickup_and_relocated_transition_trim_only_virtual_leaves(turn, offset):
    def xy(p):
        x, y = p
        for _ in range(turn):
            x, y = -y, x
        return x+offset[0], y+offset[1]
    # The pickup hits the collector at x=2, not its old extremity x=0.
    # Reversed duplicate declarations must not make that dead leaf a cycle.
    plan = [(0, 0, 10, 0, 3, 'route'), (2, 0, 0, 0, 3, 'route'),
            (2, 6, 2, 0, 1, 'route'), (10, 0, 10, 8, 2, 'route')]
    plan = [(*xy(s[:2]), *xy(s[2:4]), *s[4:]) for s in plan]
    contacts = {(*xy((2, 6)), 'route'), (*xy((10, 8)), 'route')}
    for ordered in (plan, [(*s[2:4], *s[:2], *s[4:]) for s in reversed(plan)]):
        result, receipt = cleaned(ordered, contacts)
        assert receipt['trimmed_segments'] == 1
        assert receipt['removed_virtual_length_mm'] == 2
        assert not receipt['release_authority']
        assert sum(math.dist(s[:2], s[2:4]) for s in result) == 22
        assert {s[4] for s in result} == {1, 2, 3}
        assert xy((0, 0)) not in {p for s in result for p in (s[:2], s[2:4])}


def test_same_layer_branch_crossings_are_contacts_but_other_layer_crossings_are_not():
    plan = [(0, 0, 10, 0, 2, 'main'), (5, -5, 5, 5, 1, 'main'),
            (2, -3, 2, 3, 1, 'other')]
    contacts = {(0, 0, 'main'), (5, -5, 'main'), (5, 5, 'main')}
    result, report = cleaned(plan, contacts)
    assert report['removed_virtual_length_mm'] == 5
    assert any(s[:2] == (2, -3) and s[2:4] == (2, 3) for s in result)
    assert all((10, 0) not in (s[:2], s[2:4]) for s in result)


def test_declared_array_and_cross_layer_transition_remain_fixed():
    plan = [(0, 0, 10, 0, 2, 'top'), (10, 0, 10, 8, 2, 'inner'),
            (10, 4, 14, 4, 2, 'inner')]
    result, _ = cleaned(plan, {(0, 0, 'top'), (10, 8, 'inner')}, fixed=[(14, 4, 'inner')])
    assert sum(math.dist(s[:2], s[2:4]) for s in result) == 22
    assert (10, 0) in {p for s in result if s[5] == 'top' for p in (s[:2], s[2:4])}
    assert (10, 0) in {p for s in result if s[5] == 'inner' for p in (s[:2], s[2:4])}


def test_aliases_do_not_create_a_fake_transition_anchor():
    plan = [(0, 0, 10, 0, 2, 'top'), (2, 0, 0, 0, 2, 'alias'),
            (2, 0, 2, 4, 1, 'top')]
    result, report = cleaned(plan, {(10, 0, 'physical'), (2, 4, 'physical')},
                             layer_key=lambda _: 'physical')
    assert report['removed_virtual_length_mm'] == 2
    assert sum(math.dist(s[:2], s[2:4]) for s in result) == 12


def test_missing_contact_and_cycle_are_not_erased_to_hide_invalid_construction():
    result, report = cleaned([(0, 0, 10, 0, 2, 'x')], {(0, 0, 'x')})
    assert len(result) == 1 and report['trimmed_segments'] == 0
    cycle = [(0, 0, 5, 0, 2, 'x'), (5, 0, 5, 5, 2, 'x'),
             (5, 5, 0, 5, 2, 'x'), (0, 5, 0, 0, 2, 'x')]
    assert len(cleaned(cycle)[0]) == 4


def test_overlapping_declarations_keep_the_widest_existing_copper():
    result, _ = cleaned([(0, 0, 10, 0, 1, 'x'), (8, 0, 2, 0, 3, 'x')],
                         {(0, 0, 'x'), (10, 0, 'x')})
    assert {(s[0], s[2], s[4]) for s in result} == {(0, 2, 1), (2, 8, 3), (8, 10, 1)}


def test_invalid_and_oversized_proposals_fail_closed():
    with pytest.raises(ValueError):
        cleaned([(0, 0, 1, 1, float('nan'), 'x')])
    plan = [(0, 0, 1, 1, 1, 'x')] * 513
    result, report = cleaned(plan)
    assert result == plan and report['reason'] == 'normalization_size_bound'


def test_native_drc_confirms_virtual_tail_removal_without_losing_contacts(tmp_path):
    import json
    import shutil
    import subprocess
    pcbnew = pytest.importorskip('pcbnew')
    if not shutil.which('kicad-cli'):
        pytest.skip('native KiCad CLI required')
    plan = [(0, 0, 10, 0, 1.5, 'F.Cu'),
            (2, 6, 2, 0, 1., 'F.Cu'), (10, 0, 10, 8, 1.5, 'F.Cu')]
    contacts = {(2, 6, 'F.Cu'), (10, 8, 'F.Cu')}
    normalized, _ = cleaned(plan, contacts)
    counts = []
    for index, rows in enumerate((plan, normalized)):
        board = pcbnew.CreateEmptyBoard()
        outline = pcbnew.PCB_SHAPE(board)
        outline.SetShape(pcbnew.SHAPE_T_RECT)
        outline.SetStart(pcbnew.VECTOR2I(-5000000, -5000000))
        outline.SetEnd(pcbnew.VECTOR2I(15000000, 15000000))
        outline.SetLayer(pcbnew.Edge_Cuts)
        board.Add(outline)
        net = pcbnew.NETINFO_ITEM(board, 'arbitrary_supply')
        board.Add(net)
        for number, (x, y, _) in enumerate(sorted(contacts)):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference('TERMINAL_%d' % number)
            board.Add(fp)
            pad = pcbnew.PAD(fp)
            pad.SetNumber('1')
            pad.SetSize(pcbnew.VECTOR2I(2000000, 2000000))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I(x*1000000, y*1000000))
            pad.SetNet(net)
            fp.Add(pad)
        for x0, y0, x1, y1, width, _ in rows:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I(round(x0*1e6), round(y0*1e6)))
            track.SetEnd(pcbnew.VECTOR2I(round(x1*1e6), round(y1*1e6)))
            track.SetWidth(round(width*1e6))
            track.SetNet(net)
            track.SetLayer(pcbnew.F_Cu)
            board.Add(track)
        path = tmp_path / ('case%d.kicad_pcb' % index)
        report = path.with_suffix('.json')
        pcbnew.SaveBoard(str(path), board)
        subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json',
                        '--output', str(report), str(path)], check=True,
                       capture_output=True, timeout=30)
        data = json.loads(report.read_text())
        assert not data['unconnected_items']
        counts.append(sum(q['type'] == 'track_dangling' for q in data['violations']))
    assert counts[0] > 0 and counts[1] == 0
