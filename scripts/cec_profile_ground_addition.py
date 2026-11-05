"""Exact-source profile-derived GND additions, independently reconstructed."""
import json
import re
import uuid
from pathlib import Path
import pcbnew
import cec_ground_plane as ground
import cec_additive_route_receiving as additive
import cec_source_retaining_ses_import as raw
import cec_field_coupling as field
import cec_force_current as force
import cec_copper_echo as sexpr

def normalized(node):
    return sexpr._parse(sexpr._TOKEN.findall(node))

def graft(source_text,new_text,new_ids):
    source=raw.inventory(source_text);generated=raw.inventory(new_text);result=source_text
    if set(new_ids)&source.keys():raise ValueError('new_ground_uuid_aliases_source')
    additions=[]
    for uid in new_ids:
        a,b=generated[uid];node=new_text[a:b]
        if raw.kind(node)!='zone':raise ValueError('only_profile_zone_additions_permitted')
        additions.append(node)
    end=raw.children(result,root_end=True)
    return result[:end]+'\n'+'\n'.join(additions)+'\n'+result[end:]

def validate_binding(source,board_hint,expected_source_sha256):
    if (type(board_hint)is not str or not board_hint or type(expected_source_sha256)is not str
            or not re.fullmatch('[0-9a-f]{64}',expected_source_sha256)
            or force._hash(source)!=expected_source_sha256):raise ValueError('exact_source_hash_and_board_hint_required')
    import cec_synth_pipeline
    cec_synth_pipeline.Config.load(board_hint)
    board=pcbnew.LoadBoard(str(source))
    layers,profile=ground._dedicated_ground_layers(board,board_hint)
    if not profile or not layers:raise ValueError('explicit_enabled_profile_ground_authority_required')

def validate_new_ids(mapping,missing,source_ids):
    if not isinstance(mapping,dict) or set(mapping)!=set(missing):raise ValueError('exact_missing_layer_mapping_required')
    values=list(mapping.values())
    for value in values:
        try:canonical=str(uuid.UUID(value))
        except (ValueError,TypeError,AttributeError):raise ValueError('canonical_new_zone_uuid_required')
        if value!=canonical:raise ValueError('canonical_new_zone_uuid_required')
    if len(set(values))!=len(values) or set(values)&set(source_ids):raise ValueError('new_zone_uuid_duplicate_or_source_alias')

def construct(source,out,*,board_hint,expected_source_sha256,bound_new_ids=None):
    validate_binding(source,board_hint,expected_source_sha256)
    out=Path(out);out.mkdir(exist_ok=False)
    target=force._copy_family(source,out/'candidate');b=pcbnew.LoadBoard(str(target))
    declaration=ground.declare_profile_ground_planes(b,board_path=board_hint)
    if not declaration['ok'] or not declaration['added']:raise ValueError('missing_profile_ground_authority_or_no_missing_planes')
    new={row['layer']:row['uuid'] for row in declaration['added']}
    if len(new)!=len(declaration['added']):raise ValueError('duplicate_missing_layer')
    if bound_new_ids is not None:
        validate_new_ids(bound_new_ids,new,raw.inventory(raw.raw_text(source)))
    else:validate_new_ids(new,new,raw.inventory(raw.raw_text(source)))
    # Only newly declared missing planes may fill. Existing GND caches are
    # just as immutable as source power fills and all opaque source nodes.
    selected=pcbnew.ZONES();allowed=set(new.values());before=field._field_snapshot_inventory(b)
    for zone in b.Zones():
        if str(zone.m_Uuid.AsString()) in allowed:zone.UnFill();selected.append(zone)
    import cec_zone_fill
    cec_zone_fill.compile_selected(b,selected,initialize_selected=True)
    after=field._field_snapshot_inventory(b)
    if before.keys()!=after.keys() or any(before[k]!=after[k] for k in before if k not in {('zone',u) for u in allowed}):raise ValueError('selected_new_plane_fill_changed_source_evidence')
    temp=out/'native-regenerated.kicad_pcb'
    field._save_field_snapshot(b,temp)
    generated=raw.raw_text(temp)
    if bound_new_ids is not None:
        for layer,old in new.items():
            if generated.count(old)!=1:raise ValueError('ambiguous_replay_uuid')
            generated=generated.replace(old,bound_new_ids[layer])
        new=dict(bound_new_ids)
    raw.write_raw(target,graft(raw.raw_text(source),generated,new.values()))
    return dict(candidate=str(target),new_zone_ids_by_profile_layer=new,declaration=declaration)

