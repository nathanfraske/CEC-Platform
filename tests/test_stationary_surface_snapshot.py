"""Warm surface results equal cold native checks; stale geometry must refuse."""
import pcbnew
import pytest
import cec_force_current as force
import cec_escape_pose_frontier as cold
import cec_stationary_surface_snapshot as warm
from test_static_foreign_column_filter import board_case

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_rotated_reflected_native_surface_conflicts_match_cold(quarter,mirror,layer):
    b,moving,pad,edge,point=board_case(quarter,mirror,layer)
    refs={moving.GetReference()};snapshot=warm.Snapshot(b,refs)
    for target in (point(8,8),point(13,10),point(17,17)):
        moving.Move(target-pad.GetPosition())
        a=cold.surface_screen(b,refs);r=snapshot.check()
        assert r['ok']==a['ok'] and r['conflicts']==a['conflicts']
        assert r['warm_stationary_obstacles_reused'] and r['moving_land_shapes_redecoded']
        assert not r['routing_admitted'] and not r['release_authority']

@pytest.mark.parametrize('fault',['track_move','track_width','track_net','foreign_pad_angle','foreign_pad_shape',
    'foreign_pad_size','foreign_pad_radius','foreign_pad_clearance','minimum_clearance','query_face','add_copper_graphic'])
def test_native_geometry_rules_and_layer_mutations_never_reuse_old_obstacles(fault):
    b,moving,pad,edge,point=board_case()
    fixed=pcbnew.FOOTPRINT(b);fixed.SetReference('fixed');b.Add(fixed)
    other=pcbnew.PAD(fixed);other.SetAttribute(pcbnew.PAD_ATTRIB_SMD);other.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    other.SetSize(pcbnew.VECTOR2I_MM(1,2));other.SetPosition(point(20,20));other.SetNet(b.FindNet('FOREIGN'))
    faces=pcbnew.LSET();faces.AddLayer(pcbnew.F_Cu);other.SetLayerSet(faces);fixed.Add(other)
    snap=warm.Snapshot(b,{moving.GetReference()})
    if fault=='track_move':edge.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='track_width':edge.SetWidth(edge.GetWidth()+1)
    elif fault=='track_net':edge.SetNet(b.FindNet('GND'))
    elif fault=='foreign_pad_angle':other.SetOrientationDegrees(90)
    elif fault=='foreign_pad_shape':other.SetShape(pcbnew.PAD_SHAPE_RECT)
    elif fault=='foreign_pad_size':other.SetSize(other.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='foreign_pad_radius':other.SetRoundRectRadiusRatio(.2)
    elif fault=='foreign_pad_clearance':other.SetLocalClearance(500001)
    elif fault=='minimum_clearance':b.GetDesignSettings().m_MinClearance+=1
    elif fault=='query_face':
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(mask)
    else:
        g=pcbnew.PCB_SHAPE(b);g.SetLayer(pcbnew.F_Cu);g.SetShape(pcbnew.SHAPE_T_SEGMENT)
        g.SetStart(point(0,0));g.SetEnd(point(1,1));g.SetWidth(100000);b.Add(g)
    with pytest.raises(ValueError):snap.check()

def test_unsupported_native_copper_graphics_use_the_fresh_cold_checker():
    b,moving,pad,edge,point=board_case()
    g=pcbnew.PCB_SHAPE(b);g.SetLayer(pcbnew.F_Cu);g.SetShape(pcbnew.SHAPE_T_SEGMENT)
    g.SetStart(point(2,2));g.SetEnd(point(4,4));g.SetWidth(100000);b.Add(g)
    refs={moving.GetReference()};s=warm.Snapshot(b,refs);assert not s.supported
    a=cold.surface_screen(b,refs);r=s.check();assert r['ok']==a['ok'] and r['conflicts']==a['conflicts']

@pytest.mark.parametrize('seconds',[True,0,10.01,float('nan')])
def test_no_unbounded_native_lease(seconds):
    b,moving,pad,edge,point=board_case()
    with pytest.raises(ValueError):warm.Snapshot(b,{moving.GetReference()},timeout_s=seconds)
