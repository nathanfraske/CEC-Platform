"""Source-derived translation of one closed opposite-silk reference map.

No pose admission, copper authority, unlock, ungroup, rotation or fabrication
qualification. Exact source-producer rectangular corner and native Fab-body
maps are annotation associations only, never closed assembly-body authority.
Other fragments and miniature-map variants deliberately fail closed. Separate explicit cardinal
APIs below transport recognized annotation maps; legacy APIs remain translation
only. Neither API grants pose, copper, current or fabrication admission.
"""
import copy,math,time
import hashlib
import tempfile
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as ast
import cec_copper_echo as syntax
import cec_force_current as force

PREFIX = 'CEC_READABLE_COMPONENT_REFERENCE_MAPPING:'
FAB_PROJECTION = 'exact_source_fab_body_not_manufacturing_courtyard'
COURT_PROJECTION = 'source_manufacturing_courtyard'


def _source_fab_body_vertices(fp):
    """Recognize the producer's actual Fab rectangle, not a smaller ink bbox.

    Keep the complete manufacturing courtyard as separate placement authority.
    Text, functional marks, multiple/filled/ambiguous bodies and noncardinal
    parts cannot be substituted for this one literal native body rectangle.
    """
    import cec_assembly_envelope as assembly
    from shapely.geometry import Polygon
    face = pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab
    art = [item for item in fp.GraphicalItems()
           if item.GetLayer() == face and item.GetClass() != 'PCB_TEXT']
    _require(len(art) == 1 and art[0].GetClass() == 'PCB_SHAPE'
             and art[0].GetShape() == pcbnew.SHAPE_T_RECT and not art[0].IsAnyFill()
             and fp.GetOrientationDegrees() % 90 == 0,
             'one_exact_cardinal_source_fab_body_rectangle_required')
    a, z = art[0].GetStart(), art[0].GetEnd()
    x0, x1 = sorted((a.x, z.x)); y0, y1 = sorted((a.y, z.y))
    vertices = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    body = Polygon([(x / 1e6, y / 1e6) for x, y in vertices])
    court = fp.GetCourtyard(fp.GetLayer())
    _require(x0 < x1 and y0 < y1 and court.OutlineCount() == 1
             and court.HoleCount(0) == 0
             and assembly.polygon_from_native(court).covers(body),
             'source_fab_body_must_be_inside_unchanged_manufacturing_courtyard')
    return vertices


def _guide_polygon(fp, proof):
    import cec_assembly_envelope as assembly
    if proof.get('outline_geometry') == 'exact_source_fab_body_not_manufacturing_courtyard':
        from shapely.geometry import Polygon
        return Polygon([(x / 1e6, y / 1e6) for x, y in _source_fab_body_vertices(fp)])
    return assembly.polygon_from_native(fp.GetCourtyard(fp.GetLayer()))


def _rectangular_corner_arms(vertices,stroke):
    """Exact eight-arm producer style, not a partial-outline inference."""
    if len(vertices)!=4 or len(set(vertices))!=4:return None
    vectors=[(vertices[(i+1)%4][0]-a[0],vertices[(i+1)%4][1]-a[1])
        for i,a in enumerate(vertices)]
    if any(v==(0,0)for v in vectors)or any(vectors[i][0]*vectors[(i+1)%4][0]+
            vectors[i][1]*vectors[(i+1)%4][1]!=0 for i in range(4)):
        return None
    if any(vectors[i]!=tuple(-x for x in vectors[i+2])for i in range(2)):return None
    arms=set()
    for i,a in enumerate(vertices):
        for z in(vertices[(i-1)%4],vertices[(i+1)%4]):
            length=math.dist(a,z);leg=min(350000.,length/3)
            if leg<stroke:return None
            end=tuple(round(a[k]+(z[k]-a[k])*leg/length)for k in(0,1))
            if end==a:return None
            arms.add(tuple(sorted((a,end))))
    return arms if len(arms)==8 else None


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _rectangular_nearest_leader(vertices,bounds,segment):
    """Exact integer closest-pair proof, independent of a tie's traversal order.

    Limited to an actual axis-aligned four-corner courtyard and the existing
    producer's buffered glyph envelope. Other contours keep their exact
    original nearest-point test. No distance or boundary tolerance is added.
    """
    if len(vertices)!=4 or len(bounds)!=4 or len(segment)!=2:return False
    if any(type(v)is not int for p in vertices for v in p)or any(type(v)is not int for v in bounds):return False
    xs=sorted({p[0]for p in vertices});ys=sorted({p[1]for p in vertices})
    if len(xs)!=2 or len(ys)!=2 or set(vertices)!={(x,y)for x in xs for y in ys}:return False
    if any(a[0]!=b[0]and a[1]!=b[1]for a,b in zip(vertices,vertices[1:]+vertices[:1])):return False
    body=(xs[0],ys[0],xs[1],ys[1]);glyph=tuple(bounds)
    if glyph[0]>=glyph[2]or glyph[1]>=glyph[3]:return False
    def on_boundary(point,box):
        return (len(point)==2 and all(type(n)is int for n in point)
            and box[0]<=point[0]<=box[2]and box[1]<=point[1]<=box[3]
            and(point[0]in(box[0],box[2])or point[1]in(box[1],box[3])))
    dx=max(0,body[0]-glyph[2],glyph[0]-body[2])
    dy=max(0,body[1]-glyph[3],glyph[1]-body[3]);distance2=dx*dx+dy*dy
    a,b=segment
    return bool(distance2>0 and sum((x-y)**2 for x,y in zip(a,b))==distance2
        and((on_boundary(a,body)and on_boundary(b,glyph))or(on_boundary(b,body)and on_boundary(a,glyph))))


