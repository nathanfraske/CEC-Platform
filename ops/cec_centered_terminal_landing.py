"""Source-measured centered 0/45 power-terminal frames in existing keepers.

No barrel, track, pad, field, process, original fill record or Ground sheet is
changed. A finite native addition must actually break up an exposed curved
perimeter, not merely enclose a via in an authored polygon. No capacity credit.
"""
import json
import math
from pathlib import Path
import tempfile
import time
import pcbnew
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
import cec_additive_route_receiving as additive
import cec_assembly_envelope as assembly
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as authority
import cec_native_contour_regions as signed
import cec_native_pocket_preflight as material
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_rounded_landing as landing
import cec_zone_fill

POLICY = 'source-measured-centered-native-terminal-frame-v1'
def require(ok, message):
    if not ok: raise ValueError(message)
def plain(value): return json.loads(json.dumps(value, allow_nan=False))


def centered_cover(board, via, face, width_nm):
    require(type(width_nm) is int and 500000 <= width_nm <= 10000000,
        'bounded_actual_terminal_material_width_required')
    center = list(via.GetPosition())
    proto = pcbnew.PCB_TRACK(board); proto.SetLayer(face); proto.SetWidth(width_nm)
    proto.SetStart(via.GetPosition()); proto.SetEnd(via.GetPosition())
    raw = native._native_capsule(proto); ring = raw.Outline(0)
    pts = [[ring.CPoint(i).x-center[0], ring.CPoint(i).y-center[1]] for i in range(ring.PointCount())]
    half = max(abs(v) for p in pts for v in p)+1000
    diagonal = max(max(abs(x+y), abs(x-y)) for x,y in pts)+2000
    cut = diagonal-half; require(0 < cut < half, 'proper_measured_terminal_chamfer_required')
    offsets = [(-cut,-half),(cut,-half),(half,-cut),(half,cut),(cut,half),(-cut,half),(-half,cut),(-half,-cut)]
    points = [[center[0]+x, center[1]+y] for x,y in offsets]
    missing = raw.CloneDropTriangulation(); missing.BooleanSubtract(native._poly(points))
    require(not missing.OutlineCount(), 'centered_frame_loses_actual_native_terminal_disk')
    return points


def _local_shape(board, row, deadline):
    face = row['source_configuration']['layers'][0]
    shape = material.source_material(board, row['source_configuration']['net'], face, deadline)
    shape.BooleanIntersection(native._poly(row['observation_window_nm']))
    return assembly.polygon_from_native(shape)


def curve_runs(shape, feature_nm=100000):
    """Aesthetic observation only: no width, clearance or material tolerance."""
    if shape.is_empty: return dict(longest_mm=0., noncanonical_edges=0, canonical_edges=0)
    polygons = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
    longest = 0.; curved = straight = 0; longest_raw = (0.,None); long_lines = []
    for polygon in polygons:
        # The assembly converter returns millimetres; classification is on
        # exact native nanometre coordinates, not rounded whole millimetres.
        points = [[round(x*1e6),round(y*1e6)] for x,y in list(polygon.exterior.coords)[:-1]]
        edges = []
        for a,z in zip(points, points[1:]+points[:1]):
            canonical = material.fill_edge_direction(a,z) != 'noncanonical'
            length = math.dist(a,z)
            # A long straight fill edge is not a curved perimeter run. Keep
            # its raw noncanonical heading explicit rather than silently
            # relaxing a heading rule to score native fill quantization.
            if not canonical and length > feature_nm:
                long_lines.append(dict(start_nm=a,end_nm=z,dx_nm=z[0]-a[0],dy_nm=z[1]-a[1]))
            edges.append((canonical or length > feature_nm, length))
            straight += canonical; curved += not canonical
            if not canonical and math.dist(a,z) > longest_raw[0]:
                longest_raw = (math.dist(a,z), dict(start_nm=a,end_nm=z,dx_nm=z[0]-a[0],dy_nm=z[1]-a[1]))
        if not edges: continue
        if all(not a for a,_ in edges): longest = max(longest, sum(b for _,b in edges)); continue
        pivot = next(i for i,(a,_) in enumerate(edges) if a)
        run = 0.
        for canonical, length in edges[pivot:]+edges[:pivot]:
            if canonical: longest = max(longest,run); run = 0.
            else: run += length
        longest = max(longest,run)
    return dict(longest_mm=longest/1e6, noncanonical_edges=curved, canonical_edges=straight,
        longest_noncanonical_edge=longest_raw[1],raw_long_noncanonical_fill_edges_disclosed=long_lines,
        track_centerline_angle_tolerance_nm=0,geometry_snapped_or_edited_for_observation=False)


