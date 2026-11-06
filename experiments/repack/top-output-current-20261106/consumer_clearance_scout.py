"""Private exact existing-tool transaction; no shared-code or gate changes."""
import sys,json,uuid,copy
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_consumer_group_reconstruction as group_tool
import cec_supply_consumer_branch as consumer
import cec_additive_route_receiving as native
import cec_copper_echo as syntax
import cec_force_current as force
import cec_field_coupling as field
import cec_suite_inspection as inspection

SOURCE=Path('experiments/repack/top-output-current-20261106/consolidated12-v1/carrier/board.kicad_pcb')
WORK=Path('experiments/repack/top-output-current-20261106/consumer-clearance-v1')
KEY='c93d67eb-c8c0-5624-bc60-7d19ff1d740f'
SHA='acf35631915c62f60e75a314f1d04469c8fc16647ddefc8c4ad3d4fb18c28dac'
POINTS=[[22770300,13979700],[25750000,11000000],[26050000,11000000],
        [28400000,8650000],[28400000,8350000],[29250000,7500000]]

def main():
    assert inspection.sha(SOURCE)==SHA and not WORK.exists()
    board=pcbnew.LoadBoard(str(SOURCE))
    scope=group_tool.plan(board,SOURCE,board_hint='atx-24pin-rev3',retired_track_uuids=[KEY],timeout_s=8.)
    before=consumer.inventory(board,board_hint='atx-24pin-rev3',timeout_s=8.)
    selected=next(t for t in board.GetTracks() if force._uid(t)==KEY)
    clones=[selected.Duplicate() for _ in POINTS[1:]]
    group_tool.subtract(board,scope);keys=[]
    for i,(track,a,b) in enumerate(zip(clones,POINTS,POINTS[1:])):
        key=str(uuid.uuid5(uuid.NAMESPACE_URL,'cec:consumer-bypass-scout-v2:'+KEY+':'+str(i)))
        track.m_Uuid.Clone(pcbnew.KIID(key));track.SetStart(pcbnew.VECTOR2I(*a))
        track.SetEnd(pcbnew.VECTOR2I(*b));board.Add(track);keys.append(key)
    group_tool.assign(board,scope,keys,[])
    after=consumer.inventory(board,board_hint='atx-24pin-rev3',timeout_s=8.)
    assert before['complete'] and after['complete'],after['refusals']
    oldproof=next(r for r in before['proofs'] if r['root_pad_uuid']==scope['root_pad_uuid'])
    newproof=next(r for r in after['proofs'] if r['root_pad_uuid']==scope['root_pad_uuid'])
    for name in ['budget','root_pad_uuid','anchor_uuid','retained_consumer_island_uuids',
                 'tap_capture_mode','tap_capture_via_uuid','physical_trunk_tap_count']:
        assert oldproof[name]==newproof[name],name
    native._ground_refill(board)
    target=force._copy_family(SOURCE,WORK/'carrier');raw=WORK/'native.kicad_pcb'
    field._save_field_snapshot(board,raw)
    root,old=native._nodes(SOURCE);_,fresh=native._nodes(raw)
    ground={force._uid(z) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
    changed={scope['group_uuid']}|ground
    assert set(fresh)==(set(old)-{KEY})|set(keys)
    assert all(syntax._freeze(old[u])==syntax._freeze(fresh[u]) for u in set(old)-{KEY}-changed)
    owners={id(n):u for u,n in old.items()}
    root[1:]=[copy.deepcopy(fresh[owners[id(n)]]) if owners.get(id(n)) in changed else n
              for n in root[1:] if owners.get(id(n))!=KEY]
    root.extend(copy.deepcopy(fresh[u]) for u in sorted(keys))
    target.write_text(native._render(root)+'\n')
    assert field._field_snapshot_inventory(pcbnew.LoadBoard(str(target)))==field._field_snapshot_inventory(board)
    assert force._sidecars(SOURCE)==force._sidecars(target)
    inspection.write_json(WORK/'construction.json',dict(source=str(SOURCE),source_sha256=SHA,
        candidate=str(target),candidate_sha256=inspection.sha(target),scope=scope,points_nm=POINTS,
        added_track_uuids=keys,source_consumer_inventory_complete=before['complete'],
        candidate_consumer_inventory_complete=after['complete'],exact_budget_root_anchor_and_island_preserved=True,
        routing_admitted=False,current_qualified=False,release_authority=False))
    assert inspection.sha(SOURCE)==SHA
    print(str(target))

if __name__=='__main__':main()