def _translation_bound(maximum_translation_mm):
    # Operational annotation scope, never physical placement authority.
    import math
    _require(type(maximum_translation_mm) in (int, float)
             and math.isfinite(maximum_translation_mm)
             and 0 < maximum_translation_mm <= 128,
             'bounded_reference_translation_policy_required')
    return maximum_translation_mm * 1000000


def _delta(value, maximum_translation_mm=10.):
    bound = _translation_bound(maximum_translation_mm)
    _require(type(value) in (tuple, list) and len(value) == 2
             and all(type(v) is int and abs(v) <= bound for v in value),
             'bounded_literal_translation_nm_required')
    return tuple(value)


def inspect(source, *, owner_uuid, group_uuid):
    """Independently recognize source geometry, not just its group name."""
    return inspect_many(source,[(owner_uuid,group_uuid)])[0]


def inspect_native_fab_body(source, *, owner_uuid, group_uuid):
    """Explicit Fab-map transport only; never legacy print-map authority.

    Printing still requires its independently received producer association.
    A new transport proof is not a substitute for that separate admission.
    """
    _require(all(type(value) is str and value for value in (owner_uuid,group_uuid)),
             'literal_source_fab_map_selection_required')
    with _source_context(source) as context:
        return _inspect_context(context,[(owner_uuid,group_uuid)],
                                projection_geometries=[FAB_PROJECTION])[0]


def _proof_projection(proof):
    value=proof.get('outline_geometry',COURT_PROJECTION)
    _require(value in (COURT_PROJECTION,FAB_PROJECTION),
             'exact_source_reference_projection_required')
    return value


def _inspect_proof_source(proof,source=None):
    inspect_op=inspect_native_fab_body if _proof_projection(proof)==FAB_PROJECTION else inspect
    return inspect_op(source or proof['source'],owner_uuid=proof['owner_uuid'],group_uuid=proof['group_uuid'])


def inspect_many(source,selections,*,timeout_s=10.):
    """Fresh read-only batch; no caller-supplied native board/proof/cache."""
    _require(type(selections)is list and 1<=len(selections)<=128
        and all(type(v)in(tuple,list)and len(v)==2 and all(type(x)is str and x for x in v)for v in selections)
        and len({tuple(v)for v in selections})==len(selections),'bounded_unique_source_map_selections_required')
    _require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_source_map_inspection_required')
    with _source_context(source,timeout_s=timeout_s)as context:
        return _inspect_context(context,selections)


@contextmanager
def _source_context(source,*,timeout_s=10.):
    """PRIVATE single-operation Source snapshot; never caller cache authority.

    Each producer and independent receiver creates its OWN context. Complete
    family/code/hash entry AND exit checks remain; no metadata-only shortcut.
    """
    _require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_source_map_inspection_required')
    deadline=time.monotonic()+timeout_s;source=Path(source).resolve(strict=True)
    sha=force._hash(source);code=force._code_identity();family=force._family(source)
    data=source.read_bytes()
    _require(hashlib.sha256(data).hexdigest()==sha,'source_map_snapshot_changed')
    with tempfile.TemporaryDirectory(prefix='cec-bound-annotation-')as directory:
        snapshot=Path(directory)/'source.kicad_pcb';snapshot.write_bytes(data)
        native=pcbnew.LoadBoard(str(snapshot));_require(native is not None,'valid_native_source_board_required')
        native.SetFileName(str(source))
        nodes=ast._nodes(snapshot)[1]
        context=dict(source=source,sha=sha,code=code,family=family,native=native,nodes=nodes,
            rules=_cardinal_rules(source,native),bytes=data,deadline=deadline,
            snapshot=snapshot,snapshot_written=True,proofs={})
        try:yield context
        finally:_context_live(context)


def _context_live(context):
    _require(context['sha']==force._hash(context['source'])and context['code']==force._code_identity()
        and context['family']==force._family(context['source']),'source_map_batch_source_or_code_changed')
    _require(time.monotonic()<context['deadline'],'source_map_batch_deadline')


def _inspect_context(context,selections,*,projection_geometries=None):
    if projection_geometries is None:projection_geometries=[COURT_PROJECTION]*len(selections)
    _require(len(projection_geometries)==len(selections)
             and all(v in (COURT_PROJECTION,FAB_PROJECTION)for v in projection_geometries),
             'one_exact_source_projection_per_selection_required')
    result=[]
    for (owner_uuid,group_uuid),projection in zip(selections,projection_geometries):
        _require(time.monotonic()<context['deadline'],'source_map_batch_deadline')
        proof=_inspect_bound(context['source'],context['native'],context['nodes'],context['rules'],
            context['sha'],owner_uuid=owner_uuid,group_uuid=group_uuid,projection_geometry=projection)
        context['proofs'][(owner_uuid,group_uuid)]=proof;result.append(proof)
    return result


def _clone_context(context):
    # Native BOARD(board) is not a clone in KiCad SWIG. Reload immutable exact
    # Source bytes from private storage instead of rereading a live Source.
    if not context['snapshot_written']:
        context['snapshot'].write_bytes(context['bytes']);context['snapshot_written']=True
    board=pcbnew.LoadBoard(str(context['snapshot']))
    _require(board is not None,'valid_bound_source_clone_required')
    board.SetFileName(str(context['source']))
    return board


