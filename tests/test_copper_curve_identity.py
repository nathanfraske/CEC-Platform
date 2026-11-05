"""Loaded-native curve identity, distinct from electrical connectivity proof."""
import copy
import hashlib
import json

import pcbnew
import pytest

import cec_fr


def fixture(tmp_path, *, net='CURVE', offset=(0,0), angle=0, layer=pcbnew.F_Cu):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    board.Add(pcbnew.NETINFO_ITEM(board,net))
    import cec_placement_search_domain as domain
    def point(x,y):
        px,py = domain.rotate_board_point((x,y),(0,0),angle)
        return pcbnew.VECTOR2I_MM(px+offset[0],py+offset[1])
    arc = pcbnew.PCB_ARC(board)
    arc.SetNet(board.FindNet(net));arc.SetLayer(layer)
    arc.SetStart(point(2,5));arc.SetMid(point(5,2));arc.SetEnd(point(8,5))
    arc.SetWidth(pcbnew.FromMM(.25));arc.SetLocked(True);board.Add(arc)
    path=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(path),board,True)
    return path, net, point


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle,offset',[(0,(0,0)),(90,(21,37)),(37,(-9,14))])
def test_same_chord_different_bow_is_not_the_same_locked_copper(tmp_path,layer,angle,offset):
    path,net,point=fixture(tmp_path,net='RENAMED_RAIL',offset=offset,angle=angle,layer=layer)
    contract=cec_fr.copper_geometry_prefix_contract(str(path),[net])
    signature=cec_fr.copper_geometry_signature(str(path),[net])
    assert cec_fr.check_copper_geometry_prefix(str(path),contract)['ok']
    original=path.read_bytes();board=pcbnew.LoadBoard(str(path));arc=next(iter(board.GetTracks()))
    endpoints=(arc.GetStart().x,arc.GetStart().y,arc.GetEnd().x,arc.GetEnd().y)
    arc.SetMid(point(5,8))
    assert endpoints==(arc.GetStart().x,arc.GetStart().y,arc.GetEnd().x,arc.GetEnd().y)
    changed=tmp_path/'changed.kicad_pcb';pcbnew.SaveBoard(str(changed),board,True)
    result=cec_fr.check_copper_geometry_prefix(str(changed),contract)
    assert not result['ok'] and result['missing_items']==1
    assert result['missing_by_net']=={net:1}
    assert cec_fr.copper_geometry_signature(str(changed),[net])!=signature
    assert path.read_bytes()==original


def test_reversing_arc_endpoints_preserves_physical_geometry_identity(tmp_path):
    path,net,_=fixture(tmp_path)
    contract=cec_fr.copper_geometry_prefix_contract(str(path),[net])
    signature=cec_fr.copper_geometry_signature(str(path),[net])
    board=pcbnew.LoadBoard(str(path));arc=next(iter(board.GetTracks()))
    # SWIG getters are live references: copy values before mutating either end.
    a,m,b=[pcbnew.VECTOR2I(p.x,p.y) for p in (arc.GetStart(),arc.GetMid(),arc.GetEnd())]
    arc.SetStart(b);arc.SetMid(m);arc.SetEnd(a)
    target=tmp_path/'reverse.kicad_pcb';pcbnew.SaveBoard(str(target),board,True)
    assert cec_fr.check_copper_geometry_prefix(str(target),contract)['ok']
    assert cec_fr.copper_geometry_signature(str(target),[net])==signature


def test_same_net_extension_does_not_replace_a_curve(tmp_path):
    path,net,point=fixture(tmp_path)
    contract=cec_fr.copper_geometry_prefix_contract(str(path),[net])
    signature=cec_fr.copper_geometry_signature(str(path),[net])
    board=pcbnew.LoadBoard(str(path))
    line=pcbnew.PCB_TRACK(board);line.SetNet(board.FindNet(net));line.SetLayer(pcbnew.F_Cu)
    line.SetStart(point(8,5));line.SetEnd(point(10,5));line.SetWidth(pcbnew.FromMM(.25));board.Add(line)
    target=tmp_path/'extended.kicad_pcb';pcbnew.SaveBoard(str(target),board,True)
    assert cec_fr.check_copper_geometry_prefix(str(target),contract)['ok']
    assert cec_fr.copper_geometry_signature(str(target),[net])!=signature


def test_old_chord_only_receipt_is_not_silently_upgraded(tmp_path):
    path,net,_=fixture(tmp_path)
    contract=cec_fr.copper_geometry_prefix_contract(str(path),[net])
    _,rows=cec_fr._copper_geometry_rows(str(path),[net],locked_only=True)
    old_row=rows[0][:9]
    old_digest=hashlib.sha256(json.dumps(old_row,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    old=copy.deepcopy(contract);old['members']={old_digest:1};old['member_nets']={old_digest:net}
    # Old evidence does not say which curve was protected. It must be rebuilt
    # from its verified original artifact, not recaptured from a changed output.
    assert not cec_fr.check_copper_geometry_prefix(str(path),old)['ok']


def test_contract_counts_identical_curve_multiplicity(tmp_path):
    path,net,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path));first=next(iter(board.GetTracks()))
    second=pcbnew.PCB_ARC(board)
    second.SetNet(board.FindNet(net));second.SetLayer(first.GetLayer())
    second.SetStart(first.GetStart());second.SetMid(first.GetMid());second.SetEnd(first.GetEnd())
    second.SetWidth(first.GetWidth());second.SetLocked(True);board.Add(second)
    target=tmp_path/'double.kicad_pcb';pcbnew.SaveBoard(str(target),board,True)
    contract=cec_fr.copper_geometry_prefix_contract(str(target),[net])
    assert list(contract['members'].values())==[2]
    result=cec_fr.check_copper_geometry_prefix(str(path),contract)
    assert not result['ok'] and result['missing_items']==1


def test_placement_resume_cannot_accept_a_rebowed_retained_arc(tmp_path):
    from types import SimpleNamespace
    import cec_synth_pipeline as synth
    path,net,point=fixture(tmp_path)
    contract=cec_fr.copper_geometry_prefix_contract(str(path),[net])
    owner=SimpleNamespace(protected_power_prefix=contract)
    assert synth._admit_materialized_power_prefix(owner,str(path))['ok']
    board=pcbnew.LoadBoard(str(path));arc=next(iter(board.GetTracks()))
    arc.SetMid(point(5,8))
    changed=tmp_path/'changed.kicad_pcb';pcbnew.SaveBoard(str(changed),board,True)
    with pytest.raises(ValueError,match='protected power copper'):
        synth._admit_materialized_power_prefix(owner,str(changed))
