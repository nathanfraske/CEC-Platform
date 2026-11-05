"""Exact Source maps can follow grounded passive turns, not waive contacts."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pose_additive_reconstruction as receiver
import cec_retained_passive_pose_stage as stage
from test_retained_passive_pose_stage import fixture
from test_smd_macro_transport import inventory


def request(tmp_path, *, back=False, quarter=0, turn=180, capacitor=False):
    source, owner, group, ref, _ = fixture(tmp_path,back=back,quarter=quarter,capacitor=capacitor)
    native = pcbnew.LoadBoard(str(source)); fp = native.FindFootprintByReference(ref)
    # Pose proposals come from the actual native land, not an assumed pin
    # numbering/axis/side convention. Source admission is rederived below.
    pad = next(p for p in fp.Pads() if p.GetNetname() != 'GND')
    anchor = tuple(pad.GetPosition()); fp.Rotate(pad.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    assert tuple(pad.GetPosition()) == anchor
    pose = [fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    q = stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group],
        allow_cardinal_reference_maps=True)
    return source,owner,group,ref,json.loads(json.dumps(q))


def build(tmp_path, **kwargs):
    source,owner,group,ref,q = request(tmp_path,**kwargs)
    before = source.read_bytes(); family = force._sidecars(source)
    made = stage.construct(source,tmp_path/'cardinal-received',q)
    assert made['ok'] and made['complete'],made
    assert source.read_bytes() == before and force._sidecars(source) == family
    return source,Path(made['candidate']),owner,group,ref,q,made


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('turn',[90,180,270])
@pytest.mark.parametrize('capacitor',[False,True])
def test_complete_saved_cardinal_map_and_Ground_only_pose(tmp_path,back,quarter,turn,capacitor):
    source,target,owner,group,ref,q,made=build(tmp_path,back=back,quarter=quarter,turn=turn,capacitor=capacitor)
    # construct() already calls the fresh public saved receiver. Inspect
    # that real result, rather than paying for an identical second replay.
    received=made['receiving']
    assert received['ok'] and received['complete'],received
    proof=received['independent_Source_pose_reconstruction']
    assert proof['source_closed_reference_maps_cardinal_with_own_passives']
    assert proof['all_source_reference_group_memberships_and_locks_preserved']
    assert proof['all_source_tracks_and_arcs_retained_exactly']
    assert proof['all_original_terminal_and_copper_partitions_preserved']
    assert not proof['source_closed_reference_maps_translated_with_own_passives']
    assert not proof['exact_source_plus_additions']['added_native_uuids']
    first,last=[pcbnew.LoadBoard(str(path)) for path in (source,target)]
    a,b=inventory(first),inventory(last)
    moved=[]
    for t in first.GetTracks():
        if a[force._uid(t)] != b[force._uid(t)]:
            assert t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND'
            moved.append(force._uid(t))
    assert len(moved)==1
    pads=[next(p for p in n.FindFootprintByReference(ref).Pads() if p.GetNetname()!='GND') for n in (first,last)]
    assert tuple(pads[0].GetPosition())==tuple(pads[1].GetPosition())
    assert not received['routing_admitted'] and not received['current_qualified'] and not received['release_authority']


@pytest.mark.parametrize('fault',['ink','label','member','unlock','track','signal_via','ground_drill',
    'ground_position','pad','unrelated_metadata','sidecar','new_copper'])
def test_annotation_opt_in_cannot_hide_other_saved_changes(tmp_path,fault):
    source,target,owner,group,ref,q,_=build(tmp_path)
    board=pcbnew.LoadBoard(str(target));g=next(g for g in board.Groups() if force._uid(g)==group)
    if fault=='ink':next(i for i in g.GetItems() if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='label':next(i for i in g.GetItems() if i.GetClass()=='PCB_TEXT').SetText('R86')
    elif fault=='member':g.RemoveItem(next(i for i in g.GetItems() if i.GetClass()=='PCB_SHAPE'))
    elif fault=='unlock':g.SetLocked(False)
    elif fault=='track':next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(210000)
    elif fault=='signal_via':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()!='GND').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ground_drill':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND').SetDrill(240000)
    elif fault=='ground_position':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad':next(iter(board.FindFootprintByReference(ref).Pads())).SetSize(pcbnew.VECTOR2I_MM(.81,.8))
    elif fault=='unrelated_metadata':
        props=board.GetProperties();props['FORGED']='not a pose';board.SetProperties(props)
    elif fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'forged':True}))
    else:
        from test_field_proposals import track
        track(board,'/CONTROL',(22,14),(22.2,14))
    if fault!='sidecar':field._save_field_snapshot(board,target)
    r=stage.receive(source,target,q)
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('value',[1,0,1.,0.,None,'true',[],{}])
def test_new_flag_is_literal_boolean(tmp_path,value):
    source,owner,group,ref,pose=fixture(tmp_path)
    with pytest.raises(ValueError,match='finite_explicit'):
        stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group],
            allow_cardinal_reference_maps=value)


@pytest.mark.parametrize('fault',['omitted','false','integer_true','unknown_pose','current_authority'])
def test_saved_cardinal_proposal_cannot_change_scope_or_mode(tmp_path,fault):
    source,target,owner,group,ref,q,_=build(tmp_path)
    bad=copy.deepcopy(q)
    if fault=='omitted':bad.pop('allow_cardinal_reference_maps')
    elif fault=='false':bad['allow_cardinal_reference_maps']=False
    elif fault=='integer_true':bad['allow_cardinal_reference_maps']=1
    elif fault=='unknown_pose':bad['poses'][ref][0]+=.000001
    else:bad['current_qualified']=True
    r=stage.receive(source,target,bad)
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('extra',[{'allow_source_ground_barrel_motion':False},
    {'reference_group_uuids':[]},{'allow_field_reflow':True},
    {'allow_retained_capacitor_supply_additions':True},{'source_ground_barrel_seats':[{}]},
    {'selected_pivot_pad_uuids':{'invented':'invented'}},
    {'allow_source_ordinary_resistor_reference_maps':True},
    {'allow_source_two_pin_diode_pivot':True}])
def test_cardinal_map_mode_cannot_expand_its_physical_tier(tmp_path,extra):
    source,target,owner,group,ref,q,_=build(tmp_path)
    kwargs=dict(selected_footprint_uuids=[owner],board_hint='synthetic',max_shift_mm=6.,
        allow_source_ground_barrel_motion=True,reference_group_uuids=[group],allow_cardinal_reference_maps=True)
    kwargs.update(extra)
    r=receiver.receive(source,target,**kwargs)
    assert not r['ok'] and r['errors'],r


def test_legacy_JSON_mode_remains_omitted_and_rotations_still_refuse(tmp_path):
    source,owner,group,ref,q=request(tmp_path)
    default=stage.plan(source,q['poses'],board_hint='synthetic',reference_group_uuids=[group])
    explicit=stage.plan(source,q['poses'],board_hint='synthetic',reference_group_uuids=[group],allow_cardinal_reference_maps=False)
    assert default==explicit and 'allow_cardinal_reference_maps' not in default
    with pytest.raises(ValueError,match='translation_only'):
        stage.construct(source,tmp_path/'legacy-refused',default)


@pytest.mark.parametrize('fault',['lost_signal_contact','inner_foreign_barrel_collision'])
def test_cardinal_annotations_never_replace_real_physical_contacts(tmp_path,fault):
    source,owner,group,ref,q=request(tmp_path)
    board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference(ref)
    signal_vias={force._uid(t)for t in board.GetTracks()
        if t.GetClass()=='PCB_VIA'and t.GetNetname()=='/CONTROL'}
    assert len(signal_vias)==1
    expected_owner_refusal=('stationary_source_barrel_destination_POFV_refused:'
        +next(iter(signal_vias))+':via has no bounded live SMD copper owner')
    if fault=='lost_signal_contact':
        pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,(fp.GetOrientationDegrees()+180)%360]
    else:
        # Fixed foreign inner-layer copper is legal in the parent. It must
        # remain an obstacle to the moved Ground barrel, not be auto-cut.
        from test_field_proposals import track
        scratch=pcbnew.LoadBoard(str(source));moved=scratch.FindFootprintByReference(ref)
        pose=q['poses'][ref]
        moved.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
        moved.SetOrientationDegrees(pose[2])
        at=next(p.GetPosition() for p in moved.Pads() if p.GetNetname()=='GND')
        fixed_foreign=track(board,'/CONTROL',((at.x-700000)/1e6,at.y/1e6),
            ((at.x+700000)/1e6,at.y/1e6),pcbnew.In3_Cu,.2)
        expected_native_refusal=('selected_native_fill_changed_authored_net_identity:track:'
            +force._uid(fixed_foreign)+':/CONTROL->GND')
        additive._ground_refill(board);field._save_field_snapshot(board,source)
    q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group],
        allow_cardinal_reference_maps=True)
    before=source.read_bytes()
    try:
        result=stage.construct(source,tmp_path/'physical-refusal',q)
    except ValueError as exc:
        text=str(exc)
        assert ('foreign_copper_collision' in text if fault=='inner_foreign_barrel_collision'
            else 'contact' in text or 'partition' in text or text==expected_owner_refusal),text
    except RuntimeError as exc:
        # KiCad's selected-fill protection may detect the actual foreign
        # short earlier than saved receiving. Accept only that exact native
        # authored-net refusal, never arbitrary setup/runtime failures.
        assert fault=='inner_foreign_barrel_collision'
        assert str(exc)==expected_native_refusal
    else:
        assert not result['ok'] and result['receiving']['errors'],result
        text=str(result['receiving']['errors'])
        assert ('foreign_copper_collision' in text if fault=='inner_foreign_barrel_collision'
            else 'contact' in text or 'partition' in text),text
    assert source.read_bytes()==before
