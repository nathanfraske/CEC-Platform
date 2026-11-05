"""Glyph-derived chart scale is a finite annotation search, never smaller ink."""
import copy,json
import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import box,Polygon
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as maps
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture


@pytest.mark.parametrize('face',[pcbnew.F_SilkS,pcbnew.B_SilkS])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('reference',['X1','ABC1234'])
def test_native_readable_rectangle_scale_obeys_actual_glyph_and_both_faces(face,angle,reference):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp);fp.SetReference(reference)
    shape=affinity.rotate(box(-.5,-.25,.5,.25),angle,origin=(0,0))
    floors=dict(height=1.,stroke=.15,clearance=.15,edge=.2)
    scales,evidence=dense._native_readable_chart_scales(board,[(fp,shape)],face,floors)
    assert tuple(scales[:3])==(1.5,2.,3.) and len(scales)<=4
    assert evidence['legacy_scales_unchanged']and evidence['native_glyph_and_factory_floors_unchanged']
    assert len(scales)==4 and 3.<scales[-1]<=12.
    _,_,records=dense.shapes(board,[(fp,shape)],face,floors,scale=scales[-1])
    assert len(records)==1
    # The derived floor is quantized upward, never below the necessary size.
    assert scales[-1]*16==round(scales[-1]*16)
    with pytest.raises(ValueError,match='does_not_fit'):
        dense.shapes(board,[(fp,shape)],face,floors,scale=3.)


@pytest.mark.parametrize('fault',['concave','zero','too_long','too_large'])
def test_finite_scale_discovery_never_inflates_manufacturing_geometry_or_search_bounds(fault):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp);fp.SetReference('X123')
    shape=box(-.5,-.25,.5,.25)
    if fault=='concave':shape=Polygon([(0,0),(1,0),(1,.2),(.2,.2),(.2,1),(0,1)])
    elif fault=='zero':shape=Polygon()
    elif fault=='too_long':fp.SetReference('TOO_LONG_'*30)
    else:shape=box(-30,-.25,30,.25)
    floors=dict(height=1.,stroke=.15,clearance=.15,edge=.2)
    before=shape.wkb
    scales,evidence=dense._native_readable_chart_scales(board,[(fp,shape)],pcbnew.B_SilkS,floors)
    assert scales==(1.5,2.,3.) and evidence['extra_scale_added']is False and evidence['refusal']
    assert shape.wkb==before


def tiny_source(tmp_path,*,back=False,quarter=0):
    source,grade,uid=fixture(tmp_path,roomy=True,back=back,quarter=quarter)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    # Independent native fixture: a tiny rectangular Fab guide inside the
    # unchanged real package courtyard. Only the explanatory picture grows.
    face=pcbnew.B_Fab if back else pcbnew.F_Fab
    for item in list(fp.GraphicalItems()):
        if item.GetLayer()==face and item.GetClass()=='PCB_SHAPE':fp.Remove(item)
    guide=pcbnew.PCB_SHAPE(fp);guide.SetShape(pcbnew.SHAPE_T_RECT);guide.SetLayer(face)
    guide.SetStart(pcbnew.VECTOR2I_MM(19.5,19.75));guide.SetEnd(pcbnew.VECTOR2I_MM(20.5,20.25))
    guide.SetWidth(100000);guide.SetFilled(False);fp.Add(guide)
    field._save_field_snapshot(board,source)
    j=json.loads(grade.read_text());row=j['boards']['candidate'];row['sha256']=force._hash(source)
    row['native_producer']['source_files']={str(source):force._hash(source)};force._write(grade,j)
    options=dict(grade=grade,board_hint='arbitrary-tiny-native-body',maximum_components=1,owner_uuid_scope=[uid],
        reverse_ownership='rigid_root_group_per_component',project_native_fab_body=True,
        via_ink_policy='native_mask_and_bore',opposite_face_chart=True)
    return source,uid,options


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_opt_in_scale_saved_json_and_independent_receiver_preserve_all_source(tmp_path,back,quarter):
    source,uid,options=tiny_source(tmp_path,back=back,quarter=quarter)
    before=source.read_bytes();legacy=maps.plan(source,**options)
    assert legacy['mode']=='opposite_face_projected_courtyard'
    assert 'adaptive_chart_scale'not in legacy
    q=json.loads(json.dumps(maps.plan(source,**options,adaptive_chart_scale=True)))
    assert q['adaptive_chart_scale']is True and q['mode']in('nearby_front_mapping_chart','nearby_opposite_face_mapping_chart')
    assert q['chart_scale_discovery']['front']['extra_scale_added']is True
    selected_trials=(q['front_mapping_trials']if q['mode']=='nearby_front_mapping_chart'else q['opposite_face_chart_trials'])
    assert any(row['scale']>3 and row['fits']for row in selected_trials)
    child=force._copy_family(source,tmp_path/'private');maps.write_private(source,child,q)
    proof=maps.receive(source,child,q);assert proof['ok']and proof['complete'],proof
    observed=pcbnew.LoadBoard(str(child));fp=next(iter(observed.GetFootprints()))
    original=pcbnew.LoadBoard(str(source));original_fp=next(iter(original.GetFootprints()))
    assert dense.guide_body(fp,True).equals(dense.guide_body(original_fp,True))
    assert source.read_bytes()==before
    for fault in ('flag','scale','evidence','floor'):
        bad=copy.deepcopy(q)
        if fault=='flag':del bad['adaptive_chart_scale']
        elif fault=='scale':
            trials=(bad['front_mapping_trials']if bad['mode']=='nearby_front_mapping_chart'else bad['opposite_face_chart_trials'])
            next(row for row in trials if row['fits'])['scale']+=.0625
        elif fault=='evidence':bad['chart_scale_discovery']['front']['extra_scale_added']=False
        else:bad['binding']['factory_legend']['height']=.5
        assert not maps.receive(source,child,bad)['ok']


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_scale_policy_requires_explicit_boolean_not_a_font_clearance_or_geometry_waiver(tmp_path,value):
    source,_,options=tiny_source(tmp_path)
    with pytest.raises(ValueError,match='explicit_native_readable_chart_scale'):
        maps.plan(source,**options,adaptive_chart_scale=value)
