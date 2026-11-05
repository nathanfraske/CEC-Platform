import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_rectangular_field_silk_clearance as ink
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_footprint_children


def line(fp,a,b,layer=pcbnew.F_SilkS,width=150000):
    g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(layer);g.SetWidth(width)
    g.SetStart(pcbnew.VECTOR2I_MM(*a));g.SetEnd(pcbnew.VECTOR2I_MM(*b));fp.Add(g);return g


def fixture(tmp_path,turn=0,back=False,edge=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetFPID(pcbnew.LIB_ID('Independent','Native_Field'));fp.SetReference('Renamed_Field');fp.SetValue('retained functional label')
    for index,(x,y)in enumerate(( (x,y)for y in (1.85,7.35)for x in (2.1,6.3,10.5,14.7)),1):
        p=pcbnew.PAD(fp);p.SetNumber(str(index));p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_OVAL);p.SetPosition(pcbnew.VECTOR2I_MM(x,y));p.SetSize(pcbnew.VECTOR2I_MM(2.7,3.7));p.SetDrillSize(pcbnew.VECTOR2I_MM(1.8,1.8));layers=pcbnew.LSET.AllCuMask();layers.AddLayer(pcbnew.F_Mask);layers.AddLayer(pcbnew.B_Mask);p.SetLayerSet(layers);fp.Add(p)
    for a,z in [((0,0),(16.8,0)),((16.8,0),(16.8,9.2)),((16.8,9.2),(0,9.2)),((0,9.2),(0,0))]:line(fp,a,z)
    fab=pcbnew.PCB_SHAPE(fp);fab.SetLayer(pcbnew.F_Fab);fab.SetShape(pcbnew.SHAPE_T_RECT);fab.SetStart(pcbnew.VECTOR2I_MM(0,0));fab.SetEnd(pcbnew.VECTOR2I_MM(16.8,9.2));fab.SetWidth(100000);fp.Add(fab)
    court=pcbnew.PCB_SHAPE(fp);court.SetLayer(pcbnew.F_CrtYd);court.SetShape(pcbnew.SHAPE_T_RECT);court.SetStart(pcbnew.VECTOR2I_MM(-.5,-.5));court.SetEnd(pcbnew.VECTOR2I_MM(17.3,9.7));court.SetWidth(50000);fp.Add(court)
    for f in fp.GetFields():f.SetVisible(False)
    library=tmp_path/'independent.pretty';library.mkdir();pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library),fp);template=library/'Native_Field.kicad_mod';assert template.is_file()
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(20,.1 if edge else 20))
    for a,z in [((0,0),(80,0)),((80,0),(80,80)),((80,80),(0,80)),((0,80),(0,0))]:
        g=pcbnew.PCB_SHAPE(b);g.SetLayer(pcbnew.Edge_Cuts);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetStart(pcbnew.VECTOR2I_MM(*a));g.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(g)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    # Initial fixture creation canonicalizes KiCad's PTH all-layer flip mask;
    # the actual operation below always starts with this saved native source.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    return source,force._uid(fp),template


def proposal(source,uid,template):
    return ink.plan(source,selections=[dict(footprint_uuid=uid,template_path=str(template))],board_hint='synthetic')


