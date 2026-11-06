"""One c4-bound seven-part pose: native facts, never transport permission."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path('/home/codex/src/CEC-Platform')
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_control_gate_bias_placement as native
import cec_aggregate_cap_ground_leaf as metal
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
import cec_fr as fr

p,_ = _native()
folder = Path(__file__).parent
source = ROOT/'experiments/busbars/mux-reconstruction-20261106/output-prefix-v1/candidate/board.kicad_pcb'
SHA = 'c4c92165a0e8efec60458b91af80807233033bb5668ade92f171cdacb4ce0b88'
peer = ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
stack = ROOT/'beta/assembly/hub-atx-stack.json'
old_study = ROOT/'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json'
poses = json.loads(old_study.read_text())['proposed_poses']
assert force._hash(source) == SHA
b = p.LoadBoard(str(source)); binding = row._source_binding(b)
fps = {f.GetReference():f for f in b.GetFootprints()}
source_poses = {r:[fps[r].GetPosition().x,fps[r].GetPosition().y,fps[r].GetOrientationDegrees()] for r in poses}
tracks = list(b.GetTracks()); allpads = [q for f in b.GetFootprints() for q in f.Pads()]
layers = list(b.GetEnabledLayers().CuStack())

def desc(item):
    value = dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),locked=bool(item.IsLocked()),
        groups=native._groups(b,item),layers=[int(l) for l in item.GetLayerSet().CuStack()])
    if item.GetClass() == 'PAD':
        value.update(ref=item.GetParentFootprint().GetReference(),pin=item.GetNumber(),at_nm=list(item.GetPosition()),
            native_pad_identity=native._pad(item))
    elif item.GetClass() == 'PCB_VIA':
        value.update(at_nm=list(item.GetPosition()),drill_nm=item.GetDrillValue(),top=int(item.TopLayer()),
            bottom=int(item.BottomLayer()),diameter_by_layer_nm={str(l):item.GetWidth(l) for l in item.GetLayerSet().CuStack()})
    else:value.update(start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),width_nm=item.GetWidth())
    return value

def pose_board():
    for ref,pose in poses.items():
        fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(*pose[:2]))

def project(ref,at):
    old,new = source_poses[ref],poses[ref];turn=math.radians(new[2]-old[2]);c,s=round(math.cos(turn)),round(math.sin(turn))
    x,y=at[0]-old[0],at[1]-old[1]
    return [new[0]+c*x+s*y,new[1]-s*x+c*y]

mode = argparse.ArgumentParser();mode.add_argument('mode',choices=['geometry','geometry-selected-v2','geometry-paired-v3','contacts','landings']);args=mode.parse_args()
if args.mode == 'geometry-paired-v3':
    poses=json.loads((folder/'C37-coordinated-translation.json').read_text())['ATX_poses']
    peer=folder/'hub-C37-vent-v1/candidate/board.kicad_pcb'
    assert force._hash(peer)=='4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992'
if args.mode == 'geometry-selected-v2':
    poses['C55']=[20900000,46240000,0]
    poses['C51']=source_poses['C51'][:]
base = dict(schema=1,source=str(source.relative_to(ROOT)),source_sha256=SHA,
    source_native_binding=binding,peer=str(peer.relative_to(ROOT)),peer_sha256=force._hash(peer),
    stack=str(stack.relative_to(ROOT)),stack_sha256=force._hash(stack),source_poses=source_poses,proposed_poses=poses,
    pose_origin_only_old_study=str(old_study.relative_to(ROOT)),old_study_is_not_current_source_proof=True,
    source_copper_retained=True,board_saved=False,transport_or_cut_permission=False,accepted=False,release_authority=False)

if args.mode in ('geometry','geometry-selected-v2','geometry-paired-v3'):
    pose_board();shapes={};basis={}
    for ref,fp in fps.items():
        try:shapes[ref],basis[ref]=assembly.footprint_planar_envelope(fp)
        except ValueError:pass
    hits=[];near=[];seen=set()
    for ref in poses:
        for other,g in shapes.items():
            key=tuple(sorted((ref,other)))
            if ref == other or key in seen or fps[ref].GetLayer() != fps[other].GetLayer():continue
            seen.add(key);intersection=shapes[ref].intersection(g);gap=shapes[ref].distance(g)
            if not intersection.is_empty:hits.append(dict(refs=key,area_mm2=intersection.area))
            if gap < .3:near.append(dict(refs=key,courtyard_gap_mm=gap))
    paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer)),json.loads(stack.read_text()))
    base.update(native_courtyards={r:dict(bounds_mm=list(shapes[r].bounds),geometry=shapes[r].__geo_interface__,basis=basis[r]) for r in poses},
        same_face_courtyard_collisions=hits,near_courtyards=near,paired_ok=paired['ok'],paired_violations=paired['violations'],
        actual_moved_pad_positions={r:[desc(q) for q in fps[r].Pads()] for r in poses})
    if args.mode == 'geometry-selected-v2':
        axis=p.VECTOR2I(21850000,46240000);hits=[]
        for t in tracks:
            if t.GetNetname() == 'Ground':continue
            for layer in t.GetLayerSet().CuStack():
                if t.GetEffectiveShape(layer).Collide(axis,450000):
                    hits.append(dict(item=desc(t),layer=int(layer),actual_copper_with_200000nm_clearance=True))
        from shapely.geometry import LineString,Point
        from shapely.ops import unary_union
        exclusion=unary_union([LineString([(t.GetStart().x/1e6,t.GetStart().y/1e6),
            (t.GetEnd().x/1e6,t.GetEnd().y/1e6)]).buffer(t.GetWidth()/2e6+.45,resolution=128)
            for t in tracks if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == '/SENSE3V3_HI'])
        blocker_ids={'f24778c4-cb5f-402a-8e40-a8125b10d4ea','fc438acf-f774-4fbe-8325-c3ff300f7951',
            'ae45861a-7d9c-47fb-a9fe-c4ca1dfccc72'}
        base.update(selected_physical_intent=True,stationary_refs=['C51'],
            hypothetical_C55_ground_seat=dict(axis_nm=list(axis),diameter_nm=500000,drill_nm=300000,
                all_layer_track_barrel_conflicts=hits,not_a_via_admission=True),
            retained_3V3_seat_exclusion_exit_distance_mm=Point(21.85,46.24).distance(exclusion.boundary),
            exclusion_basis='Native straight centerlines and widths, offset by .25 mm barrel radius plus .2 mm clearance; 128-segment round buffers. Exceeds .8 mm by a wide margin even allowing pad-edge entry.',
            blocking_old_SS_and_supply_tracks=[desc(t) for t in tracks if force._uid(t) in blocker_ids],
            old_track_ownership_status='No actual proposal frame supplied to this study. These are exact source obstacles; no retirement/transport authority inferred from net membership or moving U6.',
            locality_note='C51 is SS control timing, not a supply-selected bypass. Native SS route reconstruction and its own control-cap role remain mandatory; no 3.5 mm supply rule is borrowed.')

elif args.mode == 'contacts':
    deadline=time.monotonic()+9.;inventory=[];candidate={};items=metal._objects(b)
    for ref in sorted(poses):
        for pad in fps[ref].Pads():
            contacts=native._direct_contacts(b,pad,deadline)
            for contact in contacts:
                material=contact.get('material',{})
                if contact['kind']=='ZONE' and 'outline' in material:
                    outline=material.pop('outline');material['outline_sha256']=hashlib.sha256(outline.encode()).hexdigest()
            inventory.append(dict(pad=desc(pad),target_pad_center_nm=project(ref,list(pad.GetPosition())),contacts=contacts))
            incident_ids={q['item_uuid'] for q in contacts if q['kind'] == 'PCB_TRACK'}
            vias=[t for t in tracks if t.GetClass() == 'PCB_VIA']
            for via in vias:
                evidence=[]
                for q in contacts:
                    if q['kind'] == 'PCB_VIA' and q['item_uuid'] == force._uid(via):evidence.append(dict(kind='direct_pad_contact',contact=q))
                for uid in incident_ids:
                    edge=items[uid];face=int(edge.GetLayer())
                    if not via.IsOnLayer(face):continue
                    holes=[i for i in items.values() if i.IsOnLayer(face) and (i.GetClass() == 'PCB_VIA' or i.GetClass() == 'PAD' and i.HasHole())]
                    area=metal._contact(edge,via,face,holes,deadline)
                    if area is not None:evidence.append(dict(kind='pad_incident_track_to_barrel_actual_lower_contact',track_uuid=uid,
                        layer=face,contact_area_nm2=area.Area(),contact_polygon_sha256=hashlib.sha256(area.Format().encode()).hexdigest(),
                        via_at_track_endpoint=list(via.GetPosition()) in [list(edge.GetStart()),list(edge.GetEnd())]))
                if evidence:
                    entry=candidate.setdefault(force._uid(via),dict(source_barrel=desc(via),pad_contact_owners=[]))
                    entry['pad_contact_owners'].append(dict(ref=ref,pin=pad.GetNumber(),pad_uuid=force._uid(pad),
                        rigid_projected_axis_nm=project(ref,list(via.GetPosition())),evidence=evidence))
    # Full original all-face native contact ledger for every candidate barrel.
    for uid,entry in candidate.items():
        via=items[uid];ledger=[]
        for face in via.GetLayerSet().CuStack():
            holes=[i for i in items.values() if i.IsOnLayer(face) and (i.GetClass() == 'PCB_VIA' or i.GetClass() == 'PAD' and i.HasHole())]
            for other in items.values():
                if force._uid(other)==uid or not other.IsOnLayer(face):continue
                area=metal._contact(via,other,face,holes,deadline)
                if area is not None:ledger.append(dict(layer=int(face),other=desc(other) if other.GetClass() != 'ZONE' else dict(uuid=force._uid(other),kind='ZONE',net=other.GetNetname(),locked=bool(other.IsLocked())),
                    actual_lower_contact_nm2=area.Area(),actual_lower_contact_sha256=hashlib.sha256(area.Format().encode()).hexdigest()))
        axes={tuple(o['rigid_projected_axis_nm']) for o in entry['pad_contact_owners']}
        entry.update(complete_original_all_layer_contact_ledger=ledger,
            projected_axes_agree=len(axes)==1,unique_projected_axis_nm=list(next(iter(axes))) if len(axes)==1 else None,
            authority_not_inferred_from_contact=True,every_original_nonplane_contact_requires_restoration=True)
    nets={q.GetNetname() for r in poses for q in fps[r].Pads()}-{'GND'}
    base.update(original_pin_contact_inventory=inventory,barrels_with_actual_direct_or_incident_leaf_contact=list(candidate.values()),
        complete_nonGround_net_terminal_inventory={net:[desc(q) for q in allpads if q.GetNetname()==net] for net in sorted(nets)},
        external_nonGround_terminal_anchors={net:[desc(q) for q in allpads if q.GetNetname()==net
            and q.GetParentFootprint().GetReference() not in poses] for net in sorted(nets)})
    assert row._source_binding(b)==binding

else:
    contacts=json.loads((folder/'contacts.json').read_text());pose_board();hits=[]
    for ref in poses:
        for pad in fps[ref].Pads():
            for t in tracks:
                if t.GetNetCode() == pad.GetNetCode():continue
                for face in pad.GetLayerSet().CuStack():
                    if not t.IsOnLayer(face):continue
                    shape=pad.GetEffectiveShape(face)
                    overlap=shape.Collide(t.GetPosition(),t.GetWidth(face)//2) if t.GetClass() == 'PCB_VIA' else shape.Collide(t.GetEffectiveShape(face),0)
                    clear=shape.Collide(t.GetPosition(),t.GetWidth(face)//2+200000) if t.GetClass() == 'PCB_VIA' else shape.Collide(t.GetEffectiveShape(face),200000)
                    if clear:hits.append(dict(ref=ref,pin=pad.GetNumber(),pad_uuid=force._uid(pad),source_obstacle=desc(t),
                        physical_overlap=bool(overlap),clearance_nm=200000,layer=int(face)))
    seats=[]
    for ref,at in [('C54',[18924990,48610000]),('C55',[20500000,50540000])]:
        code=b.GetNetcodeFromNetname('GND');blocked,records=fab.via_at_pad_conflicts(b,p.VECTOR2I(*at),500000,300000,code);report={}
        clear=fr._via_spot_clear(b,p.VECTOR2I(*at),500000,200000,{code},drill_nm=300000,net_code=code,report=report,foreign_cache={})
        seats.append(dict(ref=ref,at_nm=at,diameter_nm=500000,drill_nm=300000,pad_process_blocked=blocked is not None,
            pad_process_records=records,all_layer_spot_clear=clear,all_layer_report=report,new_hole_or_barrel_reseat_not_authorized=True))
    base.update(moved_pad_retained_foreign_copper_conflicts=hits,actual_factory_ground_seat_probes=seats,
        original_barrel_contact_inventory_file='contacts.json',all_original_barrels_and_tracks_retained=True)
    c51=next(t for t in tracks if force._uid(t)=='7f4e567d-2755-4c6e-a51c-2af6b999bc20')
    blocked,records=fab.via_at_pad_conflicts(b,c51.GetPosition(),c51.GetWidth(c51.TopLayer()),c51.GetDrillValue(),c51.GetNetCode())
    base['retained_C51_Ground_barrel_process']=dict(uuid=force._uid(c51),at_nm=list(c51.GetPosition()),
        blocked=blocked is not None,records=records,transport_not_required_for_pad_containment=True)
    base['barrel_disposition_notes']=dict(
        source_association_is_not_transport_authority=True,
        C51='Ground barrel can stay at original axis; SS barrel can remain an external control boundary if its original connectivity is rebuilt. Neither rigid projection is mandatory.',
        C55='Rigidly transporting old dogbone preserves its failed1.35mm return. Proposed off-center pad-contained seat20.50,50.54 is a different reconstruction, requiring exact old leaf/barrel custody and fresh receiving.',
        C54='Source via is now exactly source Ground pad-centered; rigid pose maps it to proposed Ground18.92499,48.61. Existing all-layer original contacts are Ground pad plus two saved planes only.',
        other_source_barrels='Their source axes physically conflict with posed lands in several cases. Geometry demands moving/reconstructing those contacts, not inferred net-based retirement permission.')

assert force._hash(source)==SHA
out=folder/(args.mode+'.json');out.write_text(json.dumps(base,indent=2)+'\n')
print(json.dumps(dict(mode=args.mode,source_sha256=SHA,output=str(out),
    court_collisions=base.get('same_face_courtyard_collisions'),paired_ok=base.get('paired_ok'),
    original_pads=len(base.get('original_pin_contact_inventory',[])),barrels=len(base.get('barrels_with_actual_direct_or_incident_leaf_contact',[])),
    foreign_conflicts=len(base.get('moved_pad_retained_foreign_copper_conflicts',[])),seats=base.get('actual_factory_ground_seat_probes')),indent=2))
