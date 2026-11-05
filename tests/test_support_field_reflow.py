"""Text poses are advisory; readable source-authored fields stay immutable."""
import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_support_field_reflow as reflow
import cec_support_pivot_receiving as receiving
from test_support_pivot_receiving import fixture


def sample(tmp_path):
    source,target,name=fixture(tmp_path,name='R5')
    for path in (source,target):
        board=pcbnew.LoadBoard(str(path));fp=board.FindFootprintByReference(name)
        for index,text in enumerate((fp.Reference(),fp.Value())):
            text.SetLayer(pcbnew.F_SilkS);text.SetVisible(True)
            text.SetTextSize(pcbnew.VECTOR2I_MM(.5,.5));text.SetTextThickness(100000)
            text.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
            text.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(0,3.+index))
        field._save_field_snapshot(board,path)
    return source,target,name


def test_positive_native_text_pose_replay_is_opt_in_and_additive(tmp_path):
    source,target,name=sample(tmp_path)
    saved=source.read_bytes()
    assert not receiving.receive(source,target,board_hint='synthetic')['ok']
    proof=receiving.receive(source,target,board_hint='synthetic',allow_support_field_reflow=True)
    assert proof['ok'],proof['errors']
    assert proof['support_field_reflow_requested'] and proof['opens']==0
    assert source.read_bytes()==saved and not proof['release_authority']


@pytest.mark.parametrize('fault',['size','visibility','string','layer','thickness',
    'mirror','far','non_cardinal','property','copper','wrong_flag'])
def test_bounded_text_pose_permission_cannot_hide_other_edits(tmp_path,fault):
    source,target,name=sample(tmp_path)
    board=pcbnew.LoadBoard(str(target));fp=board.FindFootprintByReference(name);text=fp.Reference()
    if fault=='size':text.SetTextSize(pcbnew.VECTOR2I_MM(.4,.4))
    elif fault=='visibility':text.SetVisible(False)
    elif fault=='string':text.SetText('R6')
    elif fault=='layer':text.SetLayer(pcbnew.F_Fab)
    elif fault=='thickness':text.SetTextThickness(80000)
    elif fault=='mirror':text.SetMirrored(True)
    elif fault=='far':text.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(0,reflow.MAX_OWNER_DISTANCE_MM+.001))
    elif fault=='non_cardinal':text.SetTextAngle(pcbnew.EDA_ANGLE(15,pcbnew.DEGREES_T))
    elif fault=='property':fp.SetValue('22k')
    elif fault=='copper':fp.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(.7,.4))
    field._save_field_snapshot(board,target)
    proof=receiving.receive(source,target,board_hint='synthetic',
        allow_support_field_reflow=1 if fault=='wrong_flag' else True)
    assert not proof['ok'] and proof['errors'],proof


def test_constructor_preserves_native_fields_and_never_grants_release(tmp_path):
    _,target,name=sample(tmp_path)
    board=pcbnew.LoadBoard(str(target));fp=board.FindFootprintByReference(name)
    originals={f.GetName():(f.GetText(),tuple(f.GetTextSize()),f.GetTextThickness(),
        f.IsVisible(),f.GetLayer(),f.IsMirrored()) for f in (fp.Reference(),fp.Value())}
    proof=reflow.construct(board,name)
    assert proof['ok'],proof
    assert not proof['release_authority']
    now={f.GetName():(f.GetText(),tuple(f.GetTextSize()),f.GetTextThickness(),
        f.IsVisible(),f.GetLayer(),f.IsMirrored()) for f in (fp.Reference(),fp.Value())}
    assert originals==now
    parent=pcbnew.LoadBoard(str(target));reflow.replay_poses(parent.FindFootprintByReference(name),fp)
    assert force._uid(parent.FindFootprintByReference(name))==force._uid(fp)


def test_multiland_owner_layout_is_explicit_bounded_and_preserves_native_ink(tmp_path):
    _,target,name=sample(tmp_path)
    board=pcbnew.LoadBoard(str(target));fp=board.FindFootprintByReference(name)
    extra=pcbnew.PAD(fp);extra.SetNumber('THIRD_NATIVE_PIN')
    extra.SetAttribute(pcbnew.PAD_ATTRIB_SMD);extra.SetShape(pcbnew.PAD_SHAPE_RECT)
    extra.SetLayerSet(fp.FindPadByNumber('1').GetLayerSet());extra.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    extra.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(0,1.5));fp.Add(extra)
    before={f.GetName():(f.GetText(),tuple(f.GetTextSize()),f.GetTextThickness(),
        f.IsVisible(),f.GetLayer(),f.IsMirrored()) for f in (fp.Reference(),fp.Value())}
    with pytest.raises(ValueError):reflow.construct(board,name)
    result=reflow.construct(board,name,allow_multiland_owner=True)
    assert result['ok'],result
    assert before=={f.GetName():(f.GetText(),tuple(f.GetTextSize()),f.GetTextThickness(),
        f.IsVisible(),f.GetLayer(),f.IsMirrored()) for f in (fp.Reference(),fp.Value())}