def saved(tmp_path,**kw):
    source,uid,template=fixture(tmp_path,**kw);q=json.loads(json.dumps(proposal(source,uid,template)));child=force._copy_family(source,tmp_path/'child');ink.write_private(source,child,q);return source,child,q,uid,template


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_real_complete_pth_frame_all_faces_rotations_exact_saved_receiving(tmp_path,turn,back):
    source,child,q,uid,template=saved(tmp_path,turn=turn,back=back);before=[p.read_bytes()for p in(source,child,template)]
    r=ink.receive(source,child,q,board_hint='synthetic');assert r['ok']and r['complete'],r
    assert q['changed']and q['records'][0]['native_mask_obstacles']
    assert [p.read_bytes()for p in(source,child,template)]==before
    assert r['literal_all_source_except_declared_frame_endpoints_exact']and r['native_second_save_stable']
    b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    _,box,width,face=ink._frame(fp);assert width==150000 and face==(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    assert not r['release_authority']and not r['current_authority']


def test_separate_independent_library_proposal_not_canonical_publication(tmp_path):
    source,child,q,uid,template=saved(tmp_path);original=template.read_bytes();rows=ink.export_template_proposals(source,q,tmp_path/'asset-proposals')
    assert len(rows)==1 and template.read_bytes()==original
    assert rows[0]['source_sha256']==force._hash(template)
    fp=pcbnew.FootprintLoad(str(Path(rows[0]['proposal_path']).parent),Path(rows[0]['proposal_path']).stem)
    assert fp is not None and ink._frame(fp)[1]!=ink._frame(pcbnew.FootprintLoad(str(template.parent),template.stem))[1]


@pytest.mark.parametrize('fault',['pad','drill','court','fab','extra_art','extra_frame','missing_side','locked_fp','locked_line','group','group_line','stroke','noncardinal'])
def test_source_name_or_unsupported_art_cannot_grant_frame_ownership(tmp_path,fault):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));lines=ink._frame(fp)[0]
    if fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(2.8,3.7))
    elif fault=='drill':next(iter(fp.Pads())).SetDrillSize(pcbnew.VECTOR2I_MM(1.9,1.9))
    elif fault=='court':next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_CrtYd).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='fab':next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_Fab).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='extra_art':line(fp,(20,20),(21,20),pcbnew.F_Fab)
    elif fault=='extra_frame':line(fp,(19,20),(20,20))
    elif fault=='missing_side':discard_footprint_children(b,fp,[lines[0]])
    elif fault=='locked_fp':fp.SetLocked(True)
    elif fault=='locked_line':lines[0].SetLocked(True)
    elif fault in ('group','group_line'):
        g=pcbnew.PCB_GROUP(b);g.SetName('source-owned');b.Add(g);g.AddItem(fp if fault=='group'else lines[0])
    elif fault=='stroke':lines[0].SetWidth(100000)
    else:fp.SetOrientationDegrees(45)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):proposal(source,uid,template)


@pytest.mark.parametrize('fault',['pad','court','field','track','frame','sidecar','new_note','bom'])
def test_saved_receiver_rejects_every_unowned_change(tmp_path,fault):
    source,child,q,uid,template=saved(tmp_path);b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    if fault=='pad':next(iter(fp.Pads())).SetDrillSize(pcbnew.VECTOR2I_MM(1.9,1.9))
    elif fault=='court':next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_CrtYd).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='field':fp.Value().SetText('unowned value')
    elif fault=='track':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    elif fault=='frame':ink._frame(fp)[0][0].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='bom':fp.SetAttributes(fp.GetAttributes()^pcbnew.FP_EXCLUDE_FROM_BOM)
    elif fault=='new_note':
        t=pcbnew.PCB_TEXT(b);t.SetText('unowned');t.SetLayer(pcbnew.F_SilkS);b.Add(t)
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:field._save_field_snapshot(b,child)
    r=ink.receive(source,child,q,board_hint='synthetic');assert not r['ok'],r


@pytest.mark.parametrize('fault',['bounds','template','authority','width'])
def test_forged_plan_never_authorizes_new_geometry(tmp_path,fault):
    source,uid,template=fixture(tmp_path);q=proposal(source,uid,template)
    if fault=='bounds':q['records'][0]['target_bounds_nm'][0]-=1
    elif fault=='template':template.write_text(template.read_text()+'\n; changed independent authority\n')
    elif fault=='authority':q['authority_sha256'][str(template)]='0'*64
    else:q['records'][0]['stroke_nm']+=1
    with pytest.raises(ValueError):ink.construct(source,q)


