"""Native plated-terminal return cells, using GND-owned via requirements.

A signal land's antipad is not a plane split along the remote trace. It is a
bounded transition cell only when a nearby plated GND return actually contacts
the filled reference plane. No net name, footprint family or board exception.
"""
import math
import hashlib
from pathlib import Path
import re
import time
import pcbnew

MM = 1_000_000


def _rule_floors(board_path):
    """Conservative finite DRU minima; conditions never grant an exception.

    Taking the maximum across conditions may refuse an otherwise legal site,
    but cannot undercut a relevant rule. Expressions/unknown numeric units in
    these dimensional minima are unsupported, never interpreted as zero.
    """
    from cec_copper_echo import _parse
    path = Path(board_path).with_suffix('.kicad_dru')
    keys = {'via_diameter':'via_diameter','hole_size':'via_drill',
            'annular_width':'annular','clearance':'clearance',
            'physical_clearance':'clearance','hole_to_hole':'hole_to_hole',
            'hole_clearance':'hole_clearance','edge_clearance':'edge_clearance'}
    floors = {key:0.0 for key in keys.values()}
    if not path.exists():
        return floors,dict(present=False,sha256=None,method='all_numeric_minima_conservative')
    payload = path.read_bytes()
    if len(payload) > 262144:
        raise ValueError('return_rule_authority_budget_exhausted')
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|#[^\r\n]*|[()]|[^\s()#]+',payload.decode('utf-8'))
    rows = _parse(['(', 'rules', *[t for t in tokens if not t.startswith('#')], ')'])
    pending, count = [rows],0
    while pending:
        row = pending.pop();count += 1
        if count > 4096:
            raise ValueError('return_rule_authority_budget_exhausted')
        if len(row) > 1 and row[0] == 'constraint' and row[1] in keys:
            for value in row[2:]:
                if not isinstance(value,list) or not value or value[0] != 'min':
                    continue
                match = re.fullmatch(r'(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?(mm|mil|in)',
                                     value[1]) if len(value) == 2 and isinstance(value[1],str) else None
                if not match:
                    raise ValueError('unsupported_return_dimensional_rule_minimum')
                number = float(value[1][:-len(match[3])]) * {'mm':1.0,'mil':.0254,'in':25.4}[match[3]]
                if not math.isfinite(number) or number < 0:
                    raise ValueError('invalid_return_dimensional_rule_minimum')
                floors[keys[row[1]]] = max(floors[keys[row[1]]],number)
        pending.extend(value for value in row if isinstance(value,list))
    return floors,dict(present=True,sha256=hashlib.sha256(payload).hexdigest(),
                       method='all_numeric_minima_conservative')