def _inspect_bound(source,b,nodes,rules,source_sha,*,owner_uuid,group_uuid,
                   projection_geometry=COURT_PROJECTION):
    """Internal context constructed only by fresh inspect_many."""
    _require(projection_geometry in (COURT_PROJECTION,FAB_PROJECTION),
             'exact_source_reference_projection_required')
    groups = list(b.Groups())
    selected = [g for g in groups if force._uid(g) == group_uuid]
    _require(len(selected) == 1, 'one_actual_source_group_required')
    group = selected[0]
    members = list(group.GetItems())
    _require(6 <= len(members) <= 258 and len({force._uid(i) for i in members}) == len(members),
             'bounded_unique_closed_map_members_required')
    fps = [i for i in members if i.GetClass() == 'FOOTPRINT']
    texts = [i for i in members if i.GetClass() == 'PCB_TEXT']
    lines = [i for i in members if i.GetClass() == 'PCB_SHAPE']
    _require(len(fps) == len(texts) == 1 and len(lines) + 2 == len(members),
             'one_footprint_text_and_closed_court_only_required')
    fp, text = fps[0], texts[0]
    _require(force._uid(fp) == owner_uuid and not fp.IsLocked()
             and group.GetName() == PREFIX + fp.GetReference(), 'actual_unlocked_owner_reference_required')
    ids = {force._uid(i) for i in members}
    _require(not group.GetParentGroup() and all(not g.GetParentGroup() for g in groups if g == group)
             and all(not ({force._uid(i) for i in g.GetItems()} & (ids | {group_uuid}))
                     for g in groups if force._uid(g) != group_uuid),
             'one_nonnested_nonoverlapping_source_group_required')
    face = pcbnew.F_SilkS if fp.IsFlipped() else pcbnew.B_SilkS
    _require(not fp.Reference().IsVisible() and text.GetText() == fp.GetReference()
             and text.IsVisible() and text.GetLayer() == face
             and text.IsMirrored() == (face == pcbnew.B_SilkS)
             and text.IsLocked()
             and text.GetHorizJustify() == pcbnew.GR_TEXT_H_ALIGN_CENTER
             and text.GetVertJustify() == pcbnew.GR_TEXT_V_ALIGN_CENTER,
             'hidden_owner_and_actual_readable_opposite_reference_required')
    settings = b.GetDesignSettings()
    size = text.GetTextSize(); stroke = text.GetTextThickness()
    _require(size.x == size.y and size.x >= max(round(rules['silk_height']*1e6), settings.m_MinSilkTextHeight)
             and stroke >= max(round(rules['silk']*1e6), settings.m_MinSilkTextThickness)
             and text.GetTextAngle().AsDegrees() % 180 in (0, 90)
             and not text.IsBold() and not text.IsItalic(), 'unchanged_readable_source_font_required')
    court = fp.GetCourtyard(fp.GetLayer())
    _require(court.OutlineCount() == 1 and court.HoleCount(0) == 0,
             'one_closed_native_source_courtyard_required')
    chain = court.COutline(0)
    vertices = [(chain.CPoint(i).x, chain.CPoint(i).y) for i in range(chain.PointCount())]
    edges = {tuple(sorted((vertices[i], vertices[(i + 1) % len(vertices)])))
             for i in range(len(vertices))}
    actual = []
    for line in lines:
        _require(line.GetShape() == pcbnew.SHAPE_T_SEGMENT and line.GetLayer() == face
                 and line.IsLocked() and line.GetWidth() == stroke
                 and line.GetStart() != line.GetEnd(), 'literal_opposite_courtyard_edges_required')
        actual.append(tuple(sorted((tuple(line.GetStart()), tuple(line.GetEnd())))))
    actual_set=set(actual);style='complete_closed_source_courtyard'
    _require(len(actual)==len(actual_set),'unique_projected_source_courtyard_strokes_required')
    if projection_geometry==FAB_PROJECTION:
        # Explicitly requested Source-Fab transport is separate from legacy
        # print recognition, which still needs a received producer mapping.
        vertices=_source_fab_body_vertices(fp)
        edges={tuple(sorted((a,z)))for a,z in zip(vertices,vertices[1:]+vertices[:1])}
        _require(edges<=actual_set and len(actual_set-edges)<=1,
            'exact_complete_source_fab_body_projection_required')
        extras=actual_set-edges;style='complete_closed_source_fab_body'
    elif edges<=actual_set and len(actual_set-edges)<=1:
        extras=actual_set-edges
    else:
        arms=_rectangular_corner_arms(vertices,stroke)
        _require(arms is not None and arms<=actual_set and len(actual_set-arms)<=1,
            'exact_closed_or_all_eight_source_rectangular_corner_arms_required')
        extras=actual_set-arms;style='four_exact_source_rectangular_corner_brackets'
    # Positive readable containment is deliberately the same conservative
    # native glyph geometry used by the source annotation producer.
    import cec_assembly_envelope as assembly
    p = pcbnew.SHAPE_POLY_SET()
    text.TransformShapeToPolygon(p, face, 0, 1000, pcbnew.ERROR_OUTSIDE, False)
    glyph = assembly.polygon_from_native(p)
    if style == 'complete_closed_source_fab_body':
        from shapely.geometry import Polygon
        native_court = Polygon([(x / 1e6, y / 1e6) for x, y in vertices])
    else:
        native_court = assembly.polygon_from_native(court)
    gap = max(round(rules['silk_clearance']*1e6), settings.m_SilkClearance)
    _require(glyph.is_valid and not glyph.is_empty, 'valid_readable_reference_glyph_required')
    inside = native_court.buffer(-(stroke / 2 + gap + 2000) / 1e6,
                                 join_style=2).covers(glyph)
    if inside:
        _require(not extras, 'internal_reference_cannot_have_arbitrary_leader')
    else:
        from shapely.ops import nearest_points
        _require(len(extras) == 1 and not native_court.intersects(
            glyph.buffer((gap + 2000) / 1e6)), 'one_external_clear_readable_reference_leader_required')
        reserved_glyph=glyph.envelope.buffer((gap + stroke / 2 + 2000) / 1e6, join_style=2)
        a, z = nearest_points(native_court,reserved_glyph)
        expected_leader = tuple(sorted((tuple(round(v * 1e6) for v in a.coords[0]),
                                       tuple(round(v * 1e6) for v in z.coords[0]))))
        tied=(len(extras)==1 and _rectangular_nearest_leader(vertices,
            tuple(round(v*1e6)for v in reserved_glyph.bounds),next(iter(extras))))
        _require((extras == {expected_leader}or tied) and expected_leader[0] != expected_leader[1],
                 'exact_source_producer_nearest_point_leader_required')
    _require(ids | {group_uuid} <= nodes.keys(), 'all_members_must_be_literal_root_nodes')
    member_fields = [c for c in nodes[group_uuid][1:]
                     if isinstance(c, list) and c and c[0] == 'members']
    _require(len(member_fields) == 1 and len(member_fields[0]) - 1 == len(ids)
             and ast._members(nodes[group_uuid]) == ids,
             'literal_group_members_must_equal_native_members')
    for uid, node in nodes.items():
        if uid != group_uuid and node[0] == 'group':
            _require(not ast._members(node) & (ids | {group_uuid}),
                     'literal_nested_or_overlapping_membership_refused')
    _require(not any(isinstance(c, list) and c and c[0] == 'hide'
                     for c in nodes[force._uid(text)][1:]),
             'literal_hidden_reference_text_refused')
    proof=dict(schema=1, scope='source_closed_opposite_reference_translation',
                source=str(source), source_sha256=source_sha, owner_uuid=owner_uuid,
                group_uuid=group_uuid, member_uuids=sorted(ids),
                source_nodes={u: nodes[u] for u in sorted(ids | {group_uuid})},
                group_locked=bool(group.IsLocked()), owner_locked=bool(fp.IsLocked()),
                release_authority=False, pose_admitted=False)
    if style=='four_exact_source_rectangular_corner_brackets':
        proof.update(scope='source_exact_rectangular_corner_reference_translation',
            outline_style=style,closed_assembly_body_authority=False)
    elif style=='complete_closed_source_fab_body':
        proof.update(scope='source_exact_fab_body_reference_translation',outline_style=style,
            outline_geometry='exact_source_fab_body_not_manufacturing_courtyard',
            closed_assembly_body_authority=False,manufacturing_courtyard_unchanged=True)
    return proof


