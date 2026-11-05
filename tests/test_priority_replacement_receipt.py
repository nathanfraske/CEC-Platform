"""Native primitive ownership, typed scope and artifact-family rollback tests.

Pair physics is a separate unchanged gate in these tiny primitive fixtures;
the real retained-board replay exercises that native gate without a mock.
"""
import copy
import hashlib
import json
from types import SimpleNamespace
import pcbnew
import pytest
import cec_fr
import cec_full_pipeline as pipeline
import cec_priority_dependency as dependency
import cec_priority_replacement_receipt as receipts
import cec_placement_route_prefix as prefix
import cec_synth_pipeline as synth
from cec_native_items import discard_items


def proof():
    return dict(ok=True,constructed=True,released_nets=['N','P'],placement_unchanged=True,
        physical_ok=True,retained_prefix={'ok':True},all_original_pairs={'ok':True},authority={'ok':True})


def add_track(board,net,y):
    item=pcbnew.PCB_TRACK(board)
    item.SetNet(board.FindNet(net));item.SetLayer(pcbnew.F_Cu)
    item.SetStart(pcbnew.VECTOR2I_MM(3,y));item.SetEnd(pcbnew.VECTOR2I_MM(23,y))
    item.SetWidth(pcbnew.FromMM(.25));item.SetLocked(True);board.Add(item)


def change_pair(source,target,y):
    board=pcbnew.LoadBoard(str(source))
    discard_items(board,[t for t in board.GetTracks() if t.GetNetname() in ('P','N')])
    add_track(board,'P',y);add_track(board,'N',y+.45)
    pcbnew.SaveBoard(str(target),board,True)


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';target=tmp_path/'target.kicad_pcb'
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    for net in ('P','N','RAIL','GND'):board.Add(pcbnew.NETINFO_ITEM(board,net))
    for net,y in [('P',2),('N',2.45),('RAIL',20)]:add_track(board,net,y)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'))
    via.SetPosition(pcbnew.VECTOR2I_MM(2,5));via.SetWidth(pcbnew.FromMM(.45))
    via.SetDrill(pcbnew.FromMM(.25));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetLocked(True);board.Add(via)
    uid=via.m_Uuid.AsString();pcbnew.SaveBoard(str(source),board,True)
    contract=cec_fr.copper_geometry_prefix_contract(str(source),['P','N','RAIL','GND'])
    contract.update(placement_preserved_nets=['P','N','RAIL'],placement_power_nets=['RAIL'],
        placement_preserved_uuids=[uid],qualified_critical_pairs=[
            dict(name='pair',p='P',n='N',qualified=True)])
    plan=dependency.release_plan(contract,dict(ok=False,violations=[
        dict(kind='fixed_copper_pad_collision',copper_net='P',copper_uuid='native-witness')]))
    change_pair(source,target,4)
    monkeypatch.setattr(prefix,'check_qualified_pairs',lambda *a,**kw:dict(ok=True,applicable=True))
    return SimpleNamespace(source=source,target=target,contract=contract,plan=plan,
        source_sha=hashlib.sha256(source.read_bytes()).hexdigest(),owner=SimpleNamespace(protected_power_prefix=contract))


def issue(fixture):
    return receipts.issue(fixture.contract,fixture.plan,proof(),fixture.target,
                          source_board_sha256=fixture.source_sha)


def test_missing_receipt_fails_but_exact_accepted_transition_passes(fixture):
    with pytest.raises(ValueError,match='protected power copper'):
        synth._admit_materialized_power_prefix(fixture.owner,fixture.target)
    before=copy.deepcopy(fixture.contract)
    row=issue(fixture);receipts.stage(fixture.source,fixture.target,row)
    admitted=synth._admit_materialized_power_prefix(fixture.owner,fixture.target)
    assert admitted['ok'] and admitted['priority_replacement']['ok']
    assert fixture.contract==before  # old owner was never silently recaptured
    assert row['target_contract']['placement_power_nets']==['RAIL']
    assert row['target_contract']['placement_preserved_uuids']==before['placement_preserved_uuids']


@pytest.mark.parametrize('key',['ok','constructed','placement_unchanged','physical_ok',
                               'retained_prefix','all_original_pairs','authority'])
def test_every_independent_proof_is_required(fixture,key):
    bad=proof();bad[key]={'ok':False} if isinstance(bad[key],dict) else False
    with pytest.raises(ValueError,match='complete native acceptance'):
        receipts.issue(fixture.contract,fixture.plan,bad,fixture.target,
                       source_board_sha256=fixture.source_sha)


@pytest.mark.parametrize('net',['RAIL','GND','P'])
def test_receipt_cannot_authorize_later_copper_deletion(fixture,net):
    receipts.stage(fixture.source,fixture.target,issue(fixture))
    board=pcbnew.LoadBoard(str(fixture.target))
    discard_items(board,[t for t in board.GetTracks() if t.GetNetname()==net])
    pcbnew.SaveBoard(str(fixture.target),board,True)
    with pytest.raises(ValueError,match='protected power copper'):
        synth._admit_materialized_power_prefix(fixture.owner,fixture.target)


