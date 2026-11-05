"""Proof-bound signal-prefix transitions, carried with transactional PCB files.

The original owner stays immutable. A restored board therefore needs no
parallel mutable owner rollback: only a reachable receipt whose exact target
prefix matches the current board can replace the old pair obligation.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

SUFFIX = '.priority-replacements.json'
MAX_TRANSITIONS = 16


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def _pairs(contract):
    return {(r['name'],r['p'],r['n']) for r in contract.get('qualified_critical_pairs',())
            if r.get('qualified') is True}


def _validate_contract(contract):
    members=contract['members']; nets=contract['member_nets']
    if (contract.get('mode')!='locked_geometry_subset' or set(members)!=set(nets)
            or any(type(n) is not int or n<=0 for n in members.values())
            or contract.get('items')!=sum(members.values())
            or not set(nets.values())<=set(contract['nets'])
            or 'placement_power_nets' not in contract):
        raise ValueError('incomplete replacement prefix contract')
    if any(contract['items_by_net'].get(net,0)!=sum(
            count for member,count in members.items() if nets[member]==net)
           for net in set(contract['nets'])|set(contract['items_by_net'])):
        raise ValueError('replacement prefix counts disagree')


def _released_closure(source,nets):
    selected={p for p in _pairs(source) if {p[1],p[2]}&nets}
    closure={net for p in selected for net in p[1:]}
    if (not nets or closure!=nets or nets&set(source['placement_power_nets'])
            or not nets<=set(source.get('placement_preserved_nets',()))
            or not nets<=set(source['member_nets'].values())):
        raise ValueError('replacement is not a closed qualified signal scope')
    return selected


def _with_members(source,members,member_nets):
    target=copy.deepcopy(source)
    target.update(members=members,member_nets=member_nets,items=sum(members.values()),
        items_by_net={net:sum(n for key,n in members.items() if member_nets[key]==net)
                      for net in source['nets']})
    return target


def validate(receipt):
    if (receipt.get('schema')!=1 or receipt.get('kind')!='qualified-signal-prefix-transition'
            or receipt.get('accepted_proof') is not True
            or receipt.get('checksum')!=digest({k:v for k,v in receipt.items() if k!='checksum'})):
        raise ValueError('invalid replacement receipt')
    source,target=receipt['source_contract'],receipt['target_contract']
    _validate_contract(source);_validate_contract(target)
    nets=set(receipt['released_nets'])
    _released_closure(source,nets)
    # All non-geometry ownership metadata, including power classifications,
    # qualified-pair declarations and item-scoped return UUIDs, stays exact.
    mutable={'members','member_nets','items','items_by_net'}
    if {k:v for k,v in source.items() if k not in mutable}!={
            k:v for k,v in target.items() if k not in mutable}:
        raise ValueError('replacement changes ownership metadata')
    for net in set(source['nets'])-nets:
        old={k:v for k,v in source['members'].items() if source['member_nets'][k]==net}
        new={k:v for k,v in target['members'].items() if target['member_nets'][k]==net}
        if old!=new:raise ValueError('replacement changes retained copper')
    if not nets<=set(target['member_nets'].values()):
        raise ValueError('replacement omits a pair member')
    for key in ('source_board_sha256','accepted_board_sha256'):
        value=receipt.get(key,'')
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('replacement lacks artifact identity')
    return receipt


def issue(source_contract,plan,proof,board,*,source_board_sha256):
    """Seal only a rebuilt, physically admitted candidate before publication."""
    import cec_fr
    import cec_placement_route_prefix as prefix
    _validate_contract(source_contract)
    nets=set(plan.get('nets',()))
    selected=_released_closure(source_contract,nets)
    if (plan.get('ok') is not True or plan.get('replacement_required') is not True
            or selected!={(p['name'],p['p'],p['n']) for p in plan.get('pairs',())}
            or proof.get('ok') is not True or proof.get('constructed') is not True
            or set(proof.get('released_nets',()))!=nets
            or proof.get('placement_unchanged') is not True
            or proof.get('physical_ok') is not True
            or any(proof.get(key,{}).get('ok') is not True for key in
                   ('retained_prefix','all_original_pairs','authority'))):
        raise ValueError('replacement has no complete native acceptance proof')
    kept={k:v for k,v in source_contract['members'].items()
          if source_contract['member_nets'][k] not in nets}
    kept_nets={k:source_contract['member_nets'][k] for k in kept}
    retained=_with_members(source_contract,kept,kept_nets)
    if not cec_fr.check_copper_geometry_prefix(str(board),retained)['ok']:
        raise ValueError('retained copper changed before receipt issuance')
    if not prefix.check_qualified_pairs(str(board),source_contract)['ok']:
        raise ValueError('pair qualification changed before receipt issuance')
    replacement=cec_fr.copper_geometry_prefix_contract(str(board),nets)
    target=_with_members(source_contract,{**kept,**replacement['members']},
                         {**kept_nets,**replacement['member_nets']})
    receipt=dict(schema=1,kind='qualified-signal-prefix-transition',accepted_proof=True,
        source_contract=copy.deepcopy(source_contract),target_contract=target,
        released_nets=sorted(nets),source_board_sha256=source_board_sha256,
        accepted_board_sha256=hashlib.sha256(Path(board).read_bytes()).hexdigest())
    receipt['checksum']=digest(receipt)
    return validate(receipt)


def read(board):
    path=Path(board).with_suffix(SUFFIX)
    if not path.exists():return []
    payload=json.loads(path.read_text())
    rows=payload.get('transitions')
    if (payload.get('schema')!=1 or not isinstance(rows,list)
            or len(rows)>MAX_TRANSITIONS):
        raise ValueError('invalid or exhausted replacement history')
    return [validate(row) for row in rows]


def stage(source_board,target_board,receipt=None):
    """Carry the source history into a candidate's atomic artifact payload."""
    rows=copy.deepcopy(read(source_board))
    if receipt is not None:
        validate(receipt)
        if len(rows)>=MAX_TRANSITIONS:raise ValueError('replacement history budget exhausted')
        rows.append(copy.deepcopy(receipt))
    target=Path(target_board).with_suffix(SUFFIX)
    if rows:
        from cec_full_pipeline import atomic_json
        atomic_json(target,dict(schema=1,transitions=rows))
    elif target.exists():
        # Only this candidate's exact transactional sidecar is superseded.
        target.unlink()
    return dict(count=len(rows),new_receipt=receipt.get('checksum') if receipt else None)


