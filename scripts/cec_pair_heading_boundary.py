"""Necessary directed endpoint-edge feasibility for an octilinear pair grid."""
import math

DIRECTIONS=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))


def feasible_edges(node, heading, allowed_turn_steps, clear, *, incoming=False):
    """Return legal endpoint headings, not proof of a complete route.

    A goal's coordinate being reachable does not mean its required arrival
    direction is reachable. Check those exact final edges before spending a
    board-scale search budget. The caller supplies the same native envelope,
    material, clearance and learned-obstacle predicate used by its search.
    """
    count=len(DIRECTIONS)
    if not 0<=int(heading)<count or int(heading)!=heading:
        raise ValueError('invalid octilinear heading index')
    if not math.isfinite(allowed_turn_steps) or allowed_turn_steps<0:
        raise ValueError('invalid allowed heading turn')
    admitted=[]
    for index,(dx,dy) in enumerate(DIRECTIONS):
        turn=min(abs(index-heading),count-abs(index-heading))
        if turn>int(allowed_turn_steps):continue
        if incoming:
            a,b=(node[0]-dx,node[1]-dy),node
        else:
            a,b=node,(node[0]+dx,node[1]+dy)
        if clear(a,b):admitted.append(index)
    return admitted