def record(source, *, board_hint, via_uuid, layer_id, allow_locked_source=False):
    source = Path(source).resolve(); board = pcbnew.LoadBoard(str(source)); deadline = time.monotonic()+10.
    require(type(layer_id) is int and type(via_uuid) is str and type(allow_locked_source) is bool,
        'explicit_source_terminal_face_and_ownership_required')
    vias = [v for v in board.GetTracks() if force._uid(v) == via_uuid and v.GetClass() == 'PCB_VIA']
    require(len(vias) == 1, 'one_real_terminal_barrel_required'); via = vias[0]; net = via.GetNetname()
    require(via.GetViaType() == pcbnew.VIATYPE_THROUGH and via.IsOnLayer(layer_id) and net
        and net.rsplit('/',1)[-1].upper() not in ('GND','AGND','PGND','DGND'), 'known_non_ground_through_terminal_required')
    profile = fab.get_profile(fab.board_profile_name(board)); canonical = fab.COPPER_LAYER_IDS.get(layer_id)
    require(profile and canonical in fab.COPPER_LAYERS
        and profile['roles'][fab.COPPER_LAYERS.index(canonical)] != 'GND', 'terminal_frame_cannot_modify_reference_plane')
    kind, domain, contract = authority._model(board, source, net, board_hint)
    keepers = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == net
        and set(z.GetLayerSet().CuStack()) == {layer_id} and z.GetAssignedPriority() == 0
        and z.GetZoneName() in (native.ZONE_NAME, signed.ZONE_NAME) and z.IsFilled()
        and z.HasFilledPolysForLayer(layer_id) and z.GetFilledPolysList(layer_id).Collide(via.GetEffectiveShape(layer_id),0)]
    require(len(keepers) == 1, 'one_registered_contacting_terminal_keeper_required')
    zone = keepers[0]; config = landing._configuration(zone)
    require(not config['group_uuid'] and (not config['locked'] or allow_locked_source)
        and config['connection'] == int(pcbnew.ZONE_CONNECTION_FULL) and config['smoothing'] == 0,
        'explicit_unchanged_solid_terminal_keeper_ownership_required')
    require(zone.Outline().OutlineCount() == 1 and not zone.Outline().HoleCount(0), 'simple_native_terminal_keeper_required')
    ring = zone.Outline().Outline(0)
    points = [[ring.CPoint(i).x,ring.CPoint(i).y] for i in range(ring.PointCount())]
    require(4 <= len(points) <= 1024 and all(native._centerline_allowed(a,z,'chamfer45')
        for a,z in zip(points,points[1:]+points[:1])), 'literal_canonical_source_terminal_owner_required')
    contacts = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == net
        and t.GetLayer() == layer_id and tuple(via.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd()))]
    width = max([int(via.GetWidth(layer_id))]+[int(t.GetWidth()) for t in contacts])
    cover = centered_cover(board,via,layer_id,width); patch = native._poly(cover)
    native._require_unoccupied_outline(board,patch,net,layer_id,deadline,
        clearance_nm=config['clearance_nm'],allow_native_hole_bridges=True)
    merged = unary_union([Polygon(points),Polygon(cover)])
    require(merged.is_valid and merged.geom_type == 'Polygon' and not merged.interiors,
        'one_connected_unperforated_terminal_profile_required')
    newpoints = [[round(x),round(y)] for x,y in list(merged.exterior.coords)[:-1]]
    require(all(native._centerline_allowed(a,z,'chamfer45') for a,z in zip(newpoints,newpoints[1:]+newpoints[:1])),
        'literal_canonical_terminal_union_required')
    protected = []
    for other in board.Zones():
        if other.GetIsRuleArea() or other.GetNetname() != net or not other.IsOnLayer(layer_id) or other.GetAssignedPriority() <= config['priority']: continue
        overlap = other.Outline().CloneDropTriangulation(); overlap.BooleanIntersection(patch)
        if overlap.OutlineCount(): protected.append(dict(native=native._support_row(other,layer_id,deadline,allow_native_hole_bridges=True),configuration=landing._configuration(other)))
    require(len(protected) <= 64, 'bounded_stronger_terminal_regions_required')
    x0,y0,x1,y1 = Polygon(cover).bounds; window = [[int(x0-200000),int(y0-200000)],[int(x1+200000),int(y0-200000)],
        [int(x1+200000),int(y1+200000)],[int(x0-200000),int(y1+200000)]]
    row = dict(via_uuid=via_uuid, layer_id=layer_id, allow_locked_source=allow_locked_source,
        zone_uuid=force._uid(zone), source_configuration=config, source_keeper=landing._native_source(zone,allow_complex_fill=True),
        source_points_nm=points, points_nm=newpoints, centered_cover_nm=cover, observation_window_nm=window,
        source_barrel=plain(dict(position_nm=list(via.GetPosition()),diameter_nm=int(via.GetWidth(layer_id)),drill_nm=int(via.GetDrillValue()),
            locked=bool(via.IsLocked()),top_layer=int(via.TopLayer()),bottom_layer=int(via.BottomLayer()))),
        actual_contact_width_nm=width, source_contact_track_uuids=sorted(force._uid(t) for t in contacts),
        source_current_kind=kind, source_current_contract=plain(contract),
        regional_combination_contract=dict(fill_policy='source_preserving_regions',net=net,layer_id=layer_id,
            min_thickness_nm=config['min_thickness_nm'],supporting_zones=[],regional_fill_binding=dict(source_zone_uuid=force._uid(zone),
                protected_regions=protected,source_island=bool(zone.IsIsland(layer_id,0)),
                source_islands=[bool(zone.IsIsland(layer_id,i)) for i in range(zone.GetFilledPolysList(layer_id).OutlineCount())])))
    row['source_visible_curve_runs'] = curve_runs(_local_shape(board,row,deadline),config['min_thickness_nm'])
    require(row['source_visible_curve_runs']['longest_mm'] >= max(width/4e6,config['min_thickness_nm']/1e6),
        'no_exposed_terminal_curve_in_actual_local_material:'+str(row['source_visible_curve_runs']))
    return plain(row)


