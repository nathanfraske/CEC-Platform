"""Bounded exact-guard octilinear roadmap; proposal only, never signoff.

The roadmap origin is the actual pad, while exact two-leg end hooks avoid
snapping the destination. Optional opposite-member copper biases search, not
admission. Native clearance and all final pair contracts remain mandatory.
"""
import heapq
import itertools
import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """Search budgets, never electrical/fabrication admission limits."""
    steps: tuple = (.4, .2)
    margin_mm: float = 4.
    max_visited: int = 3500
    query_seconds: float = 3.
    total_seconds: float = 22.
    anchors_per_member: int = 2
    coupling_weight: float = 3.
    selection_reserve_seconds: float = .1

    def __post_init__(self):
        for value in (*self.steps, self.query_seconds, self.total_seconds):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('roadmap steps and time budgets must be positive and finite')
        for value in (self.margin_mm, self.coupling_weight,
                      self.selection_reserve_seconds):
            if not math.isfinite(value) or value < 0:
                raise ValueError('roadmap margin and weight must be nonnegative and finite')
        if (not self.steps or isinstance(self.max_visited, bool)
                or not isinstance(self.max_visited, int) or self.max_visited < 1
                or isinstance(self.anchors_per_member, bool)
                or not isinstance(self.anchors_per_member, int)
                or self.anchors_per_member < 0):
            raise ValueError('invalid finite roadmap search limits')
        if (type(self.selection_reserve_seconds) not in (int,float)
                or not 0 <= self.selection_reserve_seconds <= 10.):
            raise ValueError('invalid finite roadmap selection reserve')


def _collinear(points):
    """Remove only same-direction collinear vertices; caller rechecks copper."""
    result = []
    for point in points:
        if result and math.dist(result[-1], point) < 1e-10:
            continue
        while len(result) >= 2:
            a, b = result[-2:]
            u, v = (b[0]-a[0], b[1]-a[1]), (point[0]-b[0], point[1]-b[1])
            if abs(u[0]*v[1]-u[1]*v[0]) > 1e-10 or u[0]*v[0]+u[1]*v[1] <= 0:
                break
            result.pop()
        result.append(tuple(point))
    return result


def _visibility_shortcuts(points, clear):
    """Shorten a proposal only across exact, legal octilinear sight lines.

    Keep endpoints and the original path on any failed chamfer recheck. This
    is not an obstacle simplification: the caller's native clearance and
    optional opposite-member spacing predicates receive every new segment.
    """
    import cec_precision_route as route
    original = _collinear(points)
    if len(original) > 256:
        return original
    result = [original[0]]
    index = 0
    while index < len(original)-1:
        selected = index+1
        for peer in range(len(original)-1, index+1, -1):
            a, b = original[index], original[peer]
            if route._segment_is_octilinear(a,b) and clear(a,b):
                candidate = result+[b]+original[peer+1:]
                if not route._polyline_has_reverse_bend(candidate):
                    selected = peer
                    break
        result.append(original[selected])
        index = selected
    candidate = _collinear(route._chamfer_axis_path(result))
    if (route._polyline_is_octilinear(candidate)
            and not route._polyline_has_reverse_bend(candidate)
            and not route._polyline_has_self_crossing(candidate)
            and all(clear(a,b) for a,b in zip(candidate,candidate[1:]))):
        return candidate
    return original