@pytest.mark.parametrize('kind',['checksum','power-classification','retained-count','half-pair','source-mismatch'])
def test_tampered_or_foreign_receipt_never_opens_the_guard(fixture,kind):
    row=issue(fixture)
    if kind=='checksum':row['accepted_board_sha256']='0'*64
    elif kind=='power-classification':row['target_contract']['placement_power_nets']=[]
    elif kind=='retained-count':
        key=next(k for k,n in row['target_contract']['member_nets'].items() if n=='RAIL')
        row['target_contract']['members'][key]=2
        row['target_contract']['items']+=1;row['target_contract']['items_by_net']['RAIL']+=1
    elif kind=='half-pair':row['released_nets']=['P']
    else:
        # A self-consistent receipt for another original rail shape cannot
        # advance this owner, even when its new signal shape would match.
        for contract in (row['source_contract'],row['target_contract']):
            key=next(k for k,n in contract['member_nets'].items() if n=='RAIL')
            contract['members']['foreign']=contract['members'].pop(key)
            contract['member_nets']['foreign']=contract['member_nets'].pop(key)
    if kind!='checksum':row['checksum']=receipts.digest({k:v for k,v in row.items() if k!='checksum'})
    pipeline.atomic_json(fixture.target.with_suffix(receipts.SUFFIX),dict(schema=1,transitions=[row]))
    with pytest.raises(ValueError,match='protected power copper'):
        synth._admit_materialized_power_prefix(fixture.owner,fixture.target)


def test_pair_quality_is_still_checked_after_receipt_resolution(fixture,monkeypatch):
    receipts.stage(fixture.source,fixture.target,issue(fixture))
    monkeypatch.setattr(prefix,'check_qualified_pairs',lambda *a,**kw:dict(ok=False))
    with pytest.raises(ValueError,match='protected power copper'):
        synth._admit_materialized_power_prefix(fixture.owner,fixture.target)


def test_transaction_payload_rename_and_rollback_carry_the_receipt(fixture,tmp_path):
    working=tmp_path/'working.kicad_pcb'
    pipeline._copy_sidecars(fixture.source,working)
    before=tmp_path/'before';after=tmp_path/'after'
    pipeline._snapshot_placement_authority(working,before)
    row=issue(fixture);receipts.stage(fixture.source,fixture.target,row)
    pipeline._publish_placement_authority_payload(working,
        pipeline._capture_placement_authority_payload(fixture.target))
    assert receipts.read(working)==[row]
    assert synth._admit_materialized_power_prefix(fixture.owner,working)['ok']
    pipeline._snapshot_placement_authority(working,after)
    pipeline._restore_placement_authority(working,before)
    assert not working.with_suffix(receipts.SUFFIX).exists()
    assert synth._admit_materialized_power_prefix(fixture.owner,working)['ok']
    pipeline._restore_placement_authority(working,after)
    assert synth._admit_materialized_power_prefix(fixture.owner,working)['ok']
    renamed=tmp_path/'renamed.kicad_pcb';pipeline._copy_sidecars(working,renamed)
    assert receipts.read(renamed)==[row]
    pipeline._copy_sidecars(fixture.source,renamed)
    assert not renamed.with_suffix(receipts.SUFFIX).exists()


def test_chained_transition_resolves_only_reachable_current_geometry(fixture,tmp_path):
    first=issue(fixture);receipts.stage(fixture.source,fixture.target,first)
    third=tmp_path/'third.kicad_pcb';change_pair(fixture.target,third,6)
    source=first['target_contract']
    plan=dependency.release_plan(source,dict(ok=False,violations=[
        dict(kind='fixed_copper_pad_collision',copper_net='P',copper_uuid='native-next')]))
    second=receipts.issue(source,plan,proof(),third,
        source_board_sha256=hashlib.sha256(fixture.target.read_bytes()).hexdigest())
    receipts.stage(fixture.target,third,second)
    result=synth._admit_materialized_power_prefix(fixture.owner,third)
    assert result['ok'] and result['priority_replacement']['reachable_transitions']==2


def test_producer_stages_receipt_before_winning_payload_capture():
    import inspect
    code=inspect.getsource(pipeline._repair_placement_priority_routes_with_power_replan_in_process)
    position=code.index("replacement_receipt.stage(")
    assert position<code.index('payload = _capture_placement_authority_payload(',position)
    assert '_repair_placement_priority_routes_with_power_replan_in_process(' in inspect.getsource(
        pipeline._repair_failed_power_bridge_placement_in_process)


def test_receipt_addition_changes_evidence_identity_and_is_a_source_input(fixture,monkeypatch):
    import cec_route_evidence as evidence
    import cec_sch_gates
    before=evidence.files(evidence.artifact_paths(fixture.target))
    receipts.stage(fixture.source,fixture.target,issue(fixture))
    after=evidence.files(evidence.artifact_paths(fixture.target))
    assert before[receipts.SUFFIX] is None
    assert after[receipts.SUFFIX] and before!=after
    monkeypatch.setattr(cec_sch_gates,'inventory',lambda path:{})
    cfg=SimpleNamespace(sch=fixture.source.parent/'synthetic.kicad_sch',
                        dir=fixture.source.parent,params={})
    assert fixture.target.with_suffix(receipts.SUFFIX) in pipeline._source_files(cfg,fixture.target)


def test_history_is_bounded_and_failed_staging_does_not_touch_target(fixture):
    row=issue(fixture)
    pipeline.atomic_json(fixture.source.with_suffix(receipts.SUFFIX),
        dict(schema=1,transitions=[row]*receipts.MAX_TRANSITIONS))
    target=fixture.target.with_suffix(receipts.SUFFIX)
    assert not target.exists()
    with pytest.raises(ValueError,match='budget exhausted'):
        receipts.stage(fixture.source,fixture.target,row)
    assert not target.exists()
