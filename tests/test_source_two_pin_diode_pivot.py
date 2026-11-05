"""Real hierarchy/export and saved native replay; only current model is stubbed.

The existing aggregate-current authority fixture is reused, not a simulated
physical/partition verdict.  Diode spelling never supplies a protection model.
"""
import time
import pcbnew
import pytest
import cec_source_two_pin_diode_pivot as op
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_source_aggregate_capacitor_cell import fixture as cap_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    source,root,uid=cap_fixture(tmp_path,monkeypatch,quarter,back,kind='D_Schottky')
    b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if op.force._uid(f)==uid)
    fp.Reference().SetVisible(False)
    group=pcbnew.PCB_GROUP(b);group.SetName(op.reference.PREFIX+fp.GetReference());b.Add(group);group.AddItem(fp)
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    text=pcbnew.PCB_TEXT(b);text.SetText(fp.GetReference());text.SetLayer(face);text.SetMirrored(not back)
    text.SetTextSize(pcbnew.VECTOR2I_MM(1.2,1.2));text.SetTextThickness(150000);text.SetTextPos(fp.GetPosition());text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    chain=fp.GetCourtyard(fp.GetLayer()).COutline(0);points=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    for a,z in zip(points,points[1:]+points[:1]):
        item=pcbnew.PCB_SHAPE(b);item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(face)
        item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*z));item.SetWidth(150000);b.Add(item);group.AddItem(item)
    import cec_assembly_envelope as assembly
    from shapely.ops import nearest_points
    court=assembly.polygon_from_native(fp.GetCourtyard(fp.GetLayer()))
    text.SetTextPos(pcbnew.VECTOR2I(round((court.bounds[2]+6)*1e6),fp.GetPosition().y))
    poly=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
    glyph=assembly.polygon_from_native(poly)
    rules=op.reference._cardinal_rules(source,b)
    gap=max(round(rules['silk_clearance']*1e6),b.GetDesignSettings().m_SilkClearance)
    a,z=nearest_points(court,glyph.envelope.buffer((gap+75000+2000)/1e6,join_style=2))
    leader=pcbnew.PCB_SHAPE(b);leader.SetShape(pcbnew.SHAPE_T_SEGMENT);leader.SetLayer(face)
    leader.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
    leader.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])));leader.SetWidth(150000);b.Add(leader);group.AddItem(leader)
    group.SetLocked(True);fp.SetLocked(False);field._save_field_snapshot(b,source)
    args=dict(owner_uuid=uid,ground_pad_uuid=op.force._uid(fp.FindPadByNumber('2')),
        reference_group_uuid=op.force._uid(group),board_hint=str(root))
    return source,root,args


def saved(tmp_path,monkeypatch,quarter=0,back=False):
    source,root,args=fixture(tmp_path,monkeypatch,quarter,back)
    b,q=op.plan(source,**args)
    assert q['pose_screen']['ok'],q['pose_screen']
    target=op.force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);op.save_private(b,target,q)
    return source,target,args,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_renamed_diode_halfturn_keeps_Ground_and_closed_map(tmp_path,monkeypatch,quarter,back):
    source,target,args,q=saved(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();r=op.receive(source,target,**args)
    assert r['ok']and r['complete'],r
    assert r['all_original_terminal_and_copper_partitions_preserved']
    assert r['source_closed_reference_map_rigid_half_turn']
    assert not r['protection_qualified']and not r['release_authority']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['symbol','manufacturer','pin_net','pin_type','locked','hole','pad_group','arbitrary_group','source_contact','wrong_ground','copper_graphic'])
def test_actual_Source_not_diode_spelling_grants_scope(tmp_path,monkeypatch,fault):
    source,root,args=fixture(tmp_path,monkeypatch)
    if fault in ('symbol','manufacturer','pin_net','pin_type'):
        text=root.read_text()
        if fault=='symbol':text=text.replace('fixture:D_Schottky"','fixture:R"')
        elif fault=='manufacturer':text=text.replace('FIXTURE_VENDOR','OTHER_VENDOR')
        elif fault=='pin_net':text=text.replace('"ALPHA"','"OTHER"')
        else:text=text.replace('(pin passive line','(pin power_in line',1)
        root.write_text(text)
    elif fault=='wrong_ground':args['ground_pad_uuid']='invented'
    else:
        b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if op.force._uid(f)==args['owner_uuid']);pad=fp.FindPadByNumber('1')
        if fault=='locked':fp.SetLocked(True)
        elif fault=='hole':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
        elif fault=='pad_group':next(iter(b.Groups())).AddItem(pad)
        elif fault=='arbitrary_group':next(iter(b.Groups())).SetName('unrecognized')
        elif fault=='copper_graphic':
            item=pcbnew.PCB_SHAPE(fp);item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(pcbnew.F_Cu)
            item.SetStart(fp.GetPosition());item.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I(100000,0));item.SetWidth(200000);fp.Add(item)
        elif fault=='source_contact':
            at=pad.GetPosition();track(b,pad.GetNetname(),(at.x/1e6,at.y/1e6),(at.x/1e6-1,at.y/1e6),width=.5)
        field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,**args)


@pytest.mark.parametrize('fault',['Ground_shape','reference_ink','group_members','supply_geometry','old_copper','addition','wrong_pose'])
def test_saved_forgery_cannot_be_a_native_pose_proof(tmp_path,monkeypatch,fault):
    source,target,args,q=saved(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(target));fp=next(f for f in b.GetFootprints()if op.force._uid(f)==args['owner_uuid'])
    if fault=='Ground_shape':fp.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(.9,.8))
    elif fault=='reference_ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='group_members':next(iter(b.Groups())).RemoveItem(fp)
    elif fault=='supply_geometry':fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.7,.6))
    elif fault=='old_copper':next(iter(b.Zones())).SetLocalClearance(300000)
    elif fault=='addition':track(b,'/ALPHA',(25,25),(26,25),width=.5)
    else:fp.Move(pcbnew.VECTOR2I(1000,0))
    field._save_field_snapshot(b,target)
    r=op.receive(source,target,**args)
    assert not r['ok']and r['errors'],r


def test_expired_Source_inspection_has_no_following_stage_rescue(tmp_path,monkeypatch):
    source,root,args=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='deadline'):
        op.inspect(b,source,owner_uuid=args['owner_uuid'],ground_pad_uuid=args['ground_pad_uuid'],
            group_uuid=args['reference_group_uuid'],board_hint=str(root),deadline=time.monotonic()-1)
