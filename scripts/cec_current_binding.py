"""Bind declared current paths to native nets without inventing electrical loads.

Names are preferred. An absent name may be recovered only from one common net
of the complete declared endpoint sets. Candidate banks are alternatives, not
required terminals. This is netlist identity, never proof of connected copper.
"""
from __future__ import annotations

import math


class CurrentBindingError(ValueError):
    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__("current authority binding failed: " + "; ".join(
            f"{row['configured_net']}: {row['reason']}"
            for row in evidence['issues']))


def _name_matches(name, nets):
    if name in nets:
        return [name]
    suffix = "/" + name.lstrip("/")
    return sorted(n for n in nets if n.endswith(suffix)
                  or suffix.endswith("/" + n.lstrip("/")))


def resolve(board, currents, overrides=None):
    """Return current/override copies plus auditable original-to-native bindings.

    Missing names, conflicting aliases, absent required endpoints and ambiguous
    endpoint identity raise with structured evidence. There is no summing or
    last-writer-wins for two current contracts mapped to the same conductor.
    Existing native names without endpoint overrides keep legacy auto-selection.
    """
    currents, overrides = dict(currents or {}), dict(overrides or {})
    nets = {str(info.GetNetname())
            for _, info in board.GetNetInfo().NetsByNetcode().items()
            if info.GetNetname()}
    by_ref, duplicate_refs = {}, set()
    for fp in board.GetFootprints():
        ref = str(fp.GetReference() or "")
        if ref in by_ref:
            duplicate_refs.add(ref)
        by_ref.setdefault(ref, set()).update(
            str(p.GetNetname()) for p in fp.Pads() if p.GetNetname())
    bound, selected, bindings, issues = {}, {}, {}, []
    for configured, amps in currents.items():
        name = str(configured)
        row = dict(configured_net=name, amps=amps, actual_net=None)
        bindings[name] = row

        def refuse(reason):
            row['reason'] = reason
            issues.append(dict(row))

        if not name or not math.isfinite(float(amps)) or float(amps) < 0:
            refuse('invalid_current_contract')
            continue
        matches = _name_matches(name, nets)
        if len(matches) > 1:
            row['candidate_nets'] = matches
            refuse('ambiguous_hierarchical_name')
            continue
        actual = matches[0] if matches else None
        override_keys = [key for key in overrides
                         if key == name or (actual is not None
                         and _name_matches(str(key), nets) == [actual])]
        values = [overrides[key] for key in override_keys]
        if values and any(value != values[0] for value in values[1:]):
            refuse('conflicting_endpoint_overrides')
            continue
        override = values[0] if values else None
        row['override_keys'] = sorted(override_keys)
        required, candidates = {}, {}
        if isinstance(override, dict):
            # A configuration adapter may already have renamed its current
            # key. Retain the declared design-rule identity independently of
            # the thermal scenario's numerical current and native key.
            row['design_current_net'] = str(override.get('design_current_net') or name)
            for side in ('src', 'sink'):
                required[side] = {str(r) for r in (override.get('refs_' + side) or ()) if r}
                candidates[side] = {str(r) for r in
                    (override.get('refs_' + side + '_candidates') or ()) if r}
            refs = set.union(*required.values())
            all_refs = refs | set.union(*candidates.values())
            row['missing_refs'] = sorted(refs - by_ref.keys())
            row['duplicate_refs'] = sorted(all_refs & duplicate_refs)
            if row['missing_refs'] or row['duplicate_refs']:
                refuse('missing_or_duplicate_endpoint_reference')
                continue
            if actual is None:
                possible = set(nets)
                for side in ('src', 'sink'):
                    if required[side]:
                        for ref in required[side]:
                            possible &= by_ref[ref]
                    elif candidates[side]:
                        possible &= set().union(*(by_ref.get(r, set())
                                                  for r in candidates[side]))
                    else:
                        possible.clear()
                row['candidate_nets'] = sorted(possible)
                if len(possible) != 1:
                    refuse('endpoint_net_ambiguous' if possible else 'endpoint_net_unresolved')
                    continue
                actual = next(iter(possible))
            present = {r for r, own in by_ref.items() if actual in own}
            off_net = set.union(*required.values()) - present
            chosen = {side: (required[side] | candidates[side]) & present
                      for side in ('src', 'sink')}
            row.update(source_refs=sorted(chosen['src']), sink_refs=sorted(chosen['sink']),
                       off_net_required_refs=sorted(off_net))
            if off_net or not chosen['src'] or not chosen['sink']:
                refuse('incomplete_endpoint_authority')
                continue
            if not matches and chosen['src'] & chosen['sink']:
                refuse('overlapping_alias_endpoints')
                continue
            # Both routing and FEM consume the same resolved candidate bank.
            override = dict(override, refs_src=sorted(chosen['src']),
                            refs_sink=sorted(chosen['sink']))
        if actual is None:
            refuse('native_net_absent_without_endpoint_proof')
            continue
        # An override already keyed by the recovered name must not disagree
        # with the one that supplied its electrical identity.
        if not matches and actual in overrides and overrides[actual] != values[0]:
            refuse('conflicting_endpoint_overrides')
            continue
        row.update(actual_net=actual, resolution=(
            'exact_name' if actual == name else
            'hierarchical_name' if matches else 'unique_endpoint_net'))
        if actual in bound:
            refuse('multiple_current_contracts_for_native_net')
            continue
        bound[actual] = float(amps)
        if override is not None:
            selected[actual] = override
    evidence = dict(bindings=bindings, issues=issues, ok=not issues,
                    copper_connectivity_proved=False)
    if issues:
        raise CurrentBindingError(evidence)
    return bound, selected, evidence
