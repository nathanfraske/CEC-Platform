"""Project detached Source series-current passives; never route or admit them.

Fresh hierarchical two-pin ferrite/inductor intent and existing aggregate
source/sink contracts are required on BOTH nets. Detachment is actual native
contact exclusion, not same-net naming or an unrouted count. The caller still
owes placement/courtyard/field and original-parent saved receiving.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_detached_ordinary_passive_translation as detached
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_precision_route as precision
import cec_source_ground_leaf as leaf
import cec_source_literal_additions as lex
import cec_source_retaining_ses_import as literal
from cec_footprint_fields import footprint_properties


SCOPE='source_detached_two_pin_aggregate_current_passive_pose-v1'
# Placement work budget, not copper/current/clearance authority. The default
# stays local; an explicit larger cohort must still pass identical Source,
# native-body, full-current restoration and original-parent saved gates.
MAX_EXPLICIT_SHIFT_MM=32.


def _need(value, reason):
    if not value:raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10.,
        'bounded_detached_current_passive_lease_required')
    return time.monotonic()+seconds


def _tick(deadline):
    _need(time.monotonic()<deadline,'detached_current_passive_deadline')


def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def _fingerprint(fp):
    # Native writer includes ALL fields, pads, graphics, models and overrides;
    # do not approximate identity with value/MPN or a subset of pad geometry.
    writer=pcbnew.PCB_IO_KICAD_SEXPR();writer.Format(fp)
    return hashlib.sha256(writer.GetStringOutput(True).encode()).hexdigest()


def _poses(poses,max_shift_mm):
    _need(type(max_shift_mm)in(int,float)and math.isfinite(max_shift_mm)and 0<max_shift_mm<=MAX_EXPLICIT_SHIFT_MM
        and type(poses)in(list,tuple)and 1<=len(poses)<=4,
        'bounded_explicit_detached_current_passive_poses_required')
    result=[]
    for spec in poses:
        _need(type(spec)is dict and set(spec)=={'footprint_uuid','target_pose'}
            and type(spec['footprint_uuid'])is str and spec['footprint_uuid']
            and type(spec['target_pose'])in(list,tuple)and len(spec['target_pose'])==3
            and all(type(x)in(int,float)and math.isfinite(x)for x in spec['target_pose']),
            'exact_detached_current_passive_pose_record_required')
        at=spec['target_pose']
        result.append(dict(footprint_uuid=spec['footprint_uuid'],
            target_pose=[round(at[0]*1e6)/1e6,round(at[1]*1e6)/1e6,at[2]%360]))
    _need(len({p['footprint_uuid']for p in result})==len(result),
        'distinct_detached_current_passive_owners_required')
    return sorted(result,key=lambda p:p['footprint_uuid'])


def _owner(board,uid,literal_grouped):
    owners=[f for f in board.GetFootprints()if force._uid(f)==uid]
    _need(len(owners)==1,'unique_detached_current_passive_owner_required')
    fp=owners[0];pads=list(fp.Pads());face=int(fp.GetLayer())
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    children=[*pads,*fp.GraphicalItems(),*fp.GetFields()]
    _need(not fp.IsLocked()and not fp.IsDNP()and not fp.GetParentGroup()and not list(fp.Groups())
        and face in(pcbnew.F_Cu,pcbnew.B_Cu)and len(pads)==2
        and len({p.GetNumber()for p in pads})==2
        and len({p.GetNetname()for p in pads})==2 and not list(fp.Zones())
        and not({uid,*[force._uid(p)for p in children]}&(grouped|literal_grouped))
        and all(not p.IsLocked()and not p.GetParentGroup()and not p.HasHole()
            and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
            and tuple(map(int,p.GetLayerSet().CuStack()))==(face,)
            and p.GetNetCode()>0 and p.GetPinType()in('','passive')for p in pads),
        'unlocked_ungrouped_detached_two_surface_passive_required')
    _need(all(int(g.GetLayer())not in {*map(int,board.GetEnabledLayers().CuStack()),int(pcbnew.Edge_Cuts)}
        for g in [*fp.GraphicalItems(),*fp.GetFields()]),
        'detached_current_passive_cannot_carry_copper_or_edges')
    _need(not pads[0].GetEffectiveShape(face).Collide(pads[1].GetEffectiveShape(face),0),
        'detached_current_passive_source_lands_overlap')
    return fp


def _isolated(board,fp,deadline):
    detached._detached(board,fp,deadline)
    # The shared conservative guard owns tracks/pads/fill. Native copper
    # artwork is also live material, even though it has no net affiliation.
    artwork=[*board.GetDrawings(),*[g for other in board.GetFootprints()
        for g in [*other.GraphicalItems(),*other.GetFields()]]]
    for pad in fp.Pads():
        face=int(next(iter(pad.GetLayerSet().CuStack())))
        for item in artwork:
            _tick(deadline)
            if int(item.GetLayer())==face:
                _need(not item.GetEffectiveShape().Collide(pad.GetEffectiveShape(face),0),
                    'source_passive_land_has_existing_native_artwork_contact')


def _canonical(board,fp,comps,nets,node_net,instances,deadline):
    identity=leaf._identity(board,fp.GetReference(),comps,instances,deadline)
    _,path,sf,symbol=identity;component=comps[fp.GetReference()]
    kind=leaf.synth._val(leaf.synth._first(component,'libsource'),'part','')
    _need(kind in('Ferrite_Bead','FerriteBead','FerriteBead_Small','L','L_Small'),
        'canonical_two_pin_ferrite_or_inductor_symbol_required')
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    _need(len(libraries)==1,'complete_detached_current_passive_symbol_required')
    tree=leaf.synth.parse_sexpr(libraries[0])
    selected=[s for s in leaf.synth._kids(tree,'symbol')if len(s)>1 and s[1]==symbol['lib_id']]
    _need(len(selected)==1 and leaf.synth._first(selected[0],'extends')is None,
        'complete_detached_current_passive_symbol_required')
    todo=[selected[0]];pins=[];visited=0
    while todo:
        _tick(deadline);node=todo.pop();visited+=1
        _need(visited<=4096,'bounded_detached_current_passive_symbol_required')
        if isinstance(node,list)and node:
            if node[0]=='pin':pins.append(node)
            todo.extend(n for n in node if isinstance(n,list))
    _need(len(pins)==2 and {leaf.synth._val(p,'number','')for p in pins}==
        {p.GetNumber()for p in fp.Pads()}and all(p[1]=='passive'for p in pins),
        'complete_two_passive_source_pins_required')
    blocks=[b for tag,b in sf.children if tag=='symbol'and leaf.sch.prop_value(b,'Reference')==fp.GetReference()]
    fields=footprint_properties(fp)
    exported={leaf.synth._val(p,'name',''):leaf.synth._val(p,'value','')
        for p in leaf.synth._kids(component,'property')}
    _need(len(blocks)==1,'unique_detached_current_passive_source_instance_required')
    for name in('MPN','Manufacturer','LCSC'):
        _need(bool(fields.get(name))and leaf.sch.prop_value(blocks[0],name)==fields[name]
            and exported.get(name)==fields[name],
            'detached_current_passive_selected_source_field_mismatch:'+name)
    records=[]
    for pad in sorted(fp.Pads(),key=lambda p:p.GetNumber()):
        _tick(deadline);pin=pad.GetNumber();net=str(pad.GetNetname())
        _need(leaf._pin(identity,pin)['type']=='passive'
            and node_net.get((fp.GetReference(),pin))==net,
            'detached_current_passive_source_pin_net_mismatch')
        peers={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()for p in f.Pads()
            if p.GetNetname()==net}
        _need(peers==nets.get(net,set()),'detached_current_passive_complete_net_membership_mismatch')
        records.append(dict(pad_uuid=force._uid(pad),pin=pin,net=net,
            source_type='passive',source_function=leaf._pin(identity,pin).get('name')))
    return dict(sheet=str(path),symbol_uuid=symbol['uuid'],lib_id=symbol['lib_id'],
        symbol_kind=kind,value=fp.GetValue(),footprint_id=fp.GetFPIDAsString(),
        selected_fields={k:fields[k]for k in('MPN','Manufacturer','LCSC')},pins=records)


def plan(source,poses,*,board_hint,max_shift_mm=6.,timeout_s=10.):
    """Fresh Source/current/isolation proof; no placement or route permission."""
    deadline=_deadline(timeout_s);specs=_poses(poses,max_shift_mm)
    _need(type(board_hint)is str and bool(board_hint),'named_detached_current_passive_source_required')
    source=Path(source).resolve(strict=True)
    _need(source.suffix=='.kicad_pcb','saved_detached_current_passive_source_required')
    code=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));binding=row._source_binding(board)
    inventory,*_=lex._inventory(literal.raw_text(source))
    grouped={u for _,_,node in inventory.values()if literal.kind(node)=='group'for u in lex._members(node)[1]}
    root=leaf.source_nc._root(board,board_hint)
    _need(root is not None,'canonical_detached_current_passive_root_required');root=root.resolve()
    files,hashes,instances=leaf._hierarchy(root,deadline)
    tree,exporter=leaf._export(root,deadline);comps,nets,node_net=leaf._tables(tree)
    pair_nets={p[k]for p in precision.derive_coupled_pairs(str(source),board=board)for k in('p','n')}
    records=[]
    for spec in specs:
        _tick(deadline);fp=_owner(board,spec['footprint_uuid'],grouped)
        original=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
        target=spec['target_pose'];turn=(target[2]-original[2])%360
        _need(turn in(0,90,180,270)and math.dist(original[:2],target[:2])<=max_shift_mm
            and (original[:2]!=target[:2]or turn!=0),
            'bounded_nonzero_cardinal_detached_current_passive_pose_required')
        canonical=_canonical(board,fp,comps,nets,node_net,instances,deadline)
        _isolated(board,fp,deadline)
        domains=[]
        for pin in canonical['pins']:
            net=pin['net'];_need(net!='GND'and net not in pair_nets,
                'detached_current_passive_cannot_reclassify_ground_or_pair')
            kind,domain,contract=full._model(board,source,net,board_hint)
            _need(kind=='aggregate_source_sink'and domain is not None and domain.get('complete')is True
                and domain.get('source_refs')and domain.get('sink_refs')
                and ((fp.GetReference()in domain['source_refs']) !=
                    (fp.GetReference()in domain['sink_refs'])),
                'detached_current_passive_must_be_actual_aggregate_source_or_sink')
            domains.append(dict(pin=pin['pin'],net=net,kind=kind,domain=domain,contract=contract,
                source_or_sink='source'if fp.GetReference()in domain['source_refs']else'sink'))
        records.append(dict(footprint_uuid=spec['footprint_uuid'],ref=fp.GetReference(),
            source_pose=original,target_pose=target,face=int(fp.GetLayer()),
            source_footprint_sha256=_fingerprint(fp),canonical_source=canonical,current_domains=domains,
            actual_native_source_isolated=True))
    export_identity=dict(exporter);export_identity.pop('netlist_sha256')
    result=_stable(dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),
        source_family=family,source_native_binding=binding,code_identity=code,board_hint=board_hint,
        request=dict(poses=specs,max_shift_mm=max_shift_mm),records=records,
        canonical_source=dict(root=str(root),files_sha256=hashes,exporter=export_identity),
        projection_only=True,placement_admitted=False,routing_admitted=False,
        current_qualified=False,release_authority=False,retired_copper_uuids=[],
        independent_original_parent_saved_receiving_required=True))
    _need(row._source_binding(board)==binding and code==force._code_identity()
        and family==force._family(source,board_hint)
        and result['source_sha256']==family.get(str(source))
        and hashes=={str(p):force._hash(p)for p in files},
        'detached_current_passive_source_or_code_changed')
    _tick(deadline)
    return result


def apply(board,q):
    """Revalidate the fresh plan, then move only whole exact Source footprints.

    Other caller-owned private projection changes may already exist. They are
    not authorized here; each selected passive must still be literally Source
    identical and detached before any mutation. No file is saved.
    """
    deadline=_deadline(10.)
    _need(type(q)is dict and q.get('scope')==SCOPE,'typed_detached_current_passive_plan_required')
    fresh=plan(q['source'],q['request']['poses'],board_hint=q['board_hint'],
        max_shift_mm=q['request']['max_shift_mm'],timeout_s=max(.001,deadline-time.monotonic()))
    _need(_stable(q)==fresh,'stale_or_forged_detached_current_passive_plan')
    prepared=[]
    for record in fresh['records']:
        fp=_owner(board,record['footprint_uuid'],set())
        _need(_fingerprint(fp)==record['source_footprint_sha256'],
            'detached_current_passive_caller_owner_changed')
        _isolated(board,fp,deadline);prepared.append((fp,record))
    _tick(deadline)
    for fp,record in prepared:
        pose=record['target_pose']
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])))
        fp.SetOrientationDegrees(pose[2])
    _tick(deadline)
    return [record['footprint_uuid']for _,record in prepared]
