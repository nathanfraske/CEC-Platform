"""Root metadata editing must not depend on a vendor's whitespace style."""
import uuid

import pytest

import cec_pcb


def fields(text):
    return [(key, text[begin:end])
            for key, begin, end in cec_pcb._gmp._footprint_fields(text)]


@pytest.mark.parametrize('separator', [' ', '\n  ', '\r\n\t'])
@pytest.mark.parametrize('layer_first', [True, False])
@pytest.mark.parametrize('flip', [True, False])
def test_metadata_on_same_line_preserves_geometry(tmp_path, monkeypatch, separator,
                                                layer_first, flip):
    pcbnew = pytest.importorskip('pcbnew')
    from test_place_flip import TestPlaceFlip
    metadata = ['(version 20260206)', '(generator "vendor (layout)")',
                '(generator_version "1.0")']
    layer = '(layer "F.Cu")'
    header = ([layer] + metadata) if layer_first else (metadata + [layer])
    nested = ('(property "Reference" "REF**" (at 0 -2) (layer "F.SilkS") '
              '(effects (font (size 1 1) (thickness 0.15))))')
    pad = ('(pad "1" smd rect (at 1 2 90) (size 1 2) '
           '(layers "F.Cu" "F.Paste" "F.Mask"))')
    description = r'(descr "quoted \" (layer) and ) (at 91 92) stay text")'
    old_uuid = str(uuid.uuid4())
    text = '(footprint "sample"' + separator + separator.join(
        header + ['(at 100 200 180)', f'(uuid "{old_uuid}")', description, nested, pad]) + ')'
    path = tmp_path / 'sample.kicad_mod'
    path.write_text(text)
    monkeypatch.setattr(cec_pcb._gmp, 'fp_path', lambda *_: str(path))
    result = cec_pcb.place('vendor:sample', 'X1', 19.25, 27.5, 90, {}, {}, flip=flip)
    root = fields(result)
    keys = [key for key, _ in root]
    assert keys.count('at') == keys.count('uuid') == keys.count('layer') == 1
    assert not set(keys).intersection({'version', 'generator', 'generator_version'})
    assert description in result
    assert old_uuid not in result
    board_path = tmp_path / 'placed.kicad_pcb'
    board_path.write_text(TestPlaceFlip()._board_doc(result))
    board = pcbnew.LoadBoard(str(board_path))
    fp = next(iter(board.GetFootprints()))
    assert (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6) == (19.25, 27.5)
    assert fp.GetLayerName() == ('B.Cu' if flip else 'F.Cu')
    assert len(list(fp.Pads())) == 1
    native_pad = next(iter(fp.Pads()))
    assert (native_pad.GetPosition().x / 1e6, native_pad.GetPosition().y / 1e6) == (
        17.25 if flip else 21.25, 26.5)
    if not flip:
        assert pad.replace('(at 1 2 90)', '(at 1 2 180)') in result
    assert path.read_bytes() == text.encode()  # The source library stays byte-for-byte intact.


@pytest.mark.parametrize('root', [
    '(footprint "sample" (property "Reference" "X" (layer "F.SilkS")))',
    '(footprint "sample" (layer "F.Cu") (layer "B.Cu"))',
    '(footprint "sample" (version 1) (layer "F.Cu")',
    '(footprint "sample" (layer "F.Cu")) (layer "B.Cu")',
])
def test_invalid_or_missing_root_layer_fails_closed(tmp_path, monkeypatch, root):
    path = tmp_path / 'sample.kicad_mod'
    path.write_text(root)
    monkeypatch.setattr(cec_pcb._gmp, 'fp_path', lambda *_: str(path))
    with pytest.raises(ValueError):
        cec_pcb.place('vendor:sample', 'X1', 10, 20, 0, {}, {})


def test_current_multifield_m2_mount_materializes_at_requested_position(tmp_path):
    pcbnew = pytest.importorskip('pcbnew')
    from test_place_flip import TestPlaceFlip
    result = cec_pcb.place(
        'cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware',
        'H99', 12.375, 48.625, 0, {}, {})
    path = tmp_path / 'mount.kicad_pcb'
    path.write_text(TestPlaceFlip()._board_doc(result))
    board = pcbnew.LoadBoard(str(path))
    fp = next(iter(board.GetFootprints()))
    assert (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6) == (12.375, 48.625)
    assert len(list(fp.Pads())) == 9
