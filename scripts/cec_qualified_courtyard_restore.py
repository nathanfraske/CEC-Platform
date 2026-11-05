"""Restore only missing courtyards from reviewed, exact-package contracts.

No body is inferred from copper alone. The reviewed contract binds a literal
manufacturer drawing, template, exact native local pad pattern and part IDs.
Every saved edit is stripped and independently compared with a native no-op
Source snapshot. Pads, copper, fills, fields, poses, models and rules cannot
change. Assembly/DRC/current/Kelvin/stack/release receiving remains required.
"""
import copy,hashlib,json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_source_retaining_ses_import as literal
from cec_native_items import create_empty_board

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'lib/vendor-data/footprint-courtyards/index.json'
COURTS={int(pcbnew.F_CrtYd),int(pcbnew.B_CrtYd)}


def _hash_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _owned_copy(original):
    # Native FOOTPRINT::Flip consults its parent board. A library footprint
    # or detached copy has no safe parent; keep the scratch owner alive for
    # the entire transform instead of invoking the native API on an orphan.
    owner=create_empty_board();owner.SetCopperLayerCount(6)
    fp=pcbnew.FOOTPRINT(original);owner.Add(fp)
    return owner,fp


def lands(original):
    """Exact net-independent local native land pattern, normalized by KiCad."""
    scratch,fp=_owned_copy(original);fp.SetPosition(pcbnew.VECTOR2I(0,0))
    if fp.IsFlipped():fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(0);rows=[]
    for p in fp.Pads():
        if (p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or tuple(p.GetOffset())!=(0,0)
                or p.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                    pcbnew.PAD_SHAPE_OVAL,pcbnew.PAD_SHAPE_CIRCLE)):
            raise ValueError('qualified_courtyard_requires_supported_actual_surface_lands')
        rows.append(dict(number=p.GetNumber(),at_nm=list(p.GetFPRelativePosition()),size_nm=list(p.GetSize()),
            drill_nm=list(p.GetDrillSize()),offset_nm=list(p.GetOffset()),shape=int(p.GetShape()),
            attribute=int(p.GetAttribute()),angle_microdegrees=round((p.GetOrientationDegrees()%180)*1e6),
            layers=list(map(int,p.GetLayerSet().Seq()))))
    if not 1<=len(rows)<=512:raise ValueError('qualified_courtyard_land_count_bound')
    rows.sort(key=lambda q:json.dumps(q,sort_keys=True));return rows,_hash_json(rows)


def _file(value):
    path=Path(value);return (path if path.is_absolute() else ROOT/path).resolve()


def _read(path,bindings):
    path=Path(path).resolve();bindings[str(path)]=force._hash(path)
    return json.loads(path.read_text())


def _contour(fp):
    face=pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
    fp.BuildCourtyardCaches();poly=fp.GetCourtyard(face)
    if poly.OutlineCount()!=1 or poly.HoleCount(0):raise ValueError('one_exact_qualified_native_courtyard_required')
    graphics=[g for g in fp.GraphicalItems() if int(g.GetLayer()) in COURTS]
    # The DRC cache is intentionally inset relative to authored line centres.
    # It proves closure, not the physical envelope to copy or qualify.
    if len(graphics)==1 and graphics[0].GetShape()==pcbnew.SHAPE_T_RECT:
        if fp.GetOrientationDegrees()%90:raise ValueError('qualified_rectangular_source_must_be_cardinal')
        a,z=map(tuple,(graphics[0].GetStart(),graphics[0].GetEnd()))
        left,right=sorted((a[0],z[0]));top,bottom=sorted((a[1],z[1]))
        points=[(left,top),(left,bottom),(right,bottom),(right,top)]
    elif len(graphics)==4 and all(g.GetShape()==pcbnew.SHAPE_T_SEGMENT for g in graphics):
        adjacency={}
        for g in graphics:
            a,z=tuple(g.GetStart()),tuple(g.GetEnd())
            if a==z:raise ValueError('nonzero_authored_courtyard_edges_required')
            adjacency.setdefault(a,set()).add(z);adjacency.setdefault(z,set()).add(a)
        if len(adjacency)!=4 or any(len(v)!=2 for v in adjacency.values()):
            raise ValueError('single_closed_authored_courtyard_required')
        points=[min(adjacency)];previous=None
        for _ in range(3):
            following=min(p for p in adjacency[points[-1]] if p!=previous)
            previous=points[-1];points.append(following)
        if len(set(points))!=4 or points[0] not in adjacency[points[-1]]:
            raise ValueError('single_closed_authored_courtyard_required')
    else:raise ValueError('qualified_rectangular_authored_courtyard_required')
    return min(tuple(p[i:]+p[:i]) for p in (points,points[::-1]) for i in range(4))


