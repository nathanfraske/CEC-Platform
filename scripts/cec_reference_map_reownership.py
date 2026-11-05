"""Re-own one exact simple opposite-face map without changing printed art.

Only a bounded exact closed courtyard projection and its one reference glyph
(plus the independently proven nearest leader when external) may become root
annotations. Exact eight-arm rectangular source-producer brackets may also be
reowned after independent recognition, never as closed assembly-body authority.
Arbitrary artwork is not authorized.
No text disappears, no part or
manufacturer graphic is refreshed, and no library is modified. This scoped
literal/physical receipt is NOT native DRC or whole-board admission.
"""
import copy
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

import pcbnew
import cec_additive_route_receiving as ast
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_library_context as libraries
import cec_source_literal_additions as literal
import cec_source_reference_group_transport as transport
from cec_source_retaining_ses_import import children, kind

ROOT = Path(__file__).resolve().parents[1]


def _require(value, reason):
    if not value: raise ValueError(reason)


def _stable(value): return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
def _hash(value): return hashlib.sha256(json.dumps(_stable(value), sort_keys=True).encode()).hexdigest()
def _uid(node):
    rows = [x for x in node if isinstance(x,list) and x and x[0] == 'uuid']
    _require(len(rows) == 1 and len(rows[0]) == 2, 'one_literal_native_uuid_required')
    return rows[0][1].strip('"')


def _unique_uuids(text):
    """Include footprint children, not merely top-level object IDs."""
    tree=syntax._parse(syntax._TOKEN.findall(text));seen=set();todo=[tree]
    while todo:
        node=todo.pop()
        if not isinstance(node,list):continue
        if node and node[0]=='uuid':
            _require(len(node)==2 and node[1].strip('"') not in seen,'unique_literal_source_uuids_required')
            seen.add(node[1].strip('"'))
        todo.extend(v for v in node if isinstance(v,list))
    return seen


def _epoch(source, table):
    return _stable(dict(family=force._family(source), code=force._code_identity(),
        library=libraries.authority(source,table),
        environment={k:v for k,v in os.environ.items() if k.startswith('CEC_')}))


def _mm(value): return format(Decimal(int(value))/1000000, 'f')


def _replace_child(text, name, replacement):
    spans = [(a,b) for a,b in children(text) if kind(text[a:b]) == name]
    _require(len(spans) == 1, 'one_literal_annotation_'+name+'_required')
    a,b = spans[0]; return text[:a]+replacement+text[b:]


def _root_annotation(text, item):
    if kind(text) == 'fp_line':
        _require(item.GetClass() == 'PCB_SHAPE' and item.GetShape() == pcbnew.SHAPE_T_SEGMENT,
            'literal_straight_map_stroke_required')
        out = text.replace('(fp_line', '(gr_line', 1)
        for name,point in [('start',item.GetStart()),('end',item.GetEnd())]:
            out = _replace_child(out,name,'('+name+' '+_mm(point.x)+' '+_mm(point.y)+')')
        return out
    _require(kind(text) == 'fp_text' and item.GetClass() == 'PCB_TEXT', 'literal_map_text_required')
    # Keep the source string and every font/justify/lock/UUID lexeme. Only its
    # parent-dependent coordinates and root grammar change.
    first = children(text)[0][0]
    head = literal._atoms(text[1:first])
    _require(len(head) == 3 and head[1][0] == 'user', 'one_literal_user_reference_required')
    out = '(gr_text '+head[2][1]+text[first:]
    p = item.GetPosition(); angle = str(item.GetTextAngle().AsDegrees())
    return _replace_child(out,'at','(at '+_mm(p.x)+' '+_mm(p.y)+' '+angle+')')


def _geometry(item):
    if item.GetClass() == 'PCB_TEXT':
        p=pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(p,item.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE,False)
        polygons=[]
        for i in range(p.OutlineCount()):
            chain=p.COutline(i)
            holes=[]
            for h in range(p.HoleCount(i)):
                hole=p.Hole(i,h)
                holes.append([(hole.CPoint(j).x,hole.CPoint(j).y) for j in range(hole.PointCount())])
            polygons.append(dict(outline=[(chain.CPoint(j).x,chain.CPoint(j).y) for j in range(chain.PointCount())],holes=holes))
        return _stable(dict(kind='text',text=item.GetText(),layer=int(item.GetLayer()),
            position=list(item.GetPosition()),angle=item.GetTextAngle().AsDegrees(),
            size=list(item.GetTextSize()),stroke=item.GetTextThickness(),mirrored=item.IsMirrored(),
            visible=item.IsVisible(),locked=item.IsLocked(),polygons=polygons))
    return _stable(dict(kind='line',layer=int(item.GetLayer()),start=list(item.GetStart()),
        end=list(item.GetEnd()),width=item.GetWidth(),locked=item.IsLocked(),
        shape=int(item.GetShape()),filled=item.IsAnyFill()))


