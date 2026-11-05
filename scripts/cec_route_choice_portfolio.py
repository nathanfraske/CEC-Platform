"""Bounded deterministic retention of ALREADY guarded routing choices.

Generation order is not topology priority: a full surface menu must not erase
later legal layer bridges. This module grants no geometry, layer, current or
source ownership permission. All existing producers/receivers remain due.
"""
import json
import math


def _key(choice):
    if type(choice)is not dict or type(choice.get('ops'))is not list:
        raise ValueError('explicit_guarded_choice_ops_required')
    cost=choice.get('cost')
    if type(cost)not in(int,float)or not math.isfinite(cost)or cost<0:
        raise ValueError('finite_nonnegative_guarded_choice_cost_required')
    layers=set();vias=0
    for op in choice['ops']:
        if type(op)not in(list,tuple)or not op:
            raise ValueError('known_guarded_native_operation_required')
        if op[0]=='trk':
            if len(op)!=5 or type(op[4])is not int:
                raise ValueError('actual_guarded_track_layer_required')
            layers.add(op[4])
        elif op[0]=='via':
            if len(op)!=4:raise ValueError('known_guarded_barrel_operation_required')
            vias+=1
        else:raise ValueError('unknown_guarded_native_operation')
    # Dependency alternatives remain distinct: a cheap path that owes another
    # Ground root cannot replace the only independent path, or vice versa.
    dependency=json.dumps(choice.get('requires_ground_entry'),sort_keys=True,allow_nan=False)
    signature=(tuple(sorted(layers)),vias,dependency)
    geometry=json.dumps(choice['ops'],separators=(',',':'),allow_nan=False)
    return signature,(float(cost),geometry,dependency)


def retain(choices,candidate,*,capacity):
    """Insert/rebalance in place, never exceeding the original <=48 slots.

    Evict from the most overrepresented physical topology first, retaining
    cheaper alternatives within that topology. If all topologies are unique
    and the bound cannot represent another, ordinary cost wins. Existing IDs
    are opaque; the owning menu assigns final IDs after generation finishes.
    """
    if (type(choices)is not list or type(capacity)is not int or not 1<=capacity<=48
            or len(choices)>capacity):
        raise ValueError('bounded_guarded_choice_portfolio_required')
    incoming,rank=_key(candidate)
    keys=[_key(q)for q in choices]
    if any(q['ops']==candidate['ops']and q.get('requires_ground_entry')==
            candidate.get('requires_ground_entry')for q in choices):
        return dict(retained=False,duplicate=True,evicted=False)
    if len(choices)<capacity:
        choices.append(candidate)
        return dict(retained=True,duplicate=False,evicted=False)
    counts={}
    for signature,_ in [*keys,(incoming,rank)]:counts[signature]=counts.get(signature,0)+1
    largest=max(counts.values())
    # Include the incoming choice in the same election: an inferior duplicate
    # of an already overrepresented topology may itself be the one discarded.
    pool=[(i,s,r)for i,(s,r)in enumerate([*keys,(incoming,rank)])if counts[s]==largest]
    victim=max(pool,key=lambda row:(row[2],row[1],row[0]))[0]
    if victim==len(choices):
        return dict(retained=False,duplicate=False,evicted=False)
    choices.pop(victim);choices.append(candidate)
    return dict(retained=True,duplicate=False,evicted=True)
