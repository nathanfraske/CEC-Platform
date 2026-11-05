"""Long paths still require native clearance in a fine interior channel."""
import math
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_maze_channels as channels


def native_channel(gap=.8):
    b=pcbnew.BOARD();b.SetCopperLayerCount(4)
    nets={}
    for name in ('ANY_SIGNAL','OTHER_COPPER'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    for y,size in ((2.525,5.05),((5.05+gap+10)/2,10-5.05-gap)):
        f=pcbnew.FOOTPRINT(b);b.Add(f)
        p=pcbnew.PAD(f);p.SetNet(nets['OTHER_COPPER']);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(16,size))
        p.SetPosition(pcbnew.VECTOR2I_MM(12,y));p.SetLayerSet(pcbnew.PAD.SMDMask());f.Add(p)
    for s,t in (((0,0),(24,0)),((24,0),(24,10)),((24,10),(0,10)),((0,10),(0,0))):
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*s));e.SetEnd(pcbnew.VECTOR2I_MM(*t));e.SetWidth(50000);b.Add(e)
    return b,nets['ANY_SIGNAL'].GetNetCode()


def maze_stage_only(monkeypatch):
    # Force uniform-lattice fallback with optional channel-axis proposals
    # unavailable. Native copper/edge/width/clearance guards stay real.
    monkeypatch.setattr(fr,'_canonical_45_xy_paths',lambda *a,**k:[])
    monkeypatch.setattr(fr,'_offset_manhattan_xy_paths',lambda *a,**k:[])
    monkeypatch.setattr(channels,'orthogonal_channel_paths',lambda *a,**k:[])
    monkeypatch.setattr(channels,'native_obstacle_boxes',lambda *a,**k:[])


def run(b,net,**options):
    return fr._guarded_profiled_lastmile_legs(b,pcbnew.VECTOR2I_MM(1,3),pcbnew.VECTOR2I_MM(23,7),
        200000,pcbnew.F_Cu,200000,net,
        lambda s,t,h:fr._edge_leg_clear(b,s,t,h+200000),
        allow_maze=True,maze_margin_mm=4,foreign_cache={},max_length_nm=35000000,**options)


def test_native_long_narrow_middle_channel_needs_explicit_finer_grid(monkeypatch):
    maze_stage_only(monkeypatch);b,net=native_channel();before=len(list(b.GetTracks()))
    coarse={};assert run(b,net,refine_maze=True,deadline_monotonic=time.monotonic()+10,
        search_diagnostics=coarse) is None
    assert coarse['maze_tiers'][0]['grid_mm']>=.75
    fine={};legs=run(b,net,refine_maze=True,refinement_grids_mm=(.25,.125),
        deadline_monotonic=time.monotonic()+10,search_diagnostics=fine)
    assert legs is not None,fine
    assert any(q['grid_mm'] in (.25,.125) and q['path_accepted'] for q in fine['maze_tiers'])
    assert all(w==200000 and fr._tap_foreign_clear(b,s,t,w,0,200000,{net}) for s,t,w in legs)
    assert len(list(b.GetTracks()))==before


def test_finer_grid_never_shrinks_copper_or_clearance_to_pass(monkeypatch):
    maze_stage_only(monkeypatch);b,net=native_channel(gap=.5)
    assert run(b,net,refine_maze=True,refinement_grids_mm=(.25,.125),
        deadline_monotonic=time.monotonic()+10) is None


@pytest.mark.parametrize('grids',[True,(.05,),(.6,),(math.nan,),(.1,.2),(.25,.25),(.5,.4,.3,.2)])
def test_invalid_middle_refinement_portfolio_fails_closed(grids):
    b,net=native_channel()
    with pytest.raises(ValueError):
        run(b,net,refine_maze=True,refinement_grids_mm=grids,deadline_monotonic=time.monotonic()+10)


def test_explicit_portfolio_requires_opt_in_and_finite_work_deadline():
    b,net=native_channel()
    with pytest.raises(ValueError):run(b,net,refinement_grids_mm=(.25,))
    with pytest.raises(ValueError):run(b,net,refine_maze=True,refinement_grids_mm=(.25,))


def test_no_refinement_stage_can_restart_an_expired_deadline(monkeypatch):
    maze_stage_only(monkeypatch);b,net=native_channel();diag={}
    assert run(b,net,refine_maze=True,refinement_grids_mm=(.25,.125),
        deadline_monotonic=time.monotonic()-1,search_diagnostics=diag) is None
    assert not diag.get('maze_tiers')
