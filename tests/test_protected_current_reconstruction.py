"""Synthetic catalogs only; all cuts, native retention and replays are real."""
import copy
from pathlib import Path
from types import SimpleNamespace
import time

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as reflow
import cec_protected_current_reconstruction as receiving
import root_receive_local_transaction_20261022 as transaction
from cec_native_items import discard_items
from test_field_proposals import track
from test_full_current_planar_reflow import fixture as native_fixture


def fixture(tmp_path, monkeypatch, quarter=0, face='F.Cu'):
    source, unused, uid, net, contract, domains = native_fixture(tmp_path,
        quarter=quarter, face=face, prefix='/renamed-%s/' % quarter)
    parent = pcbnew.LoadBoard(str(source))
    # A separate locked member on the same current net must survive. It is
    # deliberately not part of the reconstructing owner's cut.
    extra = track(parent, net, (22,22), (24,22), width=1.)
    extra.SetLocked(True)
    field._save_field_snapshot(parent, source)
    child = force._copy_family(source, tmp_path/'with-retained-source')
    board = pcbnew.LoadBoard(str(child))
    old = next(t for t in board.GetTracks() if force._uid(t)==uid)
    a, z = tuple(old.GetStart()), tuple(old.GetEnd())
    dx, dy = z[0]-a[0], z[1]-a[1]
    # Cardinal rotation of the same canonical half-mm local detour.
    ux, uy = dx//5000000, dy//5000000
    points = [a, (a[0]+500000*(ux-uy), a[1]+500000*(uy+ux)),
        (z[0]-500000*(ux+uy), z[1]+500000*(ux-uy)), z]
    discard_items(board, [old])
    for start, end in zip(points,points[1:]):
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(board.FindNet(net)); item.SetLayer(board.GetLayerID(face))
        item.SetWidth(1000000); item.SetStart(pcbnew.VECTOR2I(*start))
        item.SetEnd(pcbnew.VECTOR2I(*end)); board.Add(item)
    field._save_field_snapshot(board, child)
    child = Path(additive.finalize_private(source, child, tmp_path/'received-descendant')['board'])
    monkeypatch.setattr(reflow.topology, 'board_current_domains', lambda *a,**k: copy.deepcopy(domains))
    monkeypatch.setattr(reflow.topology, 'route_width_contracts', lambda *a,**k: {net:copy.deepcopy(contract)})
    # Explicit synthetic protected-power catalog, not a production netname.
    monkeypatch.setattr(fr, 'locked_pour_authority_nets_board', lambda *a,**k: {net})
    row = dict(kind='full_current_planar_reflow', candidate=str(child),
        candidate_sha256=force._hash(child), retired_track_uuids=[uid])
    return source, child, row, force._uid(extra), net, contract, domains


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',['F.Cu','In2.Cu'])
def test_exact_reconstruction_changes_obligation_not_current_or_other_copper(tmp_path,monkeypatch,quarter,face):
    source, child, row, extra, net, contract, domains = fixture(tmp_path,monkeypatch,quarter,face)
    before = [p.read_bytes() for p in (source,child)]
    result = receiving.receive(source,child,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert result['ok'] is True and result['complete'] is True,result
    assert not result['literal_original_prefix']['ok']
    manifest = result['native_reconstruction_manifest']
    assert manifest['retired_original_locked_members']==1
    assert manifest['retained_original_locked_members']==1
    assert manifest['obligatory_replacement_members']==3
    assert result['source_copper']['expected_items']==4
    assert result['untouched_source_members_exact'] and result['replacements_are_retention_obligations']
    assert not any(result[k] for k in ('routing_admitted','current_authority','current_qualified',
        'full_kelvin_qualification','release_authority'))
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('fault',['replacement_missing','replacement_width','retained_missing',
    'retained_shape','retained_layer','retained_net'])
def test_final_descendant_cannot_lose_or_reshape_any_old_or_replacement_obligation(tmp_path,monkeypatch,fault):
    source, child, row, extra, net, contract, domains = fixture(tmp_path,monkeypatch)
    final = force._copy_family(child,tmp_path/'later-descendant')
    board = pcbnew.LoadBoard(str(final))
    retained = next(t for t in board.GetTracks() if force._uid(t)==extra)
    replacement = next(t for t in board.GetTracks() if force._uid(t)!=extra)
    if fault=='replacement_missing': discard_items(board,[replacement])
    elif fault=='replacement_width': replacement.SetWidth(999999)
    elif fault=='retained_missing': discard_items(board,[retained])
    elif fault=='retained_shape': retained.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='retained_layer': retained.SetLayer(pcbnew.B_Cu)
    else:
        board.Add(pcbnew.NETINFO_ITEM(board,'UNOWNED'))
        retained.SetNet(board.FindNet('UNOWNED'))
    field._save_field_snapshot(board,final)
    result = receiving.receive(source,final,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert not result['ok'] and result['errors'],result
    assert not result['source_copper']['ok']


@pytest.mark.parametrize('fault',['narrow','pose','via','unknown_current','incomplete'])
def test_current_owner_still_has_to_receive_the_actual_saved_reconstruction(tmp_path,monkeypatch,fault):
    source, child, row, extra, net, contract, domains = fixture(tmp_path,monkeypatch)
    board = pcbnew.LoadBoard(str(child))
    if fault=='narrow': next(t for t in board.GetTracks() if force._uid(t)!=extra).SetWidth(999999)
    elif fault=='pose': next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='via':
        via=pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(7,10.5))
        via.SetWidth(600000); via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); via.SetNet(board.FindNet(net)); board.Add(via)
    elif fault=='unknown_current': contract['current_authority']['source']='invented_load'
    else: domains[net]['complete']=False
    field._save_field_snapshot(board,child)
    row['candidate_sha256']=force._hash(child)
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert not result['ok'] and result['errors'],result
    assert 'native_reconstruction_manifest' not in result


