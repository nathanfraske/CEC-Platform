"""Expose an existing ordinary via/body contact without changing copper.

Only an exact interior lattice projection on a canonical straight native
track may split it. Equal-width collinear capsules preserve the complete
original material; no via, pad, zone, group or width moves. This preparation
does not grant subsequent via-motion, clearance, capacity or release rights.
"""
from fractions import Fraction
from pathlib import Path
import math
import tempfile
import time
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_route_quality as quality


def plan(board, requests, *, source_path, board_hint, timeout_s=3.):
    if (type(requests) not in (list,tuple) or not 1<=len(requests)<=8
            or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or Path(source_path).resolve()!=Path(board.GetFileName()).resolve()):
        raise ValueError('bounded_exact_source_native_body_split_required')
    deadline=time.monotonic()+timeout_s
    items={force._uid(t):t for t in board.GetTracks()}
    if len(items)>16384:raise ValueError('native_body_split_inventory_bound')
    allowed=ordinary.eligible_nets(board,Path(source_path),board_hint)
    seen=set();rows=[]
    for r in requests:
        if time.monotonic()>=deadline:raise ValueError('native_body_split_deadline')
        if (type(r) is not dict or set(r)!={'via_uuid','track_uuid','locked_source_requested'}
                or type(r['locked_source_requested']) is not bool
                or r['track_uuid'] in seen or not {r['via_uuid'],r['track_uuid']}<=items.keys()):
            raise ValueError('unique_literal_native_body_split_identity_required')
        seen.add(r['track_uuid']);v,t=items[r['via_uuid']],items[r['track_uuid']]
        if (v.GetClass()!='PCB_VIA' or t.GetClass()!='PCB_TRACK'
                or v.GetParentGroup() is not None or t.GetParentGroup() is not None
                or str(t.GetNetname()) not in allowed or v.GetNetname()!=t.GetNetname()
                or not v.IsOnLayer(t.GetLayer()) or r['locked_source_requested']!=t.IsLocked()
                or not 0<t.GetLength()<=32000000):
            raise ValueError('ordinary_ungrouped_native_body_contact_required')
        a,b,p=tuple(t.GetStart()),tuple(t.GetEnd()),tuple(v.GetPosition())
        if not quality.is_canonical_stroke(a,b,tolerance_nm=0):
            raise ValueError('canonical_source_body_split_required')
        if any(v.GetEffectiveShape(t.GetLayer()).Collide(at,0) for at in (t.GetStart(),t.GetEnd())):
            raise ValueError('existing_native_endpoint_contact_needs_no_body_split')
        if not v.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(t.GetLayer()),0):
            raise ValueError('actual_native_via_body_contact_required')
        dx,dy=b[0]-a[0],b[1]-a[1];length2=dx*dx+dy*dy
        fraction=Fraction((p[0]-a[0])*dx+(p[1]-a[1])*dy,length2)
        if not 0<fraction<1:raise ValueError('interior_native_body_projection_required')
        point=[Fraction(x)+fraction*d for x,d in zip(a,(dx,dy))]
        if any(q.denominator!=1 for q in point):
            raise ValueError('exact_native_lattice_projection_required')
        point=[int(q) for q in point]
        if (not v.GetEffectiveShape(t.GetLayer()).Collide(pcbnew.VECTOR2I(*point),0)
                or min(math.dist(point,q) for q in (a,b))<10000):
            raise ValueError('positive_native_split_cap_contact_and_nonzero_legs_required')
        rows.append(dict(via_uuid=r['via_uuid'],track_uuid=r['track_uuid'],net=str(t.GetNetname()),
            source_nm=[list(a),list(b)],split_nm=point,source_width_nm=int(t.GetWidth()),
            layer_id=int(t.GetLayer()),source_locked=t.IsLocked(),
            exact_equal_width_collinear_capsule_union=True))
    return dict(schema=1,scope='ordinary_native_body_contact_copper_equivalent_split',
        source_sha256=force._hash(Path(source_path)),requests=list(requests),rows=rows,
        no_source_copper_removed_or_added=True,no_new_barrels=True,
        routing_admitted=False,current_qualified=False,release_authority=False)


