"""Registered optional body ink; no physical or native-DRC admission.

The approved scope is only original silk lines positively corresponding to a
complete Fab body, through separately named exact-duplicate or strict native
rectangle/stroke-containment policies. Functional/notch/key marks are never
inferred optional. No board writer
or library replacement is supplied here; final native/context receiving stays
mandatory for an integrating operator. A separate manufacturer-nonpolar role
owns only the two symmetric body strokes of a registered resistor package.
"""
import hashlib
import math
import time
import tempfile
from pathlib import Path
from fractions import Fraction

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_force_current as force
import cec_native_library_context as libraries
import cec_source_retaining_ses_import as raw
import cec_ink_only_variant as ink

ROOT=Path(__file__).resolve().parents[1]
POLICY='approved-fab-duplicate-terminal-body-lines-v1'
CORRELATED_POLICY='approved-fab-correlated-rectangular-body-lines-v1'
MANUFACTURER_NONPOLAR_POLICY='registered-manufacturer-nonpolar-two-line-body-v1'
# User-ratified optional BODY role, pinned to an independent original template.
# The five nonduplicate notch/bottom strokes are deliberately outside this role.
TEMPLATES={
    'XFCN_TTR32100127-0600_THT_M3_60A':dict(
        sha256='49cd717c74fff56e0c34dd01295551ad18106a24edd84cc5338d02c7379539ff',
        mpn='TTR32100127-0600',relative='lib/vendor/Connector_Screw.pretty',
        selected_lines=3,total_silk_lines=8),
    'XFCN_T34069_THT_M3_40A':dict(
        sha256='6d680009f049236a9fc06e9f4c99f3bb79477cd9d8f3dfcb41a61b07321ab02b',
        mpn='T34069',relative='lib/vendor/Connector_Screw.pretty',
        selected_lines=4,total_silk_lines=4,geometry_role=CORRELATED_POLICY),
    'R_Bourns_CSS2H-2512R_L500':dict(
        sha256='51042fd3ffa2271ef28af8dad3cd9ad9fc9109e8743720097a1e22277d2ac52b',
        mpn='CSS2H-2512R-L500F',relative='lib/vendor/Resistor_SMD.pretty',
        catalog='Bourns CSS2H-2512R-L500F',predecessor='R_2512_6332Metric',
        predecessor_sha256='d7a14fa43aa28ab5eef5d71ccca44f1e977218c514cfa88ce77878691591087e',
        selected_lines=2,total_silk_lines=2,geometry_role=MANUFACTURER_NONPOLAR_POLICY)}


def _need(ok,message):
    if not ok:raise ValueError(message)


def _tick(deadline):
    _need(time.monotonic()<deadline,'optional_body_ink_deadline')


def _sha(text):return hashlib.sha256(text.encode()).hexdigest()


def _template_authority(template_path):
    """A copied context is usable only as byte-exact registered material.

    Never learn a footprint from Source, a proposed context or a prior verdict.
    The independent canonical asset, predecessor, drawing and existing
    manufacturer recipe remain live inputs throughout construction/receiving.
    """
    path=Path(template_path).resolve(strict=True);policy=TEMPLATES.get(path.stem)
    _need(policy is not None,'no_approved_optional_body_template')
    canonical=(ROOT/policy['relative']/path.name).resolve(strict=True)
    _need(force._hash(canonical)==policy['sha256']and force._hash(path)==policy['sha256'],
        'exact_approved_original_vendor_required')
    inputs={str(canonical):policy['sha256'],str(path):policy['sha256']}
    if policy.get('geometry_role')==MANUFACTURER_NONPOLAR_POLICY:
        import cec_manufacturer_land_pattern as manufacturer
        rule=manufacturer.CATALOG.get(policy['catalog'])
        _need(rule is not None and rule.get('new')==path.stem
            and rule.get('old')==policy['predecessor']and rule.get('selected_mpn')==policy['mpn']
            and rule.get('directory')==policy['relative'],'registered_manufacturer_body_role_required')
        old=ROOT/policy['relative']/(rule['old']+'.kicad_mod');drawing=ROOT/rule['datasheet']
        _need(force._hash(old)==policy['predecessor_sha256']
            and force._hash(drawing)==rule['datasheet_sha256'],
            'independent_manufacturer_predecessor_and_drawing_required')
        inputs.update({str(old):policy['predecessor_sha256'],str(drawing):rule['datasheet_sha256'],
            str(Path(manufacturer.__file__).resolve()):force._hash(Path(manufacturer.__file__))})
    else:_need(path==canonical,'exact_approved_original_vendor_required')
    return policy,canonical,inputs


