"""Footprint-origin bounds must never substitute for actual rotated land bounds."""
import pcbnew
import pytest
import cec_force_current as force
import cec_pad_bound_ground_cell_poses as bounded
from test_annular_ground_cell_pose_frontier import seed

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_rotating_about_an_unmoved_origin_can_exceed_the_native_pad_limit(tmp_path,monkeypatch,quarter,back):
    from test_complete_macro_cell import fixture
    source,parent,posed,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    ref=next(iter(packet['source_plan']['selected_bypasses']))
    posed=pcbnew.LoadBoard(str(source));fp=posed.FindFootprintByReference(ref)
    before=tuple(fp.GetPosition());fp.SetOrientationDegrees(fp.GetOrientationDegrees()+180.)
    assert tuple(fp.GetPosition())==before
    r=bounded.pad_motion(parent,posed,{ref},500000)
    assert not r['ok'] and r['refused_pad_uuids'] and r['exact_integer_native_pad_motion']
    assert not r['placement_or_routing_authority']

@pytest.mark.parametrize('delta',[499999,500000,500001])
@pytest.mark.parametrize('axis',[0,1])
def test_native_integer_pad_motion_floor_has_no_epsilon_waiver(tmp_path,monkeypatch,delta,axis):
    s=seed(tmp_path,monkeypatch);parent=pcbnew.LoadBoard(s['source']);posed=pcbnew.LoadBoard(s['source'])
    ref=next(iter(s['poses']));move=[0,0];move[axis]=delta
    posed.FindFootprintByReference(ref).Move(pcbnew.VECTOR2I(*move))
    r=bounded.pad_motion(parent,posed,{ref},500000)
    assert r['ok']==(delta<=500000)

def test_source_measurement_pickups_rank_a_disclosed_finite_region(tmp_path,monkeypatch):
    s=seed(tmp_path,monkeypatch)
    # This fixture has generic INPUT nets, not ratified board Kelvin lineage.
    # Inject only a producer-shaped ranking event: no copper/current authority.
    original=bounded.private.compiler.compile
    def compile(*args,**kwargs):
        board,packet=original(*args,**kwargs)
        owner=s['source_selected_bypass']['ref'];pad=next(iter(board.FindFootprintByReference(owner).Pads()))
        packet['requests']['synthetic_rank_only']=dict(kind='measurement',
            a=dict(pad_uuid=force._uid(pad)),b=dict(at_nm=[5000000,6000000]))
        return board,packet
    monkeypatch.setattr(bounded.private.compiler,'compile',compile)
    c=bounded.prepare(s,radius_mm=2.,minimum_ground_shift_mm=.5)
    ports=c['settings']['source_measurement_pickup_points_nm'];assert ports
    scores=[sum((p[0]-q[0])**2+(p[1]-q[1])**2 for q in ports) for p in c['lattice']]
    assert scores==sorted(scores) and c['settings']['all_native_smd_pad_motion_bounded']

def test_missing_typed_pickup_keeps_the_original_annular_order_instead_of_guessing(tmp_path,monkeypatch):
    import cec_annular_ground_cell_pose_frontier as annular
    s=seed(tmp_path,monkeypatch);a=annular.prepare(s,radius_mm=2.,minimum_ground_shift_mm=.5)
    b=bounded.prepare(s,radius_mm=2.,minimum_ground_shift_mm=.5)
    assert b['settings']['source_measurement_pickup_points_nm']==[] and a['lattice']==b['lattice']

@pytest.mark.parametrize('limit',[True,0,-1,32000001])
def test_native_motion_bound_cannot_be_expanded_by_truthy_or_unbounded_values(limit):
    with pytest.raises(ValueError):bounded.pad_motion(None,None,{'arbitrary'},limit)
