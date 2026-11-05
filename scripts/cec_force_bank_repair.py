"""Exact additive source-bank repair, distinct from monitor-input routing.

Derive the repair from two saved boards and fresh typed cut packets. There
is no caller success flag, edited BEFORE evidence, current-sharing credit,
board/refdes exception, or unknown-to-pass shortcut. Native connectivity is
not a conductor/barrel/terminal thermal rating and does not release a board.
"""
from pathlib import Path
import math
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_current_debt as current
import cec_current_topology as topology
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_native_supply_via_context as web
import cec_route_dimensions as dimensions
import cec_route_quality as craft


def _positive(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('positive_unchanged_force_bank_dimension_required')
    return value


def _contract(board,path,net,hint):
    with force._thermal_hint(hint):
        domain=topology.board_current_domains(board,hint).get(net)
        raw=topology.route_width_contracts(board,hint).get(net)
    if (not domain or domain.get('complete') is not True or domain.get('missing_refs')
            or not domain.get('source_refs') or not domain.get('sink_refs') or not raw):
        raise ValueError('complete_existing_source_bank_authority_required')
    _positive(domain.get('amps'))
    authority=raw.get('current_authority') or {}
    _positive(authority.get('amps'));_positive(authority.get('geometry_margin'))
    if (type(authority.get('margin_included')) is not bool
            or authority['margin_included'] and authority['geometry_margin']!=1
            or authority['amps']!=domain['amps']):
        raise ValueError('exact_unchanged_source_bank_current_basis_required')
    enabled={fab.COPPER_LAYER_IDS[int(l)] for l in board.GetEnabledLayers().CuStack()}
    widths=raw.get('required_by_layer_mm') or {}
    authorized=set(raw.get('routing_layers') or ())
    planes={fab.COPPER_LAYER_IDS[board.GetLayerID(n)] for n in fr.plane_layers(board)}
    if set(widths)!=enabled or not authorized or not authorized<=enabled or authorized & planes:
        raise ValueError('complete_nonplane_source_bank_width_contract_required')
    spec=fr._project_netclass_resolver(str(path))(net) or {}
    minimum=max(_positive(spec.get('track_width')),_positive(dimensions.board_limits(board)['track_width']))
    floors={n:max(_positive(w),minimum) for n,w in widths.items()}
    return domain,dict(raw,required_by_layer_mm=floors,branch_sharing_assumed=False,
        terminal_barrel_zone_rating_qualified=False)


def _native_bank(board,net,domain,rows,deadline):
    """Actual native source-terminal to cut-shunt terminal pairs, with fills."""
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if str(p.GetNetname())==net]
    tracks=[t for t in board.GetTracks() if str(t.GetNetname())==net]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and str(z.GetNetname())==net]
    graph,_=sense._native_graph(pads,tracks,zones,deadline)
    inventory={force._uid(p):p for p in pads}
    sources={force._uid(p):p for p in pads if p.GetParentFootprint().GetReference() in domain['source_refs']}
    sinks={force._uid(p):p for p in pads if p.GetParentFootprint().GetReference() in domain['sink_refs']}
    if not sources or not sinks or len(sources)*len(sinks)>128:
        raise ValueError('bounded_actual_force_bank_terminal_pairs_required')
    for row in rows:
        sink=row['source_pad']
        if sink['uuid'] not in sinks or sense._pad_identity(sinks[sink['uuid']])!=sink:
            raise ValueError('force_bank_cut_source_not_actual_declared_shunt')
        native=row['native'];authority=native['authority']
        if {p['uuid'] for p in authority}!=set(sources) or len(authority)!=len(sources):
            raise ValueError('force_bank_cut_authority_not_exact_native_source_population')
        for identity in [native['source'],native['sense'],*authority]:
            actual=inventory.get(identity['uuid'])
            if (actual is None or identity.get('kind')!='PAD'
                    or {k:v for k,v in identity.items() if k!='kind'}!=sense._pad_identity(actual)):
                raise ValueError('force_bank_cut_terminal_identity_changed')
    pairs={}
    for uid,pad in sorted(sources.items()):
        reached=sense._reached(graph,pad,deadline)
        for sink,terminal in sorted(sinks.items()):
            pairs[(uid,sink)]=sense._key(terminal) in reached
    return pairs


