import pytest
from cec_pair_heading_boundary import feasible_edges,DIRECTIONS


@pytest.mark.parametrize('heading',range(8))
def test_goal_boundary_uses_incoming_not_outgoing_edge(heading):
    dx,dy=DIRECTIONS[heading];goal=(7,-3)
    required=((goal[0]-dx,goal[1]-dy),goal)
    seen=[]
    def clear(a,b):seen.append((a,b));return (a,b)==required
    assert feasible_edges(goal,heading,0,clear,incoming=True)==[heading]
    assert seen==[required]
    assert feasible_edges(goal,heading,0,clear)==[]


def test_reaching_goal_from_wrong_heading_does_not_qualify():
    assert feasible_edges((3,3),0,0,lambda a,b:a==(3,2),incoming=True)==[]
    assert feasible_edges((3,3),0,1,lambda a,b:a==(2,2),incoming=True)==[1]


@pytest.mark.parametrize('args',[(8,0),(-1,0),(1.2,0),(0,-1),(0,float('nan'))])
def test_invalid_heading_policy_fails(args):
    with pytest.raises(ValueError):feasible_edges((1,2),*args,lambda a,b:True)
