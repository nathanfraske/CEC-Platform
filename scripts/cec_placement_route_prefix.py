"""Exact power and qualified critical routing ownership on placement resume.

Critical signal nets must be fully connected and pass the existing saved-board
physics checks. Their explicitly owned return vias are retained by identity,
without making the entire reference net immutable or claiming it is routed.
"""
import json
from collections import Counter
from pathlib import Path


class UnownedRoutedCopper(ValueError):
    """Placement reconstruction cannot discard another routing stage's work."""
    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__('routed_copper_requires_owned_transaction: %d unpreserved items' %
                         evidence.get('unpreserved_items', 0))


class UnadmittedLocalCopper(ValueError):
    """An expected power-qualification refusal, never retained route ownership."""
    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__('local copper lacks admitted frozen authority')


def rehydration_coverage(board, contract):
    """Prove every existing track/arc/via survives this materializer's prefix.

    ``allow_routed`` permits known retained copper, not a blanket rip-up.
    Ordinary signals and even locked/critical nets outside this exact retained
    set need a route-owned local transaction. This is not a routability test.
    """
    if contract.get('retention_only') is True:
        raise ValueError('retention_proof_cannot_authorize_placement_rehydration')
    nets = set(preserved_nets(contract))
    identities = set(preserved_uuids(contract))
    missing = Counter()
    total = 0
    for item in board.GetTracks():
        total += 1
        if (item.GetNetname() not in nets
                and item.m_Uuid.AsString() not in identities):
            missing[str(item.GetNetname())] += 1
    absent = sum(missing.values())
    return dict(schema=1, ok=not absent, total_items=total,
                preserved_items=total-absent, unpreserved_items=absent,
                unpreserved_by_net=dict(sorted(missing.items())),
                requires_owned_reroute=bool(absent), release_authority=False)


def preserved_nets(contract):
    return tuple(contract.get('placement_preserved_nets',contract.get('nets') or ()))


def preserved_uuids(contract):
    return tuple(contract.get('placement_preserved_uuids') or ())


def capture(board_path, *, include_local_authority=True):
    import pcbnew
    import cec_fr
    import cec_precision_route as precision
    import cec_staged_fr as staged
    import cec_constraints
    board=pcbnew.LoadBoard(str(board_path))
    power=cec_fr.locked_pour_authority_nets_board(board,include_complete_nets=False)
    owned=cec_fr.owned_locked_nets_board(board)
    candidates=[pair for pair in precision.derive_coupled_pairs(str(board_path),board=board)
                if {pair['p'],pair['n']}<=owned]
    qualified=[];evidence=[]
    if candidates:
        nets={pair[key] for pair in candidates for key in ('p','n')}
        connected,unused=staged.fully_connected_nets(board,nets)
        physical=cec_constraints.high_speed_pair_summary(str(board_path))
        for pair in candidates:
            pair_nets={pair['p'],pair['n']}
            physics=staged.tier_pair_physics(physical,pair_nets,[pair])
            ok=pair_nets<=connected and physics.get('ok') and physics.get('applicable')
            evidence.append(dict(name=pair['name'],p=pair['p'],n=pair['n'],
                                 qualified=bool(ok),physics=physics))
            if ok:qualified.append(pair)
    selected=power|{pair[key] for pair in qualified for key in ('p','n')}
    # Local return fields are individually owned. Do NOT make the entire GND
    # net immutable, fully routed, or exempt from ordinary geometry checks.
    ids={item.m_Uuid.AsString() for group in board.Groups()
         if group.GetName()==cec_fr.LOCAL_PAIR_RETURN_VIA_GROUP
         for item in group.GetItems()} if qualified else set()
    for item in board.GetTracks():
        uid=item.m_Uuid.AsString()
        if uid not in ids:continue
        if not item.IsLocked() or item.GetClass()!='PCB_VIA' or item.GetNetname()!='GND':
            raise ValueError('invalid local critical return ownership')
    local=None
    state_path=Path(board_path).with_suffix('.pourfirst-state.json')
    if state_path.is_file() and include_local_authority:
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('local_copper_contract') is not None:
            if (state.get('placement_scope')!='complete'
                    or (state.get('exact_admission') or {}).get('passed') is not True):
                raise UnadmittedLocalCopper(dict(schema=1,
                    reason='local_copper_lacks_admitted_frozen_authority',
                    blocked_stage='frozen_power_authority',state=str(state_path),
                    placement_scope=state.get('placement_scope'),
                    exact_admission_passed=(state.get('exact_admission') or {}).get('passed') is True,
                    grants_copper_ownership=False,release_authority=False))
            import cec_power_local_replay
            local=cec_power_local_replay.for_placement(board,state['local_copper_contract'])
            ids.update(row['uuid'] for row in local['items'])
    # Item ownership never grants the entire rail/ground net to placement.
    ids={item.m_Uuid.AsString() for item in board.GetTracks()
         if item.m_Uuid.AsString() in ids and item.GetNetname() not in selected}
    contract=cec_fr.copper_geometry_prefix_contract(str(board_path),selected,item_uuids=ids)
    contract.update(placement_power_nets=sorted(power),
                    placement_preserved_nets=sorted(selected),
                    placement_preserved_uuids=sorted(ids),qualified_critical_pairs=evidence)
    if local is not None:contract['placement_local_copper']=local
    if not include_local_authority:
        # A non-mutating/additive receiver proves every original native item
        # independently. It needs qualified pair retention, not permission to
        # reconstruct unadmitted local copper. Never feed this into placement.
        contract.update(retention_only=True,grants_local_copper_ownership=False)
    return contract


