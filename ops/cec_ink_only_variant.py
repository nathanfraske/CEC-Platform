"""PRIVATE matched schematic/board/library ink variants; never source admission.

Only independently templated symmetric nonpolar bodies or plain closed frames
are eligible. Source physical differences are not repaired or normalized here.
"""
import hashlib
import json
import math
import tempfile
import time
import uuid
from pathlib import Path

import pcbnew
from shapely.geometry import LineString
from shapely.ops import unary_union
import cec_rectangular_field_silk_clearance as frame
import cec_nonpolar_body_silk_clearance as nonpolar
import cec_force_current as force
import cec_field_coupling as field
import cec_copper_echo as syntax
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_footprint_children


def _need(ok, reason):
    if not ok:raise ValueError(reason)


def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))
def _digest(value):return hashlib.sha256(json.dumps(_stable(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _node(text):return syntax._parse(syntax._TOKEN.findall(text))
def _uid(node):
    return next((str(n[1]).strip('"')for n in node if isinstance(n,list)and n and n[0]=='uuid'),None)


def _edits(text, changes):
    for a,b,value in sorted(changes,reverse=True):text=text[:a]+value+text[b:]
    return text


def _symbol_edit(text, symbol_uuid, old, new):
    spans=raw.children(text);matches=[]
    for a,b in spans:
        part=text[a:b];node=_node(part)
        if node[0]!='symbol'or _uid(node)!=symbol_uuid:continue
        changes=[]
        for x,y in raw.children(part):
            item=_node(part[x:y])
            if item[:2]==['property','"Footprint"']:
                _need(len(item)>=3 and item[2]==json.dumps(old),'exact_source_symbol_footprint_required')
                # Replace only the authored string token, not property effects.
                token=json.dumps(old);start=part[x:y].find(token,part[x:y].find('"Footprint"')+11)
                _need(start>=0,'literal_source_footprint_token_required')
                changes.append((x+start,x+start+len(token),json.dumps(new)))
        _need(len(changes)==1,'one_source_symbol_footprint_property_required')
        matches.append((a,b,_edits(part,changes)))
    _need(len(matches)==1,'one_exact_top_level_source_symbol_required')
    return _edits(text,matches)


def _owned(board, fp, template_path, kind):
    _need(not fp.IsLocked()and not fp.IsDNP(),'unlocked_populated_source_owner_required')
    template=pcbnew.FootprintLoad(str(template_path.parent),template_path.stem)
    _need(template is not None and _matches(fp,template),
        'entire_source_body_and_physical_template_must_match')
    if kind=='nonpolar':
        bindings={};lines=nonpolar._body(fp,bindings)
        _need(str(template_path.resolve())in bindings,'actual_independent_vendored_nonpolar_template_required')
    elif kind=='rectangular_frame':
        _need(fp.GetOrientationDegrees()%90==0,'cardinal_source_frame_required')
        lines=frame._frame(fp)[0]
        # No additional silk text/markers may be inferred optional.
        _need(len([g for g in fp.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)])==4,
            'functional_or_extra_frame_artwork_refused')
    else:raise ValueError('positively_known_optional_body_kind_required')
    grouped={force._uid(i)for group in board.Groups()for i in group.GetItems()}
    _need(force._uid(fp)not in grouped and all(force._uid(g)not in grouped and not g.IsLocked()for g in lines),
        'grouped_or_locked_optional_ink_refused')
    return lines


def _matches(actual, template):
    """Forward-project independent art before exact native physical comparison.

    Native upright Fab text can acquire a literal 180-degree representation
    after a saved back-face flip. Compare the independently replayed SAME
    transform/save, rather than dropping or weakening the Fab/text subtree.
    """
    owner=pcbnew.BOARD();owner.SetCopperLayerCount(actual.GetBoard().GetCopperLayerCount());owner.Add(template)
    if actual.IsFlipped():template.Flip(pcbnew.VECTOR2I(0,0),False)
    template.SetOrientationDegrees(actual.GetOrientationDegrees());template.SetPosition(actual.GetPosition())
    with tempfile.TemporaryDirectory(prefix='cec-ink-source-pose-proof-')as work:
        path=Path(work)/'body.kicad_pcb';field._save_field_snapshot(owner,path)
        projected=pcbnew.LoadBoard(str(path));fp=next(iter(projected.GetFootprints()))
        return frame._semantic(actual)==frame._semantic(fp)


def _pieces(board, fp, lines, floors, deadline):
    material=frame.geometry.outline_material(board)
    from cec_assembly_envelope import polygon_from_native
    substrate=polygon_from_native(material)
    face=pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS
    openings=frame._mask_openings(board,face,'native_mask_and_bore')
    owned={force._uid(g)for g in lines}
    other_ink=[g for g in [*board.GetDrawings(),*(g for f in board.GetFootprints()for g in [*f.GraphicalItems(),*f.GetFields()])]
        if g.GetLayer()==face and force._uid(g)not in owned and(not hasattr(g,'IsVisible')or g.IsVisible())]
    _need(len(other_ink)<=16384,'bounded_source_native_ink_inventory_required')
    out=[]
    for g in lines:
        _need(time.monotonic()<deadline,'ink_variant_geometry_deadline')
        width=int(g.GetWidth());_need(width>=floors['stroke_nm'],'source_body_stroke_below_factory_floor')
        radius=(width+1)//2
        safe=substrate.buffer(-(radius+floors['edge_nm']+2000)/1e6,join_style=2)
        mask_polys=[p for _,p in openings]
        other_polys=[frame._poly(g,face)for g in other_ink]
        obstacles=[polygon_from_native(p).buffer((radius+floors['clearance_nm']+2000)/1e6,join_style=2)for p in [*mask_polys,*other_polys]]
        if obstacles:safe=safe.difference(unary_union(obstacles))
        a,b=tuple(g.GetStart()),tuple(g.GetEnd());line=LineString([(x/1e6,y/1e6)for x,y in(a,b)])
        clipped=line.intersection(safe);parts=[]
        def collect(p):
            if p.geom_type=='LineString'and p.length>0:parts.append(p)
            elif hasattr(p,'geoms'):
                for child in p.geoms:collect(child)
        collect(clipped)
        _need(parts and len(parts)<=8,'would_erase_body_stroke_or_exceed_piece_bound')
        pieces=[]
        for part in parts:
            p,q=[tuple(round(v*1e6)for v in xy)for xy in (part.coords[0],part.coords[-1])]
            _need(math.dist(p,q)>=max(width,250000),'unmanufacturable_body_ink_fragment')
            shape=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q),width)
            _need(frame.geometry.material_leg_clear(material,frame.geometry.material_boundaries(material),
                pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q),radius+floors['edge_nm']),
                'rounded_body_piece_fails_exact_native_edge')
            _need(not any(mask.Collide(shape,floors['clearance_nm'])for _,mask in openings),
                'rounded_body_piece_fails_exact_native_mask_or_bore')
            _need(not any(p.Collide(shape,floors['clearance_nm'])for p in other_polys),
                'rounded_body_piece_fails_exact_retained_source_ink')
            pieces.append([list(p),list(q)])
        pieces.sort();out.append(dict(graphic_uuid=force._uid(g),width_nm=width,layer=int(g.GetLayer()),
            old=[list(a),list(b)],pieces=pieces))
    return out