def _add_lines(fp,points,layer):
    made=[]
    for start,end in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(layer)
        line.SetWidth(50000);line.SetStart(pcbnew.VECTOR2I(*start));line.SetEnd(pcbnew.VECTOR2I(*end));fp.Add(line)
        made.append(line)
    return made


def _load(contract_id):
    if type(contract_id) is not str or not contract_id:raise ValueError('literal_qualified_courtyard_contract_id_required')
    bindings={};index=_read(INDEX,bindings)
    if (set(index)!={'schema','contracts'} or type(index['schema']) is not int or index['schema']!=1
            or type(index['contracts']) is not dict or not 1<=len(index['contracts'])<=256):
        raise ValueError('reviewed_courtyard_contract_registry_required')
    entry=index['contracts'].get(contract_id)
    if type(entry) is not dict or set(entry)!={'path','sha256'}:
        raise ValueError('reviewed_courtyard_contract_not_registered')
    path=_file(entry['path'])
    if force._hash(path)!=entry['sha256']:raise ValueError('qualified_courtyard_contract_changed')
    data=_read(path,bindings)
    if (type(data.get('schema')) is not int or data['schema']!=1
            or data.get('scope')!='reviewed_manufacturer_bounded_missing_courtyard_only'):
        raise ValueError('courtyard_only_manufacturer_qualification_required')
    for key in ('footprint_ids','part_values'):
        rows=data.get(key)
        if type(rows) is not list or not 1<=len(rows)<=16 or len(set(rows))!=len(rows) or any(type(x) is not str or not x for x in rows):
            raise ValueError('literal_bounded_courtyard_package_identity_required')
    bounds=data.get('body_max_bounds_nm');gap=data.get('courtyard_clearance_nm');grid=data.get('courtyard_grid_nm')
    if (type(bounds) is not list or len(bounds)!=4 or any(type(v) is not int or abs(v)>100000000 for v in bounds)
            or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]
            or type(gap) is not int or not 250000<=gap<=2000000
            or type(grid) is not int or not 1<=grid<=10000 or 10000%grid
            or data.get('courtyard_stroke_nm')!=50000 or type(data.get('courtyard_stroke_nm')) is not int):
        raise ValueError('bounded_positive_manufacturer_body_and_courtyard_policy_required')
    evidence=data.get('evidence')
    if type(evidence) is not list or not 1<=len(evidence)<=8:raise ValueError('manufacturer_courtyard_evidence_required')
    for item in evidence:
        if type(item) is not dict or not item.get('pages') or not item.get('url'):
            raise ValueError('manufacturer_drawing_identity_required')
        evidence_path=_file(item['path'])
        if force._hash(evidence_path)!=item['sha256']:raise ValueError('manufacturer_courtyard_evidence_changed')
        bindings[str(evidence_path)]=item['sha256']
    spec=data['template'];template_path=_file(spec['path'])
    if force._hash(template_path)!=spec['sha256']:raise ValueError('qualified_courtyard_template_changed')
    bindings[str(template_path)]=spec['sha256']
    template=pcbnew.FootprintLoad(str(template_path.parent),template_path.stem)
    if template is None or lands(template)[1]!=spec['pad_geometry_sha256']:
        raise ValueError('qualified_courtyard_template_land_pattern_changed')
    template.SetPosition(pcbnew.VECTOR2I(0,0));template.SetOrientationDegrees(0)
    # BOX2I's inclusive integer raster bound may contain an extra nm. It is
    # not the physical pad edge and must not grow a courtyard by a whole grid
    # cell. Use exact half-nm extents of supported cardinal native lands;
    # unsupported template geometry is refused, never approximated inward.
    pad_bounds=[]
    for p in lands(template)[0]:
        angle=p['angle_microdegrees']
        if angle not in (0,90000000):raise ValueError('qualified_template_cardinal_land_geometry_required')
        width,height=p['size_nm'] if angle==0 else p['size_nm'][::-1]
        x,y=p['at_nm'];pad_bounds.append((x-width/2,y-height/2,x+width/2,y+height/2))
    actual=[min(bounds[0],min(b[0] for b in pad_bounds)),min(bounds[1],min(b[1] for b in pad_bounds)),
        max(bounds[2],max(b[2] for b in pad_bounds)),max(bounds[3],max(b[3] for b in pad_bounds))]
    expected=[math.floor((actual[i]-gap)/grid)*grid if i<2 else math.ceil((actual[i]+gap)/grid)*grid for i in range(4)]
    target=sorted((x,y) for x in (expected[0],expected[2]) for y in (expected[1],expected[3]))
    if sorted(_contour(template))!=target:
        raise ValueError('qualified_template_courtyard_not_full_body_and_lands_plus_margin:'+repr((target,sorted(_contour(template)),actual)))
    graphics=[g for g in template.GraphicalItems() if int(g.GetLayer()) in COURTS]
    if not graphics or any(g.GetWidth()!=50000 or g.GetLayer()!=pcbnew.F_CrtYd for g in graphics):
        raise ValueError('qualified_template_courtyard_stroke_or_surface_changed')
    # Explicit segments preserve the authored geometry through arbitrary
    # native footprint rotations, without borrowing the inset DRC cache.
    points=list(_contour(template))
    for g in graphics:template.Remove(g)
    _add_lines(template,points,pcbnew.F_CrtYd)
    if _contour(template)!=tuple(points):raise ValueError('qualified_template_authored_courtyard_replay_changed')
    return data,template,bindings,expected


