"""Retire stale endpoint width-exception membership, never native copper.

This explicit Source transaction only removes a selected, already-full-width
track from the existing endpoint-exception group. Each actual routing face
must independently satisfy its unchanged complete current AND class floor.
No lock, geometry, rule, current, or reconstruction permission is changed.
The independent saved receiver reconstructs the exact literal metadata delta.
"""
import json,math,re,time
from decimal import Decimal,ROUND_CEILING
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as current
import cec_source_literal_additions as literal
import cec_source_literal_group_retirement as spelling
import cec_source_retaining_ses_import as raw
import cec_native_rule_validity as rules

SCOPE='Source_full_current_endpoint_exception_membership_retirement'

def _encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def _stable(value):
    return json.loads(_encoded(value))

def _rule_scope(source,proofs,group_ids):
    """Membership must not also carry a stronger/functional custom rule."""
    path=source.with_suffix('.kicad_dru')
    if not path.is_file():return dict(custom_rule_file_present=False,matched_width_rule_count=0)
    text=path.read_text(encoding='utf-8');tokens=rules._tokens(text);roots=[];stack=[]
    for kind,value,_,_ in tokens:
        if kind=='(':
            node=[]
            (stack[-1]if stack else roots).append(node);stack.append(node)
        elif kind==')':
            if not stack:raise ValueError('bounded_existing_endpoint_custom_rules_required')
            stack.pop()
        else:
            if not stack:raise ValueError('bounded_existing_endpoint_custom_rules_required')
            stack[-1].append((kind,rules._decode(value)if kind=='string'else value))
    if stack:raise ValueError('bounded_existing_endpoint_custom_rules_required')
    floor=min(q['full_width_floor_nm']for q in proofs.values());matched=[]
    expected="A.Type == 'Track' && A.memberOfGroup('"+fr.ENDPOINT_NECKDOWN_GROUP+"')"
    for root in roots:
        if root==[('atom','version'),('atom','1')]:continue
        if not root or root[0]!=('atom','rule'):
            raise ValueError('unknown_existing_custom_rule_form_not_membership_authority')
        def leaves(node):
            for value in node:
                if type(value)is list:yield from leaves(value)
                else:yield value
        strings=[value for kind,value in leaves(root)if kind=='string']
        target=any(fr.ENDPOINT_NECKDOWN_GROUP in value or any(gid in value for gid in group_ids)for value in strings)
        for value in strings:
            if 'memberOfGroup'in value:
                # No wildcard, regex, computed group selector, escaping or
                # alternate expression may secretly cover the selected group.
                calls=re.findall(r"\b[AB]\.memberOfGroup\('([A-Za-z0-9 _:-]+)'\)",value)
                if len(calls)!=value.count('memberOfGroup'):
                    raise ValueError('unknown_or_pattern_group_rule_not_membership_authority')
        if not target:continue
        if (len(root)!=4 or root[:2]!=[('atom','rule'),('string','CEC guarded local endpoint neckdown')]
                or root[2]!=[('atom','condition'),('string',expected)]
                or type(root[3])is not list or len(root[3])!=3
                or root[3][:2]!=[('atom','constraint'),('atom','track_width')]
                or type(root[3][2])is not list or len(root[3][2])!=2
                or root[3][2][0]!=('atom','min')or root[3][2][1][0]!='atom'):
            raise ValueError('only_exact_existing_endpoint_width_exception_may_depend_on_membership')
        number=root[3][2][1][1]
        if not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?mm',number):
            raise ValueError('finite_existing_endpoint_width_exception_required')
        minimum=int((Decimal(number[:-2])*1000000).to_integral_value(rounding=ROUND_CEILING))
        if not 0<minimum<=floor:
            raise ValueError('endpoint_group_rule_must_not_exceed_actual_full_current_class_floor')
        matched.append(minimum)
    return dict(custom_rule_file_present=True,custom_rule_sha256=force._hash(path),
        matched_width_rule_count=len(matched),width_rule_minima_nm=matched,
        no_unknown_stronger_or_functional_group_dependent_rules=True)

