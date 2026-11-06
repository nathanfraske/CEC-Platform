"""Private no-cut capacitor translation; existing bypass receiver owns proof."""
import argparse
import json
from pathlib import Path
from cec_pipeline.native import _native
p,_=_native()
from cec_pipeline import cells
import cec_additive_route_receiving as syntax
import cec_bypass_pose_receiving as bypass
import cec_decoupler_cell as decoupling
import cec_force_current as force
import cec_source_retaining_ses_import as raw


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--sha256',required=True)
    ap.add_argument('--reference',required=True)
    ap.add_argument('--board-hint',required=True)
    ap.add_argument('--xy',nargs=2,type=float,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--restore-contacts',action='store_true')
    args=ap.parse_args();source=args.source.resolve(strict=True);out=args.output.resolve()
    if force._hash(source)!=args.sha256 or out.exists():
        raise ValueError('exact_source_and_fresh_private_directory_required')
    out.mkdir(parents=True);board=p.LoadBoard(str(source))
    cap=board.FindFootprintByReference(args.reference)
    if cap is None or cap.IsLocked() or any(g.ContainsItem(cap) for g in board.Groups()):
        raise ValueError('one_ungrouped_unlocked_native_capacitor_required')
    old_ports={force._uid(pad):tuple(pad.GetPosition()) for pad in cap.Pads()}
    source_tracks={force._uid(t) for t in board.GetTracks()}
    cap.SetPosition(p.VECTOR2I(*(round(v*1e6) for v in args.xy)))
    contact_construction={}
    if args.restore_contacts:
        for pad in cap.Pads():
            if pad.GetNetname()=='GND':
                result,reason=decoupling._add_ground_return(board,pad,board_path=str(source),
                    reach_mm=.8,lock=False)
                if reason or result is None:raise ValueError('Ground_reconnection_refused:'+str(reason))
                contact_construction['Ground']={k:v for k,v in result.items() if k!='items'}
            else:
                with force._thermal_hint(args.board_hint):
                    current=decoupling._supply_current_widths(board,pad.GetNetname())
                face=decoupling._ground_terminal_layer(pad)
                width=(current or {}).get('required_by_layer_nm',{}).get(face)
                if not width:raise ValueError('exact_existing_full_current_width_required')
                route=dict(net=pad.GetNetname(),width_nm=width,layer=board.GetLayerName(face),
                    points_nm=[list(pad.GetPosition()),list(old_ports[force._uid(pad)])])
                cells.emit_connections(board,[route],[],identity='retained-capacitor-source-port:'+force._uid(pad))
                contact_construction['supply']=dict(route=route,unchanged_current=current)
    syntax._ground_refill(board)
    native=out/'native-construction.kicad_pcb'
    p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native),board)
    _,fresh=syntax._nodes(native)
    changed={force._uid(cap)}|{force._uid(z) for z in board.Zones()
        if z.GetNetname()=='GND' and not z.GetIsRuleArea()}
    text=raw.raw_text(source);inventory=raw.inventory(text)
    for uid in sorted(changed,key=lambda u:inventory[u][0],reverse=True):
        start,end=inventory[uid];text=text[:start]+syntax._render(fresh[uid])+text[end:]
    added={force._uid(t) for t in board.GetTracks()}-source_tracks
    end=text.rfind(')');text=text[:end]+'\n'+'\n'.join(syntax._render(fresh[u]) for u in sorted(added))+'\n'+text[end:]
    candidate=force._copy_family(source,out/'candidate');raw.write_raw(candidate,text)
    result=bypass.receive(source,candidate,board_hint=args.board_hint,timeout_s=10.,
        max_shift_mm=1.,max_caps=1,return_reach_mm=.8)
    (out/'bypass-receiving.json').write_text(json.dumps(result,indent=2)+'\n')
    receipt=dict(source=str(source),source_sha256=args.sha256,candidate=str(candidate),
        candidate_sha256=force._hash(candidate),reference=args.reference,xy=args.xy,
        no_copper_cuts=True,added_track_uuids=sorted(added),contact_construction=contact_construction,
        full_saved_receiving_still_required=True,
        release_authority=False)
    (out/'construction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(candidate=str(candidate),sha256=receipt['candidate_sha256'],
        bypass_ok=result['ok'],errors=result['errors'])))


if __name__=='__main__':main()
