"""Actual nonrectangular guide fit, not bounding-box or smaller-font credit."""
import copy,json,time
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import pytest
from shapely import affinity
from shapely.geometry import box,Polygon,Point
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as maps
import cec_force_current as force
import cec_field_coupling as field
from test_dense_reference_mapping import fixture

FLOORS=dict(height=1.,stroke=.15,clearance=.15,edge=.2)


def body(kind):
    if kind=='chamfer':return Polygon([(-.5,-.25),(.4,-.25),(.5,-.15),(.5,.25),(-.5,.25)])
    if kind=='trapezoid':return Polygon([(-.6,-.35),(.6,-.35),(.3,.35),(-.3,.35)])
    if kind=='diamond':return Polygon([(-.6,0),(0,-.3),(.6,0),(0,.3)])
    if kind=='round':return Point(0,0).buffer(.3,quad_segs=16)
    raise AssertionError(kind)


@pytest.mark.parametrize('kind',['chamfer','trapezoid','diamond','round'])
@pytest.mark.parametrize('angle',[0,45,90,180])
@pytest.mark.parametrize('face',[pcbnew.F_SilkS,pcbnew.B_SilkS])
def test_actual_native_nonrectangular_fit_across_surfaces_and_rotations(kind,angle,face):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('X123');board.Add(fp)
    guide=affinity.translate(affinity.rotate(body(kind),angle,origin=(0,0)),17.123456,21.765432)
    before=guide.wkb
    legacy,old=dense._native_readable_chart_scales(board,[(fp,guide)],face,FLOORS)
    assert legacy==(1.5,2.,3.) and not old['extra_scale_added']
    scales,proof=dense._native_readable_polygon_chart_scales(board,[(fp,guide)],face,FLOORS)
    assert len(scales)==4 and proof['extra_scale_added'],proof
    assert proof['scale_probes']<=145 and scales[-1]*16==round(scales[-1]*16)
    _,_,rows=dense.shapes(board,[(fp,guide)],face,FLOORS,scale=scales[-1])
    assert len(rows)==1 and guide.wkb==before and not proof['bounding_box_is_fit_authority']
    assert not proof['no_path_proof'] and not proof['release_authority']


def test_box_size_is_not_actual_diamond_fit():
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('X123');board.Add(fp)
    guide=body('diamond')
    scales,proof=dense._native_readable_polygon_chart_scales(board,[(fp,guide)],pcbnew.F_SilkS,FLOORS)
    floor=__import__('math').ceil(proof['necessary_bounding_box_scale']*16)/16
    with pytest.raises(ValueError,match='does_not_fit'):
        dense.shapes(board,[(fp,guide)],pcbnew.F_SilkS,FLOORS,scale=floor)
    assert scales[-1]>floor


@pytest.mark.parametrize('face',[pcbnew.F_SilkS,pcbnew.B_SilkS])
@pytest.mark.parametrize('angle',[0,90])
def test_asymmetric_multi_owner_cohort_repeats_whole_chart_origin_fit(face,angle):
    board=pcbnew.BOARD();models=[]
    for reference,offset in [('X123',-.7),('Y12',.7)]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(reference);board.Add(fp)
        guide=affinity.translate(affinity.rotate(body('chamfer'),angle,origin=(0,0)),
            17.123456+offset,21.765432)
        models.append((fp,guide))
    before=[guide.wkb for _,guide in models]
    scales,proof=dense._native_readable_polygon_chart_scales(board,models,face,FLOORS)
    assert proof['extra_scale_added'],proof
    _,_,rows=dense.shapes(board,models,face,FLOORS,scale=scales[-1])
    assert len(rows)==2 and [guide.wkb for _,guide in models]==before
    assert not proof['bounding_box_is_fit_authority']


@pytest.mark.parametrize('fault',['hole','self_cross','centroid_outside','too_many_points','too_large','too_long',
    'deadline','nan_deadline','infinite_deadline','bool_deadline','string_deadline'])
