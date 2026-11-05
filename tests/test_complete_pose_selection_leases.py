"""Scheduling bounds never replace source/child role or route validation."""
import pytest
import cec_complete_cell_receiving as cell
import cec_complete_macro_cell as macro


@pytest.mark.parametrize('bad',[None,[],[1]*3,[1]*5,[True]*4,[0]*4,[-1]*4,[10.1]*4,
    [float('nan')]*4,[float('inf')]*4,['1']*4,{'a':1}])
def test_invalid_explicit_pose_phase_composition_is_refused(bad):
    with pytest.raises(ValueError):cell.pose_selection_budgets(bad)


def test_each_real_stage_has_its_own_deadline_and_exact_order(monkeypatch):
    now=[0.];monkeypatch.setattr(cell,'_pose_clock',lambda:now[0]);events=[]
    with cell.observe_pose_selection_phases(events.append):
        lease=cell._PoseSelectionLease([1.]*4)
        for name in cell.POSE_SELECTION_PHASES[1:]:
            now[0]+=.9;lease.advance(name)
        now[0]+=.9;lease.finish()
    assert [(r['event'],r['index']) for r in events]==[
        (event,i) for i in range(4) for event in ('start','finish')]


@pytest.mark.parametrize('index',range(4))
def test_an_expired_stage_cannot_borrow_the_next_stage_budget(monkeypatch,index):
    now=[0.];monkeypatch.setattr(cell,'_pose_clock',lambda:now[0])
    lease=cell._PoseSelectionLease([1.]*4)
    for name in cell.POSE_SELECTION_PHASES[1:index+1]:lease.advance(name)
    now[0]=1.
    with pytest.raises(ValueError,match='complete_pose_selection_deadline'):
        lease.finish() if index==3 else lease.advance(cell.POSE_SELECTION_PHASES[index+1])


def test_skipped_reordered_and_unfinished_stages_are_refused():
    lease=cell._PoseSelectionLease([1.]*4)
    with pytest.raises(ValueError):lease.advance(cell.POSE_SELECTION_PHASES[2])
    with pytest.raises(ValueError):lease.finish()


def test_nested_observers_are_context_local_and_restore_on_failure():
    outer=[];inner=[]
    with cell.observe_pose_selection_phases(outer.append):
        with pytest.raises(RuntimeError):
            with cell.observe_pose_selection_phases(inner.append):
                cell._PoseSelectionLease(None)
                raise RuntimeError('synthetic interruption')
        cell._PoseSelectionLease(None)
    cell._PoseSelectionLease(None)
    assert len(outer)==len(inner)==1


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_optional_budgets_do_not_change_successful_native_pose_inference(tmp_path,monkeypatch,turn,back):
    from test_complete_cell_control_shunt_poses import pair
    parent,child,owner,ground,root,actual=pair(tmp_path,monkeypatch,turn,back)
    # This inherited EN-only source fixture intentionally has no modelled
    # supply/bypass pins. Give BOTH inference modes the same explicit empty
    # synthetic bypass catalog; the real canonical EN source checks run.
    monkeypatch.setattr(cell.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    legacy=cell._poses(parent,child,str(root))
    events=[]
    with cell.observe_pose_selection_phases(events.append):
        composed=cell._poses(parent,child,str(root),phase_timeouts_s=[9.5]*4)
    assert composed==legacy
    assert [r['phase'] for r in events if r['event']=='start']==list(cell.POSE_SELECTION_PHASES)


def test_new_scheduling_scope_cannot_make_an_unknown_native_motion_valid(tmp_path,monkeypatch):
    import pcbnew
    from test_complete_cell_control_shunt_poses import pair
    parent,child,owner,ground,root,actual=pair(tmp_path,monkeypatch)
    child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.1,0))
    with pytest.raises(ValueError):cell._poses(parent,child,str(root),phase_timeouts_s=[9.5]*4)


def test_macro_cannot_compose_pose_stages_above_its_external_limit():
    with pytest.raises(ValueError,match='pose_selection_constituents'):
        macro.receive('not_read','not_read_either',board_hint='synthetic',timeout_s=1.,
            pose_selection_phase_timeouts_s=[2.]*4)
