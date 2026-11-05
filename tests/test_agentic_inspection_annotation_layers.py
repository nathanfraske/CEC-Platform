"""Printed Silk and nonprinted Fab values are not conflated by inspection."""
import json
from pathlib import Path
import subprocess

import pcbnew
import pytest

import cec_suite_inspection as inspection


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('hidden', [False, True])
def test_native_visible_value_mpn_layers_are_counted_without_reference_or_functional_labels(back, hidden):
    board = pcbnew.BOARD()
    fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    fp.SetReference('U_opaque'); fp.SetValue('full component name')
    fp.SetField('MPN', 'manufacturer number')
    fp.SetField('Functional', 'PIN 1 / +12V / KEY')
    silk = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    fab = pcbnew.B_Fab if back else pcbnew.F_Fab
    fp.Reference().SetVisible(True); fp.Reference().SetLayer(silk)
    fp.Value().SetVisible(not hidden); fp.Value().SetLayer(fab)
    fp.GetField('MPN').SetVisible(not hidden); fp.GetField('MPN').SetLayer(silk)
    fp.GetField('Functional').SetVisible(True); fp.GetField('Functional').SetLayer(silk)
    before = [(str(f.m_Uuid.AsString()), str(f.GetText()), f.GetLayer(), f.IsVisible()) for f in fp.GetFields()]
    result = inspection._visible_component_field_layers(board)
    assert result['silk_visible_total'] == result['fab_visible_total'] == int(not hidden)
    assert result['by_layer']['B.Fab' if back else 'F.Fab']['Value'] == int(not hidden)
    assert result['by_layer']['B.Silkscreen' if back else 'F.Silkscreen']['MPN'] == int(not hidden)
    assert result['reference_and_functional_labels_excluded']
    assert before == [(str(f.m_Uuid.AsString()), str(f.GetText()), f.GetLayer(), f.IsVisible()) for f in fp.GetFields()]


def test_empty_visible_fields_and_other_layers_are_not_printed_value_counts():
    board = pcbnew.BOARD(); fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    fp.SetValue(' '); fp.Value().SetVisible(True); fp.Value().SetLayer(pcbnew.F_SilkS)
    fp.SetField('MPN', 'retained sourcing data'); fp.GetField('MPN').SetVisible(True)
    fp.GetField('MPN').SetLayer(pcbnew.Dwgs_User)
    result = inspection._visible_component_field_layers(board)
    assert result['silk_visible_total'] == result['fab_visible_total'] == 0


def test_ui_explains_actual_counts_without_changing_native_plots_or_default_guide():
    root = Path(__file__).resolve().parents[1]
    html = (root/'scripts/static/cec_suite_inspection.html').read_text()
    js = (root/'scripts/static/cec_suite_inspection.js').read_text()
    py = (root/'scripts/cec_suite_inspection.py').read_text()
    assert '<option value="">None</option>' in html
    assert "$('guide').value=''" in js
    assert 'guide-field-note' in html and "$('guide-field-note').textContent=guideFieldNote(board)" in js
    assert 'annotation_fields=_visible_component_field_layers(board)' in py
    assert "['F.Silkscreen','B.Silkscreen','F.Fab','B.Fab']" in py
    start = js.index('function guideFieldNote(value){')
    end = js.index('\nfunction loadLayers', start)
    program = js[start:end]+"\nconsole.log(JSON.stringify([guideFieldNote({annotation_fields:{silk_visible_total:0,fab_visible_total:573}}),guideFieldNote({})]));"
    output = subprocess.run(['node','-e',program], check=True, capture_output=True, text=True)
    known, unknown = json.loads(output.stdout)
    assert 'actual silkscreen: 0 visible' in known and 'Fab guides: 573 visible' in known
    assert 'nonprinted component values/part names, not silkscreen' in known
    assert 'functional labels are unchanged' in known
    assert 'not available' in unknown
