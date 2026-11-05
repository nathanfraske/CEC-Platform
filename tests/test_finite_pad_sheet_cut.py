from fractions import Fraction
import json
import hashlib
import time
from unittest import mock
import pcbnew
import pytest
import cec_finite_pad_sheet_cut as cut
from test_lastmile import _board


def fixture(*,rotation=0,shift=(0,0),back=False):
    """Renamable, rigidly transformed native land/foreign-branch geometry."""
    dx,dy=shift
    b=_board([(20+dx,20+dy,'LOAD'),(20+dx,30+dy,'LOAD')],edge=(0,0,70,70))
    byref={fp.GetReference():next(iter(fp.Pads())) for fp in b.GetFootprints()}
    pad,sink=byref['X1'],byref['X2'];pads=[pad,sink]
    pad.SetSize(pcbnew.VECTOR2I_MM(3.4,1.8))
    foreign=pcbnew.NETINFO_ITEM(b,'UNRELATED');b.Add(foreign)
    t=pcbnew.PCB_TRACK(b);t.SetNet(foreign);t.SetLayer(pcbnew.F_Cu)
    t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I_MM(17.9884+dx,17.8416+dy))
    t.SetEnd(pcbnew.VECTOR2I_MM(17.9884+dx,21.8+dy));b.Add(t)
    if rotation:
        centre=pcbnew.VECTOR2I_MM(20+dx,20+dy)
        for fp in b.GetFootprints():fp.Rotate(centre,pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
        t.Rotate(centre,pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    if back:
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu)
        for p in pads:p.SetLayerSet(ls)
        t.SetLayer(pcbnew.B_Cu)
    return b,pad,sink,t


def analyze(b,p,s,**kwargs):
    values=dict(current_A=65,copper_mm=.07,j_limit_A_mm2=100,
        clearance_nm=200000,cut_offsets_nm=[50000],timeout_s=1.)
    values.update(kwargs)
    return cut.analyze(b,p.m_Uuid.AsString(),[s.m_Uuid.AsString()],**values)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('shift',[(0,0),(5.234,7.891)])
@pytest.mark.parametrize('back',[False,True])
def test_exact_native_pinched_cut_is_rigid_transform_and_face_invariant(rotation,shift,back):
    b,p,s,t=fixture(rotation=rotation,shift=shift,back=back)
    report=analyze(b,p,s);r=report['minimum_cut']
    assert r['perimeter_nm']==10800000
    assert r['blocked_length_lower_nm']==1976800
    assert r['available_length_upper_nm']==8823200
    cap=r['sheet_capacity_upper_A']
    assert Fraction(cap['numerator'],cap['denominator'])==Fraction('61.7624')
    assert report['conditional_front_sheet_obstruction']
    assert {h['uuid'] for e in r['edges'] for h in e['contributors']}=={t.m_Uuid.AsString()}
    assert not any(report[k] for k in ('qualified','current_qualified','release_authority','board_mutated'))
    assert report['model']['J_limit_not_promoted_or_ratified_by_this_observer']


def test_saved_native_roundtrip_has_same_bound_and_does_not_write_source(tmp_path):
    b,p,s,t=fixture();path=tmp_path/'random.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    before=path.read_bytes();report=analyze(pcbnew.LoadBoard(str(path)),p,s)
    assert report['minimum_cut']['available_length_upper_nm']==8823200
    assert before==path.read_bytes()
    assert json.loads(json.dumps(report))==report


@pytest.mark.parametrize('fault',['same_net','other_face','diagonal','farther','unassigned'])
def test_only_actual_same_face_foreign_cardinal_body_receives_obstruction_credit(fault):
    b,p,s,t=fixture()
    if fault=='same_net':t.SetNetCode(p.GetNetCode())
    elif fault=='other_face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='diagonal':t.SetEnd(pcbnew.VECTOR2I_MM(17.7,21.8))
    elif fault=='farther':t.Move(pcbnew.VECTOR2I_MM(-1,0))
    else:t.SetNetCode(0)
    report=analyze(b,p,s)
    assert report['conditional_front_sheet_obstruction']==(fault=='unassigned')
    if fault!='unassigned':
        assert report['minimum_cut']['blocked_length_lower_nm']==0
        assert report['no_obstruction_is_not_a_route_or_capacity_pass']
    if fault=='diagonal':assert report['omitted_foreign_native_classes']['PCB_TRACK']==1


def test_duplicate_overlapping_bodies_are_unioned_not_counted_twice():
    b,p,s,t=fixture();duplicate=pcbnew.PCB_TRACK(b)
    duplicate.SetNetCode(t.GetNetCode());duplicate.SetStart(t.GetStart());duplicate.SetEnd(t.GetEnd())
    duplicate.SetLayer(t.GetLayer());duplicate.SetWidth(t.GetWidth());b.Add(duplicate)
    report=analyze(b,p,s)
    assert report['minimum_cut']['blocked_length_lower_nm']==1976800
    assert len(report['obstructions'])==2


def test_interior_cut_boundary_does_not_subtract_a_tangent_rectangle():
    q=cut._bound((0,0,100,100),[dict(uuid='x',kind='rect',rectangle_nm=[-10,-10,0,110])],
        current=Fraction(1),copper=Fraction(1),jlimit=Fraction(1),deadline=time.monotonic()+1)
    assert q['blocked_length_lower_nm']==0


@pytest.mark.parametrize('fault',['round_pad','offset','tht','hole','noncardinal','custom_stack','missing','net'])
def test_unmodelled_or_wrong_terminal_cannot_become_a_cut_certificate(fault):
    b,p,s,t=fixture()
    if fault=='round_pad':p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    elif fault=='offset':p.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='tht':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='hole':p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='noncardinal':p.SetOrientationDegrees(45)
    elif fault=='custom_stack':p.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    elif fault=='missing':pass
    else:s.SetNetCode(0)
    with pytest.raises(ValueError):
        if fault=='missing':cut.analyze(b,'absent',[s.m_Uuid.AsString()],current_A=65,copper_mm=.07,
            j_limit_A_mm2=100,clearance_nm=200000,cut_offsets_nm=[50000])
        else:analyze(b,p,s)


def test_every_receiving_land_must_be_outside_cut():
    b,p,s,t=fixture();extra=pcbnew.PAD(p.GetParentFootprint())
    extra.SetShape(pcbnew.PAD_SHAPE_RECT);extra.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    extra.SetPosition(p.GetPosition());extra.SetLayerSet(p.GetLayerSet());extra.SetNetCode(p.GetNetCode())
    p.GetParentFootprint().Add(extra)
    with pytest.raises(ValueError,match='every_actual_sink'):
        cut.analyze(b,p.m_Uuid.AsString(),[s.m_Uuid.AsString(),extra.m_Uuid.AsString()],
            current_A=65,copper_mm=.07,j_limit_A_mm2=100,clearance_nm=200000,cut_offsets_nm=[50000])


@pytest.mark.parametrize('value',[None,True,0,-1,float('nan'),float('inf'),10**400,'65'])
@pytest.mark.parametrize('key',['current_A','copper_mm','j_limit_A_mm2'])
def test_no_invented_or_nonfinite_model_numbers(key,value):
    b,p,s,t=fixture()
    with pytest.raises(ValueError):analyze(b,p,s,**{key:value})


@pytest.mark.parametrize('value',[None,[],[0],[True],[50000,50000],[{}],[5000001]])
def test_finite_unique_positive_cut_inventory_required(value):
    b,p,s,t=fixture()
    with pytest.raises(ValueError):analyze(b,p,s,cut_offsets_nm=value)


def test_more_copper_is_only_a_different_conditional_model_not_qualification():
    b,p,s,t=fixture();report=analyze(b,p,s,copper_mm=.08)
    assert not report['conditional_front_sheet_obstruction']
    assert not report['current_qualified']
    assert report['no_obstruction_is_not_a_route_or_capacity_pass']


def test_foreign_rect_pad_clearance_does_not_invent_a_corner_square():
    b,p,s,t=fixture();t.Move(pcbnew.VECTOR2I_MM(-10,0))
    # Rectangular foreign land at (18,18), whose +.2 square corner would
    # falsely touch the source's top-left cut corner (18.25,19.05).
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('irrelevant')
    land=pcbnew.PAD(fp);land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    land.SetShape(pcbnew.PAD_SHAPE_RECT);land.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    land.SetPosition(pcbnew.VECTOR2I_MM(17.9,18.8));land.SetNetCode(0)
    ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);land.SetLayerSet(ls);fp.Add(land);b.Add(fp)
    report=analyze(b,p,s)
    assert report['obstructions']
    assert report['minimum_cut']['blocked_length_lower_nm']==0
    for row in report['obstructions']:
        assert row['basis']=='exact_inscribed_foreign_body_clearance_rectangle'
    assert not report['qualified']


