"""Real canonical capacitor identity and native saved repair; no missing role."""
from pathlib import Path
import pcbnew
import pytest
import cec_source_cap_ground_via_repair as op
from test_source_aggregate_capacitor_cell import fixture as base_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch):
    source,root,_=base_fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference('RENAMED_C')
    pad=fp.FindPadByNumber('2')
    # Synthetic larger capacitor land: canonical fields/net membership are
    # real; this test does not claim package-library fabrication approval.
    pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    for v in list(board.GetTracks()):
        if v.GetClass()=='PCB_VIA':board.Remove(v)
    via=pcbnew.PCB_VIA(board);via.SetNet(pad.GetNet())
    via.SetPosition(pcbnew.VECTOR2I(pad.GetPosition().x+350000,pad.GetPosition().y))
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetLocked(True);board.Add(via)
    op.additive._ground_refill(board);op.additive.field._save_field_snapshot(board,source)
    return source,str(root),op.barrel.force._uid(pad),op.barrel.force._uid(via),list(pad.GetPosition())


def plan(data):
    source,hint,pad,via,target=data
    return op.plan(source,pad,via,target,board_hint=hint,allow_locked_via_uuid=via)


def child(data,tmp_path,fault=None):
    source,hint,pad,via,target=data
    candidate=op.barrel.force._copy_family(source,tmp_path/'child')
    board=pcbnew.LoadBoard(str(source));p,v,_=op.barrel._objects(board,pad,via)
    v.SetPosition(pcbnew.VECTOR2I(*target))
    if fault=='width':v.SetWidth(510000)
    elif fault=='drill':v.SetDrill(310000)
    elif fault=='lock':v.SetLocked(False)
    elif fault=='uuid':v.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='position':v.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='footprint':p.GetParentFootprint().SetValue('other')
    elif fault=='extra_track':track(board,'/ALPHA',(20,20),(21,20),width=.5)
    elif fault=='lost_plane':board.Remove(next(iter(board.Zones())))
    elif fault=='unrelated_width':
        stroke=next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK')
        stroke.SetWidth(stroke.GetWidth()+10000)
    elif fault=='setup':board.GetDesignSettings().m_SolderPasteMargin+=10000
    op.additive._ground_refill(board);op.additive.field._save_field_snapshot(board,candidate)
    if fault is None:
        grounds=[op.barrel.force._uid(z)for z in board.Zones()
                 if z.GetNetname()=='GND'and not z.GetIsRuleArea()]
        candidate.write_text(op.literal.assemble(op.retirement.subtract(op.raw.raw_text(source),{via}),
            op.raw.raw_text(candidate),ground_ids=grounds))
    if fault=='unrelated_net':
        text=candidate.read_text();_,end=op.literal._root(text)
        candidate.write_text(text[:end]+'(net 999 "UNRELATED_EXTRA")\n'+text[end:])
    if fault=='sidecar':
        project=candidate.with_suffix('.kicad_pro')
        project.write_text(project.read_text()+'\n')
    return candidate


def test_exact_same_barrel_reseat_preserves_all_saved_native_partitions(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);proof=plan(data);original=data[0].read_bytes()
    candidate=child(data,tmp_path)
    result=op.receive(data[0],candidate,proof,board_hint=data[1])
    assert result['ok']and result['complete']and result['retained_native_partitions']['preserved']
    assert result['original_via_dimensions_and_identity_preserved']
    assert proof['source_inpad_containment_qualified']is False
    assert proof['diameter_nm']==500000 and proof['drill_nm']==300000
    assert len(proof['source_reference_contacts'])==2
    assert not any(result[k]for k in('admitted','current_qualified','fabrication_qualified','release_authority'))
    assert data[0].read_bytes()==original


@pytest.mark.parametrize('fault',['width','drill','lock','uuid','position','footprint','extra_track','lost_plane',
                                  'unrelated_width','setup','unrelated_net','sidecar'])
def test_candidate_changes_or_missing_returns_refused(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);proof=plan(data);candidate=child(data,tmp_path,fault)
    with pytest.raises(ValueError):op.receive(data[0],candidate,proof,board_hint=data[1])


@pytest.mark.parametrize('fault',['no_consent','wrong_consent','already_contained','other_track','foreign_plane',
                                  'no_contact','target_partial','target_bool','timeout_bool'])
def test_source_debt_and_exclusive_positive_target_are_mandatory(tmp_path,monkeypatch,fault):
    source,hint,pad,via,target=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));p,v,_=op.barrel._objects(board,pad,via)
    options=dict(allow_locked_via_uuid=via)
    if fault=='no_consent':options={}
    elif fault=='wrong_consent':options['allow_locked_via_uuid']='other'
    elif fault=='already_contained':v.SetPosition(pcbnew.VECTOR2I(*target))
    elif fault=='other_track':track(board,'GND',(10.85,10),(11.5,10),width=.2)
    elif fault=='foreign_plane':next(iter(board.Zones())).SetNet(board.FindNet('/ALPHA'))
    elif fault=='no_contact':v.Move(pcbnew.VECTOR2I_MM(1,0))
    elif fault=='target_partial':target[0]+=350000
    elif fault=='target_bool':target[0]=True
    elif fault=='timeout_bool':options['timeout_s']=True
    if fault!='foreign_plane':op.additive._ground_refill(board)
    op.additive.field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):op.plan(source,pad,via,target,board_hint=hint,**options)


