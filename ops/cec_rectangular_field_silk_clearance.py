"""Bounded source/template-exact rectangular field ink clearance.

Only four plain silkscreen perimeter strokes may expand outward. No pad,
courtyard, fabrication drawing, functional mark, field or library is edited.
Native DRC/library comparison and whole-board admission remain separate.
"""
import math
import tempfile
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_source_retaining_ses_import as raw
import cec_board_geometry as geometry
import cec_fab_profile as fab
import cec_fab_check as fabcheck


def _require(ok, reason):
    if not ok:raise ValueError(reason)


def _line(g):
    _require(g.GetClass()=='PCB_SHAPE' and g.GetShape()==pcbnew.SHAPE_T_SEGMENT
        and not g.IsAnyFill() and g.GetStart()!=g.GetEnd(),'plain_unfilled_frame_stroke_required')
    return (int(g.GetLayer()),int(g.GetWidth()),tuple(g.GetStart()),tuple(g.GetEnd()))


def _frame(fp):
    face=pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS
    lines=[g for g in fp.GraphicalItems()if g.GetLayer()==face and g.GetClass()=='PCB_SHAPE']
    _require(len(lines)==4,'exact_four_stroke_silk_frame_required')
    rows=[_line(g)for g in lines];points={p for _,_,a,b in rows for p in (a,b)}
    xs=sorted({p[0]for p in points});ys=sorted({p[1]for p in points})
    _require(len(xs)==len(ys)==2 and len(points)==4 and len({r[1]for r in rows})==1,
        'one_cardinal_closed_rectangle_required')
    expected={frozenset((a,b))for a,b in (((xs[0],ys[0]),(xs[1],ys[0])),
        ((xs[1],ys[0]),(xs[1],ys[1])),((xs[1],ys[1]),(xs[0],ys[1])),((xs[0],ys[1]),(xs[0],ys[0])))}
    _require({frozenset((a,b))for _,_,a,b in rows}==expected,'closed_distinct_frame_sides_required')
    return lines,[xs[0],ys[0],xs[1],ys[1]],rows[0][1],face


def _normal(original):
    owner=pcbnew.BOARD();owner.SetCopperLayerCount(6);fp=pcbnew.FOOTPRINT(original);owner.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(0,0))
    if fp.IsFlipped():fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(0)
    for pad in fp.Pads():pad.SetNetCode(0)
    return owner,fp


def _semantic(fp):
    """Complete native pad/art/model trees; only instance identity/net/fields excluded."""
    owner,normal=_normal(fp)
    with tempfile.TemporaryDirectory(prefix='cec-field-template-')as work:
        # This disposable normalized copy is comparison material, never an
        # output board. Native serialization canonicalizes PTH wildcard masks
        # after the inverse flip; actual source/candidate masks remain exact.
        p=Path(work)/'board.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(p),owner)
        node=next(v for v in additive._nodes(p)[1].values()if v[0]=='footprint')
    def clean(n):
        if not isinstance(n,list):return n
        if n and n[0]=='attr':return [c for c in n if c!='exclude_from_bom']
        return [clean(c)for c in n if not(isinstance(c,list)and c and c[0]in
            ('uuid','tstamp','net','pinfunction','pintype'))]
    selected=[clean(c)for c in node if isinstance(c,list)and c and c[0]in
        ('pad','fp_line','fp_arc','fp_rect','fp_poly','fp_circle','fp_text','fp_text_box','model','attr',
         'solder_mask_margin','solder_paste_margin','solder_paste_ratio','clearance',
         'zone_connect','thermal_width','thermal_gap','net_tie_pad_groups')
        and not(c[0]=='fp_text'and len(c)>1 and c[1]in ('reference','value'))]
    return sorted((syntax._freeze(c)for c in selected if c!=['attr']),key=repr)


def _poly(item,layer,clearance=0):
    p=pcbnew.SHAPE_POLY_SET()
    if hasattr(item,'TransformTextToPolySet'):item.TransformTextToPolySet(p,clearance,1,pcbnew.ERROR_OUTSIDE)
    else:item.TransformShapeToPolygon(p,layer,clearance,1,pcbnew.ERROR_OUTSIDE)
    return p


