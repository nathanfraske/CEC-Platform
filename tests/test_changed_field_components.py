import pcbnew
import pytest
import cec_support_field_reflow as ink
import cec_force_current as force


def board_at(points):
    b=pcbnew.CreateEmptyBoard();fps=[]
    for i,(x,y) in enumerate(points):
        f=pcbnew.FOOTPRINT(b);f.SetReference('RENAMED'+str(i));b.Add(f)
        f.SetPosition(pcbnew.VECTOR2I_MM(x,y));fps.append(f)
    return b,fps


@pytest.mark.parametrize('angle',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_independent_domains_get_separate_bounds_neighboring_domains_are_joint(monkeypatch,angle,mirror):
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle):x,y=-y,x
        return x+100,y+100
    b,fps=board_at([at(x,y) for x,y in [(0,0),(2,0),(4,0),(30,0),(31,0),(60,0),(61,0),(90,0),(91,0)]])
    calls=[]
    def solve(board,ids,**kwargs):
        assert kwargs['include_changed_owners'] and kwargs['timeout_s']==10.
        calls.append(set(ids));return dict(ok=True)
    monkeypatch.setattr(ink,'construct_collision_cohort',solve)
    r=ink.construct_changed_components(b,[force._uid(f) for f in reversed(fps)])
    assert r['ok'] and not r['release_authority']
    assert sorted(len(g) for g in calls)==[2,2,2,3]
    assert set().union(*calls)=={force._uid(f) for f in fps}


def test_failed_second_component_atomically_restores_all_owner_and_neighbor_field_poses(monkeypatch):
    b,fps=board_at([(0,0),(30,0),(60,0)])
    original=[(force._uid(f),tuple(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in fps for f in (fp.Reference(),fp.Value())]
    calls=[]
    def solve(board,ids,**kwargs):
        calls.append(ids)
        for fp in fps:
            fp.Reference().Move(pcbnew.VECTOR2I(1,1))
            fp.Value().SetTextAngle(pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        return dict(ok=len(calls)<2)
    monkeypatch.setattr(ink,'construct_collision_cohort',solve)
    r=ink.construct_changed_components(b,[force._uid(f) for f in fps[:2]])
    assert not r['ok'] and len(calls)==2
    assert original==[(force._uid(f),tuple(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in fps for f in (fp.Reference(),fp.Value())]


@pytest.mark.parametrize('fault',['duplicate','missing','too_many','nan','infinite','zero','component_bound'])
def test_invalid_or_overlapping_unbounded_components_are_not_silently_split(monkeypatch,fault):
    b,fps=board_at([(i,0) for i in range(9)])
    ids=[force._uid(f) for f in fps];kwargs={}
    if fault=='duplicate':ids[0]=ids[1]
    elif fault=='missing':ids[0]='missing'
    elif fault=='too_many':ids=['missing'+str(i) for i in range(65)]
    elif fault in ('nan','infinite','zero'):kwargs['timeout_per_component_s']={'nan':float('nan'),'infinite':float('inf'),'zero':0}[fault]
    calls=[];monkeypatch.setattr(ink,'construct_collision_cohort',lambda *a,**k:calls.append(a))
    if fault=='component_bound':assert not ink.construct_changed_components(b,ids)['ok']
    else:
        with pytest.raises(ValueError):ink.construct_changed_components(b,ids,**kwargs)
    assert not calls
