"""Receive an anchor-preserving orphan support pivot and ordinary additions.

This narrow receiver does not widen the selected-bypass receiver. A movable
two-land support must keep an actual rectangular/roundrect land fixed; its
other land must be an isolated source terminal. Every original native copper
and terminal partition survives. Poses are reconstructed from the parent,
never copied from the child. Placement, rated current and release authority
are not rebound. This receipt only establishes a nonregressing private slice.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_force_current as force
import cec_native_fill_geometry as native
import cec_ordinary_route_receiving as ordinary
import cec_placement_geometry as geometry
import cec_route_placement_admission as placement
import cec_stage_admission as stage
import cec_support_motion as motion


def _fixed_land(pad):
    """Exact physical identity for an offset-free, drill-free symmetric land."""
    if (pad is None or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT)
            or tuple(pad.GetOffset())!=(0,0) or pad.HasHole()):
        return None
    layers=tuple(map(int,pad.GetLayerSet().CuStack()));shapes=[]
    for layer in layers:
        polygon=pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(polygon,layer,0,1,pcbnew.ERROR_OUTSIDE,False)
        shapes.append(native.identity(polygon,time.monotonic()+2.,max_vertices=4096)[0])
    return (str(pad.GetNumber()),force._uid(pad),str(pad.GetNetname()),
        tuple(pad.GetPosition()),tuple(pad.GetSize()),int(pad.GetShape()),
        pad.GetRoundRectRadiusRatio(),layers,tuple(shapes))


def _silk_inventory(board, nodes):
    """Authored identities; a pad is bound to its complete native owner."""
    result={}
    for fp in board.GetFootprints():
        owner=force._uid(fp)
        for item in [*fp.GetFields(),*fp.GraphicalItems(),*fp.Pads()]:
            uid=force._uid(item)
            if uid in result:raise ValueError('ambiguous_native_silk_identity')
            result[uid]=(item,nodes[owner])
    for item in board.GetDrawings():
        uid=force._uid(item)
        if uid in result:raise ValueError('ambiguous_native_silk_identity')
        if uid in nodes:result[uid]=(item,nodes[uid])
    return result


def _inherited_silk_overlap(parent, child, finding, old_nodes, new_nodes, *, inventories=None):
    """Positive source collision, not a waiver or a count-based inference.

    Native reports may select different subsets of a crowded silk inventory.
    Only two exact unchanged authored source items with a positive native
    collision can be marked inherited. For a pad-mask finding, actual copper
    collision is a sufficient, deliberately conservative witness only when
    the native mask aperture contains that copper (nonnegative expansion).
    Mask-only near misses, new/moved geometry and other types stay new. The
    overlap still remains fabrication/legibility debt.
    """
    kind=finding.get('type')
    if kind not in ('silk_overlap','silk_over_copper') or len(finding.get('items') or ())!=2:return None
    first,last=(inventories if inventories is not None else
        (_silk_inventory(parent,old_nodes),_silk_inventory(child,new_nodes)))
    ids=[item.get('uuid') for item in finding['items']]
    if any(uid not in first or uid not in last or
        sexpr._freeze(first[uid][1])!=sexpr._freeze(last[uid][1]) for uid in ids):return None
    items=[first[u][0] for u in ids]
    def shape(item):
        return item.GetEffectiveTextShape() if hasattr(item,'GetEffectiveTextShape') else item.GetEffectiveShape()
    if kind=='silk_overlap':
        if items[0].GetLayer()!=items[1].GetLayer() or items[0].GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS):return None
        # A direct overlap is stronger than any positive-clearance silk rule.
        if not shape(items[0]).Collide(shape(items[1]),0):return None
    else:
        pads=[i for i in items if i.GetClass()=='PAD']
        if len(pads)!=1:return None
        pad=pads[0];silk=next(i for i in items if i.GetClass()!='PAD')
        layers={pcbnew.F_SilkS:(pcbnew.F_Cu,pcbnew.F_Mask),
                pcbnew.B_SilkS:(pcbnew.B_Cu,pcbnew.B_Mask)}
        if silk.GetLayer() not in layers:return None
        copper,mask=layers[silk.GetLayer()]
        if not pad.IsOnLayer(copper) or not pad.IsOnLayer(mask):return None
        last_pad=last[force._uid(pad)][0]
        expansion=pad.GetSolderMaskExpansion(copper)
        if expansion<0 or expansion!=last_pad.GetSolderMaskExpansion(copper):return None
        if not shape(silk).Collide(pad.GetEffectiveShape(copper),0):return None
    return dict(type=kind,item_uuids=sorted(ids),
        exact_authored_source_geometry=True,native_source_collision=True,
        inherited_debt_qualified=False,release_authority=False)


def source_land_isolated(board, pad, graph):
    """Actual native contact, including inherited foreign shorts, not a DRC row."""
    if any(force._item_key(i)!=force._item_key(pad) for i in graph.GetConnectedItems(pad)):
        return False
    # Native connectivity queries are net-filtered. A foreign track/pad/zone
    # touching the source land must not disappear from its movement contract.
    material=[*(p for fp in board.GetFootprints() for p in fp.Pads()),
        *board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for other in material:
        if other.GetNetCode()==pad.GetNetCode():
            continue
        for layer in pad.GetLayerSet().CuStack():
            if not other.IsOnLayer(layer):
                continue
            if other.GetClass()=='ZONE':
                if not other.IsFilled():
                    raise ValueError('source_isolated_land_foreign_fill_unknown')
                shape=other.GetFilledPolysList(layer)
            else:
                shape=other.GetEffectiveShape(layer)
            if shape.Collide(pad.GetEffectiveShape(layer),0):
                return False
    return True


def receive(source, candidate, *, board_hint, timeout_s=10., fully_isolated_reseat=False,
            allow_support_field_reflow=False):
    started=time.monotonic();report=dict(schema=1,ok=False,complete=False,errors=[],
        scope='native_fixed_land_orphan_support_pivot_receiving',release_authority=False,
        routing_admitted=False,power_authority=False,placement_authority_transferred=False,
        support_field_reflow_requested=allow_support_field_reflow)
    try:
        if type(fully_isolated_reseat) is not bool or type(allow_support_field_reflow) is not bool:
            raise ValueError('explicit_isolated_reseat_mode_required')
        if fully_isolated_reseat:
            report['scope'] = 'native_fully_isolated_ordinary_support_reseat_receiving'
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('bounded_support_pivot_receiving_required')
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(candidate))
        if placement._population(parent)!=placement._population(child):
            raise ValueError('support_pivot_component_or_pad_definition_changed')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        fps={fp.GetReference():fp for fp in parent.GetFootprints()}
        changed=[ref for ref,fp in fps.items() if sexpr._freeze(old[force._uid(fp)])
            !=sexpr._freeze(new[force._uid(fp)])]
        if not 1<=len(changed)<=motion.MAX_REFS:raise ValueError('bounded_nonempty_support_pivots_required')
        old_parts=ordinary._partition(parent,time.monotonic()+timeout_s)
        retained=set().union(*old_parts)
        old_pad_keys={force._uid(p):force._item_key(p) for fp in parent.GetFootprints() for p in fp.Pads()}
        conn=pcbnew.CONNECTIVITY_DATA()
        for item in [*(p for fp in parent.GetFootprints() for p in fp.Pads()),
                     *parent.GetTracks(),*[z for z in parent.Zones() if not z.GetIsRuleArea()]]:
            if not conn.Add(item):raise ValueError('native_pivot_source_contact_unknown')
        eligible=ordinary.eligible_nets(parent,source,board_hint)
        pivots=[];orphan_keys=[]
        for ref in changed:
            fp,target=fps[ref],child.FindFootprintByReference(ref)
            delta=(target.GetOrientationDegrees()-fp.GetOrientationDegrees())%360
            domain=motion.capture(parent,dict(ref=ref),motion.limits())
            at=fp.GetPosition();to=target.GetPosition()
            proof=motion.evaluate(domain,dict(dx_mm=(to.x-at.x)/1e6,dy_mm=(to.y-at.y)/1e6,
                rotation_delta_deg=delta))
            rotations = (0,90,180,270) if fully_isolated_reseat else (90,180,270)
            if not proof['ok'] or not any(abs(delta-v)<1e-6 for v in rotations):
                raise ValueError('not_a_bounded_native_support_pivot')
            pads=list(fp.Pads());fixed=[p for p in pads if _fixed_land(p) is not None
                and _fixed_land(p)==_fixed_land(target.FindPadByNumber(str(p.GetNumber())))]
            if len({str(p.GetNumber()) for p in pads})!=len(pads):
                raise ValueError('unique_support_terminal_numbers_required')
            if len(pads)!=2:
                raise ValueError('two_actual_surface_lands_required')
            if fully_isolated_reseat:
                orphans = pads
            else:
                if len(fixed)!=1:raise ValueError('exactly_one_actual_fixed_land_required')
                orphans = [p for p in pads if force._uid(p)!=force._uid(fixed[0])]
            for orphan in orphans:
                if str(orphan.GetNetname()) not in eligible:
                    raise ValueError('moved_orphan_land_is_not_ordinary_owned')
                # In reseat mode neither an own-net contact nor an inherited
                # foreign short may be detached. A reported orphan alone is
                # not ownership of the native source terminal.
                isolated=(source_land_isolated(parent,orphan,conn) if fully_isolated_reseat else
                    not any(force._uid(i)!=force._uid(orphan) and i.GetNetCode()==orphan.GetNetCode()
                        for i in conn.GetConnectedItems(orphan)))
                if not isolated:
                    raise ValueError('moved_land_is_not_an_isolated_source_terminal')
                orphan_keys.append(force._item_key(orphan))
            row=dict(ref=ref,footprint_uuid=force._uid(fp),
                rotation_delta_deg=delta,motion=proof)
            if fully_isolated_reseat:
                row.update(source_isolated_pads=[str(p.GetNumber()) for p in pads],
                    source_ordinary_nets=sorted({str(p.GetNetname()) for p in pads}))
            else:
                row.update(fixed_pad=str(fixed[0].GetNumber()),
                    fixed_pad_position_nm=list(fixed[0].GetPosition()),
                    orphan_pad=str(orphans[0].GetNumber()))
            pivots.append(row)
        rebind={force._item_key(p):old_pad_keys[force._uid(p)] for fp in child.GetFootprints()
            if fp.GetReference() in changed for p in fp.Pads()}
        new_parts=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=retained,
            _identity_rebindings=rebind)
        if any(not any(p<=q for q in new_parts) for p in old_parts):
            raise ValueError('support_pivot_lost_original_native_conductor_partition')
        gained=[k for k in orphan_keys if any(k in p and len(p)>1 for p in new_parts)]
        if not gained:raise ValueError('support_pivot_cohort_has_no_native_orphan_connection_gain')
        report['cohort_native_orphan_connection_gain']=len(gained)
        # New material is ordinary only; no rated supply, ground, differential
        # or Kelvin construction can hide inside the pivot receipt.
        incoming=new.keys()-old.keys()
        if len(incoming)>256:raise ValueError('finite_pivot_ordinary_additions_required')
        for item in child.GetTracks():
            if force._uid(item) in incoming and str(item.GetNetname()) not in eligible:
                raise ValueError('support_pivot_incoming_material_not_ordinary')
        with tempfile.TemporaryDirectory(prefix='cec-support-pivot-') as work:
            work=Path(work);projected=force._copy_family(source,work/'projected')
            base=pcbnew.LoadBoard(str(projected))
            for ref in changed:
                fp,target=base.FindFootprintByReference(ref),child.FindFootprintByReference(ref)
                fp.SetOrientationDegrees(target.GetOrientationDegrees());fp.SetPosition(target.GetPosition())
                if allow_support_field_reflow:
                    import cec_support_field_reflow
                    cec_support_field_reflow.replay_poses(fp,target)
            field._save_field_snapshot(base,projected)
            _,replayed=additive._nodes(projected)
            if any(sexpr._freeze(replayed[force._uid(fps[ref])])!=sexpr._freeze(new[force._uid(fps[ref])])
                    for ref in changed):raise ValueError('received_support_differs_from_exact_native_pivot')
            receipt=additive.receive(projected,candidate,timeout_s=timeout_s)
            report['independent_pose_and_additive_replay']=receipt
            if receipt.get('ok') is not True or receipt.get('complete') is not True:
                raise ValueError('support_pivot_exact_source_delta_receiving_refused')
            def drc(path,label):
                isolated=force._copy_family(path,work/label);target=work/(label+'.drc.json')
                r=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all',
                    '--output',str(target),str(isolated)],capture_output=True,text=True,timeout=timeout_s)
                if r.returncode!=0:raise ValueError('support_pivot_native_drc_failed')
                return json.loads(target.read_text())
            before=drc(source,'source-grade');after=drc(candidate,'child-grade')
        known={stage._canonical_identity(v) for v in before['violations']}
        unseen=[v for v in after['violations'] if stage._canonical_identity(v) not in known]
        inherited=[];actual_new=[]
        silk_inventory=(_silk_inventory(parent,old),_silk_inventory(child,new))
        for finding in unseen:
            positive=_inherited_silk_overlap(parent,child,finding,old,new,inventories=silk_inventory)
            if positive:inherited.append(positive)
            else:actual_new.append(finding)
        report.update(pivots=pivots,original_native_conductor_and_terminal_partitions_preserved=True,
            source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),
            all_raw_drc=len(after['violations']),new_native_faults=actual_new,
            positively_proved_inherited_silk_collisions=inherited)
        if actual_new or report['opens']>=report['source_opens']:
            raise ValueError('support_pivot_has_no_nonregressing_native_benefit')
        physical=geometry.evaluate(candidate,timeout_s=timeout_s);report['physical_placement']=physical
        if physical.get('ok') is not True:raise ValueError('support_pivot_physical_placement_refused')
        # Final actual geometry is compared as well as the constructor's
        # planar preflight. Old blockers stay debt, never new allowances.
        with force._thermal_hint(board_hint):
            field_before=field.field_coupling_summary(str(source),board=parent)
            field_after=field.field_coupling_summary(str(candidate),board=child)
        field_new=field.blocker_keys(field_after)-field.blocker_keys(field_before)
        report['new_native_field_blockers']=sorted(field_new)
        if field_new:raise ValueError('support_pivot_new_native_field_coupling_blocker')
        final_families=[force._family(p,board_hint) for p in (source,candidate)];final_epoch=force._code_identity()
        stable=families==final_families and epoch==final_epoch
        report.update(source_candidate_families_before=families,source_candidate_families_after=final_families,
            code_before=epoch,code_after=final_epoch,raw_drc_exhaustiveness_certified=False)
        report['source_candidate_and_code_unchanged']=stable
        if not stable:raise ValueError('support_pivot_identity_changed')
        report.update(ok=True,complete=True,reason=('received_isolated_support_reseat_and_ordinary_delta'
            if fully_isolated_reseat else 'received_orphan_support_pivot_and_ordinary_delta'),
            added_native_uuids=sorted(incoming),retired_track_uuids=[],retired_via_uuids=[],
            board=str(candidate),board_sha256=force._hash(candidate),source_sha256=force._hash(source))
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    report['elapsed_s']=round(time.monotonic()-started,6)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--hint',required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--fully-isolated-reseat',action='store_true')
    p.add_argument('--allow-support-field-reflow',action='store_true');a=p.parse_args()
    result=receive(a.source,a.candidate,board_hint=a.hint,fully_isolated_reseat=a.fully_isolated_reseat,
        allow_support_field_reflow=a.allow_support_field_reflow)
    # Reject outputs that could replace source, candidate, sidecars or code.
    force._check_output(a.report,force._protected_paths(a.source,a.hint)|force._protected_paths(a.candidate,a.hint))
    force._write(a.report,result)
    print(json.dumps({k:result.get(k) for k in ('ok','complete','source_opens','opens','errors')}),flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
