"""Exact four-line -> vendor rectangle serialization, never body qualification.

The enabled project table and independent vendored template select authority.
Only an existing cardinal, closed, uniform, unlocked and ungrouped court may
change representation. Its authored contour AND native cached polygon must
remain exact. All other Source bytes, settings and companions stay opaque.
"""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import uuid

import pcbnew
import cec_additive_route_receiving as ast
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_fill_geometry as polygons
import cec_native_library_context as context
import cec_qualified_courtyard_restore as court
import cec_source_retaining_ses_import as literal
import cec_source_literal_additions as lex
import cec_synth_pipeline as synth

ROOT=Path(__file__).resolve().parents[1]
POLICY='exact_existing_four_stroke_to_vendored_courtyard_rectangle-v1'


def _uuids(text):
    seen=set();todo=[text]
    while todo:
        node=todo.pop()
        for a,z in literal.children(node):
            child=node[a:z]
            if literal.kind(child)=='uuid':
                atoms=lex._atoms(child[1:-1]);_need(len(atoms)==2,'scalar_source_uuid_required')
                uid=atoms[1][0];_need(uid not in seen,'unique_literal_source_uuids_required');seen.add(uid)
            else:todo.append(child)
    return seen


def _need(ok,why):
    if not ok:raise ValueError(why)


def _lease(timeout_s):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_courtyard_serialization_lease_required')
    return time.monotonic()+timeout_s


def _tick(deadline):
    _need(time.monotonic()<deadline,'courtyard_serialization_deadline')


def _epoch(source,table,hint):
    # This is a saved public proposal, not an in-memory callback token.
    # The native library inventory contains Python reference-pair tuples;
    # canonicalize their JSON representation before either side is bound.
    # Every value survives, and stale hashes/geometry still compare exactly.
    return json.loads(json.dumps(dict(source_sha256=force._hash(source),
        source_family=force._family(source,hint),code_identity=force._code_identity(),
        library=context.authority(source,table)),sort_keys=True,allow_nan=False))


def _cache(fp,deadline):
    fp.BuildCourtyardCaches()
    poly=fp.GetCourtyard(pcbnew.B_Cu if fp.IsFlipped()else pcbnew.F_Cu)
    _need(poly.OutlineCount()==1 and not poly.HoleCount(0),'one_native_closed_courtyard_required')
    return polygons.identity(poly,deadline,max_vertices=64)[0]


def _courts(fp):
    return [g for g in fp.GraphicalItems()if int(g.GetLayer())in court.COURTS]


def _stroke_style(node):
    fields={}
    for a,z in literal.children(node):
        key=literal.kind(node[a:z]);_need(key not in fields,'unique_courtyard_fields_required')
        fields[key]=node[a:z]
    _need(set(fields)<={'start','end','stroke','layer','uuid','tstamp','locked','fill'}
        and 'stroke'in fields,'unsupported_courtyard_attributes_refused')
    if 'fill'in fields:
        _need(literal.kind(node)=='fp_rect'and lex._atoms(fields['fill'][1:-1])in
            ([('fill','fill'),('no','no')],[('fill','fill'),('none','none')]),
            'unfilled_vendor_courtyard_rectangle_required')
    stroke=fields['stroke'];types=[lex._atoms(stroke[a+1:z-1])for a,z in literal.children(stroke)
        if literal.kind(stroke[a:z])=='type']
    _need(len(literal.children(stroke))==2 and {literal.kind(stroke[a:z])for a,z in literal.children(stroke)}=={'width','type'},
        'complete_supported_courtyard_stroke_attributes_required')
    _need(len(types)==1 and len(types[0])==2,'explicit_courtyard_stroke_style_required')
    return types[0][1][0]


