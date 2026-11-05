import copy
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_power_local_replay as replay


def fixture(*, shifted_codes=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    if shifted_codes:board.Add(pcbnew.NETINFO_ITEM(board,'unrelated'))
    net=pcbnew.NETINFO_ITEM(board,'arbitrary supply');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('DEVICE');board.Add(fp)
    for index,x in enumerate((10,12)):
        p=pcbnew.PAD(fp);p.SetNumber(str(index));p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        p.SetLayerSet(layers);p.SetNet(net)
        p.SetPosition(pcbnew.VECTOR2I_MM(x,10));fp.Add(p)
    return board,net


def copper(board,net):
    track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(10,10))
    track.SetEnd(pcbnew.VECTOR2I_MM(12,10));track.SetWidth(pcbnew.FromMM(.5))
    track.SetLayer(pcbnew.B_Cu);track.SetLocked(True);track.SetNet(net);board.Add(track)
    items=[track]
    for x in (10,12):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(x,10));v.SetWidth(pcbnew.FromMM(.35))
        v.SetDrill(pcbnew.FromMM(.25));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetLocked(True);v.SetNet(net);board.Add(v);items.append(v)
    g=pcbnew.PCB_GROUP(board);g.SetName('LOCAL_FAB_OWNERSHIP');board.Add(g)
    for item in items:g.AddItem(item)
    return items


def test_exact_replay_rebinds_nets_and_is_idempotent(tmp_path):
    source,net=fixture();items=copper(source,net)
    contract=replay.capture(source,[i.m_Uuid.AsString() for i in items])
    target,_=fixture(shifted_codes=True)
    receipt=replay.replay(target,contract)
    assert receipt['added']==3 and receipt['reused']==0 and not receipt['admitted']
    assert replay.capture(target,contract_identities(contract))==contract
    receipt=replay.replay(target,contract)
    assert receipt['added']==0 and receipt['reused']==3
    assert len(list(target.GetTracks()))==3
    assert [len(list(g.GetItems())) for g in target.Groups()]==[3]
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),target)
    loaded=pcbnew.LoadBoard(str(path))
    assert replay.replay(loaded,contract)['added']==0


def contract_identities(contract):
    return [row['uuid'] for row in contract['items']]


@pytest.mark.parametrize('defect',['tampered','terminal','identity','unlocked','duplicate'])
def test_invalid_contracts_refuse_without_partial_copper(defect):
    source,net=fixture();items=copper(source,net)
    contract=replay.capture(source,[i.m_Uuid.AsString() for i in items])
    target,_=fixture()
    if defect=='tampered':contract['items'][0]['width']+=1
    elif defect=='terminal':next(iter(next(iter(target.GetFootprints())).Pads())).SetPosition(pcbnew.VECTOR2I_MM(9,10))
    elif defect=='duplicate':
        contract['items'].append(copy.deepcopy(contract['items'][0]));contract['sha256']=replay._digest(contract['items'])
    else:
        replay.replay(target,contract)
        track=next(i for i in target.GetTracks() if i.GetClass()=='PCB_TRACK')
        if defect=='identity':track.SetWidth(pcbnew.FromMM(.9))
        else:track.SetLocked(False)
    before={i.m_Uuid.AsString():replay._geometry(target,i) for i in target.GetTracks()}
    with pytest.raises(ValueError):replay.replay(target,contract)
    assert {i.m_Uuid.AsString():replay._geometry(target,i) for i in target.GetTracks()}==before


def test_equivalent_prefix_reuses_existing_geometry():
    source,net=fixture();items=copper(source,net)
    contract=replay.capture(source,[i.m_Uuid.AsString() for i in items])
    target,net=fixture();copper(target,net)
    assert replay.replay(target,contract)['reused']==3
    assert len(list(target.GetTracks()))==3


def test_equivalent_unlocked_prefix_refuses_without_duplicating_copper():
    source,net=fixture();items=copper(source,net)
    contract=replay.capture(source,[i.m_Uuid.AsString() for i in items])
    target,net=fixture();existing=copper(target,net)
    existing[0].SetLocked(False)
    before={i.m_Uuid.AsString():replay._geometry(target,i) for i in target.GetTracks()}
    with pytest.raises(ValueError,match='lost ownership'):
        replay.replay(target,contract)
    assert {i.m_Uuid.AsString():replay._geometry(target,i) for i in target.GetTracks()}==before