_BODY_INSTANCE_FIELDS=frozenset({'at','layer','uuid','tstamp','property','path',
    'sheetname','sheetfile','version','generator','generator_version'})


def _body_tree_key(node, excluded):
    """Complete native body, with only unique Fab user-label reading angles projected.

    Board fields (native ``property`` nodes), identity and placement are instance
    data, not a package template. They remain opaque and literal in the Source
    and the independent saved receiver. ALL other nodes, including unfamiliar
    settings, attributes, locks, models and art, remain in this comparison.
    """
    _require(isinstance(node,list) and node[:1]==['footprint'],
        'native_canonical_footprint_body_required')
    def clean(n):
        # Normalize only DIRECT attributes of known native owners. A node
        # called net/uuid inside an unfamiliar physical setting is not an
        # electrical assignment or object identity we may silently erase.
        art={'fp_line','fp_arc','fp_rect','fp_circle','fp_poly','fp_curve','fp_text','fp_text_box'}
        ignored={'uuid','tstamp'}if n[0]in art|{'pad'}else set()
        if n[0]=='pad':ignored|={'net','pinfunction','pintype'}
        return [v for v in n if not(isinstance(v,list)and v and v[0]in ignored)]
    rows=[];labels=set()
    for original in node[2:]:
        _require(isinstance(original,list) and bool(original),
            'complete_native_body_child_required')
        if original[0] in _BODY_INSTANCE_FIELDS:continue
        if original[0].startswith('fp_') and any(isinstance(c,list) and
                c[:1]==['uuid'] and c[1].strip('"') in excluded for c in original):continue
        n=copy.deepcopy(original)
        if (n[:2]==['fp_text','user'] and any(isinstance(c,list) and
                c[:2]==['layer','"F.Fab"'] for c in n)):
            _require(len(n)>=3 and isinstance(n[2],str) and n[2] not in labels,
                'unique_literal_fab_user_label_inventory_required')
            labels.add(n[2])
            poses=[c for c in n if isinstance(c,list) and c[:1]==['at']]
            _require(len(poses)==1 and len(poses[0])==4,
                'exact_native_fab_user_label_pose_required')
            angle=float(poses[0][3])
            _require(math.isfinite(angle) and angle%90==0,
                'cardinal_instance_fab_user_label_reading_angle_required')
            # Comparison tree ONLY. Text, position, font, stroke, mirror,
            # visibility, locks and all remaining attributes are untouched.
            # Keeping the literal text in the key makes inventory equality
            # and same-literal matching mandatory, not a supplied label role.
            poses[0][3]='0'
        rows.append(clean(n))
    return sorted((syntax._freeze(n) for n in rows),key=repr)


def _body_key(fp, excluded, *, source_node=None):
    """Fresh normalized native comparison; never mutate the Source footprint."""
    angle=fp.GetOrientationDegrees()
    _require(math.isfinite(angle) and angle%90==0,
        'cardinal_manufacturer_body_pose_required')
    from cec_qualified_courtyard_restore import _owned_copy
    owner,copy_fp=_owned_copy(fp)
    if copy_fp.IsFlipped(): copy_fp.Flip(pcbnew.VECTOR2I(0,0),False)
    copy_fp.SetOrientationDegrees(0); copy_fp.SetPosition(pcbnew.VECTOR2I(0,0))
    with tempfile.TemporaryDirectory(prefix='cec-map-body-') as work:
        path=Path(work)/'body.kicad_pcb'; field._save_field_snapshot(owner,path)
        _,nodes=ast._nodes(path); node=next(n for n in nodes.values() if n[0]=='footprint')
    if source_node is not None:
        # Native load can omit unsupported literal settings. Do not turn
        # that omission into package equality. Authored physical/settings
        # metadata must itself survive native serialization, not just share
        # a known-node whitelist. Art/pads are compared after the native
        # cardinal transform; instance fields remain exactly Source-owned.
        _require(isinstance(source_node,list) and source_node[:1]==['footprint'],
            'literal_source_body_required')
        for setting in source_node[2:]:
            _require(isinstance(setting,list) and bool(setting),
                'complete_literal_source_body_child_required')
            if (setting[0] in _BODY_INSTANCE_FIELDS or setting[0]=='pad'
                    or setting[0].startswith('fp_')):continue
            _require(any(syntax._freeze(setting)==syntax._freeze(n) for n in node[2:]
                if isinstance(n,list) and n[:1]==setting[:1]),
                'literal_source_body_setting_not_received_by_native')
    return _body_tree_key(node,excluded)