def _apply(board, records):
    fps={force._uid(f):f for f in board.GetFootprints()}
    for record in records:
        fp=fps[record['footprint_uuid']];live={force._uid(g):g for g in fp.GraphicalItems()}
        for row in record['ink']:
            original=live[row['graphic_uuid']]
            for index,(a,b)in enumerate(row['pieces']):
                g=original if index==0 else original.Duplicate()
                if index:
                    g.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
                        record['variant_fpid']+row['graphic_uuid']+str(index)))))
                    fp.Add(g)
                g.SetStart(pcbnew.VECTOR2I(*a));g.SetEnd(pcbnew.VECTOR2I(*b))
        alias,name=record['variant_fpid'].split(':',1);fp.SetFPID(pcbnew.LIB_ID(alias,name))
    return board


def _literal_board(source_text, native_text, records):
    native_spans=raw.children(native_text);native={_uid(_node(native_text[a:b])):native_text[a:b]for a,b in native_spans if _node(native_text[a:b])[0]=='footprint'}
    spans=raw.children(source_text);replacements=[]
    for record in records:
        hits=[(a,b)for a,b in spans if _node(source_text[a:b])[0]=='footprint'and _uid(_node(source_text[a:b]))==record['footprint_uuid']]
        _need(len(hits)==1,'unique_literal_source_footprint_required');a,b=hits[0];part=source_text[a:b];new=native[record['footprint_uuid']]
        source_lines={row['graphic_uuid']for row in record['ink']};allids=set(source_lines)
        allids.update(str(uuid.uuid5(uuid.NAMESPACE_URL,record['variant_fpid']+row['graphic_uuid']+str(i)))
            for row in record['ink']for i in range(1,len(row['pieces'])))
        segments=[]
        for x,y in raw.children(new):
            if _node(new[x:y])[0]=='fp_line'and _uid(_node(new[x:y]))in allids:segments.append(new[x:y])
        _need(len(segments)==sum(len(row['pieces'])for row in record['ink']),'complete_exact_generated_piece_inventory_required')
        cuts=[(x,y,'')for x,y in raw.children(part)if _node(part[x:y])[0]=='fp_line'and _uid(_node(part[x:y]))in source_lines]
        _need(len(cuts)==len(source_lines),'complete_literal_owned_stroke_inventory_required')
        part=_edits(part,cuts);old=json.dumps(record['old_fpid']);_need(part.startswith('(footprint '+old),'exact_literal_source_fpid_required')
        part=part.replace('(footprint '+old,'(footprint '+json.dumps(record['variant_fpid']),1)
        part=part[:part.rfind(')')]+'\n'+'\n'.join(segments)+'\n)'
        replacements.append((a,b,part))
    return _edits(source_text,replacements)