def _lease(seconds):
    if type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10.:
        raise ValueError('bounded_full_width_endpoint_membership_lease_required')
    return time.monotonic()+seconds

def plan(source,track_uuids,*,board_hint,timeout_s=10.):
    deadline=_lease(timeout_s)
    if (type(track_uuids)not in(list,tuple)or not 1<=len(track_uuids)<=16
            or any(type(u)is not str or not u for u in track_uuids)
            or len(set(track_uuids))!=len(track_uuids)
            or type(board_hint)is not str or not board_hint):
        raise ValueError('finite_exact_full_width_endpoint_member_request_required')
    source=Path(source).resolve(strict=True);epoch=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));text=raw.raw_text(source);nodes,*_=literal._inventory(text)
    tracks={force._uid(t):t for t in board.GetTracks()};groups=list(board.Groups())
    if not set(track_uuids)<=tracks.keys():raise ValueError('actual_Source_endpoint_track_required')
    selected=set(track_uuids);proofs={};memberships={};models={}
    for uid in sorted(selected):
        if time.monotonic()>=deadline:raise ValueError('full_width_endpoint_membership_deadline')
        track=tracks[uid];owners=[g for g in groups if g.ContainsItem(track)]
        if (track.GetClass()!='PCB_TRACK'or not 0<track.GetLength()<=32000000
                or track.HasSolderMask()or len(owners)!=1):
            raise ValueError('plain_uniquely_grouped_Source_endpoint_track_required')
        group=owners[0];gid=force._uid(group);members=list(group.GetItems())
        if (group.GetName()!=fr.ENDPOINT_NECKDOWN_GROUP or group.IsLocked()or group.GetParentGroup()
                or sum(g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP for g in groups)!=1
                or any(g.ContainsItem(group)for g in groups)or not 1<len(members)<=512
                or any(i.GetClass()not in('PCB_TRACK','PCB_ARC')for i in members)
                or gid not in nodes or literal.kind(nodes[gid][2])!='group'
                or set(literal._members(nodes[gid][2])[1])!={force._uid(i)for i in members}
                or uid not in nodes or literal.kind(nodes[uid][2])!='segment'):
            raise ValueError('actual_unlocked_unnested_Source_endpoint_exception_group_required')
        net=track.GetNetname();face=int(track.GetLayer())
        if net not in models:models[net]=current._model(board,source,net,board_hint)
        kind,domain,contract=models[net];floor=current._source_width_floor(board,source,contract,face)
        if track.GetWidth()<floor:
            raise ValueError('actual_Source_track_must_already_meet_whole_current_and_class_floor')
        proofs[uid]=dict(net=net,layer_id=face,width_nm=int(track.GetWidth()),full_width_floor_nm=floor,
            Source_track_locked=bool(track.IsLocked()),current_model_kind=kind,
            Source_current_domain=domain,unchanged_whole_current_contract=contract)
        memberships.setdefault(gid,[]).append(uid)
    for gid,values in memberships.items():
        if not set(values)<set(literal._members(nodes[gid][2])[1]):
            raise ValueError('partial_membership_retirement_cannot_drop_the_Source_group')
    rule_scope=_rule_scope(source,proofs,memberships)
    if (time.monotonic()>=deadline or family!=force._family(source,board_hint)
            or epoch!=force._code_identity()or text!=raw.raw_text(source)):
        raise ValueError('Source_full_width_endpoint_context_changed_or_expired')
    return _stable(dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),
        source_family=family,code_identity=epoch,board_hint=board_hint,track_uuids=sorted(selected),
        group_member_retirements=memberships,actual_full_width_Source_members=proofs,
        Source_group_rule_scope=rule_scope,
        copper_retired=False,geometry_changed=False,locks_changed=False,rules_changed=False,
        native_rule_execution_and_whole_chain_receiving_still_required=True,
        routing_admitted=False,current_qualified=False,release_authority=False))

