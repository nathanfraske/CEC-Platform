#!/usr/bin/env python3
"""Read-only, identity-bound, portable PCB inspection reports.

Native KiCad plots use SAVED copper, never zone refill or FEM filler. A report
is a review snapshot, not release authority. All heavyweight operations run in
separate, bounded processes. The HTTP adapter serves only manifest-listed assets.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src')not in sys.path:sys.path.insert(0,str(ROOT/'src'))
STATIC=Path(__file__).with_name('static')
INDEX=ROOT/'docs/pcb-suite-inspection-current.json'
NAMES={'atx-24pin-rev3':'ATX 24-pin','hub-standard-rev2':'Standard Hub',
 '12vhpwr-standard':'12VHPWR','eps-8pin-rev3':'EPS 8-pin',
 'pcie-8pin-2port':'PCIe two-port','pcie-8pin-3port':'PCIe three-port',
 'output-daughterboards/atx24-out-db':'ATX output daughterboard',
 'output-daughterboards/eps-out-db':'EPS output daughterboard',
 'output-daughterboards/pcie-out-db':'PCIe output daughterboard'}
ROLES={'atx-24pin-rev3':'ATX power distribution, sensing and Hub mating interface',
 'hub-standard-rev2':'Central control, communications and matched-stack interface',
 '12vhpwr-standard':'12VHPWR power distribution, sensing and auxiliary fan/control interfaces',
 'eps-8pin-rev3':'EPS power distribution and current/voltage sensing',
 'pcie-8pin-2port':'Two-port PCIe power distribution and sensing',
 'pcie-8pin-3port':'Three-port PCIe power distribution and sensing'}
_CACHE=None


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.partial')
    temporary.write_text(json.dumps(data,ensure_ascii=True,separators=(',',':'),allow_nan=False))
    temporary.replace(path)


def verify_receipt(path, expected):
    path=Path(path).resolve(strict=True)
    if sha(path)!=expected:raise ValueError('inspection_receipt_identity_mismatch')
    if str(ROOT/'src')not in sys.path:sys.path.insert(0,str(ROOT/'src'))
    from cec_pipeline.checkpoint import normalize
    receipt=normalize(path,expected)
    if receipt.get('complete') is not True:raise ValueError('complete_inspection_receipt_required')
    boards=receipt.get('boards',[])
    if not 1<=len(boards)<=64 or len({b['board']for b in boards})!=len(boards):
        raise ValueError('bounded_unique_inspection_boards_required')
    for row in boards:
        if sha(row['path'])!=row['sha256']:raise ValueError('inspection_board_identity_mismatch:'+row['board'])
        if sha(row['result'])!=row['result_sha256']:raise ValueError('inspection_native_report_identity_mismatch')
        native=json.loads(Path(row['result']).read_text())
        actual=dict(opens=len(native.get('unconnected_items',[])),
            errors=sum(v['severity']=='error'for v in native.get('violations',[])),
            warnings=sum(v['severity']=='warning'for v in native.get('violations',[])),
            exclusions=len(native.get('excluded_violations',[])))
        if actual!=row['counts']:raise ValueError('inspection_native_count_mismatch')
    return receipt


def bounded(command, *, timeout=9.7):
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:out,err=child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL);child.communicate()
        raise RuntimeError('inspection_native_operation_exceeded_9_7_seconds')
    if child.returncode:
        raise RuntimeError('inspection_native_operation_failed:'+err.decode(errors='replace')[-1600:])
    return out.decode(errors='replace')


def plot_command(board, target, layers):
    # Fixed page preserves native board coordinates. Reframe only SVG root
    # afterwards. --check-zones is deliberately absent: no refill is authorized.
    command=['kicad-cli','pcb','export','svg','--mode-single','--output',str(target),
        '--layers',','.join(layers),'--page-size-mode','1','--exclude-drawing-sheet',
        '--drill-shape-opt','2',str(board)]
    if layers[0].endswith(('.Silkscreen','.Fab')):command.insert(-1,'--black-and-white')
    return command


def native_configuration(native):
    """Keep disabled checks distinct from zero errors and explicit exclusions."""
    return dict(kicad_version=native.get('kicad_version','Not recorded'),
        measured_at=native.get('date','Not recorded'),
        included_severities=native.get('included_severities',[]),
        ignored_checks=native.get('ignored_checks',[]))


def reframe_svg(path, bounds):
    tree=ET.parse(path);root=tree.getroot()
    if root.tag!='{http://www.w3.org/2000/svg}svg':raise ValueError('native_svg_required')
    x,y,w,h=bounds
    root.set('viewBox',' '.join(format(v,'.6f')for v in bounds))
    root.set('width',format(w,'.6f')+'mm');root.set('height',format(h,'.6f')+'mm')
    # Only page framing changes. Every native copper/path/fill child is retained.
    ET.register_namespace('','http://www.w3.org/2000/svg')
    tree.write(path,encoding='utf-8',xml_declaration=True)


def _visible_component_field_layers(board):
    """Actual saved field layers, not a combined plot or an inferred BOM."""
    import pcbnew
    layers = {pcbnew.F_SilkS: 'F.Silkscreen', pcbnew.B_SilkS: 'B.Silkscreen',
              pcbnew.F_Fab: 'F.Fab', pcbnew.B_Fab: 'B.Fab'}
    counts = {name: dict(Value=0, MPN=0) for name in layers.values()}
    for fp in board.GetFootprints():
        for label in fp.GetFields():
            name, layer = str(label.GetName()), int(label.GetLayer())
            if (name in ('Value', 'MPN') and layer in layers
                    and label.IsVisible() and str(label.GetText()).strip()):
                counts[layers[layer]][name] += 1
    return dict(schema_version=1, scope='visible_nonempty_Value_MPN_fields_only',
                by_layer=counts,
                silk_visible_total=sum(sum(counts[name].values()) for name in ('F.Silkscreen', 'B.Silkscreen')),
                fab_visible_total=sum(sum(counts[name].values()) for name in ('F.Fab', 'B.Fab')),
                reference_and_functional_labels_excluded=True)


def _metadata(spec_path, output):
    import cec_swig_guard;cec_swig_guard.pin()
    import pcbnew,wx
    quiet=wx.LogNull()
    spec=json.loads(Path(spec_path).read_text());source=Path(spec['path'])
    if sha(source)!=spec['sha256']:raise ValueError('native_metadata_source_changed')
    board=pcbnew.LoadBoard(str(source));mm=lambda v:round(v/1e6,6)
    point=lambda p:[mm(p.x),mm(p.y)]
    bbox=lambda b:[mm(b.GetX()),mm(b.GetY()),mm(b.GetWidth()),mm(b.GetHeight())]
    edges=[d for d in board.GetDrawings()if d.GetLayer()==pcbnew.Edge_Cuts]
    raw=board.GetBoardEdgesBoundingBox();half=max((d.GetWidth()for d in edges),default=0)/2
    bounds=[mm(raw.GetX()+half),mm(raw.GetY()+half),mm(raw.GetWidth()-2*half),mm(raw.GetHeight()-2*half)]
    if bounds[2]<=0 or bounds[3]<=0:raise ValueError('valid_native_board_outline_required')
    all_bounds=bbox(board.GetBoundingBox())
    x=min(bounds[0],all_bounds[0])-2;y=min(bounds[1],all_bounds[1])-2
    right=max(bounds[0]+bounds[2],all_bounds[0]+all_bounds[2])+2
    bottom=max(bounds[1]+bounds[3],all_bounds[1]+all_bounds[3])+2
    frame=[x,y,right-x,bottom-y]
    props={str(k):str(v)for k,v in board.GetProperties().items()}
    import cec_fab_profile as fabrication
    profile_name=props.get('CEC_FAB_PROFILE');profile=fabrication.get_profile(profile_name)if profile_name else None
    settings=board.GetDesignSettings();defaults={}
    for key in('m_MinClearance','m_TrackMinWidth','m_ViasMinSize','m_MinThroughDrill',
               'm_HoleToHoleMin','m_HoleClearance','m_CopperEdgeClearance','m_ViasMinAnnularWidth'):
        value=getattr(settings,key,None)
        if isinstance(value,(int,float)):defaults[key]=mm(value)
    layers=[]
    for layer in board.GetEnabledLayers().CuStack():
        standard=str(pcbnew.BOARD.GetStandardLayerName(layer))
        entry=dict(id=int(layer),name=standard,label=str(board.GetLayerName(layer)))
        if profile and standard in fabrication.COPPER_LAYERS:
            entry.update(declared_copper_um=fabrication.copper_thickness_mm(profile_name,standard)*1000,
                declared_role=profile['roles'][fabrication.COPPER_LAYERS.index(standard)])
        layers.append(entry)
    nets=defaultdict(lambda:dict(pads=[],tracks=0,vias=0,length_mm=0.,layers=set(),widths=set(),zones=0))
    components=[];items={};drills=[]
    for fp in board.GetFootprints():
        fields={str(f.GetName()):str(f.GetText())for f in fp.GetFields()}
        pads=[];boxes=[]
        for p in fp.Pads():
            net=str(p.GetNetname());pos=point(p.GetPosition());pb=bbox(p.GetBoundingBox());boxes.append(pb)
            drill=point(p.GetDrillSize());uid=str(p.m_Uuid.AsString())
            entry=dict(pin=str(p.GetNumber()),net=net,at=pos,size=point(p.GetSize()),
                drill=drill,uuid=uid,bounds=pb,layers=[str(pcbnew.BOARD.GetStandardLayerName(l))for l in p.GetLayerSet().CuStack()])
            pads.append(entry);items[uid]=dict(kind='pad',net=net,at=pos,bounds=pb,ref=fp.GetReference(),pin=entry['pin'])
            if max(drill)>0:drills.append(max(drill))
            if net:nets[net]['pads'].append(dict(ref=fp.GetReference(),pin=entry['pin'],at=pos))
        if boxes:
            xx=min(b[0]for b in boxes);yy=min(b[1]for b in boxes)
            fb=[xx,yy,max(b[0]+b[2]for b in boxes)-xx,max(b[1]+b[3]for b in boxes)-yy]
        else:fb=[*point(fp.GetPosition()),1.,1.]
        components.append(dict(ref=fp.GetReference(),value=fp.GetValue(),footprint=fp.GetFPIDAsString(),
            at=point(fp.GetPosition()),rotation=fp.GetOrientationDegrees(),side='B'if fp.IsFlipped()else'F',
            dnp=bool(fp.IsDNP()),fields=fields,pads=pads,bounds=fb))
    track_rows=[];via_rows=[];by_layer=defaultdict(lambda:dict(tracks=0,length_mm=0.,zones=0,filled_islands=0))
    for t in board.GetTracks():
        uid=str(t.m_Uuid.AsString());net=str(t.GetNetname());kind=t.GetClass()
        if kind=='PCB_VIA':
            row=dict(uuid=uid,net=net,at=point(t.GetPosition()),diameter=mm(t.GetWidth()),drill=mm(t.GetDrillValue()))
            via_rows.append(row);drills.append(row['drill']);items[uid]=dict(row,kind='via',bounds=bbox(t.GetBoundingBox()))
            if net:nets[net]['vias']+=1
        else:
            layer=str(pcbnew.BOARD.GetStandardLayerName(t.GetLayer()));length=mm(t.GetLength())
            row=dict(uuid=uid,net=net,layer=layer,a=point(t.GetStart()),b=point(t.GetEnd()),width=mm(t.GetWidth()),
                length_mm=length,kind='arc'if kind=='PCB_ARC'else'track',bounds=bbox(t.GetBoundingBox()))
            track_rows.append(row);items[uid]=row
            by_layer[layer]['tracks']+=1;by_layer[layer]['length_mm']+=length
            if net:
                n=nets[net];n['tracks']+=1;n['length_mm']+=length;n['layers'].add(layer);n['widths'].add(row['width'])
    zone_count=0
    for z in board.Zones():
        if z.GetIsRuleArea():continue
        zone_count+=1;net=str(z.GetNetname())
        zb=bbox(z.GetBoundingBox())
        items[str(z.m_Uuid.AsString())]=dict(kind='zone',net=net,
            at=[zb[0]+zb[2]/2,zb[1]+zb[3]/2],bounds=zb)
        for l in z.GetLayerSet().CuStack():
            layer=str(pcbnew.BOARD.GetStandardLayerName(l));by_layer[layer]['zones']+=1
            by_layer[layer]['filled_islands']+=z.GetFilledPolysList(l).OutlineCount()if z.HasFilledPolysForLayer(l)else 0
            if net:nets[net]['layers'].add(layer)
        if net:nets[net]['zones']+=1
    net_rows=[]
    for name,rec in sorted(nets.items()):
        rec['layers']=sorted(rec['layers']);rec['widths']=sorted(rec['widths']);rec['length_mm']=round(rec['length_mm'],4)
        net_rows.append(dict(name=name,**rec))
    for l in layers:l.update(by_layer[l['name']])
    native=json.loads(Path(spec['result']).read_text());findings=[]
    for i,rec in enumerate([*native.get('unconnected_items',[]),*native.get('violations',[])]):
        loci=[];uuids=[]
        for item in rec.get('items',[]):
            pos=item.get('pos',{})
            if 'x'in pos and'y'in pos:loci.append([pos['x'],pos['y']])
            if item.get('uuid'):uuids.append(item['uuid'])
        findings.append(dict(id='native-'+str(i),kind='native',severity=rec['severity'],type=rec['type'],
            description=rec['description'],loci=loci,uuids=uuids,items=rec.get('items',[])))
    field=spec.get('field')
    import cec_route_quality as quality
    from cec_pipeline.issues import viewer_findings
    craft=quality.analyze_board(board)
    findings.extend(viewer_findings(craft,items))
    if field:
        if field['candidate_sha256']!=spec['sha256']:raise ValueError('field_receipt_not_for_this_saved_board')
        for i,key in enumerate(field['new_field_blocker_keys']):
            parsed=json.loads(key);pair=parsed[0]
            uuids=field.get('native_members_by_key',{}).get(key,[p[0]for p in pair])
            if key in field.get('native_members_by_key',{})and any(u not in items for u in uuids):
                raise ValueError('field_run_constituent_missing_from_saved_board')
            selected=[items[u]for u in uuids if u in items]
            loci=[p for item in selected for p in(item.get('a'),item.get('b'))if p]
            findings.append(dict(id='field-'+str(i),kind='coupling',severity='blocker',type='field-coupling',
                description=parsed[1],nets=[p[1]for p in pair],layers=[p[2]for p in pair],
                angle=parsed[2],parallel_mm=parsed[3],gap_mm=parsed[4],loci=loci,uuids=uuids,
                location_kind='bounds of exact implicated native tracks',recorded_key=key))
    metadata=dict(board=spec['board'],name=NAMES.get(spec['board'],spec['board']),
        role=ROLES.get(spec['board'],'Matched output daughterboard / power mating interface'),
        source=str(source),sha256=spec['sha256'],counts=spec['counts'],outline=bounds,frame=frame,
        thickness_mm=mm(board.GetDesignSettings().GetBoardThickness()),properties=props,layers=layers,
        board_default_limits_mm=defaults,declared_profile=profile_name,
        annotation_fields=_visible_component_field_layers(board),
        components=sorted(components,key=lambda f:(re.sub(r'\d+','',f['ref']),int(re.search(r'\d+',f['ref']).group())if re.search(r'\d+',f['ref'])else 0,f['ref'])),
        nets=net_rows,tracks=track_rows,vias=via_rows,findings=findings,
        craft_observer_complete=craft.get('complete')is True,
        stats=dict(components=len(components),populated_components=sum(not c['dnp']for c in components),
            pads=sum(len(c['pads'])for c in components),nets=len(net_rows),tracks=len(track_rows),vias=len(via_rows),
            zones=zone_count,track_length_mm=round(sum(t['length_mm']for t in track_rows),3),
            ground_track_length_mm=round(sum(t['length_mm']for t in track_rows if t['net']=='GND'),3),
            min_drill_mm=min(drills)if drills else None,max_drill_mm=max(drills)if drills else None),
        native_report_sha256=spec['result_sha256'],native_verification=native_configuration(native),
        field_status=f"{len(field['new_field_blocker_keys'])} recorded blockers; not admitted"if field else'Not established by this native-only snapshot',
        qualification='Native routing closure is not electrical, thermal, current-capacity, mating or fabrication approval.')
    if sha(source)!=spec['sha256']:raise ValueError('native_metadata_source_changed_during_read')
    write_json(output,metadata)


def _normalize_field_report(value):
    """Adapt recorded evidence, never infer fresh qualification from a filename."""
    def need(condition, reason='complete_valid_field_evidence_required'):
        if not condition:raise ValueError(reason)
    need(type(value)is dict and value.get('complete')is True)
    candidate=value.get('candidate_sha256')
    need(type(candidate)is str and re.fullmatch(r'[a-f0-9]{64}',candidate))
    if 'result'in value:
        body=value['result']
        need(type(body)is dict and body.get('complete')is True
             and 'new_field_blocker_keys'not in value)
        keys=body.get('blocker_keys')
    else:
        body=None;keys=value.get('new_field_blocker_keys')
    need(type(keys)is list and len(keys)<=16384)
    normalized=[]
    for key in keys:
        need(type(key)is str)
        try:parsed=json.loads(key)
        except (ValueError,TypeError)as exc:raise ValueError('malformed_field_blocker_key')from exc
        need(type(parsed)is list and len(parsed)==6,'malformed_field_blocker_key')
        members,reason=parsed[:2]
        need(type(members)is list and len(members)==2
             and all(type(member)is list and len(member)==3
                     and all(type(part)is str and part for part in member)for member in members)
             and len({member[0]for member in members})==2
             and type(reason)is str and bool(reason),'malformed_field_blocker_key')
        numbers=parsed[2:]
        need(all(type(number)in(int,float)and math.isfinite(number)for number in numbers)
             and 0<=numbers[0]<=90 and numbers[1]>=0 and 0<=numbers[3]<=100,
             'malformed_field_blocker_key')
        normalized.append(json.dumps([sorted(members),reason,*map(float,numbers)],
                                     separators=(',',':'),allow_nan=False))
    need(len(set(normalized))==len(normalized),'duplicate_field_blocker_key')
    if body is not None:
        if 'blocking_count'in body:
            need(type(body['blocking_count'])is int and body['blocking_count']==len(normalized))
        if 'ok'in body:
            need(type(body['ok'])is bool and body['ok']==(not normalized))
    result=dict(candidate_sha256=candidate,new_field_blocker_keys=sorted(normalized))
    if body is not None and body.get('audit_basis')=='exact_collinear_union_v1':
        from cec_pipeline.fields import inventory
        need(inventory(body).get('status')=='known','complete_semantic_field_geometry_required')
        import cec_field_coupling as field
        lookup={}
        for row in body['interactions']:
            if not row['blocking']:continue
            raw_key=next(iter(field.blocker_keys(dict(interactions=[row]))))
            # Use the same numeric canonicalization as the historical adapter.
            parts=json.loads(raw_key)
            key=json.dumps([sorted(parts[0]),parts[1],*map(float,parts[2:])],
                           separators=(',',':'),allow_nan=False)
            need(key in normalized and key not in lookup,'field_run_key_inventory_mismatch')
            lookup[key]=sorted({uid for group in row['member_track_uuids']for uid in group})
        need(set(lookup)==set(normalized),'field_run_key_inventory_mismatch')
        result['native_members_by_key']=lookup
    return result


def field_receipt_index(receipt, *, receipt_path, field_receipt=None, field_sha256=None):
    """Hash-check ALL observations and index only by exact saved PCB identity.

    A newer receipt does not supersede contradictory evidence for identical
    copper. Equivalent observations can coexist with their actual provenance.
    Stale-but-valid observations remain keyed to their old candidate, never
    relabeled as evidence for a changed board.
    """
    entries=receipt.get('field_receipts',[])
    if type(entries)is not list or len(entries)>128:raise ValueError('bounded_field_receipts_required')
    if (field_receipt is None)!=(field_sha256 is None):
        raise ValueError('exact_field_receipt_and_sha256_required')
    sources=[(entry,True)for entry in entries]
    if field_receipt is not None:sources.append((dict(path=str(field_receipt),sha256=field_sha256),False))
    root=Path(receipt_path).resolve(strict=True).parent;indexed={};total=0
    for entry,relative in sources:
        if (type(entry)is not dict or type(entry.get('path'))is not str or not entry['path']
                or type(entry.get('sha256'))is not str
                or not re.fullmatch(r'[a-f0-9]{64}',entry['sha256'])):
            raise ValueError('exact_field_receipt_and_sha256_required')
        path=Path(entry['path']);path=(root/path if relative and not path.is_absolute()else path).resolve(strict=True)
        size=path.stat().st_size;total+=size
        if size>16*1024*1024 or total>64*1024*1024:raise ValueError('bounded_field_evidence_required')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']or sha(path)!=entry['sha256']:
            raise ValueError('field_evidence_identity_mismatch')
        observation=_normalize_field_report(json.loads(raw))
        candidate=observation['candidate_sha256'];previous=indexed.get(candidate)
        if previous is not None and previous['new_field_blocker_keys']!=observation['new_field_blocker_keys']:
            raise ValueError('conflicting_field_evidence_for_same_candidate')
        if previous is None:
            previous=observation;previous['recorded_field_receipts']=[];indexed[candidate]=previous
        elif observation.get('native_members_by_key'):
            if previous.get('native_members_by_key')not in(None,observation['native_members_by_key']):
                raise ValueError('conflicting_field_constituents_for_same_candidate')
            previous['native_members_by_key']=observation['native_members_by_key']
        provenance=dict(path=str(path),sha256=entry['sha256'])
        if provenance not in previous['recorded_field_receipts']:previous['recorded_field_receipts'].append(provenance)
    return indexed


def copy_review_refinements(receipt,out,assets):
    """Keep every received layer/crop pair, including legacy single views."""
    refinements=[]
    for row in receipt.get('selected_children',[]):
        copied=dict(row);copied['plots']={}
        for key,plot in row.get('reviewed_native_plots',{}).items():
            legacy=key in('before','after')
            if (not(legacy or re.fullmatch(r'(?:before|after)-(?:F|B|In[1-4])-Cu-[a-f0-9]{16}\.svg',key))
                    or sha(plot['path'])!=plot['sha256']):
                raise ValueError('reviewed_refinement_plot_identity_mismatch')
            relative='reviews/'+re.sub(r'[^a-zA-Z0-9_-]','-',row['board'])+'-'+key+('.svg'if legacy else'')
            target=Path(out)/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(Path(plot['path']).read_bytes())
            assets[relative]=sha(target);copied['plots'][key]=relative
        copied.pop('reviewed_native_plots',None);refinements.append(copied)
    return refinements


def build(args):
    receipt=verify_receipt(args.receipt,args.receipt_sha256)
    fields=field_receipt_index(receipt,receipt_path=args.receipt,
                               field_receipt=args.field_receipt,field_sha256=args.field_sha256)
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    boards=[];assets={};env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
    for index,row in enumerate(receipt['boards']):
        slug=re.sub(r'[^a-zA-Z0-9_-]','-',row['board']);directory=out/'assets'/slug;directory.mkdir(parents=True,exist_ok=True)
        spec=dict(row)
        if row['sha256']in fields:spec['field']=fields[row['sha256']]
        spec_path=directory/'input.json';write_json(spec_path,spec)
        metadata_path=directory/'metadata.json'
        print(json.dumps(dict(board=row['board'],phase='native metadata',index=index+1,total=len(receipt['boards']))),flush=True)
        bounded([sys.executable,str(Path(__file__).resolve()),'--metadata-worker',str(spec_path),str(metadata_path)])
        data=json.loads(metadata_path.read_text());data['slug']=slug;plots={}
        layer_names=[l['name']for l in data['layers']]
        layer_names+=['F.Silkscreen','B.Silkscreen','F.Fab','B.Fab']
        for layer in layer_names:
            filename=re.sub(r'[^a-zA-Z0-9]','-',layer)+'.svg';target=directory/filename
            print(json.dumps(dict(board=row['board'],phase='native saved-copper plot',layer=layer)),flush=True)
            bounded(plot_command(row['path'],target,[layer,'Edge.Cuts']))
            reframe_svg(target,data['frame']);relative=str(target.relative_to(out));assets[relative]=sha(target)
            plots[layer]=relative
        data['plots']=plots;boards.append(data)
        native_path=directory/'native.json';native_path.write_bytes(Path(row['result']).read_bytes())
        data['native_report_asset']=str(native_path.relative_to(out));assets[data['native_report_asset']]=sha(native_path)
        if sha(row['path'])!=row['sha256']:raise ValueError('inspection_source_changed_after_plots')
    order=['hub-standard-rev2','atx-24pin-rev3','eps-8pin-rev3','12vhpwr-standard','pcie-8pin-2port','pcie-8pin-3port',
        'output-daughterboards/atx24-out-db','output-daughterboards/eps-out-db','output-daughterboards/pcie-out-db']
    boards.sort(key=lambda b:order.index(b['board'])if b['board']in order else 99)
    refinements=copy_review_refinements(receipt,out,assets)
    manifest=dict(schema=1,title=f'CEC {len(boards)}-board inspection',source_receipt=str(Path(args.receipt).resolve()),
        source_receipt_sha256=args.receipt_sha256,boards=boards,assets=assets,review_refinements=refinements,
        totals={k:sum(b['counts'][k]for b in boards)for k in('opens','errors','warnings','exclusions')},
        source_inputs_rechecked=True,release_authority=False)
    finalize(out,manifest)


def finalize(out,manifest):
    """Package an identity-checked snapshot without modifying native geometry."""
    verify_receipt(manifest['source_receipt'],manifest['source_receipt_sha256'])
    now=datetime.now(ZoneInfo('America/Chicago'));boards=manifest['boards'];assets=manifest['assets']
    measured=sorted({b['native_verification']['measured_at'][:10]for b in boards})
    manifest.update(created=now.isoformat(),inspection_date=now.date().isoformat(),
        native_verification_date=', '.join(measured))
    field_count=sum(f['kind']=='coupling'for b in boards for f in b['findings'])
    manifest['limitations']=[
        f"Native counts were measured on {manifest['native_verification_date']}; exact PCB/report bytes rechecked for this report.",
        f'{field_count} coupling blockers remain recorded. Other electrical/thermal/fit qualification is not established here.',
        'Configured ignored native checks are listed per board. Zero errors does not mean every available check was enabled.',
        'Selection boxes and issue markers are review annotations, not added copper. Native SVGs show saved copper; no refill/FEM filler.']
    for name in('cec_suite_inspection.html','cec_suite_inspection.js','cec_suite_inspection.css','cec_viewport.js'):
        target='index.html'if name.endswith('.html')else name
        (out/target).write_bytes((STATIC/name).read_bytes());assets[target]=sha(out/target)
    manifest_path=out/'manifest.json';write_json(manifest_path,manifest)
    (out/'report-data.js').write_text('window.CEC_INSPECTION_MANIFEST='+json.dumps(manifest,ensure_ascii=True,separators=(',',':'))+';\n')
    summary=[f"# CEC {len(boards)}-board inspection — {manifest['inspection_date']}",'',
        'Exact saved native-closed review snapshot; NOT fabrication or electrical approval.','',
        '| Board | Dimensions (mm) | Layers | Components | Nets | Opens | Errors | Warnings |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for b in boards:
        s=b['stats'];c=b['counts'];summary.append(f"| {b['name']} | {b['outline'][2]:.2f} × {b['outline'][3]:.2f} | {len(b['layers'])} | {s['components']} | {s['nets']} | {c['opens']} | {c['errors']} | {c['warnings']} |")
    for b in boards:
        v=b['native_verification'];summary+=['',f"## {b['name']}",'',b['role'],'',
            f"KiCad {v['kicad_version']}; native report date: {v['measured_at']}. {b['field_status']}.",
            'Configured ignored checks: '+(', '.join(c.get('key',str(c))if isinstance(c,dict)else str(c)for c in v['ignored_checks'])or'None recorded')+'.',
            'PCB SHA-256: '+b['sha256']+'.']
    summary+=['','Open index.html in a browser. Two-finger scroll pans; pinch / Ctrl+scroll zooms at the pointer.','',
        'The full report includes actual layer plots, exact component/pin/net metadata, warnings, EPS coupling findings and local review notes.',
        'No CAD source was modified. The bundle contains inspection data and plots, not manufacturing files.','',*manifest['limitations']]
    (out/'analysis.md').write_text('\n'.join(summary)+'\n')
    bundle=out/'inspection-report.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as archive:
        for p in sorted(out.rglob('*')):
            if p.is_file()and p!=bundle and not p.name.endswith('.partial'):
                archive.write(p,str(p.relative_to(out)))
    verify_receipt(manifest['source_receipt'],manifest['source_receipt_sha256'])
    print(json.dumps(dict(complete=True,output=str(out),manifest_sha256=sha(manifest_path),
        bundle=str(bundle),bundle_bytes=bundle.stat().st_size)),flush=True)


def refresh(directory,expected):
    """Refresh viewer UI/configuration only; reuse verified native SVG bytes."""
    out=Path(directory).resolve(strict=True);path=out/'manifest.json'
    if sha(path)!=expected:raise ValueError('inspection_manifest_changed')
    manifest=json.loads(path.read_text())
    receipt=verify_receipt(manifest['source_receipt'],manifest['source_receipt_sha256'])
    rows={r['board']:r for r in receipt['boards']}
    if set(rows)!={b['board']for b in manifest['boards']}:raise ValueError('inspection_board_set_changed')
    for name,identity in manifest['assets'].items():
        target=(out/name).resolve(strict=True)
        if not target.is_relative_to(out)or sha(target)!=identity:raise ValueError('inspection_asset_identity_changed')
    for b in manifest['boards']:
        row=rows[b['board']]
        if b['sha256']!=row['sha256']or b['native_report_sha256']!=row['result_sha256']:
            raise ValueError('inspection_board_identity_mismatch')
        b['native_verification']=native_configuration(json.loads(Path(row['result']).read_text()))
    finalize(out,manifest)


def _published(index=INDEX):
    global _CACHE
    index=Path(index);record=json.loads(index.read_text());base=Path(record['directory']).resolve(strict=True)
    manifest_path=base/'manifest.json';key=(str(base),record['manifest_sha256'],manifest_path.stat().st_mtime_ns)
    if _CACHE and _CACHE[0]==key:return _CACHE[1:]
    if sha(manifest_path)!=record['manifest_sha256']:raise ValueError('inspection_manifest_changed')
    manifest=json.loads(manifest_path.read_text());_CACHE=(key,base,manifest)
    return base,manifest


def response(path, *, index=INDEX):
    """Return one whitelisted review resource. Never traverse arbitrary paths."""
    if path.startswith('/inspection-static/'):
        name=path.rsplit('/',1)[-1]
        if name not in('cec_viewport.js',):return None
        return (STATIC/name).read_bytes(),'application/javascript; charset=utf-8'
    base,manifest=_published(index)
    relative=unquote(path.removeprefix('/inspection/'))or'index.html'
    if relative=='report-data.js':
        return ('window.CEC_INSPECTION_MANIFEST='+json.dumps(manifest,ensure_ascii=True,separators=(',',':'))+';\n').encode(),'application/javascript; charset=utf-8'
    allowed=set(manifest['assets'])|{'index.html','report-data.js','manifest.json','analysis.md','inspection-report.zip'}
    if relative not in allowed:return None
    target=(base/relative).resolve(strict=True)
    if not target.is_relative_to(base):return None
    expected=manifest['assets'].get(relative)
    if expected and sha(target)!=expected:raise ValueError('inspection_asset_identity_changed')
    suffix=target.suffix
    content={'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8',
        '.css':'text/css; charset=utf-8','.json':'application/json','.svg':'image/svg+xml',
        '.zip':'application/zip','.md':'text/plain; charset=utf-8'}.get(suffix,'application/octet-stream')
    return target.read_bytes(),content


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--metadata-worker':_metadata(sys.argv[2],sys.argv[3])
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--receipt');parser.add_argument('--receipt-sha256')
        parser.add_argument('--output');parser.add_argument('--field-receipt');parser.add_argument('--field-sha256')
        parser.add_argument('--refresh');parser.add_argument('--manifest-sha256')
        args=parser.parse_args()
        if args.refresh:
            if not args.manifest_sha256:parser.error('--refresh requires --manifest-sha256')
            refresh(args.refresh,args.manifest_sha256)
        else:
            if not all((args.receipt,args.receipt_sha256,args.output)):parser.error('--receipt, --receipt-sha256 and --output are required')
            build(args)
