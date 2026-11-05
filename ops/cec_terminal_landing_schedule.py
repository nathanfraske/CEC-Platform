"""Finite source-rederived keeper cohorts; discovery metadata is not authority."""
import json
from pathlib import Path
import cec_force_current as force
import cec_centered_terminal_landing as owner

POLICY = 'bounded-source-rederived-terminal-keeper-cohorts-v1'


def menus(rows, *, maximum_changes=4, maximum_trials=8):
    owner.require(type(rows) is list and len(rows) <= 128
        and type(maximum_changes) is int and 1 <= maximum_changes <= 4
        and type(maximum_trials) is int and 1 <= maximum_trials <= 12,
        'finite_source_terminal_schedule_domain_required')
    unique = set()
    for row in rows:
        owner.require(type(row) is dict and set(row) == {'target','keeper_uuid'}, 'literal_terminal_schedule_record_required')
        target = row['target']
        owner.require(type(target) is dict and set(target) == {'via_uuid','layer_id','allow_locked_source'}
            and type(target['via_uuid']) is str and target['via_uuid']
            and type(target['layer_id']) is int and 0 <= target['layer_id'] < 64
            and type(target['allow_locked_source']) is bool
            and type(row['keeper_uuid']) is str and row['keeper_uuid'], 'typed_actual_terminal_target_required')
        key = (target['via_uuid'],target['layer_id'])
        owner.require(key not in unique,'duplicate_actual_terminal_target'); unique.add(key)
    result = []; seen = set()
    for offset in range(min(4,len(rows))):
        for count in dict.fromkeys((maximum_changes,min(2,maximum_changes),1)):
            cohort = []; keepers = set()
            for row in rows[offset:]:
                if row['keeper_uuid'] in keepers: continue
                cohort.append(row['target']); keepers.add(row['keeper_uuid'])
                if len(cohort) == count: break
            signature = json.dumps(cohort,sort_keys=True)
            if cohort and signature not in seen:
                result.append(cohort); seen.add(signature)
                if len(result) == maximum_trials: return result
    return result


def from_source(source, discovery_path, *, board_hint, maximum_changes=4, maximum_trials=8):
    source = Path(source).resolve(); path = Path(discovery_path).resolve()
    data = json.loads(path.read_text()); epoch = force._code_identity()
    owner.require(data['ok'] and data['complete'] and data['code_identity'] == epoch
        and data['source_sha256'] == force._hash(source)
        and Path(data['source']).resolve() == source and data['source_family_unchanged']
        and data['changed'] is False and data['actual_geometry_constructed'] is False,
        'actual_unchanged_source_discovery_binding_required')
    inputs = {str(q):force._hash(q) for q in (source,path,Path(__file__).resolve(),Path(owner.__file__).resolve())}
    for name,digest in data['input_sha256'].items():
        owner.require(force._hash(Path(name)) == digest,'terminal_discovery_dependency_changed'); inputs[name] = digest
    rows = []; refusals = []
    for row in data['attempts']:
        if row.get('eligible') is not True: continue
        try:
            actual = owner.record(source,board_hint=board_hint,**row['target'])
            owner.require(actual['zone_uuid'] == row['keeper_uuid'],'discovery_claimed_wrong_actual_terminal_keeper')
            rows.append(dict(target=row['target'],keeper_uuid=actual['zone_uuid']))
        except (ValueError,TypeError,KeyError) as exc:
            refusals.append(dict(target=row.get('target'),refusal=str(exc)))
    proposals = menus(rows,maximum_changes=maximum_changes,maximum_trials=maximum_trials)
    owner.require(epoch == force._code_identity() and all(force._hash(Path(q)) == h for q,h in inputs.items()),
        'terminal_schedule_source_or_code_changed')
    return dict(policy=POLICY,source_sha256=force._hash(source),code_identity=epoch,menus=proposals,
        actual_eligible_targets=rows,source_rederivation_refusals=refusals,input_sha256=inputs,
        all_board_contours_clean_claimed=False,release_authority=False)