def plan(source,*,contract_id,board_hint,timeout_s=10.,max_footprints=32,literal_source=False):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(max_footprints) is not int or not 1<=max_footprints<=64
            or type(board_hint) is not str or not board_hint or type(literal_source) is not bool):
        raise ValueError('bounded_qualified_courtyard_restoration_required')
    started=time.monotonic();data,template,bindings,bounds=_load(contract_id)
    source=Path(source).resolve();family=force._family(source,board_hint);epoch=force._code_identity()
    b=pcbnew.LoadBoard(str(source));records=[];seen=[]
    for fp in b.GetFootprints():
        if time.monotonic()-started>=timeout_s:raise ValueError('qualified_courtyard_source_inventory_deadline')
        identity=str(fp.GetFPID().GetLibNickname())+':'+str(fp.GetFPID().GetLibItemName())
        if identity not in data['footprint_ids']:continue
        existing=[g for g in fp.GraphicalItems() if int(g.GetLayer()) in COURTS]
        if existing:
            fp.BuildCourtyardCaches();poly=fp.GetCourtyard(pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu)
            if poly.OutlineCount()!=1 or poly.HoleCount(0):raise ValueError('existing_partial_courtyard_must_not_be_overwritten')
            continue  # Never replace a user's existing valid courtyard.
        if fp.GetValue() not in data['part_values'] or lands(fp)[1]!=data['template']['pad_geometry_sha256']:
            raise ValueError('source_package_identity_or_complete_native_land_pattern_unqualified')
        scratch,posed=_owned_copy(template)
        if fp.IsFlipped():posed.Flip(pcbnew.VECTOR2I(0,0),False)
        posed.SetOrientationDegrees(fp.GetOrientationDegrees());posed.SetPosition(fp.GetPosition())
        points=_contour(posed)
        records.append(dict(footprint_uuid=force._uid(fp),reference=fp.GetReference(),part_value=fp.GetValue(),
            footprint_id=identity,source_pose=[*fp.GetPosition(),fp.GetOrientationDegrees()],
            flipped=fp.IsFlipped(),world_points_nm=[list(p) for p in points],
            courtyard_layer=int(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)))
        seen.append(force._uid(fp))
        if len(records)>max_footprints:raise ValueError('qualified_courtyard_restoration_count_bound')
    if len(set(seen))!=len(seen):raise ValueError('qualified_courtyard_ambiguous_source_footprint')
    if family!=force._family(source,board_hint) or epoch!=force._code_identity() or any(force._hash(Path(p))!=h for p,h in bindings.items()):
        raise ValueError('qualified_courtyard_source_contract_or_code_changed')
    result=dict(schema=1,scope='source_exact_missing_manufacturer_courtyard_restoration',
        source=str(source),source_sha256=force._hash(source),contract_id=contract_id,board_hint=board_hint,
        code_identity=epoch,input_sha256=bindings,records=records,template_local_bounds_nm=bounds,
        request=dict(timeout_s=timeout_s,max_footprints=max_footprints),
        no_copper_or_component_pose_authority=True,routing_admitted=False,fab_ready=False,release_authority=False)
    if literal_source:
        result.update(literal_source=True,source_family=family)
        result['request']['literal_source']=True
    return result


