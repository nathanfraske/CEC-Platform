"""Native, geometry-independent scheduling and fail-closed fill regressions."""
import ast
from pathlib import Path
from unittest import mock

import pcbnew
import pytest
import cec_zone_fill as fill
import cec_frozen_pour_void as frozen


def fixture(path, *, back=False, turn=False):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(4)
    def xy(x,y):
        return pcbnew.VECTOR2I_MM(50-y if turn else 20+x, 40+x if turn else 30+y)
    for a,b in zip([(-5,-5),(35,-5),(35,25),(-5,25)],
                   [(35,-5),(35,25),(-5,25),(-5,-5)]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(xy(*a));edge.SetEnd(xy(*b))
        edge.SetWidth(50000);board.Add(edge)
    for name,priority,pts in [
        ('renamed-corridor',1,[(0,0),(30,0),(30,20),(29,20),(29,1),(0,1)]),
        ('renamed-interior',2,[(10,10),(11,10),(11,11),(10,11)])]:
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
        zone=pcbnew.ZONE(board);zone.SetNet(net)
        zone.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
        zone.SetZoneName('pourfirst:'+name);zone.SetAssignedPriority(priority)
        zone.SetLocalClearance(500000);zone.SetMinThickness(250000)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        zone.Outline().NewOutline()
        for p in pts:
            v=xy(*p);zone.Outline().Append(v.x,v.y)
        board.Add(zone)
    pcbnew.SaveBoard(str(path),board)
    return pcbnew.LoadBoard(str(path))


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[False,True])
def test_real_disjoint_shapes_with_overlapping_boxes_settle_exactly(tmp_path,back,turn):
    board=fixture(tmp_path/'native.kicad_pcb',back=back,turn=turn)
    before=[(z.m_Uuid.AsString(),z.GetAssignedPriority(),z.Outline().Format()) for z in board.Zones()]
    reports=[]
    for _ in range(3):
        report=fill.fill_with_report(board);reports.append(report)
        assert report['stable'] and report['ordered_passes']==2
        assert report['tolerance_nm']==0
        if len(reports)==1: saved=frozen.capture(board)
        assert frozen.preservation(saved,board)['ok']
    assert len({r['fingerprint'] for r in reports})==1
    assert before==[(z.m_Uuid.AsString(),z.GetAssignedPriority(),z.Outline().Format()) for z in board.Zones()]


@pytest.mark.parametrize('fail_after',[0,1])
def test_native_failure_never_returns_success(tmp_path,fail_after):
    board=fixture(tmp_path/'native.kicad_pcb')
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        native.return_value.Fill.side_effect=[True]*fail_after+[False]
        with pytest.raises(RuntimeError,match='zone fill failed'):
            fill.fill(board)
    assert native.return_value.Fill.call_count==fail_after+1


def test_real_new_foreign_trace_still_carves_and_fails_protection(tmp_path):
    board=fixture(tmp_path/'native.kicad_pcb')
    fill.fill(board);before=frozen.capture(board)
    track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.F_Cu)
    track.SetNet(board.FindNet('renamed-interior'));track.SetWidth(200000)
    track.SetStart(pcbnew.VECTOR2I_MM(40,29.5));track.SetEnd(pcbnew.VECTOR2I_MM(40,31.5))
    board.Add(track);fill.fill(board)
    proof=frozen.preservation(before,board)
    assert not proof['ok'] and proof['tolerance_nm']==0


def test_nonconverged_fill_is_bounded_and_rejected(tmp_path,monkeypatch):
    board=fixture(tmp_path/'native.kicad_pcb')
    fingerprints=iter(['first','different'])
    monkeypatch.setattr(fill,'_fingerprint',lambda _:next(fingerprints))
    with pytest.raises(RuntimeError,match='did not converge in two passes'):
        fill.fill(board)


def test_native_priority_order_is_not_board_insertion_order(tmp_path):
    board=fixture(tmp_path/'native.kicad_pcb')
    ordered=fill._ordered(list(board.Zones()))
    assert ordered[0].HigherPriority(ordered[1])
    assert fill._ordered(list(reversed(ordered)))[0].m_Uuid==ordered[0].m_Uuid


def test_empty_board_needs_no_native_fill():
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        assert fill.fill(pcbnew.CreateEmptyBoard())
    native.assert_not_called()


@pytest.mark.parametrize('back,turn',[(False,False),(True,True)])
def test_selected_initialization_only_compiles_exact_subset(tmp_path,back,turn):
    board=fixture(tmp_path/'native.kicad_pcb',back=back,turn=turn)
    fill.fill(board)
    selected=list(board.Zones())[:1]
    neighbor=list(board.Zones())[1]
    before=(neighbor.IsFilled(),neighbor.Outline().Format(),
            neighbor.GetFilledPolysList(neighbor.GetLayer()).Format())
    selected[0].UnFill()
    native_factory=pcbnew.ZONE_FILLER
    calls=[]
    def factory(owner):
        native=native_factory(owner)
        class Recorder:
            def Fill(self,zones):
                calls.append([z.m_Uuid.AsString() for z in zones])
                return native.Fill(zones)
        return Recorder()
    with mock.patch.object(pcbnew,'ZONE_FILLER',side_effect=factory):
        report=fill.compile_selected(board,selected,initialize_selected=True)
    assert report['stable'] and report['ordered_passes']==2
    assert report['initialized_selected'] and report['compiled_zone_count']==1
    assert not report['native_copper_received'] and not report['release_authority']
    assert calls==[[selected[0].m_Uuid.AsString()]]*3
    assert before==(neighbor.IsFilled(),neighbor.Outline().Format(),
                    neighbor.GetFilledPolysList(neighbor.GetLayer()).Format())


