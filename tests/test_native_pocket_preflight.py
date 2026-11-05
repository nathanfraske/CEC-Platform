"""Native fill, not a nominal vertex score, decides pocket eligibility."""
import copy
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_native_pocket_preflight as preflight
import cec_preflight_boundary_batch as batch
from test_source_retaining_boundary_pocket import fixture

@pytest.mark.parametrize('legacy',[False,True])
@pytest.mark.parametrize('mode',['local_overlap','inset_copy'])
def test_actual_fill_is_preflighted_and_all_source_records_remain_literal(tmp_path,legacy,mode):
    source,uid=fixture(tmp_path,legacy)
    p=batch.plan(source,board_hint='synthetic_not_hardware',support_mode=mode)
    assert p['policy']=='native-fill-preflight-canonical-pocket-cohort-v2'
    assert all(o['native_fill_preflight']['ok'] for r in p['records'] for o in r['selected_offers'])
    old=pcbnew.LoadBoard(str(source));new=batch.construct(source,p)
    z0=next(z for z in old.Zones() if force._uid(z)==uid);z1=next(z for z in new.Zones() if force._uid(z)==uid)
    assert regional.exact_source_contour_present(z1.GetFilledPolysList(pcbnew.F_Cu),z0.GetFilledPolysList(pcbnew.F_Cu),time.monotonic()+10.)
    proof=preflight.observe(old,new,p['records'][0])
    assert proof['no_new_exterior_spur'] and proof['no_new_long_noncanonical_exposed_boundary']
    assert not proof['arbitrary_angle_hull_projection_used']

@pytest.mark.parametrize('fault',['native_result','process','points','authority'])
def test_native_preflight_result_and_construction_cannot_be_forged(tmp_path,fault):
    source,_=fixture(tmp_path);p=batch.plan(source,board_hint='synthetic_not_hardware');bad=copy.deepcopy(p)
    if fault=='native_result':bad['records'][0]['selected_offers'][0]['native_fill_preflight']['native_fill_polygon_sha256']='0'*64
    elif fault=='process':bad['records'][0]['source_configuration']['min_thickness_nm']=1
    elif fault=='points':bad['records'][0]['points_nm'][0][0]+=1
    else:bad['native_fill_preflight_authority_sha256']='0'*64
    with pytest.raises(ValueError,match='stale_or_forged'):batch.construct(source,bad)

@pytest.mark.parametrize('fault',['spur','noncanonical_chord'])
def test_native_spur_or_long_sloping_chord_is_rejected_even_with_positive_area(tmp_path,fault):
    source,uid=fixture(tmp_path);p=batch.plan(source,board_hint='synthetic_not_hardware')
    before=pcbnew.LoadBoard(str(source));after=pcbnew.LoadBoard(str(source))
    old=next(z for z in before.Zones() if force._uid(z)==uid);new=next(z for z in after.Zones() if force._uid(z)==uid)
    points=([[7900000,5900000],[8200000,5900000],[8200000,6000000],[7900000,6000000]] if fault=='spur'
        else [[4000000,5800000],[6000000,5800000],[6000000,6000000]])
    extra=native._poly(points);extra.Append(old.GetFilledPolysList(pcbnew.F_Cu))
    new.UnFill();new.SetFilledPolysList(pcbnew.F_Cu,extra);new.SetIsFilled(True)
    reason='new_exterior_spur' if fault=='spur' else 'new_long_noncanonical_boundary'
    with pytest.raises(ValueError,match=reason):preflight.observe(before,after,p['records'][0])

@pytest.mark.parametrize('dx,dy',[(1000000,1000001),(-1000000,1000001),(1000001,-1000000),(-1000001,-1000000)])
def test_one_database_unit_fill_tessellation_is_disclosed_not_snapped(dx,dy):
    a=[0,0];z=[dx,dy];original=list(z)
    assert preflight.fill_edge_direction(a,z)=='native_single_grid_45_tessellation'
    assert z==original
    assert preflight.fill_edge_direction(a,[dx,dy+1000])=='noncanonical'
