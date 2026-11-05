import copy
import pytest
import pcbnew
import cec_future_power_reservations as reservation
import cec_current_topology as topology
import cec_fr as fr
from cec_native_items import discard_items
from test_lastmile import _board


def make_board(monkeypatch):
    b=_board([(10,20,'RENAMED')])
    monkeypatch.setattr(topology,'board_current_domains',lambda *a:{'RENAMED':dict(complete=True,missing_refs=[])})
    monkeypatch.setattr(topology,'route_width_contracts',lambda *a:{'RENAMED':dict(
        required_by_layer_mm={'F.Cu':3.230592,'B.Cu':3.230592},current_authority=dict(amps=12,geometry_margin=1.25))})
    monkeypatch.setattr(fr,'plane_layers',lambda b:[])
    monkeypatch.setattr(fr,'_edge_leg_clear',lambda *a:True)
    return b


@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_real_whole_source_width_and_ephemeral_removal(monkeypatch,face,rotation,mirror):
    b=make_board(monkeypatch)
    def p(x,y):
        if mirror:x=-x
        for _ in range(rotation):x,y=-y,x
        return [20000000+x,20000000+y]
    q=dict(net='RENAMED',layer=face,points_nm=[p(0,0),p(5000000,0),p(6000000,1000000)])
    old=list(b.GetTracks());ghosts,evidence=reservation.construct(b,[q],board_hint='caller')
    assert len(ghosts)==2 and all(t.GetWidth()==3230592 and t.IsLocked() for t in ghosts)
    assert not evidence['saved_copper_authority'] and not evidence['current_capacity_credited']
    assert not evidence['equal_current_sharing_assumed'] and not evidence['release_authority']
    with pytest.raises(ValueError,match='leaked'):reservation.require_removed(b,evidence)
    discard_items(b,ghosts)
    assert len(list(b.GetTracks()))==len(old) and reservation.require_removed(b,evidence)['ok']


@pytest.mark.parametrize('fault',['extra_width','zero','non45','missing_net','ground','bad_point','duplicate','too_many','edge','domain','width_floor'])
def test_invalid_reservation_refuses_without_any_added_copper(monkeypatch,fault):
    b=make_board(monkeypatch);q=dict(net='RENAMED',layer='F.Cu',points_nm=[[10000000,20000000],[20000000,20000000]])
    if fault=='extra_width':q['width_nm']=200000
    if fault=='zero':q['points_nm'][1]=list(q['points_nm'][0])
    if fault=='non45':q['points_nm'][1]=[20000000,21000000]
    if fault=='missing_net':q['net']='missing'
    if fault=='ground':q['net']='GND'
    if fault=='bad_point':q['points_nm'][1][0]=True
    if fault=='edge':monkeypatch.setattr(fr,'_edge_leg_clear',lambda *a:False)
    if fault=='domain':monkeypatch.setattr(topology,'board_current_domains',lambda *a:{'RENAMED':dict(complete=False,missing_refs=['missing'])})
    if fault=='width_floor':monkeypatch.setattr(topology,'route_width_contracts',lambda *a:{'RENAMED':dict(required_by_layer_mm={'F.Cu':38.703504})})
    qs=[q,q] if fault=='duplicate' else [q]*5 if fault=='too_many' else [q]
    before=list(b.GetTracks())
    with pytest.raises(ValueError):reservation.construct(b,qs,board_hint='caller')
    assert len(list(b.GetTracks()))==len(before)


def test_second_invalid_request_does_not_leave_first_ghosts(monkeypatch):
    b=make_board(monkeypatch);a=dict(net='RENAMED',layer='F.Cu',points_nm=[[10000000,20000000],[20000000,20000000]])
    bad=copy.deepcopy(a);bad['layer']='B.Cu';bad['points_nm'][1]=list(bad['points_nm'][0])
    with pytest.raises(ValueError):reservation.construct(b,[a,bad],board_hint='caller')
    assert not list(b.GetTracks())
