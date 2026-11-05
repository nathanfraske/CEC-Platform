from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.mark.parametrize("dnp,in_bom,on_board", [
    (False, True, True), (True, True, True),
    (False, False, True), (False, True, False)])
def test_native_assembly_flags_are_independent_and_idempotent(dnp, in_bom, on_board):
    import pcbnew
    from cec_footprint_fields import apply_assembly_state
    board = pcbnew.CreateEmptyBoard()
    fp = pcbnew.FOOTPRINT(board)
    board.Add(fp)
    part = dict(dnp=dnp, in_bom=in_bom, on_board=on_board)
    apply_assembly_state(fp, part)
    assert fp.IsDNP() == dnp
    assert fp.IsExcludedFromBOM() == (not in_bom)
    assert fp.IsExcludedFromPosFiles() == (dnp or not on_board)
    assert apply_assembly_state(fp, part) == 0


@pytest.mark.parametrize("dnp", [True, False])
def test_materializer_uses_hierarchy_flags_not_empty_dnp_field(tmp_path, dnp):
    import pcbnew
    import cec_synth_pipeline as synth
    board = pcbnew.CreateEmptyBoard()
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("FILTER_X")
    fp.SetDNP(not dnp)
    fp.SetExcludedFromPosFiles(not dnp)
    board.Add(fp)
    sch = tmp_path / "root.kicad_sch"
    sch.write_text("fixture")
    cfg = SimpleNamespace(sch=str(sch))
    with mock.patch.object(synth, "View", return_value=SimpleNamespace(
            nl=SimpleNamespace(comps={"FILTER_X": SimpleNamespace(props={"dnp": ""})}))), \
         mock.patch("cec_sch_gates.inventory", return_value={
             "FILTER_X": {"dnp": dnp, "in_bom": True, "on_board": True, "props": {}}}):
        assert synth._apply_schematic_footprint_fields(board, cfg) == 2
    assert fp.IsDNP() == dnp and fp.IsExcludedFromPosFiles() == dnp
    assert not fp.IsExcludedFromBOM()
    assert len(list(board.GetFootprints())) == 1