def template_inputs(template_path):
    return _template_authority(template_path)[2]


def _manufacturer_recipe_defaults(actual,policy,copper_layers):
    """Replay the existing old-to-manufacturer recipe, not a metadata waiver."""
    import cec_manufacturer_land_pattern as manufacturer
    import cec_nonpolar_print_context as print_context
    rule=manufacturer.CATALOG[policy['catalog']]
    board=pcbnew.BOARD();board.SetCopperLayerCount(copper_layers)
    fp=pcbnew.FootprintLoad(str(ROOT/policy['relative']),rule['old']);board.Add(fp)
    fp.SetFPIDAsString(rule['library']+':'+rule['old'])
    fp.SetField('MPN',actual.GetFieldText('MPN'));fp.SetValue(actual.GetValue())
    # The stock selector independently validates the exact MPN/value/drawing
    # and the complete predecessor lands/courtyard before materializing.
    proposal=manufacturer.plan(board,[force._uid(fp)])
    manufacturer.materialize(board,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-registered-body-origin-')as work:
        path=Path(work)/'recipe.kicad_pcb';ink.field._save_field_snapshot(board,path)
        text=path.read_text();a,b=next((a,b)for a,b in raw.children(text)
            if raw.kind(text[a:b])=='footprint')
        return print_context._extras(text[a:b])


def _native_match(actual,template_path):
    # This is independently generated comparison material, NOT a saved Source
    # or output candidate. Materialize the original template's own first-save
    # defaults after the exact pose, then require stable full physical trees.
    policy=TEMPLATES.get(template_path.stem,{})
    if policy.get('geometry_role')==MANUFACTURER_NONPOLAR_POLICY:
        import cec_nonpolar_print_context as print_context
        return print_context._physical_match(actual,
            pcbnew.FootprintLoad(str(template_path.parent),template_path.stem))
    owner=pcbnew.BOARD();owner.SetCopperLayerCount(actual.GetBoard().GetCopperLayerCount())
    projected=pcbnew.FootprintLoad(str(template_path.parent),template_path.stem);owner.Add(projected)
    if actual.IsFlipped():projected.Flip(pcbnew.VECTOR2I(0,0),False)
    projected.SetOrientationDegrees(actual.GetOrientationDegrees());projected.SetPosition(actual.GetPosition())
    if policy.get('geometry_role')==CORRELATED_POLICY:
        # Existing Fab labels can retain a cardinal instance reading angle.
        # They are NOT omitted or rewritten. Align ONLY the independent
        # comparison clone's text angles; full native comparison below still
        # owns their literal text, exact relative location, font, thickness,
        # side, mirror and every other attribute/material subtree.
        face=pcbnew.B_Fab if actual.IsFlipped()else pcbnew.F_Fab
        def fab_texts(fp):
            texts=[g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetLayer()==face]
            result={g.GetText():g for g in texts}
            _need(len(result)==len(texts),'unique_original_fab_text_inventory_required')
            return result
        left,right=fab_texts(actual),fab_texts(projected)
        _need(left.keys()==right.keys(),'exact_original_fab_label_texts_required')
        _need(actual.GetOrientationDegrees()%90==0,'cardinal_terminal_instance_required')
        for label in left:
            angle=left[label].GetTextAngle().AsDegrees()
            _need(math.isfinite(angle)and angle%90==0,'cardinal_source_fab_label_angle_required')
            right[label].SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    with tempfile.TemporaryDirectory(prefix='cec-optional-body-template-')as work:
        path=Path(work)/'comparison.kicad_pcb';pcbnew.SaveBoard(str(path),owner)
        saved=pcbnew.LoadBoard(str(path))
        pcbnew.SaveBoard(str(path),saved);again=pcbnew.LoadBoard(str(path))
        first=ink.frame._semantic(next(iter(saved.GetFootprints())))
        second=ink.frame._semantic(next(iter(again.GetFootprints())))
    return first==second==ink.frame._semantic(actual)


def _line(item):
    return tuple(sorted((tuple(item.GetStart()),tuple(item.GetEnd()))))


def _correlated_rectangle_lines(silk,fab_corners):
    """Positive closed-edge topology plus exact integer stroke containment.

    Bounds alone never establish a body. All four independently supplied
    lines must be the complete distinct cardinal cycle, with valence two at
    every actual corner. The approved original template supplies semantics;
    this geometry check supplies only exact correspondence to retained Fab.
    """
    _need(len(silk)==4,'four_complete_correlated_body_edges_required')
    widths={int(g.GetWidth())for g in silk}
    _need(len(widths)==1 and next(iter(widths))>0,'one_positive_correlated_body_stroke_required')
    edges=[_line(g)for g in silk];points={p for edge in edges for p in edge}
    _need(len(points)==4 and len(set(edges))==4 and all(a!=b and
        (a[0]==b[0]or a[1]==b[1])for a,b in edges),
        'complete_cardinal_body_cycle_required')
    valence={p:sum(p in edge for edge in edges)for p in points}
    xs=sorted({p[0]for p in points});ys=sorted({p[1]for p in points})
    _need(set(valence.values())=={2}and len(xs)==len(ys)==2,
        'closed_distinct_body_corner_cycle_required')
    corners=[(xs[0],ys[0]),(xs[1],ys[0]),(xs[1],ys[1]),(xs[0],ys[1])]
    expected={tuple(sorted((corners[i],corners[(i+1)%4])))for i in range(4)}
    _need(set(edges)==expected,'complete_body_edge_correspondence_required')
    fx=sorted({p[0]for p in fab_corners});fy=sorted({p[1]for p in fab_corners})
    _need(len(fx)==len(fy)==2 and fx[0]<fx[1]and fy[0]<fy[1],
        'complete_nondegenerate_correlated_fab_required')
    _need(xs[0]+xs[1]==fx[0]+fx[1]and ys[0]+ys[1]==fy[0]+fy[1],
        'exact_same_body_center_required')
    _need(xs[0]<=fx[0]<fx[1]<=xs[1]and ys[0]<=fy[0]<fy[1]<=ys[1],
        'fab_edge_tangent_intervals_must_be_covered')
    width=next(iter(widths))
    offsets=(fx[0]-xs[0],xs[1]-fx[1],fy[0]-ys[0],ys[1]-fy[1])
    _need(all(2*d<width for d in offsets),
        'fab_centerline_strictly_inside_original_body_stroke_required')
    return {force._uid(g)for g in silk}


def _template_lines(template,policy):
    """Exact integer centerlines; no tolerance/body-bbox/pad inference."""
    fab=[g for g in template.GraphicalItems()if g.GetLayer()==pcbnew.F_Fab
        and hasattr(g,'GetShape')and g.GetShape()==pcbnew.SHAPE_T_RECT]
    _need(len(fab)==1,'one_original_closed_fab_rectangle_required')
    a,z=fab[0].GetStart(),fab[0].GetEnd()
    _need(a.x!=z.x and a.y!=z.y,'nondegenerate_original_fab_body_required')
    corners=[(a.x,a.y),(z.x,a.y),(z.x,z.y),(a.x,z.y)]
    edges={tuple(sorted((corners[i],corners[(i+1)%4])))for i in range(4)}
    silk=[g for g in template.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS]
    _need(len(silk)==policy['total_silk_lines']and all(g.GetClass()=='PCB_SHAPE'
        and g.GetShape()==pcbnew.SHAPE_T_SEGMENT for g in silk),
        'exact_original_terminal_silk_role_inventory_required')
    if policy.get('geometry_role')==MANUFACTURER_NONPOLAR_POLICY:
        pads=list(template.Pads());widths={int(g.GetWidth())for g in silk}
        _need(len(pads)==2 and {p.GetNumber()for p in pads}=={'1','2'}
            and all(p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()for p in pads),
            'registered_two_terminal_nonpolar_body_required')
        edges=[_line(g)for g in silk]
        reflected=tuple(sorted((-x,-y)for x,y in edges[0]))
        _need(len(silk)==2 and len(widths)==1 and next(iter(widths))>0
            and len(set(edges))==2 and reflected==edges[1]
            and all(a!=b and a[1]==b[1]and a[1]!=0 for a,b in edges),
            'two_distinct_symmetric_nonpolar_body_strokes_required')
        return {force._uid(g)for g in silk}
    if policy.get('geometry_role')==CORRELATED_POLICY:
        return _correlated_rectangle_lines(silk,corners)
    chosen=[g for g in silk if _line(g)in edges]
    _need(len(chosen)==policy['selected_lines']and len({_line(g)for g in chosen})==len(chosen),
        'exact_original_fab_duplicate_body_lines_required')
    return {force._uid(g)for g in chosen}


def template_omission(template_path):
    """Exact original-library derivative; no Source or context authority."""
    path=Path(template_path).resolve(strict=True);policy,canonical,inputs=_template_authority(path)
    template=pcbnew.FootprintLoad(str(path.parent),path.stem)
    selected=_template_lines(template,policy)
    wanted={(_line(g),g.GetWidth())for g in template.GraphicalItems()if force._uid(g)in selected}
    text=path.read_text();ids=[];changes=[]
    def nm(token):
        number=Fraction(token)*1000000
        _need(number.denominator==1,'exact_integer_original_body_geometry_required')
        return int(number)
    for a,b in raw.children(text):
        part=text[a:b];node=ink._node(part)
        if node[0]!='fp_line' or not any(isinstance(n,list)and n[:2]==['layer','"F.SilkS"']for n in node):continue
        first=next(n for n in node if isinstance(n,list)and n[:1]==['start'])
        last=next(n for n in node if isinstance(n,list)and n[:1]==['end'])
        stroke=next(n for n in node if isinstance(n,list)and n[:1]==['stroke'])
        width=next(n[1] for n in stroke if isinstance(n,list)and n[:1]==['width'])
        geometry=(tuple(sorted((tuple(map(nm,first[1:])),tuple(map(nm,last[1:]))))),nm(width))
        if geometry in wanted:
            ids.append(ink._uid(node)or 'literal:'+ink._digest(part));changes.append((a,b,''))
    _need(len(ids)==policy['selected_lines']and len(set(ids))==len(ids),
        'complete_unique_literal_original_body_inventory_required')
    return dict(template=str(path),template_sha256=policy['sha256'],canonical_template=str(canonical),
        template_input_sha256=inputs,graphic_ids=sorted(ids),
        derivative_text=ink._edits(text,changes),preserved_functional_silk_lines=policy['total_silk_lines']-len(ids))


def inspect_many(source,*,library_table,footprint_uuids,expected_source_sha256,timeout_s=10.,
                 allow_already_omitted=False):
    """One fresh bounded Source snapshot; every actual owner is still proved.

    Only repeated immutable Source parsing/context inventory is shared. No
    public context, cached owner approval or prior successful receipt is an
    input. Literal/whole native owner proofs and final live bindings remain
    identical to independent single-owner inspection.
    """
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10
        and type(allow_already_omitted)is bool,
        'bounded_optional_body_ink_contract_required')
    started=time.monotonic();deadline=started+timeout_s
    source=Path(source).resolve(strict=True);table=Path(library_table).resolve(strict=True)
    _need(type(footprint_uuids)in(list,tuple)and 1<=len(footprint_uuids)<=128
        and all(type(uid)is str and uid for uid in footprint_uuids)
        and len(set(footprint_uuids))==len(footprint_uuids),'finite_unique_optional_body_owner_scope_required')
    _need(source.suffix=='.kicad_pcb'
        and type(expected_source_sha256)is str and force._hash(source)==expected_source_sha256,
        'exact_saved_optional_body_source_required')
    _need(source.stat().st_size<=32*1024*1024 and table.stat().st_size<=1024*1024,
        'bounded_optional_body_source_inventory_required')
    code=force._code_identity();authority=libraries.authority(source,table)
    text=source.read_text();_need(_sha(text)==expected_source_sha256,'literal_optional_body_source_changed')
    inventory=raw.inventory(text);board=pcbnew.LoadBoard(str(source))
    context=(source,table,expected_source_sha256,allow_already_omitted,deadline,code,authority,text,inventory,board)
    proofs={uid:_inspect_owner(context,uid)for uid in footprint_uuids}
    _need(force._hash(source)==expected_source_sha256 and code==force._code_identity()
        and authority==libraries.authority(source,table)
        and all(force._hash(Path(p))==h for proof in proofs.values()
            for p,h in proof['template_input_sha256'].items()),'optional_body_source_context_changed')
    _tick(deadline);return proofs