def _native_body(fp,*,project_instance_fab_reference_angle=False):
    """Complete physical/art tree, with one explicitly typed instance angle.

    The unique literal Fab ${REFERENCE} is a board-reading annotation: its
    cardinal angle need not equal the unplaced vendor's reading angle. Only
    the comparison tree may project that angle. Its position, font, stroke,
    mirror, visibility and every other attribute remain exact; the Source
    and saved candidate still retain the entire original text literally.
    """
    owner,normal=court._owned_copy(fp)
    normal.SetPosition(pcbnew.VECTOR2I(0,0))
    if normal.IsFlipped():normal.Flip(pcbnew.VECTOR2I(0,0),False)
    normal.SetOrientationDegrees(0)
    with tempfile.TemporaryDirectory(prefix='cec-equivalent-court-body-')as work:
        p=Path(work)/'board.kicad_pcb';field._save_field_snapshot(owner,p)
        node=next(n for n in ast._nodes(p)[1].values()if n[0]=='footprint')
    def clean(n):
        if not isinstance(n,list):return n
        return [clean(v)for v in n if not(isinstance(v,list)and v and v[0]in
            ('uuid','tstamp','net','pinfunction','pintype'))]
    instance={'at','layer','uuid','tstamp','property','path','sheetname','sheetfile',
        'version','generator','generator_version','locked'}
    references=[n for n in node[2:]if isinstance(n,list)and n[:3]==['fp_text','user','"${REFERENCE}"']
        and any(isinstance(c,list)and c[:2]==['layer','"F.Fab"']for c in n)]
    if project_instance_fab_reference_angle:
        _need(len(references)<=1,'unique_instance_fab_reference_required')
        for reference in references:
            poses=[c for c in reference if isinstance(c,list)and c[:1]==['at']]
            _need(len(poses)==1 and len(poses[0])==4,'exact_native_instance_fab_reference_pose_required')
            angle=float(poses[0][3])
            _need(math.isfinite(angle)and angle%90==0,'cardinal_instance_fab_reference_angle_required')
            # This is the freshly serialized private comparison tree, never
            # a borrowed native Source child and never candidate text.
            poses[0][3]='0'
    rows=[]
    for n in node[2:]:
        if not isinstance(n,list)or not n or n[0]in instance:continue
        if n[0]=='fp_text'and n[1]in('reference','value'):continue
        if any(isinstance(v,list)and v[:1]==['layer']and v[1].strip('"')in('F.CrtYd','B.CrtYd')for v in n):continue
        rows.append(syntax._freeze(clean(n)))
    return sorted(rows,key=repr)


def _rectangle(node,new_uuid):
    _need(literal.kind(node)=='fp_rect','one_independent_vendor_rectangle_required')
    edits=[];found=False
    for a,z in literal.children(node):
        if literal.kind(node[a:z])in('uuid','tstamp'):
            _need(not found,'unique_vendor_rectangle_identity_required');found=True
            edits.append((a,z,'(uuid '+json.dumps(new_uuid)+')'))
    for a,z,value in reversed(edits):node=node[:a]+value+node[z:]
    if not found:node=node[:node.rfind(')')]+' (uuid '+json.dumps(new_uuid)+'))'
    return node


def _replace(text,records):
    spans=literal.inventory(text);changes=[]
    for row in records:
        a,z=spans[row['footprint_uuid']];part=text[a:z];remove=[]
        for x,y in literal.children(part):
            if literal.node_uuid(part[x:y])in row['retired_graphic_uuids']:remove.append((x,y))
        _need(len(remove)==4,'exact_four_source_courtyard_nodes_required')
        # Keep the original courtyard's native graphic slot. Appending a new
        # rectangle after pads/Fab art makes a subsequent native writer move
        # it, breaking otherwise exact downstream Source retention. All
        # unowned nodes and their order/whitespace remain opaque and literal.
        first=remove[0][0]
        for x,y in reversed(remove):
            part=part[:x]+(row['rectangle_literal']if x==first else'')+part[y:]
        changes.append((a,z,part))
    for a,z,part in sorted(changes,reverse=True):text=text[:a]+part+text[z:]
    _uuids(text)
    return text


