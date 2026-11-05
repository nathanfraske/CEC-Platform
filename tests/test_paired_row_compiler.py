"""Paired repair, not repeated acceptance of a body-only pitch."""
import copy
import math
from unittest.mock import patch

import pytest
from cec_mating_rows import compile_paired_row, MatingRowConflict


def domain(name, intervals, gap=.2):
    return dict(domain=name, intervals=intervals, gap_mm=gap)


def test_repairs_both_sides_using_shared_datums_and_existing_slack():
    # The original first gap is short, but a larger later gap can donate room.
    rows = [domain('plug-body', [(-2, 2)]*3),
            domain('plug-copper', [(-3.5, 3.5)]*3),
            domain('socket-copper', [(-3, 3)]*3)]
    before = copy.deepcopy(rows)
    result = compile_paired_row([1, 7, 17], rows, maximum_last_mm=17)
    assert result['ok'] and result['changed']
    assert result['proposed_datums_mm'] == pytest.approx([1, 8.2, 17])
    assert rows == before and not result['dimensions_changed']
    assert not result['admission_ok']  # still needs native/assembly checks
    assert not compile_paired_row(result['proposed_datums_mm'], rows, maximum_last_mm=17)['changed']


def test_daughter_copper_can_be_the_limiting_geometry():
    result = compile_paired_row([0, 5], [domain('plug', [(-1, 1)]*2),
                                domain('socket', [(-3, 3)]*2)], maximum_last_mm=7)
    assert result['proposed_datums_mm'] == pytest.approx([0, 6.2])
    assert {v['domain'] for v in result['conflicts']} == {'socket'}


def test_cannot_emit_either_half_when_fixed_span_is_too_small():
    result = compile_paired_row([3.5, 10.5, 17.5, 24.5],
                               [domain('installed', [(-3.75, 3.75)]*4)], maximum_last_mm=24.5)
    assert not result['ok'] and result['proposed_datums_mm'] is None
    assert result['excess_mm'] == pytest.approx(2.1)
    assert not result['changed']


def test_nonadjacent_asymmetric_envelopes_are_checked():
    rows = [domain('offset-contacts', [(-1, 8), (-4, -3), (-1, 1)])]
    result = compile_paired_row([0, 12.2, 13], rows, maximum_last_mm=14)
    assert result['ok']
    for row in result['constraints']:
        a, b = row['indices']
        assert result['proposed_datums_mm'][b]-result['proposed_datums_mm'][a] >= row['minimum_pitch_mm']-1e-9


@pytest.mark.parametrize('shift', [-311, 0, 17.12345])
def test_translation_does_not_change_repair(shift):
    result = compile_paired_row([shift, shift+5], [domain('any', [(-3, 3)]*2)],
                               maximum_last_mm=shift+7)
    assert result['proposed_datums_mm'] == pytest.approx([shift, shift+6.2])


@pytest.mark.parametrize('rows', [[], [domain('bad', [(-1, 1)])],
    [domain('bad', [(1, -1)]*2)], [domain('bad', [(-1, math.nan)]*2)],
    [domain('bad', [(-1, 1)]*2, gap=-.1)]])
def test_missing_or_invalid_evidence_refuses(rows):
    with pytest.raises(ValueError):
        compile_paired_row([0, 5], rows, maximum_last_mm=10)


def test_all_real_producers_refuse_unfit_row_before_publishing(tmp_path):
    import cec_xfcn_contract as contract
    import cec_output_mount_repair as repair
    import cec_xfcn_place as place
    for name, plan in contract.PROJECTS.items():
        receipt = plan['mating_row_compilation']
        if receipt['ok']:
            continue
        poses = copy.deepcopy(plan['placements_mm'])
        with pytest.raises(MatingRowConflict) as failure:
            (contract.mating_row_targets if name in contract.OUTPUT_MOUNT_PORTS
             else contract.daughter_mating_targets)(name, poses)
        assert failure.value.evidence == receipt
        assert poses == plan['placements_mm']
        with pytest.raises(MatingRowConflict):
            contract.power_path_anchor_placements(plan)
        output = tmp_path / name / 'absent.kicad_pcb'
        with patch.object(place.pcbnew, 'LoadBoard') as load:
            with pytest.raises(MatingRowConflict):
                place.apply_project(name, write=True, output_pcb=output)
            load.assert_not_called()
        assert not output.parent.exists()