def _fresh(source,proposal,timeout_s):
    if type(proposal)is not dict or proposal.get('scope')!=SCOPE:
        raise ValueError('typed_full_width_endpoint_membership_proposal_required')
    fresh=plan(source,proposal['track_uuids'],board_hint=proposal['board_hint'],timeout_s=timeout_s)
    if _encoded(fresh)!=_encoded(proposal):raise ValueError('stale_or_forged_full_width_endpoint_membership_proposal')
    return fresh

def _project(text,proposal):
    nodes,*_=literal._inventory(text);result=text
    for gid in sorted(proposal['group_member_retirements'],key=lambda u:nodes[u][0],reverse=True):
        a,b,node=nodes[gid]
        result=result[:a]+spelling._drop_members(node,set(proposal['group_member_retirements'][gid]))+result[b:]
    projected,*_=literal._inventory(result)
    changed=set(proposal['group_member_retirements'])
    if (projected.keys()!=nodes.keys()or any(projected[u][2]!=nodes[u][2]for u in nodes if u not in changed)):
        raise ValueError('endpoint_membership_projection_changed_unowned_Source_material')
    return result

def receive(source,candidate,proposal,*,timeout_s=10.):
    deadline=_lease(timeout_s);report=dict(ok=False,complete=False,errors=[],routing_admitted=False,
        current_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_membership_candidate_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        q=_fresh(source,proposal,max(.001,deadline-time.monotonic()))
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('endpoint_membership_sidecars_changed')
        if raw.raw_text(candidate)!=_project(raw.raw_text(source),q):
            raise ValueError('exact_saved_Source_membership_only_replay_required')
        board=pcbnew.LoadBoard(str(candidate));live={force._uid(t):t for t in board.GetTracks()};models={}
        for uid,proof in q['actual_full_width_Source_members'].items():
            track=live[uid];net=proof['net']
            if net not in models:models[net]=current._model(board,candidate,net,q['board_hint'])
            kind,domain,contract=models[net]
            if (_encoded((kind,domain,contract))!=_encoded((proof['current_model_kind'],proof['Source_current_domain'],
                    proof['unchanged_whole_current_contract']))
                    or current._source_width_floor(board,candidate,contract,int(track.GetLayer()))!=proof['full_width_floor_nm']
                    or track.GetWidth()<proof['full_width_floor_nm']or track.GetParentGroup()is not None):
                raise ValueError('saved_full_current_and_class_membership_retirement_not_rederived')
        if _encoded(_rule_scope(candidate,q['actual_full_width_Source_members'],q['group_member_retirements']))!=_encoded(q['Source_group_rule_scope']):
            raise ValueError('saved_endpoint_group_rule_scope_not_rederived')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,q['board_hint'])for p in(source,candidate)]):
            raise ValueError('endpoint_membership_saved_Source_context_changed_or_expired')
        report.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            exact_literal_membership_only_replay=True,all_native_copper_parts_locks_and_rules_unchanged=True,
            current_and_class_rederived_on_actual_saved_candidate=True,
            no_group_unlock_or_current_exception_granted=True,
            native_rule_execution_and_whole_chain_receiving_still_required=True,
            later_geometry_changes_require_separate_typed_receiving=True)
    except(ValueError,RuntimeError,TypeError,KeyError,OSError)as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    return report

def construct(source,directory,proposal,*,timeout_s=10.):
    _lease(timeout_s);source=Path(source).resolve(strict=True);directory=Path(directory).resolve()
    if directory.exists():raise ValueError('fresh_private_membership_candidate_required')
    q=_fresh(source,proposal,timeout_s);target=force._copy_family(source,directory)
    raw.write_raw(target,_project(raw.raw_text(source),q))
    proof=receive(source,target,q,timeout_s=timeout_s)
    return dict(candidate=str(target),candidate_sha256=force._hash(target),receiving=proof,
        ok=proof['ok'],complete=proof['complete'],routing_admitted=False,release_authority=False)
