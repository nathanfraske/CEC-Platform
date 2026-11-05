"""A rooted full-face native port must not starve the other endpoint menu.

These are scheduling-only mocks. Geometry and electrical admission are not
mocked positive or claimed by this test suite.
"""
from types import SimpleNamespace
import pytest
import cec_native_portal_geometry as geometry
import cec_source_rule_signal_launches as local

LAYERS=[0,6,2]


def pad(uid):return SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:uid))


def fixture():
    roots=[pad('actual-root'),pad('actual-target')]
    menus=[[dict(at_nm=[100,200],layers=LAYERS,native_uuids=['actual-native-barrel'],
        retained_barrel_uuid='actual-native-barrel',native_finite_track_barrel_contact=True,
        retained_same_face_root_pad_uuid='actual-root')],
        [dict(at_nm=[800,900],layers=[0],native_uuids=['actual-target'])]]
    return roots,menus


@pytest.mark.parametrize('reverse',(False,True))
def test_complete_retained_port_saves_lease_for_unescaped_terminal(monkeypatch,reverse):
    roots,menus=fixture()
    if reverse:roots.reverse();menus.reverse()
    seen=[]
    def propose(board,p,**kwargs):
        seen.append(p.m_Uuid.AsString())
        return dict(choices=[dict(at_nm=[800,900],layers=LAYERS,
            operations=[('via',800,900,200000,300000)],proposed_not_retained_native_contact=True)],complete=True)
    monkeypatch.setattr(local,'propose',propose)
    work,r=geometry._source_local_pair_menu(None,roots,menus,width=250000,clearance=200000,
        layers=LAYERS,deadline=geometry.time.monotonic()+1.)
    assert seen==['actual-target']and work
    assert any(q.get('new_hole_requested')is False for q in r['launch_menus'])
    assert all(not pair[0].get('operations')if reverse is False else not pair[1].get('operations')for pair in work)
    assert any('retained_native_contact'in row for pair in work for row in pair)


@pytest.mark.parametrize('fault',('missing_barrel','not_native_contact','other_root','missing_face','bare_face_alias'))
def test_incomplete_or_unrooted_menu_cannot_skip_source_local_compiler(monkeypatch,fault):
    roots,menus=fixture();row=menus[0][0]
    if fault=='missing_barrel':row.pop('retained_barrel_uuid')
    elif fault=='not_native_contact':row['native_finite_track_barrel_contact']=False
    elif fault=='other_root':row['retained_same_face_root_pad_uuid']='not root'
    elif fault=='missing_face':row['layers']=[0,2]
    else:
        menus[0]=[dict(at_nm=[100,200],layers=LAYERS)]
    seen=[]
    monkeypatch.setattr(local,'propose',lambda board,p,**kw:seen.append(p.m_Uuid.AsString())or dict(choices=[],complete=True))
    work,r=geometry._source_local_pair_menu(None,roots,menus,width=250000,clearance=200000,
        layers=LAYERS,deadline=geometry.time.monotonic()+1.)
    assert seen==['actual-root','actual-target']and not work


def test_existing_retained_choices_stay_literal_and_caller_menus_are_not_mutated(monkeypatch):
    import copy
    roots,menus=fixture();before=copy.deepcopy(menus)
    monkeypatch.setattr(local,'propose',lambda *args,**kw:dict(choices=[dict(at_nm=[800,900],layers=[6],
        operations=[('via',800,900,200000,300000)])],complete=True))
    work,r=geometry._source_local_pair_menu(None,roots,menus,width=250000,clearance=200000,
        layers=LAYERS,deadline=geometry.time.monotonic()+1.)
    assert menus==before and len(work)==1
    assert work[0][0]['retained_native_contact']==before[0][0]and work[0][0]['layers']==LAYERS
    assert not r['release_authority']and not r['no_path_proof']
