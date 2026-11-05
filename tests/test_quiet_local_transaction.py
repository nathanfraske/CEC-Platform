"""Quiet transaction dispatch uses real saved owners, not worker success.

Native fixture substitutions are limited to its explicit schematic-export
and project-resolver boundaries. No routing/role/receiving success is mocked
in the native positive and negative dispatch cases.
"""
import copy
from pathlib import Path

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_quiet_signal_completion as quiet
import root_receive_local_transaction_20261022 as transaction
from cec_native_items import discard_items
from test_field_proposals import track
from test_quiet_signal_completion import saved_fixture


KIND='quiet_signal_join'


def phase(net='/renamed_quiet',**extra):
    return dict(kind=KIND,net=net,candidate='/actual/child.kicad_pcb',candidate_sha256='a'*64,**extra)


def printing():
    return dict(kind='print_context',candidate='/actual/print.kicad_pcb',
                candidate_sha256='b'*64,proposal='/actual/print-proposal.json')


def test_quiet_phase_preserves_six_phase_budget_distinct_nets_and_print_last():
    phases=[dict(phase('/quiet'+str(i)),candidate='/actual/child'+str(i)) for i in range(5)]+[printing()]
    assert transaction.MAX_LOCAL_PHASES==6
    assert transaction.validate_phases(phases)==[KIND]*5+['print_context']
    with pytest.raises(ValueError): transaction.validate_phases([printing(),phase()])
    with pytest.raises(ValueError): transaction.validate_phases(phases[:-1]+[phase('/sixth'),printing()])


@pytest.mark.parametrize('net',[None,False,7,'','x'*257,'/N\nother','/N\x00other'])
def test_only_literal_bounded_net_names_are_phase_schema(net):
    with pytest.raises(ValueError): transaction.validate_phases([phase(net)])


@pytest.mark.parametrize('key',['role','layer','width_nm','amps','drill','timeout_s','allow_nonplane_power_role',
    'allow_locked','ok','receiving','proposal','ops'])
def test_no_caller_geometry_role_budget_or_success_fields(key):
    value=phase();value[key]=True
    with pytest.raises(ValueError): transaction.validate_phases([value])


@pytest.mark.parametrize('kinds',[(KIND,KIND),('ordinary_join',KIND),(KIND,'ordinary_join'),
    ('ordinary_columns',KIND),(KIND,'distributed_supply_join')])
def test_quiet_and_ordinary_joins_share_existing_repeated_net_ban(kinds):
    phases=[dict(phase(),kind=kind,candidate='/actual/'+str(i)) for i,kind in enumerate(kinds)]
    with pytest.raises(ValueError): transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_public_dispatch_rederives_actual_saved_parent_under_rotations_and_faces(tmp_path,monkeypatch,quarter,back):
    source,child,hint,proposal=saved_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    original=tmp_path/'older-original.kicad_pcb';original.write_text('Not the actual saved Source parent')
    value=dict(phase(proposal['net']),candidate=str(child),candidate_sha256=force._hash(child))
    calls=[];public=quiet.receive
    def real_receive(*args,**kwargs):
        calls.append((args,kwargs));return public(*args,**kwargs)
    monkeypatch.setattr(transaction.quiet_signal_join,'receive',real_receive)
    before=[p.read_bytes() for p in (original,source,child)]
    actual,proof=transaction.receive_phase(original,source,value,hint)
    assert actual==child and proof['ok']is True and proof['complete']is True
    assert calls==[((source,child),dict(board_hint=hint,net=proposal['net'],timeout_s=10.))]
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert proof['source_class_preserved'] and proof['whole_shared_stage_still_required']
    assert len(proof['mandatory_shared_receiving'])==9
    assert not any(proof[k] for k in ('routing_admitted','current_qualified','adc_mode_qualified',
                                      'load_qualified','release_authority'))
    assert before==[p.read_bytes() for p in (original,source,child)]


def dispatch_files(tmp_path):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source dispatch identity')
    child=tmp_path/'child.kicad_pcb';child.write_text('candidate dispatch identity')
    value=dict(phase(),candidate=str(child),candidate_sha256=force._hash(child))
    return source,child,value


@pytest.mark.parametrize('fault',['stale_hash','same_path','hardlink','missing_file','missing_net',
    'extra_success','bad_hash_schema','bad_net'])