def search(start, end, clear, *, step=.25, margin=4., max_visited=3000,
           deadline=None, anchor=(), width=.25, gap=.25, coupling_weight=0.,
           minimum_spacing=None):
    import cec_precision_route as route
    if (not all(math.isfinite(v) for v in (step, margin, width, gap, coupling_weight))
            or step <= 0 or margin < 0 or width <= 0 or gap < 0 or coupling_weight < 0
            or isinstance(max_visited, bool) or not isinstance(max_visited, int)
            or max_visited <= 0
            or (deadline is not None and not math.isfinite(deadline))
            or (minimum_spacing is not None and
                (not math.isfinite(minimum_spacing) or minimum_spacing < width))
            or not all(len(p) == 2 and all(math.isfinite(v) for v in p)
                       for p in (start, end, *anchor))):
        raise ValueError('invalid bounded roadmap domain')
    start, end = tuple(start), tuple(end)
    directions = ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
    bounds = (min(start[0],end[0])-margin, min(start[1],end[1])-margin,
              max(start[0],end[0])+margin, max(start[1],end[1])+margin)
    anchor = list(zip(anchor, anchor[1:]))
    pitch = width + gap if minimum_spacing is None else minimum_spacing
    maximum_distance = width + 2.5*gap + .15
    serial = itertools.count()
    source = (0,0,-1)
    costs = {source: 0.}
    parents = {}
    queue = [(math.dist(start,end),0.,next(serial),source)]
    cache = {}
    visited = 0
    expired = False

    def point(state):
        return (start[0]+state[0]*step, start[1]+state[1]*step)

    def legal(a,b):
        key = (a,b)
        if key not in cache:
            cache[key] = bool(clear(a,b)) and all(
                route._seg_seg_dist(a,b,c,d) >= pitch-1e-6 for c,d in anchor)
        return cache[key]

    def penalty(a,b):
        length = math.dist(a,b)
        if not anchor or coupling_weight == 0:
            return length
        mid = ((a[0]+b[0])/2,(a[1]+b[1])/2)
        near = min(route._seg_seg_dist(mid,mid,c,d) for c,d in anchor)
        return length*(1.+(coupling_weight if near>maximum_distance else 0.))

    def heading(a,b):
        if math.dist(a,b)<1e-9:return None
        return max(range(8),key=lambda k: ((b[0]-a[0])*directions[k][0]
                    +(b[1]-a[1])*directions[k][1])/math.hypot(*directions[k]))

    def turns_ok(previous, points):
        for a,b in zip(points,points[1:]):
            current = heading(a,b)
            if current is None:continue
            if previous != -1 and min((current-previous)%8,(previous-current)%8)>2:
                return False
            previous = current
        return True

    def end_hooks(a):
        dx,dy = end[0]-a[0],end[1]-a[1]
        diagonal = min(abs(dx),abs(dy))
        ox,oy = math.copysign(diagonal,dx),math.copysign(diagonal,dy)
        for bend in ((a[0]+ox,a[1]+oy),(end[0]-ox,end[1]-oy)):
            points=[a]
            for p in (bend,end):
                if math.dist(points[-1],p)>1e-8:points.append(p)
            yield points

    def restore(state):
        points=[]
        while True:
            points.append(point(state))
            if state==source:break
            state=parents[state]
        points.reverse()
        return points

    best = None
    while queue and visited < max_visited:
        if deadline is not None and time.monotonic() >= deadline:
            expired=True;break
        estimate,cost,_,state=heapq.heappop(queue)
        if cost>costs[state]+1e-9:continue
        if best is not None and estimate>=best[0]-1e-9:break
        visited+=1
        a=point(state)
        if math.dist(a,end)<=2.5*step:
            for hook in end_hooks(a):
                if not turns_ok(state[2],hook):continue
                if not all(legal(c,d) for c,d in zip(hook,hook[1:])):continue
                candidate=restore(state)+hook[1:]
                candidate=_collinear(route._chamfer_axis_path(candidate))
                if (not route._polyline_is_octilinear(candidate)
                        or route._polyline_has_reverse_bend(candidate)
                        or not all(legal(c,d) for c,d in zip(candidate,candidate[1:]))):continue
                candidate=_visibility_shortcuts(candidate,legal)
                value=sum(penalty(c,d) for c,d in zip(candidate,candidate[1:]))
                if best is None or value<best[0]:best=(value,candidate)
        for h,(dx,dy) in enumerate(directions):
            if state[2]!=-1 and min((h-state[2])%8,(state[2]-h)%8)>2:continue
            nxt=(state[0]+dx,state[1]+dy,h)
            b=point(nxt)
            if not(bounds[0]<=b[0]<=bounds[2] and bounds[1]<=b[1]<=bounds[3]):continue
            next_cost=cost+penalty(a,b)
            if next_cost>=costs.get(nxt,math.inf)-1e-9:continue
            if not legal(a,b):continue
            costs[nxt]=next_cost;parents[nxt]=state
            heapq.heappush(queue,(next_cost+math.dist(b,end),next_cost,next(serial),nxt))
    return (best[1] if best else None), dict(visited=visited,queries=len(cache),
        deadline_exhausted=expired,visit_budget_exhausted=visited>=max_visited,
        finite_domain_only=True)


