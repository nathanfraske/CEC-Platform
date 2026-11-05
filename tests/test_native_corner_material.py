"""A hidden-source observation is positive, face/net-specific and read-only."""
import pytest
import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as binding
import cec_native_corner_material as material


def fixture(turn=0,back=False,anchor=True):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('renamed_signal','another_signal'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def pt(x,y):
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I(x+5000000,y+5000000)
    tracks=[]
    for a,b in (((0,1000000),(0,0)),((0,0),(1000000,0))):
        t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet('renamed_signal'));t.SetLayer(face)
        t.SetWidth(200000);t.SetStart(pt(*a));t.SetEnd(pt(*b));board.Add(t);tracks.append(t)
    if anchor:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_terminal');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetNet(board.FindNet('renamed_signal'))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(600000,600000));ls=pcbnew.LSET();ls.AddLayer(face)
        pad.SetLayerSet(ls);pad.SetPosition(pt(0,0));fp.Add(pad)
    return board,tracks,pt


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_positive_hidden_rectangular_land_bound_is_native_and_read_only(turn,back):
    b,tracks,pt=fixture(turn,back);before=binding._source_binding(b)
    result=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert result['ok'] and result['complete'],result['errors']
    assert result['hidden_material_equivalence_proved'],result
    assert not result['removed_upper_bound_outlines'] and not result['added_upper_bound_outlines']
    assert before==binding._source_binding(b)
    assert not result['mutation_or_necessity_authority']
    assert not result['electrical_or_current_or_fabrication_qualified']


@pytest.mark.parametrize('fault',['missing','wrong_net','wrong_face','small','near_only'])
def test_an_exposed_or_unrelated_anchor_never_becomes_a_hidden_equivalence(fault):
    b,tracks,pt=fixture(anchor=fault!='missing')
    if fault!='missing':
        pad=next(p for f in b.GetFootprints() for p in f.Pads())
        if fault=='wrong_net':pad.SetNet(b.FindNet('another_signal'))
        elif fault=='wrong_face':ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(ls)
        elif fault=='small':pad.SetSize(pcbnew.VECTOR2I(20000,20000))
        elif fault=='near_only':pad.SetPosition(pt(500000,500000))
    result=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert result['ok'] and result['complete']
    assert not result['hidden_material_equivalence_proved'],result


@pytest.mark.parametrize('kwargs',[dict(inset_limit_nm=True),dict(inset_limit_nm=0),
    dict(inset_limit_nm=2000001),dict(polygon_error_nm=0),dict(polygon_error_nm=1001),
    dict(timeout_s=float('nan')),dict(timeout_s=11)])
def test_bad_bounds_are_not_observation_authority(kwargs):
    b,tracks,pt=fixture()
    result=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)),**kwargs)
    assert not result['ok'] and not result['hidden_material_equivalence_proved']


def test_literal_source_id_and_actual_corner_are_required():
    b,tracks,pt=fixture()
    for ids,at in ((['not-live',force._uid(tracks[1])],list(pt(0,0))),
                   ([force._uid(tracks[0])]*2,list(pt(0,0))),
                   ([force._uid(t) for t in tracks],list(pt(10000,0)))):
        result=material.observe(b,ids,at)
        assert not result['ok'] and not result['hidden_material_equivalence_proved']


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_same_net_retained_through_barrel_is_a_material_witness_not_process_authority(turn,back):
    b,tracks,pt=fixture(turn,back,anchor=False)
    v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('renamed_signal'))
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000)
    v.SetPosition(pt(0,0));b.Add(v)
    before=binding._source_binding(b)
    proof=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert proof['hidden_material_equivalence_proved'],proof
    assert force._uid(v) in proof['retained_same_net_native_uuids']
    assert before==binding._source_binding(b) and not proof['electrical_or_current_or_fabrication_qualified']


@pytest.mark.parametrize('mode',['actual_fill','outline_only','other_net','other_face','rule_area'])
def test_filled_native_polygons_not_zone_names_or_outlines_supply_material(mode):
    b,tracks,pt=fixture(anchor=False)
    z=pcbnew.ZONE(b);z.SetNet(b.FindNet('another_signal' if mode=='other_net' else 'renamed_signal'))
    face=pcbnew.B_Cu if mode=='other_face' else pcbnew.F_Cu;z.SetLayer(face)
    z.Outline().NewOutline()
    for x,y in ((4500000,4500000),(5500000,4500000),(5500000,5500000),(4500000,5500000)):
        z.Outline().Append(x,y)
    z.SetFilledPolysList(face,z.Outline());z.SetIsFilled(mode!='outline_only')
    if mode=='rule_area':z.SetIsRuleArea(True)
    b.Add(z);before=binding._source_binding(b)
    proof=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert proof['hidden_material_equivalence_proved']==(mode=='actual_fill'),proof
    if mode=='outline_only':assert not proof['complete'] and proof['errors']
    assert before==binding._source_binding(b)


