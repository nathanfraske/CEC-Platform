"""Explicit paired engineering drafts, never accepted workbench candidates.

This materializes an agent's source-bound poses and exact track redraws so
unfinished multi-board reconstruction can be inspected in native KiCad. No
placement search, route search, current waiver, new via or source selection.
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


def stage(request, directory, *, refill=False):
    import cec_force_current as force
    import cec_additive_route_receiving as syntax
    import cec_field_coupling as field

    require(type(refill) is bool, 'explicit_draft_refill_mode')

    require(type(request) is dict and set(request)=={'schema','placement','board_hints','redraws','via_moves'}
            and type(request['schema']) is int and request['schema']==1,'exact_paired_draft_request')
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
    sources={side:Path(plan[side]['path']).resolve(strict=True) for side in ('carrier','cover')}
    families={side:force._family(path,request['board_hints'][side]) for side,path in sources.items()}
    protected={str(planpath),str(Path(plan['contract']['path']).resolve())}
    for side,path in sources.items():
        protected |= force._protected_paths(path,request['board_hints'][side])
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
        fill=None
        if refill:
            import cec_zone_fill
            zones=pcbnew.ZONES()
            for zone in board.Zones():
                if not zone.GetIsRuleArea():zones.append(zone)
            fill=cec_zone_fill.compile_selected(board,zones,timeout_s=8.,initialize_selected=True)
        work.append((side,board,moved,edits,vias,fill))
    directory.mkdir(parents=True)
    receipt=dict(schema=1,kind='UNADMITTED_PAIRED_ENGINEERING_DRAFT',request=request,
                 source_families=families,boards=[],routing_admitted=False,
                 current_Kelvin_return_and_pair_receiving_complete=False,
                 release_authority=False,complete=False)
    repack.inspection.write_json(directory/'draft.json',receipt)
    for side,board,moved,edits,vias,fill in work:
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
        changed|={key for r in edits for key in r['group_uuids']}
        names={id(node):key for key,node in old.items()}
        root[1:]=[fresh[names[id(node)]] if names.get(id(node)) in changed else node
                  for node in root[1:]]
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
            moved_footprint_uuids=moved,redraws=edits,via_moves=vias,
            saved_fills_still_source=not refill,refill_required=not refill,
            native_DRC_required=True,native_fill=fill))
    require(repack.inspection.sha(planpath)==binding['sha256']
            and repack.inspection.sha(plan['contract']['path'])==plan['contract']['sha256']
            and all(repack.inspection.sha(p)==plan[s]['sha256'] for s,p in sources.items())
            and all(force._family(p,request['board_hints'][s])==families[s] for s,p in sources.items()),
            'draft_sources_changed_during_construction')
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
