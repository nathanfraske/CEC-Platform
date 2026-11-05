"""Cheap, immutable unshieldable planar field hints for exact route search.

This is a pruning predicate, NOT field admission or shielding proof. It
recognizes same-layer parallel runs and declared layer pairs with NO
intermediate dedicated GND role. It never assumes that a declared ground
layer is continuously filled or grants a shielding pass. Every complete
proposal must still pass the native/refilled
whole-route field receiver. No copper, rules, current budgets or plane
evidence are modified. Rebuild after any foreign-net material changes.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import cec_field_coupling as field
import cec_fab_profile as fab


_retained_shield_scope = ContextVar('cec_retained_shield_search_scope', default=None)


@contextmanager
def retained_shield_search(board, guard, *, deadline):
    """Plan-local pruning shared by every nested native barrel search.

    No global monkey patch, contact waiver, or receiving authority. The
    finite outer construction lease may contain at most eight 10 s slices.
    Other boards/nets and all normal searches retain the native predicate.
    """
    if (not isinstance(guard, RetainedShieldSearchGuard)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not 0 < deadline-time.monotonic() <= 80
            or _retained_shield_scope.get() is not None):
        raise ValueError('explicit_finite_retained_shield_search_scope_required')
    code = board.GetNetcodeFromNetname(guard.net)
    if code <= 0: raise ValueError('retained_shield_search_net_missing')
    token = _retained_shield_scope.set((board, code, guard, float(deadline)))
    try:
        yield guard
    finally:
        _retained_shield_scope.reset(token)


def retained_shield_barrel_allowed(board, at, diameter_nm, clearance_nm, net_code):
    scope = _retained_shield_scope.get()
    if scope is None or scope[0] is not board or scope[1] != net_code:
        return True
    if time.monotonic() >= scope[3]: return False
    return scope[2](tuple(at), int(diameter_nm), int(clearance_nm))


class RetainedShieldSearchGuard:
    """Conservative, plan-local reservations for measured source shielding.

    A legal new barrel can cut a GND plane and break an existing unrelated
    pair's shield. Native clearance alone cannot predict that failure. Reserve
    the actual plane-covered samples of risky, already shielded source pairs.
    This is an optional search exclusion, NOT a post-fill shielding proof;
    filler island changes and new-route interactions still need full receiving.
    Reconstruct this immutable scalar snapshot after any board mutation.
    """
    def __init__(self,board,net,*,board_path='',netclass_resolver=None,
                 max_relations=4096,max_samples=131072,max_interactions=16384,timeout_s=10.,
                 board_hint=None):
        if (not isinstance(net,str) or not net or type(max_relations) is not int
                or not 1<=max_relations<=4096 or type(max_samples) is not int
                or not 1<=max_samples<=131072 or type(timeout_s) not in (int,float)
                or type(max_interactions) is not int or not 1<=max_interactions<=131072
                or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
            raise ValueError('bounded_retained_shield_search_scope_required')
        if board_hint is not None and (type(board_hint) is not str or not board_hint.strip()):
            raise ValueError('nonempty_explicit_field_design_identity_required')
        self.net=net;self.calls=self.refusals=0;self.relations=0
        self.points=[];self.clearance_mm=board.GetDesignSettings().m_MinClearance/1e6
        self._tree=None
        self.source_interactions=0
        self.max_interactions=max_interactions
        self.board_hint=board_hint
        if net=='GND':return
        deadline=time.monotonic()+timeout_s
        # Full source inspection includes harmless/unshielded interactions.
        # Only the later filtered relations consume the reservation budget.
        # Conflating these counters aborts search before routing on larger
        # sources; neither finite bound changes the final shielding policy.
        work=field._ProposalWork(deadline,8192,8388608,131072,max_interactions)
        summary=field.field_coupling_summary(str(board_path),board=board,
            _netclass_resolver=netclass_resolver,_work=work,board_hint=board_hint)
        self.source_interactions=work.counts['interactions']
        live={str(t.m_Uuid.AsString()):t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}
        seen=set()
        for row in summary['interactions']:
            if time.monotonic()>=deadline:raise ValueError('retained_shield_search_snapshot_deadline')
            shield=row['shield']
            risky=(row['parallel_overlap_mm']>=field.DEFAULT_MINIMUM_PARALLEL_MM-1e-9
                or (row['projected_copper_overlap'] and row['angle_deg']<field.DEFAULT_PERPENDICULAR_MIN_DEG-1e-9))
            if not risky or not shield['shielded'] or not shield.get('selected_layer'):continue
            if self.relations>=max_relations:raise ValueError('retained_shield_search_relation_bound')
            self.relations+=1;layer=board.GetLayerID(shield['selected_layer'])
            polys=[]
            for zone in board.Zones():
                if zone.GetNetname()!='GND' or not zone.IsOnLayer(layer) or not zone.IsFilled():continue
                poly=zone.GetFilledPolysList(layer)
                if not poly.OutlineCount():continue
                polys.append(poly)
                self.clearance_mm=max(self.clearance_mm,
                    (zone.GetLocalClearance()+zone.GetMinThickness()/2)/1e6)
            segments=[]
            for uid in row['track_uuids']:
                t=live[uid];segments.append(dict(a=tuple(v/1e6 for v in t.GetStart()),
                    b=tuple(v/1e6 for v in t.GetEnd()),width_mm=t.GetWidth()/1e6))
            reach=max(1.,3.*max(t['width_mm'] for t in segments))
            import pcbnew
            for point in field._interaction_samples(*segments,reach,.5):
                if time.monotonic()>=deadline:raise ValueError('retained_shield_search_snapshot_deadline')
                at=pcbnew.VECTOR2I(*(round(v*1e6) for v in point))
                key=tuple(at)
                if key in seen or not any(poly.Contains(at) for poly in polys):continue
                if len(self.points)>=max_samples:raise ValueError('retained_shield_search_sample_bound')
                seen.add(key);self.points.append(tuple(v/1e6 for v in at))
        if self.points:
            from shapely.geometry import Point
            from shapely.strtree import STRtree
            self._tree=STRtree([Point(*point) for point in self.points])
        if time.monotonic()>=deadline:raise ValueError('retained_shield_search_snapshot_deadline')

    @property
    def active(self):return bool(self.points)

    def __call__(self,at,diameter_nm,clearance_nm):
        if (type(diameter_nm) is not int or diameter_nm<=0 or type(clearance_nm) is not int
                or clearance_nm<0 or not all(type(v) is int for v in at)):
            raise ValueError('invalid_retained_shield_barrel_query')
        self.calls+=1
        if not self._tree:return True
        from shapely.geometry import box
        x,y=(v/1e6 for v in at)
        radius=diameter_nm/2e6+max(self.clearance_mm,clearance_nm/1e6)+1e-8
        for i in self._tree.query(box(x-radius,y-radius,x+radius,y+radius)):
            if math.dist((x,y),self.points[int(i)])<=radius:
                self.refusals+=1;return False
        return True

    def report(self):
        return dict(schema=1,scope='retained_native_shield_sample_search_reservation_only',
            net=self.net,active=self.active,relations=self.relations,samples=len(self.points),
            source_interactions=self.source_interactions,max_source_interactions=self.max_interactions,
            board_hint=self.board_hint,
            tested_barrels=self.calls,conservative_refusals=self.refusals,
            board_mutated=False,shielding_qualified=False,release_authority=False,no_path_proof=False)


class PlanarSearchGuard:
    def __init__(self, board, net, *, netclass_resolver=None, max_segments=4096,board_hint=None,
                 conservative_cross_layer_proposals=False):
        if not isinstance(net, str) or not net or type(max_segments) is not int or not 1 <= max_segments <= 4096:
            raise ValueError('invalid_field_search_scope')
        if type(conservative_cross_layer_proposals) is not bool:
            raise ValueError('explicit_conservative_cross_layer_proposal_policy_required')
        self.conservative_cross_layer_proposals=conservative_cross_layer_proposals
        self.net = net
        resolve = netclass_resolver or (lambda _name: None)
        self.role = field.classify_net(net, netclass=resolve(net))
        self.rows = []
        self.calls = self.refusals = 0
        self.cross_layer_refusals = 0
        self.per_layer = {}
        self.unreferenced_peers = {}
        self._spatial = {}
        self._memo = OrderedDict()
        self.memo_hits = 0
        self.spatial_candidates = 0
        if not (self.role['aggressor'] or self.role['victim']):
            return
        from cec_native_field_roles import NativeFieldRoles
        native_roles=NativeFieldRoles(board,board_hint=board_hint or str(board.GetFileName() or ''),
            netclass_resolver=resolve)
        self.native_conductor_roles=native_roles.report()
        classifications = {}
        for item in board.GetTracks():
            if item.GetClass() != 'PCB_TRACK' or not item.GetNetname():
                continue
            name = str(item.GetNetname())
            if name == net or field._pair_mates(net, name):
                continue
            role = classifications.setdefault(name, field.classify_net(name, netclass=resolve(name)))
            role=native_roles.role(item,role)
            if not (self.role['aggressor'] and role['victim']
                    or self.role['victim'] and role['aggressor']):
                continue
            start, end = item.GetStart(), item.GetEnd()
            if start == end:
                continue
            if len(self.rows) >= max_segments:
                raise ValueError('field_search_snapshot_budget')
            row = dict(uuid=str(item.m_Uuid.AsString()), net=name, layer=int(item.GetLayer()),
                a=(start.x/1e6, start.y/1e6), b=(end.x/1e6, end.y/1e6), width_mm=item.GetWidth()/1e6)
            if not all(math.isfinite(v) for v in (*row['a'], *row['b'], row['width_mm'])) or row['width_mm'] <= 0:
                raise ValueError('invalid_native_field_search_segment')
            self.rows.append(row)
            self.per_layer.setdefault(row['layer'], []).append(row)
        profile = fab.active_profile_name(board)
        if profile:
            roles = dict(zip(fab.COPPER_LAYERS,fab.get_profile(profile)['roles']))
            enabled = tuple(int(l) for l in board.GetEnabledLayers().CuStack())
            physical = {name:index for index,name in enumerate(fab.COPPER_LAYERS)}
            for own in enabled:
                canonical = fab.COPPER_LAYER_IDS.get(own)
                if canonical not in physical: continue
                peers = []
                for other, rows in self.per_layer.items():
                    other_name = fab.COPPER_LAYER_IDS.get(other)
                    if own == other or other_name not in physical: continue
                    low,high = sorted((physical[canonical],physical[other_name]))
                    if any(roles[name] == 'GND' for name in fab.COPPER_LAYERS[low+1:high]):
                        if not conservative_cross_layer_proposals:
                            continue  # Potential shielding is NOT proven shielding.
                    peers.extend(rows)
                self.unreferenced_peers[own] = peers
        if conservative_cross_layer_proposals:
            # Optional proposal-only fallback after saved filled-plane holes
            # invalidate a nominally shielded route. Refuse risky relations
            # even across a declared GND role, instead of repeatedly emitting
            # the same failed crossing. This can over-constrain a search; it
            # neither changes field admission nor proves absence of a route.
            for own in board.GetEnabledLayers().CuStack():
                self.unreferenced_peers[int(own)]=[row for other,rows in self.per_layer.items()
                    if other!=int(own) for row in rows]

    @property
    def active(self):
        """No peer means no pruning or accumulated-run state is necessary."""
        return bool(self.rows)

    def multilayer_callback(self):
        """Preserve field-run memory only for a nonempty native relation set.

        A dummy always-true callback is not equivalent to ``None`` in the
        maze: the callback activates accumulated-run state. The complete
        immutable snapshot above proves when that state is unnecessary.
        Active callbacks still receive the full accumulated segment from
        the maze, not just individual hops; no field predicate is removed.
        Saved whole-route/refill admission remains mandatory in both cases.
        """
        if not self.active:return None
        import pcbnew
        def checked(start,end,width,layer):
            return self(pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),width,layer)
        return checked

    def _nearby(self, rows, start, end, width_mm):
        """Conservative broad phase; the unchanged field predicate decides.

        The source rows are immutable, plan-local scalar geometry. Expanded
        peer and query envelopes bound every distance that the legacy
        reach+half-width predicate can reject. This index grants no clearance
        or shielding pass and is never reused for a mutated source board.
        """
        if len(rows) <= 8:
            self.spatial_candidates += len(rows)
            return rows
        from shapely.geometry import box
        from shapely.strtree import STRtree
        key=id(rows)
        if key not in self._spatial:
            envelopes=[]
            for peer in rows:
                radius=max(1.,3.*peer['width_mm'])+.5*peer['width_mm']+1e-8
                a,b=peer['a'],peer['b']
                envelopes.append(box(min(a[0],b[0])-radius,min(a[1],b[1])-radius,
                    max(a[0],b[0])+radius,max(a[1],b[1])+radius))
            self._spatial[key]=STRtree(envelopes)
        radius=3.*width_mm+.5*width_mm+1e-8
        a,b=(start.x/1e6,start.y/1e6),(end.x/1e6,end.y/1e6)
        query=box(min(a[0],b[0])-radius,min(a[1],b[1])-radius,
            max(a[0],b[0])+radius,max(a[1],b[1])+radius)
        indices=sorted(map(int,self._spatial[key].query(query)))
        self.spatial_candidates += len(indices)
        return [rows[index] for index in indices]

    def __call__(self, start, end, width_nm, layer):
        self.calls += 1
        if (not isinstance(width_nm, int) or isinstance(width_nm, bool) or width_nm <= 0
                or not all(isinstance(v, int) for v in (*start, *end))):
            raise ValueError('invalid_field_search_leg')
        if tuple(start) == tuple(end):
            return True  # Barrel/point legality is owned by independent guards.
        key=(tuple(start),tuple(end),width_nm,int(layer))
        if key in self._memo:
            self.memo_hits += 1
            self._memo.move_to_end(key)
            return self._memo[key]
        result=self._check(start,end,width_nm,layer)
        self._memo[key]=result
        if len(self._memo)>16384:self._memo.popitem(last=False)
        return result

    def _check(self,start,end,width_nm,layer):
        row = dict(net=self.net, layer=int(layer), a=(start.x/1e6, start.y/1e6),
                   b=(end.x/1e6, end.y/1e6), width_mm=width_nm/1e6)
        for peer in self._nearby(self.per_layer.get(int(layer), ()),start,end,row['width_mm']):
            angle = field._acute_angle(row, peer)
            if angle > field.DEFAULT_PARALLEL_ANGLE_DEG + 1e-9:
                continue
            reach = max(1.0, 3.0*max(row['width_mm'], peer['width_mm']))
            gap = field._segment_distance(row, peer) - .5*(row['width_mm']+peer['width_mm'])
            if gap > reach + 1e-9:
                continue
            overlap = max(field._parallel_overlap(row, peer), field._parallel_overlap(peer, row))
            if overlap >= field.DEFAULT_MINIMUM_PARALLEL_MM - 1e-9:
                self.refusals += 1
                return False
        for peer in self._nearby(self.unreferenced_peers.get(int(layer), ()),start,end,row['width_mm']):
            angle = field._acute_angle(row, peer)
            reach = max(1.0, 3.0*max(row['width_mm'], peer['width_mm']))
            gap = field._segment_distance(row, peer) - .5*(row['width_mm']+peer['width_mm'])
            if gap > reach + 1e-9: continue
            overlap = (max(field._parallel_overlap(row,peer),field._parallel_overlap(peer,row))
                if angle <= field.DEFAULT_PARALLEL_ANGLE_DEG + 1e-9 else 0.)
            if (overlap >= field.DEFAULT_MINIMUM_PARALLEL_MM - 1e-9
                    or (gap <= 1e-9 and angle < field.DEFAULT_PERPENDICULAR_MIN_DEG - 1e-9)):
                self.cross_layer_refusals += 1
                return False
        return True  # Not a field PASS: complete-route/refill receiving remains mandatory.

    def report(self):
        return dict(schema=1, scope='unshieldable_planar_field_search_pruning_only', net=self.net,
            retained_relation_segments=len(self.rows), tested_legs=self.calls,
            conclusive_same_layer_refusals=self.refusals, board_mutated=False,
            conclusive_unreferenced_layer_refusals=0 if self.conservative_cross_layer_proposals else self.cross_layer_refusals,
            conservative_cross_layer_proposals=self.conservative_cross_layer_proposals,
            conservative_cross_layer_proposal_refusals=self.cross_layer_refusals if self.conservative_cross_layer_proposals else 0,
            active=self.active,memo_hits=self.memo_hits,
            spatial_candidate_checks=self.spatial_candidates,memo_entries=len(self._memo),
            native_conductor_field_roles=getattr(self,'native_conductor_roles',None),
            shielding_qualified=False, release_authority=False, no_path_proof=False)
