"""Source-bound flat reinforcement trials on a paired placement proposal.

Unlike a raised jumper, a flat bar has NO routing tunnel underneath it. The
single land is real PCB copper; the separate metal gets no native ampacity or
connectivity credit. A preliminary land/paste process is never auto-promoted.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import time
import uuid
from pathlib import Path

from . import bridges, repack
from .cells import normalize_poses
from .geometry import point
from .identity import require
from .native import _native
from .legacy import ROOT


def geometry(part, candidate):
    from shapely.geometry import box
    from shapely import affinity
    require(type(part) is dict and part.get('schema') == 1
            and type(part['schema']) is int
            and part.get('mount') == 'flat_smt_reinforcement'
            and part.get('standoff_min_mm') == 0
            and part.get('unrelated_copper_underbody_permitted') is False
            and part.get('assembly_process_qualified') is False,
            'explicit_unqualified_flat_reinforcement_required')
    require(all(type(part.get(k)) is str and part[k].strip()
                for k in ('id','drawing_url','drawing_sha256','footprint','land_basis')),
            'drawing_and_land_basis_required')
    dims = part.get('dimensions_mm')
    require(type(dims) is dict and set(dims) == {'length','width','height'},
            'toleranced_flat_bar_dimensions_required')
    for pair in dims.values():
        require(type(pair) is list and len(pair) == 2
                and all(type(v) in (int,float) and math.isfinite(v) and 0<v<=100 for v in pair)
                and pair[0]<=pair[1], 'positive_bounded_bar_dimension_intervals')
    land, court = part.get('provisional_land_mm'), part.get('provisional_courtyard_mm')
    for size in (land,court):
        require(type(size) is list and len(size)==2
                and all(type(v) in (int,float) and math.isfinite(v) and 0<v<=120 for v in size),
                'explicit_bounded_land_and_courtyard_required')
    require(land[0]>dims['length'][1] and land[1]>dims['width'][1]
            and court[0]>land[0] and court[1]>land[1], 'land_must_enclose_maximum_flat_bar')
    require(type(candidate) is dict and set(candidate)=={'id','at_nm','rotation_deg','solder_allocation_nm'},
            'exact_inward_flat_bar_placement_required')
    require(type(candidate['id']) is str and 0<len(candidate['id'])<=80,
            'named_flat_bar_candidate_required')
    x,y=point(candidate['at_nm']);turn=candidate['rotation_deg']
    require(type(turn) is int and turn%90==0, 'cardinal_flat_bar_placement_required')
    solder=candidate['solder_allocation_nm']
    require(type(solder) is int and 0<solder<=1_000_000,
            'explicit_provisional_solder_height_required')
    def placed(size):
        raw=box(-size[0]/2,-size[1]/2,size[0]/2,size[1]/2)
        return affinity.translate(affinity.rotate(raw,-turn,origin=(0,0)),x/1e6,y/1e6)
    return placed([dims['length'][1],dims['width'][1]]),placed(land),placed(court)


def _read(bound):
    require(type(bound) is dict and set(bound)=={'path','sha256'},'hash_bound_bar_input_required')
    p=Path(bound['path']).resolve(strict=True)
    require(p.is_file() and p.stat().st_size<=2*1024*1024
            and repack.inspection.sha(p)==bound['sha256'],'bar_input_identity_mismatch')
    return p,json.loads(p.read_text())


def _native_land(partpath, part, candidate, land, court, *, expected_hash=None):
    """One exact, independently polygon-checked real PCB land, never bar copper."""
    pcbnew,quiet=_native()
    footprintpath=(partpath.parent/(part['footprint']+'.kicad_mod')).resolve(strict=True)
    require(footprintpath.parent==partpath.parent,'local_flat_bar_footprint_required')
    if expected_hash is not None:
        require(type(expected_hash) is str and repack.inspection.sha(footprintpath)==expected_hash,
                'flat_bar_footprint_identity_mismatch')
    fp=pcbnew.FootprintLoad(str(partpath.parent),part['footprint'])
    require(fp is not None and str(fp.GetFPID().GetLibItemName())==part['footprint']
            and fp.GetLayer()==pcbnew.F_Cu,'native_flat_bar_footprint_identity')
    pads=list(fp.Pads())
    require(len(pads)==1 and pads[0].GetNumber()=='1' and not pads[0].HasHole()
            and pads[0].GetShape()==pcbnew.PAD_SHAPE_RECT
            and list(pads[0].GetSize())==[round(v*1e6) for v in part['provisional_land_mm']]
            and list(pads[0].GetPosition())==[0,0]
            and pads[0].GetAttribute()==pcbnew.PAD_ATTRIB_SMD
            and set(pads[0].GetLayerSet().Seq())=={pcbnew.F_Cu,pcbnew.F_Mask}
            and not list(fp.Zones()) and not list(fp.Groups()) and not list(fp.Models())
            and all(g.GetLayer() in (pcbnew.F_Fab,pcbnew.F_CrtYd,pcbnew.F_SilkS)
                    for g in [*fp.GraphicalItems(),*fp.GetFields()]),
            'exact_real_reinforcement_land_without_fake_metal_or_paste')
    fp.SetOrientationDegrees(candidate['rotation_deg'])
    fp.SetPosition(pcbnew.VECTOR2I(*candidate['at_nm']))
    native_poly=pcbnew.SHAPE_POLY_SET()
    pads[0].TransformShapeToPolygon(native_poly,pcbnew.F_Cu,0,1,pcbnew.ERROR_OUTSIDE,False)
    actual_land=repack.assembly.polygon_from_native(native_poly)
    require(actual_land.symmetric_difference(land).area<1e-8,
            'native_placed_bar_land_differs_from_analyzed_land')
    actual,basis=repack.assembly.footprint_planar_envelope(fp)
    require(court.buffer(.000002,join_style='mitre').covers(actual)
            and actual.buffer(.006,join_style='mitre').covers(court),
            'flat_bar_courtyard_matches_proposal')
    return fp,footprintpath


def _footprint_items(fp):
    return [fp,*fp.Pads(),*fp.GraphicalItems(),*fp.GetFields(),*fp.Zones(),*fp.Groups()]


def construct(board, source, request, *, board_hint, identity):
    """Add one source-bound private engineering land; no routing/current admission."""
    import cec_force_current as force
    import cec_full_current_planar_reflow as authority
    import cec_fr as fr
    require(type(request) is dict and set(request)=={'part','footprint_sha256','reference',
            'source_track_uuid','candidate'},'exact_flat_bar_construction_request')
    require(type(identity) is str and identity and type(board_hint) is str and board_hint,
            'source_bound_flat_bar_construction_identity')
    ref=request['reference']
    require(type(ref) is str and 0<len(ref)<=80 and ref.strip()==ref
            and not any(c.isspace() for c in ref),'explicit_flat_bar_reference')
    require(board.FindFootprintByReference(ref) is None,'unique_flat_bar_reference')
    partpath,part=_read(request['part']);candidate=request['candidate']
    body,land,court=geometry(part,candidate)
    require(type(request['footprint_sha256']) is str,'flat_bar_footprint_identity_mismatch')
    fp,footprintpath=_native_land(partpath,part,candidate,land,court,
                               expected_hash=request['footprint_sha256'])
    require(type(request['footprint_sha256']) is str
            and repack.inspection.sha(footprintpath)==request['footprint_sha256'],
            'flat_bar_footprint_identity_mismatch')
    source=Path(source).resolve(strict=True);sourcehash=repack.inspection.sha(source)
    family=force._family(source,board_hint)
    pcbnew,quiet=_native();original=pcbnew.LoadBoard(str(source))
    tracks={str(t.m_Uuid.AsString()):t for t in original.GetTracks()}
    key=request['source_track_uuid']
    require(type(key) is str and key in tracks and tracks[key].GetClass()=='PCB_TRACK',
            'existing_force_current_source_track_required')
    net=str(tracks[key].GetNetname())
    kind,domain,current=authority._model(original,source,net,board_hint)
    require(board.FindNet(net) is not None and str(board.FindNet(net).GetNetname())==net,
            'existing_destination_flat_bar_net_required')
    resolver=fr._project_netclass_resolver(str(source),board=board)
    def clearance(other):
        return max(board.GetDesignSettings().m_MinClearance,
                   *[round(float((resolver(n) or {}).get('clearance') or 0)*1e6) for n in (net,other)])
    row,_=bridges.screen_geometry(board,body,[land],dict(id=candidate['id'],face='F.Cu'),
        net=net,clearance=clearance,mechanical_margin_nm=250000,deadline=time.monotonic()+9)
    require(row['land_clearance_screen_ok'] and row['nominal_mechanical_screen_ok'],
            'flat_bar_construction_geometry_conflict')
    row['source_copper_touches_land']=bool(row.pop('source_copper_touches_both_feet'))
    existing=[*board.GetTracks(),*board.GetDrawings(),*board.Zones(),*board.Groups()]
    for old in board.GetFootprints():existing.extend(_footprint_items(old))
    occupied={str(i.m_Uuid.AsString()) for i in existing}
    items=_footprint_items(fp)
    keys=[str(uuid.uuid5(uuid.NAMESPACE_URL,identity+':flatbar:'+ref+':'+str(i)+':'+item.GetClass()))
          for i,item in enumerate(items)]
    require(len(set(keys))==len(keys) and not occupied.intersection(keys),
            'flat_bar_derived_uuid_collision')
    for item,newkey in zip(items,keys):item.m_Uuid.Clone(pcbnew.KIID(newkey))
    fp.SetReference(ref);list(fp.Pads())[0].SetNet(board.FindNet(net))
    envelope=dict(height_max_mm=part['dimensions_mm']['height'][1]+candidate['solder_allocation_nm']/1e6,
        local_box_mm=[-part['provisional_courtyard_mm'][0]/2,-part['provisional_courtyard_mm'][1]/2,
                       part['provisional_courtyard_mm'][0]/2,part['provisional_courtyard_mm'][1]/2],
        basis='design_allocation',evidence=part['drawing_url']+'; solder height provisional')
    def unchanged():
        return (repack.inspection.sha(source)==sourcehash
                and force._family(source,board_hint)==family
                and repack.inspection.sha(partpath)==request['part']['sha256']
                and repack.inspection.sha(footprintpath)==request['footprint_sha256'])
    require(unchanged(),'flat_bar_construction_sources_changed')
    board.Add(fp)
    try:require(unchanged(),'flat_bar_construction_sources_changed')
    except Exception:
        board.Remove(fp)
        raise
    return dict(reference=ref,footprint_uuid=keys[0],added_uuids=keys,
        footprint=part['footprint'],part=copy.deepcopy(request['part']),part_id=part['id'],
        footprint_sha256=request['footprint_sha256'],source=str(source),source_sha256=sourcehash,
        source_track_uuid=key,source_family=family,net=net,source_current_contract=current,
        current_domain_kind=kind,candidate=copy.deepcopy(candidate),declared_envelope=envelope,
        geometry_screen=row,source_copper_touches_land=row['source_copper_touches_land'],
        routing_admitted=False,current_qualified=False,assembly_qualified=False,
        height_allocation_qualified=False,native_open_or_DRC_count_known=False,release_authority=False)


def preview(request):
    require(type(request) is dict and set(request)=={
        'schema','repack','part','side','board_hint','source_track_uuid','candidates'}
        and type(request['schema']) is int and request['schema']==1,
        'exact_flat_bar_preview_request_required')
    planpath,plan=_read(request['repack']);partpath,part=_read(request['part'])
    placement,data=repack.preview(plan)
    require(request['side'] in ('carrier','cover'),'paired_flat_bar_side_required')
    index=0 if request['side']=='carrier' else 1
    source=Path(plan[request['side']]['path']).resolve(strict=True)
    require(type(request['board_hint']) is str and request['board_hint'], 'source_board_hint_required')
    candidates=request['candidates']
    require(type(candidates) is list and 1<=len(candidates)<=4, 'bounded_flat_bar_trial_count')
    for candidate in candidates:geometry(part,candidate)
    require(len({c['id'] for c in candidates})==len(candidates),'unique_flat_bar_trial_ids')
    pcbnew,quiet=_native()
    boards=[pcbnew.LoadBoard(str(Path(plan[s]['path']).resolve())) for s in ('carrier','cover')]
    board=boards[index]
    tracks={str(t.m_Uuid.AsString()):t for t in board.GetTracks()}
    require(type(request['source_track_uuid']) is str and request['source_track_uuid'] in tracks,
            'existing_force_current_source_track_required')
    net=str(tracks[request['source_track_uuid']].GetNetname())
    import cec_force_current as force
    import cec_full_current_planar_reflow as authority
    import cec_fr as fr
    family=force._family(source,request['board_hint'])
    kind,domain,current=authority._model(board,source,net,request['board_hint'])
    for native,side in zip(boards,('carrier','cover')):
        poses=normalize_poses(plan[side]['poses'],limit=32) if plan[side]['poses'] else {}
        for ref,(x,y,turn) in poses.items():
            fp=native.FindFootprintByReference(ref)
            fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y))
    resolver=fr._project_netclass_resolver(str(source),board=board)
    def clearance(other):
        return max(board.GetDesignSettings().m_MinClearance,
                   *[round(float((resolver(n) or {}).get('clearance') or 0)*1e6) for n in (net,other)])
    footprintpath=partpath.parent/(part['footprint']+'.kicad_mod')
    require(footprintpath.resolve().parent==partpath.parent,'local_flat_bar_footprint_required')
    fphash=repack.inspection.sha(footprintpath)
    contract=json.loads(Path(plan['contract']['path']).read_text())
    reports=[];views=[];start=time.monotonic()
    for candidate in candidates:
        body,land,court=geometry(part,candidate)
        native_candidate=dict(id=candidate['id'],face='F.Cu')
        row,view=bridges.screen_geometry(board,body,[land],native_candidate,net=net,
            clearance=clearance,mechanical_margin_nm=250000,deadline=start+9)
        row['source_copper_touches_land']=bool(row.pop('source_copper_touches_both_feet'))
        row['scope']='maximum body and provisional actual land on moved owners; source routes NOT rebuilt'
        fp,_=_native_land(partpath,part,candidate,land,court)
        pads=list(fp.Pads())
        fp.SetReference('__BAR_TRIAL__')
        require(board.FindFootprintByReference('__BAR_TRIAL__') is None,'unique_bar_trial_reference')
        pads[0].SetNet(board.FindNet(net));board.Add(fp)
        try:
            declared=copy.deepcopy(contract)
            declared.setdefault('envelopes',{})[part['footprint']]=dict(
                height_max_mm=part['dimensions_mm']['height'][1]+candidate['solder_allocation_nm']/1e6,
                local_box_mm=[-part['provisional_courtyard_mm'][0]/2,
                              -part['provisional_courtyard_mm'][1]/2,
                               part['provisional_courtyard_mm'][0]/2,
                               part['provisional_courtyard_mm'][1]/2],
                basis='design_allocation',evidence=part['drawing_url']+'; solder height provisional')
            stack,_=repack.assembly.evaluate_boards(*boards,declared)
            actual,basis=repack.assembly.footprint_planar_envelope(fp)
            # KiCad's cached courtyard is inset by 5 um. Bound that parser
            # effect, but use the FULL declared rectangle for stack checks.
            require(court.buffer(.000002,join_style='mitre').covers(actual)
                    and actual.buffer(.006,join_style='mitre').covers(court),
                    'flat_bar_courtyard_matches_proposal')
        finally:
            board.Remove(fp)
        row.update(stack_screen_ok=stack['ok'],stack_violations=stack['violations'],
                   added_bar_stack_checks=[r for r in stack['checks'] if '__BAR_TRIAL__' in r['refs']],
                   installed_height_allocation_mm=declared['envelopes'][part['footprint']]['height_max_mm'],
                   height_allocation_qualified=False, current_qualified=False,
                   native_open_or_DRC_count_known=False, routing_admitted=False)
        reports.append(row);views.append(view)
    require(time.monotonic()-start<9,'flat_bar_screen_time_budget_exceeded')
    require(family==force._family(source,request['board_hint'])
            and fphash==repack.inspection.sha(footprintpath)
            and all(repack.inspection.sha(p)==h for p,h in [
                (planpath,request['repack']['sha256']),(partpath,request['part']['sha256']),
                *[(Path(plan[s]['path']),plan[s]['sha256']) for s in ('carrier','cover','contract')]]),
            'flat_bar_sources_changed_during_trial')
    return dict(schema=1,part_id=part['id'],part=request['part'],repack=request['repack'],
        footprint_sha256=fphash,source=plan[request['side']],source_family=family,
        net=net,source_current_contract=current,current_domain_kind=kind,
        paired_placement_screen_ok=placement['placement_screen_ok'],candidates=reports,
        source_unchanged=True,pcb_files_modified=False,release_authority=False,
        qualification_gaps=['solder land/paste process','distributed solder/current/heat transfer',
            'source-owned rated connections and assembled Kelvin isolation',
            'rebuilt native routes/fills, opens and full DRC','current inventory and assembly cost']),views


def outputs(request_path,request,output):
    import cec_force_current as force
    planpath,plan=_read(request['repack']);partpath,part=_read(request['part'])
    require(request['side'] in ('carrier','cover'),'paired_flat_bar_side_required')
    protected=set()
    for side in ('carrier','cover'):
        hint=request['board_hint'] if side==request['side'] else None
        protected |= force._protected_paths(plan[side]['path'],hint)
    protected |= {str(Path(p).resolve()) for p in (request_path,planpath,partpath,
        partpath.parent/(part['footprint']+'.kicad_mod'),plan['contract']['path'])}
    target=Path(output).resolve()
    require(target.suffix=='.json','flat_bar_report_format_required')
    force._check_output(target,protected)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();request=json.loads(Path(args.request).read_text())
    target=outputs(args.request,request,args.output)
    result,_=preview(request);repack.inspection.write_json(target,result)
    print(json.dumps(dict(part=result['part_id'],net=result['net'],
        conflicts=[len(r['land_conflicts']) for r in result['candidates']],
        stack=[r['stack_screen_ok'] for r in result['candidates']],routing_admitted=False)))


if __name__=='__main__':main()