def test_initial_selected_batch_precedes_two_exact_passes(tmp_path,monkeypatch):
    board=fixture(tmp_path/'native.kicad_pcb')
    selected=list(board.Zones());ids={z.m_Uuid.AsString() for z in selected}
    calls=[]
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        def record(zones):
            calls.append([z.m_Uuid.AsString() for z in zones]);return True
        native.return_value.Fill.side_effect=record
        monkeypatch.setattr(fill,'_fingerprint',lambda _: 'exact')
        report=fill.compile_selected(board,selected,initialize_selected=True)
    assert set(calls[0])==ids and len(calls)==5
    assert all(len(row)==1 for row in calls[1:])
    assert calls[1:3]==calls[3:5]  # same native order, never extra settling
    assert report['stable'] and report['ordered_passes']==2


def test_selected_initial_failure_is_not_retried(tmp_path):
    board=fixture(tmp_path/'native.kicad_pcb')
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        native.return_value.Fill.return_value=False
        with pytest.raises(fill.NativeFillFailed,match='initial zone fill failed'):
            fill.compile_selected(board,list(board.Zones()),initialize_selected=True)
        assert native.return_value.Fill.call_count==1


def test_selected_initialization_does_not_waive_nonconvergence(tmp_path,monkeypatch):
    board=fixture(tmp_path/'native.kicad_pcb')
    fingerprints=iter(['first','different'])
    monkeypatch.setattr(fill,'_fingerprint',lambda _:next(fingerprints))
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        native.return_value.Fill.return_value=True
        with pytest.raises(RuntimeError,match='did not converge in two passes'):
            fill.compile_selected(board,list(board.Zones()),initialize_selected=True)
        assert native.return_value.Fill.call_count==5


@pytest.mark.parametrize('initialize',[False,True])
def test_native_net_reassignment_is_reported_before_stability_receiving(tmp_path,initialize):
    board=fixture(tmp_path/'native.kicad_pcb')
    zone=list(board.Zones())[0];old_net=zone.GetNetname()
    other=next(z.GetNet() for z in board.Zones() if z.GetNetname()!=old_net)
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        def relabel(_):
            zone.SetNet(other);return True
        native.return_value.Fill.side_effect=relabel
        with pytest.raises(RuntimeError,match='changed_authored_net_identity:zone:'+zone.m_Uuid.AsString()):
            fill.compile_selected(board,list(board.Zones()),initialize_selected=initialize)
        assert native.return_value.Fill.call_count==1


@pytest.mark.parametrize('normalize',[False,True])
def test_trackless_via_is_received_only_if_authored_identity_survives(tmp_path,normalize):
    from test_field_refill_proposals import ground_fixture
    _,board=ground_fixture(tmp_path)
    # A source-owned trackless barrel is not permission for the native
    # fill/connectivity normalizer to adopt a surrounding ground plane.
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(22,14))
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(600000);via.SetDrill(300000)
    via.SetNetCode(board.GetNetcodeFromNetname('/PWM'));via.SetLocked(True);board.Add(via)
    ground=[z for z in board.Zones() if z.GetNetname()=='GND']
    for zone in ground:zone.UnFill()
    if normalize:
        with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
            def relabel(_):
                via.SetNetCode(board.GetNetcodeFromNetname('GND'));return True
            native.return_value.Fill.side_effect=relabel
            with pytest.raises(RuntimeError,match='changed_authored_net_identity:track:'+via.m_Uuid.AsString()):
                fill.compile_selected(board,ground,initialize_selected=True)
            assert native.return_value.Fill.call_count==1
    else:
        report=fill.compile_selected(board,ground,initialize_selected=True)
        assert report['stable'] and via.GetNetname()=='/PWM'
        assert not report['native_copper_received'] and not report['release_authority']


@pytest.mark.parametrize('value',[None,0,1,'yes'])
def test_invalid_selected_initialization_refuses_before_native_fill(tmp_path,value):
    board=fixture(tmp_path/'native.kicad_pcb')
    with mock.patch.object(pcbnew,'ZONE_FILLER') as native:
        with pytest.raises(ValueError,match='invalid_selected_native_fill_initialization'):
            fill.compile_selected(board,list(board.Zones()),initialize_selected=value)
        native.assert_not_called()


def test_pipeline_native_fill_cannot_bypass_shared_scheduler():
    root=Path(__file__).resolve().parents[1]/'scripts'
    bypasses=[]
    for path in root.glob('*.py'):
        if path.name=='cec_zone_fill.py':continue
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='ZONE_FILLER':
                bypasses.append((path.name,node.lineno))
    assert not bypasses