def test_copper_projection_matches_native_installed_footprint():
    import pcbnew
    import cec_pcb
    import cec_xfcn_contract as contract
    import cec_placement_geometry as geometry
    for key in (contract.T340, contract.T340_DB, contract.TTR, contract.TTR_DB):
        nick, name = contract.PARTS[key]['footprint'].split(':')
        path = cec_pcb.fp_path(nick, name)
        from pathlib import Path
        for angle in (0, 90, 180, 270):
            fp = pcbnew.FootprintLoad(str(Path(path).parent), name)
            fp.SetOrientationDegrees(angle)
            native = geometry.footprint_copper_interval(fp)
            projected = contract._installed_copper_interval(key, angle)
            assert projected == pytest.approx(native, abs=2e-6)


def test_copper_parser_preserves_repeated_pins_and_pad_rotation(tmp_path):
    import cec_pcb
    import cec_xfcn_contract as contract
    path = tmp_path / 'repeated.kicad_mod'
    path.write_text('(footprint "example" (pad "1" smd rect (at -4 0 45) (size 2 4)) '
                    '(pad "1" smd rect (at 6 0) (size 2 2)))')
    with patch.object(cec_pcb, 'fp_path', return_value=str(path)):
        result = contract._installed_copper_interval(contract.T340, 0)
    assert result == pytest.approx((-4-3/math.sqrt(2), 7))


@pytest.mark.parametrize('angle', [0, 90])
def test_repaired_shared_row_passes_saved_native_pad_drc_on_both_halves(tmp_path, angle):
    import pcbnew
    import cec_placement_geometry as geometry
    boards, envelopes, originals = [], [], []
    refs = ['contact-red', 'contact-green', 'contact-blue']
    for side, width in enumerate((4.8, 3.2)):
        board = pcbnew.BOARD()
        for i, (ref, x) in enumerate(zip(refs, (4., 8., 16.))):
            net = pcbnew.NETINFO_ITEM(board, 'rail-%d'%i)
            board.Add(net)
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            pad = pcbnew.PAD(fp)
            pad.SetNumber('1')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetSize(pcbnew.VECTOR2I_MM(width, 1) if angle == 0 else pcbnew.VECTOR2I_MM(1, width))
            pad.SetNet(net)
            fp.Add(pad)
            board.Add(fp)
            fp.SetPosition(pcbnew.VECTOR2I_MM(x, 5))
            fp.SetOrientationDegrees(angle)
        for start, end in (((0,0),(22,0)), ((22,0),(22,10)), ((22,10),(0,10)), ((0,10),(0,0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            board.Add(edge)
        footprints = {fp.GetReference():fp for fp in board.GetFootprints()}
        envelopes.append(domain(str(side), [geometry.footprint_copper_interval(footprints[r]) for r in refs], .5))
        path = tmp_path / ('side-%d.kicad_pcb'%side)
        pcbnew.SaveBoard(str(path), board)
        path.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "test-clearance" (constraint clearance (min 0.5mm)))\n')
        original = geometry.evaluate(path)
        originals.append(original)
        boards.append((board, path))
    assert not originals[0]['ok']
    proposal = compile_paired_row([4, 8, 16], envelopes, maximum_last_mm=16)
    assert proposal['ok'] and proposal['changed']
    for board, path in boards:
        for ref, x in zip(refs, proposal['proposed_datums_mm']):
            board.FindFootprintByReference(ref).SetPosition(pcbnew.VECTOR2I_MM(x, 5))
        pcbnew.SaveBoard(str(path), board)
        result = geometry.evaluate(path)
        assert result['ok'], result
        assert result['source_unchanged']
