"""Exact known-debt scheduling, never a release or DRC waiver."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,
        separators=(',',':')).encode()).hexdigest()


def _valid_snapshot(grade):
    snapshot=grade.get('mutation_snapshot')
    if not isinstance(snapshot,dict):return False
    count=grade.get('drc');opens=grade.get('unconnected')
    if (type(count) is not int or not 0<=count<=64
            or type(opens) is not int or not 0<=opens<=128
            or snapshot.get('drc')!=count or snapshot.get('unconnected')!=opens
            or grade.get('native_structural_violation_count')!=count):return False
    identities=snapshot.get('structural_drc_identities')
    if (not isinstance(identities,list) or any(not isinstance(x,str) for x in identities)
            or len(set(identities))!=count
            or len(identities)!=count):return False
    types=Counter()
    try:
        for identity in identities:
            row=json.loads(identity)
            if (not isinstance(row,list) or len(row)!=3 or row[1]!='uuid'
                    or not isinstance(row[0],str) or not row[0]
                    or not isinstance(row[2],list) or not row[2]
                    or any(not isinstance(uid,str) or not uid for uid in row[2])):return False
            types[row[0]]+=1
    except (ValueError,TypeError):return False
    return dict(types)==snapshot.get('drc_types')


def bind(grade,*,family,params_sha256,code_sha256):
    if not _valid_snapshot(grade):return None
    path=Path(grade['routed']).resolve()
    return dict(schema=1,kind='native_existing_debt_work_receipt',board=str(path),
        board_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        artifacts=family,params_sha256=params_sha256,code_sha256=code_sha256,
        snapshot_sha256=digest(grade['mutation_snapshot']),read_only=True,
        release_authority=False)


def verified(grade,*,params_sha256,code_sha256,artifacts_match):
    receipt=grade.get('repair_debt_receipt') or {}
    try:
        path=Path(grade['routed']).resolve()
        return bool(_valid_snapshot(grade) and receipt.get('schema')==1
            and receipt.get('kind')=='native_existing_debt_work_receipt'
            and receipt.get('read_only') is True and receipt.get('release_authority') is False
            and receipt.get('board')==str(path)
            and receipt.get('board_sha256')==hashlib.sha256(path.read_bytes()).hexdigest()
            and receipt.get('params_sha256')==params_sha256
            and receipt.get('code_sha256')==code_sha256
            and receipt.get('snapshot_sha256')==digest(grade['mutation_snapshot'])
            and receipt.get('artifacts') and artifacts_match(receipt['artifacts']))
    except (OSError,ValueError,TypeError,KeyError):return False


def admit(before,after):
    import cec_stage_admission
    if not (_valid_snapshot(before) and _valid_snapshot(after)):
        return dict(accepted=False,decision='complete_native_debt_identity_required')
    result=cec_stage_admission.evaluate(before['mutation_snapshot'],
        after['mutation_snapshot'],require_strict=True)
    if after['unconnected']>=before['unconnected']:
        result.update(accepted=False,decision='strict_open_reduction_required')
    result['release_authority']=False
    return result