def _fresh(proof):
    _require(_inspect_proof_source(proof) == proof, 'source_annotation_contract_changed')


def transform(board, proof, *, delta_nm, maximum_translation_mm=10.):
    """Translate every owned item exactly once; retain every authored lock."""
    return transform_many(board, [(proof, delta_nm)], maximum_translation_mm=maximum_translation_mm)


def transform_many(board, requests, *, maximum_translation_mm=10.):
    """One exact-source preflight for disjoint explicitly requested groups."""
    import cec_field_coupling as field
    _require(type(requests) in (list, tuple) and 1 <= len(requests) <= 8,
             'bounded_explicit_reference_group_translations_required')
    owned=set()
    for proof, delta_nm in requests:
        _fresh(proof); _delta(delta_nm, maximum_translation_mm)
        _require(not owned.intersection(proof['member_uuids']), 'disjoint_source_groups_required')
        owned.update(proof['member_uuids'])
    parent = pcbnew.LoadBoard(requests[0][0]['source'])
    _require(all(p['source_sha256'] == requests[0][0]['source_sha256'] for p,d in requests),
             'same_exact_source_groups_required')
    _require(field._field_snapshot_inventory(parent) == field._field_snapshot_inventory(board),
             'exact_source_native_board_required')
    items = {force._uid(i): i for i in [*board.GetFootprints(), *board.GetDrawings()]}
    for proof, delta_nm in requests:
        for uid in proof['member_uuids']:
            items[uid].Move(pcbnew.VECTOR2I(*_delta(delta_nm, maximum_translation_mm)))
    return dict(translated_member_uuids=sorted(owned), pose_admitted=False,
                release_authority=False)


def expected_nodes(proof, *, delta_nm, maximum_translation_mm=10.):
    """Source AST expected nodes; no native serialization normalization."""
    _fresh(proof); dx, dy = _delta(delta_nm, maximum_translation_mm)
    expected = copy.deepcopy(proof['source_nodes'])
    for uid in proof['member_uuids']:
        node = expected[uid]
        keys = {'at'} if node[0] in ('footprint', 'gr_text') else {'start', 'end'}
        for child in node[1:]:
            if isinstance(child, list) and child and child[0] in keys:
                child[1] = str(Decimal(str(child[1])) + Decimal(dx) / Decimal(1000000))
                child[2] = str(Decimal(str(child[2])) + Decimal(dy) / Decimal(1000000))
    return expected


