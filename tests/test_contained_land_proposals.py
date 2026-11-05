"""Fine pose scale comes from native copper and fixed barrels, never refdes."""
import math
import pytest
import pcbnew
import cec_fixed_pofv_mobility as mobility
import cec_fab_profile as fab
from test_fixed_pofv_mobility import fixture


@pytest.mark.parametrize('offset,ref,back', [((0,0),'SUPPORT',False),((43,-17),'OTHER',True)])
@pytest.mark.parametrize('shape', [pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_CIRCLE,
                                 pcbnew.PAD_SHAPE_ROUNDRECT])
def test_actual_contained_lands_cover_sub_coarse_domain_without_mutation(offset,ref,back,shape):
    board,fp,pad,via=fixture(offset=offset,ref=ref,back=back,size=(.6,.6))
    pad.SetShape(shape)
    if shape==pcbnew.PAD_SHAPE_ROUNDRECT:pad.SetRoundRectRadiusRatio(.25)
    before=(tuple(fp.GetPosition()),fp.GetOrientationDegrees(),tuple(via.GetPosition()))
    target=dict(ref=ref)
    rows=mobility.contained_land_proposals(board,target)
    assert rows and rows==mobility.contained_land_proposals(board,target)
    coarse=mobility.proposals(board,target,rotations=(0,))
    coarse_poses={(row['dx_mm'],row['dy_mm'],row['rotation_delta_deg']) for row in coarse}
    assert any((r['dx_mm'],r['dy_mm'],r['rotation_delta_deg']) not in coarse_poses
               and r['rotation_delta_deg']==0 and 0<math.hypot(r['dx_mm'],r['dy_mm'])<.125
               for r in rows)
    for row in rows:
        assert row['sampling_domain']=='contained_land'
        assert mobility.evaluate(board,target,row)['ok']
        fp.SetPosition(pcbnew.VECTOR2I(*before[0])+pcbnew.VECTOR2I_MM(row['dx_mm'],row['dy_mm']))
        fp.SetOrientationDegrees(before[1]+row['rotation_delta_deg'])
        assert fab._pad_contains_circle(pad,via.GetPosition(),via.GetWidth()//2)
        assert fab.local_pofv_via_decision(board,via)[0]
        fp.SetPosition(pcbnew.VECTOR2I(*before[0]));fp.SetOrientationDegrees(before[1])
    assert before==(tuple(fp.GetPosition()),fp.GetOrientationDegrees(),tuple(via.GetPosition()))


def test_no_slack_generated_or_unlocked_owners_do_not_get_fabricated_domain():
    board,fp,pad,via=fixture(size=(.35,.35))
    assert mobility.contained_land_proposals(board,dict(ref=fp.GetReference()))==[]
    board,fp,pad,via=fixture()
    assert mobility.contained_land_proposals(board,dict(ref=fp.GetReference()),
        generated_locked_uuids=[via.m_Uuid.AsString()])==[]
    via.SetLocked(False)
    assert mobility.contained_land_proposals(board,dict(ref=fp.GetReference()))==[]


@pytest.mark.parametrize('kwargs',[dict(fractions=()),dict(fractions=(0,)),dict(fractions=(1.1,)),
    dict(fractions=(float('nan'),)),dict(rotations=(45,)),dict(max_anchors=0),
    dict(max_candidates=True),dict(max_candidates=4097)])
def test_search_bounds_are_validated_before_native_access(kwargs):
    with pytest.raises(ValueError):mobility.contained_land_proposals(None,{},**kwargs)


def test_finite_prefix_determinism():
    board,fp,pad,via=fixture()
    target=dict(ref=fp.GetReference())
    rows=mobility.contained_land_proposals(board,target)
    assert rows[:3]==mobility.contained_land_proposals(board,target,max_candidates=3)
    assert len(rows)<=128
