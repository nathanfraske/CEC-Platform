"""One geometry-led rotated reservoir study; no saved board or cut authority."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
import cec_fr as fr

WORK=Path(__file__).resolve().parent
SOURCE=ROOT/'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb'
SHA='d4cf0b22f92526b6bdca0ae7cfa09af02217647db984577064ce91bfc177958a'


def main():
    started=time.monotonic();p,_=_native();assert force._hash(SOURCE)==SHA
    fixed_ground='--fixed-ground'in sys.argv
    flip_bypass='--flip-bypass'in sys.argv
    assert not flip_bypass or fixed_ground
    b=p.LoadBoard(str(SOURCE));fps={f.GetReference():f for f in b.GetFootprints()}
    original=p.LoadBoard(str(SOURCE))
    refs={'U6','C9','C27','C54','R54','C55'}|({'C51'}if not fixed_ground else set())
    before={r:[*map(int,fps[r].GetPosition()),fps[r].GetOrientationDegrees()]for r in refs}
    for ref in refs-{'C55','C51'}:fps[ref].Move(p.VECTOR2I(2000000,0))
    if flip_bypass:
        bypass=fps['C54']
        supply=next(q for q in bypass.Pads()if q.GetNetname()!='GND')
        supply_at=tuple(supply.GetPosition())
        bypass.SetOrientationDegrees(bypass.GetOrientationDegrees()+180)
        bypass.Move(p.VECTOR2I(supply_at[0]-supply.GetPosition().x,
                              supply_at[1]-supply.GetPosition().y))
    # Keep the supply close to its moved owner; aim Ground below the back bus.
    cap=fps['C55'];cap.SetOrientationDegrees(270)
    cap.SetPosition(p.VECTOR2I(20400000,47050000)if fixed_ground else p.VECTOR2I(20500000,49950000))
    # Rotate the soft-start cap about its original Ground land, with its
    # control land pointing downward. This is a native pose, not a role proof.
    soft=fps['C51'];ground=next(q for q in soft.Pads()if q.GetNetname()=='GND')
    anchor=tuple(ground.GetPosition())
    if not fixed_ground:
        for angle in (90,270):
            soft.SetOrientationDegrees(angle)
            other=next(q for q in soft.Pads()if q.GetNetname()!='GND')
            if other.GetPosition().y>ground.GetPosition().y:break
        shift=p.VECTOR2I(anchor[0]-ground.GetPosition().x,anchor[1]-ground.GetPosition().y)
        soft.Move(shift)
    shapes={}
    for ref,fp in fps.items():
        try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
        except ValueError:continue
    collisions=[];seen=set()
    for ref in sorted(refs):
        for other,shape in shapes.items():
            pair=tuple(sorted((ref,other)))
            if other==ref or pair in seen or fps[other].GetLayer()!=fps[ref].GetLayer():continue
            seen.add(pair)
            intersection=shapes[ref].intersection(shape)
            if not intersection.is_empty:collisions.append(dict(refs=pair,area_mm2=intersection.area))
    peer_path=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
    stack_path=ROOT/'beta/assembly/hub-atx-stack.json'
    paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer_path)),json.loads(stack_path.read_text()))
    # Fabrication eligibility and actual physical clearance are distinct.
    vias=[];layers=list(b.GetEnabledLayers().CuStack())
    for ref in ('C55','C51'):
        g=next(q for q in fps[ref].Pads()if q.GetNetname()=='GND')
        # A deterministic geometry-led seat: upper-right within the actual
        # rotated reservoir Ground land, away from the diagonal back feed.
        at=(p.VECTOR2I(19445406,48954594)if fixed_ground else p.VECTOR2I(20850000,50700000))if ref=='C55'else g.GetPosition()
        existing=next((t for t in b.GetTracks()if t.GetClass()=='PCB_VIA'
            and t.GetNetCode()==g.GetNetCode()and tuple(t.GetPosition())==tuple(at)),None)
        dia=existing.GetWidth(existing.TopLayer())if existing is not None else 600000
        drill=existing.GetDrillValue()if existing is not None else 300000
        conflicts=[]
        for t in b.GetTracks():
            if t.GetNetCode()==g.GetNetCode():continue
            for layer in layers:
                if t.IsOnLayer(layer)and t.GetEffectiveShape(layer).Collide(p.SHAPE_CIRCLE(at,dia//2),200000):
                    conflicts.append(dict(uuid=force._uid(t),net=t.GetNetname(),layer=b.GetLayerName(layer),
                        start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),
                        width_nm=t.GetWidth(layer) if t.GetClass()=='PCB_VIA'else t.GetWidth()))
        filled_conflicts=[];unknown_fills=[]
        for zone in b.Zones():
            if zone.GetIsRuleArea()or zone.GetNetCode()==g.GetNetCode():continue
            for layer in layers:
                if not zone.IsOnLayer(layer):continue
                record=dict(uuid=force._uid(zone),net=zone.GetNetname(),layer=b.GetLayerName(layer))
                if not zone.IsFilled()or not zone.HasFilledPolysForLayer(layer):unknown_fills.append(record)
                elif zone.GetFilledPolysList(layer).Collide(p.SHAPE_CIRCLE(at,dia//2),200000):
                    filled_conflicts.append(record)
        blocked,records=fab.via_at_pad_conflicts(b,at,dia,drill,g.GetNetCode())
        detail={}
        clear=fr._via_spot_clear(b,at,dia,200000,{g.GetNetCode()},drill_nm=drill,
            net_code=g.GetNetCode(),report=detail,
            existing_via_uuid=force._uid(existing)if existing is not None else None,
            native_padstack_via=existing)
        prior_detail=None
        if existing is not None:
            prior=next(t for t in original.GetTracks()if force._uid(t)==force._uid(existing))
            prior_detail={}
            fr._via_spot_clear(original,prior.GetPosition(),prior.GetWidth(prior.TopLayer()),200000,
                {prior.GetNetCode()},drill_nm=prior.GetDrillValue(),net_code=prior.GetNetCode(),
                existing_via_uuid=force._uid(prior),native_padstack_via=prior,report=prior_detail)
        vias.append(dict(ref=ref,at_nm=list(at),diameter_nm=dia,drill_nm=drill,
            retained_existing_via_uuid=force._uid(existing)if existing is not None else None,
            process_pad_clear=blocked is None,process_details=records,
            native_foreign_track_conflicts=conflicts,all_layer_guard_clear=clear,all_layer_guard_detail=detail,
            saved_filled_zone_conflicts=filled_conflicts,unknown_saved_fills=unknown_fills,
            original_source_same_axis_guard_detail=prior_detail,
            inherited_reservation_refusal_not_a_clearance_waiver=prior_detail is not None and not clear))
    result=dict(schema=1,source=str(SOURCE),source_sha256=SHA,peer_sha256=force._hash(peer_path),
        stack_sha256=force._hash(stack_path),source_poses=before,
        proposed_poses={r:[*map(int,fps[r].GetPosition()),fps[r].GetOrientationDegrees()]for r in sorted(refs)},
        proposed_pads={r:[dict(number=q.GetNumber(),net=q.GetNetname(),at_nm=list(q.GetPosition()))
                         for q in fps[r].Pads()]for r in ('C55','C51','C54')},
        courtyard_collisions=collisions,paired_assembly=paired,ground_axis_scout=vias,
        source_copper_retained_in_probe=True,copper_reconstruction_or_part_roles_qualified=False,
        accepted=False,board_saved=False,elapsed_s=time.monotonic()-started)
    assert force._hash(SOURCE)==SHA
    name=('geometry-fixed-ground-pivot-flipped-bypass.json'if flip_bypass else
        'geometry-fixed-ground-pivot.json'if fixed_ground else 'geometry-rotated-reservoir.json')
    (WORK/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('proposed_pads','courtyard_collisions','ground_axis_scout','elapsed_s')},indent=2))


if __name__=='__main__':main()