def test_native_edge_limit_cannot_be_waived_by_expanding_frame(tmp_path):
    source,uid,template=fixture(tmp_path,edge=True)
    with pytest.raises(ValueError,match='edge|material'):proposal(source,uid,template)


def test_actual_native_mask_artwork_is_not_an_invented_clearance_exception(tmp_path):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_SHAPE(b);g.SetShape(pcbnew.SHAPE_T_RECT);g.SetLayer(pcbnew.F_Mask);g.SetStart(pcbnew.VECTOR2I_MM(19,18));g.SetEnd(pcbnew.VECTOR2I_MM(38,20));g.SetWidth(200000);b.Add(g);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='bounded|clearance|edge'):proposal(source,uid,template)


def test_explicit_legend_only_policy_without_embedded_process(tmp_path):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));props=b.GetProperties();props.clear();b.SetProperties(props)
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError,match='declared_factory'):proposal(source,uid,template)
    q=ink.plan(source,selections=[dict(footprint_uuid=uid,template_path=str(template))],board_hint='synthetic',factory_legend_policy='jlcpcb')
    assert q['factory_floors']['profile']is None and q['factory_legend_policy']=='jlcpcb'
    assert q['factory_floors']['clearance_nm']>=150000 and source.read_bytes()==before
    child=force._copy_family(source,tmp_path/'child');ink.write_private(source,child,q)
    assert ink.receive(source,child,q,board_hint='synthetic')['ok']
    q['factory_legend_policy']=None
    with pytest.raises(ValueError):ink.construct(source,q)


@pytest.mark.parametrize('policy',[True,False,1,'unknown',''])
def test_invalid_explicit_factory_legend_policy_refused(tmp_path,policy):
    source,uid,template=fixture(tmp_path)
    with pytest.raises(ValueError,match='factory_legend_policy'):
        ink.plan(source,selections=[dict(footprint_uuid=uid,template_path=str(template))],board_hint='synthetic',factory_legend_policy=policy)


def test_legend_only_native_minima_clamp_and_existing_profile_retained(tmp_path):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    ds=b.GetDesignSettings();ds.m_SilkClearance=400000;ds.m_MinSilkTextThickness=250000
    f=ink._floors(b,source,'jlcpcb');assert f['profile']=='jlcpcb_6l_pofv_high_current'
    assert f['clearance_nm']==400000 and f['stroke_nm']==250000
    props=b.GetProperties();props.clear();b.SetProperties(props);f=ink._floors(b,source,'jlcpcb')
    assert f['profile']is None and f['clearance_nm']==400000 and f['stroke_nm']==250000
    props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    with pytest.raises(ValueError,match='unknown_embedded'):ink._floors(b,source,'jlcpcb')


def test_instance_bom_attribute_difference_only_is_not_template_geometry(tmp_path):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.SetAttributes(fp.GetAttributes()|pcbnew.FP_EXCLUDE_FROM_BOM);field._save_field_snapshot(b,source)
    q=proposal(source,uid,template);child=force._copy_family(source,tmp_path/'child');ink.write_private(source,child,q)
    assert ink.receive(source,child,q,board_hint='synthetic')['ok']
    assert next(iter(pcbnew.LoadBoard(str(child)).GetFootprints())).GetAttributes()&pcbnew.FP_EXCLUDE_FROM_BOM


@pytest.mark.parametrize('attr',[pcbnew.FP_SMD,pcbnew.FP_BOARD_ONLY,pcbnew.FP_EXCLUDE_FROM_POS_FILES,pcbnew.FP_DNP])
def test_other_instance_or_physical_attributes_remain_exact(tmp_path,attr):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.SetAttributes(fp.GetAttributes()^attr);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):proposal(source,uid,template)