@pytest.mark.parametrize('included,amps,margin',[(False,52,1.25),(True,65,1.25),
    (False,1.23456789012345,1.23456789012345)])
@pytest.mark.parametrize('reverse',[False,True])
def test_saved_adapter_rederives_single_injection_every_sink_mm_clearance_and_current_once(tmp_path,included,amps,margin,reverse):
    import cec_force_current as force
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_route_dimensions as dimensions
    b,p,s,t=fixture();path=tmp_path/'case.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    domain=dict(complete=True,source_refs=['X1'],sink_refs=['X2'],missing_refs=[])
    if reverse:domain.update(source_refs=['X2'],sink_refs=['X1'])
    authority=dict(amps=amps,geometry_margin=margin,margin_included=included,
        source='explicit_synthetic_authority')
    snapshot=lambda *args,**kwargs:{str(path):hashlib.sha256(path.read_bytes()).hexdigest()}
    with mock.patch.object(force,'_family',side_effect=snapshot),\
            mock.patch.object(topology,'board_current_domains',return_value={'LOAD':domain}),\
            mock.patch.object(topology,'current_contract_for_net',return_value=authority),\
            mock.patch.object(fab,'active_profile_name',return_value='explicit_synthetic_profile'),\
            mock.patch.object(fab,'copper_thickness_mm',return_value=.07),\
            mock.patch.object(dimensions,'project_resolver',return_value=lambda net:{'clearance':.2}):
        report=cut.diagnose(path,expected_sha256=sha,board_hint='synthetic',net='LOAD',
            pad_uuid=p.m_Uuid.AsString(),cut_offsets_nm=[50000],j_limit_A_mm2=100)
    assert report['source_family_unchanged'] and report['code_unchanged']
    expected=Fraction(str(amps))*(1 if included else Fraction(str(margin)))
    observed=report['model']['current_A']
    assert Fraction(observed['numerator'],observed['denominator'])==expected
    assert report['model']['clearance_nm']==200000
    assert report['minimum_cut']['sheet_capacity_upper_A']['approximate']==61.7624
    assert report['actual_remote_pad_uuids']==[s.m_Uuid.AsString()]
    assert report['all_declared_opposite_lands_rederived']
    assert report['declared_finite_terminal_role']==('declared_sink' if reverse else 'declared_source')
    assert not report['current_qualified']