def ground_return_contract(board):
    """Resolve GND itself, not the unrelated signal pair or a compact waiver."""
    import cec_route_dimensions as dimensions
    import cec_fab_profile as fab
    import cec_fab_check as fabrication
    path = Path(board.GetFileName() or '')
    if not board.GetFileName() or not path.is_file() or board.FindNet('GND') is None:
        raise ValueError('saved_ground_return_authority_required')
    project = dimensions.project_path(path)
    if project is None or project.resolve() != path.with_suffix('.kicad_pro').resolve():
        raise ValueError('exact_ground_return_project_authority_required')
    table = dimensions.NetclassTable.from_board_path(path)
    spec = table.resolve('GND')
    if not table.classes or spec['name'] not in table.classes:
        raise ValueError('effective_ground_netclass_authority_required')
    profile_name = fab.board_profile_name(board)
    profile = fab.get_profile(profile_name) if profile_name else None
    if not profile or profile['vendor'] not in fabrication.PROFILES:
        raise ValueError('declared_ground_return_fabrication_profile_required')
    fab_rules = fabrication.profile_rules(fabrication.PROFILES[profile['vendor']],
        max(fab.stackup_oz(profile_name).values()),process_profile=profile)
    board_limits = dimensions.board_limits(board)
    rule_floors, rule_identity = _rule_floors(path)
    limits = dict(via_diameter=max(board_limits['via_diameter'],fab_rules['via'],rule_floors['via_diameter']),
        via_drill=max(board_limits['via_drill'],fab_rules['drill'],rule_floors['via_drill']),
        annular=max(board_limits['annular'],fab_rules['annular'],rule_floors['annular']))
    diameter,drill = dimensions.ordinary_via_geometry(spec,limits)
    settings = board.GetDesignSettings()
    spacing = dict(hole_to_hole=max(float(settings.m_HoleToHoleMin)/MM,
                       fab_rules['h2h'],rule_floors['hole_to_hole']),
        hole_clearance=max(float(settings.m_HoleClearance)/MM,
                           fab_rules['hole_clearance'],rule_floors['hole_clearance']),
        edge_clearance=max(float(settings.m_CopperEdgeClearance)/MM,
                           fab_rules['edge'],rule_floors['edge_clearance']))
    clearances = [float(board.GetDesignSettings().m_MinClearance)/MM,
                  float(spec.get('clearance') or 0),fab_rules['clearance'],rule_floors['clearance'],
                  max(0.0,spacing['hole_clearance']-(diameter-drill)/2)]
    # The central geometric guard takes one clearance. A conservative maximum
    # of actual participating classes also protects higher-clearance foreign
    # copper; an unused class cannot silently become the GND class itself.
    for info in board.GetNetInfo().NetsByNetcode().values():
        if info.GetNetname():
            other = table.resolve(info.GetNetname())
            if other['name'] not in table.classes:
                raise ValueError('participating_netclass_clearance_authority_required')
            clearances.append(float(other.get('clearance') or 0))
    if any(not math.isfinite(value) or value < 0 for value in [*clearances,*spacing.values()]):
        raise ValueError('invalid_ground_return_clearance')
    return dict(schema=1,net='GND',netclass=spec['name'],class_spec=spec,
        project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),rules=rule_identity,
        board_limits_mm=board_limits,fabrication_profile=profile_name,
        fabrication_minima_mm={key:fab_rules[key] for key in
                              ('via','drill','annular','clearance','h2h','hole_clearance','edge')},
        conservative_rule_minima_mm=rule_floors,
        diameter_nm=math.ceil(diameter*MM),drill_nm=math.ceil(drill*MM),
        annular_min_nm=math.ceil(limits['annular']*MM),clearance_nm=math.ceil(max(clearances)*MM),
        spacing_nm={key:math.ceil(value*MM) for key,value in spacing.items()},
        scope='ordinary_ground_owned_return_no_local_geometry_exception')


def ground_site_guard(board, at, diameter_nm, drill_nm, contract, *,
                      existing_via_uuid=None, deadline=None):
    """Additional native hole/material guards for ordinary new GND seats.

    The central all-layer copper/process guard is still mandatory. Native
    holes are queried directly, including slot shape and non-copper NPTHs;
    same-net ownership never waives a fabrication spacing floor. No mutable
    settings are changed to smuggle caller-specific minima into that guard.
    """
    import cec_fr
    if deadline is not None and time.monotonic() >= deadline:
        return dict(ok=False,reason='ground_site_deadline_exhausted')
    try:
        if min(int(diameter_nm),int(drill_nm)) <= 0 or diameter_nm < drill_nm:
            return dict(ok=False,reason='invalid_ground_site_geometry')
        spacing = contract['spacing_nm']
        edge = max(500000,int(spacing['edge_clearance'])) # retain constructor floor
        bounds = board.GetBoardEdgesBoundingBox()
        if bounds.GetWidth() <= 0 or bounds.GetHeight() <= 0:
            return dict(ok=False,reason='ground_site_native_outline_required')
        if not cec_fr._edge_leg_clear(board,at,at,math.ceil(diameter_nm/2),edge_mm=edge/MM):
            return dict(ok=False,reason='ground_site_native_edge_refused')
        holes = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA']
        holes.extend(p for fp in board.GetFootprints() for p in fp.Pads() if p.HasHole())
        if len(holes) > 8192:
            return dict(ok=False,reason='ground_site_hole_inventory_budget_exhausted')
        own_seen = existing_via_uuid is None
        checked = 0
        for item in holes:
            if deadline is not None and time.monotonic() >= deadline:
                return dict(ok=False,reason='ground_site_deadline_exhausted')
            uid = item.m_Uuid.AsString()
            if uid == existing_via_uuid:
                if (item.GetClass() != 'PCB_VIA' or item.GetNetname() != 'GND'
                        or item.GetPosition() != at or item.GetDrillValue() != drill_nm
                        or item.GetWidth(item.TopLayer()) != diameter_nm):
                    return dict(ok=False,reason='ground_site_existing_identity_changed')
                own_seen = True
                continue
            if item.GetClass() == 'PCB_VIA':
                hole = pcbnew.SHAPE_CIRCLE(item.GetPosition(),math.ceil(item.GetDrillValue()/2))
                if item.GetDrillValue() <= 0:
                    return dict(ok=False,reason='ground_site_native_hole_unavailable')
            else:
                hole = item.GetEffectiveHoleShape()
            checked += 1
            if hole is None:
                return dict(ok=False,reason='ground_site_native_hole_unavailable')
            # Either physical land-to-hole or drill-to-drill separation can
            # dominate. Point-radius overload avoids asymmetric shape dispatch.
            margin = max(math.ceil(drill_nm/2)+int(spacing['hole_to_hole']),
                         math.ceil(diameter_nm/2)+int(spacing['hole_clearance']))
            if pcbnew.SHAPE.Collide(hole,at,margin):
                return dict(ok=False,reason='ground_site_native_hole_spacing_refused',
                            blocking_uuid=uid)
        if not own_seen:
            return dict(ok=False,reason='ground_site_existing_identity_missing')
        return dict(ok=True,checked_holes=checked,spacing_nm=spacing,
                    edge_clearance_nm=edge,method='native_hole_shape_and_board_material')
    except Exception as exc:
        return dict(ok=False,reason='ground_site_native_geometry_unavailable',error=str(exc))