def plan(source, *, owner_uuid, library_table, board_hint, timeout_s=10.):
    _require(type(timeout_s) in (int,float) and 0<timeout_s<=10 and
        type(owner_uuid) is str and owner_uuid and type(board_hint) is str and board_hint,
        'bounded_explicit_reference_reownership_context_required')
    started=time.monotonic();source=Path(source).resolve(strict=True);table=Path(library_table).resolve(strict=True)
    before=_epoch(source,table);text=source.read_text();source_ids=_unique_uuids(text)
    board=pcbnew.LoadBoard(str(source))
    native_before=field._field_snapshot_inventory(board)
    fps=[f for f in board.GetFootprints() if force._uid(f)==owner_uuid]
    _require(len(fps)==1, 'one_actual_reference_owner_required');fp=fps[0]
    _require(not fp.IsLocked() and not fp.IsDNP() and not fp.Reference().IsVisible(),
        'unchanged_hidden_reference_unlocked_populated_owner_required')
    opposite=pcbnew.F_SilkS if fp.IsFlipped() else pcbnew.B_SilkS
    members=[i for i in fp.GraphicalItems() if i.GetLayer()==opposite]
    texts=[i for i in members if i.GetClass()=='PCB_TEXT']
    lines=[i for i in members if i.GetClass()=='PCB_SHAPE']
    # This is only a bounded type preflight. transport.inspect below must
    # independently prove EVERY stroke equals a complete source-court edge
    # or the single exact external nearest-point leader; count is no authority.
    _require(5<=len(members)<=257 and len(texts)==1 and 4<=len(lines)<=256 and
        len(lines)+1==len(members) and all(i.IsLocked() for i in members),
        'bounded_locked_opposite_closed_reference_map_required')
    ids={force._uid(i) for i in members}
    _require(len(ids)==len(members), 'unique_source_annotation_uuids_required')
    root,nodes=ast._nodes(source)
    for node in nodes.values():
        if node[0]=='group': _require(not ast._members(node)&(ids|{owner_uuid}), 'existing_group_ownership_cannot_be_reparented')
    fpid=fp.GetFPIDAsString();alias,item=fpid.split(':',1)
    row=before['library']['rows'].get(alias)
    _require(row and row['enabled'], 'explicit_enabled_source_library_alias_required')
    vendor=(Path(row['path'])/(item+'.kicad_mod')).resolve(strict=True)
    _require(vendor.is_relative_to((ROOT/'lib/vendor').resolve()), 'actual_repository_vendored_body_required')
    template=pcbnew.FootprintLoad(str(vendor.parent),item)
    _require(template is not None and _body_key(fp,ids,source_node=nodes[owner_uuid])==_body_key(template,set()),
        'complete_canonical_manufacturer_body_and_process_required')
    _require(field._field_snapshot_inventory(board)==native_before,'canonical_body_probe_changed_source_geometry')
    spans,_=literal._root(text); owners=[(a,b) for a,b in spans if kind(text[a:b])=='footprint'
        and _uid(syntax._parse(syntax._TOKEN.findall(text[a:b])))==owner_uuid]
    _require(len(owners)==1,'one_literal_owner_required');a,b=owners[0];part=text[a:b]
    edits=[];root_nodes=[];native={force._uid(i):i for i in members}
    for x,y in children(part):
        child_text=part[x:y]
        if kind(child_text) not in ('fp_line','fp_text'):continue
        uid=_uid(syntax._parse(syntax._TOKEN.findall(child_text)))
        if uid in ids:
            root_nodes.append(_root_annotation(child_text,native[uid]));edits.append((x,y))
    _require(len(edits)==len(ids), 'all_map_members_must_be_literal_footprint_children')
    for x,y in reversed(edits):part=part[:x]+part[y:]
    group_id=str(uuid.uuid5(uuid.NAMESPACE_URL,force._hash(source)+':map-reownership:'+owner_uuid))
    _require(group_id not in source_ids,'fresh_reference_group_uuid_required')
    group=('(group '+json.dumps(transport.PREFIX+fp.GetReference())+' (uuid '+group_id+') (locked yes) (members '+
        ' '.join(json.dumps(u) for u in sorted(ids|{owner_uuid}))+'))')
    expected=text[:a]+part+text[b:]
    closing=expected.rfind(')');expected=expected[:closing]+'\n'+'\n'.join(root_nodes+[group])+'\n'+expected[closing:]
    with tempfile.TemporaryDirectory(prefix='cec-map-proof-') as work:
        projected=force._copy_family(source,Path(work)/'family');projected.write_text(expected)
        transport.inspect(projected,owner_uuid=owner_uuid,group_uuid=group_id)
        child=pcbnew.LoadBoard(str(projected));new={force._uid(i):i for i in child.GetDrawings()}
        _require(ids<=new.keys() and all(_geometry(native[u])==_geometry(new[u]) for u in ids),
            'exact_world_reference_glyph_and_stroke_geometry_required')
    _require(time.monotonic()-started<timeout_s and _epoch(source,table)==before,
        'reference_source_library_code_or_lease_changed')
    return dict(schema=1,scope='exact_simple_opposite_reference_map_reownership',source=str(source),
        owner_uuid=owner_uuid,library_table=str(table),board_hint=board_hint,timeout_s=timeout_s,
        epoch=before,group_uuid=group_id,member_uuids=sorted(ids),vendor=str(vendor),
        expected_text_sha256=hashlib.sha256(expected.encode()).hexdigest(),
        expected_text=expected,world_geometry={u:_geometry(native[u]) for u in sorted(ids)},
        mandatory_receiving=['fresh_severity_all_native_nonregression','intake','parity','source_current_ground_field'],
        native_drc_qualified=False,release_authority=False)


