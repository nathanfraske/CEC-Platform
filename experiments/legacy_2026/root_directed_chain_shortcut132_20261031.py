"""Finite agent construction using the unchanged public ordinary receivers.

The analytic portfolio preserves both real directed boundary launches. It is
only a geometry hint: no source ownership, clearance or receiving by assertion.
No production script, selected board or archived control is edited here.
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import signal
import time
import traceback


def paths(points, minimum_phase_nm):
    """Integer three-run candidates, with no new hard90 or reverse corner."""
    import cec_source_guided_ordinary_detour as guide
    guide.length_terms(points)
    if not 4 <= len(points) <= 17 or type(minimum_phase_nm) is not int or minimum_phase_nm <= 0:
        raise ValueError('finite_directed_chain_geometry_required')
    def direction(a, b):
        return tuple((b[k] > a[k])-(b[k] < a[k]) for k in (0, 1))
    def cross(u, v):
        return u[0]*v[1]-u[1]*v[0]
    a, z = points[0], points[-1]
    u, v = direction(*points[:2]), direction(*points[-2:])
    delta = [z[k]-a[k] for k in (0, 1)]
    first = max(abs(points[1][k]-a[k]) for k in (0, 1))
    last = max(abs(z[k]-points[-2][k]) for k in (0, 1))
    extent = sum(max(abs(q[k]-p[k]) for k in (0, 1)) for p, q in zip(points, points[1:]))
    found = set()
    for middle in ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)):
        if any(sum(x*y for x,y in zip(middle, ray)) <= 0 for ray in (u,v)):
            continue
        det = cross(middle, v)
        if not det:
            continue
        # Middle/final extents are affine functions of the first extent t.
        cm, bm = Fraction(cross(delta,v),det), Fraction(-cross(u,v),det)
        cv, bv = Fraction(cross(middle,delta),det), Fraction(-cross(middle,u),det)
        low, high = Fraction(minimum_phase_nm), Fraction(first)
        for c, b, upper in ((cm,bm,extent),(cv,bv,last)):
            if b == 0:
                if not minimum_phase_nm <= c <= upper:
                    low, high = Fraction(1), Fraction(0)
                    break
            else:
                l, h = (Fraction(minimum_phase_nm)-c)/b, (Fraction(upper)-c)/b
                low, high = max(low,min(l,h)), min(high,max(l,h))
        if low > high:
            continue
        lo, hi = math.ceil(low), math.floor(high)
        events = {lo,hi,(lo+hi)//2}
        for event in sorted({e+d for e in events for d in (-1,0,1)}):
            if not lo <= event <= hi:
                continue
            m, end = cm+bm*event, cv+bv*event
            if m.denominator != 1 or end.denominator != 1:
                continue
            b = [a[k]+u[k]*event for k in (0,1)]
            c = [z[k]-v[k]*int(end) for k in (0,1)]
            option = [list(a),b,c,list(z)]
            guide.length_terms(option)
            if not guide.strictly_shorter(option,points):
                continue
            vectors = [[q[k]-p[k] for k in (0,1)] for p,q in zip(option,option[1:])]
            if any(sum(x*y for x,y in zip(left,right)) <= 0 for left,right in zip(vectors,vectors[1:])):
                continue
            found.add(tuple(map(tuple,option)))
    return [list(map(list,p)) for p in sorted(found,key=lambda p:(sum(math.dist(x,z) for x,z in zip(p,p[1:])),p))][:16]


def main():
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet = wx.LogNull()
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_route_quality as craft
    import cec_field_coupling as field
    import cec_native_rule_areas as rules
    import cec_ordinary_source_connected_reflow as owner
    import cec_source_guided_ordinary_detour as guide
    import cec_additive_route_receiving as additive
    from cec_native_items import discard_items
    p = argparse.ArgumentParser()
    p.add_argument('stage',choices=('scope','construct','receive','field','current','craft','native_source','native_child',
        'current_source','current_child','current_compare','field_source','field_child','field_compare'))
    p.add_argument('--source',required=True)
    p.add_argument('--source-sha256',required=True)
    p.add_argument('--hint',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--issue-index',type=int,default=0)
    args = p.parse_args()
    began = time.monotonic(); deadline = began+9.1
    def alarm(*_):
        raise TimeoutError('directed_chain_shortcut_hard9_4')
    signal.signal(signal.SIGALRM,alarm); signal.setitimer(signal.ITIMER_REAL,9.4)
    source, out = Path(args.source).resolve(), Path(args.out).resolve()
    assert force._hash(source) == args.source_sha256
    freeze = Path('/mnt/c/Users/Admin/Documents/CEC-Board-Reviews/Source132-frozen-identity-20261031-root-ig.json')
    assert force._hash(freeze) == '1723497cbba5a41b6ddd3fd36cb36f5c0aa12df29cc07f4407ae61dbbfab9d4a'
    frozen = json.loads(freeze.read_text())
    assert force._code_identity() == frozen['code_identity']
    # Full control-directory fences are a separate bounded checkpoint step,
    # not charged repeatedly against the independent native receiver lease.
    family = force._family(source,args.hint)
    report = out/(args.stage+'.json'); assert not report.exists()
    child = out/'UNADMITTED-directed-source-shortcut'/'board.kicad_pcb'
    result = dict(stage=args.stage,complete=False,ok=False,source=str(source),source_sha256=args.source_sha256,
        source_family=family,code_identity=frozen['code_identity'],board_hint=args.hint,
        selected_frontier_changed=False,routing_admitted=False,release_authority=False,
        full_control_directory_terminal_fence_still_required=True)
    candidate_family = None
    timings = {}
    try:
        parent = pcbnew.LoadBoard(str(source))
        if args.stage == 'scope':
            whole = craft.analyze_board(parent)
            issues = [i for i in whole['issues'] if i['type']=='reverse_diagonal_jog']
            issue = issues[args.issue_index]; cuts = set(issue['track_uuids'])
            # Join only overlapping observations on this exact net/surface.
            for _ in range(16):
                before = set(cuts)
                for other in issues:
                    if (other['net'],other['layer']) == (issue['net'],issue['layer']) and cuts.intersection(other['track_uuids']):
                        cuts.update(other['track_uuids'])
                assert len(cuts) <= 16
                if before == cuts:
                    break
            live = {force._uid(t):t for t in parent.GetTracks()}; selected = [live[u] for u in sorted(cuts)]
            params = dict(board_hint=args.hint,net=issue['net'],retired_track_uuids=sorted(cuts),
                allow_locked_track_uuids=sorted(force._uid(t) for t in selected if t.IsLocked()))
            q = owner.plan(parent,source,timeout_s=deadline-time.monotonic(),**params)
            chain,_ = owner._chain(selected,deadline)
            original = [list(chain[0][1])]+[list(r[2]) for r in chain]
            trial = pcbnew.LoadBoard(str(source)); discard_items(trial,[t for t in trial.GetTracks() if force._uid(t) in cuts])
            width, face, code = q['width_nm'],q['layer_id'],selected[0].GetNetCode()
            spec = fr._project_netclass_resolver(str(source),board=parent)(issue['net']) or {}
            gap = max(int(parent.GetDesignSettings().m_MinClearance),math.ceil(float(spec.get('clearance') or 0)*1e6))
            zones,copper = fr._foreign_shape_indexes(trial,face,{code})
            forbidden = [r['shape'] for r in rules.areas(trial,'tracks') if face in r['layers']]
            checks = []
            for points in paths(original,max(20000,width)):
                if time.monotonic() >= deadline:
                    raise TimeoutError('directed_shortcut_portfolio_expired')
                rows = [dict(net=issue['net'],layer=face,width_nm=width,start_nm=x,end_nm=z) for x,z in zip(points,points[1:])]
                clear = all(fr._edge_leg_clear(trial,pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*z),(width+1)//2)
                    and fr._snapshot_foreign_clear(pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*z),width,gap,zones,copper)
                    and not any(s.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*z),width),0) for s in forbidden)
                    for x,z in zip(points,points[1:]))
                row = dict(points_nm=points,native_clear=clear); checks.append(row)
                if not clear or not guide._source_contacts(parent,selected,points,deadline):
                    continue
                row['craft'] = craft.assess_proposed_route(trial,rows,deadline=deadline)
                row['field'] = field.assess_proposed_route(trial,rows,deadline=deadline,
                    netclass_resolver=fr._project_netclass_resolver(str(source)))
                if all(row[k].get('ok') is True and row[k].get('complete') is True for k in ('craft','field')):
                    result.update(params=params,points_nm=points,source_points_nm=original,
                        source_scope=q,source_issue=issue,clearance_nm=gap,
                        original_length_mm=sum(math.dist(x,z) for x,z in zip(original,original[1:]))/1e6,
                        replacement_length_mm=sum(math.dist(x,z) for x,z in zip(points,points[1:]))/1e6,
                        same_fixed_ports_width_and_directed_launches=True,ok=True)
                    break
            result.update(whole_source_craft=whole,trials=checks,complete=True)
        else:
            recipe = json.loads((out/'scope.json').read_text())
            assert recipe['ok'] is True and recipe['complete'] is True
            assert recipe['source_sha256'] == args.source_sha256 and recipe['source_family'] == family
            assert recipe['code_identity'] == frozen['code_identity']
            params = recipe['params']
            if args.stage == 'construct':
                import tempfile
                import cec_source_literal_additions as literal
                import cec_source_literal_retirement as retirement
                import cec_source_retaining_ses_import as raw
                assert not child.parent.exists()
                q = owner.plan(parent,source,timeout_s=deadline-time.monotonic(),**params)
                assert q == recipe['source_scope']
                selected = [t for t in parent.GetTracks() if force._uid(t) in params['retired_track_uuids']]
                assert guide.strictly_shorter(recipe['points_nm'],recipe['source_points_nm'])
                assert guide._source_contacts(parent,selected,recipe['points_nm'],deadline)
                trial = pcbnew.LoadBoard(str(source)); discard_items(trial,[t for t in trial.GetTracks() if force._uid(t) in params['retired_track_uuids']])
                for x,z in zip(recipe['points_nm'],recipe['points_nm'][1:]):
                    t = selected[0].Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
                    t.SetStart(pcbnew.VECTOR2I(*x)); t.SetEnd(pcbnew.VECTOR2I(*z)); trial.Add(t)
                ground = additive._ground_refill(trial)
                child = force._copy_family(source,child.parent)
                with tempfile.TemporaryDirectory(prefix='cec-directed-shortcut-') as tmp:
                    native = Path(tmp)/'board.kicad_pcb'; field._save_field_snapshot(trial,native)
                    raw.write_raw(child,literal.assemble(retirement.subtract(raw.raw_text(source),params['retired_track_uuids']),raw.raw_text(native),ground_ids=ground))
                proof = dict(ok=True,complete=True,ground_refilled=ground,independent_saved_receiving_required=True)
            else:
                assert child.is_file(); candidate_family = force._family(child,args.hint)
                saved = json.loads((out/'construct.json').read_text())
                assert saved['ok'] is True and saved['candidate_sha256'] == force._hash(child)
                if args.stage == 'receive':
                    # Named bounded coordinator: preparation and independent
                    # native receiving have separate <=9.4s leases. This is
                    # not a longer lease for the native receiver itself.
                    timings['preparation_s'] = time.monotonic()-began
                    assert timings['preparation_s'] < 9.4
                    print(json.dumps(dict(stage='native_receive_start',preparation_s=timings['preparation_s'])),flush=True)
                    receive_start = time.monotonic(); deadline = receive_start+9.0
                    signal.setitimer(signal.ITIMER_REAL,9.3)
                    proof = owner.receive(source,child,timeout_s=deadline-time.monotonic(),**params)
                    timings['independent_native_receiver_s'] = time.monotonic()-receive_start
                    assert timings['independent_native_receiver_s'] < 9.3
                    print(json.dumps(dict(stage='native_receive_finish',elapsed_s=timings['independent_native_receiver_s'],ok=proof['ok'])),flush=True)
                elif args.stage == 'field':
                    proof = field.assess_native_ordinary_replacement(source,child,**{k:v for k,v in params.items() if k!='net'},timeout_s=deadline-time.monotonic())
                elif args.stage == 'current':
                    import cec_current_debt as current
                    proof = current.receive(source,child,board_hint=args.hint)
                elif args.stage in ('current_source','current_child'):
                    import cec_constraints as constraints
                    endpoint = source if args.stage == 'current_source' else child
                    with force._thermal_hint(args.hint):
                        board = pcbnew.LoadBoard(str(endpoint))
                        raw_result = constraints.CHECKERS['trace-width-high-current'](board,str(endpoint),{})
                    import cec_current_debt as current
                    # Parse the full typed inventory now, not just its label.
                    snapshot = current._snapshot(raw_result)
                    result['raw_current_result'] = raw_result
                    proof = dict(ok=True,complete=True,fault_objects=len(snapshot['atoms']),
                        current_qualified=raw_result[0] is True,actual_saved_board_evaluated=str(endpoint))
                elif args.stage == 'current_compare':
                    import cec_current_debt as current
                    packets = [json.loads((out/(name+'.json')).read_text()) for name in ('current_source','current_child')]
                    for packet in packets:
                        assert packet['complete'] is True and packet['ok'] is True
                        assert packet['source_family'] == family and packet['candidate_family'] == candidate_family
                        assert packet['code_identity'] == frozen['code_identity']
                    proof = current.evaluate(*(q['raw_current_result'] for q in packets))
                    proof['independent_native_evaluations'] = 2
                    proof['whole_typed_inventory_received_in_separate_bounded_stages'] = True
                elif args.stage in ('field_source','field_child'):
                    endpoint = source if args.stage == 'field_source' else child
                    board = pcbnew.LoadBoard(str(endpoint)); refilled = []
                    assert len(list(board.GetTracks()))+len(list(board.Zones())) <= 16384
                    resolver = fr._project_netclass_resolver(str(endpoint))
                    for t in board.GetTracks():
                        if t.GetClass() in ('PCB_TRACK','PCB_VIA'):
                            continue
                        role = field.classify_net(t.GetNetname(),netclass=field._netclass_name(resolver(t.GetNetname())))
                        assert not role['aggressor'] and not role['victim']
                    if args.stage == 'field_child':
                        # Only this native RAM copy is refilled. The exact
                        # original saved parent's actual fills remain intact.
                        identity = [(force._uid(t),t.GetNetname(),force._item_key(t)) for t in board.GetTracks()]
                        refilled = additive._ground_refill(board)
                        assert identity == [(force._uid(t),t.GetNetname(),force._item_key(t)) for t in board.GetTracks()]
                    raw_result = field.field_coupling_summary(str(endpoint),board=board,
                        _work=field._ProposalWork(deadline,16384,1000000,1000000,16384),board_hint=args.hint)
                    result['raw_field_result'] = raw_result
                    proof = dict(ok=True,complete=True,actual_saved_board_evaluated=str(endpoint),
                        ground_refilled_on_private_RAM_copy=refilled,actual_original_parent_not_projected=True,
                        old_old_and_new_interactions_included=True)
                elif args.stage == 'field_compare':
                    packets = [json.loads((out/(name+'.json')).read_text()) for name in ('field_source','field_child')]
                    for packet in packets:
                        assert packet['complete'] is True and packet['ok'] is True
                        assert packet['source_family'] == family and packet['candidate_family'] == candidate_family
                        assert packet['code_identity'] == frozen['code_identity']
                    received = json.loads((out/'receive.json').read_text())
                    assert received['ok'] is True and received['complete'] is True
                    assert received['source_family'] == family and received['candidate_sha256'] == force._hash(child)
                    assert received['code_identity'] == frozen['code_identity']
                    before,after = [q['raw_field_result'] for q in packets]
                    old = field.blocker_keys(before)
                    introduced = [r for r in after['interactions'] if r.get('blocking')
                        and next(iter(field.blocker_keys(dict(interactions=[r])))) not in old]
                    proof = dict(ok=not introduced,complete=True,new_blockers=introduced,
                        prior_blocking_count=before['blocking_count'],final_blocking_count=after['blocking_count'],
                        original_parent_field_and_private_refilled_child_field=True,
                        independent_saved_ordinary_receiving_separate_and_required=True,
                        inherited_field_debt_qualified=False,release_authority=False)
                elif args.stage == 'craft':
                    from cec_received_private_stage import route_craft_delta
                    before,after = [craft.analyze(str(p)) for p in (source,child)]
                    result.update(whole_source_craft=before,whole_saved_craft=after)
                    proof = dict(route_craft_delta(before,after),complete=True)
                else:
                    import cec_native_drc_runner as native
                    context_path = Path('/mnt/c/Users/Admin/Documents/CEC-Board-Reviews/selected106-native-observed131-20261031-root-gr/receipt.json')
                    assert force._hash(context_path) == 'e74b3ce880d5985f2e929d87922d0896ec27ac403fee66d011ea38fed21fa16b'
                    context = json.loads(context_path.read_text())['selected_library_table_identities'][args.hint]
                    table = Path(context['path']); assert force._hash(table) == context['sha256']
                    endpoint = source if args.stage == 'native_source' else child
                    directory = out/args.stage; assert not directory.exists(); directory.mkdir()
                    copied = force._copy_family(endpoint,directory/'native-input')
                    proof = native.run(copied,directory/'native.json',footprint_table=table,
                        reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=min(9.,deadline-time.monotonic()))
                    data = json.loads((directory/'native.json').read_text())
                    result['counts'] = dict(opens=len(data['unconnected_items']),
                        errors=sum(r['severity']=='error' for r in data['violations']),warnings=sum(r['severity']=='warning' for r in data['violations']),
                        exclusions=len(data.get('excluded_violations',[])))
            result.update(ok=proof.get('ok') is True,complete=proof.get('complete') is True,proof=proof)
            result.update(candidate=str(child),candidate_sha256=force._hash(child),
                candidate_family=force._family(child,args.hint))
    except BaseException as exc:
        result['error'] = dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        final_start = time.monotonic()
        signal.setitimer(signal.ITIMER_REAL,9.4)
        assert force._family(source,args.hint) == family
        if candidate_family is not None:
            assert force._family(child,args.hint) == candidate_family
        assert force._code_identity() == frozen['code_identity']
        timings['terminal_fence_s'] = time.monotonic()-final_start
        result.update(source_family_and_code_unchanged=True,helper_sha256=force._hash(__file__),elapsed_s=time.monotonic()-began,
            timings_s=timings,native_constituent_limit_s=9.3)
        report.parent.mkdir(parents=True,exist_ok=True); force._write(report,result)
        signal.setitimer(signal.ITIMER_REAL,0)
        print(json.dumps(dict(stage=args.stage,ok=result['ok'],complete=result['complete'],report=str(report),
            sha256=force._hash(report),error=result.get('error'),errors=result.get('proof',{}).get('errors'),
            counts=result.get('counts'),elapsed_s=result['elapsed_s'])),flush=True)


if __name__ == '__main__':
    main()