def complete_context(board, pair, endpoints):
    """Bind whole-pair heuristics only to fresh, complete physical endpoints.

    No virtual portal, partial flow leg, or pre-existing routed pair is inferred
    to be a complete obligation. Skipping here retains the historical solver.
    Final native qualification remains mandatory even for an applicable pair.
    """
    import cec_precision_route as route
    p_start, p_end, n_start, n_end = endpoints
    nets = {pair['p'], pair['n']}
    if any(item.GetNetname() in nets for item in board.GetTracks()):
        return None
    for net, first, last in ((pair['p'], p_start, p_end), (pair['n'], n_start, n_end)):
        pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetNetname() == net]
        if len(pads) < 2 or math.dist(first, last) < 1e-6:
            return None
        positions = [(pad.GetPosition().x/route.MM, pad.GetPosition().y/route.MM)
                     for pad in pads]
        if (not all(min(math.dist(point, first), math.dist(point, last)) <= 1e-5
                    for point in positions)
                or not all(any(math.dist(point, end) <= 1e-5 for point in positions)
                           for end in (first, last))):
            return None
    return dict(pair=dict(pair), endpoint_stations=route._pair_endpoint_stations(board, pair),
                detour_limit=2., minimum_detour_span_mm=2.,
                scope='fresh_complete_physical_pair')


def inline_context(board, pair, endpoints, *, minimum_coupled_fraction,
                   clearance_mm):
    """Recognize one real inline-bank leg, not a virtual portal or whole pair.

    Existing package ties are obstacles, not a reason to disable constructive
    search. The caller's local coverage floor applies only to this leg; the
    complete atomic transaction still owns final skew, coupling and topology.
    """
    import cec_precision_route as route
    flow = route._flow_through_pair_legs(board, pair)
    if flow is None:
        return None
    for variant in route._flow_bank_candidates(*flow):
        for leg in variant['legs']:
            reverse = (leg[1], leg[0], leg[3], leg[2])
            if any(all(math.dist(a,b) < 1e-6 for a,b in zip(endpoints, row))
                   for row in (leg, reverse)):
                return dict(pair=dict(pair), endpoint_stations=[],
                    detour_limit=2., minimum_detour_span_mm=2.,
                    scope='physical_inline_leg',
                    minimum_coupled_fraction=float(minimum_coupled_fraction),
                    clearance_mm=float(clearance_mm))
    return None


def terminal_context(board, pair, endpoints, *, layer, max_span_mm=12.):
    """Bind a local real-pad-to-virtual-throat obligation, never a whole bus.

    Only one exact physical P/N bank on the requested native copper face may
    own the search. The other bank is a compact nominal-pitch proposal. No
    signal barrel is synthesized here; transitions, whole-graph coupling,
    reference returns and saved-board admission remain the caller's duties.
    """
    import pcbnew
    import cec_precision_route as route
    import cec_fab_profile as fab
    if (type(max_span_mm) not in (int,float) or not math.isfinite(max_span_mm)
            or not 0 < max_span_mm <= 12.):
        raise ValueError('terminal roadmap span must be finite and within twelve millimetres')
    if (len(endpoints) != 4 or any(len(p) != 2 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in p)
            for p in endpoints)):
        return None
    if any(not callable(getattr(board,name,None)) for name in
           ('GetLayerID','GetEnabledLayers','GetFootprints','GetFileName')):
        return None
    lid = board.GetLayerID(layer)
    if (lid not in set(map(int,board.GetEnabledLayers().CuStack()))
            or fab.COPPER_LAYER_IDS.get(lid) not in fab.referenced_signal_layers(
                board,hint=board.GetFileName() or '')):
        return None
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    banks = ((endpoints[0],endpoints[2]),(endpoints[1],endpoints[3]))
    physical = []
    for bank in banks:
        witnesses = []
        for net,xy in zip((pair['p'],pair['n']),bank):
            matches = [p for p in pads if str(p.GetNetname()) == net
                       and tuple(p.GetPosition()) == tuple(route._v(*xy))]
            if len(matches) != 1:
                break
            p = matches[0]
            if (not p.IsOnLayer(lid) or p.GetAttribute() not in
                    (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)
                    or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and not p.HasHole()):
                break
            witnesses.append(p.m_Uuid.AsString())
        physical.append(witnesses if len(witnesses) == 2 else [])
    if sum(bool(bank) for bank in physical) != 1:
        return None
    real_index = 0 if physical[0] else 1
    throat = banks[1-real_index]
    # Neither virtual member may masquerade as an actual native terminal.
    if any(tuple(p.GetPosition()) == tuple(route._v(*xy))
           for xy in throat for p in pads):
        return None
    pitch = float(pair['width'])+float(pair['gap'])
    transition_vias = []
    if abs(math.dist(*throat)-pitch) > 1e-5:
        # A remote matched transition is a physical native endpoint, not an
        # arbitrary virtual lane split. Its lands require more pitch than
        # the nominal ribbon. Bind the wider search domain only to the two
        # exact authored, profile-legal through barrels; never create vias
        # here or waive the complete saved pair's coupling/return contract.
        try:
            profile = fab.get_profile(fab.board_profile_name(board))
            if not profile.get('pofv'):
                return None
            minimum_diameter,minimum_drill,_ = fab.precision_signal_via_geometry(board,.5,.25)
            clearance = route._pair_clearance(board,pair,None)
            for net,xy in zip((pair['p'],pair['n']),throat):
                matches = [v for v in board.GetTracks()
                    if v.GetClass() == 'PCB_VIA' and str(v.GetNetname()) == net
                    and tuple(v.GetPosition()) == tuple(route._v(*xy))]
                if len(matches) != 1:
                    return None
                via = matches[0]
                diameter,drill = via.GetWidth(lid)/route.MM,via.GetDrill()/route.MM
                if (via.GetViaType() != pcbnew.VIATYPE_THROUGH
                        or not via.IsOnLayer(lid)
                        or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                        or abs(diameter-minimum_diameter) > 1e-6
                        or abs(drill-minimum_drill) > 1e-6
                        or drill <= 0 or drill >= diameter):
                    return None
                transition_vias.append(via.m_Uuid.AsString())
            transition_pitch = max(pitch,minimum_diameter+clearance+.05)
            if (len(set(transition_vias)) != 2
                    or abs(math.dist(*throat)-transition_pitch) > 1e-5):
                return None
        except (AttributeError,KeyError,TypeError,ValueError):
            return None
    if (not route._segment_is_octilinear(*throat)
            or any(not 1e-6 < math.dist(a,b) <= max_span_mm
                   for a,b in zip(*banks))):
        return None
    return dict(pair=dict(pair),endpoint_stations=[],detour_limit=2.,
                minimum_detour_span_mm=2.,scope='native_terminal_fanin',
                native_pad_uuids=physical[real_index],layer=layer,
                native_transition_via_uuids=transition_vias,
                target_pitch_mm=math.dist(*throat),
                minimum_coupled_fraction=0.,whole_pair_qualification_required=True,
                new_signal_vias_authorized=False,release_authority=False)