def _mask_openings(board,face,via_ink_policy='reserve_native_lands'):
    _require(type(via_ink_policy)is str and via_ink_policy in
        ('reserve_native_lands','native_mask_and_bore'),'explicit_native_via_ink_policy_required')
    mask=pcbnew.F_Mask if face==pcbnew.F_SilkS else pcbnew.B_Mask
    cu=pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu
    rows=[]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(mask):rows.append((force._uid(p),_poly(p,cu,int(p.GetSolderMaskExpansion(mask)))))
            if p.HasHole():
                poly=pcbnew.SHAPE_POLY_SET();p.GetEffectiveHoleShape().TransformToPolygon(poly,1,pcbnew.ERROR_OUTSIDE)
                rows.append((force._uid(p)+':hole',poly))
    for v in board.GetTracks():
        if v.GetClass()=='PCB_VIA'and v.IsOnLayer(cu):
            if via_ink_policy=='reserve_native_lands':
                # Historical conservative policy remains unchanged by default.
                rows.append((force._uid(v),_poly(v,cu)))
            else:
                # Match the actual native mask, but NEVER erase the drill
                # keepout. KiCad 10's silk checker substitutes the effective
                # hole shape for a tented drilled item. HasSolderMask() is an
                # inherited TRACK setting, not this via aperture's authority.
                modes=(pcbnew.TENTING_MODE_FROM_BOARD,pcbnew.TENTING_MODE_TENTED,
                    pcbnew.TENTING_MODE_NOT_TENTED)
                mode=v.GetFrontTentingMode()if face==pcbnew.F_SilkS else v.GetBackTentingMode()
                _require(mode in modes,'unknown_native_via_tenting_mode')
                tented=bool(v.IsTented(face))
                _require(bool(v.IsOnLayer(mask))==(not tented),'inconsistent_native_via_mask_aperture')
                if not tented:rows.append((force._uid(v),_poly(v,cu,int(v.GetSolderMaskExpansion()))))
                poly=pcbnew.SHAPE_POLY_SET();v.GetEffectiveHoleShape().TransformToPolygon(poly,1,pcbnew.ERROR_OUTSIDE)
                rows.append((force._uid(v)+':hole',poly))
    for item in [*board.GetDrawings(),*(g for f in board.GetFootprints()for g in [*f.GraphicalItems(),*f.GetFields()])]:
        if item.GetLayer()==mask and(not hasattr(item,'IsVisible')or item.IsVisible()):rows.append((force._uid(item),_poly(item,mask)))
    _require(len(rows)<=16384,'bounded_native_mask_opening_inventory_required')
    return rows


def _set_bounds(lines,old,new):
    for g in lines:
        a,b=tuple(g.GetStart()),tuple(g.GetEnd())
        def point(p):return (new[0]if p[0]==old[0]else new[2],new[1]if p[1]==old[1]else new[3])
        g.SetStart(pcbnew.VECTOR2I(*point(a)));g.SetEnd(pcbnew.VECTOR2I(*point(b)))


def _floors(board,source,factory_legend_policy=None):
    _require(factory_legend_policy is None or type(factory_legend_policy)is str
        and factory_legend_policy=='jlcpcb','unknown_or_conflicting_factory_legend_policy')
    name=fab.board_profile_name(board)
    declared={str(k):str(v)for k,v in board.GetProperties().asdict().items()}.get('CEC_FAB_PROFILE')
    _require(not declared or name is not None,'unknown_embedded_factory_profile')
    _require(name is not None or factory_legend_policy=='jlcpcb','declared_factory_legend_profile_required')
    vendor=fabcheck.PROFILES['jlcpcb']
    # No copper/process inference for annotation-only authority.
    rules=(fabcheck.profile_rules(vendor,fabcheck.board_outer_copper_oz(source),name)if name else
        dict(silk_clearance=vendor['min_silk_clearance'],edge=vendor['min_copper_edge'],silk=vendor['min_silk_width']))
    ds=board.GetDesignSettings()
    return dict(profile=name,factory_legend_policy=factory_legend_policy,
        factory_annotation_rules={k:rules[k]for k in('silk_clearance','edge','silk')},
        clearance_nm=max(round(rules['silk_clearance']*1e6),int(ds.m_SilkClearance)),
        edge_nm=max(round(max(rules['edge'],rules['silk_clearance'])*1e6),int(ds.m_SilkClearance)),
        stroke_nm=max(round(rules['silk']*1e6),int(ds.m_MinSilkTextThickness)))


