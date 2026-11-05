"""One trapped source cut cannot starve another finite independent cut lease."""
from types import SimpleNamespace
import time

import pcbnew
import pytest

import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_fr as fr
import cec_future_pose_clearance as future
from test_field_proposals import track
from test_future_pose_clearance import fixture


def two_cuts(tmp_path):
    board,source,poses,_=fixture(tmp_path)
    # A long two-land passive's future footprint intersects two separately
    # owned ordinary nets. Their source pads and tracks are still distinct.
    fp=board.FindFootprintByReference(next(iter(poses)))
    for pad in fp.Pads():pad.SetSize(pcbnew.VECTOR2I_MM(.6,2.2))
    net=pcbnew.NETINFO_ITEM(board,'/SECOND_CONTROL');board.Add(net)
    for x in (5,15):
        other=pcbnew.FOOTPRINT(board);other.SetReference('SECOND_END_'+str(x));board.Add(other)
        pad=pcbnew.PAD(other);pad.SetNet(net);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetPosition(pcbnew.VECTOR2I_MM(x,11));other.Add(pad)
    track(board,'/SECOND_CONTROL',(5,11),(15,11))
    field._save_field_snapshot(board,source)
    proposal=future.plan(board,poses,source=source,board_hint='synthetic')
    assert len(proposal['cut_boundaries'])==2 and proposal['ok'],proposal
    return board,source,proposal


@pytest.mark.parametrize('fair',[False,True])
def test_each_explicit_cut_has_its_own_lease_but_default_keeps_aggregate_bound(tmp_path,monkeypatch,fair):
    board,source,proposal=two_cuts(tmp_path)
    tick=[time.monotonic()];seen=[]
    monkeypatch.setattr(future,'time',SimpleNamespace(monotonic=lambda:tick[0]))
    def exhausted_search(board,a,b,*args,**kwargs):
        seen.append(kwargs['deadline_monotonic'])
        # Emulate a bounded but trapped first cut using its whole lease.
        tick[0]+=3.01
        return None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',exhausted_search)
    result=future.construct(board,proposal,source=source,timeout_s=3,
        per_boundary_leases=fair)
    assert len(seen)==(2 if fair else 1)
    assert result['max_construction_wall_s']==(6 if fair else 3)
    assert result['closed']==0 and not result['release_authority']
    assert not any(z.GetZoneName().startswith('TEMP FUTURE') for z in board.Zones())
    if fair:assert seen[1]>seen[0]


@pytest.mark.parametrize('value',[1,None,'yes'])
def test_lease_boolean_is_explicit_and_rejection_is_before_mutation(tmp_path,value):
    board,source,proposal=two_cuts(tmp_path);binding=row._source_binding(board)
    with pytest.raises(ValueError,match='explicit_future_pose_maze_refinement_required'):
        future.construct(board,proposal,source=source,per_boundary_leases=value)
    assert row._source_binding(board)==binding


def test_three_way_native_cut_does_not_starve_its_second_surviving_junction(tmp_path,monkeypatch):
    board,source,proposal=two_cuts(tmp_path)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(8,10))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNet(board.FindNet('/CONTROL'));board.Add(via)
    track(board,'/CONTROL',(8,10),(8,8),layer=pcbnew.B_Cu)
    field._save_field_snapshot(board,source)
    proposal=future.plan(board,{r['ref']:r['target_pose_mm'] for r in proposal['poses']},
        source=source,board_hint='synthetic')
    assert proposal['ok'] and sorted(len(r['anchors_nm']) for r in proposal['cut_boundaries'])==[2,3]
    tick=[time.monotonic()];seen=[]
    monkeypatch.setattr(future,'time',SimpleNamespace(monotonic=lambda:tick[0]))
    def exhausted_search(board,a,b,*args,**kwargs):
        seen.append(kwargs['deadline_monotonic']);tick[0]+=3.01;return None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',exhausted_search)
    result=future.construct(board,proposal,source=source,timeout_s=3.,per_boundary_leases=True)
    assert len(seen)==3 and seen[0]<seen[1]<seen[2]
    assert result['max_construction_wall_s']==9 and result['independent_boundary_work_leases']==3
    assert not result['closed'] and not result['release_authority']
