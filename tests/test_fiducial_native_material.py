"""Optical windows must lie on native substrate, not merely inside its AABB."""
import pcbnew
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import cec_board_geometry as geometry
import cec_edge_recess as recess
import cec_synth_pipeline as synth
import test_fiducial_edge_policy as fid_fixture


def fixture(kind,rotation):
    b=fid_fixture.TestFiducialEdgePolicy._board()
    b.FindFootprintByReference('FID3').SetPosition(pcbnew.VECTOR2I_MM(45,5))
    if kind=='notch':
        edge=next(e for e in b.GetDrawings() if e.GetLayer()==pcbnew.Edge_Cuts
            and e.GetStart().y==0 and e.GetEnd().y==0)
        keeper=recess.replace_edge(b,edge,(0,1),opening=(2,14),depth=12,radius=.5)
    else:
        edge=pcbnew.PCB_SHAPE(b);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_CIRCLE)
        edge.SetStart(pcbnew.VECTOR2I_MM(5,5));edge.SetEnd(pcbnew.VECTOR2I_MM(8,5));b.Add(edge)
    if rotation:
        angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T);at=pcbnew.VECTOR2I_MM(25,25)
        for item in [*b.GetFootprints(),*b.GetDrawings()]:item.Rotate(at,angle)
    return b


@pytest.mark.parametrize('kind',['notch','cutout'])
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_missing_material_is_rejected_and_repaired_without_changing_outline(tmp_path,kind,rotation):
    b=fixture(kind,rotation);p=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(p),b)
    before=sorted((e.m_Uuid.AsString(),e.GetShape(),tuple(e.GetStart()),tuple(e.GetEnd())) for e in b.GetDrawings())
    checked=synth._oracle_fiducials(str(p),expect=True)
    assert not checked['ok'] and any(r[:2]==('outside_board_material','FID1') for r in checked['violations'])
    result=synth.repair_fiducials_to_edge_band(str(p))
    assert result['ok'] and any(r['ref']=='FID1' for r in result['moved']),result
    actual=pcbnew.LoadBoard(str(p));outline=geometry.outline_material(actual)
    boundaries=geometry.material_boundaries(outline)
    assert synth._oracle_fiducials(str(p),expect=True)['ok']
    assert before==sorted((e.m_Uuid.AsString(),e.GetShape(),tuple(e.GetStart()),tuple(e.GetEnd())) for e in actual.GetDrawings())
    for f in actual.GetFootprints():
        assert outline.Contains(f.GetPosition())
        assert not any(boundary.Collide(f.GetPosition(),1500000) for boundary in boundaries)


@pytest.mark.parametrize('kind',['notch','cutout'])
def test_center_inside_does_not_waive_optical_window_overhang(tmp_path,kind):
    b=fixture(kind,0);f=b.FindFootprintByReference('FID1')
    f.SetPosition(pcbnew.VECTOR2I_MM(15,5) if kind=='notch' else pcbnew.VECTOR2I_MM(9,5))
    assert geometry.outline_material(b).Contains(f.GetPosition())
    p=tmp_path/'overhang.kicad_pcb';pcbnew.SaveBoard(str(p),b)
    result=synth._oracle_fiducials(str(p),expect=True)
    assert not result['ok'] and any(r[:2]==('outside_board_material','FID1') for r in result['violations'])


def test_broken_outline_cannot_fall_back_to_bounding_box_success(tmp_path):
    b=fixture('notch',0);b.Remove(next(iter(b.GetDrawings())))
    p=tmp_path/'broken.kicad_pcb';pcbnew.SaveBoard(str(p),b)
    result=synth._oracle_fiducials(str(p),expect=True)
    assert not result['ok'] and result['violations'][0][0]=='native_board_material_unknown'
    with pytest.raises(ValueError):synth.repair_fiducials_to_edge_band(str(p))
