"""Exact active experimental draft selection; never a rating/release gate.

Agent construction and publication must use the designated native draft or
its explicitly source-bound descendant, not whichever older sibling has a
more convenient receipt. All board identities and paths come from caller data.
"""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(path, repo):
    value = Path(path)
    return (value if value.is_absolute() else Path(repo)/value).resolve()


def unique_object(pairs):
    """An authoritative key cannot silently be overwritten by a later copy."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_authoritative_json_key:' + key)
        result[key] = value
    return result


def load(path, *, repo):
    path = resolve(path,repo)
    value = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if value.get('schema') != 1 or not isinstance(value.get('boards'),dict) or not 1 <= len(value['boards']) <= 64:
        raise ValueError('bounded_explicit_draft_frontier_required')
    return dict(path=str(path),sha256=digest(path),repo=str(Path(repo).resolve()),state=value)


def selected(frontier, hint):
    row = frontier['state']['boards'].get(hint)
    if not isinstance(row,dict):
        raise ValueError('draft_frontier_board_identity_absent')
    receipt = resolve(row['construction'],frontier['repo'])
    producer = json.loads(receipt.read_text(), object_pairs_hook=unique_object)
    if producer.get('errors') or not producer.get('candidate'):
        raise ValueError('draft_frontier_failed_or_missing_construction')
    board = resolve(producer['candidate'],frontier['repo'])
    actual = digest(board)
    if actual != producer.get('candidate_sha256') or actual != row.get('candidate_sha256'):
        raise ValueError('draft_frontier_native_identity_changed')
    return dict(board=str(board),sha256=actual,construction=str(receipt),
        construction_sha256=digest(receipt),board_hint=hint,
        experimental_working_geometry=True,qualification_granted=False,release_authority=False)


def require(frontier,hint,producer,*,allow_descendant=False):
    wanted = selected(frontier,hint)
    keys = ('candidate','source') if allow_descendant else ('candidate',)
    matches = [key for key in keys if producer.get(key)
        and resolve(producer[key],frontier['repo']) == Path(wanted['board'])
        and producer.get(key+'_sha256') == wanted['sha256']]
    if not matches:
        raise ValueError('superseded_or_unrelated_experimental_draft_refused')
    return dict(wanted,matched_receipt_field=matches[0],frontier_sha256=frontier['sha256'])


def unchanged(frontier):
    return digest(frontier['path']) == frontier['sha256']