def test_saved_hash_mismatch_refuses_before_native_load(tmp_path):
    b,p,s,t=fixture();path=tmp_path/'case.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    with mock.patch.object(pcbnew,'LoadBoard',side_effect=AssertionError('native load forbidden')):
        with pytest.raises(ValueError,match='saved_hash_mismatch'):
            cut.diagnose(path,expected_sha256='0'*64,board_hint='synthetic',net='LOAD',
                pad_uuid=p.m_Uuid.AsString(),cut_offsets_nm=[50000],j_limit_A_mm2=100)


@pytest.mark.parametrize('attr',[pcbnew.PAD_ATTRIB_NPTH,pcbnew.PAD_ATTRIB_PTH])
def test_hole_bounding_box_is_not_invented_rectangular_foreign_copper(attr):
    b,p,s,t=fixture();t.Move(pcbnew.VECTOR2I_MM(-10,0))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('HOLE')
    q=pcbnew.PAD(fp);q.SetAttribute(attr);q.SetShape(pcbnew.PAD_SHAPE_RECT)
    q.SetSize(pcbnew.VECTOR2I_MM(.1,.1));q.SetDrillSize(pcbnew.VECTOR2I_MM(1,1))
    q.SetPosition(p.GetPosition());q.SetLayerSet(p.GetLayerSet());fp.Add(q);b.Add(fp)
    report=analyze(b,p,s)
    assert report['minimum_cut']['blocked_length_lower_nm']==0
    assert report['omitted_foreign_native_classes']['PAD']==1
