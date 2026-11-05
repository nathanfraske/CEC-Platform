"""Clear optional nonpolar chip body strokes from their own authored labels.

Only exact symmetric library body lines of a two-land, nonpolar metric C/R
may be omitted. Every retained label, pad, courtyard, fabrication drawing,
model, pose, conductor, fill, rule and unrelated native node is Source-owned.
This is not text suppression, a polarity-marker eraser or clearance/release
qualification. The enclosing atomic placement still needs full native DRC.
"""
import math,re,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_qualified_courtyard_restore as courtyard
from cec_native_items import create_empty_board,discard_footprint_children

ROOT=Path(__file__).resolve().parents[1]


def _settings(selected_footprint_uuids,board_hint,timeout_s):
    if (type(selected_footprint_uuids) not in (list,tuple)
            or not 1<=len(selected_footprint_uuids)<=8
            or any(type(u) is not str or not u for u in selected_footprint_uuids)
            or len(set(selected_footprint_uuids))!=len(selected_footprint_uuids)
            or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_nonpolar_body_silk_scope_required')


def _line(item):
    if (item.GetClass()!='PCB_SHAPE' or item.GetShape()!=pcbnew.SHAPE_T_SEGMENT
            or item.IsAnyFill() or not 50000<=item.GetWidth()<=300000
            or item.GetStart()==item.GetEnd()):
        raise ValueError('exact_unfilled_symmetric_library_body_lines_required')
    return (int(item.GetLayer()),int(item.GetWidth()),
        tuple(sorted((tuple(item.GetStart()),tuple(item.GetEnd())))))


def _body(fp,bindings):
    """Match actual complete lands and ink, not a claimed library name alone."""
    name=str(fp.GetFPID().GetLibItemName())
    match=re.fullmatch(r'([CR])_(0201|0402|0603|0805|1206|1210)_[0-9]{4}Metric',name)
    namespace={'C':'Capacitor_SMD','R':'Resistor_SMD'}.get(match[1]) if match else None
    nickname=str(fp.GetFPID().GetLibNickname())
    if (not namespace or nickname not in (namespace,'cec-'+namespace) or fp.IsDNP() or fp.IsLocked()
            or fp.GetOrientationDegrees()%90 or not fp.Reference().IsVisible()
            or fp.Reference().GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS)
            or not fp.Reference().GetText().strip()):
        raise ValueError('source_visible_reference_and_exact_nonpolar_chip_identity_required')
    path=ROOT/'lib/vendor'/(namespace+'.pretty')/(name+'.kicad_mod')
    if not path.is_file():raise ValueError('actual_vendored_nonpolar_body_template_required')
    bindings[str(path.resolve())]=force._hash(path)
    template=pcbnew.FootprintLoad(str(path.parent),name)
    if template is None:raise ValueError('native_nonpolar_body_template_load_refused')
    if (len(list(fp.Pads()))!=2 or {p.GetNumber() for p in fp.Pads()}!={'1','2'}
            or courtyard.lands(fp)!=courtyard.lands(template)):
        raise ValueError('complete_unmodified_nonpolar_chip_land_pattern_required')
    owner=create_empty_board();owner.SetCopperLayerCount(fp.GetBoard().GetCopperLayerCount());owner.Add(template)
    if fp.IsFlipped():template.Flip(pcbnew.VECTOR2I(0,0),False)
    template.SetOrientationDegrees(fp.GetOrientationDegrees());template.SetPosition(fp.GetPosition())
    silk=pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS
    canonical=[g for g in template.GraphicalItems() if g.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)]
    if len(canonical)!=2:raise ValueError('two_symmetric_optional_nonpolar_body_strokes_required')
    shapes=[_line(g) for g in canonical];at=tuple(fp.GetPosition())
    reflected=(shapes[0][0],shapes[0][1],tuple(sorted(tuple(2*at[i]-p[i] for i in (0,1)) for p in shapes[0][2])))
    if (shapes[0]==shapes[1] or reflected!=shapes[1] or any(q[0]!=silk for q in shapes)):
        raise ValueError('polarity_or_unknown_body_art_cannot_be_suppressed')
    body=[g for g in fp.GraphicalItems() if g.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)]
    signatures=[_line(g) for g in body]
    if len(set(signatures))!=len(signatures) or any(q not in shapes for q in signatures):
        raise ValueError('source_body_art_differs_from_symmetric_library_template')
    return body


