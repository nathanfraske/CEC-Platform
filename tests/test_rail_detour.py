import time
import pytest
from shapely.geometry import box,LineString,Point
from shapely.affinity import translate
from cec_rail_detour import repair_plan


def test_contact_targets_use_actual_layer_and_projected_trunk_not_a_planned_band():
    from cec_rail_detour import contact_targets
    trunk=[(8.,2.,8.,12.,2.,'actual'),(1.,4.,9.,4.,2.,'old-layer')]
    assert contact_targets((2.,6.),trunk,'actual')==[(8.,6.)]
    assert contact_targets((2.,6.),trunk,'absent')==[]
    assert contact_targets((2.,6.),trunk,'actual',limit=0)==[]


@pytest.mark.parametrize('offset',[(0,0),(43,-17),(-55,90)])
def test_width_layer_and_middle_branch_are_preserved(offset):
    x,y=offset
    plan=[(x+1,y+5,x+19,y+5,1.,'declared-layer'),
          (x+13,y+5,x+13,y+9,1.,'declared-layer')]
    obstacles=[translate(box(6,3,10,7),xoff=x,yoff=y)]
    def collision(rows):
        return 'foreign copper' if any(LineString((s[:2],s[2:4])).buffer(s[4]/2).intersects(o)
            for s in rows for o in obstacles) else None
    result,report=repair_plan(plan,region=translate(box(0,0,21,11),xoff=x,yoff=y),
        obstacles_for=lambda _:obstacles,collision=collision)
    assert result and report['changed'] and not report['admitted']
    assert collision(result) is None
    assert {(s[4],s[5]) for s in result}=={(1.,'declared-layer')}
    assert any(s[:2]==(x+13,y+5) or s[2:4]==(x+13,y+5) for s in result[:-1])


def test_blocked_fixed_junction_refuses_instead_of_dropping_branch():
    plan=[(1,5,19,5,1,'layer'),(8,5,8,9,1,'layer')]
    obstacle=box(6,3,10,7)
    result,report=repair_plan(plan,region=box(0,0,21,11),obstacles_for=lambda _:[obstacle],
        collision=lambda rows:'blocked' if any(LineString((s[:2],s[2:4])).intersects(obstacle)
                                              for s in rows) else None)
    assert result is None and report['reason']=='fixed_terminal_or_channel_blocked'
    assert plan==[(1,5,19,5,1,'layer'),(8,5,8,9,1,'layer')]


def test_deadline_refuses_without_partially_replacing_graph():
    result,report=repair_plan([(1,5,19,5,1,'layer')],region=box(0,0,21,11),
        obstacles_for=lambda _:[],collision=lambda _:'blocked',deadline=time.monotonic()-1)
    assert result is None and report['reason']=='bounded_search_exhausted'


def _collision(obstacles):
    return lambda rows: 'blocked' if any(
        LineString((s[:2],s[2:4])).buffer(s[4]/2).intersects(o)
        for s in rows for o in obstacles) else None


@pytest.mark.parametrize('offset', [(0,0),(43,-17),(-55,90)])
@pytest.mark.parametrize('reverse', [False, True])
def test_virtual_elbow_is_not_a_physical_anchor(offset, reverse):
    x,y=offset
    plan=[(x+2,y+2,x+12,y+2,1,'route'),(x+12,y+2,x+12,y+12,1,'route')]
    if reverse:
        plan=[(*s[2:4],*s[:2],*s[4:]) for s in reversed(plan)]
    obstacles=[translate(box(10,0,14,4),xoff=x,yoff=y)]
    result,report=repair_plan(plan,region=translate(box(0,0,16,16),xoff=x,yoff=y),
        obstacles_for=lambda _:obstacles,collision=_collision(obstacles),
        anchors=[(x+2,y+2),(x+12,y+12)],relax_unanchored_bends=True)
    assert result and report['changed'] and not report['admitted']
    assert _collision(obstacles)(result) is None
    assert report['detours'][0]['virtual_bends'][0] == [x+12,y+2]
    assert {tuple(p) for p in report['detours'][0]['fixed_junctions']} == {
        (x+2,y+2),(x+12,y+12)}
    assert {(s[4],s[5]) for s in result} == {(1,'route')}
    assert all(abs(s[2]-s[0])<1e-8 or abs(s[3]-s[1])<1e-8
               or abs(abs(s[2]-s[0])-abs(s[3]-s[1]))<1e-8 for s in result)


@pytest.mark.parametrize('kind', ['explicit','branch','width','layer'])
def test_real_junction_stays_fixed_even_when_obstructed(kind):
    plan=[(2,2,12,2,1,'route'),(12,2,12,12,1,'route')]
    anchors=[]
    if kind=='explicit': anchors=[(12,2)]
    if kind=='branch': plan.append((12,2,16,2,1,'route'))
    if kind=='width': plan[1]=(12,2,12,12,2,'route')
    if kind=='layer': plan[1]=(12,2,12,12,1,'another-layer')
    obstacle=box(10,0,14,4)
    result,report=repair_plan(plan,region=box(0,0,20,20),
        obstacles_for=lambda _:[obstacle],collision=_collision([obstacle]),
        anchors=anchors,relax_unanchored_bends=True)
    assert result is None
    assert report['reason']=='fixed_terminal_or_channel_blocked'
    assert report['start_legal'] is False or report['end_legal'] is False


