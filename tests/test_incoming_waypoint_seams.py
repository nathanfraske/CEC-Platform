"""Waypoint hints never authorize a Source corner cut or an acute reversal."""
from unittest import mock
import pcbnew
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_layer_chain as worker
import cec_rated_branch_repair as rated
import cec_scalar_corner_stage as corners
from test_long_undersized_supply_reconstruction import fixture,OPTIONS
from test_undersized_inner_supply_repair import checker


def seam_case(tmp_path,rotation=0,face=pcbnew.F_Cu):
    source,uid,net,catalog,stages=fixture(tmp_path,48.,rotation,rotation in (90,270),face)
    board=pcbnew.LoadBoard(str(source))
    next(t for t in board.GetTracks()if force._uid(t)==uid).SetWidth(300000)
    field._save_field_snapshot(board,source)
    contract=catalog['contracts'][net]
    contract['current_authority']['amps']=1.
    contract['required_by_layer_mm'].update({'F.Cu':.2,'B.Cu':.2,'In2.Cu':1.256679})
    start,end=stages[0]['points_nm'];direction=[(end[i]-start[i])/48000000 for i in (0,1)]
    def at(along,side):
        return [round(start[0]+1e6*(along*direction[0]-side*direction[1])),
                round(start[1]+1e6*(along*direction[1]+side*direction[0]))]
    stages[0]['points_nm']=[start,at(25,0),at(24.6,.4),end]
    return source,uid,net,catalog,stages


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_newly_constructed_seam_is_smoothed_without_touching_source_or_widths(tmp_path,rotation,face):
    source,uid,net,catalog,stages=seam_case(tmp_path,rotation,face);saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}):
        with pytest.raises(worker.Refused,match='incoming_craft_refused'):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**OPTIONS)
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,compact_new_waypoint_seams=True,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'received');field._save_field_snapshot(board,candidate)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**OPTIONS)
    assert received['ok'] and received['complete'],received
    evidence=proposal['incoming_waypoint_seam_compaction']
    assert evidence['retained_native_material_unchanged'] and evidence['source_current_guard_rechecked']
    assert sum(q['chamfered']for q in evidence['records'])>=1
    assert proposal['craft']['craft_ok'] and proposal['craft']['geometry_ok']
    assert not evidence['source_track_retirement_authority'] and not evidence['release_authority']
    assert all(t.GetWidth()==300000 for t in board.GetTracks()if force._uid(t)in proposal['new_track_uuids'])
    assert proposal['new_via_uuids']==[] and source.read_bytes()==saved


@pytest.mark.parametrize('fault',['unowned_retirement','changed_retained_via','source_current_capture'])
def test_private_seam_cleanup_cannot_take_retained_source_or_capture_permission(tmp_path,monkeypatch,fault):
    source,uid,net,catalog,stages=seam_case(tmp_path);saved=source.read_bytes()
    original=corners.construct
    def corrupt(board,*args,**kw):
        result=original(board,*args,**kw)
        via=next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA')
        if fault=='unowned_retirement':result['retired_track_uuids'].append(force._uid(via))
        elif fault=='changed_retained_via':via.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='source_current_capture':
            monkeypatch.setattr(worker.capture,'Guard',lambda *a,**k:lambda *a:False)
        return result
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}), \
            mock.patch.object(corners,'construct',side_effect=corrupt):
        with pytest.raises(ValueError,match='seam_compaction'):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                compact_new_waypoint_seams=True,**OPTIONS)
    assert source.read_bytes()==saved


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_seam_mode_is_explicit_not_truthy(tmp_path,flag):
    source,uid,net,catalog,stages=seam_case(tmp_path)
    with pytest.raises(ValueError,match='bounded_explicit_rated_layer_chain_required'):
        worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
            compact_new_waypoint_seams=flag,**OPTIONS)