@pytest.mark.parametrize('face',[pcbnew.F_SilkS,pcbnew.B_SilkS])
@pytest.mark.parametrize('default',[False,True])
@pytest.mark.parametrize('mode',[pcbnew.TENTING_MODE_FROM_BOARD,pcbnew.TENTING_MODE_TENTED,pcbnew.TENTING_MODE_NOT_TENTED])
def test_native_via_mask_policy_honors_actual_face_overrides_but_always_retains_bore(face,default,mode):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);ds=b.GetDesignSettings()
    ds.m_TentViasFront=default;ds.m_TentViasBack=not default
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(30,30));v.SetWidth(1000000);v.SetDrill(500000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetFrontTentingMode(mode);v.SetBackTentingMode(mode);b.Add(v);uid=force._uid(v)
    before=(v.GetFrontTentingMode(),v.GetBackTentingMode(),ds.m_TentViasFront,ds.m_TentViasBack)
    rows=ink._mask_openings(b,face,'native_mask_and_bore');by_id=dict(rows)
    assert uid+':hole'in by_id
    assert (uid in by_id)==(not v.IsTented(face))
    bore=by_id[uid+':hole'].BBox();assert 500000<=bore.GetWidth()<=500004
    # A point outside the drill but inside a tented land is not a mask
    # aperture. The actual bore itself remains forbidden native geometry.
    point=pcbnew.VECTOR2I_MM(30.4,30)
    assert any(poly.Collide(point,0)for _,poly in rows)==(not v.IsTented(face))
    assert any(poly.Collide(pcbnew.VECTOR2I_MM(30,30),0)for _,poly in rows)
    assert before==(v.GetFrontTentingMode(),v.GetBackTentingMode(),ds.m_TentViasFront,ds.m_TentViasBack)
    # Old conservative behavior remains opt-in independent and unchanged.
    assert uid in dict(ink._mask_openings(b,face))


@pytest.mark.parametrize('margin',[-100000,0,100000])
def test_untented_via_uses_native_mask_expansion_without_erasing_drill(margin):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);v=pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I_MM(30,30));v.SetWidth(1000000);v.SetDrill(500000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED);v.SetLocalSolderMaskMargin(margin);b.Add(v)
    rows=dict(ink._mask_openings(b,pcbnew.F_SilkS,'native_mask_and_bore'))
    width=rows[force._uid(v)].BBox().GetWidth()
    assert abs(width-(v.GetWidth()+2*v.GetSolderMaskExpansion()))<=4
    assert force._uid(v)+':hole'in rows


def test_native_mask_policy_saved_transaction_does_not_change_tenting_or_board_defaults(tmp_path):
    source,uid,template=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));ds=b.GetDesignSettings()
    ds.m_TentViasFront=True;ds.m_TentViasBack=False
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(45,40));v.SetWidth(1000000);v.SetDrill(500000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_FROM_BOARD);v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED);b.Add(v)
    field._save_field_snapshot(b,source);before=source.read_bytes()
    q=ink.plan(source,selections=[dict(footprint_uuid=uid,template_path=str(template))],board_hint='synthetic',
        via_ink_policy='native_mask_and_bore')
    child=force._copy_family(source,tmp_path/'native-mask');ink.write_private(source,child,q)
    r=ink.receive(source,child,q,board_hint='synthetic');assert r['ok'],r
    saved=pcbnew.LoadBoard(str(child));saved_via=next(iter(saved.GetTracks()))
    assert saved_via.GetFrontTentingMode()==v.GetFrontTentingMode()
    assert saved_via.GetBackTentingMode()==v.GetBackTentingMode()
    assert saved.GetDesignSettings().m_TentViasFront and not saved.GetDesignSettings().m_TentViasBack
    assert source.read_bytes()==before


@pytest.mark.parametrize('policy',[None,True,False,'skip_tented',''])
def test_unknown_via_ink_policy_never_erases_native_holes(policy):
    with pytest.raises(ValueError,match='explicit_native_via_ink_policy'):
        ink._mask_openings(pcbnew.BOARD(),pcbnew.F_SilkS,policy)