def check_local_copper(board_path,contract):
    local=contract.get('placement_local_copper')
    if local is None:return dict(ok=True,applicable=False)
    import pcbnew
    import cec_power_local_replay
    try:
        evidence=cec_power_local_replay.verify_present(pcbnew.LoadBoard(str(board_path)),local)
        return dict(evidence,applicable=True)
    except (ValueError,TypeError,KeyError) as exc:
        return dict(ok=False,applicable=True,reason=str(exc))


def carry_local_authority(source,output,contract):
    """Carry the verified scope forward; never recapture it after a move."""
    local=contract.get('placement_local_copper')
    if local is None:return
    import shutil
    import cec_full_pipeline
    state_path=Path(output).with_suffix('.pourfirst-state.json')
    # State + skeleton are source authority, not newly inferred geometry.
    # The caller runs in an isolated staging directory and publishes only if
    # this handoff and the exact original power-independence guard succeed.
    if not state_path.is_file():
        source_state=Path(source).with_suffix('.pourfirst-state.json')
        state=json.loads(source_state.read_text(encoding='utf-8'))
        skeleton=Path(state['skeleton'])
        if not skeleton.is_absolute():skeleton=source_state.parent/skeleton
        if not skeleton.is_file():raise ValueError('local copper frozen skeleton is missing')
        destination=Path(output).with_suffix('.pourfirst-skeleton.kicad_pcb')
        if skeleton.resolve()!=destination.resolve():shutil.copy2(skeleton,destination)
        state['skeleton']=str(destination.resolve())
    else:
        state=json.loads(state_path.read_text(encoding='utf-8'))
    original=state.get('local_copper_contract') or {}
    if original.get('sha256')!=local.get('sha256'):
        raise ValueError('local copper authority payload changed during handoff')
    state['local_copper_contract']=local
    state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    result=cec_full_pipeline._sync_safe_postfreeze_placement_delta(output)
    if not result.get('ok'):
        raise ValueError('local copper handoff violates frozen power placement: %s'%result)


def rebase_published_state(staged_board,destination):
    """An atomic directory handoff must not leave a deleted staging pointer."""
    path=Path(staged_board).with_suffix('.pourfirst-state.json')
    if not path.is_file():return
    state=json.loads(path.read_text(encoding='utf-8'))
    skeleton=Path(state.get('skeleton') or '')
    if not skeleton.is_absolute():skeleton=path.parent/skeleton
    if not skeleton.is_file():raise ValueError('published frozen skeleton is missing')
    if skeleton.resolve().parent!=path.resolve().parent:
        raise ValueError('published frozen skeleton is not self-contained')
    state['skeleton']=str(Path(destination).resolve().parent/skeleton.name)
    path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')


def check_qualified_pairs(board_path, contract):
    """Moving other packages/refilling planes may invalidate an exact pair."""
    expected=[row for row in contract.get('qualified_critical_pairs',())
              if row.get('qualified')]
    if not expected:
        return dict(ok=True,applicable=False,pairs=[])
    import pcbnew
    import cec_precision_route as precision
    import cec_staged_fr as staged
    import cec_constraints
    board=pcbnew.LoadBoard(str(board_path))
    derived=precision.derive_coupled_pairs(str(board_path),board=board)
    actual={(pair['name'],pair['p'],pair['n']):pair for pair in derived}
    nets={row[key] for row in expected for key in ('p','n')}
    connected,_unused=staged.fully_connected_nets(board,nets)
    physical=cec_constraints.high_speed_pair_summary(str(board_path))
    results=[]
    for row in expected:
        pair=actual.get((row['name'],row['p'],row['n']))
        pair_nets={row['p'],row['n']}
        physics=(staged.tier_pair_physics(physical,pair_nets,[pair]) if pair
                 else dict(ok=False,applicable=False,reason='pair contract changed'))
        results.append(dict(name=row['name'],connected=pair_nets<=connected,
                            physics=physics,ok=bool(pair_nets<=connected
                            and physics.get('ok') and physics.get('applicable'))))
    return dict(ok=all(row['ok'] for row in results),applicable=True,pairs=results)


if __name__=='__main__':
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    import cec_swig_guard
    cec_swig_guard.pin()
    result=capture(sys.argv[1])
    print(json.dumps({k:v for k,v in result.items() if k not in ('members','member_nets')},indent=2))