def plan(source, *, selections, board_hint, factory_legend_policy='jlcpcb', timeout_s=10.):
    _need(type(selections)is list and 1<=len(selections)<=8 and len({s['footprint_uuid']for s in selections})==len(selections),
        'bounded_unique_explicit_variant_owners_required')
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10 and type(board_hint)is str and board_hint,
        'bounded_explicit_variant_source_required')
    started=time.monotonic();source=Path(source).resolve(strict=True);board=pcbnew.LoadBoard(str(source));fps={force._uid(f):f for f in board.GetFootprints()}
    dependencies={str(Path(__file__).resolve()):force._hash(Path(__file__)),str(Path(frame.__file__).resolve()):force._hash(Path(frame.__file__)),str(Path(nonpolar.__file__).resolve()):force._hash(Path(nonpolar.__file__))}
    inputs={str(source):force._hash(source)};records=[];floors=frame._floors(board,source,factory_legend_policy)
    for selection in selections:
        uid=selection['footprint_uuid'];_need(uid in fps,'actual_selected_source_owner_required');fp=fps[uid]
        template=Path(selection['template_path']).resolve(strict=True)
        _need(template.is_relative_to((nonpolar.ROOT/'lib/vendor').resolve()),'independent_original_vendored_template_required')
        _need(template.stem==str(fp.GetFPID().GetLibItemName()),'selected_template_name_must_match_source_fpid')
        inputs[str(template)]=force._hash(template);lines=_owned(board,fp,template,selection['kind'])
        schematic=Path(selection['schematic_path']).resolve(strict=True);symbol_uuid=selection['symbol_uuid']
        path=fp.GetPath().AsString().rstrip('/').split('/')[-1]
        _need(path==symbol_uuid,'board_hierarchy_symbol_identity_must_match')
        inputs[str(schematic)]=force._hash(schematic);old=fp.GetFPIDAsString();_symbol_edit(schematic.read_text(),symbol_uuid,old,old)
        ink=_pieces(board,fp,lines,floors,started+timeout_s)
        token=_digest(dict(template=inputs[str(template)],kind=selection['kind'],ink=ink))[:24]
        variant='cec-private-ink:'+template.stem+'__ink_'+token
        records.append(dict(footprint_uuid=uid,old_fpid=old,variant_fpid=variant,template_path=str(template),
            schematic_path=str(schematic),symbol_uuid=symbol_uuid,kind=selection['kind'],ink=ink))
    _need(time.monotonic()<started+timeout_s,'ink_variant_source_deadline')
    return _stable(dict(schema=1,scope='PRIVATE_source_template_exact_optional_ink_variant',source=str(source),
        selections=selections,board_hint=board_hint,factory_legend_policy=factory_legend_policy,timeout_s=timeout_s,
        factory_floors=floors,records=records,input_sha256=inputs,dependency_sha256=dependencies,
        source_sidecar_sha256=force._sidecars(source),script_code_identity=force._code_identity(),
        canonical_source_changed=False,admitted=False,release_authority=False))


