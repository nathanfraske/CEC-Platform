import copy
from pathlib import Path
import pcbnew,pytest
from shapely.ops import nearest_points
import cec_root_reference_seating as op
from test_source_reference_group_cardinal import fixture as original


def fixture(tmp_path,back=False,turn=0,brackets=False):
    source,proof=original(tmp_path,back=back,source_turn=turn,external=True)
    b=pcbnew.LoadBoard(str(source));fp,text,leader,court,lines=op._nodes(b,proof)
    # Cardinal transport's fixture deliberately strips all root drawings,
    # including its old outline; seating additionally requires real substrate.
    for a,z in (((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))):
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));edge.SetWidth(50000);b.Add(edge)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    text.SetTextSize(pcbnew.VECTOR2I_MM(1,1));text.SetTextThickness(150000)
    for line in lines:line.SetWidth(150000)
    op.field._save_field_snapshot(b,source)
    floor=op.seats.dense.floors(b,source);glyph=op.seats.dense.polygon(text,text.GetLayer())
    a,z=nearest_points(court,glyph.envelope.buffer(floor['clearance']+.075+.002,join_style=2))
    leader.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
    leader.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])))
    if brackets:
        group=next(iter(b.Groups()));chain=fp.GetCourtyard(fp.GetLayer()).COutline(0)
        vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
        for line in lines:
            if line==leader:continue
            group.RemoveItem(line);b.Remove(line)
        for a,z in op.ownership._rectangular_corner_arms(vertices,150000):
            line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(text.GetLayer())
            line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(150000);line.SetLocked(True)
            b.Add(line);group.AddItem(line)
    op.field._save_field_snapshot(b,source)
    return source,proof['owner_uuid'],proof['group_uuid']


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('brackets',[False,True])
def test_exact_source_caption_seating_and_material_relation(tmp_path,back,turn,brackets):
    source,owner,group=fixture(tmp_path,back,turn,brackets);before=source.read_bytes()
    q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,q)
    r=op.receive(source,child,q);assert r['ok']and r['same_material'],r
    assert q['tested_positions']<=120 and q['angle_degrees']in(0,90)
    assert not r['current_authority']and not r['full_kelvin_qualification']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['group','font','face','text','lock','body','copper','extra_ink','opaque','one_nm'])
def test_no_other_candidate_delta_authorized(tmp_path,fault):
    source,owner,group=fixture(tmp_path);q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,q)
    if fault=='opaque':
        text=child.read_text();child.write_text(text[:-2]+'(opaque_material 1)\n)')
    else:
        b=pcbnew.LoadBoard(str(child));fp,t,leader,court,lines=op._nodes(b,q['ownership'])
        if fault=='group':next(iter(b.Groups())).SetName('forged')
        elif fault=='font':t.SetTextThickness(t.GetTextThickness()+1)
        elif fault=='face':t.SetLayer(pcbnew.F_Fab)
        elif fault=='text':t.SetText('forged')
        elif fault=='lock':t.SetLocked(False)
        elif fault=='body':fp.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='one_nm':leader.SetEnd(leader.GetEnd()+pcbnew.VECTOR2I(1,0))
        elif fault=='copper':
            x=pcbnew.PCB_TRACK(b);x.SetStart(pcbnew.VECTOR2I_MM(1,1));x.SetEnd(pcbnew.VECTOR2I_MM(2,1));x.SetWidth(200000);b.Add(x)
        elif fault=='extra_ink':
            x=pcbnew.PCB_TEXT(b);x.SetText('extra');x.SetLayer(t.GetLayer());b.Add(x)
        op.field._save_field_snapshot(b,child)
    assert not op.receive(source,child,q)['ok']


def test_forged_plan_is_not_scope(tmp_path):
    source,owner,group=fixture(tmp_path);q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    q['at_nm'][0]+=1
    child=op.force._copy_family(source,tmp_path/'child')
    with pytest.raises(ValueError,match='stale_or_forged'):op.write_private(source,child,q)


def test_native_opaque_change_refused_independently(tmp_path,monkeypatch):
    source,owner,group=fixture(tmp_path);q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,q)
    original_save=op.field._save_field_snapshot
    def corrupt(board,path):
        original_save(board,path)
        if Path(path).name=='0.kicad_pcb':
            text=Path(path).read_text();Path(path).write_text(text[:-2]+'(future_native_material 1)\n)')
    monkeypatch.setattr(op.field,'_save_field_snapshot',corrupt)
    r=op.receive(source,child,q)
    assert not r['ok']and r['error']=='root_reference_whole_native_roundtrip_changed',r


