"""Diagonal package poses retain only the exact existing saved local rule."""
import pcbnew
import pytest
import cec_existing_local_pofv_pad_rule as rule
import cec_field_coupling as field
import cec_smd_macro_transport as transport
from test_existing_local_pofv_pad_rule import case,seat


@pytest.mark.parametrize('turn',[45,135,225,315])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_diagonal_package_is_rederived_without_changing_existing_process_floors(tmp_path,turn,face):
    board,source,pad=case(tmp_path,face=face);fp=pad.GetParentFootprint()
    old={p.m_Uuid.AsString():tuple(p.GetPosition()) for p in fp.Pads()}
    fp.SetPosition(pad.GetPosition())
    for p in fp.Pads():p.SetPosition(pcbnew.VECTOR2I(*old[p.m_Uuid.AsString()]))
    field._save_field_snapshot(board,source);parent=pcbnew.LoadBoard(str(source))
    raw=source.read_bytes();floors=rule._floors(board)
    fp.Move(pcbnew.VECTOR2I_MM(2,1));fp.SetOrientationDegrees(fp.GetOrientationDegrees()+turn)
    pose=[*(v/1e6 for v in fp.GetPosition()),fp.GetOrientationDegrees()]
    transport.apply(parent,board,allow_octilinear_rotations=True,maximum_shift_mm=8.)
    rule.bind_projected_source_poses(board,{fp.GetReference():pose})
    assert rule.resolve(board,pad) is None
    rule.bind_projected_source_poses(board,{fp.GetReference():pose},allow_octilinear_rotations=True)
    context=rule.resolve(board,pad)
    assert context and context['projected_native_source_package']['entire_source_native_package_rederived']
    assert seat(board,pad,local_pofv_pad=pad)
    assert rule._floors(board)==floors and source.read_bytes()==raw
    pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    assert rule.resolve(board,pad) is None


@pytest.mark.parametrize('value',[None,1,0,'yes',{}])
def test_existing_rule_diagonal_permission_is_never_inferred_from_truthiness(tmp_path,value):
    board,source,pad=case(tmp_path)
    with pytest.raises(ValueError):
        rule.bind_projected_source_poses(board,{pad.GetParentFootprint().GetReference():[0.,0.,45.]},
            allow_octilinear_rotations=value)
