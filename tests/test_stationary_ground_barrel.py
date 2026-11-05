"""Stationary Source metal is not permission to invent a Ground link."""
import copy
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as complete
import cec_field_coupling as field
import cec_force_current as force
import cec_smd_macro_transport as transport
import cec_stationary_ground_barrel as stationary
from test_complete_macro_cell import fixture


def setup_root(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,unused,initial=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    root=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA'
        and t.GetNetname()=='GND' and t.GetDrillValue()==300000)
    return source,parent,initial['source_plan']['poses'],force._uid(root)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_barrel_can_stay_when_its_owner_moves_without_any_link_credit(tmp_path,monkeypatch,quarter,back):
    source,parent,poses,uid=setup_root(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes()
    ordinary,old=compiler.compile(source,poses,board_hint='opaque')
    private,packet=compiler.compile(source,poses,board_hint='opaque',stationary_ground_barrel_uuids=[uid])
    before=next(t for t in parent.GetTracks() if force._uid(t)==uid)
    after=next(t for t in private.GetTracks() if force._uid(t)==uid)
    moved=next(t for t in ordinary.GetTracks() if force._uid(t)==uid)
    assert tuple(after.GetPosition())==tuple(before.GetPosition())!=tuple(moved.GetPosition())
    proofs=packet['transport']['explicit_stationary_source_ground_barrels']
    assert len(proofs)==1 and proofs[0]['source_reference_via']['uuid']==uid
    assert not proofs[0]['new_local_connection_received']
    assert uid not in {q['uuid'] for q in packet['transport']['source_process_barrel_motion']}
    assert compiler.packet_options(packet)['stationary_ground_barrel_uuids']==[uid]
    prefill=compiler.pre_refill_barrel_screen(private,packet)
    assert prefill['all_carried_barrels_examined']==1+len(packet['transport']['source_process_barrel_motion'])
    assert source.read_bytes()==raw and packet['no_new_copper_or_barrels_constructed']
    assert stationary.receive(parent,proofs)[0]['no_local_ground_connection_credited_by_retention']


@pytest.mark.parametrize('bad',[None,True,'uuid',{},['not-a-source-uuid'],['a','a']])
def test_nonliteral_or_ambiguous_stationary_root_is_refused_before_native_writes(tmp_path,monkeypatch,bad):
    source,parent,poses,uid=setup_root(tmp_path,monkeypatch);raw=source.read_bytes()
    with pytest.raises((ValueError,KeyError)):
        compiler.compile(source,poses,board_hint='opaque',stationary_ground_barrel_uuids=bad)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['source','position','width','drill','net','proof','missing_reference'])
def test_source_and_saved_barrel_and_reference_contacts_are_rederived(tmp_path,monkeypatch,fault):
    source,parent,poses,uid=setup_root(tmp_path,monkeypatch)
    q=stationary.plan(parent,[uid],source_path=source,board_hint='opaque')
    child=pcbnew.LoadBoard(str(source));via=next(t for t in child.GetTracks() if force._uid(t)==uid)
    if fault=='source':q[0]['source_sha256']='not-the-source'
    elif fault=='position':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='width':via.SetWidth(via.GetWidth(via.TopLayer())+1)
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='net':via.SetNetCode(0)
    elif fault=='proof':q[0]['new_local_connection_received']=True
    else:
        from cec_native_items import discard_items
        discard_items(child,list(child.Zones()))
    with pytest.raises((ValueError,KeyError)):
        stationary.receive(child,q)


def test_keeping_a_barrel_does_not_make_an_unrouted_macro_complete(tmp_path,monkeypatch):
    source,parent,poses,uid=setup_root(tmp_path,monkeypatch)
    private,packet=compiler.compile(source,poses,board_hint='opaque',stationary_ground_barrel_uuids=[uid])
    target=tmp_path/'UNROUTED.kicad_pcb';field._save_field_snapshot(private,target)
    r=complete.receive(source,target,board_hint='opaque',stationary_ground_barrel_uuids=[uid])
    assert not r['ok'] and not r['complete'] and r['errors']


def test_non_ground_terminal_cannot_become_a_stationary_ground_root(tmp_path,monkeypatch):
    source,parent,poses,uid=setup_root(tmp_path,monkeypatch)
    v=next(t for t in parent.GetTracks() if force._uid(t)==uid)
    terminal=next(p for f in parent.GetFootprints() for p in f.Pads()
        if p.GetNetname() and p.GetNetname()!='GND')
    v.SetNet(terminal.GetNet());v.SetPosition(terminal.GetPosition())
    expected=terminal.GetNetname();assert expected!='GND' and v.GetNetname()==expected
    pcbnew.SaveBoard(str(source),parent)
    loaded=pcbnew.LoadBoard(str(source))
    assert next(t for t in loaded.GetTracks() if force._uid(t)==uid).GetNetname()==expected
    with pytest.raises(ValueError,match='qualified_literal_source_ground_barrel_required'):
        stationary.plan(loaded,[uid],source_path=source,board_hint='opaque')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_retaining_local_pofv_metal_does_not_preapprove_its_missing_new_owner_link(tmp_path,monkeypatch,quarter,back):
    source,parent,poses,unused=setup_root(tmp_path,monkeypatch,quarter,back)
    ids=[force._uid(t) for t in parent.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND']
    assert any(t.GetDrillValue()==250000 for t in parent.GetTracks() if force._uid(t) in ids)
    private,packet=compiler.compile(source,poses,board_hint='opaque',stationary_ground_barrel_uuids=ids)
    proofs=packet['transport']['explicit_stationary_source_ground_barrels']
    assert len(proofs)==len(ids) and not packet['transport']['source_process_barrel_motion']
    assert all(not q['new_local_connection_received'] for q in proofs)
    with pytest.raises(ValueError,match='stationary_ground_saved_barrel_or_live_process_changed'):
        stationary.receive(private,proofs)