def test_standalone_dispatch_refuses_bad_identity_and_schema_before_public_receiver(tmp_path,monkeypatch,fault):
    source,child,value=dispatch_files(tmp_path)
    monkeypatch.setattr(transaction.quiet_signal_join,'receive',lambda *a,**kw:pytest.fail('invalid phase dispatched'))
    if fault=='stale_hash': child.write_text('changed since declared identity')
    elif fault=='same_path': value.update(candidate=str(source),candidate_sha256=force._hash(source))
    elif fault=='hardlink':
        alias=tmp_path/'alias.kicad_pcb';alias.hardlink_to(source)
        value.update(candidate=str(alias),candidate_sha256=force._hash(alias))
    elif fault=='missing_file': value['candidate']=str(tmp_path/'missing.kicad_pcb')
    elif fault=='missing_net': del value['net']
    elif fault=='extra_success': value['ok']=True
    elif fault=='bad_hash_schema': value['candidate_sha256']='A'*64
    else: value['net']=True
    with pytest.raises((AssertionError,ValueError,FileNotFoundError)):
        transaction.receive_phase(source,source,value,'actual-Source')


@pytest.mark.parametrize('failed',[dict(ok=False,complete=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_public_refusal_or_incomplete_result_cannot_be_relabelled_as_success(tmp_path,monkeypatch,failed):
    source,child,value=dispatch_files(tmp_path)
    monkeypatch.setattr(transaction.quiet_signal_join,'receive',lambda *a,**kw:copy.deepcopy(failed))
    with pytest.raises(AssertionError): transaction.receive_phase(source,source,value,'actual-Source')


@pytest.mark.parametrize('fault',['width','orphan','missing_join','source_pin','source_role','unknown_exact_net','literal_wrong_net'])
def test_fresh_public_quiet_receiver_negatives_remain_mandatory_through_dispatch(tmp_path,monkeypatch,fault):
    source,child,hint,proposal=saved_fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child));tracks=list(board.GetTracks())
    if fault=='width': tracks[0].SetWidth(250000)
    elif fault=='orphan': track(board,proposal['net'],(30,30),(31,30),width=.2)
    elif fault=='missing_join': discard_items(board,tracks)
    elif fault=='source_pin': quiet._pads(board,proposal['request'])[1].SetNumber('24')
    elif fault=='source_role':
        root=Path(hint)
        original=root.read_text();changed=original.replace('(pin output ','(pin input ')
        assert changed!=original;root.write_text(changed)
    elif fault=='literal_wrong_net':
        for item in tracks: item.SetNet(board.FindNet('+3V3'))
    if fault not in ('source_role','unknown_exact_net'):
        if fault=='literal_wrong_net': pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
        else: field._save_field_snapshot(board,child)
    value=dict(phase(proposal['net'] if fault!='unknown_exact_net' else ' '+proposal['net']),
               candidate=str(child),candidate_sha256=force._hash(child))
    before=[p.read_bytes() for p in (source,child)]
    with pytest.raises(AssertionError): transaction.receive_phase(source,source,value,hint)
    assert before==[p.read_bytes() for p in (source,child)]


def current_phase(cuts,**extra):
    return dict(kind='full_current_planar_reflow',candidate='/actual/current-child',
                candidate_sha256='a'*64,retired_track_uuids=cuts,**extra)


def six_phase_current_quiet_cohort():
    return [current_phase(['Source-force-LO']),
        dict(kind='ordinary_source_reflow',candidate='/actual/FAN',candidate_sha256='b'*64,
             net='/FAN',retired_track_uuids=['Source-FAN-stroke'],allow_locked_track_uuids=[]),
        dict(kind='source_ordinary_barrel_reseat',candidate='/actual/GPIO',candidate_sha256='c'*64,
             via_uuid='Source-GPIO-barrel'),
        dict(current_phase(['Source-supply']),candidate='/actual/supply'),
        phase(),printing()]


def test_two_disjoint_current_preclears_compose_with_ordinary_barrel_quiet_and_final_print():
    rows=six_phase_current_quiet_cohort()
    assert transaction.MAX_LOCAL_PHASES==6
    assert transaction.validate_phases(rows)==[r['kind'] for r in rows]
    with pytest.raises(ValueError): transaction.validate_phases(rows[:-1]+[phase('/extra'),printing()])
    with pytest.raises(ValueError): transaction.validate_phases(rows[:-2]+[printing(),phase()])


@pytest.mark.parametrize('second',[['a'],['b','a'],['new','a'],['b','new']])
def test_repeated_or_partly_overlapping_full_current_source_cuts_are_not_new_attempts(second):
    with pytest.raises(ValueError):
        transaction.validate_phases([current_phase(['a','b']),current_phase(second)])


@pytest.mark.parametrize('cuts',[[],True,[True],[''],['a','a'],list('123456789'),None,{'caller':'scope'}])
def test_full_current_cut_identity_validation_is_not_weakened(cuts):
    with pytest.raises((ValueError,TypeError)):
        transaction.validate_phases([current_phase(cuts)])


def test_disjoint_current_phases_still_cannot_supply_ratings_or_work_overrides():
    for extra in (dict(current_qualified=True),dict(amps=1),dict(timeout_s=30),dict(max_source_track_mm=32)):
        with pytest.raises(ValueError):
            transaction.validate_phases([current_phase(['a']),current_phase(['b'],**extra)])


def test_two_distinct_saved_current_dispatches_rederive_each_immediate_parent(tmp_path,monkeypatch):
    import cec_additive_route_receiving as additive
    import cec_full_current_planar_reflow as full
    from test_lastmile import _board
    nets=['/synthetic/force','/synthetic/supply']
    board=_board([(x,y,net) for net,y in zip(nets,(10,20)) for x in (5,10)],edge=(0,0,30,30))
    old=[]
    for net,y in zip(nets,(10,20)):
        item=track(board,net,(5,y),(10,y),width=.2);item.SetLocked(True);old.append(force._uid(item))
    original=tmp_path/'current-source.kicad_pcb';field._save_field_snapshot(board,original)
    # Synthetic authority catalogs only, identical to the existing native
    # full-current fixture. Real saved boundary/current receivers run twice.
    contracts={net:dict(net=net,required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},
        routing_layers=['F.Cu','B.Cu'],current_authority=dict(amps=.5,geometry_margin=1.25,
        margin_included=False,source='board_design_basis')) for net in nets}
    domains={net:dict(net=net,complete=True,source_refs=['source'],sink_refs=['sink']) for net in nets}
    monkeypatch.setattr(full.topology,'route_width_contracts',lambda *a,**kw:copy.deepcopy(contracts))
    monkeypatch.setattr(full.topology,'board_current_domains',lambda *a,**kw:copy.deepcopy(domains))
    calls=[];public=full.receive
    def real_receive(*args,**kwargs):
        calls.append((args,kwargs));return public(*args,**kwargs)
    monkeypatch.setattr(transaction.full_current_planar,'receive',real_receive)
    parent=original;rows=[];parent_bytes=original.read_bytes()
    for index,(net,y,uid) in enumerate(zip(nets,(10,20),old)):
        candidate=force._copy_family(parent,tmp_path/('current-child-'+str(index)))
        child=pcbnew.LoadBoard(str(candidate))
        discard_items(child,[t for t in child.GetTracks() if force._uid(t)==uid])
        for a,z in [((5,y),(5.5,y+.5)),((5.5,y+.5),(9.5,y+.5)),((9.5,y+.5),(10,y))]:
            track(child,net,a,z,width=.2)
        field._save_field_snapshot(child,candidate)
        candidate=Path(additive.finalize_private(parent,candidate,tmp_path/('current-final-'+str(index)))['board'])
        value=dict(current_phase([uid]),candidate=str(candidate),candidate_sha256=force._hash(candidate))
        selected,proof=transaction.receive_phase(original,parent,value,'synthetic')
        assert selected==candidate and proof['ok']is True and proof['complete']is True
        assert proof['source_width_and_current_exact'] and proof['all_surviving_native_partitions_preserved']
        assert not proof['routing_admitted'] and not proof['current_authority'] and not proof['release_authority']
        assert calls[-1]==((parent,candidate),dict(board_hint='synthetic',retired_track_uuids=[uid],timeout_s=10.))
        rows.append(value);parent=candidate
    assert len(calls)==2 and calls[1][0][0]==calls[0][0][1]
    assert transaction.validate_phases(rows)==['full_current_planar_reflow']*2
    assert original.read_bytes()==parent_bytes