def _final_guard(board,records,floors):
    outline=geometry.outline_material(board);boundaries=geometry.material_boundaries(outline)
    for r in records:
        fp=next(f for f in board.GetFootprints()if force._uid(f)==r['footprint_uuid']);lines,box,width,face=_frame(fp)
        ids={force._uid(g)for g in lines};openings=_mask_openings(board,face,
            floors.get('via_ink_policy','reserve_native_lands'))
        ink=[i for i in [*board.GetDrawings(),*(g for f in board.GetFootprints()for g in [*f.GraphicalItems(),*f.GetFields()])]
            if i.GetLayer()==face and force._uid(i)not in ids and(not hasattr(i,'IsVisible')or i.IsVisible())]
        for g in lines:
            _require(geometry.material_leg_clear(outline,boundaries,g.GetStart(),g.GetEnd(),
                (width+1)//2+floors['edge_nm']),'expanded_frame_native_material_edge_clearance_refused')
            _require(not any(p.Collide(g.GetEffectiveShape(),floors['clearance_nm'])for _,p in openings),
                'expanded_frame_native_mask_clearance_refused')
            _require(not any(_poly(i,face).Collide(g.GetEffectiveShape(),floors['clearance_nm'])for i in ink),
                'expanded_frame_other_source_ink_clearance_refused')


def plan(source,*,selections,board_hint,timeout_s=10.,max_shift_mm=1.,factory_legend_policy=None,
         via_ink_policy='reserve_native_lands'):
    _require(type(selections)in(list,tuple)and 1<=len(selections)<=8
        and all(type(r)is dict and set(r)=={'footprint_uuid','template_path'}for r in selections)
        and len({r['footprint_uuid']for r in selections})==len(selections)
        and type(board_hint)is str and bool(board_hint)
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10
        and type(max_shift_mm)in(int,float)and math.isfinite(max_shift_mm)and 0<max_shift_mm<=2,
        'bounded_explicit_frame_template_selection_required')
    _require(type(via_ink_policy)is str and via_ink_policy in
        ('reserve_native_lands','native_mask_and_bore'),'explicit_native_via_ink_policy_required')
    start=time.monotonic();deadline=start+timeout_s
    def tick():_require(time.monotonic()<deadline,'field_frame_plan_deadline')
    source=Path(source).resolve();code=force._code_identity();family=force._family(source,board_hint)
    authority={str(Path(__file__).resolve()):force._hash(Path(__file__).resolve())}
    b=pcbnew.LoadBoard(str(source));floors=_floors(b,source,factory_legend_policy);fps={force._uid(f):f for f in b.GetFootprints()}
    if via_ink_policy!='reserve_native_lands':floors['via_ink_policy']=via_ink_policy
    _,nodes=additive._nodes(source);source_groups={u for u,node in nodes.items()if node[0]=='group'}
    _require(source_groups=={force._uid(g)for g in b.Groups()}and all(list(g.GetItems())for g in b.Groups()),
        'nonroundtrip_source_group_requires_separate_owner')
    grouped={u for node in nodes.values()if node[0]=='group'for u in additive._members(node)}
    records=[];normalized=[]
    for selected in sorted(selections,key=lambda r:r['footprint_uuid']):
        tick();fp=fps.get(selected['footprint_uuid']);_require(fp is not None,'actual_source_frame_owner_required')
        path=Path(selected['template_path']).resolve();_require(path.is_file()and path.suffix=='.kicad_mod','independent_native_template_path_required')
        authority[str(path)]=force._hash(path);template=pcbnew.FootprintLoad(str(path.parent),path.stem)
        _require(template is not None and _semantic(fp)==_semantic(template),'complete_independent_template_pad_art_model_equivalence_required')
        _require(not fp.IsLocked()and not fp.IsDNP()and force._uid(fp)not in grouped and not fp.GetParentGroup(),
            'active_unlocked_ungrouped_frame_owner_required')
        _require(fp.GetOrientationDegrees()%90==0,'cardinal_source_frame_pose_required')
        lines,old,width,face=_frame(fp);_frame(template)
        _require(width>=floors['stroke_nm']and width<=300000,'unchanged_readable_native_frame_stroke_required')
        _require(all(not g.IsLocked()and force._uid(g)not in grouped for g in lines),'locked_or_group_owned_frame_stroke_refused')
        openings=_mask_openings(b,face,via_ink_policy);new=old[:];margin=(width+1)//2+floors['clearance_nm']+2
        touched=set()
        for _ in range(16):
            tick();changed=False
            for g in lines:
                a,z=tuple(g.GetStart()),tuple(g.GetEnd());horizontal=a[1]==z[1]
                side=(1 if a[1]==new[1]else 3)if horizontal else(0 if a[0]==new[0]else 2)
                for uid,poly in openings:
                    if not poly.Collide(g.GetEffectiveShape(),floors['clearance_nm']):continue
                    bb=poly.BBox();value={0:bb.GetLeft()-margin,1:bb.GetTop()-margin,
                        2:bb.GetRight()+margin,3:bb.GetBottom()+margin}[side]
                    before=new[side];new[side]=min(before,value)if side in(0,1)else max(before,value)
                    touched.add(uid);changed|=new[side]!=before
            _require(max(abs(a-z)for a,z in zip(old,new))<=round(max_shift_mm*1e6),'bounded_outward_frame_expansion_exceeded')
            if not changed:break
            _set_bounds(lines,[min(g.GetStart().x for g in lines),min(g.GetStart().y for g in lines),
                max(g.GetStart().x for g in lines),max(g.GetStart().y for g in lines)],new)
        else:raise ValueError('finite_frame_clearance_events_exhausted')
        records.append(dict(footprint_uuid=force._uid(fp),template_path=str(path),source_bounds_nm=old,
            target_bounds_nm=new,layer_id=int(face),stroke_nm=width,
            graphic_uuids=sorted(force._uid(g)for g in lines),native_mask_obstacles=sorted(touched)))
        normalized.append(dict(footprint_uuid=force._uid(fp),template_path=str(path)))
    _final_guard(b,records,floors);tick()
    _require(code==force._code_identity()and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in authority.items()),'frame_source_code_or_template_changed')
    result=dict(schema=1,scope='source_template_exact_rectangular_field_ink_expansion',source=str(source),
        source_sha256=force._hash(source),source_family=family,code_identity=code,authority_sha256=authority,
        board_hint=board_hint,selections=normalized,timeout_s=timeout_s,max_shift_mm=max_shift_mm,
        factory_legend_policy=factory_legend_policy,
        factory_floors=floors,records=records,changed=any(r['source_bounds_nm']!=r['target_bounds_nm']for r in records),
        canonical_library_changed=False,current_authority=False,placement_authority=False,
        fab_ready=False,release_authority=False)
    if via_ink_policy!='reserve_native_lands':result['via_ink_policy']=via_ink_policy
    return result


def construct(source,proposal):
    fresh=plan(source,via_ink_policy=proposal.get('via_ink_policy','reserve_native_lands'),
        **{k:proposal[k]for k in('selections','board_hint','timeout_s','max_shift_mm','factory_legend_policy')})
    _require(fresh==proposal,'stale_or_forged_rectangular_field_plan')
    b=pcbnew.LoadBoard(str(source));fps={force._uid(f):f for f in b.GetFootprints()}
    for r in fresh['records']:
        lines,old,_,_=_frame(fps[r['footprint_uuid']]);_set_bounds(lines,old,r['target_bounds_nm'])
    _final_guard(b,fresh['records'],fresh['factory_floors']);return b


def _replace_endpoints(original,native):
    def nodes(text):return {raw.kind(text[a:b]):(a,b,text[a:b])for a,b in raw.children(text)
        if raw.kind(text[a:b])in('start','end')}
    a,b=nodes(original),nodes(native);_require(set(a)==set(b)=={'start','end'},'exact_native_frame_endpoint_nodes_required')
    result=original
    for key in sorted(a,key=lambda k:a[k][0],reverse=True):
        x,y,_=a[key];result=result[:x]+b[key][2]+result[y:]
    return result


def _literal(source_text,native_text,records):
    before=raw.inventory(source_text);after=raw.inventory(native_text);result=source_text
    for r in sorted(records,key=lambda r:before[r['footprint_uuid']][0],reverse=True):
        uid=r['footprint_uuid'];a,b=before[uid];x,y=after[uid];old=source_text[a:b];new=native_text[x:y]
        def graphics(text):return {raw.node_uuid(text[i:j]):(i,j,text[i:j])for i,j in raw.children(text)
            if raw.kind(text[i:j])=='fp_line'}
        og,ng=graphics(old),graphics(new);edited=old
        for gid in sorted(r['graphic_uuids'],key=lambda g:og[g][0],reverse=True):
            i,j,text=og[gid];edited=edited[:i]+_replace_endpoints(text,ng[gid][2])+edited[j:]
        result=result[:a]+edited+result[b:]
    return result


def write_private(source,candidate,proposal):
    """Caller supplies an exact private family copy; preserve all opaque Source text."""
    source,candidate=Path(source).resolve(),Path(candidate).resolve()
    _require(source!=candidate and force._hash(source)==force._hash(candidate),'exact_private_frame_source_copy_required')
    board=construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-field-ink-')as work:
        p=Path(work)/'native.kicad_pcb';field._save_field_snapshot(board,p)
        text=_literal(raw.raw_text(source),raw.raw_text(p),proposal['records'])
    raw.write_raw(candidate,text)
    return dict(candidate=str(candidate),sha256=force._hash(candidate),unadmitted=True)


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_authority=False,fab_ready=False,release_authority=False)
    try:
        _require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_frame_receiving_required')
        started=time.monotonic();source,candidate=Path(source).resolve(),Path(candidate).resolve()
        _require(source!=candidate and board_hint==proposal['board_hint'],'distinct_exact_frame_source_candidate_required')
        families=[force._family(p,board_hint)for p in(source,candidate)];code=force._code_identity();board=construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-field-receive-')as work:
            p=Path(work)/'native.kicad_pcb';field._save_field_snapshot(board,p)
            expected=_literal(raw.raw_text(source),raw.raw_text(p),proposal['records'])
            _require(expected==raw.raw_text(candidate),'frame_edit_changed_unowned_literal_source_evidence')
            first=Path(work)/'first.kicad_pcb';second=Path(work)/'second.kicad_pcb'
            child=pcbnew.LoadBoard(str(candidate));_final_guard(child,proposal['records'],proposal['factory_floors'])
            field._save_field_snapshot(child,first);field._save_field_snapshot(pcbnew.LoadBoard(str(first)),second)
            _require(syntax._freeze(additive._nodes(first)[0])==syntax._freeze(additive._nodes(second)[0]),'frame_native_second_save_not_stable')
        _require(force._sidecars(source)==force._sidecars(candidate),'frame_edit_changed_source_sidecars')
        _require(time.monotonic()-started<timeout_s and code==force._code_identity()
            and families==[force._family(p,board_hint)for p in(source,candidate)],'frame_receiving_identity_or_deadline_changed')
        r.update(ok=True,complete=True,literal_all_source_except_declared_frame_endpoints_exact=True,
            native_second_save_stable=True,source_templates_unchanged=True,
            canonical_library_publication_and_native_drc_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def template_proposal(source,proposal,footprint_uuid):
    """Return an independent template derivative; never save over the authority."""
    board=construct(source,proposal);record=next(r for r in proposal['records']if r['footprint_uuid']==footprint_uuid)
    fp=next(f for f in board.GetFootprints()if force._uid(f)==footprint_uuid);owner,normal=_normal(fp)
    original=pcbnew.LoadBoard(str(source));old=next(f for f in original.GetFootprints()if force._uid(f)==footprint_uuid)
    oldowner,oldnormal=_normal(old);oldlines,_,_,_=_frame(oldnormal);newlines,_,_,_=_frame(normal)
    geometry_by_uid={force._uid(g):g for g in newlines}
    path=Path(record['template_path']);template=pcbnew.FootprintLoad(str(path.parent),path.stem)
    # Keep the independent library owner alive during native edits/export.
    library=pcbnew.BOARD();library.SetCopperLayerCount(6);library.Add(template)
    candidates=list(template.GraphicalItems())
    for g in oldlines:
        signature=_line(g);hits=[t for t in candidates if t.GetClass()=='PCB_SHAPE'
            and t.GetShape()==pcbnew.SHAPE_T_SEGMENT and _line(t)==signature]
        _require(len(hits)==1,'unique_independent_template_frame_side_required')
        new=geometry_by_uid[force._uid(g)];hits[0].SetStart(new.GetStart());hits[0].SetEnd(new.GetEnd())
    return library,template


def export_template_proposals(source,proposal,out):
    """Create separately named review artifacts; no canonical asset/BOM/FPID ECO."""
    out=Path(out).resolve();_require(not out.exists(),'fresh_private_template_proposal_directory_required');out.mkdir(parents=True)
    rows=[]
    for r in proposal['records']:
        library,fp=template_proposal(source,proposal,r['footprint_uuid']);directory=out/(r['footprint_uuid']+'.pretty');directory.mkdir()
        pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(directory),fp);files=list(directory.glob('*.kicad_mod'));_require(len(files)==1,'single_native_template_proposal_required')
        rows.append(dict(source_template=r['template_path'],source_sha256=proposal['authority_sha256'][r['template_path']],
            footprint_uuid=r['footprint_uuid'],proposal_path=str(files[0]),proposal_sha256=force._hash(files[0])))
    force._write(out/'receipt.json',dict(records=rows,canonical_library_changed=False,release_authority=False));return rows
