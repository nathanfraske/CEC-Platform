"""Close caller-declared placement cells over exact native terminal bindings.

This does not infer capacitor ownership from shared-rail proximity, refdes,
value or prose. Explicit validated design bindings are the caller's authority;
native pin/net/population consistency is checked before membership is returned.
Membership is placement search input, never copper-motion or release authority.
"""
from __future__ import annotations

import copy
import math
import time

MAX_BINDINGS = 256
MAX_REFS = 4096


def close(board, cells, bindings, *, context, timeout_s=2.):
    """Return a copy of cells with every explicitly bound support included.

Cells use ``refs: {context: [ref, ...]}``. An owner must already belong to
one cell or be a support resolved by another binding. Conflicting membership,
missing/foreign terminals, duplicate bindings, DNPs and cycles fail closed.
Bounds, poses and copper are not changed; they still need cooperative packing,
native contact/return reconstruction and independent saved-board receiving.
"""
    if (type(context) is not int or not 0 <= context <= 63
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or not isinstance(cells, dict) or not cells
            or not isinstance(bindings, (list, tuple)) or not 1 <= len(bindings) <= MAX_BINDINGS):
        raise ValueError('functional_cell_explicit_bounded_scope_required')
    deadline = time.monotonic() + timeout_s

    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('functional_cell_closure_deadline')

    fps = {}
    for fp in board.GetFootprints():
        tick()
        ref = str(fp.GetReference())
        if not ref or ref in fps or len(fps) >= MAX_REFS:
            raise ValueError('functional_cell_ambiguous_native_inventory')
        fps[ref] = fp
    result = copy.deepcopy(cells)
    owners = {}
    total = 0
    for key, cell in result.items():
        tick()
        if (type(key) is not str or not key or not isinstance(cell, dict)
                or not isinstance(cell.get('refs'), dict)):
            raise ValueError('functional_cell_explicit_cell_refs_required')
        refs = cell['refs'].get(context, [])
        if (not isinstance(refs, (list, tuple))
                or any(type(ref) is not str or not ref or ref not in fps for ref in refs)
                or len(set(refs)) != len(refs)):
            raise ValueError('functional_cell_stale_or_duplicate_cell_refs')
        cell['refs'][context] = list(refs)
        for ref in refs:
            total += 1
            if ref in owners or total > MAX_REFS:
                raise ValueError('functional_cell_conflicting_owner_membership')
            owners[ref] = key
    fields = {'support_ref', 'support_pin', 'owner_ref', 'owner_pin', 'net'}
    seen = set()
    checked = []
    for binding in bindings:
        tick()
        if (not isinstance(binding, dict) or set(binding) != fields
                or any(type(value) is not str or not value for value in binding.values())):
            raise ValueError('functional_cell_explicit_terminal_binding_required')
        support, owner = binding['support_ref'], binding['owner_ref']
        if support == owner or support in seen:
            raise ValueError('functional_cell_unique_distinct_support_required')
        seen.add(support)
        for ref, pin in ((support, binding['support_pin']), (owner, binding['owner_pin'])):
            fp = fps.get(ref)
            if fp is None or fp.IsDNP():
                raise ValueError('functional_cell_missing_or_dnp_member')
            pads = [pad for pad in fp.Pads() if str(pad.GetNumber()) == pin]
            if not pads or any(str(pad.GetNetname()) != binding['net'] or pad.GetNetCode() <= 0
                               or not pad.IsOnCopperLayer() for pad in pads):
                raise ValueError('functional_cell_native_terminal_net_mismatch')
        checked.append(dict(binding))
    dependencies = {binding['support_ref']: binding['owner_ref'] for binding in checked}
    for support in dependencies:
        chain = set()
        at = support
        while at in dependencies:
            tick()
            if at in chain:
                raise ValueError('functional_cell_binding_cycle')
            chain.add(at)
            at = dependencies[at]
    pending = list(checked)
    additions = []
    while pending:
        tick()
        unresolved = []
        for binding in pending:
            tick()
            support, owner = binding['support_ref'], binding['owner_ref']
            key = owners.get(owner)
            if key is None:
                unresolved.append(binding)
                continue
            if support in owners and owners[support] != key:
                raise ValueError('functional_cell_support_already_in_other_cell')
            if support not in owners:
                result[key]['refs'][context].append(support)
                owners[support] = key
                additions.append(dict(cell=key, context=context, **binding))
        if len(unresolved) == len(pending):
            raise ValueError('functional_cell_unresolved_owner_or_binding_cycle')
        pending = unresolved
    return dict(schema=1, cells=result, bindings=checked, additions=additions,
        native_binding_consistency_checked=True, inferred_ownership=False,
        copper_motion_admitted=False, routing_admitted=False, release_authority=False)
