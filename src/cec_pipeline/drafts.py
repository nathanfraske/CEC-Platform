"""Explicit paired engineering drafts, never accepted workbench candidates.

This materializes an agent's source-bound poses and exact track redraws so
unfinished multi-board reconstruction can be inspected in native KiCad. No
placement search, route search, current waiver or implicit source selection.
Drafts cannot be promoted by this module; every independent receiving gate is
still required. Reviewed sources and project rules are immutable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from . import repack, geometry
from .identity import digest, require
from .native import _native


def _retire(board, ids):
    """Explicit private subtraction; no connectivity or current authority.

    Restrict this drafting operation to ungrouped straight tracks. A source
    anchor embedded in a typed allocation remains protected by native deletion.
    Validate the complete batch before mutating any copper.
    """
    from cec_native_items import discard_items
    require(type(ids) is list and len(ids) <= 128
            and all(type(key) is str and key for key in ids)
            and len(set(ids)) == len(ids), 'bounded_unique_draft_retirement_ids')
    tracks = {str(t.m_Uuid.AsString()): t for t in board.GetTracks()}
    require(all(key in tracks for key in ids), 'existing_draft_retirement_tracks')
    selected = [tracks[key] for key in ids]
    require(all(t.GetClass() == 'PCB_TRACK' for t in selected),
            'draft_retirement_is_not_via_or_arc_removal')
    require(not any(g.ContainsItem(t) for g in board.Groups() for t in selected),
            'draft_retirement_cannot_change_groups')
    records = [dict(uuid=key, net=str(t.GetNetname()), layer=board.GetLayerName(t.GetLayer()),
                    width_nm=t.GetWidth(), locked=bool(t.IsLocked()),
                    source_points_nm=[list(t.GetStart()), list(t.GetEnd())])
               for key, t in zip(ids, selected)]
    discard_items(board, selected)
    return records


def _redraw(board, edits, identity):
    pcbnew,quiet=_native()
    require(type(edits) is list and len(edits)<=128,'bounded_explicit_draft_redraws_required')
    uid=lambda item:str(item.m_Uuid.AsString())
    source={uid(t):t for t in board.GetTracks()}
    require(len(source)==len(list(board.GetTracks())),'unique_source_draft_tracks_required')
    prepared=[];seen=set()
    for edit in edits:
        require(type(edit) is dict and set(edit)=={'uuid','points_nm'},'exact_draft_redraw_fields')
        key=edit['uuid']
        require(type(key) is str and key in source and key not in seen,'unique_existing_draft_track')
        seen.add(key);track=source[key]
        require(track.GetClass()=='PCB_TRACK','draft_redraw_is_not_via_or_arc_conversion')
        points=geometry.path(edit['points_nm'],minimum_phase_nm=20000)
        groups=[g for g in board.Groups() if g.ContainsItem(track)]
        require(not any(g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|') for g in groups),
                'draft_cannot_reinterpret_typed_supply_allocation')
        prepared.append((key,track,points,groups))
    records=[]
    for key,track,points,groups in prepared:
        record=dict(source_uuid=key,net=str(track.GetNetname()),layer=board.GetLayerName(track.GetLayer()),
                    width_nm=track.GetWidth(),locked=bool(track.IsLocked()),
                    source_points_nm=[list(track.GetStart()),list(track.GetEnd())],
                    points_nm=points,group_uuids=[uid(g) for g in groups],added_uuids=[])
        # Keep the source UUID and group anchor alive. Extra legs inherit the
        # same net, width, face and lock, rather than fresh net-name defaults.
        copies=[track.Duplicate() for _ in points[2:]]
        track.SetStart(pcbnew.VECTOR2I(*points[0]));track.SetEnd(pcbnew.VECTOR2I(*points[1]))
        for i,(new,a,b) in enumerate(zip(copies,points[1:],points[2:]),1):
            key_new=str(uuid.uuid5(uuid.NAMESPACE_URL,identity+':'+key+':'+str(i)))
            require(key_new not in source,'draft_derived_track_uuid_collision')
            new.m_Uuid.Clone(pcbnew.KIID(key_new))
            new.SetStart(pcbnew.VECTOR2I(*a));new.SetEnd(pcbnew.VECTOR2I(*b));board.Add(new)
            for group in groups:group.AddItem(new)
            record['added_uuids'].append(key_new)
        records.append(record)
    return records


def _move_vias(board, edits):
    """Exact agent-selected translations; preserve every barrel/process field."""
    pcbnew, quiet = _native()
    require(type(edits) is list and len(edits) <= 32, 'bounded_explicit_draft_vias')
    tracks = {str(t.m_Uuid.AsString()): t for t in board.GetTracks()}
    seen = set(); records = []; prepared = []
    for edit in edits:
        require(type(edit) is dict and set(edit) == {'uuid', 'at_nm'}, 'exact_draft_via_fields')
        key = edit['uuid']
        require(type(key) is str and key in tracks and key not in seen, 'unique_existing_draft_via')
        seen.add(key); via = tracks[key]
        require(via.GetClass() == 'PCB_VIA', 'draft_via_translation_is_not_conversion')
        require(not any(g.ContainsItem(via) and g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|')
                        for g in board.Groups()), 'draft_cannot_reinterpret_typed_supply_allocation')
        at = geometry.point(edit['at_nm'])
        prepared.append((key, via, at))
    for key, via, at in prepared:
        records.append(dict(uuid=key, source_at_nm=list(via.GetPosition()), at_nm=at,
                            net=str(via.GetNetname()), locked=bool(via.IsLocked())))
        via.SetPosition(pcbnew.VECTOR2I(*at))
    return records


def _copy_vias(board, edits, identity):
    """Clone explicit ungrouped source barrels; geometry, not current authority."""
    pcbnew,quiet=_native()
    require(type(edits) is list and len(edits)<=32,'bounded_explicit_draft_via_copies')
    tracks={str(t.m_Uuid.AsString()):t for t in board.GetTracks()}
    occupied=set(tracks)
    for fp in board.GetFootprints():
        occupied|={str(i.m_Uuid.AsString()) for i in
                   [fp,*fp.Pads(),*fp.GraphicalItems(),*fp.GetFields()]}
    occupied|={str(i.m_Uuid.AsString()) for i in [*board.GetDrawings(),*board.Zones(),*board.Groups()]}
    sites={tuple(t.GetPosition()) for t in tracks.values() if t.GetClass()=='PCB_VIA'}
    prepared=[]
    for index,edit in enumerate(edits):
        require(type(edit) is dict and set(edit)=={'source_uuid','at_nm'},'exact_draft_via_copy_fields')
        key=edit['source_uuid']
        require(type(key) is str and key in tracks and tracks[key].GetClass()=='PCB_VIA',
                'existing_source_barrel_required')
        via=tracks[key];at=geometry.point(edit['at_nm'])
        require(bool(str(via.GetNetname())) and not any(g.ContainsItem(via) for g in board.Groups()),
                'named_ungrouped_source_via_required')
        require(tuple(at) not in sites,'draft_copied_via_site_collision')
        sites.add(tuple(at))
        derived=str(uuid.uuid5(uuid.NAMESPACE_URL,identity+':via-copy:'+str(index)+':'+key))
        require(derived not in occupied,'draft_copied_via_uuid_collision');occupied.add(derived)
        prepared.append((key,via,at,derived))
    records=[]
    for key,via,at,derived in prepared:
        clone=via.Duplicate();clone.m_Uuid.Clone(pcbnew.KIID(derived))
        clone.SetPosition(pcbnew.VECTOR2I(*at));board.Add(clone)
        records.append(dict(source_uuid=key,added_uuid=derived,net=str(via.GetNetname()),
            source_at_nm=list(via.GetPosition()),at_nm=at,locked=bool(via.IsLocked()),
            drill_nm=via.GetDrillValue(),top_layer=board.GetLayerName(via.TopLayer()),
            bottom_layer=board.GetLayerName(via.BottomLayer()),
            source_process_cloned=True,current_qualified=False,assembly_qualified=False))
    return records


def stage(request, directory, *, refill=False):
    import cec_force_current as force
    import cec_additive_route_receiving as syntax
    import cec_field_coupling as field

    require(type(refill) is bool, 'explicit_draft_refill_mode')

    fields={'schema','placement','board_hints','redraws','via_moves'}
    require(type(request) is dict and type(request.get('schema')) is int
            and request['schema'] in (1,2,3,4)
            and set(request)==fields|({'retired_tracks'} if request['schema']>=2 else set())
                                   |({'flatbars'} if request['schema']>=3 else set())
                                   |({'via_copies'} if request['schema']==4 else set()),
            'exact_paired_draft_request')
    binding=request['placement']
    require(type(binding) is dict and set(binding)=={'path','sha256'},'hash_bound_draft_placement')
    planpath=Path(binding['path']).resolve(strict=True)
    require(planpath.stat().st_size<=2*1024*1024 and repack.inspection.sha(planpath)==binding['sha256'],
            'draft_placement_identity_mismatch')
    plan=json.loads(planpath.read_text())
    preview,_=repack.preview(plan)
    require(preview['placement_screen_ok'],'paired_draft_requires_passing_placement_screen')
    require(type(request['board_hints']) is dict and set(request['board_hints'])=={'carrier','cover'}
            and all(type(v) is str and v for v in request['board_hints'].values()),
            'explicit_paired_draft_current_hints')
    require(type(request['redraws']) is dict and set(request['redraws'])=={'carrier','cover'},
            'explicit_paired_draft_redraw_scopes')
    require(type(request['via_moves']) is dict and set(request['via_moves'])=={'carrier','cover'},
            'explicit_paired_draft_via_scopes')
    retired=request.get('retired_tracks',{'carrier':[],'cover':[]})
    require(type(retired) is dict and set(retired)=={'carrier','cover'},
            'explicit_paired_draft_retirement_scopes')
    for side in ('carrier','cover'):
        require(type(retired[side]) is list and all(type(key) is str for key in retired[side]),
                'explicit_draft_retirement_ids')
        require(type(request['redraws'][side]) is list and type(request['via_moves'][side]) is list,
                'explicit_draft_edit_lists')
        edited={edit.get('uuid') for edit in request['redraws'][side]+request['via_moves'][side]
                if type(edit) is dict and type(edit.get('uuid')) is str}
        require(not set(retired[side]) & edited, 'draft_retirement_overlaps_redraw_or_via_move')
    bars=request.get('flatbars',{'carrier':[],'cover':[]})
    require(type(bars) is dict and set(bars)=={'carrier','cover'}
            and all(type(rows) is list and len(rows)<=4 for rows in bars.values()),
            'bounded_explicit_paired_flatbar_scopes')
    via_copies=request.get('via_copies',{'carrier':[],'cover':[]})
    require(type(via_copies) is dict and set(via_copies)=={'carrier','cover'}
            and all(type(rows) is list and len(rows)<=32 for rows in via_copies.values()),
            'bounded_explicit_paired_via_copy_scopes')
    for side in ('carrier','cover'):
        moved={r.get('uuid') for r in request['via_moves'][side] if type(r) is dict
               and type(r.get('uuid')) is str}
        require(all(type(r) is dict and type(r.get('source_uuid')) is str
                    and r['source_uuid'] not in moved for r in via_copies[side]),
                'draft_via_copy_requires_unmoved_source_prototype')
    sources={side:Path(plan[side]['path']).resolve(strict=True) for side in ('carrier','cover')}
    families={side:force._family(path,request['board_hints'][side]) for side,path in sources.items()}
    protected={str(planpath),str(Path(plan['contract']['path']).resolve())}
    for side,path in sources.items():
        protected |= force._protected_paths(path,request['board_hints'][side])
    from . import flatbars
    for rows in bars.values():
        for row in rows:
            require(type(row) is dict and 'part' in row,'explicit_draft_flatbar_input')
            partpath,part=flatbars._read(row['part'])
            protected |= {str(partpath),str((partpath.parent/(part['footprint']+'.kicad_mod')).resolve())}
    directory=Path(directory).resolve()
    force._check_proposal_directory(directory,protected)
    require(not directory.exists(),'draft_directory_must_be_new_never_overwrite')
    pcbnew,quiet=_native();work=[]
    for side,path in sources.items():
        require(repack.inspection.sha(path)==plan[side]['sha256'],
                'draft_source_changed_after_placement_preview')
        board=pcbnew.LoadBoard(str(path));moved=[]
        poses=repack.normalize_poses(plan[side]['poses'],limit=32) if plan[side]['poses'] else {}
        for ref,(x,y,turn) in poses.items():
            fp=board.FindFootprintByReference(ref)
            # The preview already binds identity and max shift. Draft motion
            # preserves all embedded pin/net/drill/pad/process definitions.
            fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            moved.append(str(fp.m_Uuid.AsString()))
        edits=_redraw(board,request['redraws'][side],digest(request)+':'+side)
        vias=_move_vias(board,request['via_moves'][side])
        cuts=_retire(board,retired[side])
        inserted=[flatbars.construct(board,path,row,board_hint=request['board_hints'][side],
                                    identity=digest(request)+':'+side) for row in bars[side]]
        copies=_copy_vias(board,via_copies[side],digest(request)+':'+side)
        fill=None
        if refill:
            import cec_zone_fill
            zones=pcbnew.ZONES()
            for zone in board.Zones():
                if not zone.GetIsRuleArea():zones.append(zone)
            fill=cec_zone_fill.compile_selected(board,zones,timeout_s=8.,initialize_selected=True)
        work.append((side,board,moved,edits,vias,cuts,inserted,copies,fill))
    bar_stack=None
    if any(bars.values()):
        contract=json.loads(Path(plan['contract']['path']).read_text())
        envelopes=contract.setdefault('envelopes',{})
        for _,_,_,_,_,_,inserted,_,_ in work:
            for row in inserted:
                key=row['footprint'];env=row['declared_envelope']
                if key in envelopes:
                    require(envelopes[key]==env,'draft_bar_envelope_cannot_override_contract')
                envelopes[key]=env
        bar_stack,_=repack.assembly.evaluate_boards(work[0][1],work[1][1],contract)
        require(bar_stack['ok'],'draft_bar_requires_passing_paired_stack_screen')
    directory.mkdir(parents=True)
    receipt=dict(schema=1,kind='UNADMITTED_PAIRED_ENGINEERING_DRAFT',request=request,
                 source_families=families,boards=[],routing_admitted=False,
                 current_Kelvin_return_and_pair_receiving_complete=False,
                 bar_stack_screen=bar_stack,release_authority=False,complete=False)
    repack.inspection.write_json(directory/'draft.json',receipt)
    for side,board,moved,edits,vias,cuts,inserted,copies,fill in work:
        parent=sources[side];folder=directory/side;folder.mkdir()
        for path in parent.parent.glob(parent.stem+'.*'):
            if path.is_file():shutil.copy2(path,folder/path.name)
        target=folder/parent.name
        with tempfile.NamedTemporaryFile(prefix='draft-io-',suffix='.kicad_pcb',
                                         dir=folder,delete=False) as scratch:
            raw=Path(scratch.name)
        field._save_field_snapshot(board,raw)
        # Splice ONLY exact posed owners and explicit redraws. Keep every
        # unrelated source native node intact; no wholesale serialization.
        root,old=syntax._nodes(parent);_,fresh=syntax._nodes(raw)
        changed=set(moved)|{r['source_uuid'] for r in edits}
        changed|={r['uuid'] for r in vias}
        if refill:changed|={str(z.m_Uuid.AsString()) for z in board.Zones() if not z.GetIsRuleArea()}
        added={key for r in edits for key in r['added_uuids']}
        added|={r['footprint_uuid'] for r in inserted}
        added|={r['added_uuid'] for r in copies}
        changed|={key for r in edits for key in r['group_uuids']}
        removed={r['uuid'] for r in cuts}
        names={id(node):key for key,node in old.items()}
        root[1:]=[fresh[names[id(node)]] if names.get(id(node)) in changed else node
                  for node in root[1:] if names.get(id(node)) not in removed]
        root.extend(fresh[key] for key in sorted(added))
        target.write_text(syntax._render(root)+'\n')
        saved=pcbnew.LoadBoard(str(target))
        require(field._field_snapshot_inventory(saved)==field._field_snapshot_inventory(board),
                'draft_spliced_native_copper_identity_changed')
        properties=lambda value:{str(k):str(v) for k,v in value.GetProperties().asdict().items()}
        require(properties(saved)==properties(board),
                'draft_saved_board_process_metadata_changed')
        require(force._sidecars(parent)==force._sidecars(target),
                'draft_must_preserve_source_companions')
        raw.unlink()  # Our new, verified IO scratch file; not a source artifact.
        receipt['boards'].append(dict(side=side,path=str(target),source=str(parent),
            source_sha256=plan[side]['sha256'],sha256=repack.inspection.sha(target),
            moved_footprint_uuids=moved,redraws=edits,via_moves=vias,retired_tracks=cuts,flatbars=inserted,
            via_copies=copies,
            saved_fills_still_source=not refill,refill_required=not refill,
            native_DRC_required=True,native_fill=fill))
    require(repack.inspection.sha(planpath)==binding['sha256']
            and repack.inspection.sha(plan['contract']['path'])==plan['contract']['sha256']
            and all(repack.inspection.sha(p)==plan[s]['sha256'] for s,p in sources.items())
            and all(force._family(p,request['board_hints'][s])==families[s] for s,p in sources.items()),
            'draft_sources_changed_during_construction')
    for rows in bars.values():
        for row in rows:
            partpath,part=flatbars._read(row['part'])
            require(repack.inspection.sha(partpath.parent/(part['footprint']+'.kicad_mod'))
                    ==row['footprint_sha256'],'draft_bar_footprint_changed_during_construction')
    receipt['complete']=True;receipt['source_unchanged']=True
    repack.inspection.write_json(directory/'draft.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--directory',required=True)
    parser.add_argument('--refill',action='store_true',help='native fill, preserving all non-zone metadata')
    args=parser.parse_args();path=Path(args.request).resolve(strict=True)
    directory=Path(args.directory).resolve()
    require(not path.is_relative_to(directory),'draft_output_cannot_contain_request')
    result=stage(json.loads(path.read_text()),directory,refill=args.refill)
    print(json.dumps(dict(complete=result['complete'],source_unchanged=result['source_unchanged'],
        boards=[b['path'] for b in result['boards']],routing_admitted=False)))


if __name__=='__main__':main()