def plan(source,*,selected_footprint_uuids,board_hint,timeout_s=10.):
    _settings(selected_footprint_uuids,board_hint,timeout_s)
    started=time.monotonic();source=Path(source).resolve()
    epoch=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));owners={force._uid(f):f for f in board.GetFootprints()}
    if not set(selected_footprint_uuids)<=owners.keys():raise ValueError('actual_nonpolar_body_owner_identity_required')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    # KiCad's live group resolver may omit a nested footprint child. Its
    # authored UUID membership is still ownership, never permission to erase.
    _,nodes=additive._nodes(source)
    grouped.update(u for node in nodes.values() if node[0]=='group' for u in additive._members(node))
    gap=max(150000,int(board.GetDesignSettings().m_SilkClearance));bindings={};records=[]
    for uid in sorted(selected_footprint_uuids):
        if time.monotonic()-started>=timeout_s:raise ValueError('nonpolar_body_silk_source_deadline')
        fp=owners[uid]
        if uid in grouped:raise ValueError('group_owned_nonpolar_body_graphics_refused')
        for graphic in _body(fp,bindings):
            if force._uid(graphic) in grouped or graphic.IsLocked():
                raise ValueError('locked_or_group_owned_nonpolar_body_stroke_refused')
            fields=[f for f in (fp.Reference(),fp.Value()) if f.IsVisible() and f.GetLayer()==graphic.GetLayer()
                and f.GetEffectiveTextShape().Collide(graphic.GetEffectiveShape(),gap)]
            if fields:
                signature=_line(graphic)
                records.append(dict(footprint_uuid=uid,graphic_uuid=force._uid(graphic),
                    colliding_authored_field_uuids=sorted(force._uid(f) for f in fields),
                    source_body_segment=dict(layer=signature[0],width_nm=signature[1],
                        endpoints_nm=[list(p) for p in signature[2]])))
    if (time.monotonic()-started>=timeout_s or epoch!=force._code_identity()
            or family!=force._family(source,board_hint)
            or any(force._hash(Path(p))!=h for p,h in bindings.items())):
        raise ValueError('nonpolar_body_silk_source_code_or_library_changed')
    return dict(schema=1,scope='source_exact_optional_nonpolar_chip_body_strokes_only',
        source=str(source),source_sha256=force._hash(source),board_hint=board_hint,
        selected_footprint_uuids=sorted(selected_footprint_uuids),timeout_s=timeout_s,code_identity=epoch,
        input_sha256=bindings,effective_silk_clearance_nm=gap,records=records,
        source_label_strings_fonts_poses_visibility_layers_unchanged=True,
        no_copper_or_placement_authority=True,routing_admitted=False,fab_ready=False,release_authority=False)


def construct(source,proposal):
    fresh=plan(source,selected_footprint_uuids=proposal['selected_footprint_uuids'],
        board_hint=proposal['board_hint'],timeout_s=proposal['timeout_s'])
    if fresh!=proposal:raise ValueError('stale_or_forged_nonpolar_body_silk_plan')
    board=pcbnew.LoadBoard(str(source));owners={force._uid(f):f for f in board.GetFootprints()}
    for uid in proposal['selected_footprint_uuids']:
        cuts={r['graphic_uuid'] for r in fresh['records'] if r['footprint_uuid']==uid}
        if cuts:discard_footprint_children(board,owners[uid],
            [g for g in owners[uid].GraphicalItems() if force._uid(g) in cuts])
    return board


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    report=dict(ok=False,complete=False,errors=[],routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        _settings(proposal['selected_footprint_uuids'],board_hint,timeout_s)
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate));started=time.monotonic()
        if source==candidate or board_hint!=proposal['board_hint']:
            raise ValueError('distinct_exact_nonpolar_silk_source_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        expected=construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-nonpolar-body-silk-') as work:
            projected=Path(work)/'exact-source-with-optional-body-lines-cleared.kicad_pcb'
            field._save_field_snapshot(expected,projected)
            first,_=additive._nodes(projected);last,_=additive._nodes(candidate)
            if syntax._freeze(first)!=syntax._freeze(last):
                raise ValueError('nonpolar_body_silk_edit_changed_unowned_source_native_evidence')
        if force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('nonpolar_body_silk_edit_changed_project_or_process_rules')
        if (time.monotonic()-started>=timeout_s or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]
                or any(force._hash(Path(p))!=h for p,h in proposal['input_sha256'].items())):
            raise ValueError('nonpolar_body_silk_receiving_epoch_or_lease_changed')
        report.update(ok=True,complete=True,changed=bool(proposal['records']),code_identity=epoch,
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            removed_body_graphic_uuids=[r['graphic_uuid'] for r in proposal['records']],
            modified_footprint_uuids=sorted({r['footprint_uuid'] for r in proposal['records']}),
            all_source_labels_copper_pads_fills_courtyards_fab_drawings_poses_models_and_rules_exact=True,
            independent_complete_native_source_replay_matched=True,source_family_and_code_unchanged=True,
            full_native_DRC_placement_current_Kelvin_stack_and_visual_receiving_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