def plan(source,*,board_hint,footprint_uuids,library_table=None,timeout_s=10.):
    deadline=_lease(timeout_s);source=Path(source).resolve(strict=True)
    _need(type(board_hint)is str and board_hint and type(footprint_uuids)in(list,tuple)
        and 1<=len(footprint_uuids)<=8 and len(set(footprint_uuids))==len(footprint_uuids)
        and all(type(u)is str and u for u in footprint_uuids),'bounded_exact_courtyard_owner_scope_required')
    canonical=(Path(synth.Config.load(board_hint).dir)/'fp-lib-table').resolve(strict=True)
    table=canonical if library_table is None else Path(library_table).resolve(strict=True)
    _need(table==canonical,'actual_project_library_table_required')
    epoch=_epoch(source,table,board_hint);text=literal.raw_text(source);ids=_uuids(text)
    b=pcbnew.LoadBoard(str(source));_need(b is not None,'native_source_board_load_refused')
    fps={force._uid(fp):fp for fp in b.GetFootprints()}
    _need(set(footprint_uuids)<=fps.keys(),'actual_source_courtyard_owner_required')
    grouped={force._uid(i)for g in b.Groups()for i in g.GetItems()}
    # Native groups plus literal memberships both remain opaque and exact.
    for a,z in literal.children(text):
        node=text[a:z]
        if literal.kind(node)!='group':continue
        for x,y in literal.children(node):
            if literal.kind(node[x:y])=='members':grouped.update(v[0]for v in lex._atoms(node[x+1:y-1])[1:])
    records=[];vendors={}
    for uid in sorted(footprint_uuids):
        _tick(deadline);fp=fps[uid];lines=_courts(fp)
        _need(not fp.IsLocked()and fp.GetOrientationDegrees()%90==0,
            'unlocked_cardinal_courtyard_owner_required')
        face=pcbnew.B_CrtYd if fp.IsFlipped()else pcbnew.F_CrtYd
        _need(len(lines)==4 and all(g.GetShape()==pcbnew.SHAPE_T_SEGMENT and g.GetLayer()==face
            and not g.IsLocked()and force._uid(g)not in grouped for g in lines),
            'four_unlocked_ungrouped_same_face_courtyard_lines_required')
        sa,sz=literal.inventory(text)[uid];part=text[sa:sz]
        raw_lines={literal.node_uuid(part[a:z]):part[a:z]for a,z in literal.children(part)
            if literal.kind(part[a:z])=='fp_line'}
        styles={_stroke_style(raw_lines[force._uid(g)])for g in lines}
        widths={int(g.GetWidth())for g in lines}
        _need(len(widths)==len(styles)==1 and next(iter(widths))>0,'uniform_courtyard_stroke_required')
        contour=court._contour(fp);xs={p[0]for p in contour};ys={p[1]for p in contour}
        _need(len(xs)==len(ys)==2 and all((x,y)in contour for x in xs for y in ys),
            'exact_axis_aligned_closed_rectangle_required')
        alias,item=fp.GetFPIDAsString().split(':',1);entry=epoch['library']['rows'].get(alias)
        _need(entry and entry['enabled'],'enabled_project_vendor_alias_required')
        vendor=(Path(entry['path'])/(item+'.kicad_mod')).resolve(strict=True)
        _need(vendor.is_relative_to((ROOT/'lib/vendor').resolve()),'independent_vendored_template_required')
        vendors[str(vendor)]=force._hash(vendor)
        template=pcbnew.FootprintLoad(str(vendor.parent),item)
        _need(template is not None,'native_vendor_footprint_required')
        original_text=vendor.read_text();original_rects=[original_text[a:z]for a,z in literal.children(original_text)
            if literal.kind(original_text[a:z])=='fp_rect'and any(literal.kind(original_text[a:z][x:y])=='layer'
                and 'CrtYd'in original_text[a:z][x:y]for x,y in literal.children(original_text[a:z]))]
        _need(len(original_rects)==1 and _stroke_style(original_rects[0])=='solid',
            'one_exact_supported_literal_vendor_rectangle_required')
        native_template,posed=court._owned_copy(template)
        if fp.IsFlipped():posed.Flip(pcbnew.VECTOR2I(0,0),False)
        posed.SetOrientationDegrees(fp.GetOrientationDegrees());posed.SetPosition(fp.GetPosition())
        rects=_courts(posed)
        _need(len(rects)==1 and rects[0].GetShape()==pcbnew.SHAPE_T_RECT
            and rects[0].GetLayer()==face and not rects[0].IsLocked(),
            'one_same_face_unlocked_vendor_rectangle_required')
        rect=rects[0]
        # KiCad's DEFAULT stroke is its solid-line representation, not a
        # dashed alternative. Every other native style remains forbidden.
        _need(styles<={'default','solid'}
            and widths=={int(rect.GetWidth())},'exact_vendor_courtyard_width_and_solid_style_required')
        _need(contour==court._contour(posed)and _cache(fp,deadline)==_cache(posed,deadline),
            'authored_and_cached_vendor_courtyard_must_match_exactly')
        _need(_native_body(fp,project_instance_fab_reference_angle=True)
            ==_native_body(posed,project_instance_fab_reference_angle=True),
            'complete_source_vendor_physical_art_identity_required')
        with tempfile.TemporaryDirectory(prefix='cec-independent-court-rect-')as work:
            path=Path(work)/'posed.kicad_pcb';field._save_field_snapshot(native_template,path)
            saved=literal.raw_text(path);span=next((a,z)for a,z in literal.children(saved)
                if literal.kind(saved[a:z])=='footprint');vendor_text=saved[span[0]:span[1]]
        nodes=[vendor_text[a:z]for a,z in literal.children(vendor_text)
            if literal.kind(vendor_text[a:z])=='fp_rect'and any(literal.kind(vendor_text[a:z][x:y])=='layer'
                and 'CrtYd' in vendor_text[a:z][x:y]for x,y in literal.children(vendor_text[a:z]))]
        _need(len(nodes)==1,'unique_literal_vendor_courtyard_rectangle_required')
        _need(_stroke_style(nodes[0])=='solid','solid_vendor_courtyard_rectangle_required')
        # Obtain local node coordinates from the independently native-posed
        # vendor, including exact native back-face reflection semantics.
        node=nodes[0]
        new=str(uuid.uuid5(uuid.NAMESPACE_URL,POLICY+epoch['source_sha256']+uid+vendors[str(vendor)]))
        _need(new not in ids,'fresh_deterministic_courtyard_uuid_required')
        records.append(dict(footprint_uuid=uid,retired_graphic_uuids=sorted(force._uid(g)for g in lines),
            rectangle_uuid=new,rectangle_literal=_rectangle(node,new),vendor=str(vendor),
            authored_contour_nm=[list(p)for p in contour],native_courtyard_sha256=_cache(fp,deadline)))
    expected=_replace(text,records)
    # Native readback must prove the independently local vendor node really
    # undergoes the Source rotation/flip, rather than trusting text arithmetic.
    with tempfile.TemporaryDirectory(prefix='cec-equivalent-court-plan-')as work:
        p=Path(work)/'board.kicad_pcb';literal.write_raw(p,expected);child=pcbnew.LoadBoard(str(p))
        for row in records:
            fp=next(f for f in child.GetFootprints()if force._uid(f)==row['footprint_uuid'])
            _need(court._contour(fp)==tuple(map(tuple,row['authored_contour_nm']))
                and _cache(fp,deadline)==row['native_courtyard_sha256'],'literal_vendor_rectangle_transform_changed_geometry')
    _tick(deadline)
    _need(epoch==_epoch(source,table,board_hint)and all(force._hash(Path(p))==h for p,h in vendors.items()),
        'courtyard_source_code_library_changed')
    _tick(deadline)
    return dict(schema=1,scope=POLICY,source=str(source),board_hint=board_hint,library_table=str(table),
        request=dict(footprint_uuids=list(footprint_uuids),timeout_s=timeout_s),epoch=epoch,
        vendor_sha256=vendors,records=records,expected_text_sha256=hashlib.sha256(expected.encode()).hexdigest(),
        release_authority=False,physical_or_electrical_qualification=False)