def test_virtual_bend_relaxation_is_opt_in():
    obstacle=box(10,0,14,4)
    result,report=repair_plan([(2,2,12,2,1,'route'),(12,2,12,12,1,'route')],
        region=box(0,0,16,16),obstacles_for=lambda _:[obstacle],
        collision=_collision([obstacle]))
    assert result is None and report['reason']=='fixed_terminal_or_channel_blocked'


def test_implicit_middle_branch_remains_connected_when_virtual_elbow_moves():
    plan=[(2,2,12,2,1,'route'),(12,2,12,15,1,'route'),
          (12,10,17,10,1,'route')]
    obstacle=box(10,0,14,4)
    result,report=repair_plan(plan,region=box(0,0,20,20),
        obstacles_for=lambda _:[obstacle],collision=_collision([obstacle]),
        relax_unanchored_bends=True)
    assert result and report['changed']
    assert (12,10) in [tuple(p) for p in report['detours'][0]['fixed_junctions']]
    assert any(s[:2]==(12,10) and s[2:4]==(17,10) or
               s[:2]==(17,10) and s[2:4]==(12,10) for s in result)


def test_chain_traversal_preserves_widths_when_declaration_starts_at_transition():
    from cec_rail_detour import _anchor_chains
    plan=[(2,2,4,2,1,'x'),(4,2,4,4,1,'x'),(4,4,8,4,2,'x')]
    points={p for s in plan for p in (s[:2],s[2:4])}
    for ordered in (plan,list(reversed(plan)),[plan[1],plan[2],plan[0]]):
        chains=_anchor_chains(ordered,points,set())
        assert sorted((parts[0][4],joints) for _,parts,joints,_ in chains) == [
            (1,[(2,2),(4,4)]),(2,[(4,4),(8,4)])]


def test_closed_cycle_is_never_collapsed_to_nothing():
    from cec_rail_detour import _anchor_chains
    plan=[(2,2,8,2,1,'x'),(8,2,8,8,1,'x'),
          (8,8,2,8,1,'x'),(2,8,2,2,1,'x')]
    points={p for s in plan for p in (s[:2],s[2:4])}
    chains=_anchor_chains(plan,points,set())
    assert len(chains)==4 and sum(len(parts) for _,parts,_,_ in chains)==4
    assert all(a!=b for _,_,(a,b),_ in chains)


def test_degenerate_edge_is_retained_without_following_it_forever():
    from cec_rail_detour import _anchor_chains
    chains=_anchor_chains([(5,5,5,5,1,'x')],{(5,5)},set())
    assert len(chains)==1 and chains[0][1]==[(5,5,5,5,1,'x')]


@pytest.mark.parametrize('offset',[(0,0),(43,-17)])
@pytest.mark.parametrize('reverse',[False,True])
def test_clear_but_backtracking_virtual_transition_body_is_rebuilt(offset,reverse):
    from cec_rail_detour import has_virtual_backtrack
    x,y=offset
    plan=[(x+2,y+2,x+10,y+2,1,'route'),(x+10,y+2,x+8,y+4,1,'route')]
    if reverse:plan=[(*s[2:4],*s[:2],*s[4:]) for s in reversed(plan)]
    anchors=[(x+2,y+2),(x+8,y+4)]
    assert has_virtual_backtrack(plan,anchors=anchors)
    result,report=repair_plan(plan,region=translate(box(0,0,16,16),xoff=x,yoff=y),
        obstacles_for=lambda _:[],collision=lambda _:None,anchors=anchors,
        relax_unanchored_bends=True,repair_topology=True)
    assert report['changed'] and not report['admitted']
    assert not has_virtual_backtrack(result,anchors=anchors)
    assert {(s[4],s[5]) for s in result}=={(1,'route')}
    assert {p for p in anchors} <= {p for s in result for p in (s[:2],s[2:4])}
    assert report['detours'][0]['trigger']=='acute_virtual_backtrack'


@pytest.mark.parametrize('kind',['opt_out','explicit','width','layer','branch'])
def test_topology_polish_cannot_rewrite_physical_or_branched_vertices(kind):
    from cec_rail_detour import has_virtual_backtrack
    plan=[(2,2,10,2,1,'route'),(10,2,8,4,1,'route')]
    anchors=[(2,2),(8,4)]
    if kind=='explicit':anchors.append((10,2))
    elif kind=='width':plan[1]=(*plan[1][:4],2,'route')
    elif kind=='layer':plan[1]=(*plan[1][:5],'other')
    elif kind=='branch':plan.append((10,2,10,8,1,'route'))
    result,report=repair_plan(plan,region=box(0,0,16,16),obstacles_for=lambda _:[],
        collision=lambda _:None,anchors=anchors,relax_unanchored_bends=True,
        repair_topology=kind!='opt_out')
    assert not report['changed']
    assert (10,2) in {p for s in result for p in (s[:2],s[2:4])}
    if kind!='opt_out':assert not has_virtual_backtrack(plan,anchors=anchors)