@pytest.mark.parametrize('field_name',['ok','receiving','contract','amps','width_nm','allow_locked','timeout_s'])
def test_worker_success_or_geometry_fields_never_supply_ownership(tmp_path,monkeypatch,field_name):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    row[field_name]=True
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row])
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('fault',['stale_hash','uppercase_hash','empty_cut','duplicate_cut','wrong_kind',
    'same_parent','hardlink','missing_child'])
def test_exact_saved_phase_schema_and_identity_are_mandatory(tmp_path,monkeypatch,fault):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    if fault=='stale_hash': row['candidate_sha256']='a'*64
    elif fault=='uppercase_hash': row['candidate_sha256']=row['candidate_sha256'].upper()
    elif fault=='empty_cut': row['retired_track_uuids']=[]
    elif fault=='duplicate_cut': row['retired_track_uuids']*=2
    elif fault=='wrong_kind': row['kind']='ordinary_reflow'
    elif fault=='same_parent': row.update(candidate=str(source),candidate_sha256=force._hash(source))
    elif fault=='hardlink':
        alias=tmp_path/'alias.kicad_pcb'; alias.hardlink_to(child)
        row['candidate']=str(alias)
    else: row['candidate']=str(tmp_path/'missing.kicad_pcb')
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row])
    assert not result['ok'] and result['errors'],result


def test_no_declared_reconstruction_stays_strict_and_does_not_use_a_newer_board(tmp_path,monkeypatch):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    literal=receiving.receive(source,source,board_hint='synthetic',phases=[])
    assert literal['ok'] and literal['complete']
    result=receiving.receive(source,child,board_hint='synthetic',phases=[])
    assert not result['ok'] and 'independent_full_current_chain' not in result


def test_two_disjoint_saved_current_repairs_preserve_every_replacement(tmp_path,monkeypatch):
    source, first, row, extra, net, *_ = fixture(tmp_path,monkeypatch)
    second=force._copy_family(first,tmp_path/'second-current-parent')
    board=pcbnew.LoadBoard(str(second))
    discard_items(board,[t for t in board.GetTracks() if force._uid(t)==extra])
    for a,z in [((22,22),(22.5,22.5)),((22.5,22.5),(23.5,22.5)),((23.5,22.5),(24,22))]:
        track(board,net,a,z,width=1.)
    field._save_field_snapshot(board,second)
    second=Path(additive.finalize_private(first,second,tmp_path/'second-current-final')['board'])
    row2=dict(kind='full_current_planar_reflow',candidate=str(second),
        candidate_sha256=force._hash(second),retired_track_uuids=[extra])
    result=receiving.receive(source,second,board_hint='synthetic',phases=[row,row2],per_phase_leases=True)
    assert result['ok'] and result['complete'],result
    manifest=result['native_reconstruction_manifest']
    assert manifest['retired_original_locked_members']==2
    assert manifest['obligatory_replacement_members']==6
    assert result['source_copper']['expected_items']==6