def test_bounded_or_unknown_shapes_never_gain_fit_or_no_path_authority(fault):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('X123');board.Add(fp)
    guide=body('chamfer');kw={}
    if fault=='hole':guide=Polygon([(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)],holes=[[(-.1,-.1),(.1,-.1),(.1,.1),(-.1,.1)]])
    elif fault=='self_cross':guide=Polygon([(0,0),(1,1),(1,0),(0,1)])
    elif fault=='centroid_outside':guide=Polygon([(0,0),(1,0),(1,.2),(.2,.2),(.2,1),(0,1)])
    elif fault=='too_many_points':guide=Point(0,0).buffer(.3,quad_segs=128)
    elif fault=='too_large':guide=box(-30,-.25,30,.25)
    elif fault=='too_long':fp.SetReference('TOO_LONG_'*30)
    elif fault=='deadline':kw['deadline']=time.monotonic()-1
    elif fault=='nan_deadline':kw['deadline']=float('nan')
    elif fault=='infinite_deadline':kw['deadline']=float('inf')
    elif fault=='bool_deadline':kw['deadline']=True
    else:kw['deadline']='forever'
    scales,proof=dense._native_readable_polygon_chart_scales(board,[(fp,guide)],pcbnew.F_SilkS,FLOORS,**kw)
    assert scales==(1.5,2.,3.) and not proof['extra_scale_added'] and proof['refusal']
    assert not proof['no_path_proof']


def polygon_source(tmp_path,back=False,quarter=0):
    source,grade,uid=fixture(tmp_path,roomy=True,back=back,quarter=quarter)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));center=fp.GetPosition()
    # This synthetic source keeps the old native ink on Fab rather than
    # destroying borrowed library-item proxies during source authoring.
    # The tested CrtYd remains the exact five-segment native loop below.
    for item in list(fp.GraphicalItems()):
        if item.GetLayer() in (pcbnew.F_CrtYd,pcbnew.B_CrtYd):
            item.SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)
    points=[(-.5,-.25),(.4,-.25),(.5,-.15),(.5,.25),(-.5,.25)]
    # Exact authored native loop, not a mocked guide or caller 'fit' flag.
    for a,b in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd);line.SetWidth(50000)
        line.SetStart(center+pcbnew.VECTOR2I_MM(*a));line.SetEnd(center+pcbnew.VECTOR2I_MM(*b));fp.Add(line)
    field._save_field_snapshot(board,source)
    data=json.loads(grade.read_text());row=data['boards']['candidate'];row['sha256']=force._hash(source)
    row['native_producer']['source_files']={str(source):force._hash(source)};force._write(grade,data)
    options=dict(grade=grade,board_hint='arbitrary-native-polygon-chart',maximum_components=1,
        owner_uuid_scope=[uid],reverse_ownership='rigid_root_group_per_component',
        via_ink_policy='native_mask_and_bore',opposite_face_chart=True,adaptive_chart_scale=True)
    return source,options


@pytest.mark.parametrize('back',[False,True])
def test_explicit_polygon_policy_and_saved_reconstruction_bind_actual_guide(tmp_path,back):
    source,options=polygon_source(tmp_path,back);before=source.read_bytes()
    old=maps.plan(source,**options);assert 'polygon_chart_scale'not in old
    proposal=json.loads(json.dumps(maps.plan(source,**options,polygon_chart_scale=True)))
    assert proposal['polygon_chart_scale'] and proposal['chart_scale_discovery']['front']['extra_scale_added']
    child=force._copy_family(source,tmp_path/'candidate');maps.write_private(source,child,proposal)
    proof=maps.receive(source,child,proposal);assert proof['ok'] and proof['complete'],proof
    assert source.read_bytes()==before
    for fault in ('flag','evidence','floor'):
        bad=copy.deepcopy(proposal)
        if fault=='flag':del bad['polygon_chart_scale']
        elif fault=='evidence':bad['chart_scale_discovery']['front']['bounding_box_is_fit_authority']=True
        else:bad['binding']['factory_legend']['height']=.5
        assert not maps.receive(source,child,bad)['ok']


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_new_policy_requires_explicit_bool_and_existing_adaptive_opt_in(tmp_path,value):
    source,options=polygon_source(tmp_path)
    with pytest.raises(ValueError,match='explicit_polygon_chart_scale'):
        maps.plan(source,**options,polygon_chart_scale=value)


def test_polygon_policy_cannot_sneak_in_without_adaptive_request(tmp_path):
    source,options=polygon_source(tmp_path);options['adaptive_chart_scale']=False
    with pytest.raises(ValueError,match='requires_adaptive'):
        maps.plan(source,**options,polygon_chart_scale=True)