def receive(source,candidate,*,board_hint,timeout_s=20.):
    """Fresh saved-board-only authority repair; no caller repair-net allowlist.

    The selected nets and native count manifest are inferred from additions.
    Existing debt stays explicit; unchanged contacts remain strict. Every old
    unknown affected cut must specifically be a disconnected native baseline,
    and every AFTER cut must be absolutely positive with identical authority.
    """
    result=dict(schema=1,scope='native_additive_whole_source_bank_repair',ok=False,
        complete=False,errors=[],source_current_reduced=False,branch_sharing_assumed=False,
        plated_barrel_current_qualified=False,full_kelvin_qualification=False,
        inherited_debt_qualified=False,release_authority=False,fab_ready=False)
    try:
        if (type(board_hint) is not str or not board_hint or type(timeout_s) not in (int,float)
                or not math.isfinite(timeout_s) or not 0<timeout_s<=60):
            raise ValueError('bounded_explicit_force_bank_receiving_context_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        boards=[pcbnew.LoadBoard(str(p)) for p in paths]
        inventories=[{force._uid(t):t for t in b.GetTracks()} for b in boards]
        old,new=inventories
        if (old.keys()-new.keys() or any(len(i)!=len(list(b.GetTracks()))
                or len(i)>16384 for i,b in zip(inventories,boards))):
            raise ValueError('source_bank_must_be_exact_additive_conductor_transaction')
        incoming=set(new)-set(old);added=[new[u] for u in sorted(incoming)]
        nets=sorted({str(t.GetNetname()) for t in added})
        if (not 1<=len(added)<=128 or not 1<=len(nets)<=4
                or sum(t.GetClass()=='PCB_VIA' for t in added)>4
                or any(t.GetClass() not in ('PCB_TRACK','PCB_VIA') or not t.GetNetCode() or not t.IsLocked() for t in added)):
            raise ValueError('bounded_locked_native_force_bank_additions_required')
        received=additive.receive(*paths,board_hint=board_hint,timeout_s=10.)
        result['exact_additive_receiving']=received
        if not received['ok'] or not received['complete']:
            raise ValueError('exact_native_source_bank_delta_and_ground_refill_required')
        contracts={};domains={};webs=[]
        for net in nets:
            first,contract=_contract(boards[0],paths[0],net,board_hint)
            last,new_contract=_contract(boards[1],paths[1],net,board_hint)
            if first!=last or contract!=new_contract:
                raise ValueError('source_bank_current_authority_or_width_changed')
            domains[net]=first;contracts[net]=contract
            for item in added:
                if str(item.GetNetname())!=net:continue
                if item.GetClass()=='PCB_TRACK':
                    face=fab.COPPER_LAYER_IDS[int(item.GetLayer())]
                    if (face not in contract['routing_layers']
                            or item.GetWidth()<math.ceil(contract['required_by_layer_mm'][face]*1e6)):
                        raise ValueError('whole_source_bank_track_width_required')
                else:
                    proof=web.receive(boards[1],force._uid(item),contract,timeout_s=2.)
                    if not proof['ok'] or not proof['complete']:
                        raise ValueError('whole_source_bank_actual_contact_web_required')
                    webs.append(proof)
        debt=current.receive(*paths,board_hint=board_hint)
        result['unchanged_current_debt_receiving']=debt
        if not debt['ok'] or not debt['complete']:
            raise ValueError('source_bank_current_debt_changed_or_worsened')
        quality=craft.analyze_board(boards[1],track_uuid_scope=incoming)
        if not quality['craft_ok']:raise ValueError('canonical_force_bank_copper_required')
        with force._thermal_hint(board_hint):
            blockers=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if blockers:raise ValueError('new_native_force_bank_field_blocker')
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=timeout_s) for p in paths]
        result.update(source_sense=before,candidate_sense=after)
        proofs={};manifest=[]
        for net in nets:
            prior=[r for r in before['clipped_isolation']['details'] if r['net']==net]
            actual=[r for r in after['clipped_isolation']['details'] if r['net']==net]
            if (not prior or len(prior)!=len(actual) or any(r.get('ok') is not None
                    or r.get('status')!='unknown' or r['native'].get('ok') is not None
                    or r['native'].get('complete') is not False
                    or r['native'].get('reason')!='baseline_native_terminal_connectivity_incomplete'
                    or r['native'].get('physical_bypass_proved') is not False for r in prior)):
                raise ValueError('exact_disconnected_native_force_bank_baseline_required')
            for category in ('same_net_connectivity','inner_departure'):
                if any(r.get('ok') is not True for r in before[category]['details'] if r['net']==net):
                    raise ValueError('bank_basis_cannot_hide_unconnected_monitor_input_or_bad_departure')
            previous=_native_bank(boards[0],net,domains[net],prior,time.monotonic()+10.)
            connected=_native_bank(boards[1],net,domains[net],actual,time.monotonic()+10.)
            changed=[list(k) for k in sorted(previous) if previous[k] is False and connected.get(k) is True]
            if previous.keys()!=connected.keys() or not changed or not all(connected.values()):
                raise ValueError('all_actual_force_bank_source_to_shunt_pairs_must_close')
            proofs[net]=dict(native_bank_closed=True,newly_connected_pairs=changed,
                actual_pairs_checked=len(connected),all_after_pairs_connected=True,
                before_unknown_reason='baseline_native_terminal_connectivity_incomplete',
                terminal_capacity_qualified=False,release_authority=False)
            selected=[t for t in added if str(t.GetNetname())==net]
            manifest.append(dict(net=net,retired_track_uuids=[],added_track_uuids=sorted(force._uid(t) for t in selected),
                retired_via_uuids=[],added_via_uuids=sorted(force._uid(t) for t in selected if t.GetClass()=='PCB_VIA'),
                added_zone_uuids=[]))
        preservation=sense._compare_repaired_preservation(before,after,repair_nets=nets,
            modified_nets=nets,native_copper_transforms=manifest,_received_force_banks=proofs)
        result['physical_preservation']=preservation
        if not preservation['comparison_complete'] or not preservation['same_evidence']:
            raise ValueError('absolute_bank_cut_and_strict_unaffected_evidence_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('source_bank_saved_family_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),code_identity=epoch,source_candidate_and_code_unchanged=True,
            inferred_repaired_nets=nets,native_count_manifest=manifest,actual_bank_connectivity=proofs,
            unchanged_whole_source_contracts=contracts,new_actual_contact_webs=webs,new_route_craft=quality,
            fresh_native_DRC_stack_and_outline_receiving_still_required=True)
    except (ValueError,TypeError,KeyError,StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
