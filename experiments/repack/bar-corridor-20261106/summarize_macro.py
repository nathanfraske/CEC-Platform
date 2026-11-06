"""Summarize an independently received private macro; never grant release."""
import argparse
import json
from pathlib import Path
import cec_force_current as force
import cec_additive_route_receiving as ast


def load(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def evidence_bindings(checks, source, candidate):
    macro=checks.get('macro',{}); current=checks.get('current',{}); native=checks.get('native_drc',{})
    files=native.get('source_files',{})
    required=[candidate,candidate.with_suffix('.kicad_pro'),candidate.with_suffix('.kicad_dru')]
    return dict(macro_saved_hashes=macro.get('source_sha256')==force._hash(source) and macro.get('candidate_sha256')==force._hash(candidate),
                native_saved_family=native.get('ok') is True and native.get('complete') is True and all(p.is_file() and files.get(str(p))==force._hash(p) for p in required) and all(Path(p).is_file() and force._hash(Path(p))==h for p,h in files.items()),
                current_complete_stable=current.get('complete') is True and current.get('source_candidate_and_code_unchanged') is True)


def summarize(folder):
    folder = Path(folder).resolve()
    plan = load(folder/'route-plan.json')
    source = Path(plan['source']).resolve()
    candidate = Path(plan['candidate']).resolve()
    packet = load(folder/'packet.json')
    checks = load(folder/'independent-receiving.json')
    drc = load(folder/'native-drc.json')
    old, new = ast._nodes(source)[1], ast._nodes(candidate)[1]
    def net(node):
        return next((p[1].strip('"') for p in node if isinstance(p,list) and p and p[0]=='net'),'')
    zones = {u:n for u,n in old.items() if n[0]=='zone' and net(n)!='GND'}
    def outline(nodes):
        return {u:n for u,n in nodes.items() if any(isinstance(p,list) and p and p[0]=='layer' and p[1].strip('"')=='Edge.Cuts' for p in n)}
    old_vias = {u for u,n in old.items() if n[0]=='via'}
    new_vias = {u for u,n in new.items() if n[0]=='via'}
    macro, current, partitions = (checks.get(k,{}) for k in ('macro','current','partitions'))
    counts = dict(errors=sum(v.get('severity')=='error' for v in drc.get('violations',[])),
                  warnings=sum(v.get('severity')=='warning' for v in drc.get('violations',[])),
                  opens=len(drc.get('unconnected_items',[]))) if 'violations' in drc and 'unconnected_items' in drc else None
    gates = dict(macro=macro.get('ok') is True and macro.get('complete') is True,
                 current_nonregression=current.get('ok') is True,
                 partitions=partitions.get('preserved') is True and not partitions.get('demoted_parts'),
                 native=counts is not None and counts['errors']==0 and counts['opens']==0,
                 source_hash=plan.get('sha256',plan.get('source_sha256'))==force._hash(source),
                 non_ground_zone_ASTs=all(new.get(u)==n for u,n in zones.items()) and {u for u,n in new.items() if n[0]=='zone' and net(n)!='GND'}==set(zones),
                 exact_outline=bool(outline(old)) and outline(old)==outline(new),
                 no_new_barrels=not(new_vias-old_vias),
                 all_obligations_present_and_resolved=bool(packet.get('requests')) and 'unresolved' in plan and not plan['unresolved'],
                 trace_craft_nonregression=isinstance(macro.get('trace_craft_before_after'),list) and len(macro['trace_craft_before_after'])==2 and macro['trace_craft_before_after'][1]<=macro['trace_craft_before_after'][0])
    gates.update(evidence_bindings(checks,source,candidate))
    manifest = dict(schema=1, source=str(source),source_sha256=force._hash(source),candidate=str(candidate),candidate_sha256=force._hash(candidate),
                    source_sidecars=force._sidecars(source),candidate_sidecars=force._sidecars(candidate),
                    board_family_files=[dict(name=f.name,sha256=force._hash(f),bytes=f.stat().st_size,
                        source_sha256=force._hash(source.parent/f.name) if (source.parent/f.name).is_file() else None,
                        source_exact=f.read_bytes()==(source.parent/f.name).read_bytes() if (source.parent/f.name).is_file() else False)
                        for f in sorted(candidate.parent.glob(candidate.stem+'.*')) if f.is_file()],release_authority=False)
    manifest_path=folder/'family-manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    out=dict(schema=1,status='private_native_macro_RECEIVED_NOT_RELEASED' if all(gates.values()) else 'private_native_macro_FAILED_OR_INCOMPLETE',
             source=str(source),source_sha256=force._hash(source),candidate=str(candidate),candidate_sha256=force._hash(candidate),board_hint=plan.get('board_hint'),
             gates=gates,failed_or_missing_gates=[k for k,v in gates.items() if not v],
             obligations=dict(mandatory=len(packet.get('requests',{})) if 'requests' in packet else None,
                              planned_resolved=len(plan.get('routed',[])),unresolved=len(plan.get('unresolved',[])),
                              independently_all_received=gates['macro']),
             native=counts,macro=dict(ok=macro.get('ok'),complete=macro.get('complete'),errors=macro.get('errors')),
             current={k:current.get(k) for k in ('ok','before_fault_objects','after_fault_objects','new_faults','worsened_faults','errors')},
             partitions={k:partitions.get(k) for k in ('preserved','ok','error','source_component_count','child_component_count','native_source_component_count','native_child_component_count','exact_positive_native_island_overlap')},
             trace_craft_before_after=macro.get('trace_craft_before_after'),
             source_geometry=dict(non_ground_zone_count=len(zones),changed_non_ground_zones=[u for u,n in zones.items() if new.get(u)!=n],new_barrel_uuids=sorted(new_vias-old_vias),retired_barrel_uuids=sorted(old_vias-new_vias)),
             family_manifest=dict(path=manifest_path.name,sha256=force._hash(manifest_path)),
             evidence={n:force._hash(folder/n) if (folder/n).is_file() else None for n in ('route-plan.json','packet.json','construction.json','independent-receiving.json','native-drc.json')},
             current_qualified=False,routing_admitted=False,release_authority=False,
             limits=['Private evidence only; current nonregression is not current or thermal qualification.','No fabrication, bar fit, assembled-height, paired-field, or release qualification is established.'])
    (folder/'compact-receipt.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(status=out['status'],gates=gates,native=counts,trace_craft_before_after=out['trace_craft_before_after'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',nargs='?');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:
        import copy
        import tempfile
        with tempfile.TemporaryDirectory(prefix='macro-summary-bindings-') as temporary:
            root=Path(temporary);source=root/'source.kicad_pcb';candidate=root/'board.kicad_pcb'
            source.write_bytes(b'source');candidate.write_bytes(b'candidate')
            for suffix in ('.kicad_pro','.kicad_dru'): candidate.with_suffix(suffix).write_bytes(suffix.encode())
            checks=dict(macro=dict(source_sha256=force._hash(source),candidate_sha256=force._hash(candidate)),
                        native_drc=dict(ok=True,complete=True,source_files={str(p):force._hash(p) for p in (candidate,candidate.with_suffix('.kicad_pro'),candidate.with_suffix('.kicad_dru'))}),
                        current=dict(complete=True,source_candidate_and_code_unchanged=True))
            assert all(evidence_bindings(checks,source,candidate).values())
            candidate.write_bytes(b'changed child')
            result=evidence_bindings(checks,source,candidate)
            assert not result['macro_saved_hashes'] and not result['native_saved_family']
            candidate.write_bytes(b'candidate');candidate.with_suffix('.kicad_dru').write_bytes(b'changed rule')
            assert not evidence_bindings(checks,source,candidate)['native_saved_family']
            broken=copy.deepcopy(checks);broken['current'].pop('source_candidate_and_code_unchanged')
            assert not evidence_bindings(broken,source,candidate)['current_complete_stable']
        print('source-bound evidence negative smokes passed')
    elif args.folder: summarize(args.folder)
    else: parser.error('folder or --self-test required')