def construct(source,proposal):
    fresh=plan(source,contract_id=proposal['contract_id'],board_hint=proposal['board_hint'],**proposal['request'])
    if fresh!=proposal:raise ValueError('stale_or_forged_manufacturer_courtyard_source_plan')
    board=pcbnew.LoadBoard(str(source));owners={force._uid(fp):fp for fp in board.GetFootprints()}
    for row in proposal['records']:
        fp=owners[row['footprint_uuid']];points=row['world_points_nm']
        _add_lines(fp,points,row['courtyard_layer'])
        if _contour(fp)!=tuple(map(tuple,points)):raise ValueError('constructed_native_courtyard_differs_from_reviewed_template')
    return board


def _uid(node):
    values=[q[1].strip('"') for q in node[1:] if isinstance(q,list) and len(q)==2 and q[0]=='uuid']
    return values[0] if len(values)==1 else None


def _append_literal(source_text,child_text,proposal,incoming=None):
    """Compose only independently validated fresh fp_line nodes into Source."""
    old,new=literal.inventory(source_text),literal.inventory(child_text);result=source_text
    for row in sorted(proposal['records'],key=lambda r:old[r['footprint_uuid']][0],reverse=True):
        uid=row['footprint_uuid'];a,z=old[uid];x,y=new[uid]
        before=source_text[a:z];after=child_text[x:y]
        source_ids={literal.node_uuid(before[i:j])for i,j in literal.children(before)}
        additions=[after[i:j]for i,j in literal.children(after)if literal.kind(after[i:j])=='fp_line'
            and literal.node_uuid(after[i:j])not in source_ids]
        if len(additions)!=4 or (incoming is not None and
                not {literal.node_uuid(q)for q in additions}<=set(incoming)):
            raise ValueError('exact_four_validated_fresh_courtyard_edges_required')
        at=literal.children(before,root_end=True)
        replacement=before[:at]+'\n'+'\n'.join(additions)+'\n'+before[at:]
        result=result[:a]+replacement+result[z:]
    return result


def _literal_ids(text):
    found=[]
    def visit(node):
        if not isinstance(node,list):return
        if node and node[0]=='uuid':
            if len(node)!=2:raise ValueError('one_literal_courtyard_uuid_required')
            found.append(node[1].strip('"'))
        for child in node:visit(child)
    visit(syntax._parse(syntax._TOKEN.findall(text)))
    if len(found)!=len(set(found)):raise ValueError('unique_literal_courtyard_source_and_child_uuids_required')
    return set(found)


