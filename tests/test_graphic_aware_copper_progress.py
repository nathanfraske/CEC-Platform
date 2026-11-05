"""Actual copper artwork is included, never bbox-only or silently removed."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_graphic_aware_copper_progress as progress
import cec_native_copper_delta as original
import cec_source_retaining_boundary_batch as batch
from test_source_retaining_boundary_pocket import fixture

@pytest.mark.parametrize('on_back',[False,True])
def test_real_filled_copper_art_hides_only_real_same_face_added_material(tmp_path,on_back):
    source,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    shape=pcbnew.PCB_SHAPE(fp);shape.SetLayer(pcbnew.B_Cu if on_back else pcbnew.F_Cu)
    shape.SetShape(pcbnew.SHAPE_T_RECT);shape.SetStart(pcbnew.VECTOR2I(2000000,2000000))
    shape.SetEnd(pcbnew.VECTOR2I(8000000,6000000));shape.SetWidth(0);shape.SetFillMode(pcbnew.FILL_T_FILLED_SHAPE);fp.Add(shape)
    field._save_field_snapshot(b,source)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware');before=pcbnew.LoadBoard(str(source));after=batch.construct(source,proposal)
    old=original.compare(before,after,net='SYNTH_POCKET',layer_ids=[pcbnew.F_Cu])
    assert not old['ok'] and 'unsupported_footprint_copper_graphic' in str(old['errors'])
    result=progress.compare(before,after,net='SYNTH_POCKET',layer_ids=[pcbnew.F_Cu])
    assert result['ok'] and result['complete'],result['errors']
    assert result['faces'][0]['actual_source_copper_graphics_included']==(0 if on_back else 1)
    if on_back:assert result['faces'][0]['definitely_added_area_mm2']>.0025
    else:assert result['faces'][0]['definitely_added_area_mm2']==0
    assert not result['electrical_current_reference_or_release_qualified'] and not result['original_clipped_cut_gate_changed']

def test_native_artwork_hollow_rectangle_is_not_replaced_with_its_filled_bbox(tmp_path):
    source,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    shape=pcbnew.PCB_SHAPE(fp);shape.SetLayer(pcbnew.F_Cu);shape.SetShape(pcbnew.SHAPE_T_RECT)
    shape.SetStart(pcbnew.VECTOR2I(1000000,1000000));shape.SetEnd(pcbnew.VECTOR2I(9000000,7000000))
    shape.SetWidth(100000);shape.SetFillMode(pcbnew.FILL_T_NO_FILL);fp.Add(shape);field._save_field_snapshot(b,source)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware');before=pcbnew.LoadBoard(str(source));after=batch.construct(source,proposal)
    result=progress.compare(before,after,net='SYNTH_POCKET',layer_ids=[pcbnew.F_Cu])
    assert result['ok'] and result['faces'][0]['definitely_added_area_mm2']>.0025