def _fresh(source,proposal,deadline):
    _tick(deadline)
    fresh=plan(source,board_hint=proposal['board_hint'],library_table=proposal['library_table'],
        footprint_uuids=proposal['request']['footprint_uuids'],timeout_s=min(proposal['request']['timeout_s'],deadline-time.monotonic()))
    # Remaining lease is an observation, not replayable design authority.
    fresh['request']['timeout_s']=proposal['request']['timeout_s']
    _need(fresh==proposal,'stale_or_forged_equivalent_courtyard_plan')
    return _replace(literal.raw_text(source),fresh['records'])


def _native_tree(path,target):
    field._save_field_snapshot(pcbnew.LoadBoard(str(path)),target)
    return syntax._freeze(syntax._parse(syntax._TOKEN.findall(literal.raw_text(target))))


def receive(source,candidate,proposal,*,timeout_s=10.):
    deadline=_lease(timeout_s);result=dict(ok=False,complete=False,errors=[],release_authority=False,
        physical_or_electrical_qualification=False)
    try:
        source,candidate=Path(source).resolve(strict=True),Path(candidate).resolve(strict=True)
        _need(source!=candidate,'distinct_courtyard_source_candidate_required')
        before=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        expected=_fresh(source,proposal,deadline)
        _need(literal.raw_text(candidate)==expected,'changed_unowned_source_literal')
        _need(force._sidecars(source)==force._sidecars(candidate),'changed_source_sidecars')
        with tempfile.TemporaryDirectory(prefix='cec-equivalent-court-replay-')as work:
            root=Path(work);p=root/'expected.kicad_pcb';literal.write_raw(p,expected)
            want=_native_tree(p,root/'expected-native.kicad_pcb')
            actual=_native_tree(candidate,root/'candidate-native.kicad_pcb')
            again=_native_tree(root/'candidate-native.kicad_pcb',root/'second-native.kicad_pcb')
            _need(want==actual==again,'whole_native_replay_or_second_save_changed')
        _tick(deadline)
        _need(before==[force._family(p,proposal['board_hint'])for p in(source,candidate)]
            and proposal['epoch']==_epoch(source,Path(proposal['library_table']),proposal['board_hint']),
            'courtyard_source_candidate_context_changed')
        _tick(deadline)
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            exact_source_minus_four_lines_plus_vendor_rectangle=True,whole_native_second_save_exact=True,
            all_material_and_functional_ink_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def write_private(source,candidate,proposal,*,timeout_s=10.):
    deadline=_lease(timeout_s);source=Path(source).resolve(strict=True);candidate=Path(candidate).resolve()
    _need(source.parent!=candidate.parent and not candidate.exists()and not candidate.parent.exists(),
        'fresh_private_courtyard_namespace_required')
    expected=_fresh(source,proposal,deadline);child=force._copy_family(source,candidate.parent)
    _need(child.name==candidate.name,'source_basename_required')
    literal.write_raw(candidate,expected)
    proof=receive(source,candidate,proposal,timeout_s=max(.001,deadline-time.monotonic()))
    _need(proof['ok']and proof['complete'],'private_courtyard_receiving_refused:'+str(proof['errors']))
    _tick(deadline)
    return candidate