def ground_barrels(board):
    result = [item for item in board.GetTracks()
              if item.GetClass() == 'PCB_VIA' and item.GetNetname() == 'GND'
              and item.GetViaType() == pcbnew.VIATYPE_THROUGH]
    result.extend(pad for footprint in board.GetFootprints() for pad in footprint.Pads()
                  if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                  and pad.GetNetname() == 'GND')
    return result


def reference_cells(board, net, signal_layer, reference_layer, polygons, *, reach_mm=1.5):
    """Exact land shapes with independently witnessed local plane returns."""
    if not math.isfinite(reach_mm) or reach_mm <= 0:
        raise ValueError('return reach must be finite and positive')
    if not polygons:
        return []
    returns = []
    for item in ground_barrels(board):
        if not (item.IsOnLayer(signal_layer) and item.IsOnLayer(reference_layer)):
            continue
        try:
            if any(poly.Collide(item.GetEffectiveShape(reference_layer), 0)
                   for poly in polygons):
                returns.append(item)
        except Exception:
            # Missing native contact evidence cannot create an exemption.
            continue
    cells = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or pad.GetNetname() != net
                    or not pad.IsOnLayer(signal_layer) or not pad.IsOnLayer(reference_layer)):
                continue
            at = pad.GetPosition()
            witnesses = []
            for item in returns:
                other = item.GetPosition()
                distance = math.hypot(at.x-other.x, at.y-other.y)/MM
                if distance <= reach_mm + 1e-9:
                    witnesses.append(dict(uuid=item.m_Uuid.AsString(), distance_mm=distance))
            if witnesses:
                cells.append(dict(shape=pad.GetEffectiveShape(reference_layer),
                    pad_uuid=pad.m_Uuid.AsString(), reference_layer=int(reference_layer),
                    returns=witnesses))
    return cells


def contains_sample(point, cells, *, clearance_mm, sample_mm):
    """Bound the exclusion to native own-net land + clearance + half sample."""
    if not all(math.isfinite(v) for v in (clearance_mm, sample_mm)) \
            or clearance_mm < 0 or sample_mm <= 0:
        raise ValueError('invalid native transition sample geometry')
    shape = pcbnew.SHAPE_SEGMENT(point, point, 0)
    margin = int(round((clearance_mm + sample_mm/2.0)*MM))
    return any(cell['shape'].Collide(shape, margin) for cell in cells)