def construct(source, candidate, proposal):
    """Write only the exact rederived source AST into a fresh private family."""
    fresh=plan(source,owner_uuid=proposal['owner_uuid'],library_table=proposal['library_table'],
        board_hint=proposal['board_hint'],timeout_s=proposal['timeout_s'])
    _require(fresh==proposal,'stale_or_forged_reference_reownership_plan')
    return _write_exact_family(source,candidate,fresh)


def _write_exact_family(source,candidate,fresh,*,deadline=None):
    source,candidate=Path(source).resolve(),Path(candidate).resolve()
    _require(candidate.suffix=='.kicad_pcb' and not candidate.exists() and candidate.parent!=source.parent and
        not candidate.parent.is_relative_to(source.parent), 'fresh_disjoint_private_reference_candidate_required')
    companions=force._sidecars(source);candidate.parent.mkdir(parents=True,exist_ok=False)
    owned={};remaining=force.MAX_SAVED_FAMILY_BYTES
    try:
        for suffix,digest in companions.items():
            if digest is not None:
                target=candidate.with_suffix(suffix)
                remaining-=force._copy_family_file(source.with_suffix(suffix),target,remaining)
                owned[target]=digest
        _require(len(fresh['expected_text'].encode())<=remaining,'reference_family_storage_bound')
        _require(deadline is None or time.monotonic()<deadline,'whole_reference_batch_lease_exhausted_before_board_write')
        with candidate.open('x') as stream:stream.write(fresh['expected_text'])
        owned[candidate]=fresh['expected_text_sha256']
        _require(force._sidecars(candidate)==companions and
            _epoch(source,fresh['library_table'])==fresh['epoch'] and
            (deadline is None or time.monotonic()<deadline),'late_reference_source_epoch_changed')
    except Exception:
        for path,digest in owned.items():
            if path.is_file() and force._hash(path)==digest:path.unlink()
        if not any(candidate.parent.iterdir()):candidate.parent.rmdir()
        raise
    return candidate