def test_a_long_visible_bevel_is_not_hidden_just_because_its_vertex_has_a_pad():
    b,tracks,pt=fixture()
    proof=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)),inset_limit_nm=1000000)
    assert proof['ok'] and proof['complete'] and not proof['hidden_material_equivalence_proved']


def test_a_contact_alias_is_not_silently_projected_off_the_actual_source_line():
    b,tracks,pt=fixture();tracks[0].SetEnd(pt(100,0))
    proof=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert not proof['hidden_material_equivalence_proved'] and not proof['complete']
    assert any('exact_source_capsule_split' in e for e in proof['errors'])


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('height',[1,2800,40000])
@pytest.mark.parametrize('mirror',[False,True])
def test_an_exact_redundant_import_splice_is_covered_by_real_h_and_45_webs(turn,back,height,mirror):
    b,tracks,pt=fixture(turn,back,anchor=False)
    if mirror:
        original=pt
        pt=lambda x,y:original(-x,y)
    tracks[0].SetStart(pt(0,-height));tracks[0].SetEnd(pt(0,0))
    tracks[1].SetStart(pt(-1000000,0));tracks[1].SetEnd(pt(0,0))
    d=pcbnew.PCB_TRACK(b);d.SetNet(tracks[0].GetNet());d.SetLayer(tracks[0].GetLayer());d.SetWidth(200000)
    d.SetStart(pt(0,-height));d.SetEnd(pt(1000000,-1000000-height));b.Add(d)
    before=binding._source_binding(b)
    proof=material.microsplice_coverage(b,force._uid(tracks[0]),[force._uid(tracks[1]),force._uid(d)])
    assert proof['covered'] and proof['exact_constant_width_capsule_union_coverage'],proof
    assert not proof['retirement_or_current_or_contact_authority'] and before==binding._source_binding(b)
    observed=material.observe(b,[force._uid(t) for t in tracks],list(pt(0,0)))
    assert observed['exposed_hard90_not_present_by_positive_native_material_evidence'],observed


@pytest.mark.parametrize('fault',['long','raw_diagonal','wrong_direction','short_receiver',
    'endpoint_alias','wrong_net','wrong_face','width','mask'])
def test_exact_two_web_coverage_cannot_hide_a_different_or_exposed_geometry(fault):
    b,tracks,pt=fixture(anchor=False);h=2800
    tracks[0].SetStart(pt(0,-h));tracks[0].SetEnd(pt(0,0))
    tracks[1].SetStart(pt(-1000000,0));tracks[1].SetEnd(pt(0,0))
    d=pcbnew.PCB_TRACK(b);d.SetNet(tracks[0].GetNet());d.SetLayer(tracks[0].GetLayer());d.SetWidth(200000)
    d.SetStart(pt(0,-h));d.SetEnd(pt(1000000,-1000000-h));b.Add(d)
    if fault=='long':tracks[0].SetStart(pt(0,-50000));d.SetStart(pt(0,-50000))
    elif fault=='raw_diagonal':d.SetEnd(pt(1000001,-1000000-h))
    elif fault=='wrong_direction':d.SetEnd(pt(-1000000,-1000000-h))
    elif fault=='short_receiver':tracks[1].SetStart(pt(-1000,0))
    elif fault=='endpoint_alias':d.SetStart(pt(1,-h))
    elif fault=='wrong_net':d.SetNet(b.FindNet('another_signal'))
    elif fault=='wrong_face':d.SetLayer(pcbnew.B_Cu)
    elif fault=='width':d.SetWidth(199999)
    elif fault=='mask':d.SetHasSolderMask(True)
    proof=material.microsplice_coverage(b,force._uid(tracks[0]),[force._uid(tracks[1]),force._uid(d)])
    assert not proof['covered'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('height,covered',[(41421,True),(41422,False)])
def test_exact_integer_tube_bound_not_a_float_or_area_tolerance(height,covered):
    b,tracks,pt=fixture(anchor=False)
    tracks[0].SetStart(pt(0,-height));tracks[0].SetEnd(pt(0,0))
    tracks[1].SetStart(pt(-1000000,0));tracks[1].SetEnd(pt(0,0))
    d=pcbnew.PCB_TRACK(b);d.SetNet(tracks[0].GetNet());d.SetLayer(tracks[0].GetLayer());d.SetWidth(200000)
    d.SetStart(pt(0,-height));d.SetEnd(pt(1000000,-1000000-height));b.Add(d)
    proof=material.microsplice_coverage(b,force._uid(tracks[0]),[force._uid(d),force._uid(tracks[1])])
    assert proof['covered']==covered
