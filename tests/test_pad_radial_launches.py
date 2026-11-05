"""Pure radial proposals carry no process or clearance authority."""
import math
import pcbnew
import pytest
import cec_pad_face_launch as launch
from test_pair_package_via_floor import package_board

@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_finite_centre_owned_exact_octilinear_radial_domain(angle,back):
    board,_=package_board(angle,pad_size=.4)
    fp=next(iter(board.GetFootprints()));fp.SetReference('RENAMED_RADIAL')
    if back:fp.Flip(fp.GetPosition(),False)
    pad=next(iter(fp.Pads()));origin=tuple(pad.GetPosition())
    rows=launch.radial_candidates(pad,[(.3,.2)],distances_mm=[.75,1.,1.25,1.5])
    assert len(rows)==32 and len({tuple(r['end'])for r in rows})==32
    for row in rows:
        assert tuple(row['start'])==origin
        dx,dy=(v-u for u,v in zip(origin,tuple(row['end'])))
        assert dx==0 or dy==0 or abs(dx)==abs(dy)
        assert 0<math.hypot(dx,dy)<=1500000
        assert row['diameter']==.3 and row['drill']==.2
        assert math.hypot(dx,dy)<=row['radial_distance_mm']*1e6

@pytest.mark.parametrize('args',[
    {'distances_mm':[1.500001]}, {'distances_mm':[0]}, {'distances_mm':[True]},
    {'distances_mm':[float('nan')]}, {'distances_mm':[float('inf')]},
    {'distances_mm':[.5,.5]}, {'distances_mm':[]},
    {'distances_mm':[.1,.2,.3,.4,.5]}, {'reach_mm':0}, {'reach_mm':True},
    {'reach_mm':float('nan')}, {'geometries':[(0,.2)]},
    {'geometries':[(.3,-1)]}, {'geometries':[(.3,float('nan'))]},
    {'geometries':[(True,.2)]}, {'geometries':[]}])
def test_bad_or_outside_reach_inputs_refuse(args):
    board,_=package_board();pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    kwargs=dict(geometries=[(.3,.2)],distances_mm=[.75,1.,1.25,1.5]);kwargs.update(args)
    with pytest.raises(ValueError):launch.radial_candidates(pad,**kwargs)

@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_CUSTOM,pcbnew.PAD_SHAPE_TRAPEZOID])
def test_unsupported_native_land_shape_gets_no_radial_permission(shape):
    board,_=package_board();pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetShape(shape)
    assert launch.radial_candidates(pad,[(.3,.2)],distances_mm=[1.5])==[]
