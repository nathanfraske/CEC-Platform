"""An unchanged native placement must survive repeated mm serialization."""
from types import SimpleNamespace
import pcbnew
import pytest
import cec_synth_pipeline as synth
from cec_power_local_replay import _terminals
from test_lastmile import _board


@pytest.mark.parametrize('x,y,angle', [
    (16338589, 65194999, 0), (300019, 15338859, 90),
    (-16338589, -65194999, 270)])
def test_exact_native_terminal_geometry_survives_rehydration(tmp_path, monkeypatch, x, y, angle):
    board=_board([(5, 5, 'RENAMED_SUPPLY')], edge=(-80,-80,80,80))
    fp=next(iter(board.GetFootprints()))
    fp.SetReference('ANONYMOUS_OWNER')
    fp.SetPosition(pcbnew.VECTOR2I(x,y)); fp.SetOrientationDegrees(angle)
    path=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(path),board)
    pristine=path.read_bytes()
    # This fixture has no schematic/device policy. Exercise the real native
    # clone/apply/save path while removing only unrelated metadata/rail work.
    monkeypatch.setattr(synth,'_apply_schematic_footprint_fields',lambda *a: None)
    monkeypatch.setattr(synth,'_apply_declared_board_pad_nets',lambda *a: None)
    monkeypatch.setattr(synth,'_carry_project_rule_authority',lambda *a,**kw: {'carried':True})
    monkeypatch.setattr(synth,'_lay_declared_blueprint_cells',lambda *a,**kw: None)
    monkeypatch.setattr(synth,'_lay_declared_force_rails',lambda *a,**kw: [])
    import cec_outline_geometry
    monkeypatch.setattr(cec_outline_geometry,'reconcile_candidate',lambda *a: None)
    expected=_terminals(board,{'RENAMED_SUPPLY'})
    current=path
    for index in range(3):
        loaded=pcbnew.LoadBoard(str(current))
        poses={f.GetReference():(f.GetPosition().x/1e6,f.GetPosition().y/1e6,
                                f.GetOrientationDegrees()) for f in loaded.GetFootprints()}
        candidate=SimpleNamespace(source_board=str(current),P=poses,back_refs=())
        target=tmp_path/('round-%d.kicad_pcb'%index)
        synth._materialize_rehydrated_board(candidate,SimpleNamespace(params={}),str(target))
        result=pcbnew.LoadBoard(str(target))
        assert _terminals(result,{'RENAMED_SUPPLY'}) == expected
        current=target
    assert path.read_bytes() == pristine


def test_real_one_native_unit_edit_is_not_swallowed(tmp_path, monkeypatch):
    # The conversion fixes representation, not equality tolerance. A requested
    # one-unit movement must still produce a different integer coordinate.
    for value in (16338589, 65194999, -16338589):
        assert int(round((value/1e6)*pcbnew.pcbIUScale.IU_PER_MM)) == value
        assert int(round(((value+1)/1e6)*pcbnew.pcbIUScale.IU_PER_MM)) == value+1