def _query_projection(path,records,*,source,deadline):
    """Entire actual AST, subtracting only the independently received court."""
    import cec_ink_material_identity as material
    text=literal.raw_text(path)
    _need(len(text.encode())<=material.MAX_BYTES,'bounded_courtyard_query_text_required')
    tokens=[]
    for match in material.TOKEN.finditer(text):
        if len(tokens)%4096==0:_tick(deadline)
        token=match.group()
        if not token.startswith(';'):tokens.append(token)
        _need(len(tokens)<=material.MAX_TOKENS,'bounded_courtyard_query_tokens_required')
    # Semicolon comments are grammar, not atoms outside the root. The fresh
    # literal receiver above still preserves every comment byte exactly.
    root=syntax._parse(tokens)
    nodes={court._uid(n):n for n in root[1:]if isinstance(n,list)and court._uid(n)}
    for row in records:
        ids=set(row['retired_graphic_uuids']if source else[row['rectangle_uuid']])
        owner=nodes.get(row['footprint_uuid'])
        _need(owner is not None and owner[0]=='footprint','exact_courtyard_query_owner_required')
        removed=[node for node in owner[1:]if isinstance(node,list)and court._uid(node)in ids]
        _need(len(removed)==len(ids)and all(node[0]==('fp_line'if source else'fp_rect')for node in removed),
            'exact_received_courtyard_query_nodes_required')
        owner[:]=[node for node in owner if not(isinstance(node,list)and court._uid(node)in ids)]
    return syntax._freeze(root)