def emit(source, records):
    before, after = [pcbnew.LoadBoard(str(source)) for _ in range(2)]
    old = {force._uid(z):z for z in before.Zones()}; zones = {force._uid(z):z for z in after.Zones()}
    batch = pcbnew.ZONES()
    require(len({r['zone_uuid'] for r in records}) == len(records), 'one_terminal_per_keeper_in_native_batch_required')
    for row in records:
        zone = zones[row['zone_uuid']]; zone.UnFill(); zone.Outline().RemoveAllContours()
        zone.Outline().Append(native._poly(row['points_nm'])); batch.append(zone)
    cec_zone_fill.compile_selected(after,batch,timeout_s=10.)
    for row in records:
        zone = zones[row['zone_uuid']]; face = row['layer_id']; original = old[row['zone_uuid']]
        result = regional._combine(before,zone.GetFilledPolysList(face),row['regional_combination_contract'],time.monotonic()+10.)
        flags = row['regional_combination_contract']['regional_fill_binding']['source_islands']
        for i in reversed(range(result.OutlineCount()-len(flags),result.OutlineCount())): result.RemoveOutline(i)
        result.BooleanIntersection(native._poly(row['centered_cover_nm']))
        result = regional.anchored_native_additions(before,result,net=row['source_configuration']['net'],layer=face,
            source_zone_uuids=[row['zone_uuid']],deadline=time.monotonic()+10.)
        result.Fracture(); result.Append(original.GetFilledPolysList(face))
        zone.UnFill(); zone.SetFilledPolysList(face,result); zone.SetIsFilled(True)
        for i,flag in enumerate(flags):
            if flag: zone.SetIsIsland(face,result.OutlineCount()-len(flags)+i)
    # Clearance was checked against the actual saved foreign metal, including
    # Ground. No opportunistic/global plane refill can change a reference sheet.
    return after


