"""One private monotone C37 guard refresh; no general gate changes."""
import sys,json,copy
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_assembly_envelope as assembly,cec_force_current as force
import cec_additive_route_receiving as syntax,cec_field_coupling as field
from shapely.geometry import shape,mapping
SOURCE=ROOT/'experiments/repack/j3-inward-20261105/typed-v10/carrier/board.kicad_pcb'
PEER=ROOT/'experiments/repack/hub-kvm-20261105/native-v15/cover/board.kicad_pcb'
OLDPEER=ROOT/'experiments/repack/j6c-connected-20261105/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
BOUND={SOURCE:'27db3ea6947ce467587f454b3b719d123306b43397cd74c9ad985fc320d9dfa4',PEER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',OLDPEER:'cc864ff969103e4581fe97625d39052a1c7feb111a91cf1bf5c8c361ed911bcc',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
assert all(force._hash(p)==h for p,h in BOUND.items())
WORK=ROOT/'experiments/repack/c37-vent-refresh-20261105';UID='cdb78967-1044-43e6-b127-3e01854ea586'
mode=sys.argv[1]
if mode=='construct':
 board=pcbnew.LoadBoard(str(SOURCE));peer=pcbnew.LoadBoard(str(PEER));oldpeer=pcbnew.LoadBoard(str(OLDPEER));contract=json.loads(CONTRACT.read_text())
 zones=[z for z in board.Zones() if str(z.m_Uuid.AsString()).startswith('cdb78967-')];assert len(zones)==1
 guard=zones[0];UID=guard.m_Uuid.AsString()
 assert guard.GetIsRuleArea() and list(guard.GetLayerSet().Seq())==[pcbnew.F_Cu]
 assert all((guard.GetDoNotAllowFootprints(),guard.GetDoNotAllowTracks(),guard.GetDoNotAllowVias(),guard.GetDoNotAllowZoneFills()))
 before_result,_=assembly.evaluate_boards(board,oldpeer,contract);after_result,_=assembly.evaluate_boards(board,peer,contract)
 pick=lambda result:next(v for v in assembly.facing_vents(result,contract,'carrier') if v['ref']=='C37')
 oldvent,newvent=pick(before_result),pick(after_result)
 old=assembly.polygon_from_native(guard.Outline());new=shape(newvent['xy']);assert old.buffer(.000002).covers(shape(oldvent['xy']))
 print(json.dumps(dict(old_bounds=old.bounds,old_vent_bounds=shape(oldvent['xy']).bounds,new_vent_bounds=new.bounds,old_hits=assembly.vent_reservations(board,[dict(newvent,xy=mapping(old))]),new_hits=assembly.vent_reservations(board,[newvent]))))
 union=old.union(new.buffer(.000002,join_style='mitre'));assert union.geom_type=='Polygon' and not union.interiors and union.is_valid
 out=guard.Outline();out.RemoveAllContours();out.NewOutline()
 for x,y in list(union.exterior.coords)[:-1]:out.Append(round(x*1e6),round(y*1e6))
 actual=assembly.polygon_from_native(out);assert actual.covers(old) and actual.covers(new)
 screen=assembly.vent_reservations(board,[dict(newvent,xy=mapping(actual))]);print(json.dumps(screen))
 for z in board.Zones():
  if str(z.m_Uuid.AsString())=='4298863e-593a-4614-93d4-b005e5fa434e':
   overlap=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(pcbnew.F_Cu));overlap.BooleanIntersection(out)
   print(json.dumps(dict(fill_net=z.GetNetname(),positive_native_overlap_mm2=overlap.Area()/1e12)))
 # Preserve exact strict finding in the receipt; boundary-scale inherited
 # power-fill contact is not authority to refill or weaken a rated contour.
 reservation=assembly.footprint_reservation_check(board);assert reservation['ok']
 target=force._copy_family(SOURCE,WORK/'candidate/carrier');raw=WORK/'candidate/native.kicad_pcb';field._save_field_snapshot(board,raw)
 root,nodes=syntax._nodes(SOURCE);_,fresh=syntax._nodes(raw);oldnode=nodes[UID];replacement=copy.deepcopy(oldnode)
 polygons=[n for n in fresh[UID] if isinstance(n,list) and n and n[0]=='polygon'];assert len(polygons)==1
 replacement[:]=[n for n in replacement if not(isinstance(n,list) and n and n[0]=='polygon')];replacement.extend(polygons)
 root[1:]=[replacement if n is oldnode else n for n in root[1:]];target.write_text(syntax._render(root)+'\n')
 saved=pcbnew.LoadBoard(str(target));assert field._field_snapshot_inventory(saved)==field._field_snapshot_inventory(board)
 _,final=syntax._nodes(target);strip=lambda n:[v for v in n if not(isinstance(v,list) and v and v[0]=='polygon')]
 assert strip(nodes[UID])==strip(final[UID]) and all(final[k]==v for k,v in nodes.items() if k!=UID)
 current_vent=assembly.vent_reservations(saved,[newvent]);assert current_vent[0]['ok']
 result=dict(schema=1,scope='PRIVATE_MONOTONE_NATIVE_C37_VENT_GUARD_REFRESH',status='STRICT_FULL_GUARD_COPPER_SCREEN_BLOCKED' if screen[0]['copper_hits'] else 'PRIVATE_GEOMETRY_SCREENED',authority=[dict(path=str(p),sha256=h)for p,h in BOUND.items()],candidate=dict(path=str(target),sha256=force._hash(target)),reservation_uuid=UID,old_projected_vent=oldvent,new_projected_vent=newvent,old_guard_xy=mapping(old),new_guard_xy=mapping(actual),old_guard_wholly_retained=True,new_current_vent_wholly_covered=True,only_selected_polygon_AST_changed=True,all_settings_flags_layers_UUID_preserved=True,all_copper_AST_exact_unchanged=True,full_union_native_copper_screen=screen,inherited_boundary_contact=dict(zone_uuid='4298863e-593a-4614-93d4-b005e5fa434e',net='/SENSE5V_HI',positive_native_overlap_mm2=5.0518e-8,already_present_against_original_guard=True,waived=False),footprint_reservation_check=reservation,current_vent_check=current_vent,paired_current_assembly=after_result,protection_reduced=False,routing_admitted=False,current_qualified=False,release_authority=False)
 (WORK/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=result['candidate']['sha256'],uuid=UID,old_centroid=list(old.centroid.coords)[0],new_vent_centroid=list(new.centroid.coords)[0],old_area=old.area,new_area=actual.area)))