def _unfinished_annotation_snapshot(board,path):
    """Native IO query only: never reload a deliberately unfinished frame.

    Reloading may propagate a temporary foreign contact's net before the
    macro has transported its Source-owned barrels. Preserve every live item
    and compare a second complete serialization instead. This is NOT the
    full-field snapshot gate and grants no copper or saved-frame admission.
    """
    import tempfile
    import cec_native_layer_masks as masks
    masks.install(pcbnew)
    def identity():
        items=[*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings(),
            *board.Zones(),*board.Groups()]
        _require(len(items)<=16384,'bounded_unfinished_annotation_native_inventory')
        rows=[];total=0
        for item in items:
            writer=pcbnew.PCB_IO_KICAD_SEXPR();writer.Format(item)
            text=writer.GetStringOutput(True);total+=len(text)
            _require(total<=64*1024*1024,'bounded_unfinished_annotation_native_serialization')
            rows.append((item.GetClass(),force._uid(item),text))
        # wxString proxies are newly allocated on every asdict() call and
        # their Python identity is not the authored property string value.
        properties=tuple(sorted((str(k),str(v))for k,v in board.GetProperties().asdict().items()))
        return (_cardinal_identity(board),tuple(rows),properties,
            tuple(board.GetEnabledLayers().Seq()),board.GetCopperLayerCount(),board.GetFileName())
    before=identity();name=board.GetFileName()or ''
    try:
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    finally:board.SetFileName(name)
    _require(identity()==before,'unfinished_annotation_query_changed_caller_identity')
    _require(Path(path).is_file(),'unfinished_annotation_query_missing')
    with tempfile.TemporaryDirectory(prefix='cec-annotation-query-stability-')as directory:
        repeated=Path(directory)/'repeat.kicad_pcb'
        try:pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(repeated),board)
        finally:board.SetFileName(name)
        _require(identity()==before,'unfinished_annotation_query_changed_caller_identity')
        _require(syntax._freeze(ast._nodes(path)[0])==syntax._freeze(ast._nodes(repeated)[0]),
            'unfinished_annotation_complete_native_query_unstable')


def verify_native(source, board, requests, *, maximum_translation_mm=10.):
    """Native root ink/group replay for an unfinished copper macro frame.

    Only selected footprint nodes participate; every unrelated root drawing
    and group remains exact. Copper ownership is entirely the macro's job.
    """
    import tempfile
    source=Path(source).resolve(strict=True);source_hash=force._hash(source)
    _require(all(Path(p['source']).resolve()==source for p,d in requests),'same_reference_native_source_required')
    expected=pcbnew.LoadBoard(str(source))
    transform_many(expected, requests, maximum_translation_mm=maximum_translation_mm)
    owners={p['owner_uuid'] for p,d in requests}
    with tempfile.TemporaryDirectory(prefix='cec-reference-native-replay-') as directory:
        files=[Path(directory)/'expected.kicad_pcb',Path(directory)/'actual.kicad_pcb']
        for native,path in zip((expected,board),files):_unfinished_annotation_snapshot(native,path)
        maps=[ast._nodes(path)[1] for path in files]
    def selected(nodes):
        return {u:n for u,n in nodes.items() if u in owners or n[0]=='group' or str(n[0]).startswith('gr_')}
    before,after=map(selected,maps)
    _require(before.keys()==after.keys() and all(syntax._freeze(before[u])==syntax._freeze(after[u])
             for u in before), 'native_source_reference_annotation_replay_differs')
    _require(force._hash(source)==source_hash,'unfinished_reference_native_source_changed')
    return dict(ok=True,complete=True,current_authority=False,release_authority=False,
        scope='unfinished_selected_footprints_and_all_root_ink_groups_native_query_only',
        copper_identity_reload_deferred=True,full_field_snapshot_proved=False,
        full_macro_physical_copper_and_final_saved_receiving_still_required=True)


def verify(source, candidate, proof, *, delta_nm, maximum_translation_mm=10.):
    """All root AST nodes exact, except source-derived translated coordinates."""
    _require(Path(source).resolve() == Path(proof['source']), 'same_source_required')
    expected = expected_nodes(proof, delta_nm=delta_nm, maximum_translation_mm=maximum_translation_mm)
    _, before = ast._nodes(source); _, after = ast._nodes(candidate)
    _require(before.keys() == after.keys(), 'source_root_identity_set_changed')
    _require(all(syntax._freeze(after[u]) == syntax._freeze(expected.get(u, n))
                 for u, n in before.items()), 'source_expected_annotation_translation_differs')
    # Re-recognition also rejects malformed/native lost group ownership.
    _inspect_proof_source(proof,candidate)
    return dict(ok=True, complete=True, current_authority=False,
                pose_admitted=False, release_authority=False)