def _contract(p, n, context, options):
    import cec_precision_route as route
    length = lambda path: sum(math.dist(a,b) for a,b in zip(path,path[1:]))
    pl, nl = length(p), length(n)
    detour = all(span < context['minimum_detour_span_mm'] or
                 value/span <= context['detour_limit']+1e-9
                 for value, span in ((pl, options['p_span']), (nl, options['n_span'])))
    skew = abs(options['existing_signed_skew_mm']+pl-nl)
    skew_ok = options['max_skew'] is None or skew <= options['max_skew']+1e-9
    pair = context['pair']
    coverage = route._polyline_coupling_coverage(p,n,options['width'],options['gap'])
    if context['scope'] in ('physical_inline_leg','native_terminal_fanin'):
        coupling = dict(coverage, ok=coverage['fraction']+1e-9 >=
                        context['minimum_coupled_fraction'])
    else:
        coupling = route._pair_coupling_contract(pair, coverage,
            {pair['p']:pl,pair['n']:nl},endpoint_stations=context['endpoint_stations'])
    return dict(ok=bool(detour and skew_ok and coupling['ok']),
                detour_ok=detour, skew_ok=skew_ok, coupling=coupling)


def refine(p_paths, n_paths, selected, *, endpoints, p_clear, n_clear,
           options, context, minimum_end_heading_alignment=-1.,
           limits=None, deadline=None):
    """Add exact-guard proposals only after a complete local contract fails.

    Retain the original result on failure. Final saved-board admission is never
    substituted. The caller supplies an immutable solve's native predicates;
    caches are query-local and never survive a geometry mutation.
    """
    import cec_precision_route as route
    evidence = dict(applicable=context is not None, attempted=False, selected=False,
                    finite_domain_only=True, queries=[], selection_attempts=[],
                    selection_policy='contract-first-anytime')
    if context is None:
        return selected, evidence
    if selected is not None:
        initial = _contract(*selected, context, options)
        evidence['incumbent_contract'] = initial
        if initial['ok']:
            evidence['reason'] = 'incumbent_satisfies_complete_local_contract'
            return selected, evidence
    limits = limits or (Limits(steps=(.2,.1),max_visited=30000,
        query_seconds=6.,total_seconds=24.)
        if context['scope'] in ('physical_inline_leg','native_terminal_fanin') else Limits())
    evidence['scope'] = context['scope']
    local_deadline = min(deadline if deadline is not None else math.inf,
                         time.monotonic()+limits.total_seconds)
    if time.monotonic() >= local_deadline:
        evidence['reason'] = 'deadline_exhausted'
        return selected, evidence
    evidence['attempted'] = True
    domains = [list(p_paths), list(n_paths)]
    seen = [{tuple(map(tuple,path)) for path in paths} for paths in domains]
    evidence['original_domain_sizes'] = list(map(len, domains))
    # No persistent cache: a board mutation changes the native guard domain.
    query_keys = set()
    length = lambda path: sum(math.dist(a,b) for a,b in zip(path,path[1:]))

    def add(member, step, anchor=()):
        if time.monotonic() >= local_deadline:
            return
        key = (member, step, tuple(map(tuple, anchor)))
        if key in query_keys:
            return
        query_keys.add(key)
        start, end = (endpoints[0],endpoints[2]) if member == 0 else (endpoints[1],endpoints[3])
        clear = p_clear if member == 0 else n_clear
        spacing = options['width'] + options['gap']
        if (context['scope'] == 'physical_inline_leg'
                and not options['strict_pair_gap']):
            # Match the existing terminal-taper search domain, with the
            # physical clearance floor as well. Nominal gap and coupling
            # scoring remain unchanged; this is never trunk-gap permission.
            spacing = options['width'] + max(options['gap']/2., context['clearance_mm'])
        query_started = time.monotonic()
        remaining = max(0., local_deadline-query_started)
        # Refinement is optional; checking the paths already generated is not.
        # Keep a small bounded part of this SAME absolute lease for exact joint
        # admission. Never replenish the parent or treat an expired query as
        # a completed negative.
        reserve = min(limits.selection_reserve_seconds, .1*remaining)
        query_deadline = min(local_deadline-reserve,
                             query_started+limits.query_seconds)
        path, report = search(start,end,clear,step=step,margin=limits.margin_mm,
            max_visited=limits.max_visited,
            deadline=query_deadline,
            anchor=anchor,width=options['width'],gap=options['gap'],
            minimum_spacing=spacing,
            coupling_weight=limits.coupling_weight if anchor else 0.)
        report.update(member=member,step_mm=step,anchored=bool(anchor),found=path is not None,
            wall_seconds=round(time.monotonic()-query_started,6),
            granted_seconds=max(0.,query_deadline-query_started),
            selection_reserve_seconds=reserve)
        evidence['queries'].append(report)
        if (path is None or route._path_end_heading_alignment(
                path,options['preferred_end_direction'])+1e-9 < minimum_end_heading_alignment):
            return
        key = tuple(map(tuple,path))
        if key not in seen[member]:
            seen[member].add(key);domains[member].append(path)

    last_selected_domain = None

    def select(stage):
        nonlocal last_selected_domain
        sizes = tuple(map(len, domains))
        if (not all(sizes) or sizes == last_selected_domain
                or time.monotonic() >= local_deadline):
            return None
        last_selected_domain = sizes
        diagnostics = {}
        started = time.monotonic()
        candidate = route._ranked_joint_escape(*domains,**dict(options,
            deadline=local_deadline,diagnostics=diagnostics,
            pair_admission=lambda p,n: _contract(p,n,context,options)['ok']))
        evidence['selection_attempts'].append(dict(stage=stage,domain_sizes=list(sizes),
            wall_seconds=round(time.monotonic()-started,6),diagnostics=diagnostics))
        evidence.update(expanded_domain_sizes=list(sizes),selection=diagnostics)
        if candidate is not None:
            evidence.update(selected=True,selected_stage=stage,
                selected_contract=_contract(*candidate,context,options))
        return candidate

    # Do not generate every coarse/fine/anchored hypothesis before examining
    # any complete pair. A later optional query can consume the entire lease
    # even when an earlier bounded domain already contained a legal pair.
    # The exact ranked selector and local electrical contract are unchanged;
    # the first fully admitted domain wins, not an unverified member path.
    candidate = select('initial-domain')
    if candidate is not None:
        return candidate, evidence
    for step in limits.steps:
        for member in (0,1):
            add(member,step)
            candidate = select('unanchored-member')
            if candidate is not None:
                return candidate, evidence
    for member in (0,1):
        for anchor in sorted(domains[1-member],key=lambda path:(length(path),tuple(map(tuple,path))))[:limits.anchors_per_member]:
            add(member,limits.steps[-1],anchor)
            candidate = select('anchored-member')
            if candidate is not None:
                return candidate, evidence
    exhausted = time.monotonic() >= local_deadline
    evidence.update(expanded_domain_sizes=list(map(len,domains)),
        deadline_exhausted=exhausted, search_inconclusive=exhausted,
        reason=('deadline_exhausted' if exhausted else
                'bounded_domain_has_no_admitted_alternative'))
    return selected, evidence
