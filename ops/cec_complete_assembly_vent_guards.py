"""Complete missing native vent guards on an exact saved assembly instance.

Only a clear, already-fitting vent projection may receive an additional rule
area. No existing copper, bodies, footprints, rules or outlines are changed.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet = wx.LogNull()
import pcbnew
import cec_assembly_envelope as envelope
import cec_assembly_instance as instance
import cec_field_coupling as field
import cec_force_current as force

ROOT = Path(__file__).resolve().parents[1]


def complete(source, context, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('fresh private output required')
    bound = instance.resolve(source, context, ROOT)
    family = force._family(source)
    epoch = force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    before = field._field_snapshot_inventory(board)
    check = instance.check(board, source, context, ROOT)
    if (check.get('missing') or check.get('violations') or not check['vertical']['ok']
            or not check['authority_unchanged']
            or not all(row['ok'] for row in check['contacts'])
            or not all(row['ok'] for row in check['hardware'])):
        raise ValueError('contact/body/hardware/vertical assembly faults must be resolved first')
    if any(row['copper_hits'] for row in check['vent_reservations']):
        raise ValueError('vent region contains actual native copper')
    role = bound['role']
    missing = {row['ref'] for row in check['vent_reservations']
               if row['receiver'] == role and not row['native_rule_covers']}
    if not missing:
        raise ValueError('no missing guard on this receiving member')
    contract = json.loads(bound['paths']['contract'].read_text())
    vents = [row for row in envelope.facing_vents(check, contract, role) if row['ref'] in missing]
    if {row['ref'] for row in vents} != missing:
        raise ValueError('complete missing native vent projection required')
    envelope.vent_reservations(board, vents, install=True)
    after = field._field_snapshot_inventory(board)
    added = set(after) - set(before)
    if (not added or any(key[0] != 'zone' for key in added)
            or any(key not in after or after[key] != value for key, value in before.items())):
        raise ValueError('guard completion changed existing native material')
    candidate = force._copy_family(source, out)
    pcbnew.SaveBoard(str(candidate), board)
    saved = pcbnew.LoadBoard(str(candidate))
    if field._field_snapshot_inventory(saved) != after:
        raise ValueError('saved guard-only native snapshot mismatch')
    new_context = copy.deepcopy(context)
    new_context['members'][role] = dict(path=str(candidate), sha256=force._hash(candidate))
    received = instance.check(saved, candidate, new_context, ROOT)
    if not received['ok']:
        raise ValueError('completed saved assembly still fails physical checks')
    if (epoch != force._code_identity() or family != force._family(source)
            or any(instance.digest(path) != bound['hashes'][key] for key, path in bound['paths'].items())):
        raise ValueError('source or assembly authority changed during guard construction')
    report = dict(schema=1, ok=True, source=str(source), source_sha256=force._hash(source),
                  candidate=str(candidate), candidate_sha256=force._hash(candidate),
                  missing_guards_completed=sorted(missing), added_rule_uuids=sorted(key[1] for key in added),
                  all_existing_native_items_exact=True, new_assembly_instance=new_context,
                  saved_assembly=received, code_identity=epoch,
                  tool_sha256=force._hash(Path(__file__)),
                  routing_admitted=False, fab_ready=False, release_authority=False)
    force._write(out / 'vent-guard-receipt.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--instance-json', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = complete(args.source, json.loads(args.instance_json.read_text()), args.out)
    print(json.dumps({key: value for key, value in result.items()
                      if key in ('ok', 'candidate', 'candidate_sha256', 'missing_guards_completed',
                                 'all_existing_native_items_exact')}), flush=True)