def _hidden_field_order(node):
    """Only the native writer's placement of a property/hide directive.

    No unknown field, changed visibility, duplicate directive or other
    ordering difference is normalized.  This comparison is used to RESTORE
    exact source nodes in the constructor, not to loosen saved receiving.
    """
    result=copy.deepcopy(node)
    if result[0]=='footprint':
        for child in result[1:]:
            if not isinstance(child,list) or not child or child[0]!='property':continue
            hidden=[p for p in child[3:] if isinstance(p,list) and p and p[0]=='hide']
            _require(len(hidden)<=1 and all(len(p)==2 and p[1] in ('yes','no') for p in hidden),
                'one_literal_property_visibility_directive_required')
            if hidden:child[:]=[p for p in child if p not in hidden]+hidden
    return syntax._freeze(result)


def preserve_literal_hidden_field_order(candidate, requests, *, maximum_translation_mm=10.):
    """Restore owned source AST order after a native save, with no new edits.

    KiCad serializes a hidden Reference before its UUID, while a literal
    source annotation producer may append the same hide flag afterwards.
    Only that proven permutation is restored.  Copper/parts/ink/visibility
    cannot change, and unrelated candidate text remains byte-for-byte exact.
    The normal strict saved receiver is deliberately unchanged.
    """
    import cec_field_coupling as field
    import cec_source_retaining_ses_import as raw
    _require(type(requests) in (list,tuple) and 1<=len(requests)<=8,
        'bounded_source_literal_reference_save_scope_required')
    candidate=Path(candidate).resolve(strict=True)
    _,actual=ast._nodes(candidate);expected={}
    for proof,delta in requests:
        _require(candidate!=Path(proof['source']).resolve(),'distinct_private_reference_candidate_required')
        nodes=expected_nodes(proof,delta_nm=delta,maximum_translation_mm=maximum_translation_mm)
        _require(not set(nodes)&set(expected),'disjoint_source_literal_reference_nodes_required')
        expected.update(nodes)
    _require(set(expected)<=set(actual),'all_owned_candidate_reference_nodes_required')
    changes={}
    for uid,node in expected.items():
        _require(_hidden_field_order(node)==_hidden_field_order(actual[uid]),
            'candidate_owned_reference_node_changed_beyond_hidden_field_order')
        if syntax._freeze(node)!=syntax._freeze(actual[uid]):changes[uid]=node
    before=pcbnew.LoadBoard(str(candidate));native=field._field_snapshot_inventory(before)
    original=raw.raw_text(candidate);text=original;spans=raw.inventory(original)
    for uid,node in sorted(changes.items(),key=lambda q:spans[q[0]][0],reverse=True):
        a,z=spans[uid];text=text[:a]+ast._render(node)+text[z:]
    if changes:
        try:
            raw.write_raw(candidate,text)
            after=pcbnew.LoadBoard(str(candidate))
            _require(after is not None and field._field_snapshot_inventory(after)==native,
                'literal_reference_field_order_changed_native_identity')
            _,saved=ast._nodes(candidate)
            _require(saved.keys()==actual.keys() and all(syntax._freeze(saved[u])==
                syntax._freeze(expected[u] if u in changes else actual[u]) for u in actual),
                'literal_reference_save_changed_unowned_candidate_node')
        except Exception:
            raw.write_raw(candidate,original)
            raise
    return dict(ok=True,complete=True,restored_source_literal_node_uuids=sorted(changes),
        native_parts_copper_ink_visibility_and_all_other_candidate_text_unchanged=True,
        saved_receiving_not_relaxed=True,routing_admitted=False,release_authority=False)


def _quarter(value):
    _require(type(value)is int and value in (0,1,2,3),'explicit_quarter_turns_0_to_3_required')
    return value


def _quarter_point(point,pivot,turn,delta):
    x,y=point[0]-pivot[0],point[1]-pivot[1]
    for _ in range(turn):x,y=y,-x
    return (pivot[0]+x+delta[0],pivot[1]+y+delta[1])


def _cardinal_identity(board):
    """No outward Source polygon is a substitute for actual native identity."""
    import cec_field_coupling as field
    import cec_reference_map_reownership as ink
    import cec_route_placement_admission as placement
    drawings={force._uid(i):(ink._geometry(i),
        (i.IsKeepUpright(),i.GetFontName(),i.GetHorizJustify(),i.GetVertJustify(),
         i.IsBold(),i.IsItalic())if i.GetClass()=='PCB_TEXT'else None)
        for i in board.GetDrawings()if i.GetClass()in('PCB_TEXT','PCB_SHAPE')}
    _require(len(drawings)==len(list(board.GetDrawings())),
        'unsupported_source_root_drawing_for_cardinal_replay')
    groups={force._uid(g):(g.GetName(),bool(g.IsLocked()),
        tuple(sorted(force._uid(i)for i in g.GetItems())))for g in board.Groups()}
    fields={force._uid(f):tuple(sorted((force._uid(t),t.GetName(),t.GetText(),
        tuple(t.GetPosition()),t.GetTextAngle().AsDegrees(),int(t.GetLayer()),
        tuple(t.GetTextSize()),t.GetTextThickness(),t.IsVisible(),t.IsLocked(),
        t.IsMirrored(),t.IsKeepUpright(),t.GetFontName(),t.IsBold(),t.IsItalic(),
        t.GetHorizJustify(),t.GetVertJustify())for t in f.GetFields()))
        for f in board.GetFootprints()}
    return field._field_snapshot_inventory(board),drawings,groups,placement._population(board),fields


def _cardinal_rules(source,board):
    import cec_fab_profile as profile
    import cec_fab_check as fab
    declared=profile.board_profile_name(board)
    return (fab.profile_rules(fab.PROFILES['jlcpcb'],fab.board_outer_copper_oz(source),declared)
        if declared is not None else dict(silk_height=.8,silk=.12,silk_clearance=.2))


