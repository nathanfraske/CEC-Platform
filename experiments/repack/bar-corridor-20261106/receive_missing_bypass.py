"""Independent private single-cap corrective receiving, never fab admission.

Every stage rereads saved source/candidate geometry. Construction manifests
are claims to compare, not ownership or current authority. Partial failures
are persisted and cannot become a successful receipt.
"""
import argparse
import copy
import json
from pathlib import Path
import signal
import tempfile
import time

from cec_pipeline.native import _native
p, _ = _native()
from cec_pipeline import cells, geometry, pairs
import cec_additive_route_receiving as ast
import cec_complete_cell_receiving as complete
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_decoupler_cell as decoupling
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_preservation as returns
import cec_measurement_leaf as leaf
import cec_missing_bypass_repair as repair
import cec_native_drc_runner as drc
import cec_native_partition_pair as partitions
import cec_protector_cell as placement
import cec_route_quality as craft
from cec_native_items import discard_items


def need(value, reason):
    if not value: raise ValueError(reason)


def signature(node):
    return syntax._freeze([x for x in node if not(isinstance(x,list) and x and x[0]=='uuid')])


def globals_only(root,nodes):
    ids={id(n) for n in nodes.values()}
    return syntax._freeze([n for n in root if id(n) not in ids])


def run(folder, *, footprint_table, reporting_build, cover=None, stack_contract=None):
    folder=Path(folder).resolve(strict=True)
    record=json.loads((folder/'construction.json').read_text())
    role=json.loads((folder/'role.json').read_text())
    claimed_leaf=json.loads((folder/'source-supply-leaf.json').read_text())
    source=Path(record['source']).resolve(strict=True);candidate=Path(record['candidate']).resolve(strict=True)
    hint=record['board_hint'];epoch=force._code_identity()
    identity=dict(source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
                  source_sidecars=force._sidecars(source),candidate_sidecars=force._sidecars(candidate),code_identity=epoch)
    out=dict(schema=1,scope='independent_private_single_missing_bypass_corrective_checks',
             source=str(source),candidate=str(candidate),identity=identity,stages={},errors=[],
             ok=False,complete=False,admitted=False,current_qualified=False,release_authority=False)
    report=folder/'independent-receiving.json'
    def save():force._write(report,out)
    def stage(name,call):
        started=time.monotonic()
        def expired(*unused):raise TimeoutError('independent_stage_exceeded_ten_seconds')
        previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,10.)
        try:
            value=call();out['stages'][name]=dict(ok=True,result=value,elapsed_s=time.monotonic()-started);return value
        except Exception as exc:
            error=type(exc).__name__+':'+str(exc);out['errors'].append(name+':'+error)
            out['stages'][name]=dict(ok=False,error=error,elapsed_s=time.monotonic()-started);return None
        finally:
            signal.setitimer(signal.ITIMER_REAL,0.);signal.signal(signal.SIGALRM,previous);save()
    parent=p.LoadBoard(str(source));child=p.LoadBoard(str(candidate))
    old_root,old=ast._nodes(source);new_root,new=ast._nodes(candidate)
    state={}
    def semantic():
        need(record['source_sha256']==identity['source_sha256'] and record['candidate_sha256']==identity['candidate_sha256'],'construction_actual_hash_mismatch')
        need(record['intent']==role['intent'],'construction_intent_mismatch')
        fresh=repair.plan(source,record['intent'],board_hint=hint)
        need(repair._replay_identity(fresh)==repair._replay_identity(role),'fresh_missing_bypass_role_differs')
        uid=record['intent']['capacitor_uuid'];fp=next(f for f in parent.GetFootprints() if force._uid(f)==uid)
        supply=next(pad for pad in fp.Pads() if pad.GetNetname()==fresh['requirement']['rail'])
        owned=leaf.plan_missing_bypass_supply(parent,force._uid(supply),board_hint=hint,missing_bypass_intent=record['intent'])
        need(syntax._freeze(owned)==syntax._freeze(claimed_leaf),'fresh_exact_supply_leaf_differs')
        state.update(role=fresh,leaf=owned,uid=uid,ref=fp.GetReference())
        return dict(ok=True,retired_tracks=owned['track_uuids'],source_role_only=True)
    stage('fresh_semantic_role_and_leaf',semantic)
    stage('saved_missing_assignment',lambda:repair.receive(source,candidate,role,board_hint=hint))
    def barrel_scope():
        need(state,'fresh_semantics_required')
        retired=record.get('retired_via_uuids',[])
        need(type(retired)is list and len(retired)==len(set(retired)) and len(retired)<=1,
             'one_explicit_corrective_ground_barrel_maximum')
        if not retired:
            need(record.get('ground_replacement_via_uuid') is None and not (folder/'source-ground-barrel.json').exists(),
                 'undeclared_ground_barrel_replacement')
            state['retired_vias']=set()
            return dict(ok=True,applicable=False,retired_via_uuids=[])
        import cec_corrective_bypass_ground_barrel as barrel
        proof=json.loads((folder/'source-ground-barrel.json').read_text())
        fresh=barrel.plan(source,record['intent'],proof['ground_pad_uuid'],retired[0],board_hint=hint,
                         allow_locked_via_uuid=proof['allow_locked_via_uuid'],timeout_s=9.)
        need(fresh==proof,'exact_fresh_corrective_barrel_scope_required')
        need(proof['via_uuid']==retired[0] and proof['missing_bypass_intent']==record['intent'],
             'only_declared_corrective_barrel_source_owned')
        state.update(barrel=proof,retired_vias=set(retired))
        return dict(ok=True,applicable=True,proof=fresh)
    stage('fresh_exclusive_ground_barrel_scope',barrel_scope)
    def receive_barrel():
        need('retired_vias' in state,'fresh_barrel_scope_required')
        if not state['retired_vias']:return dict(ok=True,complete=True,applicable=False)
        import cec_corrective_bypass_ground_barrel as barrel
        return barrel.receive(source,candidate,state['barrel'],record['ground_replacement_via_uuid'],
                              board_hint=hint,retired_supply_track_uuids=state['leaf']['track_uuids'],timeout_s=9.)
    stage('independent_saved_ground_barrel_replacement',receive_barrel)
    def reconstruct():
        need(state,'fresh_semantics_required')
        need('retired_vias' in state,'fresh_barrel_scope_required')
        owned=state['leaf'];retired=set(owned['track_uuids']);uid=state['uid']
        need(set(record['retired_track_uuids'])==retired,'claimed_cuts_differ_from_fresh_leaf')
        board=p.LoadBoard(str(source));cap=next(f for f in board.GetFootprints() if force._uid(f)==uid)
        need(not any(g.ContainsItem(cap) for g in board.Groups()),'grouped_cap_needs_separate_annotation_owner')
        cap.SetOrientationDegrees(record['pose'][2]);cap.SetPosition(p.VECTOR2I(*(round(v*1e6) for v in record['pose'][:2])))
        actual=next(f for f in child.GetFootprints() if force._uid(f)==uid)
        need(tuple(actual.GetPosition())==tuple(cap.GetPosition()) and actual.GetOrientationDegrees()==cap.GetOrientationDegrees(),'saved_cap_pose_differs')
        need(len(record['pose'])==3 and record['pose'][2] in (0,90,180,270),'bounded_cardinal_pose_required')
        original=next(f for f in parent.GetFootprints() if force._uid(f)==uid)
        need(__import__('math').dist(tuple(original.GetPosition()),tuple(cap.GetPosition()))<=6000000,'source_local_six_mm_limit')
        discard_items(board,[t for t in board.GetTracks() if force._uid(t) in retired|state['retired_vias']])
        ground=next(pad for pad in cap.Pads() if pad.GetNetname()=='GND')
        result,refusal=decoupling._add_ground_return(board,ground,board_path=str(source),reach_mm=.8,
                                                  lock=bool(state['retired_vias']),diagnostics={})
        need(result and not refusal,'independent_ground_construction_refused:'+str(refusal))
        route=record['supply_route'];points=route['points_nm']
        need(route['net']==owned['net'] and route['width_nm']==owned['width_nm'] and route['layer']==board.GetLayerName(owned['layer']),'exact_source_leaf_route_net_width_layer_required')
        geometry.path(points,minimum_phase_nm=20000)
        supply=next(pad for pad in cap.Pads() if force._uid(pad)==owned['pad_uuid'])
        guarded=copy.deepcopy(owned);guarded['points_nm'][0]=list(supply.GetPosition())
        diagnostics={}
        need(leaf.path_clear(board,guarded,points,timeout_s=8.,diagnostics=diagnostics),'independent_source_leaf_path_guard:'+str(diagnostics))
        cells.emit_connections(board,[route],[],identity='missing-bypass-corrective-pilot:'+uid)
        state['projected']=board
        return dict(ok=True,path_clear=diagnostics,source_leaf_width_nm=owned['width_nm'],new_barrel_capacity_credit=False)
    stage('independent_ground_and_supply_path',reconstruct)
    def exact_delta():
        need('projected' in state,'independent_construction_required')
        retired=set(state['leaf']['track_uuids'])|state['retired_vias'];uid=state['uid']
        ground={force._uid(z) for z in parent.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
        need(globals_only(old_root,old)==globals_only(new_root,new),'root_metadata_changed')
        need(set(old)-set(new)==retired,'unexpected_source_object_retirement')
        additions=set(new)-set(old);need(additions==set(record['added_track_uuids']),'added_native_inventory_differs')
        need(set(record['changed_source_uuids'])==ground|{uid},'unexpected_changed_source_scope')
        for key,node in old.items():
            if key in retired or key==uid:continue
            if key in ground:need(ast._without(node,'filled_polygon')==ast._without(new[key],'filled_polygon'),'ground_nonfill_changed')
            else:need(node==new.get(key),'unowned_source_node_changed:'+key)
        need(force._sidecars(source)==force._sidecars(candidate),'source_rules_or_companions_changed')
        with tempfile.TemporaryDirectory(prefix='missing-bypass-expect-') as work:
            native=Path(work)/'expected.kicad_pcb';field._save_field_snapshot(state['projected'],native)
            expected=ast._nodes(native)[1]
            expected_added=set(expected)-set(old)
            need(sorted(map(repr,(signature(expected[u]) for u in expected_added)))==sorted(map(repr,(signature(new[u]) for u in additions))),
                 'new_copper_process_geometry_or_inventory_not_exact_independent_replay')
        state.update(ground=ground,additions=additions)
        return dict(ok=True,unowned_source_ASTs_exact=True,all_unretired_source_barrels_exact=True,
                    exclusively_retired_source_barrels=sorted(state['retired_vias']),added_uuids=sorted(additions))
    stage('whole_saved_delta_and_new_process',exact_delta)
    def ground_fill():
        need('projected' in state,'independent_construction_required')
        ast._ground_refill(state['projected'])
        with tempfile.TemporaryDirectory(prefix='missing-bypass-fill-') as work:
            native=Path(work)/'filled.kicad_pcb';field._save_field_snapshot(state['projected'],native);expected=ast._nodes(native)[1]
            for uid in state['ground']:need(expected[uid]==new[uid],'saved_ground_fill_not_exact_replay:'+uid)
        return dict(ok=True,ground_fill_replayed=True,non_ground_fills_unchanged=True)
    stage('independent_saved_ground_fill',ground_fill)
    stage('saved_native_pose',lambda:placement._screen(child,record['capacitor_ref'],time.monotonic()+9.))
    def immediate():
        cap=next(f for f in child.GetFootprints() if force._uid(f)==record['intent']['capacitor_uuid'])
        ground=next(pad for pad in cap.Pads() if pad.GetNetname()=='GND')
        found=decoupling._existing_return(child,ground,.8,allow_native_track_body=True)
        need(found is not None,'saved_immediate_ground_return_missing')
        return dict(ok=True,length_mm=found[0],via_uuid=force._uid(found[1]),maximum_mm=.8)
    stage('saved_immediate_ground_return',immediate)
    def partition_check():
        need(state,'fresh_semantics_required')
        need('retired_vias' in state,'fresh_barrel_scope_required')
        proof=partitions.compare(parent,child,timeout_s=9.,retired_uuids=set(state['leaf']['track_uuids'])|state['retired_vias'],identity_rebindings=complete._pad_rebindings(parent,child,{state['ref']:record['pose']}))
        need(proof['preserved'] and not proof['demoted_parts'],'original_terminal_partition_demoted')
        return {k:v for k,v in proof.items() if k not in ('source_parts','child_parts','demoted_parts')}
    stage('all_original_partitions',partition_check)
    stage('all_original_ground_returns',lambda:returns.receive(parent,child,timeout_s=9.))
    stage('whole_current_nonregression',lambda:current.receive(source,candidate,board_hint=hint))
    def quality():
        a,b=craft.analyze_board(parent),craft.analyze_board(child)
        need(b['issue_count']<=a['issue_count'] and b['non_octilinear_count']<=a['non_octilinear_count'],'trace_craft_regression')
        return dict(ok=True,before_after=[a['issue_count'],b['issue_count']])
    stage('tracecraft',quality)
    stage('paired_electrical_field_nonregression',lambda:pairs.receive(source,candidate,timeout_s=8.))
    def stack():
        import cec_assembly_envelope as assembly
        need(cover is not None and stack_contract is not None,'explicit_matched_cover_and_stack_contract_required')
        files=[candidate,Path(cover).resolve(strict=True),Path(stack_contract).resolve(strict=True)]
        hashes={str(path):force._hash(path) for path in files}
        contract=json.loads(files[2].read_text());fit,_=assembly.evaluate(files[0],files[1],contract)
        vents=assembly.vent_reservations(child,assembly.facing_vents(fit,contract,'carrier'))
        need(fit['ok'] and all(row['ok'] for row in vents),'paired_body_or_vent_screen_refused')
        need(hashes=={str(path):force._hash(path) for path in files},'paired_inputs_changed')
        return dict(ok=True,source_files=hashes,paired_body_checks=len(fit['checks']),
                    missing=fit['missing'],failures=[row for row in fit['checks'] if not row['ok']],vent_checks=vents,
                    contacts=fit['contacts'],hardware=fit['hardware'],assembled_height_qualified=False)
    stage('explicit_saved_paired_stack',stack)
    def native():
        result=drc.run(candidate,folder/'native-drc.json',reporting_build=reporting_build,timeout_s=9.,footprint_table=footprint_table)
        need(result.get('ok') and result.get('complete'),'native_drc_unavailable')
        data=json.loads((folder/'native-drc.json').read_text())
        counts=dict(errors=sum(v.get('severity')=='error' for v in data['violations']),warnings=sum(v.get('severity')=='warning' for v in data['violations']),opens=len(data['unconnected_items']))
        need(counts['errors']==0 and counts['opens']==0,'native_errors_or_opens:'+str(counts))
        return dict(ok=True,counts=counts,producer=result,report_sha256=force._hash(folder/'native-drc.json'))
    stage('saved_native_drc',native)
    final=dict(source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),source_sidecars=force._sidecars(source),candidate_sidecars=force._sidecars(candidate),code_identity=force._code_identity())
    out['source_candidate_and_code_unchanged']=identity==final
    if identity!=final:out['errors'].append('source_candidate_or_code_changed')
    for name,row in out['stages'].items():
        if row.get('ok') and isinstance(row.get('result'),dict) and (row['result'].get('ok') is False or row['result'].get('complete') is False):
            row['ok']=False;out['errors'].append(name+':receiver_refused')
    out['complete']=True;out['ok']=not out['errors'] and all(s['ok'] for s in out['stages'].values())
    out['limits']=['Experimental independent checks only; no fabrication, bar, thermal, matched-stack or release admission.','Source-chain receiving remains mandatory; current debt nonregression is not qualification.']
    save();print(json.dumps(dict(ok=out['ok'],report=str(report),report_sha256=force._hash(report),errors=out['errors'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--footprint-table',type=Path,required=True);parser.add_argument('--reporting-build',type=Path,required=True)
    parser.add_argument('--cover',type=Path);parser.add_argument('--stack-contract',type=Path)
    args=parser.parse_args();run(args.folder,footprint_table=args.footprint_table,reporting_build=args.reporting_build,cover=args.cover,stack_contract=args.stack_contract)
