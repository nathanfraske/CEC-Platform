"""Exact saved-source force/sense replay in independently bounded constituents.

The default replay is unchanged. Each worker rederives the COMPLETE lineage,
physical terminals, current authority, code and saved family; it observes only
one physical input/leg, or the independent legacy diagnostic. Only assemble()
can emit a complete replay, after an exact fresh manifest/coverage join. The
unchanged clipping audit still models every conductor, hole and bound.

Deadlines are cooperative between native calls. Run each CLI invocation under
an EXTERNAL <=10-second process deadline; never SIGALRM-interrupt GEOS/SWIG.
No native proxy or geometry cache crosses a worker boundary.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import time

import cec_force_sense_evidence as evidence


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _budget(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10:
        raise ValueError('force_sense_shard_constituent_budget_in_0_to_10_required')
    return value


def _manifest_payload(report):
    keys=('board_hint','budget','inventory','geometry_policy','lineage','declared_pairs','shard_inventory')
    if type(report) is not dict or not set(keys)<=report.keys():
        raise ValueError('complete_force_sense_shard_manifest_inventory_required')
    return {key:report[key] for key in keys}


def _run(source,board_hint,selector,timeout_s):
    import pcbnew
    import cec_swig_guard
    import cec_force_current as force
    cec_swig_guard.pin()
    start=time.monotonic();seconds=_budget(timeout_s)
    source=Path(source).resolve(strict=True)
    before,code=force._family(source,board_hint),force._code_identity()
    board=pcbnew.LoadBoard(str(source))
    result=evidence.audit(board,board_hint=board_hint,deadline=start+seconds,_shard=selector)
    after,code_after=force._family(source,board_hint),force._code_identity()
    result.update(source=str(source),source_family_before=before,source_family_after=after,
        code_before=code,code_after=code_after,code_identity_scope='all_local_scripts_python_sources',
        source_identity_scope='existing_force_source_family_guard',loaded_board_identity_verified=True,
        source_unchanged=before==after,code_unchanged=code==code_after,
        identity_stable=before==after and code==code_after)
    if not result['identity_stable']:
        result.update(shard_complete=False,stop='concurrent_source_family_or_code_change')
    if 'shard_inventory' in result:
        result['shard_manifest_sha256']=_digest(_manifest_payload(result))
    result['elapsed_s']=time.monotonic()-start
    return result


def manifest(source,*,board_hint,timeout_s=9.1):
    """Full exact denominator/identity inventory; never a complete replay."""
    return _run(source,board_hint,('manifest',),timeout_s)


def _require(report,reference,selector):
    if (type(report) is not dict or report.get('scope')!=evidence.SCOPE
            or report.get('complete') is not False or report.get('shard_complete') is not True
            or report.get('stop') is not None or report.get('errors')
            or report.get('identity_stable') is not True
            or report.get('loaded_board_identity_verified') is not True
            or report.get('source_unchanged') is not True or report.get('code_unchanged') is not True
            or type(report.get('elapsed_s')) not in (int,float)
            or not math.isfinite(report['elapsed_s']) or not 0<=report['elapsed_s']<=10
            or report.get('shard_selector')!=list(selector)):
        raise ValueError('complete_bound_exact_scoped_force_sense_shard_required')
    for key in ('source','board_hint','source_family_before','source_family_after','code_before','code_after'):
        if _json(report.get(key))!=_json(reference.get(key)):
            raise ValueError('force_sense_shard_source_family_or_code_epoch_mismatch:'+key)
    payload=_manifest_payload(report);expected=_manifest_payload(reference)
    if (_json(payload)!=_json(expected) or report.get('shard_manifest_sha256')!=_digest(payload)
            or reference.get('shard_manifest_sha256')!=_digest(expected)):
        raise ValueError('force_sense_shard_full_lineage_or_denominator_mismatch')


def replay_leg(source,prepared,*,board_hint,input_ref,leg,timeout_s=9.1):
    """Observe ONE actual input/leg; all reported denominators remain full."""
    if type(input_ref) is not str or not input_ref or leg not in ('p','n'):
        raise ValueError('one_literal_physical_input_leg_required')
    _require(prepared,prepared,('manifest',))
    if not any((q['input_ref'],q['leg'])==(input_ref,leg) for q in prepared['shard_inventory']['legs']):
        raise ValueError('selected_input_leg_not_in_complete_source_lineage')
    result=_run(source,board_hint,('leg',input_ref,leg),timeout_s)
    if result.get('shard_complete') is True:_require(prepared,result,('manifest',))
    return result


def replay_legacy(source,prepared,*,board_hint,timeout_s=9.1):
    """Run the independent legacy diagnostic once, not as a clipped proof."""
    _require(prepared,prepared,('manifest',))
    result=_run(source,board_hint,('legacy',),timeout_s)
    if result.get('shard_complete') is True:_require(prepared,result,('manifest',))
    return result


def _omitted(rows,expected,unresolved):
    checked=sum(row['observed'] for row in rows)
    return dict(ok=None,isolation_qualified=None,
        status='observed' if checked==expected and checked and not unresolved else
            'not_applicable' if not expected and not unresolved else 'unknown',
        expected=expected,checked=checked,unknown=expected-checked,unresolved_inputs=unresolved,
        reached_authority_legs=sum(bool(row.get('reached_authority')) for row in rows),
        tracks_clipped=False,physical_bypass_proved=False,nonregression_isolation_certificate=False,details=rows)


def _coverage(report):
    inventory=report['shard_inventory'];unresolved=inventory['unresolved_inputs']
    for category in ('same_net_connectivity','inner_departure','clipped_isolation'):
        packet=report[category]
        expected=inventory['expected_demands' if category=='same_net_connectivity' else 'expected_legs']
        if _json(packet)!=_json(evidence._coverage(packet['details'],expected,unresolved_inputs=unresolved)):
            raise ValueError('force_sense_shard_coverage_counter_mismatch:'+category)
    packet=report['shunt_pad_omitted']
    if _json(packet)!=_json(_omitted(packet['details'],inventory['expected_legs'],unresolved)):
        raise ValueError('force_sense_shard_omitted_coverage_counter_mismatch')


def _leg_key(row):
    return row['input_ref'],row['leg'],row['net']


def _segment_key(row):
    return (*_leg_key(row),_json((row['start'],row['end'])))


def assemble(source,prepared,leg_reports,legacy_report,*,board_hint,timeout_s=9.1):
    """Fresh full Source manifest + every exact leg + ONE legacy observation.

    No proof outcome is normalized, repaired, replaced or granted by this
    join. Unknown/failed absolute cuts and all original counters stay visible.
    Complete means the same observation coverage as replay(), not a pass.
    """
    import cec_force_current as force
    started=time.monotonic();deadline=started+_budget(timeout_s)
    def tick():
        if time.monotonic()>=deadline:raise ValueError('force_sense_coverage_join_deadline_exhausted')
    fresh=manifest(source,board_hint=board_hint,timeout_s=timeout_s)
    _require(prepared,fresh,('manifest',));_require(fresh,fresh,('manifest',))
    inventory=fresh['shard_inventory'];legs=inventory['legs'];segments=inventory['segments']
    if (type(leg_reports) not in (list,tuple) or len(leg_reports)!=len(legs)
            or len(leg_reports)>2*evidence.MAX_INPUTS):
        raise ValueError('every_full_manifest_physical_leg_required_exactly_once')
    expected={_leg_key(row):row for row in legs}
    if len(expected)!=len(legs):raise ValueError('ambiguous_full_manifest_physical_leg')
    observed={};collected={key:{} for key in ('same_net_connectivity','inner_departure','shunt_pad_omitted','clipped_isolation')}
    authority={}
    for report in leg_reports:
        tick()
        selector=report.get('shard_selector',()) if type(report) is dict else ()
        if len(selector)!=3 or selector[0]!='leg':raise ValueError('one_exact_input_leg_shard_required')
        _require(report,fresh,tuple(selector));_coverage(report)
        matches=[key for key in expected if key[:2]==tuple(selector[1:])]
        if len(matches)!=1 or matches[0] in observed:raise ValueError('duplicate_or_foreign_physical_leg_shard')
        key=matches[0];fact=expected[key];observed[key]=report
        for category,rows in collected.items():
            details=report[category]['details']
            wanted=[q for q in segments if _leg_key(q)[:2]==key[:2]] if category=='same_net_connectivity' else [fact]
            key_for=_segment_key if category=='same_net_connectivity' else _leg_key
            actual={key_for(q):q for q in details}
            if len(actual)!=len(details) or actual.keys()!={key_for(q) for q in wanted}:
                raise ValueError('missing_duplicate_or_foreign_shard_detail:'+category)
            for item_key,row in actual.items():
                tick()
                if item_key in rows:raise ValueError('duplicate_shard_detail:'+category)
                if (category=='shunt_pad_omitted' and type(row.get('observed')) is not bool
                        or category!='shunt_pad_omitted' and row.get('ok') is not None and type(row['ok']) is not bool):
                    raise ValueError('literal_boolean_or_unknown_native_observation_required')
                for identity in ('source_pad','sense_terminal'):
                    if identity in row and _json(row[identity])!=_json(fact[identity]):
                        raise ValueError('shard_physical_terminal_identity_changed')
                if category=='same_net_connectivity':
                    original=next(q for q in wanted if _segment_key(q)==item_key)
                    for field in ('leg','net','input_ref','start','end','start_pad','end_pad'):
                        if field in row and _json(row[field])!=_json(original[field]):
                            raise ValueError('shard_segment_physical_identity_changed')
                if category=='shunt_pad_omitted' and 'authority_excluding_cut' in row:
                    if _json(row['authority_excluding_cut'])!=_json(fact['authority_excluding_cut']):
                        raise ValueError('shard_physical_authority_changed')
                if category=='clipped_isolation' and 'native' in row:
                    import cec_kelvin_copper_cut as cut
                    proof=row['native']
                    if (type(proof.get('schema')) is not int or proof['schema']!=1 or proof.get('scope')!=cut.SCOPE
                            or type(proof.get('approximation_error_nm')) is not int or proof['approximation_error_nm']!=cut.ERROR_NM
                            or type(proof.get('numerical_guard_nm')) is not int or proof['numerical_guard_nm']!=cut.GUARD_NM
                            or type(proof.get('complete')) is not bool
                            or proof.get('ok') is not None and proof['complete'] is not True
                            or proof.get('tracks_clipped') is not True or proof.get('ok') is not row['ok']):
                        raise ValueError('shard_absolute_cut_model_or_result_changed')
                    for label,identity in (('source','source_pad'),('sense','sense_terminal')):
                        if _json(proof.get(label))!=_json(dict(fact[identity],kind='PAD')):
                            raise ValueError('shard_absolute_cut_physical_terminal_changed')
                    expected_authority=[dict(p,kind='PAD') for p in fact['authority_excluding_cut']]
                    if _json(proof.get('authority'))!=_json(expected_authority):
                        raise ValueError('shard_absolute_cut_physical_authority_changed')
                rows[item_key]=copy.deepcopy(row)
        for net,domain in report['authority'].items():
            if _json(domain)!=_json(inventory['authority_domains'].get(net)) or net in authority and _json(authority[net])!=_json(domain):
                raise ValueError('shard_current_authority_changed')
            authority[net]=copy.deepcopy(domain)
    if observed.keys()!=expected.keys():raise ValueError('incomplete_full_physical_leg_coverage')
    _require(legacy_report,fresh,('legacy',));_coverage(legacy_report)
    if any(legacy_report[c]['details'] for c in collected) or legacy_report['authority']:
        raise ValueError('independent_legacy_shard_contains_nonlegacy_observations')
    result=copy.deepcopy(fresh)
    for key in ('shard_inventory','shard_selector','shard_complete','shard_manifest_sha256'):
        result.pop(key,None)
    unresolved=inventory['unresolved_inputs']
    for category,rows in collected.items():
        order=segments if category=='same_net_connectivity' else legs
        key_for=_segment_key if category=='same_net_connectivity' else _leg_key
        ordered=[rows[key_for(q)] for q in order]
        result[category]=(_omitted(ordered,inventory['expected_legs'],unresolved) if category=='shunt_pad_omitted'
            else evidence._coverage(ordered,inventory['expected_demands' if category=='same_net_connectivity' else 'expected_legs'],unresolved_inputs=unresolved))
    result.update(complete=True,authority=authority,legacy_topology=copy.deepcopy(legacy_report['legacy_topology']),
        sharded_replay=dict(manifest_sha256=fresh['shard_manifest_sha256'],physical_legs=len(legs),
            same_net_demands=len(segments),legacy_observations=1,full_exact_coverage_join=True,
            constituent_elapsed_s=[q['elapsed_s'] for q in [*[observed[_leg_key(row)] for row in legs],legacy_report,fresh]],
            constituent_sha256=[_digest(q) for q in [prepared,*[observed[_leg_key(row)] for row in legs],legacy_report]],
            native_proxies_or_geometry_caches_shared=False,absolute_proofs_unchanged=True))
    # The fresh manifest guards its own observation, not the later join. Close
    # the saved-family/code epoch AGAIN after every receipt has been consumed.
    after,code_after=force._family(Path(source).resolve(),board_hint),force._code_identity()
    tick()
    if after!=fresh['source_family_before'] or code_after!=fresh['code_before']:
        raise ValueError('force_sense_source_family_or_code_changed_during_coverage_join')
    result.update(source_family_after=after,code_after=code_after,elapsed_s=time.monotonic()-started)
    return result


def main(argv=None):
    import argparse
    import cec_force_current as force
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('manifest','leg','legacy','assemble'))
    for name in ('source','board-hint','out'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--timeout-s',type=float,default=9.1)
    parser.add_argument('--manifest');parser.add_argument('--input-ref');parser.add_argument('--leg',choices=('p','n'))
    parser.add_argument('--leg-report',action='append',default=[]);parser.add_argument('--legacy-report')
    args=parser.parse_args(argv);out=Path(args.out)
    if out.exists():raise ValueError('new_shard_evidence_output_required')
    options=dict(board_hint=args.board_hint,timeout_s=args.timeout_s)
    read=lambda path:json.loads(Path(path).read_text())
    if args.stage=='manifest':result=manifest(args.source,**options)
    elif args.stage=='leg':result=replay_leg(args.source,read(args.manifest),input_ref=args.input_ref,leg=args.leg,**options)
    elif args.stage=='legacy':result=replay_legacy(args.source,read(args.manifest),**options)
    else:result=assemble(args.source,read(args.manifest),[read(p) for p in args.leg_report],read(args.legacy_report),**options)
    force._write(out,result)
    print(_json(dict(output=str(out),sha256=force._hash(out),complete=result['complete'],
        shard_complete=result.get('shard_complete'),stop=result.get('stop'))),flush=True)


if __name__=='__main__':main()