def _rotate_cardinal_fp(fp,turn):
    # Native Rotate may normalize KeepUpright field angles by 180 degrees.
    # Preserve the authored field-angle phase across four exact quarter turns;
    # the authored KeepUpright flag still controls rendering, unchanged.
    texts=[*fp.GetFields(),*[i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT']]
    angles=[t.GetTextAngle().AsDegrees()for t in texts]
    if turn:
        fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
        for text,angle in zip(texts,angles):
            text.SetTextAngle(pcbnew.EDA_ANGLE((angle+turn*90)%360,pcbnew.DEGREES_T))


def _cardinal_derive(proof,quarter_turns,delta_nm,maximum_translation_mm=10.):
    """Construct only from freshly re-recognized literal Source; no pivot input."""
    with _source_context(proof['source'])as context:
        _inspect_context(context,[(proof['owner_uuid'],proof['group_uuid'])],
                         projection_geometries=[_proof_projection(proof)])
        return _cardinal_derive_context(context,proof,quarter_turns,delta_nm,maximum_translation_mm)


def _cardinal_derive_context(context,proof,quarter_turns,delta_nm,maximum_translation_mm=10.):
    _require(context['proofs'].get((proof['owner_uuid'],proof['group_uuid']))==proof,
        'source_annotation_contract_changed')
    turn=_quarter(quarter_turns);delta=_delta(delta_nm,maximum_translation_mm)
    board=_clone_context(context)
    items={force._uid(i):i for i in [*board.GetFootprints(),*board.GetDrawings()]}
    fp=items[proof['owner_uuid']];pivot=tuple(fp.GetPosition())
    _require(fp.GetOrientationDegrees()%90==0,'cardinal_source_owner_orientation_required')
    text=next(items[u]for u in proof['member_uuids']if items[u].GetClass()=='PCB_TEXT')
    lines=[items[u]for u in proof['member_uuids']if items[u].GetClass()=='PCB_SHAPE']
    court=fp.GetCourtyard(fp.GetLayer());chain=court.COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    if proof.get('outline_geometry')=='exact_source_fab_body_not_manufacturing_courtyard':
        vertices=_source_fab_body_vertices(fp)
    if proof.get('outline_style')=='four_exact_source_rectangular_corner_brackets':
        outline=_rectangular_corner_arms(vertices,text.GetTextThickness())
    else:outline={tuple(sorted((a,z)))for a,z in zip(vertices,vertices[1:]+vertices[:1])}
    leaders=[i for i in lines if tuple(sorted((tuple(i.GetStart()),tuple(i.GetEnd()))))not in outline]
    _require(len(leaders)<=1,'one_source_cardinal_leader_required')
    old_text_angle=text.GetTextAngle().AsDegrees();keep=text.IsKeepUpright()
    # FP.Rotate is invoked ONCE about its own actual Source center. Coordinates
    # for board-level ink use exact integer arithmetic, never trig rounding.
    _rotate_cardinal_fp(fp,turn)
    fp.SetPosition(pcbnew.VECTOR2I(pivot[0]+delta[0],pivot[1]+delta[1]))
    for line in lines:
        a,z=tuple(line.GetStart()),tuple(line.GetEnd())
        line.SetStart(pcbnew.VECTOR2I(*_quarter_point(a,pivot,turn,delta)))
        line.SetEnd(pcbnew.VECTOR2I(*_quarter_point(z,pivot,turn,delta)))
    at=tuple(text.GetTextPos())
    text.SetTextPos(pcbnew.VECTOR2I(*_quarter_point(at,pivot,turn,delta)))
    if turn:text.SetTextAngle(pcbnew.EDA_ANGLE((old_text_angle+turn*90)%180,pcbnew.DEGREES_T))
    text.SetKeepUpright(keep)
    if leaders:
        import cec_assembly_envelope as assembly
        from shapely.ops import nearest_points
        poly=pcbnew.SHAPE_POLY_SET()
        text.TransformShapeToPolygon(poly,text.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE,False)
        glyph=assembly.polygon_from_native(poly)
        native_court=_guide_polygon(fp,proof)
        rules=context['rules']
        gap=max(round(rules['silk_clearance']*1e6),board.GetDesignSettings().m_SilkClearance)
        _require(not native_court.intersects(glyph.buffer((gap+2000)/1e6)),
            'rotated_external_reference_must_remain_clear')
        a,z=nearest_points(native_court,glyph.envelope.buffer(
            (gap+text.GetTextThickness()/2+2000)/1e6,join_style=2))
        leaders[0].SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
        leaders[0].SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])))
    nodes=copy.deepcopy(proof['source_nodes'])
    def child(node,name):
        values=[v for v in node[1:]if isinstance(v,list)and v and v[0]==name]
        _require(len(values)==1,'one_literal_cardinal_coordinate_required')
        return values[0]
    def mm(value):return str(Decimal(int(value))/Decimal(1000000))
    def angle(at,value,always=False):
        _require(len(at)in(3,4),'literal_cardinal_angle_shape_required')
        at[3:]=[str(value)]if always or value else []
    for uid in proof['member_uuids']:
        node=nodes[uid];item=items[uid]
        if node[0]=='footprint':
            at=child(node,'at');at[1:3]=[mm(v)for v in fp.GetPosition()]
            if turn:
                value=fp.GetOrientationDegrees()%360
                angle(at,value-360 if value>180 else value)
                fields={force._uid(v):v for v in [*fp.GetFields(),*fp.GraphicalItems(),*fp.Pads()]}
                for sub in node[1:]:
                    if not isinstance(sub,list)or not sub or sub[0]not in('property','fp_text','pad'):continue
                    uuid=child(sub,'uuid')[1].strip('"');native=fields.get(uuid)
                    _require(native is not None,'same_source_cardinal_field_or_pad_required')
                    if sub[0]=='pad':angle(child(sub,'at'),native.GetOrientationDegrees()%360)
                    else:angle(child(sub,'at'),native.GetTextAngle().AsDegrees(),always=True)
        elif node[0]=='gr_text':
            at=child(node,'at');at[1:3]=[mm(v)for v in text.GetTextPos()]
            if turn:angle(at,text.GetTextAngle().AsDegrees())
        elif node[0]=='gr_line':
            child(node,'start')[1:3]=[mm(v)for v in item.GetStart()]
            child(node,'end')[1:3]=[mm(v)for v in item.GetEnd()]
        else:raise ValueError('unsupported_cardinal_source_map_member')
    all_nodes=dict(context['nodes']);all_nodes.update(nodes)
    _inspect_bound(Path(proof['source']),board,all_nodes,context['rules'],
        proof['source_sha256'],owner_uuid=proof['owner_uuid'],group_uuid=proof['group_uuid'],
        projection_geometry=_proof_projection(proof))
    _require(text.IsKeepUpright()==keep,'source_reference_upright_attribute_changed')
    return board,nodes


