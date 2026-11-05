"""Plan-local aperture reuse changes work only, never exact native geometry."""
import pcbnew
import pytest
from shapely.geometry import box
import cec_dense_reference_mapping as dense
import cec_rectangular_field_silk_clearance as native_mask
import cec_force_current as force
from test_dense_reference_mapping import fixture
from test_interrupted_reference_guides import opening


def source_board(tmp_path,*,back=False,quarter=0):
    source,_,uid=fixture(tmp_path,back=back,quarter=quarter)
    b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(10,10));v.SetWidth(600000);v.SetDrill(300000)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    return b,fp,v


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('policy',['reserve_native_lands','native_mask_and_bore'])
def test_native_rows_and_guide_intersections_equal_independent_conversion(tmp_path,back,quarter,policy):
    board,fp,_=source_board(tmp_path,back=back,quarter=quarter)
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    shape=dense.court(fp);x0,y0,x1,y1=shape.bounds
    opening(board,box(x1-.4,y0-.4,x1+.4,y0+.4),face)
    prep=dense._ObstaclePreparation(board)
    independent=tuple((uid,dense.assembly.polygon_from_native(poly).wkb)
        for uid,poly in native_mask._mask_openings(board,face,policy))
    for _ in range(2):
        assert tuple((uid,p.wkb)for uid,p in prep.apertures(board,face,policy))==independent
    options=dict(height=1.,stroke=.15,clearance=.15,edge=.2)
    raw=dense._interrupted_body_guides(board,shape,face,options)
    cached=dense._interrupted_body_guides(board,shape,face,options,_prepared=prep)
    assert raw==cached


def test_obstacle_and_multiple_guides_convert_same_face_once_per_plan(tmp_path,monkeypatch):
    board,fp,_=source_board(tmp_path);face=pcbnew.B_SilkS;shape=dense.court(fp)
    prep=dense._ObstaclePreparation(board);calls=[];real=native_mask._mask_openings
    def observe(*args):calls.append((args[1],args[2]));return real(*args)
    monkeypatch.setattr(native_mask,'_mask_openings',observe)
    dense.obstacles(board,face,set(),.15,assembled_bodies=False,via_ink_policy='native_mask_and_bore',_prepared=prep)
    for _ in range(2):dense._interrupted_body_guides(board,shape,face,dict(stroke=.15,clearance=.15),_prepared=prep)
    assert calls==[(face,'native_mask_and_bore')]
    prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore')
    prep.apertures(board,face,'reserve_native_lands')
    assert len(calls)==3  # Face and physical via policy never alias.
    other=dense._ObstaclePreparation(board);other.apertures(board,face,'native_mask_and_bore')
    assert len(calls)==4  # Independent construction/replay cannot share caches.


def test_returned_rows_and_geometry_objects_cannot_poison_reuse(tmp_path):
    board,_,_=source_board(tmp_path);prep=dense._ObstaclePreparation(board)
    a=prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore')
    b=prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore')
    assert isinstance(a,tuple)and a and a[0][1] is not b[0][1]
    expected=tuple((uid,p.wkb)for uid,p in b)
    # Caller transformations create unrelated values; the private bytes stay literal.
    altered=a[0][1].buffer(10)
    assert altered.wkb!=a[0][1].wkb
    assert tuple((uid,p.wkb)for uid,p in prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore'))==expected


@pytest.mark.parametrize('fault',['pad_position','pad_size','pad_mask','pad_drill','via_position','via_diameter',
    'via_drill','via_mask','via_tenting','board_expansion','board_min_width','board_tenting','other_board'])
def test_every_live_native_aperture_input_is_rechecked_before_reuse(tmp_path,fault):
    board,fp,via=source_board(tmp_path);pad=next(iter(fp.Pads()));prep=dense._ObstaclePreparation(board)
    prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore')
    if fault=='pad_position':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad_size':pad.SetSize(pcbnew.VECTOR2I(123000,456000))
    elif fault=='pad_mask':pad.SetLocalSolderMaskMargin(10000)
    elif fault=='pad_drill':pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif fault=='via_position':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='via_diameter':via.SetWidth(700000)
    elif fault=='via_drill':via.SetDrill(350000)
    elif fault=='via_mask':via.SetLocalSolderMaskMargin(10000)
    elif fault=='via_tenting':via.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    elif fault=='board_expansion':board.GetDesignSettings().m_SolderMaskExpansion+=1000
    elif fault=='board_min_width':board.GetDesignSettings().m_SolderMaskMinWidth+=1000
    elif fault=='board_tenting':board.GetDesignSettings().m_TentViasBack=not board.GetDesignSettings().m_TentViasBack
    else:board=pcbnew.BOARD()
    with pytest.raises(ValueError,match='reference_obstacle_native_inputs_changed'):
        prep.apertures(board,pcbnew.F_SilkS,'native_mask_and_bore')


def test_invalid_face_policy_and_external_preparation_are_not_authority(tmp_path):
    board,_,_=source_board(tmp_path);prep=dense._ObstaclePreparation(board)
    with pytest.raises(ValueError,match='exact_reference_aperture_face_policy_required'):
        prep.apertures(board,pcbnew.In1_Cu,'native_mask_and_bore')
    with pytest.raises(ValueError,match='exact_reference_aperture_face_policy_required'):
        prep.apertures(board,pcbnew.F_SilkS,'worker_override')
    with pytest.raises(ValueError,match='planner_owned_reference_aperture_preparation_required'):
        dense._interrupted_body_guides(board,box(1,1,2,2),pcbnew.F_SilkS,dict(stroke=.15,clearance=.15),_prepared={})