def inspect(source,*,library_table,footprint_uuid,expected_source_sha256,timeout_s=10.,
            allow_already_omitted=False):
    return inspect_many(source,library_table=library_table,footprint_uuids=[footprint_uuid],
        expected_source_sha256=expected_source_sha256,timeout_s=timeout_s,
        allow_already_omitted=allow_already_omitted)[footprint_uuid]


def _inspect_owner(context,footprint_uuid):
    (source,table,expected_source_sha256,allow_already_omitted,deadline,code,authority,text,inventory,board)=context
    _tick(deadline)
    owners=[f for f in board.GetFootprints()if force._uid(f)==footprint_uuid]
    _need(len(owners)==1,'one_exact_source_owner_required');fp=owners[0]
    _need(len(list(fp.GraphicalItems()))<=128 and len(list(fp.Pads()))<=16,
        'bounded_optional_body_owner_inventory_required')
    _need(not fp.IsDNP()and not fp.IsLocked(),'unlocked_populated_source_terminal_required')
    alias,item=fp.GetFPIDAsString().split(':',1);policy=TEMPLATES.get(item)
    _need(policy is not None,'no_approved_optional_body_template')
    row=authority['rows'].get(alias)
    _need(row and row['enabled'],'explicit_enabled_source_library_required')
    template_path=Path(row['path'])/(item+'.kicad_mod')
    _,canonical,inputs=_template_authority(template_path)
    template=pcbnew.FootprintLoad(str(template_path.parent),item)
    registered_nonpolar=policy.get('geometry_role')==MANUFACTURER_NONPOLAR_POLICY
    _need(template is not None and fp.HasField('MPN')
        and (registered_nonpolar or template.HasField('MPN')and template.GetFieldText('MPN')==policy['mpn'])
        and fp.GetFieldText('MPN')==policy['mpn'],'exact_source_manufacturer_identity_required')
    selected=_template_lines(template,policy)
    selected_geometry={(_line(g),g.GetWidth())for g in template.GraphicalItems()
        if force._uid(g)in selected}
    _tick(deadline)
    source_silk=[g for g in fp.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)]
    already=allow_already_omitted and len(source_silk)==policy['total_silk_lines']-policy['selected_lines']
    if already:
        derivative=template_omission(template_path)
        with tempfile.TemporaryDirectory(prefix='cec-original-minus-body-')as work:
            path=Path(work)/template_path.name;path.write_text(derivative['derivative_text'])
            _need(_native_match(fp,path),'already_omitted_body_not_exact_original_derivative')
    else:_need(_native_match(fp,template_path),'entire_source_native_template_must_match')
    # Complete original native root defaults, not only the helper's known
    # pad/art subset. A recognized future physical setting cannot disappear
    # behind a template comparison that excludes instance fields.
    import cec_nonpolar_print_context as print_context
    a,b=inventory[footprint_uuid];owner_text=text[a:b]
    original_extra=print_context._original_defaults(template_path,board.GetCopperLayerCount())
    alternatives={'independent_original_defaults':original_extra}
    if registered_nonpolar:
        alternatives['independent_manufacturer_recipe']=_manufacturer_recipe_defaults(fp,policy,board.GetCopperLayerCount())
    origins=sorted(name for name,value in alternatives.items()if print_context._extras(owner_text)==value)
    _need(origins,
        'unknown_or_additional_source_physical_settings_differ')
    # Child UUIDs may be regenerated by placement; match exact transformed
    # native lines, never UUID spelling or Source coordinates as role policy.
    projected=pcbnew.FootprintLoad(str(template_path.parent),item)
    holder=pcbnew.BOARD();holder.Add(projected)
    wanted=[g for g in projected.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS
        and g.GetClass()=='PCB_SHAPE'and g.GetShape()==pcbnew.SHAPE_T_SEGMENT
        and (_line(g),g.GetWidth())in selected_geometry]
    _need(len(wanted)==policy['selected_lines'],'complete_projected_body_role_required')
    if fp.IsFlipped():projected.Flip(pcbnew.VECTOR2I(0,0),False)
    projected.SetOrientationDegrees(fp.GetOrientationDegrees());projected.SetPosition(fp.GetPosition())
    face=pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS
    found=[]
    for target in ([] if already else wanted):
        matches=[g for g in fp.GraphicalItems()if g.GetLayer()==face and g.GetClass()=='PCB_SHAPE'
            and g.GetShape()==pcbnew.SHAPE_T_SEGMENT and _line(g)==_line(target)
            and g.GetWidth()==target.GetWidth()]
        _need(len(matches)==1 and not matches[0].IsLocked(),'unique_unlocked_exact_source_body_line_required')
        found.append(force._uid(matches[0]))
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    _need(not set(found)&grouped and footprint_uuid not in grouped and fp.GetParentGroup()is None,
        'grouped_body_artwork_not_owned')
    proof=dict(schema=1,policy=policy.get('geometry_role',POLICY),source=str(source),source_sha256=expected_source_sha256,
        library_table=str(table),library_authority=authority,script_code_identity=code,
        helper_sha256=force._hash(Path(__file__)),footprint_uuid=footprint_uuid,
        source_owner_literal_sha256=_sha(owner_text),template=str(template_path),
        template_sha256=policy['sha256'],canonical_template=str(canonical),template_input_sha256=inputs,
        independently_reproduced_metadata_origins=origins,graphic_uuids=sorted(found),
        source_optional_body_state='already_omitted_approved_body'if already else'original_approved_body',
        preserved_nonoptional_silk_count=policy['total_silk_lines']-policy['selected_lines'],
        allow_already_omitted=allow_already_omitted,
        comparison_helper_sha256=force._hash(Path(print_context.__file__)),
        all_other_source_bytes_must_survive=True,complete_fab_and_courtyard_must_survive=True,
        native_drc_and_complete_source_context_receiving_required=True,
        current_authority=False,physical_change_authority=False,release_authority=False)
    _tick(deadline);return proof


