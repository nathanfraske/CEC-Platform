"""Bounded lazy field-conflict guidance for a native coupled corridor.

The final, unchanged whole-route field predicate supplies each no-good. A
no-good only prunes subsequent proposals in this invocation; it grants no
shielding, connectivity, current, pair or release authority. No board copper
is constructed here and no net/refdes/coordinate exception is permitted.
"""
import math
import time

import cec_fr as fr
import cec_field_coupling as field
import cec_precision_route as route


class Guide:
    def __init__(self, board, pair, *, layer, step_mm, deadline,
                 netclass_resolver=None, native_validator=None,
                 mandatory_throats_mm=(), board_hint=None):
        if (type(step_mm) not in (int,float) or not math.isfinite(step_mm)
                or not .1 <= step_mm <= .75
                or type(deadline) not in (int,float) or not math.isfinite(deadline)):
            raise ValueError('finite_native_pair_field_guidance_required')
        if (not isinstance(pair,dict) or not all(isinstance(pair.get(k),str)
                and pair[k] for k in ('p','n')) or pair['p']==pair['n']
                or any(type(pair.get(k)) not in (int,float)
                    or not math.isfinite(pair[k]) for k in ('width','gap'))
                or not 0<pair['width']<=5 or not 0<=pair['gap']<=5
                or not 0<deadline-time.monotonic()<=60.1):
            raise ValueError('two_actual_pair_members_required')
        self.board,self.pair,self.layer=board,pair,int(layer)
        self.step,self.deadline=step_mm,deadline
        self.resolve,self.native_validator=netclass_resolver,native_validator
        self.board_hint=board_hint
        self.no_goods=[];self.proofs=[];self.refusals=0;self.incomplete=False
        if (not isinstance(mandatory_throats_mm,(list,tuple))
                or len(mandatory_throats_mm)>2):
            raise ValueError('bounded_directed_terminal_throats_required')
        self.mandatory_throats=[]
        for throat in mandatory_throats_mm:
            if (not isinstance(throat,(list,tuple)) or len(throat)!=2
                    or any(not isinstance(p,(list,tuple)) or len(p)!=2
                        or any(type(v) not in (int,float) or not math.isfinite(v) for v in p)
                        for p in throat)
                    or not 0<max(abs(throat[1][i]-throat[0][i])
                        for i in (0,1))<=2*step_mm+1e-9):
                raise ValueError('bounded_directed_terminal_throats_required')
            self.mandatory_throats.append(tuple(tuple(p) for p in throat))
        self.retained_throat_edges=0
        self.native_tracks={str(t.m_Uuid.AsString()):
            (tuple(v/1e6 for v in t.GetStart()),tuple(v/1e6 for v in t.GetEnd()))
            for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}

    def paths(self, pp, nn):
        if self.native_validator is not None:
            native=self.native_validator(pp,nn)
            if native is not True and (not isinstance(native,dict) or not native.get('ok')):
                return native if isinstance(native,dict) else dict(ok=False)
        rows=[dict(net=net,layer=self.layer,start_nm=[fr._nm(x) for x in a],
            end_nm=[fr._nm(x) for x in b],width_nm=fr._nm(self.pair['width']))
            for net,points in ((self.pair['p'],pp),(self.pair['n'],nn))
            for a,b in zip(points,points[1:])]
        # Both members are one proposal. Keep the existing predicate and its
        # documented finite ceiling; do not interpret the smaller single-
        # track default's exhaustion as either a conflict or a pass.
        proof=field.assess_proposed_tracks(self.board,rows,
            netclass_resolver=self.resolve,deadline=self.deadline,
            max_interactions=2048,board_hint=self.board_hint)
        self.proofs.append(dict(ok=proof.get('ok'),complete=proof.get('complete'),
            reason=proof.get('reason'),new_blockers=proof.get('new_blockers',[])))
        if not proof.get('complete'):
            self.incomplete=True
            return dict(ok=False,reason='incomplete_native_pair_field_proof')
        if proof.get('ok') is True:
            return dict(ok=True,field_complete=True)
        for blocker in proof.get('new_blockers',[]):
            for uid in blocker.get('track_uuids',[]):
                if not isinstance(uid,str) or not uid.startswith('proposed-field-track:'):
                    continue
                suffix=uid.rsplit(':',1)[-1]
                if not suffix.isdigit() or not 0 <= int(suffix) < len(rows):
                    raise ValueError('field_no_good_proposed_identity_mismatch')
                row=rows[int(suffix)]
                a,b=[tuple(v/1e6 for v in row[k]) for k in ('start_nm','end_nm')]
                # A long proposed straight can fail beside one small peer.
                # Excluding its entire length would also block its exact
                # source/target headings, leaving no alternate route at all.
                # Clip this proposal no-good to the positively identified
                # peer's projection, not a guessed global interference halo.
                peers=[]
                for other in blocker.get('track_uuids',[]):
                    if other in self.native_tracks:peers.append(self.native_tracks[other])
                    elif isinstance(other,str) and other.startswith('proposed-field-track:'):
                        value=other.rsplit(':',1)[-1]
                        if value.isdigit() and int(value)!=int(suffix) and int(value)<len(rows):
                            peers.append(tuple(tuple(v/1e6 for v in rows[int(value)][k])
                                for k in ('start_nm','end_nm')))
                length=math.dist(a,b)
                if not peers or length<=0:
                    raise ValueError('field_no_good_native_peer_identity_missing')
                ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
                for first,last in peers:
                    projections=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (first,last))
                    low,high=max(0.,projections[0]),min(length,projections[1])
                    if high-low<=1e-9:
                        continue
                    clipped=(tuple(a[i]+low*(ux,uy)[i] for i in (0,1)),
                             tuple(a[i]+high*(ux,uy)[i] for i in (0,1)))
                    if clipped not in self.no_goods and tuple(reversed(clipped)) not in self.no_goods:
                        self.no_goods.append(clipped)
                if len(self.no_goods)>64:
                    self.incomplete=True
                    return dict(ok=False,reason='finite_field_no_good_budget_exhausted')
        return dict(ok=False,reason='actual_native_pair_field_conflict',
                    no_goods=len(self.no_goods))

    def edge(self, a, b):
        if self.incomplete or time.monotonic()>=self.deadline:
            return False
        query=dict(a=tuple(a),b=tuple(b))
        # A local search exclusion, never a claim that this whole area is
        # physically unroutable. A perpendicular crossing is still searchable.
        radius=4*self.step+(self.pair['width']+self.pair['gap'])/2
        for s,t in self.no_goods:
            failed=dict(a=s,b=t)
            if (field._acute_angle(query,failed)<=field.DEFAULT_PARALLEL_ANGLE_DEG
                    and field._segment_distance(query,failed)<=radius
                    and max(field._parallel_overlap(query,failed),
                            field._parallel_overlap(failed,query))>1e-9):
                # A failed LONG run is a search no-good, not proof that its
                # compulsory first/last grid edge is itself illegal. Erasing
                # a directed terminal throat made the next replay report
                # initial_heading_blocked before it could turn away. Preserve
                # only the exact finite mandatory throat; native collision,
                # member-pad, and complete unchanged field checks still apply.
                if any(self._inside_throat(a,b,first,last)
                        for first,last in self.mandatory_throats):
                    self.retained_throat_edges+=1
                    continue
                self.refusals+=1
                return False
        return True

    @staticmethod
    def _inside_throat(a,b,first,last):
        dx,dy=last[0]-first[0],last[1]-first[1]
        length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
        for p in (a,b):
            px,py=p[0]-first[0],p[1]-first[1]
            along=px*ux+py*uy
            if abs(px*uy-py*ux)>1e-8 or not -1e-8<=along<=length+1e-8:
                return False
        return True

    def report(self):
        return dict(scope='lazy_native_pair_field_proposal_guidance',
            no_goods=len(self.no_goods),pruned_edges=self.refusals,
            complete_route_proofs=self.proofs,incomplete=self.incomplete,
            mandatory_throats_mm=self.mandatory_throats,
            retained_mandatory_throat_edges=self.retained_throat_edges,
            board_mutated=False,no_path_proof=False,release_authority=False)


