"""Exact reference annotation reparenting is not library/body replacement."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_reference_map_reownership as op
import cec_field_coupling as field
import cec_force_current as force
import cec_assembly_envelope as assembly
from test_lastmile import _board


def fixture(tmp_path,quarter=0,back=False,reference='C7',offset=(0,0),package=None):
    board=_board([],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    alias,item=package or ('Capacitor_SMD','C_0603_1608Metric')
    directory=op.ROOT/'lib/vendor'/(alias+'.pretty')
    fp=pcbnew.FootprintLoad(str(directory),item);assert fp is not None
    board.Add(fp);fp.SetFPID(pcbnew.LIB_ID('cec-'+alias,item))
    fp.SetReference(reference);fp.SetValue('100nF');fp.Reference().SetVisible(False)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(quarter*90);fp.SetPosition(pcbnew.VECTOR2I_MM(20+offset[0],20+offset[1]))
    fp.BuildCourtyardCaches();face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    text=pcbnew.PCB_TEXT(fp);text.SetText(reference);text.SetLayer(face);text.SetMirrored(not back)
    text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000)
    text.SetPosition(pcbnew.VECTOR2I_MM(20+offset[0],(14 if package else 17)+offset[1]));text.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    text.SetLocked(True);fp.Add(text)
    court=pcbnew.SHAPE_POLY_SET(fp.GetCourtyard(fp.GetLayer()));chain=court.COutline(0)
    points=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for a,b in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(face)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*b));line.SetWidth(120000);line.SetLocked(True);fp.Add(line)
    from shapely.ops import nearest_points
    p=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(p,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
    glyph=assembly.polygon_from_native(p);polygon=assembly.polygon_from_native(court)
    a,b=nearest_points(polygon,glyph.envelope.buffer(.2+.12/2+.002,join_style=2))
    line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(face)
    line.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
    line.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in b.coords[0])));line.SetWidth(120000);line.SetLocked(True);fp.Add(line)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(board,source)
    table=source.parent/'fp-lib-table';table.write_text('(fp_lib_table (version 7)(lib (name '+json.dumps('cec-'+alias)+')(type "KiCad")(uri '+json.dumps(str(directory))+')(options "")))')
    return source,force._uid(fp),table


def proposal(source,owner,table):
    return op.plan(source,owner_uuid=owner,library_table=table,board_hint='synthetic')


def corner_fixture(tmp_path,quarter=0,back=False,internal=False):
    package=('Resistor_SMD','R_2512_6332Metric')if internal else None
    source,owner,table=fixture(tmp_path,quarter,back,package=package)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    court=pcbnew.SHAPE_POLY_SET(fp.GetCourtyard(fp.GetLayer()));chain=court.COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    edges={tuple(sorted((a,z)))for a,z in zip(vertices,vertices[1:]+vertices[:1])}
    lines=[i for i in fp.GraphicalItems()if i.GetLayer()==face and i.GetClass()=='PCB_SHAPE']
    remove=[i for i in lines if internal or tuple(sorted((tuple(i.GetStart()),tuple(i.GetEnd()))))in edges]
    from cec_native_items import discard_footprint_children
    discard_footprint_children(b,fp,remove)
    if internal:next(i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT').SetPosition(fp.GetPosition())
    # Independent literal producer arithmetic, not the new receiver helper.
    import math
    for i,a in enumerate(vertices):
        for z in(vertices[(i-1)%4],vertices[(i+1)%4]):
            length=math.dist(a,z);leg=min(350000.,length/3)
            end=tuple(round(a[k]+(z[k]-a[k])*leg/length)for k in(0,1))
            line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(face)
            line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*end))
            line.SetWidth(120000);line.SetLocked(True);fp.Add(line)
    field._save_field_snapshot(b,source);return source,owner,table


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_eight_corner_arms_reown_world_print_not_assembly_body(tmp_path,quarter,back):
    source,owner,table=corner_fixture(tmp_path,quarter,back);before=force._family(source)
    q=proposal(source,owner,table);assert len(q['member_uuids'])==10
    child=tmp_path/'private'/'board.kicad_pcb';op.construct(source,child,q)
    r=op.receive(source,child,q,board_hint='synthetic');assert r['ok']and r['complete'],r
    p=op.transport.inspect(child,owner_uuid=owner,group_uuid=q['group_uuid'])
    assert p['outline_style']=='four_exact_source_rectangular_corner_brackets'
    assert p['closed_assembly_body_authority']is False
    assert force._family(source)==before
    assert not r['native_drc_qualified']and not r['release_authority']


def test_exact_internal_corner_map_has_no_invented_leader(tmp_path):
    source,owner,table=corner_fixture(tmp_path,internal=True);q=proposal(source,owner,table)
    assert len(q['member_uuids'])==9
    child=tmp_path/'private'/'board.kicad_pcb';op.construct(source,child,q)
    assert op.receive(source,child,q,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',['missing_arm','corner_1nm','arm_length_1nm','duplicate_arm',
    'extra_art','wrong_text','wrong_leader','borrowed_arm'])
def test_corner_maps_require_every_exact_arm_and_unambiguous_source_association(tmp_path,fault):
    source,owner,table=corner_fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    lines=[i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.B_SilkS and i.GetClass()=='PCB_SHAPE']
    # The sole leader is longer than every bounded <=.35mm corner arm.
    leader=max(lines,key=lambda i:(i.GetEnd()-i.GetStart()).EuclideanNorm())
    arm=next(i for i in lines if force._uid(i)!=force._uid(leader))
    if fault=='missing_arm':
        from cec_native_items import discard_footprint_children
        discard_footprint_children(b,fp,[arm])
    elif fault=='corner_1nm':arm.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='arm_length_1nm':arm.SetEnd(arm.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault in('duplicate_arm','extra_art'):
        extra=arm.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID())
        if fault=='extra_art':extra.Move(pcbnew.VECTOR2I(1000000,1000000))
        fp.Add(extra)
    elif fault=='wrong_text':next(i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT').SetText('OTHER OWNER')
    elif fault=='wrong_leader':
        # Moving a vertical nearest leader horizontally by1nm can select an
        # equally valid minimum on parallel edges. This negative must leave
        # the exact court/glyph boundaries, not assert a traversal tie-break.
        delta=leader.GetEnd()-leader.GetStart()
        leader.Move(pcbnew.VECTOR2I(0,1)if delta.y else pcbnew.VECTOR2I(1,0))
    else:arm.SetStart(pcbnew.VECTOR2I_MM(30,30));arm.SetEnd(pcbnew.VECTOR2I_MM(30.35,30))
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError):proposal(source,owner,table)
    assert source.read_bytes()==before


def test_corner_map_integer_nearest_tie_is_still_an_exact_owned_leader(tmp_path):
    source,owner,table=corner_fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    lines=[i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.B_SilkS and i.GetClass()=='PCB_SHAPE']
    leader=max(lines,key=lambda i:(i.GetEnd()-i.GetStart()).EuclideanNorm())
    delta=leader.GetEnd()-leader.GetStart();assert delta.x==0 and delta.y!=0
    leader.Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(b,source)
    q=proposal(source,owner,table);child=tmp_path/'child'/'board.kicad_pcb'
    op.construct(source,child,q)
    received=op.receive(source,child,q,board_hint='synthetic')
    assert received['ok']and received['complete'],received


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_twelve_edge_vendor_court_is_independently_received(tmp_path,quarter,back):
    source,owner,table=fixture(tmp_path,quarter,back,package=('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    before=force._family(source);q=proposal(source,owner,table)
    assert len(q['member_uuids'])==14 # twelve court edges, exact leader, reference
    child=tmp_path/'child'/'board.kicad_pcb';op.construct(source,child,q)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert force._family(source)==before and not r['native_drc_qualified']
    parent=pcbnew.LoadBoard(str(source));saved=pcbnew.LoadBoard(str(child))
    assert len(list(saved.GetDrawings()))==len(list(parent.GetDrawings()))+14


@pytest.mark.parametrize('fault',['missing_edge','partial_edge','duplicate_leader','wrong_leader',
    'extra_art','extra_text','corner_brackets'])
def test_more_members_are_not_authority_for_partial_or_unowned_styles(tmp_path,fault):
    source,owner,table=fixture(tmp_path,package=('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    lines=[i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.B_SilkS and i.GetClass()=='PCB_SHAPE']
    # Native child insertion order is retained by this fixture; identify exact
    # court edges geometrically rather than trusting an annotation label.
    court=pcbnew.SHAPE_POLY_SET(fp.GetCourtyard(fp.GetLayer()));chain=court.COutline(0)
    points=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    edges={tuple(sorted((a,z)))for a,z in zip(points,points[1:]+points[:1])}
    courtlines=[i for i in lines if tuple(sorted((tuple(i.GetStart()),tuple(i.GetEnd()))))in edges]
    leader=next(i for i in lines if i not in courtlines)
    if fault=='missing_edge':
        from cec_native_items import discard_footprint_children
        discard_footprint_children(b,fp,[courtlines[0]])
    elif fault=='partial_edge':courtlines[0].SetEnd(courtlines[0].GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault in ('duplicate_leader','extra_art'):
        extra=leader.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID())
        if fault=='extra_art':extra.Move(pcbnew.VECTOR2I(123000,456000))
        fp.Add(extra)
    elif fault=='wrong_leader':leader.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_text':
        extra=next(i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT').Duplicate()
        extra.m_Uuid.Clone(pcbnew.KIID());extra.SetText('historical label');fp.Add(extra)
    else:
        # Valid corner fragments are deliberately unsupported by the existing
        # independent closed-outline authority; never infer missing edges.
        for line in courtlines:
            a,z=line.GetStart(),line.GetEnd();line.SetEnd(pcbnew.VECTOR2I((3*a.x+z.x)//4,(3*a.y+z.y)//4))
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError):proposal(source,owner,table)
    assert source.read_bytes()==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_saved_reownership_preserves_source_and_all_world_art(tmp_path,quarter,back):
    source,owner,table=fixture(tmp_path,quarter,back);before=force._family(source)
    q=proposal(source,owner,table)
    child=tmp_path/'private'/'child.kicad_pcb';op.construct(source,child,q)
    r=op.receive(source,child,q,board_hint='synthetic');assert r['ok'] and r['complete'],r
    assert force._family(source)==before
    assert r['native_nonregression_still_required'] and not r['native_drc_qualified']
    parent=pcbnew.LoadBoard(str(source));saved=pcbnew.LoadBoard(str(child))
    assert len(list(parent.GetDrawings()))+6==len(list(saved.GetDrawings()))
    assert next(iter(saved.GetFootprints())).GetReference()=='C7'
    assert len(list(next(iter(saved.GetFootprints())).Pads()))==2


@pytest.mark.parametrize('fault',['wrong_text','mirror','font','partial_map','bracket','copper','pad','body','grouped','visible','locked_owner','unknown_library'])
def test_untyped_or_noncanonical_source_never_grants_reownership(tmp_path,fault):
    source,owner,table=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    members=[i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.B_SilkS]
    text=next(i for i in members if i.GetClass()=='PCB_TEXT');line=next(i for i in members if i.GetClass()=='PCB_SHAPE')
    if fault=='wrong_text':text.SetText('POLARITY')
    elif fault=='mirror':text.SetMirrored(False)
    elif fault=='font':text.SetTextSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='partial_map':
        from cec_native_items import discard_footprint_children
        discard_footprint_children(b,fp,[line])
    elif fault=='bracket':
        extra=line.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());fp.Add(extra)
    elif fault=='copper':line.SetLayer(pcbnew.B_Cu)
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='body':
        next(i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.F_SilkS and i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='grouped':
        g=pcbnew.PCB_GROUP(b);g.SetName('existing owner');b.Add(g);g.AddItem(fp)
    elif fault=='visible':fp.Reference().SetVisible(True)
    elif fault=='locked_owner':fp.SetLocked(True)
    else:fp.SetFPID(pcbnew.LIB_ID('unknown','C_0603_1608Metric'))
    field._save_field_snapshot(b,source)
    before=source.read_bytes()
    with pytest.raises(ValueError):proposal(source,owner,table)
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['label','line','pad','pose','field','sidecar','extra_node'])
def test_literal_saved_receiver_refuses_any_unowned_edit(tmp_path,fault):
    source,owner,table=fixture(tmp_path);q=proposal(source,owner,table)
    child=tmp_path/'child'/'board.kicad_pcb';op.construct(source,child,q)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
    if fault=='label':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetText('C8')
    elif fault=='line':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='field':fp.SetValue('different')
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    else:child.write_text(child.read_text().replace('(kicad_pcb','(kicad_pcb (unknown yes)',1))
    if fault not in ('sidecar','extra_node'):field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic');assert not r['ok'] and not r['complete'],r


def test_stale_and_forged_plans_never_write_a_candidate(tmp_path):
    source,owner,table=fixture(tmp_path);q=proposal(source,owner,table)
    forged=copy.deepcopy(q);forged['expected_text']+=' '
    with pytest.raises(ValueError):op.construct(source,tmp_path/'forged'/'board.kicad_pcb',forged)
    table.write_text(table.read_text()+'\n')
    with pytest.raises(ValueError):op.construct(source,tmp_path/'stale'/'board.kicad_pcb',q)
    assert not (tmp_path/'forged').exists() and not (tmp_path/'stale').exists()


def test_json_roundtrip_and_source_control_are_not_admission(tmp_path):
    source,owner,table=fixture(tmp_path);q=json.loads(json.dumps(proposal(source,owner,table)))
    control=source.read_bytes()
    assert not op.receive(source,source,q,board_hint='synthetic')['ok']
    child=tmp_path/'derived'/'board.kicad_pcb';op.construct(source,child,q)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'] and source.read_bytes()==control
    assert not r['native_drc_qualified'] and not r['release_authority']


def test_late_epoch_refusal_rolls_back_only_own_private_family(tmp_path,monkeypatch):
    source,owner,table=fixture(tmp_path)
    source.with_suffix('.opaque-proof.json').write_text('{"historical":true}')
    q=proposal(source,owner,table);before=force._family(source);actual=op._epoch;calls=0
    def late(*args):
        nonlocal calls
        calls+=1
        return {'changed':True} if calls==3 else actual(*args)
    monkeypatch.setattr(op,'_epoch',late)
    child=tmp_path/'late'/'board.kicad_pcb'
    with pytest.raises(ValueError,match='late_reference_source_epoch_changed'):
        op.construct(source,child,q)
    assert not child.exists() and not child.parent.exists()
    assert force._family(source)==before


def test_existing_output_is_never_overwritten(tmp_path):
    source,owner,table=fixture(tmp_path);q=proposal(source,owner,table)
    child=tmp_path/'existing'/'board.kicad_pcb';child.parent.mkdir();child.write_text('untouched')
    with pytest.raises(ValueError):op.construct(source,child,q)
    assert child.read_text()=='untouched'


@pytest.mark.parametrize('timeout',[True,0,-1,float('nan'),10.01])
def test_work_bounds_fail_closed(tmp_path,timeout):
    source,owner,table=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,owner_uuid=owner,library_table=table,board_hint='synthetic',timeout_s=timeout)


def batch_fixture(tmp_path,quarter=0,back=True,package=None):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    source,first,table=fixture(a,package=package)
    other,second,_=fixture(b,quarter=quarter,back=back,reference='C8',offset=(10,10),package=package)
    board=pcbnew.LoadBoard(str(source));peer=pcbnew.LoadBoard(str(other))
    fp=next(iter(peer.GetFootprints())).Duplicate(False);board.Add(fp)
    second=force._uid(fp);field._save_field_snapshot(board,source)
    return source,[first,second],table


def batch_plan(source,owners,table,**kwargs):
    return op.plan_batch(source,owner_uuids=owners,library_table=table,board_hint='synthetic',**kwargs)


def test_multi_edge_closed_maps_compose_without_fixed_six_child_assumption(tmp_path):
    source,owners,table=batch_fixture(tmp_path,quarter=1,back=True,
        package=('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
    before=force._family(source);q=batch_plan(source,owners,table)
    assert all(len(c['member_uuids'])==14 for c in q['contracts'])
    child=tmp_path/'batch'/'board.kicad_pcb';op.construct_batch(source,child,q)
    r=op.receive_batch(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    parent=pcbnew.LoadBoard(str(source));saved=pcbnew.LoadBoard(str(child))
    assert len(list(saved.GetDrawings()))==len(list(parent.GetDrawings()))+28
    assert force._family(source)==before


@pytest.mark.parametrize('quarter,back',[(0,False),(1,True),(2,False),(3,True)])
def test_two_original_owner_maps_are_one_exact_saved_batch(tmp_path,quarter,back):
    source,owners,table=batch_fixture(tmp_path,quarter,back);before=force._family(source)
    q=batch_plan(source,list(reversed(owners)),table)
    assert q['original_source_only'] and len(q['contracts'])==2
    assert all('expected_text' not in one for one in q['contracts'])
    q=json.loads(json.dumps(q));child=tmp_path/'batch'/'board.kicad_pcb'
    op.construct_batch(source,child,q)
    r=op.receive_batch(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['owner_count']==2,r
    assert r['exact_whole_literal_board_received'] and r['native_nonregression_still_required']
    assert not r['partial_batch_authority'] and not r['native_drc_qualified']
    assert force._family(source)==before
    original=pcbnew.LoadBoard(str(source));saved=pcbnew.LoadBoard(str(child))
    assert len(list(saved.GetDrawings()))==len(list(original.GetDrawings()))+12
    assert sorted(fp.GetReference()for fp in saved.GetFootprints())==['C7','C8']


@pytest.mark.parametrize('fault',['label','line','copper','mask','part','pose','extra_group'])
def test_saved_batch_rejects_unowned_whole_board_changes(tmp_path,fault):
    source,owners,table=batch_fixture(tmp_path);q=batch_plan(source,owners,table)
    child=tmp_path/'batch'/'board.kicad_pcb';op.construct_batch(source,child,q)
    b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
    if fault=='label':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetText('changed')
    elif fault=='line':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='copper':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='mask':next(iter(fp.Pads())).SetLocalSolderMaskMargin(1)
    elif fault=='part':fp.SetValue('changed')
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    else:
        g=pcbnew.PCB_GROUP(b);g.SetName('unowned');b.Add(g)
    field._save_field_snapshot(b,child)
    result=op.receive_batch(source,child,q,board_hint='synthetic')
    assert not result['ok'] and not result['complete'],result


def test_one_bad_original_owner_refuses_the_entire_batch(tmp_path):
    source,owners,table=batch_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    fp=next(fp for fp in b.GetFootprints()if force._uid(fp)==owners[-1])
    next(i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT'and i.GetLayer()==pcbnew.F_SilkS).SetText('not-the-reference')
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError):batch_plan(source,owners,table)
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['duplicate_owner','shared_child_uuid','group_uuid_collision','shared_group_uuid'])
def test_batch_cannot_share_original_members_or_group_ownership(tmp_path,monkeypatch,fault):
    source,owners,table=batch_fixture(tmp_path)
    if fault=='duplicate_owner':owners=[owners[0],owners[0]]
    elif fault=='shared_child_uuid':
        b=pcbnew.LoadBoard(str(source));maps=[]
        for fp in b.GetFootprints():maps.append(next(i for i in fp.GraphicalItems()if i.GetClass()=='PCB_TEXT'and i.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)))
        source.write_text(source.read_text().replace(force._uid(maps[1]),force._uid(maps[0])))
    else:
        fixed=op.uuid.UUID(owners[0]) if fault=='group_uuid_collision' else op.uuid.uuid4()
        monkeypatch.setattr(op.uuid,'uuid5',lambda *args:fixed)
    with pytest.raises(ValueError):batch_plan(source,owners,table)


@pytest.mark.parametrize('fault',['source','table','vendor','code'])
def test_source_code_and_vendor_epoch_drift_refuse_batch_before_write(tmp_path,monkeypatch,fault):
    source,owners,table=batch_fixture(tmp_path)
    if fault=='vendor':
        repo=tmp_path/'repo';directory=repo/'lib/vendor/Capacitor_SMD.pretty';directory.mkdir(parents=True)
        target=directory/'C_0603_1608Metric.kicad_mod'
        target.write_bytes((op.ROOT/'lib/vendor/Capacitor_SMD.pretty'/target.name).read_bytes())
        table.write_text(table.read_text().replace(str(op.ROOT/'lib/vendor/Capacitor_SMD.pretty'),str(directory)))
        monkeypatch.setattr(op,'ROOT',repo)
    q=batch_plan(source,owners,table)
    if fault=='source':source.write_text(source.read_text()+'\n')
    elif fault=='table':table.write_text(table.read_text()+'\n')
    elif fault=='vendor':target.write_text(target.read_text()+'\n')
    else:
        actual=op._epoch
        def changed(*args):
            result=actual(*args);result['code']={'changed':True};return result
        monkeypatch.setattr(op,'_epoch',changed)
    child=tmp_path/'refused'/'board.kicad_pcb'
    with pytest.raises(ValueError):op.construct_batch(source,child,q)
    assert not child.parent.exists()


@pytest.mark.parametrize('kwargs',[{'owner_uuids':[]},{'owner_uuids':['x']*17},
    {'wall_s':True},{'wall_s':0},{'wall_s':301},{'proof_s':True},{'proof_s':10.01},
    {'wall_s':1,'proof_s':2}])
def test_whole_batch_and_per_owner_effort_are_explicitly_bounded(tmp_path,kwargs):
    source,owners,table=batch_fixture(tmp_path);values=dict(owner_uuids=owners,library_table=table,board_hint='synthetic');values.update(kwargs)
    with pytest.raises(ValueError):op.plan_batch(source,**values)


def test_batch_receiver_does_not_borrow_a_larger_plan_lease(tmp_path):
    source,owners,table=batch_fixture(tmp_path);q=batch_plan(source,owners,table)
    child=tmp_path/'child'/'board.kicad_pcb';op.construct_batch(source,child,q)
    result=op.receive_batch(source,child,q,board_hint='synthetic',wall_s=10.)
    assert not result['ok'] and any('receiver_whole_lease' in x for x in result['errors'])


def test_owner_ceiling_is_sixteen_distinct_original_ids_not_a_hint():
    op._batch_settings([str(i) for i in range(16)],120.,10.)
    with pytest.raises(ValueError):op._batch_settings([str(i) for i in range(17)],120.,10.)