def test_later_cut_cannot_retire_newly_constructed_current_material(tmp_path,monkeypatch):
    source, first, row, extra, net, *_ = fixture(tmp_path,monkeypatch)
    second=force._copy_family(first,tmp_path/'repeated-new-cut')
    board=pcbnew.LoadBoard(str(second))
    incoming=next(t for t in board.GetTracks() if force._uid(t)!=extra)
    row2=dict(kind='full_current_planar_reflow',candidate=str(second),
        candidate_sha256=force._hash(second),retired_track_uuids=[force._uid(incoming)])
    result=receiving.receive(source,second,board_hint='synthetic',phases=[row,row2],per_phase_leases=True)
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('fault',['family','code'])
def test_identity_change_after_a_real_current_proof_is_not_receiving(tmp_path,monkeypatch,fault):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    real=receiving.chain.receive
    def changed(*args,**kwargs):
        result=real(*args,**kwargs)
        assert result['ok'],result
        if fault=='family': source.with_suffix('.new-authority.json').write_text('{}')
        else:
            epoch=force._code_identity()
            monkeypatch.setattr(force,'_code_identity',lambda:dict(epoch,changed_source='a'*64))
        return result
    monkeypatch.setattr(receiving.chain,'receive',changed)
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert not result['ok'] and any('changed' in e for e in result['errors']),result


def test_finished_geometry_after_deadline_is_still_refused(tmp_path,monkeypatch):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    real=receiving._reconstruct
    monotonic=time.monotonic
    def late(*args,**kwargs):
        value=real(*args,**kwargs)
        monkeypatch.setattr(receiving,'time',SimpleNamespace(monotonic=lambda:monotonic()+11))
        return value
    monkeypatch.setattr(receiving,'_reconstruct',late)
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert not result['ok'] and any('deadline' in e for e in result['errors']),result


def test_pair_physics_cannot_be_bypassed_by_receiving_a_power_cut(tmp_path,monkeypatch):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(receiving.protected,'check_qualified_pairs',
        lambda *a,**kw: dict(ok=False,applicable=True,pairs=[dict(ok=False)]))
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row],per_phase_leases=True)
    assert not result['ok'] and result['errors'] and not result['qualified_pairs']['ok']


@pytest.mark.parametrize('seconds',[True,False,0,-1,10.01,float('nan'),float('inf'),'10'])
def test_no_constituent_deadline_override(tmp_path,monkeypatch,seconds):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    result=receiving.receive(source,child,board_hint='synthetic',phases=[row],timeout_s=seconds)
    assert not result['ok'] and result['errors']


def test_local_transaction_uses_fresh_owner_and_preserves_failed_literal_evidence(tmp_path,monkeypatch):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    result=transaction.protected_copper_reports(source,child,scope_source=source,
        board_hint='synthetic',phases=[row])
    assert not result['literal_source_copper']['ok']
    assert result['source_copper']['ok'] and result['qualified_pairs']['ok']
    assert result['typed_protected_current_reconstruction']['ok']


@pytest.mark.parametrize('position',['not_leading','different_source','no_phase'])
def test_other_phase_kinds_and_baseline_bridges_cannot_borrow_this_owner(tmp_path,monkeypatch,position):
    source, child, row, *_ = fixture(tmp_path,monkeypatch)
    phases=[row]; original=source
    if position=='not_leading': phases=[dict(kind='quiet_signal_join'),row]
    elif position=='different_source': original=child
    else: phases=[]
    monkeypatch.setattr(transaction.protected_current,'receive',
        lambda *a,**kw: pytest.fail('unowned reconstruction dispatched'))
    result=transaction.protected_copper_reports(source,child,scope_source=original,
        board_hint='synthetic',phases=phases)
    assert not result['source_copper']['ok'] and 'typed_protected_current_reconstruction' not in result