elif mode in ('drc','baseline'):
 import cec_native_drc_runner as n
 reportpath=WORK/('source-native-drc.json' if mode=='baseline' else 'candidate/native-drc.json')
 result=n.run(SOURCE if mode=='baseline' else WORK/'candidate/carrier/board.kicad_pcb',reportpath,reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
 reportpath.with_name(reportpath.stem+'-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 report=json.loads(reportpath.read_text());print(json.dumps(dict(errors=sum(r['severity']=='error'for r in report['violations']),opens=len(report['unconnected_items']),warnings=sum(r['severity']=='warning'for r in report['violations']))))
 if mode=='baseline':
  candidate=json.loads((WORK/'candidate/native-drc.json').read_text())
  identity=lambda rows:{json.dumps(v,sort_keys=True) for v in rows if v.get('severity')=='error'}
  before,after=identity(report['violations']),identity(candidate['violations'])
  receipt=json.loads((WORK/'receipt.json').read_text());receipt['native_DRC']=dict(source_errors=len(before),candidate_errors=len(after),source_opens=len(report['unconnected_items']),candidate_opens=len(candidate['unconnected_items']),new_errors=[json.loads(v)for v in sorted(after-before)],removed_errors=[json.loads(v)for v in sorted(before-after)],source_report_sha256=force._hash(reportpath),candidate_report_sha256=force._hash(WORK/'candidate/native-drc.json'))
  (WORK/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  (ROOT/'docs/evidence/20261105-bar-land/c37-vent-refresh.json').write_text(json.dumps(receipt,indent=2)+'\n')
  print(json.dumps(receipt['native_DRC']))
else:raise ValueError(mode)
assert all(force._hash(p)==h for p,h in BOUND.items())