def _batch_settings(owners,wall_s,proof_s):
    _require(type(owners) in (list,tuple) and 1<=len(owners)<=16
        and all(type(u) is str and u for u in owners) and len(set(owners))==len(owners),
        'one_to_sixteen_unique_original_reference_owners_required')
    _require(type(wall_s) in (int,float) and math.isfinite(wall_s) and 0<wall_s<=300
        and type(proof_s) in (int,float) and math.isfinite(proof_s) and 0<proof_s<=10
        and wall_s>=proof_s,'bounded_whole_batch_and_individual_proof_leases_required')


def plan_batch(source,*,owner_uuids,library_table,board_hint,wall_s=120.,proof_s=10.):
    """Compose disjoint edits against ONE source, never a chain of children.

    Every independent single-owner proof remains <=10 seconds. They use
    flat temporary projections from the same original SHA, not nested copied
    families. Only one final expected board string is retained by the batch.
    """
    _batch_settings(owner_uuids,wall_s,proof_s);deadline=time.monotonic()+wall_s
    source=Path(source).resolve(strict=True);table=Path(library_table).resolve(strict=True)
    before=_epoch(source,table);text=source.read_text();all_ids=_unique_uuids(text)
    spans,_=literal._root(text);original={_uid(syntax._parse(syntax._TOKEN.findall(text[a:b]))):(a,b)
        for a,b in spans if kind(text[a:b])=='footprint'}
    edits=[];appended=[];contracts=[];claimed=set();groups=set()
    for owner in sorted(owner_uuids):
        _require(time.monotonic()+proof_s<=deadline,'whole_batch_lease_cannot_fund_next_independent_proof')
        q=plan(source,owner_uuid=owner,library_table=table,board_hint=board_hint,timeout_s=proof_s)
        _require(q['epoch']==before,'batch_original_source_epoch_changed')
        ids=set(q['member_uuids']);group=q['group_uuid']
        _require(not ids&claimed and group not in all_ids|groups|claimed
            and not ids&groups,'disjoint_batch_annotation_and_group_ids_required')
        claimed|=ids;groups.add(group)
        expected=q['expected_text'];parts,_=literal._root(expected);replacement=None;new=[]
        for a,b in parts:
            node_text=expected[a:b]
            if kind(node_text) not in ('footprint','gr_text','gr_line','group'):continue
            uid=_uid(syntax._parse(syntax._TOKEN.findall(node_text)))
            if uid==owner:replacement=node_text
            if uid in ids|{group}:new.append(node_text)
        _require(owner in original and replacement is not None and len(new)==len(ids)+1,
            'exact_original_owner_and_all_root_annotation_nodes_required')
        a,b=original[owner];edits.append((a,b,replacement));appended.extend(new)
        contracts.append({k:v for k,v in q.items() if k not in ('expected_text','epoch')})
        _require(time.monotonic()<deadline,'whole_reference_batch_lease_exhausted')
    expected=text
    for a,b,replacement in sorted(edits,reverse=True):expected=expected[:a]+replacement+expected[b:]
    closing=expected.rfind(')');expected=expected[:closing]+'\n'+'\n'.join(appended)+'\n'+expected[closing:]
    _unique_uuids(expected)
    _require(_epoch(source,table)==before and time.monotonic()<deadline,'batch_source_library_code_or_lease_changed')
    return dict(schema=1,scope='exact_disjoint_simple_reference_map_reownership_batch',
        source=str(source),source_sha256=force._hash(source),owner_uuids=sorted(owner_uuids),
        library_table=str(table),board_hint=board_hint,wall_s=wall_s,proof_s=proof_s,
        epoch=before,contracts=contracts,expected_text=expected,
        expected_text_sha256=hashlib.sha256(expected.encode()).hexdigest(),
        owner_count=len(contracts),original_source_only=True,partial_batch_authority=False,
        native_drc_qualified=False,release_authority=False,
        mandatory_receiving=['fresh_severity_all_native_nonregression','intake','parity','source_current_ground_field'])


def _fresh_batch(source,proposal):
    q=plan_batch(source,owner_uuids=proposal['owner_uuids'],library_table=proposal['library_table'],
        board_hint=proposal['board_hint'],wall_s=proposal['wall_s'],proof_s=proposal['proof_s'])
    _require(q==proposal,'stale_or_forged_reference_batch_plan')
    return q


