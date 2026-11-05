"""Exact metadata-only normalization with real native Source and saved deltas."""
import copy,json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_full_width_endpoint_group as op
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,*,quarter=0,back=False,width=.5,rules=True):
    net='/RENAMED/WHOLE_RAIL_491';board=_board([(5,8,net),(8,8,net)],edge=(0,0,30,30))
    selected=track(board,net,(5,8),(8,8),width=width,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    selected.SetLocked(True)
    peer=track(board,net,(12,12),(13,12),width=.15)
    group=pcbnew.PCB_GROUP(board);group.SetName(op.fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group)
    group.AddItem(selected);group.AddItem(peer)
    center=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    for fp in board.GetFootprints():fp.Rotate(center,angle)
    for t in board.GetTracks():t.Rotate(center,angle)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    if rules:
        source.with_suffix('.kicad_dru').write_text('(version 1)\n# existing generated exception\n'
            '(rule "CEC guarded local endpoint neckdown"\n'
            ' (condition "A.Type == \'Track\' && A.memberOfGroup(\'CEC_LOCAL_ENDPOINT_NECKDOWN\')")\n'
            ' (constraint track_width (min 0.200mm)))\n')
    contract=dict(net=net,required_by_layer_mm={'F.Cu':width,'B.Cu':width},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    domains={net:dict(net=net,complete=True,source_refs=['SourcePort'],sink_refs=['LoadPort'])}
    return source,force._uid(selected),force._uid(peer),force._uid(group),net,contract,domains


@contextmanager
def catalog(net,contract,domains):
    # Explicit synthetic Source catalogs, never a production load inference.
    # Actual native topology, literal delta, rules, locks and widths are real.
    with patch.object(op.current.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(op.current.topology,'board_current_domains',return_value=domains):
        yield


def build(tmp_path,**kwargs):
    source,uid,peer,group,net,contract,domains=fixture(tmp_path,**kwargs)
    with catalog(net,contract,domains):
        q=json.loads(json.dumps(op.plan(source,[uid],board_hint='synthetic')))
        result=op.construct(source,tmp_path/'metadata-only',q)
    assert result['ok']and result['complete'],result
    return source,Path(result['candidate']),q,uid,peer,group,net,contract,domains


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('width',[.5,1.])
def test_complete_saved_metadata_delta_preserves_all_copper_locks_parts_rules(tmp_path,quarter,back,width):
    source,child,q,uid,peer,group,net,contract,domains=build(tmp_path,quarter=quarter,back=back,width=width)
    raw=source.read_bytes();sidecars=force._sidecars(source)
    with catalog(net,contract,domains):proof=op.receive(source,child,json.loads(json.dumps(q)))
    assert proof['ok']and proof['complete'],proof
    assert proof['exact_literal_membership_only_replay']and proof['all_native_copper_parts_locks_and_rules_unchanged']
    assert proof['current_and_class_rederived_on_actual_saved_candidate']
    assert not proof['current_qualified']and not proof['routing_admitted']and not proof['release_authority']
    a,*_=op.literal._inventory(op.raw.raw_text(source));b,*_=op.literal._inventory(op.raw.raw_text(child))
    assert a.keys()==b.keys()and{u for u in a if a[u][2]!=b[u][2]}=={group}
    assert op.literal._members(b[group][2])[1]==[peer]
    board=pcbnew.LoadBoard(str(child));live={force._uid(t):t for t in board.GetTracks()}
    assert live[uid].IsLocked()and live[uid].GetParentGroup()is None
    assert source.read_bytes()==raw and force._sidecars(source)==sidecars


@pytest.mark.parametrize('fault',['narrow','unknown_current','incomplete_current','mixed_group','wrong_group',
    'locked_group','nested_group','duplicate_group_name','arc','mask','unknown_uid','all_members','duplicate','boolean_uid'])
def test_membership_name_does_not_grant_current_geometry_or_group_unlock_authority(tmp_path,fault):
    source,uid,peer,group,net,contract,domains=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    g=next(g for g in board.Groups()if force._uid(g)==group);request=[uid]
    if fault=='narrow':live[uid].SetWidth(499999)
    elif fault=='unknown_current':contract['current_authority']['source']='unverified_guess'
    elif fault=='incomplete_current':domains[net]['complete']=False
    elif fault=='mixed_group':
        fp=next(iter(board.GetFootprints()));g.AddItem(fp)
    elif fault=='wrong_group':g.SetName('ARBITRARY_PROTECTED_POWER_GROUP')
    elif fault=='locked_group':g.SetLocked(True)
    elif fault=='nested_group':
        outer=pcbnew.PCB_GROUP(board);board.Add(outer);outer.AddItem(g)
    elif fault=='duplicate_group_name':
        outer=pcbnew.PCB_GROUP(board);outer.SetName(op.fr.ENDPOINT_NECKDOWN_GROUP);board.Add(outer)
        # Native saves omit empty groups. Keep the duplicate name present in
        # the actual saved Source rather than only in the transient board.
        duplicate=track(board,net,(18,18),(19,18),width=.5)
        outer.AddItem(duplicate)
    elif fault=='arc':
        item=pcbnew.PCB_ARC(board);item.SetNet(board.FindNet(net));board.Add(item);g.AddItem(item);request=[force._uid(item)]
    elif fault=='mask':live[uid].SetHasSolderMask(True)
    elif fault=='unknown_uid':request=['not-a-native-identity']
    elif fault=='all_members':request=[uid,peer];live[peer].SetWidth(500000)
    elif fault=='duplicate':request=[uid,uid]
    else:request=[True]
    field._save_field_snapshot(board,source);before=source.read_bytes()
    with catalog(net,contract,domains),pytest.raises(ValueError):op.plan(source,request,board_hint='synthetic')
    assert before==source.read_bytes()


@pytest.mark.parametrize('fault',['stronger_width','clearance','functional','max_width','negated','pattern',
    'uuid_alias','additional_constraint','unknown_form','other_group_pattern'])
def test_unchanged_rule_bytes_cannot_hide_removed_functional_membership_gates(tmp_path,fault):
    source,uid,peer,group,net,contract,domains=fixture(tmp_path)
    rule=source.with_suffix('.kicad_dru');text=rule.read_text()
    if fault=='stronger_width':text=text.replace('0.200mm','0.501mm')
    elif fault=='clearance':text=text.replace('track_width','clearance')
    elif fault=='functional':text=text.replace('(constraint track_width (min 0.200mm))','(constraint disallow track)')
    elif fault=='max_width':text=text.replace('(min 0.200mm)','(max 0.200mm)')
    elif fault=='negated':text=text.replace("A.Type == 'Track' && A.memberOfGroup", "A.Type == 'Track' && !A.memberOfGroup")
    elif fault=='pattern':text=text.replace('CEC_LOCAL_ENDPOINT_NECKDOWN','CEC_LOCAL_.*')
    elif fault=='uuid_alias':text=text.replace('CEC_LOCAL_ENDPOINT_NECKDOWN',group)
    elif fault=='additional_constraint':text=text.replace('(constraint track_width', '(constraint clearance (min 0.5mm)) (constraint track_width')
    elif fault=='unknown_form':text+='(include "external-rules")\n'
    else:text+='(rule "other" (condition "A.memberOfGroup(\'.*\')") (constraint clearance (min 1mm)))\n'
    rule.write_text(text);before=source.read_bytes()
    with catalog(net,contract,domains),pytest.raises(ValueError):op.plan(source,[uid],board_hint='synthetic')
    assert before==source.read_bytes()


@pytest.mark.parametrize('fault',['proposal_source','proposal_current','proposal_membership','integer_false','float_false',
    'track','locked_track','part','peer_membership','group_name','extra_rule','sidecar'])
def test_forged_scope_or_unowned_saved_changes_cannot_pass_independent_replay(tmp_path,fault):
    source,child,q,uid,peer,group,net,contract,domains=build(tmp_path)
    board=pcbnew.LoadBoard(str(child));live={force._uid(t):t for t in board.GetTracks()}
    if fault=='proposal_source':q['source_sha256']='0'*64
    elif fault=='proposal_current':q['actual_full_width_Source_members'][uid]['unchanged_whole_current_contract']['current_authority']['amps']=.01
    elif fault=='proposal_membership':q['group_member_retirements'][group]=[peer]
    elif fault=='integer_false':q['copper_retired']=0
    elif fault=='float_false':q['routing_admitted']=0.0
    elif fault=='track':live[uid].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='locked_track':live[uid].SetLocked(False)
    elif fault=='part':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='peer_membership':next(iter(board.Groups())).RemoveItem(live[peer])
    elif fault=='group_name':next(iter(board.Groups())).SetName('CHANGED')
    elif fault=='extra_rule':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:child.with_suffix('.kicad_pro').write_text(json.dumps({'unreceived':True}))
    if fault in('track','locked_track','part','peer_membership','group_name'):field._save_field_snapshot(board,child)
    with catalog(net,contract,domains):proof=op.receive(source,child,q)
    assert not proof['ok']and proof['errors'],proof


@pytest.mark.parametrize('timeout',[None,True,0,10.1,float('nan'),float('inf')])
def test_exact_member_transaction_has_finite_strict_native_lease(tmp_path,timeout):
    source,uid,peer,group,net,contract,domains=fixture(tmp_path)
    with catalog(net,contract,domains),pytest.raises(ValueError):op.plan(source,[uid],board_hint='synthetic',timeout_s=timeout)


def test_no_custom_rule_file_does_not_create_or_relax_any_rule(tmp_path):
    source,child,q,uid,peer,group,net,contract,domains=build(tmp_path,rules=False)
    assert not q['Source_group_rule_scope']['custom_rule_file_present']
    assert not child.with_suffix('.kicad_dru').exists()


def test_saved_receiver_rederives_actual_child_current_catalog_not_old_proposal(tmp_path,monkeypatch):
    source,child,q,uid,peer,group,net,contract,domains=build(tmp_path)
    before=copy.deepcopy(contract);changed=copy.deepcopy(contract);changed['current_authority']['amps']=.6
    with patch.object(op.current.topology,'route_width_contracts',side_effect=[{net:before},{net:changed}]), \
         patch.object(op.current.topology,'board_current_domains',return_value=domains):
        proof=op.receive(source,child,q)
    assert not proof['ok']and any('saved_full_current_and_class'in e for e in proof['errors'])
