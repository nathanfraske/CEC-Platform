"""Reconcile missing membership in an EXISTING scoped filled/capped via rule.

Only a private proposal is written. No dimensions, copper, poses, process flags
or rules change. Independently prove each incoming live SMD owner and the exact
literal saved delta, then require complete native-error nonregression.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet = wx.LogNull()
import pcbnew
import cec_additive_route_receiving as literal
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native


def existing_rule_geometry(text):
    start, end = fr.LOCAL_POFV_SIGNAL_VIA_RULE_BEGIN, fr.LOCAL_POFV_SIGNAL_VIA_RULE_END
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('one existing scoped local-via rule required; no new rule permitted')
    block = text.split(start, 1)[1].split(end, 1)[0]
    block = '\n'.join(line for line in block.splitlines() if not line.lstrip().startswith('#'))
    rule = syntax._parse(syntax._TOKEN.findall(block))
    condition = next((row[1].strip('"') for row in rule
                      if isinstance(row, list) and row and row[0] == 'condition'), None)
    expected = "A.Type == 'Via' && A.memberOfGroup('%s')" % fr.LOCAL_POFV_SIGNAL_VIA_GROUP
    if condition != expected:
        raise ValueError('existing local-via rule has a different scope')
    values = {}
    for row in rule:
        if not isinstance(row, list) or not row or row[0] != 'constraint':
            continue
        if (len(row) != 3 or not isinstance(row[2], list) or len(row[2]) != 2
                or row[2][0] != 'min' or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?mm', row[2][1])):
            raise ValueError('explicit mm minima required for existing local-via rule')
        if row[1] in values:
            raise ValueError('ambiguous existing local-via constraint')
        values[row[1]] = float(row[2][1][:-2])
    if set(values) != {'via_diameter', 'hole_size', 'annular_width'} or min(values.values()) <= 0:
        raise ValueError('complete existing local-via geometry required')
    return values


def filled_and_capped(board, via):
    settings = board.GetDesignSettings()
    return (
        via.GetFillingMode() == pcbnew.FILLING_MODE_FILLED
        or via.GetFillingMode() == pcbnew.FILLING_MODE_FROM_BOARD and settings.m_FillVias
    ) and (
        via.GetCappingMode() == pcbnew.CAPPING_MODE_CAPPED
        or via.GetCappingMode() == pcbnew.CAPPING_MODE_FROM_BOARD and settings.m_CapVias)


def eligible(board, via, limits, cache):
    if not via.IsLocked():
        return False, 'unlocked source object; this actuator cannot change locks'
    if any(group.ContainsItem(via) for group in board.Groups()):
        return False, 'another or existing group already owns the via'
    if not filled_and_capped(board, via):
        return False, 'actual via does not inherit or select filled/capped processing'
    diameter, drill = via.GetWidth(via.TopLayer())/1e6, via.GetDrillValue()/1e6
    if (diameter < limits['via_diameter']-1e-9 or drill < limits['hole_size']-1e-9
            or (diameter-drill)/2 < limits['annular_width']-1e-9):
        return False, 'via does not meet the unchanged existing scoped rule'
    return fab.local_pofv_via_decision(board, via, cache=cache)


def literal_group_extension(source, candidate, group_uuid, added):
    old_root, old = literal._nodes(source)
    new_root, new = literal._nodes(candidate)
    if old.keys() != new.keys():
        raise ValueError('membership reconciliation added/removed a native item')
    changed = {uid for uid in old if syntax._freeze(old[uid]) != syntax._freeze(new[uid])}
    if changed != {group_uuid}:
        raise ValueError('unrelated literal native change: '+str(sorted(changed)))
    a, b = old[group_uuid], new[group_uuid]
    if (a[0] != 'group' or literal._without(a, 'members') != literal._without(b, 'members')
            or literal._members(b) != literal._members(a) | set(added)
            or literal._members(a) & set(added)):
        raise ValueError('not an exact extension of the existing local-via group')
    # Also bind non-UUID data such as setup, process flags and board properties.
    def header(root):
        return syntax._freeze([node for node in root[1:] if not (
            isinstance(node, list) and any(isinstance(row, list) and row
                and row[0] == 'uuid' for row in node[1:]))])
    if header(old_root) != header(new_root):
        raise ValueError('non-object board setup or properties changed')
    return dict(unchanged_native_uuid_blocks=len(old)-1, changed_group_uuid=group_uuid,
                added_existing_via_uuids=sorted(added), all_native_geometry_and_fields_literal=True)


def _errors(raw):
    return Counter((row['type'], tuple(sorted(item['uuid'] for item in row['items'])))
                   for row in raw['violations'] if row['severity'] == 'error')


def propose(source, out, *, board_hint, reporting_build):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('fresh private proposal directory required')
    family, epoch = force._family(source, board_hint), force._code_identity()
    helper_sha256 = force._hash(Path(__file__))
    rules = source.with_suffix('.kicad_dru')
    limits = existing_rule_geometry(rules.read_text())
    board = pcbnew.LoadBoard(str(source))
    profile = fab.get_profile(fab.board_profile_name(board))
    if profile.get('pofv') is not True:
        raise ValueError('selected existing POFV process required')
    groups = [g for g in board.Groups() if g.GetName() == fr.LOCAL_POFV_SIGNAL_VIA_GROUP]
    if len(groups) != 1:
        raise ValueError('one existing exact local-via group required')
    cache = {}
    for via in groups[0].GetItems():
        if (via.GetClass() != 'PCB_VIA' or not filled_and_capped(board, via)
                or fab.local_pofv_via_decision(board, via, cache=cache)[0] is not True):
            raise ValueError('inherited group has unresolved qualification debt')
    candidate = force._copy_family(source, out)
    producer = native.run(candidate, out/'native-before.json', reporting_build=reporting_build, timeout_s=10.)
    if not producer.get('ok') or not producer.get('complete'):
        raise ValueError('complete native source measurement required: '+str(producer.get('errors')))
    raw = json.loads(Path(producer['report']).read_text())
    selected = {item['uuid'] for row in raw['violations']
                if row['severity'] == 'error' and row['type'] in ('via_diameter', 'annular_width')
                for item in row['items']}
    tracks = {force._uid(item): item for item in board.GetTracks()}
    if not 0 < len(selected) <= 512:
        raise ValueError('bounded native dimension-error object set required')
    accepted, evidence = [], []
    for uid in sorted(selected):
        via = tracks.get(uid)
        if via is None or via.GetClass() != 'PCB_VIA':
            continue
        ok, reason = eligible(board, via, limits, cache)
        evidence.append(dict(uuid=uid, ok=ok, reason=reason))
        if ok:
            accepted.append(via)
    if not accepted:
        raise ValueError('no native-error via eligible under unchanged existing rules')
    before = field._field_snapshot_inventory(board)
    group_uuid = force._uid(groups[0])
    grouping = fr.group_local_pofv_signal_vias(board, accepted)
    if grouping is None or field._field_snapshot_inventory(board) != before:
        raise ValueError('reconciliation changed material or locks')
    field._save_field_snapshot(board, candidate)
    exact = literal_group_extension(source, candidate, group_uuid,
                                    {force._uid(v) for v in accepted})
    if force._hash(rules) != force._hash(candidate.with_suffix('.kicad_dru')):
        raise ValueError('native rules changed')
    after_producer = native.run(candidate, out/'native-after.json',
                                reporting_build=reporting_build, timeout_s=10.)
    if not after_producer.get('ok') or not after_producer.get('complete'):
        raise ValueError('complete saved native child measurement required')
    child = json.loads(Path(after_producer['report']).read_text())
    if (_errors(child)-_errors(raw) or len(child['unconnected_items']) != len(raw['unconnected_items'])
            or sum(_errors(child).values()) >= sum(_errors(raw).values())):
        raise ValueError('saved native error/open nonregression refused')
    if (epoch != force._code_identity() or family != force._family(source, board_hint)
            or helper_sha256 != force._hash(Path(__file__))):
        raise ValueError('source family or engine changed')
    result = dict(schema=1, source=str(source), source_sha256=force._hash(source),
        candidate=str(candidate), candidate_sha256=force._hash(candidate), code_identity=epoch,
        helper_sha256=helper_sha256,
        existing_rule_geometry=limits, incoming_native_qualification=evidence, literal_receiving=exact,
        source_native_producer=producer, child_native_producer=after_producer,
        native_errors_before=sum(_errors(raw).values()), native_errors_after=sum(_errors(child).values()),
        opens_before=len(raw['unconnected_items']), opens_after=len(child['unconnected_items']),
        source_and_engine_unchanged=True, physical_geometry_changed=False, rules_changed=False,
        routing_admitted=False, fab_ready=False, release_authority=False)
    force._write(out/'receipt.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--board-hint', required=True)
    parser.add_argument('--reporting-build', type=Path, required=True)
    args = parser.parse_args()
    result = propose(args.source, args.out, board_hint=args.board_hint, reporting_build=args.reporting_build)
    print(json.dumps({key: result[key] for key in ('candidate','candidate_sha256','native_errors_before',
        'native_errors_after','opens_before','opens_after','physical_geometry_changed','rules_changed')}), flush=True)