def construct_batch(source,candidate,proposal):
    started=time.monotonic();q=_fresh_batch(source,proposal)
    _require(time.monotonic()-started<q['wall_s'],'whole_batch_lease_exhausted_before_write')
    return _write_exact_family(source,candidate,q,deadline=started+q['wall_s'])


def receive_batch(source,candidate,proposal,*,board_hint,wall_s=120.):
    """Recompile EVERY original contract; no per-owner receipt is authority."""
    result=dict(ok=False,complete=False,errors=[],native_drc_qualified=False,
        native_nonregression_still_required=True,release_authority=False,partial_batch_authority=False)
    try:
        _batch_settings(proposal['owner_uuids'],wall_s,proposal['proof_s'])
        _require(board_hint==proposal['board_hint'],'exact_reference_batch_board_context_required')
        _require(wall_s>=proposal['wall_s'],'receiver_whole_lease_must_cover_original_batch_policy')
        deadline=time.monotonic()+wall_s;source=Path(source).resolve(strict=True);candidate=Path(candidate).resolve(strict=True)
        _require(source!=candidate,'distinct_reference_batch_source_candidate_required')
        candidate_before=force._family(candidate);q=_fresh_batch(source,proposal)
        _require(time.monotonic()<deadline,'whole_reference_batch_receiver_lease_exhausted')
        _require(candidate.read_text()==q['expected_text'] and force._sidecars(source)==force._sidecars(candidate),
            'exact_whole_batch_literal_source_and_family_required')
        _unique_uuids(candidate.read_text());board=pcbnew.LoadBoard(str(candidate))
        drawings={force._uid(i):i for i in board.GetDrawings()}
        for one in q['contracts']:
            started=time.monotonic();_require(started+q['proof_s']<=deadline,'batch_receiver_cannot_fund_next_geometry_proof')
            transport.inspect(candidate,owner_uuid=one['owner_uuid'],group_uuid=one['group_uuid'])
            _require(all(u in drawings and _geometry(drawings[u])==g for u,g in one['world_geometry'].items()),
                'whole_saved_batch_world_reference_geometry_changed')
            _require(time.monotonic()-started<q['proof_s'],'individual_saved_batch_geometry_lease_exhausted')
        _require(time.monotonic()<deadline and _epoch(source,q['library_table'])==q['epoch']
            and force._family(candidate)==candidate_before,'batch_saved_source_code_library_or_lease_changed')
        result.update(ok=True,complete=True,owner_count=q['owner_count'],
            original_contracts_independently_recompiled=True,exact_whole_literal_board_received=True,
            labels_and_all_physical_geometry_unchanged=True,manufacturer_body_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    """Exact literal and world-geometry scope only; full native still required."""
    result=dict(ok=False,complete=False,errors=[],native_drc_qualified=False,
        native_nonregression_still_required=True,release_authority=False)
    try:
        _require(board_hint==proposal['board_hint'] and type(timeout_s) in (int,float) and 0<timeout_s<=10,
            'exact_bounded_reference_receiver_context_required')
        started=time.monotonic();source,candidate=Path(source).resolve(strict=True),Path(candidate).resolve(strict=True)
        _require(source!=candidate,'distinct_reference_source_candidate_required')
        fresh=plan(source,owner_uuid=proposal['owner_uuid'],library_table=proposal['library_table'],
            board_hint=board_hint,timeout_s=proposal['timeout_s'])
        _require(fresh==proposal,'saved_reference_plan_not_fresh')
        candidate_before=force._family(candidate)
        _require(candidate.read_text()==fresh['expected_text'],'unowned_literal_source_or_annotation_change')
        _require(force._sidecars(source)==force._sidecars(candidate),'reference_reownership_sidecar_change')
        transport.inspect(candidate,owner_uuid=proposal['owner_uuid'],group_uuid=proposal['group_uuid'])
        board=pcbnew.LoadBoard(str(candidate));new={force._uid(i):i for i in board.GetDrawings()}
        _require(all(u in new and _geometry(new[u])==g for u,g in fresh['world_geometry'].items()),
            'saved_world_reference_geometry_changed')
        _require(_epoch(source,proposal['library_table'])==fresh['epoch'] and
            force._family(candidate)==candidate_before and time.monotonic()-started<timeout_s,
            'reference_saved_family_or_lease_changed')
        result.update(ok=True,complete=True,labels_and_all_physical_geometry_unchanged=True,
            manufacturer_body_unchanged=True,scoped_literal_reownership_received=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
