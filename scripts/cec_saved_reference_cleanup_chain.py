"""Compose at most three distinct, independently received annotation owners.

This is reference cleanup only: no new material operator or physical authority
is introduced. The outer material transaction keeps its four-phase limit.
Each existing public receiver still reconstructs its literal Source scope,
factory glyphs, associations, masks, locks and complete saved native delta.
"""
import json,re
from pathlib import Path
import cec_force_current as force
import cec_root_reference_seating as root_seats
import cec_reference_field_seating as fields
import cec_mask_search_reference_mapping as maps

OPERATIONS={'root_reference_seat':root_seats,'reference_fields':fields,'reference_map':maps}


def _need(value,reason):
    if not value:raise ValueError(reason)


def dependencies():
    modules=(root_seats,fields,maps)
    result={str(Path(__file__).resolve()):force._hash(Path(__file__))}
    for module in modules:
        result[str(Path(module.__file__).resolve())]=force._hash(Path(module.__file__))
        if hasattr(module,'dependencies'):result.update(module.dependencies())
    return result


def _file(row):
    _need(type(row)is dict and set(row)=={'path','sha256'}and type(row['path'])is str
        and type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),
        'exact_saved_reference_cleanup_file_required')
    p=Path(row['path'])
    _need(p.is_absolute()and not p.is_symlink(),'absolute_reference_cleanup_file_required')
    p=p.resolve(strict=True)
    _need(p.is_file()and force._hash(p)==row['sha256'],'saved_reference_cleanup_file_changed')
    return p


def validate(source,candidate,proposal):
    _need(type(proposal)is dict and set(proposal)=={'schema','board_hint','source','candidate','steps'}
        and type(proposal['schema'])is int and proposal['schema']==1
        and type(proposal['board_hint'])is str and proposal['board_hint'],
        'exact_saved_reference_cleanup_schema_required')
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    _need(source==_file(proposal['source'])and candidate==_file(proposal['candidate'])and source!=candidate,
        'exact_reference_cleanup_endpoints_required')
    steps=proposal['steps']
    _need(type(steps)is list and 2<=len(steps)<=3,'finite_two_or_three_reference_cleanup_steps_required')
    cursor=source;kinds=[];owners=set();resolved=[];paths={source}
    for row in steps:
        _need(type(row)is dict and set(row)=={'kind','source','candidate','proposal'}
            and row.get('kind')in OPERATIONS and row['kind']not in kinds,
            'distinct_public_annotation_cleanup_steps_required')
        kind=row['kind']
        _need(kind!='root_reference_seat'or not kinds,'existing_root_caption_preparation_must_be_first')
        parent,child,request=[_file(row[k])for k in('source','candidate','proposal')]
        _need(parent==cursor and child not in paths and request not in paths|{child},
            'continuous_distinct_saved_reference_cleanup_boundaries_required')
        q=json.loads(request.read_text())
        if kind=='root_reference_seat':
            selected=[q.get('owner_uuid')];declared=q.get('source');digest=q.get('source_sha256')
        else:
            _need(type(q.get('records'))is list and q['records'],'nonempty_received_reference_cleanup_records_required')
            selected=[r.get('footprint_uuid')for r in q['records']]
            binding=q.get('binding',{});declared=binding.get('source');digest=binding.get('source_sha256')
        _need(q.get('board_hint')==proposal['board_hint']and type(declared)is str
            and Path(declared).resolve(strict=True)==parent and digest==force._hash(parent),
            'each_cleanup_operation_must_bind_its_actual_saved_parent')
        _need(1<=len(selected)<=16 and all(type(u)is str and u for u in selected)
            and len(set(selected))==len(selected)and not owners.intersection(selected),
            'disjoint_literal_reference_cleanup_owners_required')
        owners.update(selected);kinds.append(kind);paths.update((child,request))
        resolved.append((kind,parent,child,request,q));cursor=child
    _need(cursor==candidate,'reference_cleanup_final_endpoint_required')
    return resolved


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],routing_admitted=False,current_qualified=False,
        release_authority=False,scope='bounded_saved_disjoint_reference_cleanup_only')
    try:
        _need(type(proposal)is dict and proposal.get('board_hint')==board_hint,'same_literal_reference_cleanup_board_required')
        epoch=force._code_identity();deps=dependencies()
        steps=validate(source,candidate,proposal)
        files={str(p):force._hash(p)for _,parent,child,request,_ in steps for p in(parent,child,request)}
        paths={p for _,a,b,_,_ in steps for p in(a,b)}
        families={str(p):force._family(p,board_hint)for p in paths}
        sidecars=force._sidecars(Path(source))
        _need(all(force._sidecars(p)==sidecars for p in paths),'reference_cleanup_sidecars_must_stay_exact')
        received=[]
        for kind,parent,child,request,q in steps:
            result=OPERATIONS[kind].receive(parent,child,q)
            received.append(dict(kind=kind,source=str(parent),candidate=str(child),receiving=result))
            _need(result.get('ok')is True and result.get('complete')is True,
                'independent_saved_reference_cleanup_refused:'+kind+':'+str(result.get('errors',result.get('error'))))
            _need(kind!='reference_map'or result.get('read_only_legacy_replay')is not True,
                'observational_legacy_map_cannot_authorize_reference_cleanup')
        _need(epoch==force._code_identity()and deps==dependencies()
            and all(force._hash(p)==h for p,h in files.items())
            and families=={str(p):force._family(p,board_hint)for p in paths},
            'reference_cleanup_sources_candidates_proposals_or_code_changed')
        r.update(ok=True,complete=True,steps=received,dependencies=deps,
            exact_saved_public_annotation_reconstruction=True,
            only_distinct_source_owned_references_and_associations_changed=True,
            no_parts_copper_masks_courtyards_rules_or_dimensions_changed=True,
            original_parent_whole_native_current_fields_contact_and_intake_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