def _extends(larger,smaller):
    """A source may include extra locks, but cannot weaken the earlier owner."""
    return (all(larger['members'].get(k,0)>=n and larger['member_nets'].get(k)==
                smaller['member_nets'][k] for k,n in smaller['members'].items())
            and set(smaller.get('placement_power_nets',()))<=set(larger['placement_power_nets'])
            and _pairs(smaller)<=_pairs(larger)
            and set(smaller.get('placement_preserved_uuids',()))<=
                set(larger.get('placement_preserved_uuids',())))


def resolve(board,original):
    """Find a source-reachable exact target; never infer authority from counts."""
    import cec_fr
    _validate_contract(original)
    candidates=[original]
    receipts=read(board)
    used=[]
    for receipt in receipts:
        if any(_extends(receipt['source_contract'],candidate) for candidate in candidates):
            candidates.append(receipt['target_contract']);used.append(receipt['checksum'])
    for candidate in reversed(candidates[1:]):
        evidence=cec_fr.check_copper_geometry_prefix(str(board),candidate)
        if evidence['ok']:
            return candidate,dict(ok=True,applicable=True,receipt_count=len(receipts),
                reachable_transitions=len(used),target_contract_sha256=digest(candidate))
    return original,dict(ok=False,applicable=bool(receipts),receipt_count=len(receipts),
        reachable_transitions=len(used),reason='no_verified_replacement_matches_current_copper')
