"""The shared emitter must not reintroduce full part names onto silk."""

import pcbnew
import pytest

import cec_pcb
import test_place_flip as _flip_fixture


@pytest.mark.parametrize('libid', [
    'cec-Package_SO:VSSOP-10_3x3mm_P0.5mm',
    'cec-Package_TO_SOT_SMD:SOT-23-6',
    'cec-Resistor_SMD:R_2512_6332Metric',
])
@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_generated_values_stay_on_fab_without_changing_native_lands(tmp_path, libid, rotation, back):
    boards = []
    value = 'FULL-MANUFACTURER-PART-NAME'
    for supplied in (None, value):
        emitted = cec_pcb.place(libid, 'OPAQUE_REF', 50, 50, rotation,
                               {}, {}, flip=back, val=supplied)
        path = tmp_path / ('library.kicad_pcb' if supplied is None else 'named.kicad_pcb')
        path.write_text(_flip_fixture.TestPlaceFlip()._board_doc(emitted))
        boards.append(pcbnew.LoadBoard(str(path)))
    original, actual = [next(iter(board.GetFootprints())) for board in boards]
    assert actual.Value().GetText() == value
    assert actual.Value().GetLayer() == original.Value().GetLayer() == (
        pcbnew.B_Fab if back else pcbnew.F_Fab)
    assert actual.Reference().GetLayer() == (pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    assert actual.Reference().GetText() == 'OPAQUE_REF'
    assert actual.Value().IsVisible() == original.Value().IsVisible()
    assert actual.Value().GetPosition() == original.Value().GetPosition()
    assert actual.Value().IsMirrored() == original.Value().IsMirrored()
    assert actual.Value().GetTextSize() == original.Value().GetTextSize()
    def lands(fp):
        return sorted((p.GetNumber(), tuple(p.GetPosition()), tuple(p.GetSize()),
                       p.GetOrientationDegrees(), p.GetAttribute(),
                       tuple(p.GetLayerSet().CuStack())) for p in fp.Pads())
    assert lands(actual) == lands(original)
