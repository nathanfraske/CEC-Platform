"""Opt-in joint search must preserve every non-silkscreen field and rollback."""
import pcbnew
import pytest
import cec_support_field_reflow as ink
import cec_force_current as force
from test_support_field_reflow import sample
from test_changed_field_components import board_at


def snapshot(text):
    return (force._uid(text),text.GetText(),tuple(text.GetPosition()),text.GetTextAngle().AsDegrees(),
        text.GetLayer(),text.IsVisible(),tuple(text.GetTextSize()),text.GetTextThickness())


@pytest.mark.parametrize('visible',[False,True])
@pytest.mark.parametrize('rank',[0,1,2,3])
def test_single_silk_reference_can_move_without_moving_or_restyling_native_fab_value(tmp_path,visible,rank):
    source,_,ref=sample(tmp_path);b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference(ref)
    fp.Value().SetLayer(pcbnew.F_Fab);fp.Value().SetVisible(visible)
    before=snapshot(fp.Value());ref_properties=snapshot(fp.Reference())
    r=ink._construct(b,ref,allow_multiland_owner=True,allow_mixed_silk_fields=True,candidate_rank=rank)
    assert r['ok'] and r['non_silkscreen_fields_unchanged'],r
    assert snapshot(fp.Value())==before
    after=snapshot(fp.Reference())
    assert after[:2]==ref_properties[:2] and after[4:]==ref_properties[4:]
    assert not r['release_authority']


def test_non_silk_owner_is_unchanged_not_hidden_or_relayered(tmp_path):
    source,_,ref=sample(tmp_path);b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference(ref)
    fp.Reference().SetLayer(pcbnew.F_Fab);fp.Value().SetLayer(pcbnew.F_Fab)
    before=[snapshot(f) for f in (fp.Reference(),fp.Value())]
    r=ink.construct_changed_components(b,[force._uid(fp)])
    assert r['ok'] and not r['release_authority']
    assert before==[snapshot(f) for f in (fp.Reference(),fp.Value())]


def test_joint_search_backtracks_an_early_pose_instead_of_weakening_a_later_owner(monkeypatch):
    b,fps=board_at([(0,0),(2,0)]);first=[];calls=[]
    def solve(board,ref,**kwargs):
        fp=board.FindFootprintByReference(ref);rank=kwargs['candidate_rank'];calls.append((ref,rank))
        if not first:first.append(ref)
        if ref==first[0]:
            fp.Value().SetTextAngle(pcbnew.EDA_ANGLE(0 if rank==0 else 90,pcbnew.DEGREES_T))
            return dict(ok=True)
        return dict(ok=board.FindFootprintByReference(first[0]).Value().GetTextAngle().AsDegrees()==90)
    monkeypatch.setattr(ink,'_construct',solve)
    result=ink.construct_collision_cohort(b,[force._uid(f) for f in fps],
        include_changed_owners=True,candidate_choices=4)
    assert result['ok'] and result['search_states']==4
    assert (first[0],1) in calls and not result['release_authority']


@pytest.mark.parametrize('policy',[True,0,5,None,1.2])
def test_invalid_candidate_budget_does_not_change_fields(policy):
    b,fps=board_at([(0,0)])
    before=[snapshot(f) for f in (fps[0].Reference(),fps[0].Value())]
    with pytest.raises(ValueError):ink.construct_collision_cohort(b,[force._uid(fps[0])],candidate_choices=policy)
    assert before==[snapshot(f) for f in (fps[0].Reference(),fps[0].Value())]