def materialize(board, proposal, *, source_path, board_hint, _incoming_uuids=None):
    actual=plan(board,proposal['requests'],source_path=source_path,board_hint=board_hint)
    if actual!=proposal:raise ValueError('source_body_split_proposal_changed')
    ids={force._uid(t) for t in board.GetTracks()}
    if _incoming_uuids is not None and (type(_incoming_uuids) not in (list,tuple)
            or len(_incoming_uuids)!=len(actual['rows']) or len(set(_incoming_uuids))!=len(_incoming_uuids)
            or any(type(u) is not str or u in ids for u in _incoming_uuids)):
        raise ValueError('exact_independent_body_split_replay_ids_required')
    live={force._uid(t):t for t in board.GetTracks()};created=[]
    for i,row in enumerate(actual['rows']):
        old=live[row['track_uuid']];part=old.Duplicate();part.m_Uuid.Clone(pcbnew.KIID())
        if _incoming_uuids is not None:part.m_Uuid.Clone(pcbnew.KIID(_incoming_uuids[i]))
        part.SetStart(pcbnew.VECTOR2I(*row['split_nm']));part.SetEnd(pcbnew.VECTOR2I(*row['source_nm'][1]))
        old.SetEnd(pcbnew.VECTOR2I(*row['split_nm']));board.Add(part)
        created.append(force._uid(part))
    return dict(incoming_track_uuids=created,original_track_ids_retained=True,
        all_original_copper_preserved=True,no_new_vias=True,
        independent_saved_receiving_required=True,routing_admitted=False,release_authority=False)


def receive(source, candidate, requests, *, board_hint):
    result=dict(schema=1,scope='independent_saved_ordinary_body_split_receiving',ok=False,complete=False,
        errors=[],current_qualified=False,routing_admitted=False,release_authority=False)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        a,b=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proof=plan(a,requests,source_path=source,board_hint=board_hint)
        old={force._uid(t):t for t in a.GetTracks()};new={force._uid(t):t for t in b.GetTracks()}
        added=set(new)-set(old)
        if set(old)-set(new) or len(added)!=len(proof['rows']):
            raise ValueError('exact_saved_body_split_population_required')
        incoming=[]
        for row in proof['rows']:
            choices=[u for u in added if new[u].GetClass()=='PCB_TRACK'
                and str(new[u].GetNetname())==row['net'] and int(new[u].GetLayer())==row['layer_id']
                and tuple(new[u].GetStart())==tuple(row['split_nm'])
                and tuple(new[u].GetEnd())==tuple(row['source_nm'][1])]
            if len(choices)!=1:raise ValueError('literal_saved_second_body_leg_required')
            incoming.append(choices[0]);added.remove(choices[0])
        with tempfile.TemporaryDirectory(prefix='cec-native-body-split-receiving-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected')
            expected=pcbnew.LoadBoard(str(path))
            expected_plan=plan(expected,requests,source_path=path,board_hint=board_hint)
            materialize(expected,expected_plan,source_path=path,board_hint=board_hint,_incoming_uuids=incoming)
            field._save_field_snapshot(expected,path)
            want_root,want=additive._nodes(path);got_root,got=additive._nodes(candidate)
            if (syntax._freeze(want_root)!=syntax._freeze(got_root)
                    or want.keys()!=got.keys() or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in want)):
                raise ValueError('exact_independent_body_split_native_replay_differs')
        if force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('body_split_source_sidecars_changed')
        retired={r['track_uuid'] for r in proof['rows']}
        first=ordinary._partition(a,time.monotonic()+10.,retired_uuids=retired)
        keys=set().union(*first);last=ordinary._partition(b,time.monotonic()+10.,retained_keys=keys)
        if not all(any(p<=q for q in last) for p in first):
            raise ValueError('body_split_source_native_partition_lost')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('body_split_source_family_or_code_changed')
        result.update(ok=True,complete=True,plan=proof,incoming_track_uuids=incoming,
            exact_independent_native_replay=True,all_retained_native_partitions_preserved=True,
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,actual_copper_geometry_unchanged=True)
    except (ValueError,KeyError,TypeError,StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