@pytest.mark.parametrize('phase',['reconstruction','literal_native'])
def test_explicit_finite_receiving_phases(tmp_path,monkeypatch,phase):
    source,owner,group=fixture(tmp_path);q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,q)
    clock=[100.];monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    if phase=='reconstruction':
        original_construct=op._construct
        def slow(*args):
            value=original_construct(*args);clock[0]+=10.;return value
        monkeypatch.setattr(op,'_construct',slow)
    else:
        original_save=op.field._save_field_snapshot
        def slow(board,path):
            original_save(board,path)
            if Path(path).name=='expected.kicad_pcb':clock[0]+=10.
        monkeypatch.setattr(op.field,'_save_field_snapshot',slow)
    r=op.receive(source,child,q)
    assert not r['ok']and 'deadline'in r['error'],r
    assert r['bounded_composition']['aggregate_limit_s']==20


@pytest.mark.parametrize('timeout',[True,0,-1,11,float('nan')])
def test_finite_timeout(tmp_path,timeout):
    source,owner,group=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group,timeout_s=timeout)


@pytest.mark.parametrize('back',[False,True])
def test_actual_opposite_owner_reserves_map_space_without_adding_or_hiding_art(tmp_path,back):
    source,owner,group=fixture(tmp_path,back)
    q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    board=pcbnew.LoadBoard(str(source));old_fp,_,_,_,_=op._nodes(board,q['ownership'])
    other=pcbnew.FOOTPRINT(board);other.SetReference('OPAQUE_42');other.SetValue('unchanged')
    other.SetLayer(old_fp.GetLayer());other.SetPosition(pcbnew.VECTOR2I(*q['at_nm']));board.Add(other)
    other.Reference().SetVisible(True)
    other.Reference().SetLayer(pcbnew.B_SilkS if old_fp.IsFlipped()else pcbnew.F_SilkS)
    rect=pcbnew.PCB_SHAPE(other);rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetLayer(pcbnew.B_CrtYd if old_fp.IsFlipped()else pcbnew.F_CrtYd)
    rect.SetStart(other.GetPosition()-pcbnew.VECTOR2I(100000,100000))
    rect.SetEnd(other.GetPosition()+pcbnew.VECTOR2I(100000,100000));rect.SetWidth(50000);other.Add(rect)
    op.field._save_field_snapshot(board,source);uid=op.force._uid(other);before=source.read_bytes()
    unconstrained=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    reserved=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group,
        opposite_owner_uuid_reservations=[uid])
    assert reserved['at_nm']!=unconstrained['at_nm']
    assert reserved['reservations_constrain_search_only']is True
    child=op.force._copy_family(source,tmp_path/'reserved')
    op.write_private(source,child,reserved);received=op.receive(source,child,reserved)
    assert received['ok']and received['same_material'],received
    assert source.read_bytes()==before
    actual=pcbnew.LoadBoard(str(child));peer=next(f for f in actual.GetFootprints()if op.force._uid(f)==uid)
    assert peer.Reference().IsVisible()and peer.GetValue()=='unchanged'
    # A claimed reservation cannot become a broader arbitrary obstacle or
    # omit its fresh Source geometry in the saved reconstruction.
    forged=copy.deepcopy(reserved);forged['source_opposite_courtyard_reservations'][0]['courtyard_xy_mm'][0][0]+=.001
    assert not op.receive(source,child,forged)['ok']


@pytest.mark.parametrize('owners',[['missing'],['same','same'],[True],None])
def test_forged_reference_reservation_is_not_geometry_authority(tmp_path,owners):
    source,owner,group=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group,
        opposite_owner_uuid_reservations=owners)


@pytest.mark.parametrize('samples',[[True],[-.5],[.24],[3.01],[float('nan')],[1,1],[1]*7,None])
def test_extra_gap_samples_are_finite_existing_local_domain_only(tmp_path,samples):
    source,owner,group=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group,
        seat_gap_samples_mm=samples)


def test_explicit_intermediate_gaps_replay_without_relabeling_the_legacy_recipe(tmp_path):
    source,owner,group=fixture(tmp_path);old=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group)
    assert 'seat_gap_samples_mm'not in old
    q=op.plan(source,board_hint='renamed',owner_uuid=owner,group_uuid=group,seat_gap_samples_mm=[.75,1.5,2.])
    assert q['tested_positions']<=240 and q['seat_gap_samples_mm']==[.75,1.5,2.]
    child=op.force._copy_family(source,tmp_path/'gaps');op.write_private(source,child,q)
    assert op.receive(source,child,q)['ok']