def construct_private(source, proposal, out):
    source=Path(source).resolve(strict=True);out=Path(out).resolve()
    fresh=plan(source,selections=proposal['selections'],board_hint=proposal['board_hint'],factory_legend_policy=proposal['factory_legend_policy'],timeout_s=proposal['timeout_s'])
    _need(fresh==proposal,'stale_or_forged_ink_variant_plan')
    _need(not out.exists()and source.parent not in out.parents,'fresh_disjoint_private_variant_directory_required')
    out.mkdir(parents=True);board=_apply(pcbnew.LoadBoard(str(source)),fresh['records'])
    with tempfile.TemporaryDirectory(prefix='cec-private-ink-native-')as work:
        saved=Path(work)/'board.kicad_pcb';field._save_field_snapshot(board,saved)
        candidate=out/'board.kicad_pcb';candidate.write_text(_literal_board(source.read_text(),saved.read_text(),fresh['records']))
    for suffix,digest in fresh['source_sidecar_sha256'].items():
        side=source.with_suffix(suffix)
        if digest is not None:candidate.with_suffix(suffix).write_bytes(side.read_bytes())
    pretty=out/'private-ink.pretty';pretty.mkdir();schematics={};templates=[]
    for record in fresh['records']:
        authority=Path(record['template_path']);template=pcbnew.PCB_IO_KICAD_SEXPR().FootprintLoad(str(authority.parent),authority.stem,True)
        owner=pcbnew.BOARD();owner.SetCopperLayerCount(6);owner.Add(template)
        # Transform the independent template to the actual source frame first.
        old=next(f for f in board.GetFootprints()if force._uid(f)==record['footprint_uuid'])
        if old.IsFlipped():template.Flip(pcbnew.VECTOR2I(0,0),False)
        template.SetOrientationDegrees(old.GetOrientationDegrees());template.SetPosition(old.GetPosition())
        signatures={frame._line(g):g for g in template.GraphicalItems()if g.GetClass()=='PCB_SHAPE'and g.GetShape()==pcbnew.SHAPE_T_SEGMENT}
        for row in record['ink']:
            signature=(row['layer'],row['width_nm'],tuple(row['old'][0]),tuple(row['old'][1]))
            matches=[g for sig,g in signatures.items()if sig==signature or sig==(signature[0],signature[1],signature[3],signature[2])]
            _need(len(matches)==1,'independent_original_template_stroke_required');g=matches[0]
            for index,(a,b)in enumerate(row['pieces']):
                item=g if index==0 else g.Duplicate()
                if index:
                    item.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
                        record['variant_fpid']+force._uid(g)+str(index)))))
                    template.Add(item)
                item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b))
        normal_owner,normal=frame._normal(template);name=record['variant_fpid'].split(':',1)[1];normal.SetFPID(pcbnew.LIB_ID('cec-private-ink',name))
        pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(pretty),normal)
        target=pretty/(name+'.kicad_mod');native_template=target.read_text();original_template=authority.read_text()
        def silk_line(text):
            n=_node(text)
            return n[0]=='fp_line'and any(isinstance(c,list)and c[:1]==['layer']and c[1]in('"F.SilkS"','"B.SilkS"')for c in n)
        additions=[native_template[a:b]for a,b in raw.children(native_template)if silk_line(native_template[a:b])]
        removals=[(a,b,'')for a,b in raw.children(original_template)if silk_line(original_template[a:b])]
        _need(len(removals)==len(record['ink'])and len(additions)==sum(len(r['pieces'])for r in record['ink']),
            'independent_template_optional_strokes_only_required')
        exact=_edits(original_template,removals)
        _need(exact.startswith('(footprint '+json.dumps(authority.stem)),'exact_original_template_name_required')
        exact=exact.replace('(footprint '+json.dumps(authority.stem),'(footprint '+json.dumps(name),1)
        exact=exact[:exact.rfind(')')]+'\n'+'\n'.join(additions)+'\n)\n'
        target.write_text(exact);templates.append(str(target))
        sch=record['schematic_path'];schematics[sch]=_symbol_edit(schematics.get(sch,Path(sch).read_text()),record['symbol_uuid'],record['old_fpid'],record['variant_fpid'])
    source_tree=out/'schematic-copies';source_tree.mkdir()
    _need(len({Path(p).name for p in schematics})==len(schematics),'schematic_basename_collision_refused')
    for path,text in schematics.items():(source_tree/Path(path).name).write_text(text)
    (out/'fp-lib-table').write_text('(fp_lib_table\n (lib (name "cec-private-ink") (type "KiCad") (uri "${KIPRJMOD}/private-ink.pretty") (options "") (descr "PRIVATE ink-only proposal; not source ECO admission"))\n)')
    # A partial table is explicitly not a runnable suite replacement.
    report=dict(candidate=str(candidate),private_templates=templates,private_schematic_copies=[str(source_tree/Path(p).name)for p in schematics],
        source_schematic_hierarchy_not_republished=True,private_table_contains_only_new_alias=True,
        canonical_source_changed=False,admitted=False,release_authority=False)
    force._write(out/'proposal.json',fresh);force._write(out/'artifact.json',report);return report