def coupled_path(board, *, pair, netclass_resolver=None, board_hint=None, max_attempts=8,
                 search_budget_s=10.,
                 diagnostics=None, **kwargs):
    if type(max_attempts) is not int or not 1<=max_attempts<=8:
        raise ValueError('bounded_pair_field_replay_required')
    requested=kwargs.get('deadline')
    if requested is not None and (type(requested) not in (int,float) or not math.isfinite(requested)):
        raise ValueError('finite_native_pair_field_guidance_required')
    if (not isinstance(pair,dict) or any(not isinstance(pair.get(k),str) or not pair[k]
            for k in ('p','n')) or pair['p']==pair['n']):
        raise ValueError('two_actual_pair_members_required')
    try:
        codes=tuple(board.GetNetcodeFromNetname(pair[k]) for k in ('p','n'))
    except (IndexError,KeyError) as exc:
        raise ValueError('positive_distinct_native_pair_codes_required') from exc
    if any(type(c) is not int or c<=0 for c in codes) or codes[0]==codes[1]:
        raise ValueError('positive_distinct_native_pair_codes_required')
    explicit=kwargs.get('pair_net_codes')
    if explicit is not None and (not isinstance(explicit,(list,tuple))
            or len(explicit)!=2 or any(type(c) is not int for c in explicit)
            or tuple(explicit)!=codes):
        raise ValueError('ordered_native_pair_codes_must_match_members')
    if 'own' in kwargs and set(kwargs['own'])!=set(codes):
        raise ValueError('native_pair_codes_must_match_excluded_nets')
    # Preserve lane polarity from actual named native nets. An unordered
    # exclusion set cannot supply P/N identity to the member obstacle guard.
    kwargs['pair_net_codes']=codes
    kwargs['own']=set(codes)
    if (type(search_budget_s) not in (int,float) or not math.isfinite(search_budget_s)
            or not 0<search_budget_s<=60.):
        raise ValueError('finite_bounded_pair_field_search_budget_required')
    deadline=min(time.monotonic()+search_budget_s,requested) if requested is not None else time.monotonic()+search_budget_s
    kwargs['deadline']=deadline
    binding=field._field_snapshot_inventory(board)
    step=kwargs.get('step',.5);throats=[]
    if kwargs.get('portal_mode'):
        for center_key,heading_key,turn_key,sign in (
                ('start_center','portal_start_heading','initial_turn_steps',1),
                ('end_center','portal_end_heading','terminal_turn_steps',-1)):
            center=kwargs.get(center_key);heading=kwargs.get(heading_key)
            turns=kwargs.get(turn_key,1)
            if (not isinstance(center,(list,tuple)) or len(center)!=2
                    or not isinstance(heading,(list,tuple)) or len(heading)!=2
                    or any(type(v) not in (int,float) or not math.isfinite(v)
                        for v in (*center,*heading))
                    or type(turns) is not int or turns not in (0,1)
                    or type(step) not in (int,float) or not math.isfinite(step)
                    or not .1<=step<=.75 or math.hypot(*heading)<=0):
                raise ValueError('bounded_directed_terminal_throats_required')
            # The native maze advances by (dx*step,dy*step), not a
            # Euclidean-normalized step. Match its nearest octilinear
            # direction: a diagonal first edge is sqrt(2)*step long.
            directions=((1,0),(1,1),(0,1),(-1,1),
                        (-1,0),(-1,-1),(0,-1),(1,-1))
            snapped=max(directions,key=lambda d:
                sum(heading[i]*d[i] for i in (0,1))/math.hypot(*d))
            scale=sign*step*(turns+1)
            throats.append((tuple(center),tuple(center[i]+snapped[i]*scale for i in (0,1))))
    guide=Guide(board,pair,layer=kwargs['layer_id'],step_mm=kwargs.get('step',.5),
        deadline=deadline,netclass_resolver=netclass_resolver,
        native_validator=kwargs.pop('path_validator',None),mandatory_throats_mm=throats,
        board_hint=board_hint)
    outer=kwargs.pop('edge_validator',None)
    attempts=[];result=None
    for index in range(max_attempts):
        if time.monotonic()>=deadline or guide.incomplete:
            break
        old=len(guide.no_goods);detail={}
        result=route._grid_coupled_path(board,**kwargs,diagnostics=detail,
            path_validator=guide.paths,
            edge_validator=lambda a,b: guide.edge(a,b) and (outer is None or outer(a,b)))
        attempts.append(dict(status=detail.get('status'),visited=detail.get('visited'),
            learned_no_goods=len(guide.no_goods)-old,grid=detail))
        if result or len(guide.no_goods)==old:
            break
    if diagnostics is not None:
        diagnostics.update(status='accepted' if result else 'refused',attempts=attempts,
            field_guidance=guide.report(),ordered_native_pair_net_codes=list(codes))
    if field._field_snapshot_inventory(board)!=binding:
        raise ValueError('pair_field_proposal_search_changed_native_source')
    return result