def observe(before, after, row):
    deadline = time.monotonic()+10.; first = _local_shape(before,row,deadline); last = _local_shape(after,row,deadline)
    a,b = [curve_runs(shape,row['source_configuration']['min_thickness_nm']) for shape in (first,last)]
    added = last.difference(first)
    require(added.area >= .0025, 'terminal_frame_has_no_actual_visible_native_progress')
    require(b['longest_mm'] <= .5*a['longest_mm'],
        'native_terminal_frame_did_not_break_up_visible_curved_run:'+str(dict(source=a,candidate=b)))
    return plain(dict(ok=True,complete=True,source_curve_runs=a,candidate_curve_runs=b,
        visible_added_native_area_mm2=added.area,centered_on_actual_unchanged_barrel=True,
        aesthetic_interest_threshold_is_not_manufacturing_or_material_loss_tolerance=True,
        every_source_ground_sheet_retained_without_refill=True,release_authority=False))


def plan(source, *, board_hint, targets):
    require(type(targets) is list and 1 <= len(targets) <= 4,
        'bounded_explicit_terminal_cohort_required')
    records = [record(source,board_hint=board_hint,**r) for r in targets]
    require(len({r['zone_uuid'] for r in records}) == len(records), 'one_terminal_per_keeper_required')
    return plain(dict(policy=POLICY,source_sha256=force._hash(Path(source)),code_identity=force._code_identity(),
        authority_sha256=force._hash(Path(__file__).resolve()),board_hint=board_hint,targets=targets,records=records,
        current_or_barrel_qualified=False,release_authority=False))


def construct(source, proposal):
    require(plan(source,board_hint=proposal['board_hint'],targets=proposal['targets']) == proposal,
        'stale_or_forged_centered_terminal_proposal')
    return emit(source,proposal['records'])


def receive_literal(source, candidate, proposal):
    result = dict(ok=False,complete=False,errors=[],release_authority=False,
        current_or_barrel_qualified=False,fresh_whole_board_receiving_still_required=True)
    try:
        source,candidate = map(Path,(source,candidate)); before = pcbnew.LoadBoard(str(source))
        expected = construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-centered-terminal-') as tmp:
            path = Path(tmp)/'expected.kicad_pcb'; field._save_field_snapshot(expected,path)
            require(syntax._freeze(additive._nodes(path)[0]) == syntax._freeze(additive._nodes(candidate)[0]),
                'centered_terminal_changed_unowned_native_source_evidence')
        require(force._sidecars(source) == force._sidecars(candidate), 'terminal_frame_changed_rules_or_companions')
        after = pcbnew.LoadBoard(str(candidate)); observations = []
        for row in proposal['records']:
            first,last = [next(z for z in board.Zones() if force._uid(z) == row['zone_uuid']) for board in (before,after)]
            require(landing._configuration(first) == landing._configuration(last), 'terminal_source_process_or_ownership_changed')
            require(regional.exact_source_contour_present(last.GetFilledPolysList(row['layer_id']),first.GetFilledPolysList(row['layer_id']),time.monotonic()+10.),
                'terminal_frame_lost_original_native_filled_record')
            observations.append(observe(before,after,row))
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            code_identity=force._code_identity(),exact_saved_source_native_reconstruction=True,
            every_original_filled_record_track_pad_barrel_field_and_ground_sheet_literal=True,
            actual_saved_terminal_progress=observations,modified_zone_uuids=[r['zone_uuid'] for r in proposal['records']],
            modified_nets=sorted({r['source_configuration']['net'] for r in proposal['records']}))
    except (ValueError,RuntimeError,AssertionError,KeyError,TypeError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