def _native_literal_replay(parent,child,incoming,tmp):
    """Normalize each ACTUAL board independently, twice; strip only new IDs."""
    for generation in range(2):
        paths=[Path(tmp)/('%s-%d.kicad_pcb'%(label,generation))for label in ('source','child')]
        for board,path in zip((parent,child),paths):field._save_field_snapshot(board,path)
        source_root,_=additive._nodes(paths[0]);child_root,_=additive._nodes(paths[1])
        stripped=copy.deepcopy(child_root);removed=[]
        for node in stripped[1:]:
            if not isinstance(node,list)or not node or node[0]!='footprint':continue
            for q in list(node[1:]):
                if isinstance(q,list)and _uid(q)in incoming:
                    if q[0]!='fp_line':raise ValueError('native_fresh_courtyard_node_type_changed')
                    removed.append(_uid(q));node.remove(q)
        if sorted(removed)!=sorted(incoming) or syntax._freeze(source_root)!=syntax._freeze(stripped):
            raise ValueError('courtyard_edit_changed_independently_normalized_source_evidence')
        parent,child=[pcbnew.LoadBoard(str(p))for p in paths]


def write_private(source,candidate,proposal,*,timeout_s=10.):
    """Opt-in exact literal Source + reviewed four edges; PCB written LAST."""
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_literal_courtyard_write_required')
    started=time.monotonic();source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
    if proposal.get('literal_source')is not True:raise ValueError('explicit_literal_source_courtyard_plan_required')
    if (candidate.suffix!='.kicad_pcb' or candidate.exists() or candidate.parent==source.parent
            or candidate.parent.is_relative_to(source.parent)):
        raise ValueError('fresh_disjoint_private_courtyard_family_required')
    board=construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-literal-courtyard-write-')as tmp:
        snap=Path(tmp)/'constructed.kicad_pcb';field._save_field_snapshot(board,snap)
        text=_append_literal(literal.raw_text(source),literal.raw_text(snap),proposal)
    companions=force._sidecars(source);candidate.parent.mkdir(parents=True,exist_ok=False)
    owned={};remaining=force.MAX_SAVED_FAMILY_BYTES
    try:
        for suffix,digest in companions.items():
            if digest is not None:
                target=candidate.with_suffix(suffix)
                remaining-=force._copy_family_file(source.with_suffix(suffix),target,remaining);owned[target]=digest
        if len(text.encode())>remaining or time.monotonic()-started>=timeout_s:
            raise ValueError('literal_courtyard_write_storage_or_deadline')
        with candidate.open('x',newline='')as stream:stream.write(text)
        owned[candidate]=hashlib.sha256(text.encode()).hexdigest()
        proof=receive(source,candidate,proposal,board_hint=proposal['board_hint'],
            timeout_s=max(.001,timeout_s-(time.monotonic()-started)),literal_source=True)
        if not proof['ok']or time.monotonic()-started>=timeout_s:
            raise ValueError('literal_courtyard_private_receiving_refused:'+repr(proof['errors']))
        return candidate
    except BaseException:
        for path,digest in reversed(list(owned.items())):
            if path.is_file()and force._hash(path)==digest:path.unlink()
        try:candidate.parent.rmdir()
        except OSError:pass
        raise


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.,literal_source=False):
    r=dict(ok=False,complete=False,errors=[],no_copper_or_component_pose_authority=True,
        full_placement_native_DRC_current_Kelvin_stack_and_release_receiving_still_required=True,
        routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
                or type(literal_source)is not bool or literal_source!=proposal.get('literal_source',False)):
            raise ValueError('bounded_saved_courtyard_receiving_required')
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        if source==candidate or board_hint!=proposal['board_hint']:raise ValueError('distinct_exact_courtyard_source_candidate_required')
        started=time.monotonic();epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,contract_id=proposal['contract_id'],board_hint=board_hint,**proposal['request'])
        if fresh!=proposal:raise ValueError('saved_courtyard_source_contract_or_plan_changed')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        owners={force._uid(fp):fp for fp in child.GetFootprints()};root,nodes=additive._nodes(candidate)
        stripped=copy.deepcopy(root);strip_nodes={_uid(q):q for q in stripped[1:] if isinstance(q,list) and _uid(q)}
        original_ids={force._uid(i) for i in [*parent.GetTracks(),*parent.Zones(),*parent.Groups(),*parent.GetDrawings(),
            *parent.GetFootprints(),*(p for f in parent.GetFootprints() for p in f.Pads()),
            *(g for f in parent.GetFootprints() for g in [*f.GraphicalItems(),*f.GetFields()])]}
        incoming=[]
        if literal_source:
            original_ids|=_literal_ids(literal.raw_text(source));_literal_ids(literal.raw_text(candidate))
        for row in fresh['records']:
            fp=owners[row['footprint_uuid']]
            graphics=[g for g in fp.GraphicalItems() if int(g.GetLayer()) in COURTS]
            if (len(graphics)!=4 or any(g.GetClass()!='PCB_SHAPE' or g.GetShape()!=pcbnew.SHAPE_T_SEGMENT
                    or g.GetWidth()!=50000 or int(g.GetLayer())!=row['courtyard_layer'] for g in graphics)
                    or _contour(fp)!=tuple(map(tuple,row['world_points_nm']))):
                raise ValueError('saved_courtyard_not_exact_reviewed_native_envelope')
            ids={force._uid(g) for g in graphics}
            if len(ids)!=4 or ids&original_ids or ids&set(incoming):raise ValueError('new_courtyard_graphic_identity_required')
            incoming.extend(sorted(ids));node=strip_nodes[row['footprint_uuid']]
            removed=[q for q in node[1:] if isinstance(q,list) and _uid(q) in ids]
            if len(removed)!=4 or any(q[0]!='fp_line' for q in removed):raise ValueError('literal_added_courtyard_lines_required')
            for q in removed:
                tags={v[0] for v in q[1:] if isinstance(v,list) and v}
                if tags!={'start','end','stroke','layer','uuid'}:
                    raise ValueError('courtyard_only_graphic_has_unowned_properties')
                if literal_source and len(q)!=6:raise ValueError('exact_single_literal_courtyard_properties_required')
                strokes=[v for v in q[1:] if isinstance(v,list) and v and v[0]=='stroke']
                if len(strokes)!=1:raise ValueError('exact_courtyard_stroke_required')
                settings={v[0]:v[1:] for v in strokes[0][1:] if isinstance(v,list) and v}
                if (set(settings)!={'width','type'} or settings['type'] not in (['default'],['solid'])
                        or len(strokes[0])!=3):
                    raise ValueError('solid_unmodified_courtyard_stroke_required')
            node[:]=[q for q in node if not (isinstance(q,list) and _uid(q) in ids)]
        with tempfile.TemporaryDirectory(prefix='cec-exact-courtyard-') as tmp:
            if literal_source:
                expected=_append_literal(literal.raw_text(source),literal.raw_text(candidate),fresh,incoming)
                if expected!=literal.raw_text(candidate):raise ValueError('courtyard_edit_changed_other_literal_source_bytes')
                _native_literal_replay(parent,child,incoming,tmp)
            else:
                expected=Path(tmp)/'source-noop.kicad_pcb';field._save_field_snapshot(parent,expected)
                want,_=additive._nodes(expected)
                if syntax._freeze(want)!=syntax._freeze(stripped):raise ValueError('courtyard_edit_changed_other_native_source_evidence')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('courtyard_edit_changed_source_family_rules')
        if (time.monotonic()-started>timeout_s or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]
                or any(force._hash(Path(p))!=h for p,h in fresh['input_sha256'].items())):
            raise ValueError('saved_courtyard_family_code_or_work_bound_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            changed=bool(fresh['records']),modified_footprint_uuids=[q['footprint_uuid'] for q in fresh['records']],
            added_courtyard_graphic_uuids=incoming,source_family_and_code_unchanged=True,
            all_original_copper_pads_fills_fields_poses_models_and_rules_exact=True,
            independent_native_noop_source_replay_matched=True)
        if literal_source:r.update(exact_whole_literal_source_plus_courtyard_only=True,
            independent_actual_source_child_native_replays=2,literal_source=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
