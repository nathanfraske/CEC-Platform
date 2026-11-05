"""Actual native source requests and saved-chain receiving, not route mocks."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_current_topology as topology
from cec_native_items import discard_items
from test_measurement_terminal_route import fixture as route_fixture


def case(tmp_path,monkeypatch,quarter=0,renamed=True,back=False):
    board,_demand,root,target=route_fixture(quarter)
    anchor=target.GetParentFootprint();owner=root.GetParentFootprint()
    if renamed:owner.SetReference('RENAMED_INPUT_DEVICE');anchor.SetReference('RENAMED_REAL_SHUNT')
    if back:
        pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Flip(pivot,True)
    domains={n.GetNetname():dict(complete=True,authority_refs=[anchor.GetReference()])
             for n in board.GetNetInfo().NetsByNetcode().values()if n.GetNetname()}
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:copy.deepcopy(domains))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    return source,force._uid(root),force._uid(target)


def module():
    import cec_isolated_measurement_completion as op
    return op


def plan(source,pad_uuid):
    return module().plan(pcbnew.LoadBoard(str(source)),source,board_hint='RENAMED_SOURCE',pad_uuid=pad_uuid,timeout_s=10.)


def refused(call):
    try:result=call()
    except (ValueError,RuntimeError):return
    assert result.get('complete') is not True or result.get('ok') is False,result


def child(source,tmp_path,pad_uuid,target_uuid,fault=None):
    candidate=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(candidate));pads={force._uid(p):p for f in b.GetFootprints()for p in f.Pads()};root=pads[pad_uuid];target=pads[target_uuid];width=200000;points=[tuple(root.GetPosition()),tuple(target.GetPosition())]
    if fault=='thin':width=100000
    elif fault=='wrong_width':width=250000
    elif fault=='wide':width=400000
    elif fault=='wrong_target':points[-1]=tuple(b.FindFootprintByReference('SERIES_A').FindPadByNumber('left').GetPosition())
    elif fault=='force_contact':points[-1]=(24000000,10000000)
    elif fault=='noncanonical':points.insert(1,(15000000,11000000))
    elif fault=='missing_join':points[-1]=(19000000,10000000)
    if fault=='source_cut':discard_items(b,[t for t in b.GetTracks()])
    if fault=='source_pin':root.SetNumber('forged_input_pin')
    if fault=='moved_owner':root.GetParentFootprint().Move(pcbnew.VECTOR2I_MM(.1,0))
    for a,c in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*c));t.SetWidth(width);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(root.GetNetCode()if fault!='wrong_net'else b.GetNetcodeFromNetname('FORCE_B'));b.Add(t)
    if fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(root.GetPosition());v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(root.GetNet());b.Add(v)
    if fault=='orphan':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(40,20));t.SetEnd(pcbnew.VECTOR2I_MM(41,20));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(root.GetNet());b.Add(t)
    if fault=='back_track':
        for t in b.GetTracks():
            if t.GetWidth()==200000:t.SetLayer(pcbnew.B_Cu)
    if fault=='new_group':
        g=pcbnew.PCB_GROUP(b);g.SetName('unowned_worker_annotation');b.Add(g)
        g.AddItem(next(t for t in b.GetTracks()if t.GetWidth()==200000))
    if fault=='no_new_route':
        discard_items(b,[t for t in b.GetTracks()if t.GetWidth()==200000])
    if fault=='wrong_net':
        # Intentionally malformed authored evidence: the safer snapshot
        # helper rejects this short before saved receiving can examine it.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate),b)
    else:field._save_field_snapshot(b,candidate)
    return candidate


@pytest.mark.parametrize('quarter',range(4))
def test_plan_is_fresh_source_named_front_only_nonload_request(tmp_path,monkeypatch,quarter):
    source,uid,target=case(tmp_path,monkeypatch,quarter);before=source.read_bytes();q=plan(source,uid)
    assert q['complete'],q
    assert q['request']['demand']['pad_uuid']==uid and q['request']['demand']['target_uuid']==target
    assert q['request']['width_nm']==200000
    assert q['request']['demand']['source_topology']['kind']=='direct'
    assert source.read_bytes()==before


@pytest.mark.parametrize('quarter',range(4))
def test_actual_saved_renamed_rotated_chain_receives_without_source_change(tmp_path,monkeypatch,quarter):
    source,uid,target=case(tmp_path,monkeypatch,quarter);candidate=child(source,tmp_path,uid,target);before=[p.read_bytes()for p in (source,candidate)]
    result=module().receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,timeout_s=10.)
    assert result['ok']and result['complete'],result
    assert [p.read_bytes()for p in (source,candidate)]==before
    assert not result.get('release_authority',False)and not result.get('current_authority',False)


@pytest.mark.parametrize('fault',['thin','wrong_width','wide','wrong_target','force_contact','noncanonical',
    'missing_join','source_cut','source_pin','moved_owner','wrong_net','via','orphan','back_track','new_group','no_new_route'])
def test_saved_delta_cannot_gain_unowned_or_nonfront_or_incomplete_geometry(tmp_path,monkeypatch,fault):
    source,uid,target=case(tmp_path,monkeypatch);candidate=child(source,tmp_path,uid,target,fault)
    refused(lambda:module().receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,timeout_s=10.))


def test_back_surface_not_authorized_by_front_no_via_policy(tmp_path,monkeypatch):
    source,uid,target=case(tmp_path,monkeypatch,back=True)
    refused(lambda:plan(source,uid))


@pytest.mark.parametrize('fault',['unknown_uuid','power_pin','wrong_mpn','wrong_package','dnp','filtered'])
def test_plan_does_not_infer_missing_manufacturer_or_direct_shunt_authority(tmp_path,monkeypatch,fault):
    source,uid,target=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));owner=next(f for f in b.GetFootprints()if any(force._uid(p)==uid for p in f.Pads()));root=next(p for p in owner.Pads()if force._uid(p)==uid)
    if fault=='unknown_uuid':uid='not_source_uuid'
    elif fault=='power_pin':root.SetNumber('6')
    elif fault=='wrong_mpn':owner.SetValue('UNKNOWN_MANUFACTURER_INPUT')
    elif fault=='wrong_package':owner.SetFPID(pcbnew.LIB_ID('fixture','wrong_package'))
    elif fault=='dnp':owner.SetDNP(True)
    else:root.SetNet(b.FindNet('INPUT_A'))
    field._save_field_snapshot(b,source)
    refused(lambda:plan(source,uid))


def test_source_connected_terminal_is_not_claimed_as_a_new_component_gain(tmp_path,monkeypatch):
    source,uid,target=case(tmp_path,monkeypatch);candidate=child(source,tmp_path,uid,target)
    refused(lambda:module().plan(pcbnew.LoadBoard(str(candidate)),candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,timeout_s=10.))


def test_branch_width_uses_actual_board_minimum_without_whole_force_current(tmp_path,monkeypatch):
    source,uid,target=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));b.GetDesignSettings().m_TrackMinWidth=250000
    # Board-level plan consumes its actual native settings. KiCad's file
    # writer does not persist this project setting in a standalone PCB.
    q=module().plan(b,source,board_hint='RENAMED_SOURCE',pad_uuid=uid,timeout_s=10.)
    assert q['complete']and q['request']['width_nm']==250000,q


@pytest.mark.parametrize('ordinary,expected',[(.22,220000),(.4,None),(None,None)])
def test_constructor_uses_authored_nonload_width_and_never_guesses_for_large_rail_class(tmp_path,monkeypatch,ordinary,expected):
    source,uid,target=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));root=next(p for f in b.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    classes=[{'name':'full_load','track_width':2.5}]
    if ordinary is not None:classes.append({'name':'Default','track_width':ordinary})
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes':classes,'netclass_assignments':{root.GetNetname():['full_load']}}}))
    before=source.read_bytes();project=source.with_suffix('.kicad_pro').read_bytes()
    if expected is None:refused(lambda:plan(source,uid))
    else:
        q=plan(source,uid)
        assert q['complete'] and q['request']['width_nm']==expected,q
        assert q['request']['nonload_width_basis']['parent_net_class']['track_width']==2.5
    assert source.read_bytes()==before and source.with_suffix('.kicad_pro').read_bytes()==project


def test_unknown_or_incomplete_current_source_does_not_create_a_demand(tmp_path,monkeypatch):
    source,uid,target=case(tmp_path,monkeypatch)
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{})
    refused(lambda:plan(source,uid))


def test_constructor_recompiles_instead_of_trusting_forged_worker_ops(tmp_path,monkeypatch):
    source,uid,target=case(tmp_path,monkeypatch);proposal=plan(source,uid)
    proposal=copy.deepcopy(proposal);proposal['ops']=[('via',[10000000,10000000],.2,.3)];proposal['request']['width_nm']=100000
    candidate=force._copy_family(source,tmp_path/'forged')
    result=module().construct_private(source,candidate,proposal,board_hint='RENAMED_SOURCE',timeout_s=20.)
    assert result['complete'],result
    assert result['request']['width_nm']==200000
    old={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    b=pcbnew.LoadBoard(str(candidate));incoming=[t for t in b.GetTracks()if force._uid(t)not in old]
    assert incoming and all(t.GetClass()=='PCB_TRACK'and t.GetWidth()==200000 and t.GetLayer()==pcbnew.F_Cu for t in incoming)
    received=module().receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,timeout_s=10.)
    assert received['ok']and received['complete'],received


@pytest.mark.parametrize('include_bounded_alternative',[False,True])
def test_constructor_filters_same_saved_path_bounds_before_any_native_write(tmp_path,monkeypatch,include_bounded_alternative):
    import cec_measurement_terminal_route as terminal
    source,uid,target=case(tmp_path,monkeypatch);proposal=plan(source,uid)
    candidate=force._copy_family(source,tmp_path/'bounded');before=candidate.read_bytes()
    demand=proposal['request']['demand'];a=demand['a_nm'];b=demand['b_nm']
    points=[a,[a[0],50000000],[b[0],50000000],b]
    overlong=[['trk',left,right,200000,int(pcbnew.F_Cu)]for left,right in zip(points,points[1:])]
    direct=[['trk',a,b,200000,int(pcbnew.F_Cu)]]
    monkeypatch.setattr(terminal,'menus',lambda *a,**kw:{'ops':
        [overlong,direct]if include_bounded_alternative else[overlong]})
    result=module().construct_private(source,candidate,proposal,board_hint='RENAMED_SOURCE')
    if include_bounded_alternative:
        assert result['complete'] and result['ops']==direct
        proof=module().receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid)
        assert proof['ok'] and proof['complete'],proof
    else:
        assert not result['complete']
        assert result['reason']=='finite_surface_menu_outside_saved_path_scope'
        assert candidate.read_bytes()==before


def test_saved_path_length_limit_is_passed_into_proposal_search(tmp_path,monkeypatch):
    import cec_measurement_terminal_route as terminal
    source,uid,target=case(tmp_path,monkeypatch);proposal=plan(source,uid)
    candidate=force._copy_family(source,tmp_path/'length-domain');before=candidate.read_bytes()
    seen=[]
    def scoped(*args,**kwargs):seen.append(kwargs);return {'ops':[]}
    monkeypatch.setattr(terminal,'menus',scoped)
    result=module().construct_private(source,candidate,proposal,board_hint='RENAMED_SOURCE')
    assert seen[0]['max_length_nm']==module().MAX_PATH_LENGTH_NM==24000000
    assert not result['complete'] and candidate.read_bytes()==before
