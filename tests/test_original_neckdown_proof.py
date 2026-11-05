"""Saved-artifact exemptions cannot refer to only a legal post-split fragment."""
import json
import pcbnew
import pytest
import cec_fr,cec_constraints


def fixture(tmp_path,*,length,locked,offset=0,second_pad=False):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'arbitrary-supply');board.Add(net)
    for index,x in enumerate(([10+offset,10+offset+length] if second_pad else [10+offset])):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('PORT'+str(index))
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,10));layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers);pad.SetNet(net);fp.Add(pad);board.Add(fp)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(10+offset,10));track.SetEnd(pcbnew.VECTOR2I_MM(10+offset+length,10))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLocked(locked);board.Add(track)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{
        'classes':[{'name':'Default','track_width':.2},{'name':'Supply','track_width':1.0}],
        'netclass_assignments':{'arbitrary-supply':'Supply'},'netclass_patterns':[]}}))
    return board,track,path


@pytest.mark.parametrize('length,expected',[(1.,True),(3.,False)])
@pytest.mark.parametrize('locked',[False,True])
@pytest.mark.parametrize('offset',[0,30])
def test_original_full_length_proof_is_lock_and_translation_invariant(tmp_path,length,expected,locked,offset):
    board,track,path=fixture(tmp_path,length=length,locked=locked,offset=offset)
    identity=track.m_Uuid.AsString();saved=path.read_bytes()
    result=cec_fr.normalize_netclass_geometry(board,str(path))
    assert (identity in result['legal_original_neckdown_uuids']) is expected
    assert (identity in cec_constraints._legal_neckdown_uuids(str(path),{})) is expected
    assert path.read_bytes()==saved
    if length==3. and not locked:
        assert result['neckdown_split_tracks']==1
        assert identity in result['legal_neckdown_uuids']
        assert track.GetLength()<pcbnew.FromMM(length)


@pytest.mark.parametrize('locked',[False,True])
def test_both_endpoint_budgets_may_cover_one_original_segment(tmp_path,locked):
    board,track,path=fixture(tmp_path,length=2.5,locked=locked,second_pad=True)
    identity=track.m_Uuid.AsString()
    result=cec_fr.normalize_netclass_geometry(board,str(path))
    assert identity in result['legal_original_neckdown_uuids']
    assert identity in cec_constraints._legal_neckdown_uuids(str(path),{})


def test_legacy_generated_piece_evidence_cannot_grant_original_exception(tmp_path,monkeypatch):
    board,track,path=fixture(tmp_path,length=3.,locked=False)
    identity=track.m_Uuid.AsString()
    monkeypatch.setattr(cec_fr,'normalize_netclass_geometry',lambda *a:{'legal_neckdown_uuids':[identity]})
    assert identity not in cec_constraints._legal_neckdown_uuids(str(path),{})