def query_input_identity(source,candidate,proposal,*,timeout_s=10.):
    """Prove unchanged inputs; do NOT evaluate or qualify inherited debt.

    Fresh Source reconstruction, exact literal substitution, actual child
    court geometry and entire independently native-resaved trees own this
    relation. Separate public representation receiving is still mandatory
    for mutation authority. Do not redundantly serialize its expected/child/
    second-child snapshots here: the two actual endpoint trees below are the
    identity comparison. No caller geometry, success inventory or stale scope
    is accepted, and no arbitrary court can be ignored.
    """
    started=time.monotonic();result=dict(ok=False,complete=False,comparison_complete=False,
        same_material=False,mutation_authority=False,full_kelvin_qualification=False,
        inherited_electrical_debt='unchanged_not_evaluated',release_authority=False,
        independent_equivalent_courtyard_receiving_required=True)
    try:
        deadline=_lease(timeout_s);source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
        code=force._code_identity();families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        expected=_fresh(source,proposal,deadline)
        _need(literal.raw_text(candidate)==expected,'changed_unowned_source_literal')
        _need(force._sidecars(source)==force._sidecars(candidate),'changed_source_sidecars')
        records=proposal['records'];raw=[_query_projection(p,records,source=i==0,deadline=deadline)
            for i,p in enumerate((source,candidate))]
        _need(raw[0]==raw[1],'non_equivalent_courtyard_saved_query_input_changed')
        boards=[];native=[]
        with tempfile.TemporaryDirectory(prefix='cec-equivalent-court-query-')as work:
            for i,path in enumerate((source,candidate)):
                _tick(deadline);board=pcbnew.LoadBoard(str(path));boards.append(board)
                if i==1:
                    owners={force._uid(fp):fp for fp in board.GetFootprints()}
                    for row in records:
                        fp=owners[row['footprint_uuid']]
                        _need(court._contour(fp)==tuple(map(tuple,row['authored_contour_nm']))
                            and _cache(fp,deadline)==row['native_courtyard_sha256'],
                            'actual_native_courtyard_query_geometry_changed')
                saved=Path(work)/(str(i)+'.kicad_pcb');field._save_field_snapshot(board,saved)
                native.append(_query_projection(saved,records,source=i==0,deadline=deadline))
            _need(native[0]==native[1],'non_equivalent_courtyard_native_query_input_changed')
        _tick(deadline)
        _need(code==force._code_identity()and families==[force._family(p,proposal['board_hint'])for p in(source,candidate)]
            and proposal['epoch']==_epoch(source,Path(proposal['library_table']),proposal['board_hint']),
            'equivalent_courtyard_query_source_context_changed')
        digest=lambda tree:hashlib.sha256(repr(tree).encode()).hexdigest()
        raw_digest,native_digest=digest(raw[0]),digest(native[0])
        _tick(deadline)
        result.update(ok=True,complete=True,comparison_complete=True,same_material=True,
            source=str(source),candidate=str(candidate),code_identity=code,
            fresh_exact_source_scope_reconstructed=True,actual_native_courtyard_geometry_equal=True,
            unchanged_saved_ast_sha256=raw_digest,unchanged_native_ast_sha256=native_digest,
            scope='complete_query_inputs_except_freshly_received_equal_courtyard_representation')
    except Exception as exc:result['errors']=[type(exc).__name__+':'+str(exc)]
    result['elapsed_s']=time.monotonic()-started
    return result
