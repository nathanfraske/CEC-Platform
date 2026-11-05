"""One bounded upstream pair transaction before repeating residual searches."""
import copy
import math
import os
from pathlib import Path
import time


def _native_attempt(source,output_dir,cfg,wall_s=390.):
    import pcbnew
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_placement_route_prefix as prefix
    import cec_future_pin_access as access
    import cec_route_preflight as preflight
    import cec_precision_route as precision
    import cec_route_pair_admission as admission
    import cec_certificate_repair as repair
    import cec_fr
    import cec_score
    from cec_native_items import discard_items
    from cec_local_copper_cell import copper_inventory
    if not math.isfinite(wall_s) or not 30 <= wall_s <= 600:
        raise ValueError('pair-access transaction needs a finite 30..600 second lease')
    source,output_dir=Path(source).resolve(),Path(output_dir).resolve()
    if output_dir.exists():
        raise ValueError('pair-access trial requires a new private directory')
    output_dir.mkdir(parents=True)
    inputs=pipeline._artifact_rows(p for p in pipeline._placement_authority_family(source) if p.is_file())
    result=dict(schema=1,ok=False,changed=False,release_authority=False,attempts=[])
    started=time.monotonic()
    def finish(reason):
        result.update(reason=reason,wall_s=round(time.monotonic()-started,3))
        return result
    try:
        bound,binding=synth.config_with_board_route_authority(cfg,str(source))
        if not binding.get('ok'):
            return finish('source_authority_invalid')
        with synth._oracle_env(bound.params):
            before_score=cec_score.score(str(source))
            targets=set(before_score.detail.get('unconn_nets') or ())
            if before_score.drc!=0 or not targets:
                return finish('no_clean_residual_source')
            contract=prefix.capture(str(source))
            pairs=[pair for pair in contract.get('qualified_critical_pairs',()) if pair.get('qualified')]
            chosen=None
            for pair in pairs[:8]:
                witness=access.replacement_witness(source,contract,pair,targets,
                    deadline_monotonic=min(started+30,time.monotonic()+10))
                result['attempts'].append(dict(pair=pair['name'],witness=witness))
                if witness['ok']:
                    chosen=pair,witness
                    break
            if chosen is None:
                return finish('no_owned_pair_pin_access_frontier')
            pair,witness=chosen
            pair_s=min(240.,wall_s-(time.monotonic()-started)-120.)
            if pair_s<5:
                return finish('pair_search_and_proof_unfunded')
            pair_nets=set(witness['scope']['nets'])
            board=pcbnew.LoadBoard(str(source))
            original=copper_inventory(board)
            removed=[item for item in board.GetTracks() if item.GetNetname() in pair_nets]
            removed_ids={item.m_Uuid.AsString() for item in removed}
            if removed_ids!=set(witness['removed_pair_uuids']):
                return finish('pair_inventory_changed_after_witness')
            discard_items(board,removed)
            del removed
            os.environ['CEC_PRECISION_PAIR_TIMEOUT']=str(pair_s)
            reservations=preflight.compile_route_reservations(str(source),board=board)
            avoid=preflight.priority_pair_avoid(str(source),reservations,policy='power-first')
            solved=precision.precision_route_board(board,board_path=str(source),do_kelvin=False,
                include_pair_names=[pair['name']],pair_grid=True,avoid=avoid,
                _group_order_retry=False,_pair_search_deadline=time.monotonic()+pair_s)
            pipeline.atomic_json(output_dir/'precision.json',solved)
            if not solved.get('pairs_ok'):
                return finish('priority_pair_reconstruction_refused')
            after=copper_inventory(board)
            if any(after.get(uid)!=row for uid,row in original.items() if uid not in removed_ids):
                return finish('pair_solver_changed_non_pair_parent')
            target=output_dir/'proposal'/'board.kicad_pcb'
            pipeline._copy_sidecars(source,target,cfg=bound)
            pcbnew.SaveBoard(str(target),board)
            cec_fr.ensure_local_pair_return_via_rule(str(target),solved)
            if not cec_fr.refill_zones_isolated(str(target)):
                return finish('pair_refill_refused')
            remaining=wall_s-(time.monotonic()-started)-90.
            if remaining<=0:
                return finish('target_completion_and_proof_unfunded')
            completed=repair._lastmile_worker(str(target),witness['target_nets'],16,5.,
                prefer_bridge=True,wall_timeout_s=min(60.,remaining))
            pipeline.atomic_json(output_dir/'completion.json',completed)
            if not completed.get('closed'):
                return finish('recovered_access_did_not_close_target')
            revalidated=admission._native_prepare(source,target,output_dir/'admission',bound)
            result['revalidation']=revalidated
            if not revalidated.get('ok'):
                return finish('independent_pair_access_admission_refused')
            result.update(ok=True,changed=True,board=revalidated['board'],
                          recovered_nets=revalidated['recovered_nets'])
            return finish('owned_pair_pin_access_improved')
    finally:
        result['input_family_unchanged']=pipeline.artifacts_match(inputs)
        if not result['input_family_unchanged']:
            result.update(ok=False,changed=False,reason='input_family_changed')
        pipeline.atomic_json(output_dir/'repair.json',result)


def attempt(source,output_dir,cfg,*,wall_s=390.):
    import cec_certificate_repair as repair
    return repair._spawn_apply(_native_attempt,
        (str(source),str(output_dir),copy.deepcopy(cfg),float(wall_s)),
        timeout_s=float(wall_s)+10.,search_budget_arg=3)