@pytest.mark.parametrize('options',[{'allow_multiland_owner':1},{'timeout_s':0},
    {'timeout_s':True},{'timeout_s':11}])
def test_owner_field_layout_bounds_refuse_before_any_text_motion(tmp_path,options):
    _,target,name=sample(tmp_path)
    board=pcbnew.LoadBoard(str(target));fp=board.FindFootprintByReference(name)
    before=[(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in (fp.Reference(),fp.Value())]
    with pytest.raises(ValueError):reflow.construct(board,name,**options)
    assert before==[(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in (fp.Reference(),fp.Value())]


def collision_sample(tmp_path, *, peer_count=1, angle=0, back=False):
    _, target, name = sample(tmp_path)
    board = pcbnew.LoadBoard(str(target))
    changed = board.FindFootprintByReference(name)
    land = next(iter(changed.Pads())).GetPosition()
    peers = []
    for index in range(peer_count):
        owner = pcbnew.FOOTPRINT(board)
        owner.SetReference('RENAMED_NEIGHBOR_' + str(index))
        owner.SetValue('100k')
        owner.SetPosition(pcbnew.VECTOR2I_MM(14 + index, 10))
        for number, offset in (('1', -.5), ('2', .5)):
            pad = pcbnew.PAD(owner)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6, .4))
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(owner.GetPosition() + pcbnew.VECTOR2I_MM(offset, 0))
            owner.Add(pad)
        board.Add(owner)
        for index_field, text in enumerate((owner.Reference(), owner.Value())):
            text.SetLayer(pcbnew.F_SilkS)
            text.SetVisible(True)
            text.SetTextSize(pcbnew.VECTOR2I_MM(.5, .5))
            text.SetTextThickness(100000)
            text.SetPosition(land + pcbnew.VECTOR2I_MM(0, index_field * .1))
        peers.append(owner)
    if back:
        for item in [*board.GetFootprints(), *board.GetTracks()]:
            item.Flip(pcbnew.VECTOR2I_MM(15, 15), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15, 15), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    return board, changed, peers


def text_identity(board):
    return {force._uid(f): (f.GetText(), tuple(f.GetTextSize()), f.GetTextThickness(),
        f.IsVisible(), f.GetLayer(), f.IsMirrored())
        for fp in board.GetFootprints() for f in (fp.Reference(), fp.Value())}


@pytest.mark.parametrize('angle,back', [(0, False), (90, False), (180, True), (270, True)])
def test_native_neighbor_collision_discovery_is_rotation_and_side_independent(tmp_path, angle, back):
    board, changed, peers = collision_sample(tmp_path, angle=angle, back=back)
    snapshot = tmp_path / 'cohort-before.kicad_pcb'
    field._save_field_snapshot(board, snapshot)
    source_bytes = snapshot.read_bytes()
    parent = pcbnew.LoadBoard(str(snapshot))
    before = text_identity(board)
    copper = {force._uid(p): force._item_key(p) for fp in board.GetFootprints() for p in fp.Pads()}
    poses = {force._uid(fp): (tuple(fp.GetPosition()), fp.GetOrientationDegrees()) for fp in board.GetFootprints()}
    result = reflow.construct_collision_cohort(board, [force._uid(changed)])
    assert result['ok'], result
    assert result['impacted_footprint_uuids'] == [force._uid(peers[0])]
    assert result['source_strings_fonts_visibility_and_layers_preserved']
    assert not result['component_and_copper_geometry_changed'] and not result['release_authority']
    assert text_identity(board) == before
    assert copper == {force._uid(p): force._item_key(p) for fp in board.GetFootprints() for p in fp.Pads()}
    assert poses == {force._uid(fp): (tuple(fp.GetPosition()), fp.GetOrientationDegrees()) for fp in board.GetFootprints()}
    reflow.replay_poses(parent.FindFootprintByReference(peers[0].GetReference()), peers[0])
    assert snapshot.read_bytes() == source_bytes


def test_neighbor_field_cohort_rolls_back_all_prior_layouts_on_failure(tmp_path, monkeypatch):
    board, changed, peers = collision_sample(tmp_path, peer_count=2)
    before = {force._uid(f): (tuple(f.GetPosition()), f.GetTextAngle().AsDegrees())
        for fp in board.GetFootprints() for f in (fp.Reference(), fp.Value())}
    calls = []
    def refused_second(board, ref, **kwargs):
        calls.append(ref)
        fp = board.FindFootprintByReference(ref)
        fp.Reference().Move(pcbnew.VECTOR2I_MM(1, 1))
        return dict(ok=len(calls) == 1)
    monkeypatch.setattr(reflow, '_construct', refused_second)
    result = reflow.construct_collision_cohort(board, [force._uid(changed)])
    assert not result['ok'] and len(calls) == 2
    assert before == {force._uid(f): (tuple(f.GetPosition()), f.GetTextAngle().AsDegrees())
        for fp in board.GetFootprints() for f in (fp.Reference(), fp.Value())}