def synthesize(board, pair, *, return_reach_mm=1.5, deadline=None):
    """Add exact-clearance returns for this pair's native plated terminals.

    Final refill/contact and unchanged DRC/connectivity admission remain
    mandatory. This function never declares a board or pair fabrication-ready.
    """
    import cec_precision_route as precision
    if precision._deadline_expired(deadline):
        return dict(ok=False,applicable=True,added_count=0,terminals=[],
                    reason='ground_return_deadline_exhausted')
    nets = {pair['p'], pair['n']}
    pads = [pad for footprint in board.GetFootprints() for pad in footprint.Pads()
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pad.GetNetname() in nets]
    if not pads:
        return dict(ok=True, applicable=False, added_count=0, terminals=[])
    try:
        dimensions = ground_return_contract(board)
    except Exception as exc:
        return dict(ok=False,applicable=True,added_count=0,terminals=[],
            reason='ground_return_contract_unavailable',error=str(exc))
    diameter,drill = dimensions['diameter_nm']/MM,dimensions['drill_nm']/MM
    clearance = precision._pair_clearance(board,pair,dimensions['clearance_nm']/MM)
    # A nearby return in an antipad pocket can be clearance-clean but have no
    # plane contact after island pruning. Compile one disposable native fill
    # for this complete-pair transaction; never add prospective planes to the
    # caller or accept proximity alone when a profile declares references.
    from cec_return_plane_preview import compile_contact_filter
    try:
        reference_contact, reference_preview = compile_contact_filter(board)
    except Exception as exc:
        return dict(ok=False,applicable=True,added_count=0,terminals=[],
            reason='native_reference_preview_refused',error=str(exc))
    site_refusals = {}
    def guarded_reference_contact(point, candidate_diameter):
        at = pcbnew.VECTOR2I(round(point[0]*MM),round(point[1]*MM))
        candidate_nm = round(candidate_diameter*MM)
        # The shared constructor also asks whether an existing barrel can be
        # reused. Exempt only that exact native identity from its own hole.
        existing = [item for item in board.GetTracks() if item.GetClass() == 'PCB_VIA'
                    and item.GetNetname() == 'GND' and item.GetPosition() == at
                    and item.GetWidth(item.TopLayer()) == candidate_nm]
        if len(existing) > 1:
            site_refusals['ground_site_ambiguous_existing_identity'] = (
                site_refusals.get('ground_site_ambiguous_existing_identity',0)+1)
            return False
        report = ground_site_guard(board,at,candidate_nm,
            existing[0].GetDrillValue() if existing else dimensions['drill_nm'],dimensions,
            existing_via_uuid=existing[0].m_Uuid.AsString() if existing else None,deadline=deadline)
        if not report['ok']:
            site_refusals[report['reason']] = site_refusals.get(report['reason'],0)+1
            return False
        return reference_contact is None or reference_contact(point,candidate_diameter)
    original = {item.m_Uuid.AsString() for item in board.GetTracks()}
    rows = []
    for pad in sorted(pads, key=lambda p:(p.GetPosition().x,p.GetPosition().y,p.GetNumber())):
        if precision._deadline_expired(deadline):
            precision._rollback_created_tracks(board,original)
            return dict(ok=False,applicable=True,added_count=0,terminals=rows,
                reason='ground_return_deadline_exhausted',dimensions=dimensions)
        at = pad.GetPosition(); center = (at.x/MM, at.y/MM)
        # Reuse a plated ground terminal only after proving its plane contact
        # on every adjacent reference used by a connected trace layer.
        import cec_fab_profile
        profile_name = cec_fab_profile.active_profile_name(board, hint=board.GetFileName() or '')
        profile = cec_fab_profile.get_profile(profile_name) if profile_name else None
        refs = []
        if profile:
            layers = cec_fab_profile.COPPER_LAYERS
            roles = dict(zip(layers, profile['roles']))
            for i, signal in enumerate(layers):
                if 'SIG' not in roles.get(signal, ''): continue
                adjacent = [layers[j] for j in (i-1,i+1) if 0 <= j < len(layers)]
                ref = next((name for name in adjacent if roles.get(name) == 'GND'), None)
                if ref is None: continue
                lid, rid = board.GetLayerID(signal), board.GetLayerID(ref)
                polys = [z.GetFilledPolysList(rid) for z in board.Zones()
                         if z.GetNetname() == 'GND' and z.IsOnLayer(rid)]
                refs.append(any(cell['pad_uuid'] == pad.m_Uuid.AsString()
                    for cell in reference_cells(board, pad.GetNetname(), lid, rid, polys,
                                                reach_mm=return_reach_mm)))
        if refs and all(refs):
            rows.append(dict(pad_uuid=pad.m_Uuid.AsString(), status='existing_plated_return', added=[]))
            continue
        added, status = precision._add_pair_transition_returns(board, center, (1.,0.),
            signal_points=(center,), width=float(pair['width']), gap=float(pair['gap']),
            clearance=clearance, via_diameter_mm=diameter, via_drill_mm=drill,
            return_reach_mm=return_reach_mm,reference_contact=guarded_reference_contact,deadline=deadline)
        rows.append(dict(pad_uuid=pad.m_Uuid.AsString(), status=status,
                         added=[item.m_Uuid.AsString() for item in added]))
        if status not in ('added', 'covered'):
            precision._rollback_created_tracks(board, original)
            return dict(ok=False, applicable=True, added_count=0, terminals=rows,
                        reason='native_plated_terminal_return_refused', dimensions=dimensions,
                        site_guard_refusals=site_refusals)
    return dict(ok=True, applicable=True, terminals=rows, dimensions=dimensions,
                reference_preview=reference_preview,
                site_guard_refusals=site_refusals,
                added_count=sum(len(row['added']) for row in rows))
