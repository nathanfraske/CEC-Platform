"""Finite bidirectional frontier proposals; diagnostic paths grant no authority.

Only a complete, freshly rechecked Source-typed ordinary join may be saved.
Every local prefix and retained contact is independently rederived. A failed
partial path is never published on its own or treated as a no-path proof.
"""
import itertools
import json
import math
import time
from pathlib import Path


def _need(value,reason):
    if not value:raise ValueError(reason)


def _decode(rows,width,layers):
    import pcbnew
    _need(type(rows)is list and 1<=len(rows)<=128,'bounded_frontier_operations_required')
    result=[]
    for row in rows:
        _need(type(row)is dict,'literal_frontier_operation_required')
        if row.get('kind')=='trk':
            _need(set(row)=={'kind','start_nm','end_nm','width_nm','layer'}
                and row['width_nm']==width and type(row['width_nm'])is int
                and type(row['layer'])is int and row['layer']in layers
                and all(type(row[k])is list and len(row[k])==2
                    and all(type(x)is int for x in row[k])for k in('start_nm','end_nm')),
                'exact_frontier_track_geometry_required')
            a,b=row['start_nm'],row['end_nm'];dx,dy=b[0]-a[0],b[1]-a[1]
            _need((dx or dy)and(dx==0 or dy==0 or abs(dx)==abs(dy)),
                'canonical_nonzero_frontier_track_required')
            result.append(('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,row['layer']))
        else:
            _need(set(row)=={'kind','at_nm','drill_mm','diameter_mm'}and row['kind']=='via'
                and type(row['at_nm'])is list and len(row['at_nm'])==2
                and all(type(x)is int for x in row['at_nm'])
                and all(type(row[k])in(int,float)and math.isfinite(row[k])and 0<row[k]<=2
                    for k in('drill_mm','diameter_mm')),'bounded_frontier_barrel_geometry_required')
            result.append(('via',pcbnew.VECTOR2I(*row['at_nm']),row['drill_mm'],row['diameter_mm']))
    return result


def _rows(reports,board,roots,menus,local,width,layers):
    import cec_force_current as force
    from cec_route_proposal_guard import RouteProposalGuard as Guard
    allowed={force._uid(p):i for i,p in enumerate(roots)};found={}
    for report in reports:
        context=report.get('source_local_pad_rule_launches')or{}
        for attempt in context.get('attempts',[]):
            ends=attempt.get('local_endpoints',[])
            if len(ends)!=2:continue
            first=ends[0];contact=first.get('retained_native_contact',{})
            uid=(first.get('source_pad_uuid')or contact.get('pad_uuid')
                or contact.get('retained_same_face_root_pad_uuid'))
            if uid not in allowed:continue
            root=allowed[uid];prefix=first.get('operations',[])
            if prefix:
                # Fresh Source-rule plan, not a claimed historical boolean.
                matches=[e for pair in local for e in pair if e.get('source_pad_uuid')==uid
                    and json.dumps(e['operations'],allow_nan=False)==json.dumps(prefix,allow_nan=False)
                    and tuple(e['at_nm'])==tuple(first.get('at_nm',()))
                    and set(first.get('layers',[]))<=set(e['layers'])]
            else:
                matches=[e for e in menus[root]if tuple(e['at_nm'])==tuple(first.get('at_nm',()))
                    and set(first.get('layers',[]))<=set(e['layers'])]
            if not matches:continue
            for search in attempt.get('diagnostics',{}).get('middle_searches',[]):
                feedback=search.get('best_reached_prefix',{})
                if feedback.get('complete')is not True or feedback.get('complete_route')is not False:continue
                try:
                    ops=_decode(feedback['ops'],width,layers)
                    _need(ops[0][0]=='trk'and list(ops[0][1])==first['at_nm']
                        and ops[0][4]in first['layers'],'frontier_original_launch_required')
                    full=Guard._unpack(prefix)+ops
                    key=(root,Guard._pack(full));found.setdefault(key,dict(root=root,ops=full))
                except (ValueError,KeyError,TypeError,IndexError):continue
    # Stable finite menus, independent of worker completion timing.
    ranked=[[found[k]for k in sorted(found,key=lambda k:(len(k[1]),repr(k[1])))if k[0]==root]
        for root in(0,1)]
    return [rows[index]for index in range(16)for rows in ranked if index<len(rows)]


def _seats(row):
    result=[]
    for index,op in enumerate(row['ops']):
        if op[0]=='trk':result.append((tuple(op[2]),op[4],row['ops'][:index+1]))
    return result[-24:]


def _reverse(ops):
    return [('trk',op[2],op[1],op[3],op[4])if op[0]=='trk'else op for op in reversed(ops)]


def has_feedback(reports):
    return any(s.get('best_reached_prefix',{}).get('complete')is True
        for r in reports for a in(r.get('source_local_pad_rule_launches')or{}).get('attempts',[])
        for s in a.get('diagnostics',{}).get('middle_searches',[]))


def apply(candidate,target,seconds,reports):
    import pcbnew
    import cec_fr as fr
    import cec_force_current as force
    import cec_fab_profile as fab
    import cec_native_component_ports as ports
    import cec_native_portal_geometry as geometry
    import cec_source_rule_signal_launches as source_local
    import cec_certificate_repair as repair
    import cec_additive_pair_repair as additive
    from cec_route_proposal_guard import RouteProposalGuard as Guard
    from cec_field_search import PlanarSearchGuard
    deadline=time.monotonic()+geometry._budget(seconds);started=time.monotonic()
    _need(type(reports)is list and len(reports)<=16,'finite_frontier_worker_reports_required')
    epoch=force._code_identity();family=force._family(Path(candidate))
    board=pcbnew.LoadBoard(str(candidate));net=target['target_net'];code=board.GetNetcodeFromNetname(net)
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    roots=[pads.get(e['uuid'])for e in target['route_endpoints']]
    _need(code>0 and len(roots)==2 and all(p is not None and p.GetNetname()==net
        and tuple(p.GetPosition())==(round(e['x_mm']*1e6),round(e['y_mm']*1e6))
        for p,e in zip(roots,target['route_endpoints'])),'exact_frontier_native_roots_required')
    resolver=fr._project_netclass_resolver(str(candidate),board=board);spec=resolver(net)or{}
    width=round(target['width_mm']*1e6);gap=round(target['clearance_mm']*1e6)
    _need(width>=max(board.GetDesignSettings().m_TrackMinWidth,round(float(spec.get('track_width')or 0)*1e6))
        and gap>=max(board.GetDesignSettings().m_MinClearance,round(float(spec.get('clearance')or 0)*1e6)),
        'frontier_cannot_relax_project_geometry')
    layers=fr._lastmile_route_layers(board,net_name=net,spec=spec,exclude_front=False)
    inset_only=target.get('source_local_contained_intervals_only',False)
    _need(type(inset_only)is bool and(not inset_only or target.get('source_local_pad_rule_launches')is True),
        'explicit_frontier_contained_interval_policy_required')
    menus=[ports.same_face_track_endpoints(board,net,p,route_layers=layers,
        toward_nm=tuple(other.GetPosition()),max_sites=16,minimum_barrel_web_nm=width,
        deadline=min(deadline,time.monotonic()+1.))for p,other in((roots[0],roots[1]),(roots[1],roots[0]))]
    local,discovery=geometry._source_local_pair_menu(board,roots,menus,width=width,clearance=gap,
        layers=layers,deadline=deadline,**(dict(contained_intervals_only=True)if inset_only else{}))
    rows=_rows(reports,board,roots,menus,local,width,layers)
    result=dict(closed=0,scope='finite_freshly_rechecked_bidirectional_frontier_splice',
        elapsed_s=0.,rederived_frontiers=len(rows),tested_bridges=0,partial_route_published=False,
        release_authority=False,no_path_proof=False,refusal_counts={},refusal_samples=[],
        immutable_native_operation_cache_hits=0)
    guard=Guard(board,net,board_path=str(candidate),netclass_resolver=resolver,
        deadline=deadline,preflight_s=4.,board_hint=target.get('source_board_hint'))
    turns=ports.plain_endpoint_turn_guard(board,net);foreign={};holes=fr._via_hole_snapshot(board)
    prefixes={tuple(r)for pair in local for endpoint in pair for r in endpoint['operations']if r[0]=='via'}
    def refuse(reason,op=None):
        result['refusal_counts'][reason]=result['refusal_counts'].get(reason,0)+1
        if op is not None and len(result['refusal_samples'])<6:
            sample=dict(reason=reason,operation=list(Guard._pack([op])[0]))
            if reason=='foreign_copper_or_hole'and op[0]=='trk':
                zones,copper=fr._layer_foreign_shapes(board,op[4],{code},identified=True)
                sample['native_blockers']=fr._snapshot_foreign_blockers(op[1],op[2],op[3],gap,zones,copper,limit=8)
            if sample not in result['refusal_samples']:result['refusal_samples'].append(sample)
        return False
    native_verdicts={}
    def native_clear(op,packed):
        if op[0]=='trk':
            _,a,b,w,l=op
            if not fr._edge_leg_clear(board,a,b,(w+1)//2+gap):return refuse('edge',op)
            if not fr._tap_foreign_clear(board,a,b,w,l,gap,{code},foreign_cache=foreign):return refuse('foreign_copper_or_hole',op)
            if not source_local._immutable_power_clear(board,a,b,w,l,gap,code):return refuse('immutable_power',op)
        elif packed not in prefixes:
            dia,drill,_=fab.board_legal_through_via_geometry(board,op[3],op[2])
            if op[3]<dia or op[2]<drill:return refuse('ordinary_via_floor',op)
            if not fr._via_spot_clear(board,op[1],round(op[3]*1e6),gap,{code},
                drill_nm=round(op[2]*1e6),net_code=code,foreign_cache=foreign,_via_holes=holes):return refuse('ordinary_via_native_clearance',op)
        return True
    def clear(ops):
        if len(ops)>128:return refuse('operation_budget')
        vias=[]
        for op in ops:
            if time.monotonic()>=deadline:return refuse('deadline')
            packed=Guard._pack([op])[0]
            if op[0]=='via':vias.append(packed)
            if packed in native_verdicts:result['immutable_native_operation_cache_hits']+=1
            else:native_verdicts[packed]=native_clear(op,packed)
            if not native_verdicts[packed]:return False
        unique=set(vias);hole_gap=int(board.GetDesignSettings().m_HoleToHoleMin)
        if len(unique-prefixes)>2:return refuse('middle_barrel_budget')  # Not per half.
        if any(math.dist(a[1:3],b[1:3])<(a[3]+b[3])/2+hole_gap
                for a,b in itertools.combinations(unique,2)):return refuse('proposed_hole_clearance')
        return True
    pairs=[]
    for a in rows:
        if a['root']!=0:continue
        for b in rows:
            if b['root']!=1:continue
            choices=sorted(((math.dist(x,y),x,y,l,one,two)
                for x,l,one in _seats(a)for y,m,two in _seats(b)if l==m),key=lambda q:(q[0],q[1],q[2]))
            if choices:pairs.append(choices[:24])
    # Contact-pair fairness: a longer but genuinely different corridor must
    # not be starved by many tiny variations of one blocked nearest join.
    work=[q for depth in range(24)for pair in pairs if depth<len(pair)for q in[pair[depth]]][:512]
    for distance,a,b,layer,one,two in work:
        if time.monotonic()>=deadline:break
        for points in fr._canonical_45_xy_paths(a,b)if a!=b else[(a,)]:
            bridge=[('trk',pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*y),width,layer)
                for x,y in zip(points,points[1:])if x!=y]
            ops=[*one,*bridge,*_reverse(two)];result['tested_bridges']+=1
            if not clear(ops):continue
            if not turns(ops):refuse('complete_endpoint_turn');continue
            prepared=guard.prepare(ops)
            if prepared is None:continue
            _need(epoch==force._code_identity()and family==force._family(Path(candidate)),
                'frontier_source_or_code_epoch_changed')
            old={force._uid(t)for t in board.GetTracks()};before=fr.net_connectivity_component_count(board,code)
            repair._lay_ops(board,prepared,code,lock=False,reuse_existing_collinear=True)
            after=fr.net_connectivity_component_count(board,code)
            if after>=before:raise ValueError('complete_frontier_splice_did_not_join_native_components')
            _need(epoch==force._code_identity()and family==force._family(Path(candidate)),
                'frontier_source_or_code_epoch_changed')
            additive.save_native_additions(candidate,board,result,old,board_hint=target.get('source_board_hint'))
            result.update(closed=1,components_before=before,components_after=after)
            break
        if result['closed']:break
    result.update(elapsed_s=time.monotonic()-started,proposal_guard=guard.report())
    return result