def expected_cardinal_nodes(proof,*,quarter_turns,delta_nm=(0,0),maximum_translation_mm=10.):
    """Exact Source-derived root AST; all unlisted lexemes stay authored."""
    return _cardinal_derive(proof,quarter_turns,delta_nm,maximum_translation_mm)[1]


def transform_cardinal(board,proof,*,quarter_turns,delta_nm=(0,0),maximum_translation_mm=10.):
    """Explicit single-map quarter turn. No caller pivot, flip or pose admission."""
    parent=pcbnew.LoadBoard(proof['source'])
    _require(_cardinal_identity(parent)==_cardinal_identity(board),'exact_cardinal_source_native_board_required')
    # Full native serialization also binds field-less local body geometry,
    # pad process overrides and project settings omitted by copper inventories.
    # This is native-to-native preflight, never normalization of saved Source.
    import tempfile
    import cec_field_coupling as field
    with tempfile.TemporaryDirectory(prefix='cec-cardinal-source-')as directory:
        roots=[]
        for index,native in enumerate((parent,board)):
            path=Path(directory)/(str(index)+'.kicad_pcb')
            field._save_field_snapshot(native,path);roots.append(syntax._freeze(ast._nodes(path)[0]))
        _require(roots[0]==roots[1],'exact_cardinal_source_native_serialization_required')
    expected,nodes=_cardinal_derive(proof,quarter_turns,delta_nm,maximum_translation_mm)
    # Reuse the source-derived native operations only after all validation has
    # succeeded on scratch. No partially rotated caller on a failed proposal.
    old={force._uid(i):i for i in [*board.GetFootprints(),*board.GetDrawings()]}
    new={force._uid(i):i for i in [*expected.GetFootprints(),*expected.GetDrawings()]}
    fp=old[proof['owner_uuid']];pivot=fp.GetPosition();turn=_quarter(quarter_turns)
    _rotate_cardinal_fp(fp,turn)
    fp.SetPosition(new[proof['owner_uuid']].GetPosition())
    for uid in proof['member_uuids']:
        item,target=old[uid],new[uid]
        if item.GetClass()=='PCB_SHAPE':item.SetStart(target.GetStart());item.SetEnd(target.GetEnd())
        elif item.GetClass()=='PCB_TEXT':
            item.SetTextPos(target.GetTextPos());item.SetTextAngle(target.GetTextAngle())
    _require(_cardinal_identity(board)==_cardinal_identity(expected),'native_cardinal_transport_differs')
    return dict(quarter_turns=turn,source_pivot_nm=list(pivot),
        transformed_member_uuids=proof['member_uuids'],pose_admitted=False,
        current_authority=False,release_authority=False)


def verify_cardinal(source,candidate,proof,*,quarter_turns,delta_nm=(0,0),maximum_translation_mm=10.):
    """Independent exact literal replay plus fresh native map recognition."""
    _require(Path(source).resolve()==Path(proof['source']),'same_cardinal_source_required')
    expected=expected_cardinal_nodes(proof,quarter_turns=quarter_turns,delta_nm=delta_nm,maximum_translation_mm=maximum_translation_mm)
    _,before=ast._nodes(source);_,after=ast._nodes(candidate)
    _require(before.keys()==after.keys()and all(syntax._freeze(after[u])==syntax._freeze(expected.get(u,n))
        for u,n in before.items()),'source_expected_cardinal_annotation_differs')
    _inspect_proof_source(proof,candidate)
    actual=pcbnew.LoadBoard(str(candidate));native,_=_cardinal_derive(proof,quarter_turns,delta_nm,maximum_translation_mm)
    _require(_cardinal_identity(actual)==_cardinal_identity(native),'saved_native_cardinal_annotation_differs')
    return dict(ok=True,complete=True,current_authority=False,pose_admitted=False,release_authority=False)