def receive(source, candidate, proposal, *, timeout_s=10.):
    result=dict(ok=False,complete=False,admitted=False,release_authority=False)
    try:
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_private_ink_receive_required')
        started=time.monotonic();candidate=Path(candidate).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix='cec-ink-independent-replay-')as work:
            expected=construct_private(source,proposal,Path(work)/'expected');root=Path(expected['candidate']).parent
            expected_files={p.relative_to(root):p.read_bytes()for p in root.rglob('*')if p.is_file()}
            actual_files={p.relative_to(candidate.parent):p.read_bytes()for p in candidate.parent.rglob('*')if p.is_file()}
            # Receipt paths are output metadata; geometry and all other bytes exact.
            for name in ('artifact.json',):
                expected_meta=json.loads(expected_files.pop(Path(name)))
                actual_meta=json.loads(actual_files.pop(Path(name),b'{}'))
                for key in ('candidate','private_templates','private_schematic_copies'):
                    expected_meta.pop(key);actual_meta.pop(key,None)
                _need(expected_meta==actual_meta,'private_artifact_qualification_metadata_changed')
            different=sorted(str(p)for p in expected_files.keys()|actual_files.keys()if expected_files.get(p)!=actual_files.get(p))
            if different:
                import difflib
                name=Path(different[0]);result['first_literal_difference']=list(difflib.unified_diff(expected_files.get(name,b'').decode().splitlines(),actual_files.get(name,b'').decode().splitlines()))[:16]
            _need(not different,'private_ink_transaction_differs_from_exact_source_replay:'+','.join(different))
            child=pcbnew.LoadBoard(str(candidate))
            for record in proposal['records']:
                fp=next(f for f in child.GetFootprints()if force._uid(f)==record['footprint_uuid'])
                name=record['variant_fpid'].split(':',1)[1];template=pcbnew.FootprintLoad(str(candidate.parent/'private-ink.pretty'),name)
                _need(_matches(fp,template),'saved_private_variant_body_must_match_independent_derivative')
            first=Path(work)/'first.kicad_pcb';second=Path(work)/'second.kicad_pcb'
            field._save_field_snapshot(child,first);field._save_field_snapshot(pcbnew.LoadBoard(str(first)),second)
            _need(syntax._freeze(frame.additive._nodes(first)[0])==syntax._freeze(frame.additive._nodes(second)[0]),'private_ink_second_native_save_unstable')
        _need(time.monotonic()-started<timeout_s,'private_ink_receiving_deadline')
        result.update(ok=True,complete=True,scope_only=True,whole_source_eco_native_parity_current_field_ground_receiving_still_required=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,StopIteration)as exc:result['error']=str(exc)
    return result
