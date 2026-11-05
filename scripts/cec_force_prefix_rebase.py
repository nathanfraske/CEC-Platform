"""Literal force-first construction and conservative ordinary-delta recovery.

Donor bytes are construction material, not a certificate. Force ownership is
recompiled from source current domains, real physical terminals and filled
native copper. Whole-current/thermal/Kelvin qualification remains unknown.
Saved full DRC/current/intake/field/isolation receiving is still mandatory.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_force_current as force
import cec_source_retaining_ses_import as raw
import cec_current_topology as topology
import cec_ordinary_route_receiving as ordinary
import cec_fab_profile as fab
import cec_fr as fr
import cec_kelvin_copper_cut as cut
import cec_copper_echo as sexpr


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_force_rebase_required')
    return time.monotonic()+seconds


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('force_rebase_deadline')


def _nodes(path):
    text=raw.raw_text(path)
    return text,{u:text[a:z] for u,(a,z) in raw.inventory(text).items()}


def _fixed(text):
    return sexpr._freeze(sexpr._parse(sexpr._TOKEN.findall(text)))


def _root_metadata(text):
    root=sexpr._parse(sexpr._TOKEN.findall(text))
    # Top-level UUID-owned copper/population is checked separately. Every
    # other root field participates, including native net codes and unknown
    # metadata. A net-name comparison cannot authorize a different code map.
    return sexpr._freeze([root[0],*[node for node in root[1:]if not isinstance(node,list)
        or not any(isinstance(child,list)and child and child[0]=='uuid'for child in node[1:])]])


def _originals(base,donor,*,literal):
    a,old=_nodes(base);b,new=_nodes(donor)
    for uid,node in old.items():
        if uid not in new:raise ValueError('original_node_missing:'+uid)
        if (node!=new[uid]) if literal else (_fixed(node)!=_fixed(new[uid])):
            raise ValueError('original_node_changed:'+uid)
    # Opaque root fields are not new copper permission.
    # root fields are checked independently by the native preservation tuple;
    # Unknown syntax is not normalized away to grant mutation permission.
    if force._preservation_snapshot(base)[1]!=force._preservation_snapshot(donor)[1]:
        raise ValueError('root_or_settings_changed')
    return a,old,b,new


def _native_live(board):
    return {force._uid(i):i for i in [*board.GetTracks(),*board.Zones()]}


def _terminals_same(a,b):
    from cec_route_placement_admission import _population
    if _population(a)!=_population(b):raise ValueError('source_population_or_pad_nets_changed')
    def identities(board):
        return sorted((force._uid(f),f.GetReference(),f.GetFPIDAsString(),f.GetValue(),
            tuple(f.GetPosition()),f.GetOrientationDegrees(),f.IsFlipped(),f.IsDNP(),
            tuple(sorted((x.GetName(),x.GetText())for x in f.GetFields())))for f in board.GetFootprints())
    if identities(a)!=identities(b):raise ValueError('source_component_identity_or_pose_changed')


def _literal_solderland_containment(pad,zones,layer,deadline):
    """Exact native OUTSIDE polygon minus literal saved fill, zero tolerance.

    This is only an alternative to conservative envelope buffers at an
    identical native boundary. No positive residual, buffer, area threshold,
    centre sample or historical receipt can grant a positive result.
    """
    _tick(deadline)
    if pad.HasHole()or not pad.IsOnLayer(layer):return False
    native=pad.GetEffectivePolygon(layer,pcbnew.ERROR_OUTSIDE).CloneDropTriangulation()
    if native.OutlineCount()!=1 or native.HoleCount(0) or native.Outline(0).ArcCount():return False
    original=native.Format();fills=[];union=pcbnew.SHAPE_POLY_SET()
    for zone in zones:
        _tick(deadline)
        if not zone.IsOnLayer(layer)or not zone.IsFilled()or not zone.HasFilledPolysForLayer(layer):continue
        poly=zone.GetFilledPolysList(layer)
        fills.append((zone,poly.Format()));union.BooleanAdd(poly)
    if not fills:return False
    native.BooleanSubtract(union)
    _tick(deadline)
    return (not native.OutlineCount() and original==pad.GetEffectivePolygon(layer,pcbnew.ERROR_OUTSIDE).Format()
        and all(snapshot==z.GetFilledPolysList(layer).Format()for z,snapshot in fills))


def _force_geometry(base,donor,added,domains,deadline):
    """Native contact/conservation evidence; not a global minimum-cut proof."""
    live=_native_live(donor);nets={str(live[u].GetNetname())for u in added}
    if not nets or not nets<=domains.keys():raise ValueError('new_force_material_without_source_domain')
    graph=fr._read_only_route_connectivity(donor);proofs={}
    for net in sorted(nets):
        _tick(deadline);domain=domains[net]
        if domain.get('complete') is not True:raise ValueError('incomplete_source_current_domain')
        authority=domain.get('current_contract')or{}
        amps=authority.get('amps');margin=authority.get('geometry_margin')
        if (type(amps)not in(int,float)or type(margin)not in(int,float)
                or not math.isfinite(amps*margin)or amps<=0 or margin<=0):
            raise ValueError('positive_unchanged_source_current_required')
        target=amps*margin
        # Existing platform count policy, never a guessed branch allocation.
        import cec_slab_pour as slab
        needed=math.ceil(target/slab.VIA_AMPS)+1
        if needed>slab.FIELD_VIA_CAP or slab.VIA_AMPS!=2.:
            raise ValueError('force_field_exceeds_existing_barrel_policy')
        items=[live[u]for u in added if live[u].GetNetname()==net]
        if any(i.GetClass()not in('ZONE','PCB_VIA')for i in items):
            raise ValueError('initial_force_prefix_scope_is_zones_and_fields_only')
        zones=[i for i in items if i.GetClass()=='ZONE'];vias=[i for i in items if i.GetClass()=='PCB_VIA']
        if len(vias)!=needed or not 1<=len(zones)<=8:raise ValueError('exact_source_policy_force_field_count_required')
        layers=tuple(donor.GetEnabledLayers().CuStack());work=cut._Work(deadline)
        from shapely.ops import unary_union
        zone_polys={}
        for l in (pcbnew.F_Cu,pcbnew.B_Cu):
            polys=[cut._poly(z.GetFilledPolysList(l),work)for z in zones
                if not z.GetIsRuleArea()and z.IsFilled()and z.IsOnLayer(l)and z.HasFilledPolysForLayer(l)]
            if not polys:raise ValueError('saved_outer_force_collector_required')
            zone_polys[l]=unary_union(polys)
        contacts=[]
        for via in vias:
            _tick(deadline);cut._simple_drill(via,layers)
            if via.GetDrillValue()!=500000 or any(via.GetWidth(l)<900000 for l in layers):
                raise ValueError('exact_ordinary_force_field_geometry_required')
            for l in zone_polys:
                # Lower copper must contain the full upper annulus. No bore
                # or centre-only contact is credited as metal.
                annulus=cut._shape(via,l,True,work).difference(cut._hole(via,False,work))
                if not zone_polys[l].covers(annulus):raise ValueError('force_field_full_annular_contact_missing')
            contacts.append(force._uid(via))
        pads=force._authority_pads(donor,net,domain)
        if not pads:raise ValueError('source_physical_force_terminals_missing')
        reached={force._item_key(i)for i in graph.GetConnectedItems(pads[0])}|{force._item_key(pads[0])}
        if any(force._item_key(p)not in reached for p in pads):raise ValueError('force_physical_terminal_partition_incomplete')
        smd=[]
        for pad in pads:
            if pad.HasHole():continue
            available=[l for l in zone_polys if pad.IsOnLayer(l)]
            if not available or not any(zone_polys[l].covers(cut._shape(pad,l,True,work))
                    or _literal_solderland_containment(pad,zones,l,deadline)for l in available):
                raise ValueError('actual_shunt_solderland_not_fully_covered')
            smd.append(force._uid(pad))
        proofs[net]=dict(current_authority=authority,required_amps=target,barrels=len(vias),
            physical_authority_pad_uuids=sorted(force._uid(p)for p in pads),
            full_outer_annular_contact_uuids=sorted(contacts),full_smd_solderland_uuids=sorted(smd),
            whole_min_cut_qualified=False,current_qualified=False,thermal_qualified=False,release_authority=False)
    return proofs


def _graft(base_text,nodes):
    end=raw.children(base_text,root_end=True)
    return base_text[:end]+'\n'+'\n'.join(nodes)+'\n'+base_text[end:]


def plan(base,force_donor,ordinary_donor,*,board_hint,expected_sha256,timeout_s=10.,max_components=128):
    """Read-only, source/hash-bound literal packet selection; never admission."""
    deadline=_deadline(timeout_s)
    if (type(board_hint)is not str or not board_hint or type(max_components)is not int
            or not 1<=max_components<=128 or type(expected_sha256)is not dict
            or set(expected_sha256)!={'base','force','ordinary'}):
        raise ValueError('exact_force_rebase_context_required')
    paths={k:Path(v).resolve()for k,v in [('base',base),('force',force_donor),('ordinary',ordinary_donor)]}
    hashes={k:force._hash(p)for k,p in paths.items()}
    if hashes!=expected_sha256:raise ValueError('force_rebase_source_epoch_mismatch')
    report=dict(schema=1,scope='source_bound_force_first_literal_rebase',complete=False,
        board_hint=board_hint,paths={k:str(v)for k,v in paths.items()},sha256=hashes,
        force_ids=[],ordinary_ids=[],groups=[],refused=[],errors=[],current_qualified=False,
        whole_min_cut_qualified=False,thermal_qualified=False,release_authority=False)
    try:
        bt,bn,ft,fn=_originals(paths['base'],paths['force'],literal=True)
        # Ordinary donor can have serializer-only source text changes, never
        # changed original copper/root/population. Native originals checked.
        ot,on=_nodes(paths['ordinary'])
        if not _root_metadata(bt)==_root_metadata(ft)==_root_metadata(ot):
            raise ValueError('exact_native_root_and_netcode_authority_required')
        boards={k:pcbnew.LoadBoard(str(v))for k,v in paths.items()};a=boards['base'];f=boards['force'];o=boards['ordinary']
        for b in(f,o):_terminals_same(a,b)
        ai=__import__('cec_field_coupling')._field_snapshot_inventory(a)
        oi=__import__('cec_field_coupling')._field_snapshot_inventory(o)
        if any(oi.get(k)!=v for k,v in ai.items()):raise ValueError('ordinary_donor_original_native_copper_changed')
        for k in('force','ordinary'):
            for suffix in(('.kicad_pro','.kicad_dru')if k=='force'else('.kicad_pro',)):
                x,y=paths['base'].with_suffix(suffix),paths[k].with_suffix(suffix)
                if x.exists()!=y.exists()or x.exists()and force._hash(x)!=force._hash(y):raise ValueError('project_authority_changed')
        domains=topology.board_current_domains(a,board_hint)
        force_ids=sorted(set(fn)-set(bn))
        if not force_ids or any(raw.kind(fn[u])not in('zone','via')for u in force_ids):raise ValueError('finite_force_prefix_nodes_required')
        report['force_geometry']=_force_geometry(a,f,force_ids,domains,deadline);report['force_ids']=force_ids
        eligible=ordinary.eligible_nets(o,paths['ordinary'],board_hint)
        live=_native_live(o);incoming={u:i for u,i in live.items()if u not in bn and i.GetClass()in('PCB_TRACK','PCB_VIA')}
        conn=pcbnew.CONNECTIVITY_DATA()
        for i in incoming.values():
            if not conn.Add(i):raise ValueError('ordinary_component_native_inventory_refused')
        remaining=dict(incoming);components=[]
        while remaining:
            _tick(deadline);uid=min(remaining);item=remaining[uid]
            group={force._uid(i)for i in conn.GetConnectedItems(item)}|{uid}
            group&=remaining.keys();components.append(sorted(group))
            for u in group:remaining.pop(u)
            if len(components)>max_components:raise ValueError('ordinary_component_inventory_bound')
        report['component_count']=len(components)
        protected={u for group in o.Groups()for u in(force._uid(i)for i in group.GetItems())}
        for ids in components:
            _tick(deadline);items=[incoming[u]for u in ids];nets={str(i.GetNetname())for i in items}
            reason=None
            if len(nets)!=1 or not nets<=eligible:reason='not_positive_ordinary_signal_scope'
            elif set(ids)&protected:reason='grouped_copper_requires_separate_requalification'
            else:
                net=next(iter(nets));spec=fr._project_netclass_resolver(str(paths['ordinary']))(net)
                gap=max(200000,int(a.GetDesignSettings().m_MinClearance),round(spec['clearance']*1e6))
                for i in items:
                    _tick(deadline)
                    if i.GetClass()=='PCB_TRACK':
                        l=int(i.GetLayer());w=int(i.GetWidth());s,z=i.GetStart(),i.GetEnd()
                        if (w<max(int(a.GetDesignSettings().m_TrackMinWidth),round(spec['track_width']*1e6))
                                or not fr._edge_leg_clear(f,s,z,w/2+gap)
                                or not fr._tap_foreign_clear(f,s,z,w,l,gap,{f.GetNetcodeFromNetname(net)},foreign_cache={})):
                            reason='native_foreign_outline_or_width';break
                    else:
                        dia=int(i.GetWidth(i.TopLayer()));drill=int(i.GetDrillValue())
                        required=fab.board_legal_through_via_geometry(f,spec['via_diameter'],spec['via_drill'])
                        if (drill<round(required[1]*1e6)or dia<round(required[0]*1e6)
                                or not fr._via_spot_clear(f,i.GetPosition(),dia,gap,{f.GetNetcodeFromNetname(net)},drill_nm=drill,net_code=f.GetNetcodeFromNetname(net))):
                            reason='native_column_process_or_foreign';break
            if reason:report['refused'].append(dict(uuids=ids,nets=sorted(nets),reason=reason))
            else:report['ordinary_ids'].extend(ids)
        report['ordinary_ids'].sort();report['complete']=True
        if hashes!={k:force._hash(p)for k,p in paths.items()}:raise ValueError('force_rebase_inputs_changed')
    except (ValueError,RuntimeError,KeyError,TypeError,AttributeError)as exc:report['errors'].append(type(exc).__name__+':'+str(exc));report['complete']=False
    return report


def construct_private(proposal,out):
    """Build literal source plus selected NEW nodes; no source refill or edits."""
    if proposal.get('scope')!='source_bound_force_first_literal_rebase'or proposal.get('complete')is not True:
        raise ValueError('complete_force_rebase_proposal_required')
    paths={k:Path(p)for k,p in proposal['paths'].items()}
    if {k:force._hash(p)for k,p in paths.items()}!=proposal['sha256']:raise ValueError('force_rebase_epoch_changed')
    bt,bn=_nodes(paths['base']);_,fn=_nodes(paths['force']);_,on=_nodes(paths['ordinary'])
    ids=proposal['force_ids']+proposal['ordinary_ids']
    if len(ids)!=len(set(ids))or set(ids)&bn.keys():raise ValueError('new_only_rebase_identity_required')
    target=force._copy_family(paths['base'],Path(out)/'candidate')
    raw.write_raw(target,_graft(bt,[fn[u]for u in proposal['force_ids']]+[on[u]for u in proposal['ordinary_ids']]))
    return target


def receive(base,force_donor,ordinary_donor,candidate,*,board_hint,expected_sha256,timeout_s=10.,max_components=128):
    """Independent deterministic literal replay, NOT full board admission."""
    proof=plan(base,force_donor,ordinary_donor,board_hint=board_hint,expected_sha256=expected_sha256,timeout_s=timeout_s,max_components=max_components)
    result=dict(ok=False,complete=False,proof=proof,current_qualified=False,whole_min_cut_qualified=False,
        thermal_qualified=False,release_authority=False,full_saved_current_native_intake_field_isolation_required=True)
    if not proof['complete']:return result
    with tempfile.TemporaryDirectory(prefix='cec-force-prefix-replay-')as work:
        expected=construct_private(proof,work)
        result['exact_literal_expected_replay']=raw.raw_text(expected)==raw.raw_text(candidate)
        result['ok']=result['complete']=result['exact_literal_expected_replay']
    return result