def expected_omission(source,proof,*,timeout_s=10.):
    """Recompile Source ownership and return ONLY exact literal line omissions."""
    started=time.monotonic()
    fresh=inspect(source,library_table=proof['library_table'],footprint_uuid=proof['footprint_uuid'],
        expected_source_sha256=proof['source_sha256'],timeout_s=timeout_s,
        allow_already_omitted=proof['allow_already_omitted'])
    _need(fresh==proof,'optional_body_contract_changed')
    text=Path(source).read_text();a,b=raw.inventory(text)[proof['footprint_uuid']]
    owner=text[a:b];changes=[]
    for x,y in raw.children(owner):
        part=owner[x:y];node=ink._node(part)
        if ink._uid(node)in proof['graphic_uuids']:
            _need(node[0]=='fp_line','only_exact_body_line_omission_allowed');changes.append((a+x,a+y,''))
    _need(len(changes)==len(proof['graphic_uuids']),'every_exact_body_line_literal_required')
    result=ink._edits(text,changes);_tick(started+timeout_s)
    return result


def receive_literal(source,candidate,proof,*,timeout_s=10.):
    """Scope only: every unowned Source byte remains exact. Not admission."""
    started=time.monotonic();expected=expected_omission(source,proof,timeout_s=timeout_s)
    _need(Path(source).resolve()!=Path(candidate).resolve()
        and Path(candidate).stat().st_size==len(expected.encode())and Path(candidate).read_text()==expected,
        'optional_body_changed_unowned_source_literal')
    _tick(started+timeout_s)
    return dict(ok=True,scope_only=True,native_drc_and_full_context_receiving_required=True,
        release_authority=False,physical_change_authority=False)