def test_neighbor_collision_bound_refuses_before_text_motion(tmp_path):
    board, changed, _ = collision_sample(tmp_path, peer_count=2)
    before = {force._uid(f): tuple(f.GetPosition()) for fp in board.GetFootprints() for f in fp.GetFields()}
    result = reflow.construct_collision_cohort(board, [force._uid(changed)], max_owners=1)
    assert not result['ok'] and result['reason'] == 'native_neighbor_field_cohort_bound'
    assert before == {force._uid(f): tuple(f.GetPosition()) for fp in board.GetFootprints() for f in fp.GetFields()}


@pytest.mark.parametrize('scope,options', [([], {}), (['unknown'], {}),
    (['duplicate', 'duplicate'], {}), (['placeholder'], {'max_owners': True}),
    (['placeholder'], {'max_owners': 9}), (['placeholder'], {'timeout_s': 0}),
    (['placeholder'], {'timeout_s': True}), (['placeholder'], {'timeout_s': 11})])
def test_neighbor_cohort_invalid_scope_never_authorizes_changes(tmp_path, scope, options):
    board, _, _ = collision_sample(tmp_path)
    before = text_identity(board)
    with pytest.raises(ValueError):
        reflow.construct_collision_cohort(board, scope, **options)
    assert before == text_identity(board)


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,True),(270,True)])
def test_joint_native_cohort_places_largest_ink_before_changed_owner(tmp_path,monkeypatch,angle,back):
    board,changed,peers=collision_sample(tmp_path,angle=angle,back=back)
    before=text_identity(board)
    copper={force._uid(p):force._item_key(p) for fp in board.GetFootprints() for p in fp.Pads()}
    original=reflow._construct
    calls=[]
    def observed(board,ref,**kwargs):
        calls.append((ref,set(kwargs['pending_field_uuids'])))
        return original(board,ref,**kwargs)
    monkeypatch.setattr(reflow,'_construct',observed)
    result=reflow.construct_collision_cohort(board,[force._uid(changed)],include_changed_owners=True)
    assert result['ok'],result
    assert calls[0][0]==peers[0].GetReference()
    assert {force._uid(f) for f in (changed.Reference(),changed.Value())}<=calls[0][1]
    assert set(result['reflowed_footprint_uuids'])=={force._uid(changed),force._uid(peers[0])}
    assert text_identity(board)==before
    assert copper=={force._uid(p):force._item_key(p) for fp in board.GetFootprints() for p in fp.Pads()}
    assert not result['release_authority'] and result['include_changed_owners']


def test_joint_native_cohort_rolls_back_changed_and_neighbor_on_failure(tmp_path,monkeypatch):
    board,changed,_=collision_sample(tmp_path)
    before={force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in board.GetFootprints() for f in (fp.Reference(),fp.Value())}
    calls=[]
    def refused_second(board,ref,**kwargs):
        calls.append(ref)
        board.FindFootprintByReference(ref).Reference().Move(pcbnew.VECTOR2I_MM(1,1))
        return dict(ok=len(calls)==1)
    monkeypatch.setattr(reflow,'_construct',refused_second)
    result=reflow.construct_collision_cohort(board,[force._uid(changed)],include_changed_owners=True)
    assert not result['ok'] and len(calls)==2
    assert before=={force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in board.GetFootprints() for f in (fp.Reference(),fp.Value())}


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_joint_field_cohort_requires_explicit_boolean(tmp_path,flag):
    board,changed,_=collision_sample(tmp_path)
    before=text_identity(board)
    with pytest.raises(ValueError,match='bounded_native_neighbor_field_cohort_required'):
        reflow.construct_collision_cohort(board,[force._uid(changed)],include_changed_owners=flag)
    assert text_identity(board)==before


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_native_bbox_screen_matches_unscreened_glyph_and_mask_receiving(tmp_path,monkeypatch,angle,back):
    board,changed,_=collision_sample(tmp_path,angle=angle,back=back)
    source=tmp_path/'exact-source.kicad_pcb';field._save_field_snapshot(board,source)
    accelerated=reflow.construct_collision_cohort(board,[force._uid(changed)],include_changed_owners=True)
    assert accelerated['ok'],accelerated
    poses=lambda b:{force._uid(f):(tuple(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in b.GetFootprints() for f in (fp.Reference(),fp.Value())}
    saved_poses=poses(board)
    raw=pcbnew.LoadBoard(str(source))
    monkeypatch.setattr(reflow,'_native_boxes_near',lambda *args:True)
    unfiltered=reflow.construct_collision_cohort(raw,[force._uid(changed)],include_changed_owners=True)
    assert unfiltered['ok'],unfiltered
    assert poses(raw)==saved_poses and text_identity(raw)==text_identity(board)
