"""Actual canonical parts, with explicitly synthetic current test contracts.

This tier only recognizes coherent poses. It grants no copper cut/transport,
new barrel, reduced current/width or completed ground-return authority.
"""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_programming_resistor_placement as op
from test_source_linear_power_stage import fixture


def make_pair(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,root,tree,_,calls=fixture(tmp_path,monkeypatch,turn,back)
    resistor=b.FindFootprintByReference('R_program')
    poses={fp.GetReference():[fp.GetPosition().x/1e6+.5,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()]for fp in (owner,resistor)}
    return b,owner,resistor,root,poses,calls


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_positive_source_stage_and_coherent_follower_keep_all_authority(tmp_path,monkeypatch,turn,back):
    b,owner,resistor,root,poses,calls=make_pair(tmp_path,monkeypatch,turn,back)
    before=op.row._source_binding(b);saved=Path(b.GetFileName()).read_bytes()
    with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root))
    selected=op.plan(b,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=True)
    item=selected[resistor.GetReference()];motion=item['coherent_owner_motion']
    assert 'source_stationary_owner_identity'not in item
    assert motion['delta_nm']==[500000,0]
    assert set(motion['source_linear_stage']['source_power_nets'])=={'input-a','input-b','out'}
    assert set(calls)=={'input-a','input-b','out'}
    assert not any(item[k]for k in('current_authority','programmed_current_qualified',
        'new_barrel_authority','source_trace_retirement_authority','release_authority'))
    assert not motion['copper_transport_authority']
    assert set(op.participant_refs(selected))=={resistor.GetReference()}
    child=pcbnew.LoadBoard(b.GetFileName())
    for ref,target in poses.items():
        child.FindFootprintByReference(ref).SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])))
    proposal=dict(poses=poses,selected_programming_resistors=selected,board_hint=str(root),
        allow_linear_power_stage_reconstruction=True)
    requests=op.requests(b,child,proposal)
    assert len(requests)==1
    assert next(iter(requests.values()))['every_original_contact_and_immediate_Ground_return_still_required']
    assert before==op.row._source_binding(b)and Path(b.GetFileName()).read_bytes()==saved


@pytest.mark.parametrize('fault',['nonrigid','rotate_owner','rotate_both','no_current','owner_only',
    'flag_string','flag_int','flag_none','locked_owner'])
def test_incomplete_pair_cannot_acquire_scope(tmp_path,monkeypatch,fault):
    b,owner,resistor,root,poses,_=make_pair(tmp_path,monkeypatch)
    flag=True
    if fault=='nonrigid':poses[resistor.GetReference()][0]+=.001
    elif fault=='rotate_owner':poses[owner.GetReference()][2]+=90
    elif fault=='rotate_both':
        for pose in poses.values():pose[2]+=90
    elif fault=='no_current':
        import cec_source_linear_power_stage as stage
        def missing(*a,**k):raise ValueError('synthetic_missing_current')
        monkeypatch.setattr(stage.full,'_model',missing)
    elif fault=='owner_only':del poses[resistor.GetReference()]
    elif fault=='flag_string':flag='yes'
    elif fault=='flag_int':flag=1
    elif fault=='flag_none':flag=None
    else:
        owner.SetLocked(True)
        import cec_field_coupling as field
        field._save_field_snapshot(b,Path(b.GetFileName()))
    if fault=='owner_only':
        assert op.plan(b,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=flag)=={}
    else:
        with pytest.raises(ValueError):
            op.plan(b,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=flag)


@pytest.mark.parametrize('fault',['one_nm','owner_part','owner_pad','dropped_flag','forged_motion'])
def test_projected_owner_and_flag_are_independently_replayed(tmp_path,monkeypatch,fault):
    b,owner,resistor,root,poses,_=make_pair(tmp_path,monkeypatch)
    selected=op.plan(b,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=True)
    child=pcbnew.LoadBoard(b.GetFileName())
    for ref,target in poses.items():
        child.FindFootprintByReference(ref).SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])))
    proposal=dict(poses=poses,selected_programming_resistors=copy.deepcopy(selected),
        board_hint=str(root),allow_linear_power_stage_reconstruction=True)
    live=child.FindFootprintByReference(owner.GetReference())
    if fault=='one_nm':live.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='owner_part':live.SetField('MPN','other')
    elif fault=='owner_pad':live.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='dropped_flag':del proposal['allow_linear_power_stage_reconstruction']
    else:proposal['selected_programming_resistors'][resistor.GetReference()]['coherent_owner_motion']['delta_nm'][0]+=1
    with pytest.raises(ValueError):op.requests(b,child,proposal)