@pytest.mark.parametrize('candidate_side',[False,True])
def test_relevant_unfilled_zone_is_unknown_not_absent_copper(tmp_path,monkeypatch,candidate_side):
    data=fixture(tmp_path,monkeypatch)
    proof=plan(data) if candidate_side else None
    path=child(data,tmp_path) if candidate_side else data[0]
    board=pcbnew.LoadBoard(str(path));zone=next(iter(board.Zones()))
    zone.SetIsFilled(False);zone.SetFilledPolysList(zone.GetLayer(),pcbnew.SHAPE_POLY_SET())
    op.additive.field._save_field_snapshot(board,path)
    with pytest.raises(ValueError,match='repair_relevant_saved_zone_fill_unknown'):
        if candidate_side:op.receive(data[0],path,proof,board_hint=data[1])
        else:plan(data)


@pytest.mark.parametrize('alter_opaque',[False,True])
def test_unrelated_opaque_text_missing_zero_angle_remains_exact(tmp_path,monkeypatch,alter_opaque):
    import uuid
    data=fixture(tmp_path,monkeypatch);source,hint,pad,via,target=data
    text=op.raw.raw_text(source);_,end=op.literal._root(text)
    text_uid=str(uuid.uuid4())
    node='(gr_text "OPAQUE" (at 24 24) (layer "B.SilkS") (uuid "'+text_uid+'") '+\
         '(effects (font (size 1 1) (thickness 0.15)) (justify mirror)))'
    source.write_text(text[:end]+node+'\n'+text[end:])
    proof=plan(data)
    candidate=child(data,tmp_path)
    native_text=op.raw.raw_text(candidate)
    # The candidate producer also retains Source lexemes instead of accepting
    # SaveBoard's unrelated '(at 24 24 0)' serialization normalization.
    grounds=[op.barrel.force._uid(z)for z in pcbnew.LoadBoard(str(source)).Zones()
             if z.GetNetname()=='GND' and not z.GetIsRuleArea()]
    candidate.write_text(op.literal.assemble(op.retirement.subtract(op.raw.raw_text(source),{via}),
        native_text,ground_ids=grounds))
    if alter_opaque:candidate.write_text(candidate.read_text().replace('"OPAQUE"','"ALTERED"'))
    if alter_opaque:
        with pytest.raises(ValueError,match='repair_only_exact_via_seat'):
            op.receive(source,candidate,proof,board_hint=hint)
    else:
        result=op.receive(source,candidate,proof,board_hint=hint)
        assert result['ok'] and result['complete']
        saved=op.literal._inventory(candidate.read_text())[0][text_uid][2]
        assert '(at 24 24)'in saved and '(at 24 24 0)'not in saved


def test_full_root_token_comparison_ignores_only_real_comments_and_whitespace():
    assert op._root_tokens('(a "x ; y" 1)')==op._root_tokens(' (a\n "x ; y" ; ignored\n 1 )')
    assert op._root_tokens('(at 1 2)')!=op._root_tokens('(at 1 2 0)')
    assert op._root_tokens('(a "x ; y")')!=op._root_tokens('(a "x y")')
    assert op._root_tokens('(a 1) "')!=op._root_tokens('(a 1)')


@pytest.mark.parametrize('degrees',[0,90,180,270])
def test_complete_native_fixture_rigid_transform_retains_same_repair_and_partitions(tmp_path,monkeypatch,degrees):
    source,hint,pad,via,_=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source))
    origin=pcbnew.VECTOR2I(0,0);angle=pcbnew.EDA_ANGLE(degrees,pcbnew.DEGREES_T)
    offset=pcbnew.VECTOR2I_MM(80,100)
    # Transform each top-level native object once; footprints own their pads,
    # fields and graphics. Native refill rebuilds the transformed zone metal.
    objects=[*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings(),*board.Zones()]
    for item in objects:
        item.Rotate(origin,angle);item.Move(offset)
    op.additive._ground_refill(board);op.additive.field._save_field_snapshot(board,source)
    target=list(next(p for f in board.GetFootprints()for p in f.Pads()
                     if op.barrel.force._uid(p)==pad).GetPosition())
    data=(source,hint,pad,via,target);proof=plan(data);candidate=child(data,tmp_path)
    before=source.read_bytes()
    result=op.receive(source,candidate,proof,board_hint=hint)
    assert result['ok']and result['complete']and result['retained_native_partitions']['preserved']
    assert result['original_returns_preserved']
    assert proof['diameter_nm']==500000 and proof['drill_nm']==300000
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['trailing_junk','escaped_quote_change'])
def test_complete_candidate_tokens_cannot_hide_junk_or_escaped_string_changes(tmp_path,monkeypatch,fault):
    import uuid
    data=fixture(tmp_path,monkeypatch);source,hint,pad,via,target=data
    text=source.read_text();_,end=op.literal._root(text)
    # The semicolon and escaped quote belong to the quoted text token, not
    # to a comment or a delimiter. Preserve this exact opaque Source node.
    node='(gr_text "quote \\"; keep" (at 24 24) (layer "B.SilkS") (uuid "'+str(uuid.uuid4())+'") '+\
         '(effects (font (size 1 1) (thickness 0.15)) (justify mirror)))'
    source.write_text(text[:end]+node+'\n'+text[end:])
    proof=plan(data);candidate=child(data,tmp_path)
    if fault=='trailing_junk':candidate.write_text(candidate.read_text()+'\nUNEXPECTED_TRAILING_TOKEN\n')
    else:candidate.write_text(candidate.read_text().replace('keep','altered'))
    with pytest.raises((ValueError,OSError)):
        op.receive(source,candidate,proof,board_hint=hint)


def test_exact_tokens_keep_escaped_quote_and_semicolon_inside_strings():
    text=r'(a "quoted \"; still string" 1)'
    assert op._root_tokens(text)==op._root_tokens(text+' ; actual comment\n')
    assert op._root_tokens(text)!=op._root_tokens(text.replace('still','changed'))
    assert op._root_tokens(text)!=op._root_tokens(text+' TRAILING')
