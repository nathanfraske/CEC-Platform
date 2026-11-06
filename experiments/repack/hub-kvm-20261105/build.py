"""Private source-bound Hub KVM engineering experiment, no admission."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
from cec_pipeline import drafts,repack
import cec_force_current as f
SOURCE=ROOT/'experiments/repack/j6c-connected-20261105/cover/board.kicad_pcb'
EXPECTED='cc864ff969103e4581fe97625d39052a1c7feb111a91cf1bf5c8c361ed911bcc'
WORK=ROOT/'experiments/repack/hub-kvm-20261105'
assert f._hash(SOURCE)==EXPECTED
spec=json.loads((ROOT/'docs/evidence/20261105-bar-land/hub-kvm-source-proposal.json').read_text())
mode=sys.argv[1]
if mode=='inventory':
 b=pcbnew.LoadBoard(str(SOURCE));nets={p['net'] for o in spec['owners'] for p in o['pads']} - {'GND','+5VSB'}
 out={}
 for net in sorted(nets):
  out[net]=dict(pads=[dict(ref=fp.GetReference(),number=p.GetNumber(),at_nm=list(p.GetPosition())) for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==net],tracks=[dict(uuid=f._uid(t),kind=t.GetClass(),layer=b.GetLayerName(t.GetLayer()),width_nm=t.GetWidth(t.TopLayer()) if t.GetClass()=='PCB_VIA' else t.GetWidth(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),grouped=t.GetParentGroup() is not None) for t in b.GetTracks() if t.GetNetname()==net])
 (WORK/'inventory.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
elif mode=='prepare':
 plan=json.loads((ROOT/'docs/evidence/20261105-busbar-candidates/paired-request.json').read_text())
 plan['carrier']=dict(path='experiments/repack/j6c-connected-20261105/carrier/board.kicad_pcb',sha256=f._hash(ROOT/'experiments/repack/j6c-connected-20261105/carrier/board.kicad_pcb'),poses=[])
 plan['cover']=dict(path=str(SOURCE),sha256=EXPECTED,poses=[o['target'] for o in spec['owners']])
 path=WORK/'placement.json';path.write_text(json.dumps(plan,indent=2)+'\n')
 request=dict(schema=2,placement=dict(path=str(path),sha256=f._hash(path)),board_hints=dict(carrier='atx-24pin-rev3',cover='hub-standard-rev2'),redraws=dict(carrier=[],cover=[]),via_moves=dict(carrier=[],cover=[]),retired_tracks=dict(carrier=[],cover=[]))
 (WORK/'request.json').write_text(json.dumps(request,indent=2)+'\n')
 print(json.dumps(repack.preview(plan)[0],indent=2))
elif mode=='author':
 request=json.loads((WORK/'request.json').read_text());inv=json.loads((WORK/'inventory.json').read_text())
 raw=inv['/KVM AUXILIARY + RAIL SENSING/KVM_5V_RAW']['tracks']
 # Complete two-terminal RAW network, retain one exact source-width leg as
 # the new local branch; other eight source tracks are explicit retirements.
 anchor='1bc01650-9ec9-47ed-8d2e-29aad564492f'
 request['retired_tracks']['cover']=[t['uuid'] for t in raw if t['uuid']!=anchor]
 request['redraws']['cover']=[
  dict(uuid=anchor,points_nm=[[64100000,5750000],[64100000,10162500],[62300000,11962500]]),
  dict(uuid='6f3244b8-7bd2-44fd-9e22-3f683e35e748',points_nm=[[56100000,5750000],[56100000,10350000],[55000000,11450000]]),
  dict(uuid='96759590-2e6e-4d37-bc3e-b473ef22c6c6',points_nm=[[55000000,11450000],[54300000,11450000],[53900000,11050000],[53900000,7670000],[53400000,7170000]]),
  dict(uuid='0f0f9528-575e-44a6-b4b7-9d2b43cd5350',points_nm=[[53390000,12700000],[52811700,13278300],[52759300,13278300]]),
  dict(uuid='812515ab-d134-45c8-9215-6815585b9c12',points_nm=[[57331300,10206300],[56500000,10206300],[54006300,12700000],[53390000,12700000]]),
  dict(uuid='9b798315-b643-4cb9-9322-f1b90fd747b6',points_nm=[[54410000,12700000],[54800000,12310000],[54800000,10217600],[56881300,8136300]]),
  dict(uuid='f18f398d-f296-45da-9c64-be3699f18d98',points_nm=[[55000000,9350000],[54325000,9350000]])
 ]
 request['redraws']['cover'] += [
  dict(uuid='6ddf7806-a470-435f-9092-4ea319c5aee6',points_nm=[[37800000,53000000],[40500000,50300000],[40500000,49500000]]),
  dict(uuid='20a90713-1a9e-5caf-84a9-f6cf9ce17086',points_nm=[[53500000,4956299],[53500000,11000000],[56300000,13800000]]),
  dict(uuid='dc85b1e2-ad17-46a5-a526-99c9c38812f1',points_nm=[[45000000,4500000],[53500000,4500000]]),
  dict(uuid='fb2c944f-7b79-444f-8bb1-37f625088a23',points_nm=[[53500000,4500000],[53500000,4956299]]),
  dict(uuid='a02d54b2-5398-492f-8839-bb45dce5b044',points_nm=[[75301000,56900000],[73800000,56900000],[73500000,56600000]]),
  dict(uuid='f998ae56-ef9c-54bb-9018-9a10e088677b',points_nm=[[72100000,56900000],[73200000,56900000],[73500000,56600000]])
 ]
 request['via_moves']['cover']=[dict(uuid='6989b933-4a49-435f-835d-ea6d0d9b2ad7',at_nm=[62300000,9037500]),dict(uuid='0ca4d4b4-644c-45ef-be69-570c9a59f0d3',at_nm=[43200000,53000000]),dict(uuid='d52a6523-8b53-4a63-b1dd-2d349d822a3d',at_nm=[45850000,50780000])]
 request['via_moves']['cover'] += [dict(uuid='12117b2c-ad36-4b96-bac5-3345fb3907cd',at_nm=[53500000,4956299]),dict(uuid='434aa75c-5627-464e-9437-06fb40f2f600',at_nm=[73500000,56600000]),dict(uuid='ee3f11eb-6272-4635-b0a8-5ff97b44ce1e',at_nm=[73500000,42600000])]
 # Keep reference transfer on its original SIG2 routing layer and move the
 # original D7 barrel with its owner, instead of crossing dense F.Cu logic.
 remove={'6f3244b8-7bd2-44fd-9e22-3f683e35e748','96759590-2e6e-4d37-bc3e-b473ef22c6c6','f18f398d-f296-45da-9c64-be3699f18d98'}
 request['redraws']['cover']=[r for r in request['redraws']['cover'] if r['uuid'] not in remove]
 request['retired_tracks']['cover']+=sorted(remove)
 for r in request['via_moves']['cover']:
  if r['uuid']=='d52a6523-8b53-4a63-b1dd-2d349d822a3d':r['at_nm']=[45850000,51050000]
 request['via_moves']['cover'] += [dict(uuid='70fbea0b-47ad-41b8-844b-def48f88ddaf',at_nm=[55000000,11450000]),dict(uuid='c667bdd2-6cae-4912-8dbf-fad0d98eba7a',at_nm=[55000000,9350000])]
 changes={
 '812515ab-d134-45c8-9215-6815585b9c12':[[57331300,10206300],[56800000,10206300],[56500000,10506300],[56500000,12000000],[55000000,13500000],[54190000,13500000],[53390000,12700000]],
 '9b798315-b643-4cb9-9322-f1b90fd747b6':[[54410000,12700000],[54800000,12700000],[56000000,11500000],[56000000,9017600],[56881300,8136300]]}
 for r in request['redraws']['cover']:
  if r['uuid'] in changes:r['points_nm']=changes[r['uuid']]
 request['redraws']['cover'] += [
  dict(uuid='7382bcd4-ecaf-4d20-a938-b29325cc4f54',points_nm=[[55000000,11450000],[55000000,16250000],[51750000,19500000]]),
  dict(uuid='b766093a-33a1-4cc3-a8f6-f49deb6c469d',points_nm=[[56100000,5750000],[56100000,10350000],[55000000,11450000]]),
  dict(uuid='5d60acd4-2fd3-4c45-8a1b-4e142cbb428f',points_nm=[[53000000,6000000],[55000000,4000000],[68000000,4000000],[70000000,6000000]]),
  dict(uuid='2d298844-4c13-4154-9661-dce09080d982',points_nm=[[54000000,3750000],[37500000,3750000]]),
  dict(uuid='48d154c0-f5c8-4373-891a-a12b08047c92',points_nm=[[54000000,3750000],[54200000,3950000]]),
  dict(uuid='8ccacead-93d5-4016-8e65-da74c51122d3',points_nm=[[54200000,6000000],[54200000,3950000]]),
  dict(uuid='c92b8cc3-97da-4a05-ab6e-437c871d9928',points_nm=[[57750000,6750000],[57200000,7300000],[55500000,7300000],[54200000,6000000]]),
  dict(uuid='ef1c0615-5302-4726-9971-04f285c142b9',points_nm=[[53160000,9321250],[53600000,8881250],[53600000,8400000]]),
  dict(uuid='db06bf8a-8513-4ae5-bcb9-ce31639f368c',points_nm=[[53600000,8400000],[53800000,8200000]]),
  dict(uuid='54eb3309-d8d8-46ad-bb20-20a841a20699',points_nm=[[53800000,8200000],[54000000,8000000]]),
  dict(uuid='a3772212-541f-4a04-a3dd-a0c8ca02833e',points_nm=[[54000000,8000000],[55250000,6750000],[57000000,6750000]])
 ]
 updates={
 '6ddf7806-a470-435f-9092-4ea319c5aee6':[[37800000,53000000],[34000000,53000000],[33000000,52000000],[33000000,50000000],[33500000,49500000],[35600000,49500000]],
 '20a90713-1a9e-5caf-84a9-f6cf9ce17086':[[51800000,4800000],[51800000,10700000],[53500000,12400000],[56000000,12400000],[56300000,12700000],[56300000,13800000]],
 'dc85b1e2-ad17-46a5-a526-99c9c38812f1':[[45000000,4500000],[51800000,4500000]],
 'fb2c944f-7b79-444f-8bb1-37f625088a23':[[51800000,4500000],[51800000,4800000]],
 '7382bcd4-ecaf-4d20-a938-b29325cc4f54':[[55000000,11450000],[54800000,11650000],[54800000,16450000],[51750000,19500000]],
 '812515ab-d134-45c8-9215-6815585b9c12':[[57331300,10206300],[54200000,10206300],[53390000,11016300],[53390000,12700000]],
 'ef1c0615-5302-4726-9971-04f285c142b9':[[53160000,9321250],[54000000,9321250]],
 'db06bf8a-8513-4ae5-bcb9-ce31639f368c':[[54000000,9321250],[54000000,9150000]],
 '54eb3309-d8d8-46ad-bb20-20a841a20699':[[54000000,9150000],[54000000,9000000]],
 'a3772212-541f-4a04-a3dd-a0c8ca02833e':[[54000000,9000000],[54000000,8800000],[54400000,8400000],[55650000,8400000],[57000000,7050000],[57000000,6750000]],
 '12163c2e-5864-4e61-b00d-e25c09a00f31':[[56000000,7500000],[55750000,7750000],[55750000,8200000],[55550000,8400000],[54400000,8400000],[54000000,8800000],[54000000,9500000]],
 '78aba0c5-9bf4-4c09-b3c6-7e880cca1f43':[[65000000,12500000],[64500000,13000000],[61400000,13000000],[61000000,12600000],[61000000,7700000],[60800000,7500000],[60000000,7500000]],
 '1fec2168-ae1b-4239-9240-7b9d88df06fa':[[60400000,8513300],[60400000,11312600]],
 'c2a0ad2e-a633-4e5e-b7f2-a86afe2730dd':[[60023000,8136300],[60400000,8513300]],
 '3b3c7a06-320b-4d6e-8ffd-4c0537864e24':[[60400000,11312600],[59606300,12106300]]
 }
 ids={r['uuid'] for r in request['redraws']['cover']}
 for r in request['redraws']['cover']:
  if r['uuid'] in updates:r['points_nm']=updates[r['uuid']]
 request['redraws']['cover'] += [dict(uuid=k,points_nm=v) for k,v in updates.items() if k not in ids]
 for r in request['via_moves']['cover']:
  if r['uuid']=='12117b2c-ad36-4b96-bac5-3345fb3907cd':r['at_nm']=[51800000,4800000]
  if r['uuid']=='d52a6523-8b53-4a63-b1dd-2d349d822a3d':r['at_nm']=[45800000,51100000]
 # Bulk pad's existing POFV barrel travels with the capacitor; reconnect on
 # its original 1 mm B.Cu source process, not across the unrelated F.Cu return.
 request['retired_tracks']['cover'].append('6ddf7806-a470-435f-9092-4ea319c5aee6')
 request['redraws']['cover']=[r for r in request['redraws']['cover'] if r['uuid']!='6ddf7806-a470-435f-9092-4ea319c5aee6']
 updates={
 '20a90713-1a9e-5caf-84a9-f6cf9ce17086':[[37800000,53000000],[37800000,52200000],[40500000,49500000]],
 'dc85b1e2-ad17-46a5-a526-99c9c38812f1':[[45000000,4500000],[53500000,4500000]],
 'fb2c944f-7b79-444f-8bb1-37f625088a23':[[53500000,4500000],[53500000,4956299]],
 '4cf58cc9-56e0-4dc1-b4fd-c45773534cdd':[[62300000,9037500],[62300000,10037500]],
 '2d298844-4c13-4154-9661-dce09080d982':[[54300000,3750000],[37500000,3750000]],
 '48d154c0-f5c8-4373-891a-a12b08047c92':[[54300000,3750000],[54500000,3950000]],
 '8ccacead-93d5-4016-8e65-da74c51122d3':[[54500000,6000000],[54500000,3950000]],
 'c92b8cc3-97da-4a05-ab6e-437c871d9928':[[57750000,6750000],[57200000,7300000],[55800000,7300000],[54500000,6000000]],
 '5d60acd4-2fd3-4c45-8a1b-4e142cbb428f':[[53000000,6000000],[52500000,5500000],[52500000,4300000],[53000000,3800000],[68000000,3800000],[70000000,5800000],[70000000,6000000]],
 '76d49d6a-fdbe-4a60-ad74-df5a8e7fe197':[[40500000,54000000],[40500000,52896000],[40500000,52300000]]
 }
 ids={r['uuid'] for r in request['redraws']['cover']}
 for r in request['redraws']['cover']:
  if r['uuid'] in updates:r['points_nm']=updates[r['uuid']]
 request['redraws']['cover'] += [dict(uuid=k,points_nm=v) for k,v in updates.items() if k not in ids]
 for r in request['via_moves']['cover']:
  if r['uuid']=='12117b2c-ad36-4b96-bac5-3345fb3907cd':r['at_nm']=[37800000,53000000]
 updates={
 '1fec2168-ae1b-4239-9240-7b9d88df06fa':[[60600000,8713300],[60600000,11112600]],
 'c2a0ad2e-a633-4e5e-b7f2-a86afe2730dd':[[60023000,8136300],[60600000,8713300]],
 '3b3c7a06-320b-4d6e-8ffd-4c0537864e24':[[60600000,11112600],[59606300,12106300]],
 '78aba0c5-9bf4-4c09-b3c6-7e880cca1f43':[[65000000,12500000],[64680000,12820000],[61425000,12820000],[61025000,12420000],[61025000,7725000],[60800000,7500000],[60000000,7500000]],
 'a3772212-541f-4a04-a3dd-a0c8ca02833e':[[54000000,9000000],[54000000,8840000],[54400000,8440000],[55610000,8440000],[57000000,7050000],[57000000,6750000]],
 '12163c2e-5864-4e61-b00d-e25c09a00f31':[[56000000,7500000],[55750000,7750000],[55750000,8200000],[55510000,8440000],[54400000,8440000],[54000000,8840000],[54000000,9500000]],
 'b13f72fa-cced-4d53-ad06-c57a7350f608':[[39475000,25435000],[39965000,25435000],[57650000,7750000],[59250000,7750000],[60100000,6900000],[60100000,5750000]],
 '5a7b574f-72b1-4717-8c89-66980ab24116':[[39475000,25370000],[39475000,26400000]],
 'f2f6c3d8-bd8c-4378-93b9-05b19edce949':[[41795000,25435000],[47730000,25435000],[56600000,16565000],[56600000,7250000],[58100000,5750000]]
 }
 # Preserve the source driver-side pad/barrel owners; explicitly retire the
 # obsolete two-terminal connector tails, not unrelated shared trunks.
 tx_keep={'9558daf2-104d-4766-8beb-49568f7292ea','5a7b574f-72b1-4717-8c89-66980ab24116','b13f72fa-cced-4d53-ad06-c57a7350f608'}
 rx_keep={'890b79d9-93f3-4d13-826d-aabf4c2c35bc','f2f6c3d8-bd8c-4378-93b9-05b19edce949'}
 for net,keep in [('AUX_TXC',tx_keep),('AUX_RXC',rx_keep)]:
  for t in inv['/KVM AUXILIARY + RAIL SENSING/'+net]['tracks']:
   if t['kind']=='PCB_TRACK' and t['uuid'] not in keep:request['retired_tracks']['cover'].append(t['uuid'])
 ids={r['uuid'] for r in request['redraws']['cover']}
 for r in request['redraws']['cover']:
  if r['uuid'] in updates:r['points_nm']=updates[r['uuid']]
 request['redraws']['cover'] += [dict(uuid=k,points_nm=v) for k,v in updates.items() if k not in ids]
 request['via_moves']['cover'].append(dict(uuid='e796e1a1-afe7-47ac-a5ca-771656a5c387',at_nm=[39475000,26400000]))
 plan=json.loads((WORK/'placement.json').read_text())
 plan['carrier']=dict(path='experiments/repack/bar-corridor-20261105/carrier/board.kicad_pcb',sha256='496e90672ac0eb24920bccde582661b895ebebb88aaca5bb46ee32db86216749',poses=[dict(reference='J3',at_nm=[60349999,77400000],rotation_deg=180),dict(reference='C9',at_nm=[10550000,48000000],rotation_deg=270),dict(reference='R54',at_nm=[12800000,48625000],rotation_deg=270)])
 if not any(p['reference']=='C37' for p in plan['cover']['poses']):plan['cover']['poses'].append(dict(reference='C37',at_nm=[73500000,49600000],rotation_deg=90))
 (WORK/'placement.json').write_text(json.dumps(plan,indent=2)+'\n');request['placement']['sha256']=f._hash(WORK/'placement.json')
 (WORK/'request.json').write_text(json.dumps(request,indent=2)+'\n')
 print('Explicit local redraws authored; incomplete external reconnections remain.')
elif mode=='c37':
 b=pcbnew.LoadBoard(str(SOURCE));fp=b.FindFootprintByReference(sys.argv[2] if len(sys.argv)>2 else 'C37')
 print(fp.GetPosition(),fp.GetOrientationDegrees())
 for p in fp.Pads():
  print(p.GetNumber(),p.GetNetname(),list(p.GetPosition()))
  for t in b.GetTracks():
   if t.GetNetname()!=p.GetNetname():continue
   if any(t.IsOnLayer(l) and p.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(p.GetEffectiveShape(l),0) for l in (0,2,4,6,8,10)):
    print(f._uid(t),t.GetClass(),list(t.GetStart()),list(t.GetEnd()),t.GetParentGroup() is not None)
elif mode=='neighbors':
 b=pcbnew.LoadBoard(str(SOURCE));byid={f._uid(t):t for t in b.GetTracks()}
 for key in sys.argv[2:]:
  item=byid[key];print('SOURCE',key,item.GetNetname(),list(item.GetPosition()),item.GetParentGroup().GetName() if item.GetParentGroup() else None)
  for t in b.GetTracks():
   if f._uid(t)==key or t.GetNetname()!=item.GetNetname():continue
   if any(t.IsOnLayer(l) and item.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(item.GetEffectiveShape(l),0) for l in (0,2,4,6,8,10)):
    print(f._uid(t),b.GetLayerName(t.GetLayer()),t.GetClass(),list(t.GetStart()),list(t.GetEnd()),t.GetWidth(t.TopLayer()) if t.GetClass()=='PCB_VIA' else t.GetWidth())
elif mode=='plot':
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Polygon
 b=pcbnew.LoadBoard(str(WORK/sys.argv[2]/'cover/board.kicad_pcb'))
 fig,axes=plt.subplots(1,3,figsize=(18,8))
 nets=sorted({str(t.GetNetname()) for t in b.GetTracks()});colors={n:plt.cm.tab20(i%20) for i,n in enumerate(nets)}
 colors.update({'+3V3':'orange','+5VSB':'red','GND':'gray'})
 for ax,layer in zip(axes,(0,2,6)):
  for item in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:
   if not item.IsOnLayer(layer):continue
   poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,layer,0,10000,pcbnew.ERROR_OUTSIDE)
   shape=repack.assembly.polygon_from_native(poly)
   for geom in getattr(shape,'geoms',[shape]):
    ax.add_patch(Polygon(list(geom.exterior.coords),facecolor=colors.get(item.GetNetname(),'black'),alpha=.65))
  for fp in b.GetFootprints():
   x,y=fp.GetPosition();x/=1e6;y/=1e6
   if (37<x<48 and 18<y<27) if len(sys.argv)>3 else (50<x<67 and 3<y<16):ax.text(x,y,fp.GetReference(),fontsize=8)
  ax.set(xlim=(37,48) if len(sys.argv)>3 else (50,67),ylim=(27,18) if len(sys.argv)>3 else (16,3),aspect='equal',title=b.GetLayerName(layer));ax.grid()
 fig.savefig(WORK/'top.png',dpi=150)
elif mode=='augment':
 # Explicit one-off layer reconstruction authorized by the campaign owner.
 # Source pad UUIDs own net assignment; barrel duplication supplies process
 # only, never net or current authority for a different signal.
 import uuid
 import cec_additive_route_receiving as syntax
 import cec_native_items as items
 import cec_zone_fill as fill,cec_field_coupling as field
 parent=WORK/'local-v7/cover/board.kicad_pcb';parenthash=f._hash(parent)
 folder=WORK/(sys.argv[2] if len(sys.argv)>2 else 'native-v8')
 target=f._copy_family(parent,folder/'cover')
 b=pcbnew.LoadBoard(str(parent));byid={f._uid(t):t for t in b.GetTracks()}
 receipt=json.loads((WORK/'local-v7/draft.json').read_text())
 edits=next(r for r in receipt['boards'] if r['side']=='cover')['redraws']
 selected={'b13f72fa-cced-4d53-ad06-c57a7350f608','5a7b574f-72b1-4717-8c89-66980ab24116','f2f6c3d8-bd8c-4378-93b9-05b19edce949','78aba0c5-9bf4-4c09-b3c6-7e880cca1f43','4cf58cc9-56e0-4dc1-b4fd-c45773534cdd'}
 removed={k for r in edits if r['source_uuid'] in selected|{'9b798315-b643-4cb9-9322-f1b90fd747b6'} for k in r['added_uuids']}
 removed.add('9b798315-b643-4cb9-9322-f1b90fd747b6')
 refnet='/KVM AUXILIARY + RAIL SENSING/KVM_3V3_REF'
 assert {(fp.GetReference(),p.GetNumber()) for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==refnet}=={('J_KVM','5'),('D7','1'),('R21','1')}
 refkeep={'a3afa899-88fa-426a-8990-2824b2e59e47','8f1027ab-1857-4485-bd38-a9f43764b8f7','c3e0b582-1af8-440c-966a-eacb2f6e139f','a48395d8-c239-446f-adf5-39a9e84637ea','5ee0ae7f-9628-4873-a930-42eb5ba844ea','926e0d5d-7c01-4ddb-b297-54c39679427e','a8229488-8fe6-4c68-89ec-21e4399790ae','d243f1eb-c66f-45ac-ab08-c50d74ee1bc8','70fbea0b-47ad-41b8-844b-def48f88ddaf','7382bcd4-ecaf-4d20-a938-b29325cc4f54','b766093a-33a1-4cc3-a8f6-f49deb6c469d'}
 refkeep|={k for r in edits if r['source_uuid'] in refkeep for k in r['added_uuids']}
 obsolete_ref={k for k,t in byid.items() if t.GetNetname()==refnet and k not in refkeep}
 removed|=obsolete_ref
 items.discard_items(b,[byid[k] for k in removed])
 changed=set(selected)|{'e796e1a1-afe7-47ac-a5ca-771656a5c387'};added=set();records=[]
 def key(label):return str(uuid.uuid5(uuid.NAMESPACE_URL,parenthash+':explicit-kvm:'+label))
 def path(item,points,layer,label):
  clones=[item.Duplicate() for _ in points[2:]]
  item.SetLayer(layer);item.SetStart(pcbnew.VECTOR2I(*points[0]));item.SetEnd(pcbnew.VECTOR2I(*points[1]))
  for i,(clone,a,z) in enumerate(zip(clones,points[1:],points[2:]),1):
   uid=key(label+':leg:'+str(i));clone.m_Uuid.Clone(pcbnew.KIID(uid));clone.SetParentGroup(None)
   clone.SetLayer(layer);clone.SetStart(pcbnew.VECTOR2I(*a));clone.SetEnd(pcbnew.VECTOR2I(*z));b.Add(clone);added.add(uid)
  records.append(dict(operation='explicit_track_path',source_or_added_uuid=f._uid(item),net=item.GetNetname(),width_nm=item.GetWidth(),layer=b.GetLayerName(layer),points_nm=points))
 def via(label,ref,number,at):
  # Exact qualified Hub LP POFV process; explicit destination pad owns net.
  proto=byid['75cd976c-99f6-444d-ada4-61885efd6b18'];clone=proto.Duplicate();uid=key(label)
  pad=next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber()==number)
  clone.m_Uuid.Clone(pcbnew.KIID(uid));clone.SetParentGroup(None);clone.SetPosition(pcbnew.VECTOR2I(*at));clone.SetNet(pad.GetNet());b.Add(clone);added.add(uid)
  records.append(dict(operation='explicit_pad_owned_via',uuid=uid,net=pad.GetNetname(),net_authority_pad_uuid=f._uid(pad),net_authority_reference=ref+'.'+number,process_prototype_uuid=f._uid(proto),diameter_nm=clone.GetWidth(pcbnew.F_Cu),drill_nm=clone.GetDrillValue(),at_nm=at,process_only_not_current_authority=True))
  return clone
 path(byid['b13f72fa-cced-4d53-ad06-c57a7350f608'],[[39475000,25435000],[39475000,25800000],[40000000,26325000],[43200000,26325000],[43475000,26600000]],pcbnew.B_Cu,'tx-main')
 path(byid['5a7b574f-72b1-4717-8c89-66980ab24116'],[[43475000,26600000],[43475000,24905000],[47400000,20980000]],6,'tx-power-crossing')
 path(byid['78aba0c5-9bf4-4c09-b3c6-7e880cca1f43'],[[65000000,12500000],[64670000,12830000],[61425000,12830000],[61025000,12430000],[61025000,7725000],[60800000,7500000],[60000000,7500000]],pcbnew.F_Cu,'retained-3v3-f5-clearance')
 byid['e796e1a1-afe7-47ac-a5ca-771656a5c387'].SetPosition(pcbnew.VECTOR2I(43475000,26600000))
 path(byid['f2f6c3d8-bd8c-4378-93b9-05b19edce949'],[[41795000,25435000],[42065000,25435000],[47200000,20300000]],6,'rx-power-crossing')
 via('rx-transition','R20','2',[47200000,20300000]);via('rx-right','R20','2',[56100000,18700000]);via('tx-transition','R19','2',[57000000,18900000])
 via('tx-mid','R19','2',[47400000,20980000])
 via('comp-start','R28','2',[54200000,12700000]);via('comp-end','R28','2',[59000000,8136300])
 def newpath(label,ref,number,points,layer,width):
  pad=next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber()==number)
  track=pcbnew.PCB_TRACK(b);uid=key(label);track.m_Uuid.Clone(pcbnew.KIID(uid));track.SetNet(pad.GetNet());track.SetWidth(width);track.SetLocked(True);b.Add(track);added.add(uid)
  path(track,points,layer,label)
 newpath('rx-main','R20','2',[[47200000,20300000],[47200000,18900000],[47900000,18200000],[55600000,18200000],[56100000,18700000]],pcbnew.B_Cu,200000)
 newpath('tx-middle','R19','2',[[47400000,20980000],[46500000,20980000],[46000000,20480000],[46000000,18500000],[46800000,17700000],[56500000,17700000],[57000000,18200000],[57000000,18900000]],pcbnew.B_Cu,200000)
 newpath('rx-top','R20','2',[[56100000,18700000],[56600000,18200000],[56600000,7250000],[58100000,5750000]],6,200000)
 newpath('tx-top','R19','2',[[57000000,18900000],[57950000,17950000],[57950000,10200000],[57850000,10100000],[57850000,8150000],[58250000,7750000],[60100000,5900000],[60100000,5750000]],6,200000)
 newpath('comp-bridge','R28','2',[[54200000,12700000],[55000000,12700000],[57400000,10300000],[57400000,8900000],[58163700,8136300],[59000000,8136300]],pcbnew.B_Cu,200000)
 newpath('c32-capacitor-twig','C32','1',[[45850000,49820000],[45780000,49750000],[44820000,49750000]],pcbnew.F_Cu,280000)
 # Restore the original shared5VSB source split using an explicit1mm B.Cu
 # feed between actual source trunks; no cap-only/current-sharing inference.
 newpath('5vsb-source-feed','C_bulk1','1',[[45000000,4500000],[45000000,9500000],[52100000,16600000],[57500000,16600000],[57900000,17000000],[59500000,17000000]],pcbnew.B_Cu,1000000)
 path(byid['4cf58cc9-56e0-4dc1-b4fd-c45773534cdd'],[[62300000,9037500],[62300000,10137500],[66500000,14337500],[66500000,50000000],[64000000,52500000],[51000000,52500000]],pcbnew.B_Cu,'f5-source-reconnect')
 zones=pcbnew.ZONES()
 for z in b.Zones():
  if not z.GetIsRuleArea():zones.append(z)
 fill.compile_selected(b,zones,timeout_s=10.,initialize_selected=True)
 raw=folder/'native.kicad_pcb';field._save_field_snapshot(b,raw)
 root,old=syntax._nodes(parent);_,fresh=syntax._nodes(raw);names={id(n):k for k,n in old.items()}
 changed|={f._uid(z) for z in b.Zones() if not z.GetIsRuleArea()}
 root[1:]=[fresh[names[id(n)]] if names.get(id(n)) in changed else n for n in root[1:] if names.get(id(n)) not in removed]
 root.extend(fresh[k] for k in sorted(added));target.write_text(syntax._render(root)+'\n')
 saved=pcbnew.LoadBoard(str(target));assert field._field_snapshot_inventory(saved)==field._field_snapshot_inventory(b)
 (folder/'additions.json').write_text(json.dumps(dict(parent_sha256=parenthash,board_sha256=f._hash(target),changed_uuids=sorted(changed),removed_uuids=sorted(removed),added_uuids=sorted(added),operations=records,routing_admitted=False,current_qualified=False,release_authority=False),indent=2)+'\n')
 assert f._hash(parent)==parenthash
 print(f._hash(target))
elif mode=='reference_proof':
 import cec_native_partition_pair as partitions
 folder=WORK/sys.argv[2];target=folder/'cover/board.kicad_pcb'
 a=pcbnew.LoadBoard(str(SOURCE));b=pcbnew.LoadBoard(str(target));net='/KVM AUXILIARY + RAIL SENSING/KVM_3V3_REF'
 class FootprintView:
  def __init__(self,fp):self.fp=fp
  def Pads(self):return [p for p in self.fp.Pads() if p.GetNetname()==net]
 class NetView:
  def __init__(self,board):self.board=board
  def GetFootprints(self):return [FootprintView(fp) for fp in self.board.GetFootprints()]
  def GetTracks(self):return [t for t in self.board.GetTracks() if t.GetNetname()==net]
  def Zones(self):return [z for z in self.board.Zones() if z.GetNetname()==net]
 pads=lambda board:{(fp.GetReference(),p.GetNumber()):p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net}
 old,new=pads(a),pads(b);assert old.keys()==new.keys()=={('J_KVM','5'),('D7','1'),('R21','1')}
 rebindings={f._item_key(new[k]):f._item_key(old[k]) for k in old}
 result=partitions.compare(NetView(a),NetView(b),timeout_s=10.,retained_keys={f._item_key(p) for p in old.values()},identity_rebindings=rebindings)
 result.update(net=net,source_sha256=EXPECTED,candidate_sha256=f._hash(target),terminal_owners=sorted('.'.join(k) for k in old),scope='Actual native authored-net copper connectivity, including every original/retained track, pad, via and saved zone on this net; no endpoint graph shortcut; terminal partition only, not impedance/current qualification.')
 (folder/'reference-partition.json').write_text(json.dumps(result,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else str(v))+'\n')
 print(result['preserved'],result['native_source_component_count'],result['native_child_component_count'])
elif mode=='power_components':
 import time,cec_native_partition_pair as part
 b=pcbnew.LoadBoard(str(WORK/sys.argv[2]/'cover/board.kicad_pcb'))
 data=part._inventory(b,time.monotonic()+10.,dict(items=16384,vertices=200000,polygons=4096))
 for component in data['components']:
  live=[data['live'][k] for k in component if k in data['live']]
  if not any(i.GetNetname()=='+5VSB' for i in live) and not any('+5VSB' in str(k) for k in component):continue
  print('COMPONENT',len(component),'PADS',[(i.GetParentFootprint().GetReference(),i.GetNumber())for i in live if i.GetClass()=='PAD'])
  if len(component)<60:
   for i in live:
    if i.GetClass() in ('PCB_TRACK','PCB_VIA'):print(f._uid(i),i.GetClass(),b.GetLayerName(i.GetLayer()),list(i.GetStart()),list(i.GetEnd()),i.GetWidth(i.TopLayer())if i.GetClass()=='PCB_VIA'else i.GetWidth())
  if not live or len(component)<8:print(component)
 for key,rows in data['zones'].items():
  if key[1]!='+5VSB':continue
  for row in rows:
   k=f._item_key(row['item']);idx=data['component_of'][k]
   if len(data['components'][idx])<8:print('ISLAND',key,row['digest'],row['shape'].BBox().GetPosition(),row['shape'].BBox().GetSize())
elif mode=='terminal_proof':
 import time,cec_native_partition_pair as part
 folder=WORK/sys.argv[2];target=folder/'cover/board.kicad_pcb'
 a=pcbnew.LoadBoard(str(SOURCE));b=pcbnew.LoadBoard(str(target));deadline=time.monotonic()+10.
 bound=dict(items=16384,vertices=200000,polygons=4096)
 old=part._inventory(a,deadline,bound);new=part._inventory(b,deadline,bound)
 pads=lambda board:{(f._uid(fp),f._uid(p),p.GetNumber()):p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode()>0}
 left,right=pads(a),pads(b);assert left.keys()==right.keys()
 rebinding={};moved=[]
 for k,p in left.items():
  q=right[k]
  assert p.GetNetname()==q.GetNetname() and p.GetShape()==q.GetShape() and tuple(p.GetSize())==tuple(q.GetSize()) and tuple(p.GetDrillSize())==tuple(q.GetDrillSize()) and tuple(p.GetLayerSet().CuStack())==tuple(q.GetLayerSet().CuStack())
  rebinding[f._item_key(q)]=f._item_key(p)
  if tuple(p.GetPosition())!=tuple(q.GetPosition()):moved.append(dict(reference=p.GetParentFootprint().GetReference(),number=p.GetNumber(),source_nm=list(p.GetPosition()),candidate_nm=list(q.GetPosition())))
 oldparts={};newparts={}
 for p in left.values():oldparts.setdefault(old['component_of'][f._item_key(p)],set()).add(f._item_key(p))
 for p in right.values():newparts.setdefault(new['component_of'][f._item_key(p)],set()).add(rebinding[f._item_key(p)])
 demoted=[v for v in oldparts.values() if not any(v<=w for w in newparts.values())]
 result=dict(source_sha256=EXPECTED,candidate_sha256=f._hash(target),terminal_count=len(left),source_terminal_component_count=len(oldparts),candidate_terminal_component_count=len(newparts),native_source_copper_components=len(old['components']),native_candidate_copper_components=len(new['components']),preserved=not demoted,demoted_terminal_components=demoted,moved_pads=moved,method='Per-authored-net native CONNECTIVITY_DATA over real pads/tracks/vias and decomposed saved-fill islands; terminal partition comparison with exact moved-pad identity rebindings, not endpoint graph or whole-zone UUID shortcut.',retained_copper_partition_or_current_qualification=False,routing_admitted=False,release_authority=False)
 (folder/'terminal-partition.json').write_text(json.dumps(result,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else str(v))+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('moved_pads','demoted_terminal_components')}))
elif mode=='pairs':
 from cec_pipeline.pairs import receive
 folder=WORK/sys.argv[2];result=receive(SOURCE,folder/'cover/board.kicad_pcb',timeout_s=8.)
 (folder/'pairs.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
elif mode=='summarize':
 import cec_additive_route_receiving as syntax,cec_copper_echo as echo
 folder=WORK/sys.argv[2];target=folder/'cover/board.kicad_pcb'
 b=pcbnew.LoadBoard(str(target));a=pcbnew.LoadBoard(str(SOURCE))
 report=json.loads((folder/'cover-drc.json').read_text());addition=json.loads((folder/'additions.json').read_text())
 _,native=syntax._nodes(target);_,source_nodes=syntax._nodes(SOURCE)
 stripped=lambda node:echo._freeze([v for v in node if not (isinstance(v,list) and v and v[0] in ('uuid','at','net'))])
 via_records=[r for r in addition['operations'] if r['operation']=='explicit_pad_owned_via']
 for row in via_records:
  assert stripped(native[row['uuid']])==stripped(source_nodes[row['process_prototype_uuid']])
 old={f._uid(t):t for t in a.GetTracks()};new={f._uid(t):t for t in b.GetTracks()}
 before,after=syntax._nodes(SOURCE)[1],syntax._nodes(target)[1]
 changed=[k for k in before.keys()&after.keys() if echo._freeze(before[k])!=echo._freeze(after[k])]
 proof=json.loads((folder/'terminal-partition.json').read_text());pairs=json.loads((folder/'pairs.json').read_text())
 assert proof['preserved'] and pairs['ok'] and not report['unconnected_items'] and not any(r['severity']=='error' for r in report['violations'])
 carrier=pcbnew.LoadBoard(str(WORK/'local-v7/carrier/board.kicad_pcb'))
 plan=json.loads((WORK/'placement.json').read_text());contract=json.loads((ROOT/plan['contract']['path']).read_text())
 stack,_=repack.assembly.evaluate_boards(carrier,b,contract)
 result=dict(schema=1,status='PRIVATE_NATIVE_CONNECTED_ENGINEERING_CANDIDATE',source=dict(path=str(SOURCE),sha256=EXPECTED,unchanged=f._hash(SOURCE)==EXPECTED),candidate=dict(path=str(target),sha256=f._hash(target)),owners=['J_KVM','F5','D7','R28','C_bulk1','C32','C37'],placement_binding=dict(path=str(WORK/'placement.json'),sha256=f._hash(WORK/'placement.json')),native_DRC=dict(errors=0,opens=0,warnings=sum(r['severity']=='warning' for r in report['violations']),report=str(folder/'cover-drc.json'),sha256=f._hash(folder/'cover-drc.json'),receipt=str(folder/'drc-receipt.json')),terminal_partition=dict(path=str(folder/'terminal-partition.json'),preserved=True,terminals=proof['terminal_count'],source_components=proof['source_terminal_component_count'],candidate_components=proof['candidate_terminal_component_count']),pair_nonregression=dict(path=str(folder/'pairs.json'),ok=True,metrics_unchanged=True,continuous_return_proof=False),paired_native_assembly_screen=stack,retired_source_copper_uuids=sorted(old.keys()-new.keys()),added_copper_uuids=sorted(new.keys()-old.keys()),changed_native_owner_uuids=sorted(changed),explicit_via_records=via_records,all_added_via_process_AST_matches_exact_source_except_uuid_position_net=True,source_proto_process_ownership='Source75cd976c supplies physical barrel process only; each new net is explicitly authorized by recorded target pad UUID. No inherited current allocation or annotation membership.',native_operations=str(folder/'additions.json'),construction_recipe=str(WORK/'build.py'),source_request=str(WORK/'request.json'),COMP_role_evidence=['scripts/cec_hub_holdup.py reference ratio/hysteresis network','beta/hub-standard-rev2/pipeline-policy.json critical_route_nets includes COMP_THRESH, BLACKOUT_SENSE, PWR_FAIL_INT; no front-only or Kelvin designation found'],power_reconstruction_notes=['F5 output reconnect retains exact existing1mm B.Cu width and source barrel process; long route requires current/thermal/field receiving.','Shared5VSB split restored between actual source trunks using new1mm B.Cu feed; no source-domain sharing credit inferred.','C32 isolated shunt capacitor reconnect uses0.28mm F.Cu twig; not asserted as a2.5A source-to-load path. Independent current/decoupling receiving remains required.'],outstanding=['Independent source-retirement and changed-copper admission','Critical COMP/PWR/BLACKOUT analog integrity and coupling review','Shared5VSB and KVM source current/voltage-drop/thermal receiving','New via/process/POFV receiving and assembly qualification','Continuous UART/reference-return and full field screening','Production release qualification'],routing_admitted=False,current_qualified=False,assembly_qualified=False,release_authority=False)
 output=ROOT/'docs/evidence/20261105-bar-land/hub-kvm-construction.json';output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(candidate_sha256=result['candidate']['sha256'],retired=len(result['retired_source_copper_uuids']),added=len(result['added_copper_uuids']),added_vias=len(via_records),paired_stack_ok=stack['ok'],evidence_sha256=f._hash(output))))
elif mode=='stage':
 print(json.dumps(drafts.stage(json.loads((WORK/'request.json').read_text()),WORK/sys.argv[2],refill=True),indent=2))
elif mode=='drc':
 import cec_native_drc_runner as n
 folder=WORK/sys.argv[2]
 result=n.run(folder/'cover/board.kicad_pcb',folder/'cover-drc.json',reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/hub-standard-rev2/library/fp-lib-table')
 (folder/'drc-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 p=json.loads((folder/'cover-drc.json').read_text());print(json.dumps(dict(errors=[r for r in p['violations'] if r['severity']=='error'],opens=p['unconnected_items']),indent=2))
else:raise ValueError(mode)
assert f._hash(SOURCE)==EXPECTED