def receive(source,candidate,replay_out,*,board_hint,new_ids,expected_source_sha256):
    replay=construct(source,replay_out,board_hint=board_hint,expected_source_sha256=expected_source_sha256,bound_new_ids=new_ids)
    expected=raw.raw_text(replay['candidate']);actual=raw.raw_text(candidate)
    # Exact whole-root AST includes unknown fields, declarations, per-zone
    # clearance and independently native-rebuilt fills, not child authority.
    validate_expected(source,actual,expected,new_ids)
    source_companions,_=force._companion_inventory(Path(source))
    candidate_companions,_=force._companion_inventory(Path(candidate))
    if set(source_companions)!=set(candidate_companions):raise ValueError('source_companion_inventory_changed')
    for ext,path in source_companions.items():
        other=candidate_companions[ext]
        if path.exists()!=other.exists() or (path.exists() and path.read_bytes()!=other.read_bytes()):raise ValueError('source_companion_bytes_changed')
    b=pcbnew.LoadBoard(str(candidate))
    required=[str(v.m_Uuid.AsString()) for v in b.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND']
    audit=ground.audit_board(b,board_path=board_hint,required_via_uuids=required)
    return dict(independent_full_root_replay=True,all_original_nodes_literal_exact=True,
        source_companions_byte_exact=True,only_expected_profile_plane_additions=True,ground_audit=audit,replay=replay,
        ground_contact_scope='native_center_contact_only_not_full_annular_or_current_qualification')

def validate_expected(source,actual,expected,new_ids):
    if normalized(expected)!=normalized(actual):raise ValueError('profile_ground_independent_replay_mismatch')
    source_text=raw.raw_text(source);old=raw.inventory(source_text);child=raw.inventory(actual)
    for uid,(a,b) in old.items():
        if uid not in child:raise ValueError('source_uuid_lost')
        x,y=child[uid]
        if source_text[a:b]!=actual[x:y]:raise ValueError('original_opaque_source_node_changed')
    if set(child)-set(old)!=set(new_ids.values()):raise ValueError('unexpected_added_source_nodes')
    return True

def _receive_full(source,candidate,output,*,board_hint,new_ids,expected_source_sha256):
    """Bounded independent construction/source/native/current receiver.

    PASS only permits this additive plane frontier; it grants no whole-power,
    thermal, Kelvin or fabrication qualification. Native reports are fresh.
    """
    import time
    import cec_native_drc_runner as native
    import cec_current_debt as debt
    import cec_synth_pipeline as synth
    import cec_full_pipeline as pipeline
    import cec_constraints as constraints
    from cec_stage_admission import native_geometry_nonregression
    if force._hash(source)!=expected_source_sha256:raise ValueError('expected_source_binding_changed')
    out=Path(output);out.mkdir(exist_ok=False)
    code=force._code_identity();source_family=force._family(source,board_hint)
    candidate_family=force._family(candidate,board_hint);started=time.monotonic()
    result=dict(scope='profile_ground_addition_only',current_qualified=False,release_authority=False)
    result['independent']=receive(source,candidate,out/'independent-replay',board_hint=board_hint,new_ids=new_ids,expected_source_sha256=expected_source_sha256)
    cfg=synth.Config.load(board_hint)
    result['source_intake']=pipeline._source_intake(cfg,source,out/'source-intake.json',allow_derived_input=True)
    result['candidate_intake']=pipeline._source_intake(cfg,candidate,out/'candidate-intake.json',allow_derived_input=True)
    for name,path in [('before',source),('after',candidate)]:
        proof=native.run(path,out/(name+'.native.json'),reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.)
        if not proof.get('ok') or not proof.get('complete'):raise ValueError('incomplete_native_plane_receiving')
    before=json.loads((out/'before.native.json').read_text());after=json.loads((out/'after.native.json').read_text())
    result['native_geometry']=native_geometry_nonregression(before,after)
    result['native_error_delta']=raw.raw_error_delta(before,after)
    result['opens_nonincreasing']=len(after['unconnected_items'])<=len(before['unconnected_items'])
    result['current_debt']=debt.receive(source,candidate,board_hint=board_hint)
    result['parity']=constraints._chk_sch_pcb_sync(pcbnew.LoadBoard(str(candidate)),str(candidate),{'sch':str(cfg.sch)})
    result['source_and_candidate_unchanged']=(source_family==force._family(source,board_hint) and candidate_family==force._family(candidate,board_hint))
    result['code_unchanged']=code==force._code_identity()
    result['ok']=all((result['independent']['ground_audit']['ok'],result['source_intake']['ok'],result['candidate_intake']['ok'],
        result['native_geometry']['ok'],result['native_geometry']['complete'],result['native_error_delta']['ok'],
        result['opens_nonincreasing'],result['current_debt']['ok'],result['current_debt']['complete'],result['parity'][0],
        result['source_and_candidate_unchanged'],result['code_unchanged']))
    result.update(source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),elapsed_s=time.monotonic()-started)
    (out/'receiving.json').write_text(json.dumps(result,indent=2,default=str));return result

def receive_full(source,candidate,output,*,board_hint,new_ids,expected_source_sha256):
    """Persist PASS/refusal including traceback. Caller MUST lease process≤120s.

    Fresh native subprocesses are individually bounded at ten seconds. This
    synchronous API cannot preempt native extensions; an outer process lease
    is required, never inferred from its return. Ground contacts are center
    contacts only, not full annular/current/thermal qualification.
    """
    import time,traceback
    out=Path(output);out.mkdir(exist_ok=False);started=time.monotonic()
    result=dict(ok=False,release_authority=False,current_qualified=False,required_outer_wall_s=120)
    try:
        result.update(_receive_full(source,candidate,out/'checks',board_hint=board_hint,new_ids=new_ids,expected_source_sha256=expected_source_sha256))
    except Exception as exc:result.update(ok=False,error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
    finally:
        result['whole_elapsed_s']=time.monotonic()-started
        (out/'receiving.json').write_text(json.dumps(result,indent=2,default=str))
    return result
