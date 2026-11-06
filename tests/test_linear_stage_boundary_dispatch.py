"""Distinct grounded-control ownership never falls through to low-power rules."""
import copy
import time
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_linear_stage_ground_boundary as linear
import cec_selected_cap_ground_boundary as selected
import cec_cell_escape_replan as escape
from test_linear_stage_ground_boundary import fixture,plan


def test_actual_stage_contact_selects_separate_fresh_checker(tmp_path,monkeypatch):
    parent,q,ids,_,_=fixture(tmp_path,monkeypatch,kind='control')
    seen=[];transport={'fresh':'native_frame'}
    proof=plan(parent,q,ids)['extras']
    def fresh(*a,**kw):
        seen.append((a,kw));return dict(extras=proof)
    monkeypatch.setattr(linear,'ownership',fresh)
    monkeypatch.setattr(linear,'transport_matches',lambda a,t:t is transport,raising=False)
    monkeypatch.setattr(selected,'single_edge_ownerships',lambda *a,**kw:pytest.fail('wrong low-power checker'))
    options={}
    result=compiler._pending_ground_ownership(parent,q,[ids['edge']],transport,
        deadline=time.monotonic()+9.,native_transport_options=options)
    assert result==proof
    assert seen[0][0][:3]==(parent,q,[ids['edge']])
    assert seen[0][1]['native_transport_options'] is options
    assert seen[0][1]['allow_locked_track_uuids']==[]
    assert all(p['authority']['kind']==linear.KIND for p in result)


@pytest.mark.parametrize('fault',['missing_intents','mismatched_transport','incomplete_result'])
def test_dispatch_never_accepts_missing_or_wrong_physical_transport(tmp_path,monkeypatch,fault):
    parent,q,ids,_,_=fixture(tmp_path,monkeypatch,kind='control')
    proof=plan(parent,q,ids)['extras']
    monkeypatch.setattr(linear,'ownership',lambda *a,**k:dict(extras=[]if fault=='incomplete_result'else proof))
    monkeypatch.setattr(linear,'transport_matches',lambda *a:fault!='mismatched_transport',raising=False)
    with pytest.raises(ValueError):
        compiler._pending_ground_ownership(parent,q,[ids['edge']],{},deadline=time.monotonic()+9.,
            native_transport_options=None if fault=='missing_intents'else {})


@pytest.mark.parametrize('consent',[False,True])
def test_only_actual_selected_locked_edges_inherit_explicit_cell_consent(tmp_path,monkeypatch,consent):
    parent,q,ids,_,_=fixture(tmp_path,monkeypatch,kind='control')
    proof=plan(parent,q,ids)['extras'];linear.native._items(parent)[ids['edge']].SetLocked(True)
    q['allow_owned_locked_escapes']=consent;seen=[]
    monkeypatch.setattr(linear,'ownership',lambda *a,**k:seen.append(k)or dict(extras=proof))
    monkeypatch.setattr(linear,'transport_matches',lambda *a:True,raising=False)
    compiler._pending_ground_ownership(parent,q,[ids['edge']],{},deadline=time.monotonic()+9.,native_transport_options={})
    assert seen[0]['allow_locked_track_uuids']==([ids['edge']]if consent else [])


def test_menu_keeps_control_ground_class_and_never_grants_current(tmp_path,monkeypatch):
    parent,q,ids,_,_=fixture(tmp_path,monkeypatch,kind='control')
    authority=plan(parent,q,ids)['extras'][0]['authority']
    request=dict(kind='source_boundary',net='GND',width_nm=250000,
        every_surviving_source_component_port_mandatory=True,
        exact_additional_macro_component_source_ownership=[authority])
    result=escape._typed_macro_ground_scope(request)
    assert result['current_authority'] is False and result['source_width_nm']==250000
    assert authority['source_pad_roots'][0]['role']=='control'
    assert authority['source_pad_roots'][0]['functional_ground_return'] is False
    corrupted=copy.deepcopy(request)
    corrupted['exact_additional_macro_component_source_ownership'][0]['current_authority']=True
    assert escape._typed_macro_ground_scope(corrupted) is None
