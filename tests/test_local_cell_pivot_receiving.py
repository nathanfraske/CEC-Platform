"""Exact source ownership and partitions for fixed-supply private-return pivots."""
import math

import pcbnew
import pytest

import cec_field_coupling as field
import cec_local_cell_pivot_receiving as receiver
import cec_native_placement_context as motion
from test_assigned_ground_access import fixture as ground_fixture


def fixture(tmp_path, *, layer=pcbnew.F_Cu, names=('DEVICE_GENERIC', 'C_ANY_LOCAL'),foreign=None):
    _, board, owner, cap, _, via = ground_fixture(tmp_path, layer=layer, names=names)
    owner.FindPadByNumber('7').SetPosition(pcbnew.VECTOR2I_MM(12.25,18.7))
    positions = {p.GetNumber():p.GetPosition() for p in cap.Pads()}
    cap.SetPosition(pcbnew.VECTOR2I_MM(15,18.7))
    for pad in cap.Pads(): pad.SetPosition(positions[pad.GetNumber()])
    # Keep BOTH rigid poses physically clear of the stationary supply lead.
    # A straight .6 mm barrel only .5 mm from that lead is not a valid
    # positive clearance control, despite preserving native connectivity.
    old_via=via.GetPosition();via.SetPosition(pcbnew.VECTOR2I_MM(16,19.5))
    for track in board.GetTracks():
        if track.GetClass()!='PCB_TRACK' or track.GetNetname()!='GND':continue
        if track.GetStart()==old_via:track.SetStart(via.GetPosition())
        if track.GetEnd()==old_via:track.SetEnd(via.GetPosition())
    if foreign in ('same_net_hole','foreign_hole'):
        extra=pcbnew.PCB_VIA(board);extra.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        extra.SetNet(board.FindNet('GND' if foreign=='same_net_hole' else '/RENAMED_DEVICE_RAIL'))
        extra.SetWidth(500000);extra.SetDrill(300000);extra.SetPosition(pcbnew.VECTOR2I_MM(13.5,17.4));board.Add(extra)
    # The projected serializer and constructor use the same complete native
    # footprint, while independently inferred source ownership grants scope.
    source = tmp_path/'source-bound.kicad_pcb'
    field._save_field_snapshot(board,source)
    pivot = cap.FindPadByNumber('1')
    motion.rotate_isolated_local_cells(board,{cap.GetReference():180},
          pivot_pad_uuids={cap.GetReference():pivot.m_Uuid.AsString()})
    candidate = tmp_path/'candidate.kicad_pcb'
    if foreign=='foreign_hole':
        # Deliberately shorted hostile input only; real producers correctly
        # refuse its saved identity, and the receiver must refuse it too.
        pcbnew.SaveBoard(str(candidate),board)
    else:field._save_field_snapshot(board,candidate)
    return source,candidate,board,owner,cap,via


@pytest.mark.parametrize('layer,names',[
    (pcbnew.F_Cu,('DEVICE_GENERIC','C_ANY_LOCAL')),
    (pcbnew.B_Cu,('UNRELATED_DEVICE','C_RENAMED_CERAMIC'))])
def test_source_assigned_return_portal_pivot_receives_exact_saved_native_motion(tmp_path,layer,names):
    source,candidate,*_=fixture(tmp_path,layer=layer,names=names)
    original=source.read_bytes();saved=candidate.read_bytes()
    result=receiver.receive(source,candidate,board_hint='unrelated-board')
    assert result['ok'] and result['complete'],result
    proof=result['source_selected_bypass_metrics'][0]
    assert proof['owner']==names[0] and proof['ref']==names[1]
    assert proof['before']['ground_pin_span_mm']==3.
    assert proof['after']['ground_pin_span_mm']==2.
    assert proof['before']['supply_path_mm']==proof['after']['supply_path_mm']
    assert proof['before']['ground_return_mm']==proof['after']['ground_return_mm']
    assert result['all_original_native_components_preserved']
    assert not result['release_authority'] and not result['current_qualification']
    assert not result['placement_qualification'] and not result['inherited_debt_qualified']
    assert source.read_bytes()==original and candidate.read_bytes()==saved


@pytest.mark.parametrize('fault',['via_width','via_drill','remote_track_width',
                                'extra_item','cap_value','pad_size','power_anchor',
                                'missing_barrel','changed_net','selected_field'])
def test_unowned_material_or_role_changes_cannot_hide_inside_a_pivot(tmp_path,fault):
    source,candidate,board,_,cap,via=fixture(tmp_path)
    if fault=='via_width':via.SetWidth(800000)
    elif fault=='via_drill':via.SetDrill(250000)
    elif fault=='remote_track_width':
        next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
             and t.GetNetname()=='/RENAMED_DEVICE_RAIL').SetWidth(350000)
    elif fault=='extra_item':
        extra=pcbnew.PCB_TRACK(board);extra.SetLayer(pcbnew.F_Cu)
        extra.SetStart(pcbnew.VECTOR2I_MM(8,8));extra.SetEnd(pcbnew.VECTOR2I_MM(9,8))
        extra.SetWidth(200000);extra.SetNet(board.FindNet('GND'));board.Add(extra)
    elif fault=='cap_value':cap.SetValue('220nF')
    elif fault=='pad_size':cap.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.4,.5))
    elif fault=='power_anchor':cap.FindPadByNumber('1').Move(pcbnew.VECTOR2I(10000,0))
    elif fault=='missing_barrel':
        from cec_native_items import discard_items
        discard_items(board,[via])
    elif fault=='changed_net':cap.FindPadByNumber('2').SetNet(board.FindNet('/RENAMED_DEVICE_RAIL'))
    else:cap.SetField('UnownedAuthority','changed')
    if fault == 'changed_net':
        # The guarded producer correctly rejects this deliberately malformed
        # connected net edit. Plain serialization creates only the hostile
        # synthetic test input; it is never used for real candidate output.
        pcbnew.SaveBoard(str(candidate), board)
    else:
        field._save_field_snapshot(board,candidate)
    original=source.read_bytes()
    result=receiver.receive(source,candidate,board_hint='unrelated-board')
    assert not result['ok'] and result['errors']
    assert not result['release_authority'] and not result['inherited_debt_qualified']
    assert source.read_bytes()==original


@pytest.mark.parametrize('arguments',[{'timeout_s':0},{'timeout_s':True},{'timeout_s':math.nan},
    {'timeout_s':11},{'max_caps':0},{'max_caps':True},{'max_caps':5},
    {'max_shift_mm':7},{'return_reach_mm':2},{'board_hint':''}])
def test_unbounded_or_unidentified_pivot_receiving_never_grants_authority(tmp_path,arguments):
    source,candidate,*_=fixture(tmp_path)
    options=dict(board_hint='unrelated-board',**{k:v for k,v in arguments.items() if k!='board_hint'})
    if 'board_hint' in arguments:options['board_hint']=arguments['board_hint']
    result=receiver.receive(source,candidate,**options)
    assert not result['ok'] and result['errors'] and not result['release_authority']


def test_unchanged_source_is_not_presented_as_loop_geometry_progress(tmp_path):
    source,_,*_=fixture(tmp_path)
    result=receiver.receive(source,source,board_hint='unrelated-board')
    assert not result['ok'] and 'scope' in str(result['errors'])


@pytest.mark.parametrize('foreign',['inner_track','same_net_hole','foreign_hole'])
def test_pivoted_existing_barrel_checks_all_copper_layers_and_every_hole(tmp_path,foreign):
    source,candidate,board,*_=fixture(tmp_path,foreign=None if foreign=='inner_track' else foreign)
    if foreign=='inner_track':
        # Append the same native-shaped foreign segment to both saved inputs.
        # A normal producer correctly refuses to serialize this hostile short;
        # do not let normalization change its net and accidentally test GND.
        import copy,uuid
        import cec_additive_route_receiving as additive
        _,nodes=additive._nodes(source)
        template=copy.deepcopy(nodes[next(track.m_Uuid.AsString() for track in board.GetTracks()
            if track.GetClass()=='PCB_TRACK' and track.GetNetname()=='/RENAMED_DEVICE_RAIL')])
        changes={'start':['start','12.5','17.35'],'end':['end','14.5','17.35'],
            'layer':['layer','"In1.Cu"'],'uuid':['uuid','"'+str(uuid.uuid4())+'"']}
        template=[changes.get(row[0],row) if isinstance(row,list) and row else row for row in template]
        for path in (source,candidate):
            root,_=additive._nodes(path);root.append(copy.deepcopy(template));path.write_text(additive._render(root))
    result=receiver.receive(source,candidate,board_hint='unrelated-board')
    assert not result['ok'] and 'foreign_hole_or_edge_refused' in str(result['errors']),result
    assert not result['release_authority'] and not result['inherited_debt_qualified']


def field_fixture(tmp_path):
    source,candidate,_,_,cap,_=fixture(tmp_path)
    ref=cap.GetReference()
    parent=pcbnew.LoadBoard(str(source));selected=parent.FindFootprintByReference(ref)
    for index,text in enumerate((selected.Reference(),selected.Value())):
        text.SetLayer(pcbnew.F_SilkS);text.SetVisible(True)
        text.SetTextSize(pcbnew.VECTOR2I_MM(.4,.4));text.SetTextThickness(100000)
        text.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
        text.SetPosition(selected.GetPosition()+pcbnew.VECTOR2I_MM(0,3+index))
    field._save_field_snapshot(parent,source)
    pivot=selected.FindPadByNumber('1')
    motion.rotate_isolated_local_cells(parent,{ref:180},
        pivot_pad_uuids={ref:pivot.m_Uuid.AsString()})
    for index,text in enumerate((selected.Reference(),selected.Value())):
        text.SetPosition(selected.GetPosition()+pcbnew.VECTOR2I_MM(2,1+index))
        text.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    field._save_field_snapshot(parent,candidate)
    return source,candidate,ref


def test_pivot_text_pose_replay_is_explicit_and_preserves_source_ink(tmp_path):
    source,candidate,_=field_fixture(tmp_path)
    assert not receiver.receive(source,candidate,board_hint='generic')['ok']
    proof=receiver.receive(source,candidate,board_hint='generic',allow_field_reflow=True)
    assert proof['ok'],proof
    assert proof['source_owned_affected_field_replay']
    assert not proof['release_authority'] and not proof['inherited_debt_qualified']


@pytest.mark.parametrize('fault',['size','visibility','string','layer','thickness','mirror',
                                'far','noncardinal','property','wrong_flag'])
def test_pivot_text_scope_cannot_erase_shrink_relabel_or_modify_authored_fields(tmp_path,fault):
    source,candidate,ref=field_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(candidate));cap=board.FindFootprintByReference(ref);text=cap.Reference()
    if fault=='size':text.SetTextSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='visibility':text.SetVisible(False)
    elif fault=='string':text.SetText('ANOTHER_COMPONENT')
    elif fault=='layer':text.SetLayer(pcbnew.F_Fab)
    elif fault=='thickness':text.SetTextThickness(50000)
    elif fault=='mirror':text.SetMirrored(True)
    elif fault=='far':text.SetPosition(cap.GetPosition()+pcbnew.VECTOR2I_MM(0,5.001))
    elif fault=='noncardinal':text.SetTextAngle(pcbnew.EDA_ANGLE(15,pcbnew.DEGREES_T))
    elif fault=='property':cap.SetValue('220nF')
    field._save_field_snapshot(board,candidate)
    proof=receiver.receive(source,candidate,board_hint='generic',allow_field_reflow=1 if fault=='wrong_flag' else True)
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']


def test_unrelated_owner_text_is_not_permitted_by_the_pivot_scope(tmp_path):
    source,candidate,_=field_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(candidate))
    owner=board.FindFootprintByReference('DEVICE_GENERIC')
    owner.Reference().Move(pcbnew.VECTOR2I_MM(1,0))
    field._save_field_snapshot(board,candidate)
    proof=receiver.receive(source,candidate,board_hint='generic',allow_field_reflow=True)
    assert not proof['ok'] and 'field_only_owner_not_impacted' in str(proof['errors'])


def test_native_field_diagnostics_distinguish_stationary_from_new_contact(tmp_path):
    source,candidate,board,owner,cap,_=fixture(tmp_path)
    prior=pcbnew.LoadBoard(str(source));old_cap=prior.FindFootprintByReference(cap.GetReference())
    old_owner=prior.FindFootprintByReference(owner.GetReference())
    for selected in (cap,old_cap):
        selected.Reference().SetVisible(False);selected.Value().SetVisible(False)
        for pad in selected.Pads():
            layers=pad.GetLayerSet();layers.AddLayer(pcbnew.F_Mask);pad.SetLayerSet(layers)
    for selected in (owner,old_owner):
        selected.Value().SetVisible(False)
        text=selected.Reference();text.SetLayer(pcbnew.F_SilkS);text.SetVisible(True)
        text.SetTextSize(pcbnew.VECTOR2I_MM(.1,.1));text.SetTextThickness(30000)
        text.SetText('MARK');text.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
        text.SetPosition(cap.FindPadByNumber('2').GetPosition())
    before=receiver.field_contact_keys(old_owner,[old_cap],prior)
    after=receiver.field_contact_keys(owner,[cap],board)
    assert after-before
    assert any(key[1]==cap.FindPadByNumber('2').m_Uuid.AsString() and key[2]=='pad' for key in after-before)
    # A same-UID stationary power contact is existing debt, not a new impact.
    for selected in (owner,old_owner):selected.Reference().SetPosition(cap.FindPadByNumber('1').GetPosition())
    assert receiver.field_contact_keys(old_owner,[old_cap],prior)==receiver.field_contact_keys(owner,[cap],board)


def test_native_field_diagnostics_do_not_include_self_hidden_or_other_side_ink(tmp_path):
    _,_,board,_,cap,_=fixture(tmp_path)
    for pad in cap.Pads():
        layers=pad.GetLayerSet();layers.AddLayer(pcbnew.F_Mask);pad.SetLayerSet(layers)
    text=cap.Reference();cap.Value().SetVisible(False)
    text.SetLayer(pcbnew.F_SilkS);text.SetVisible(True);text.SetText('SELF')
    text.SetTextSize(pcbnew.VECTOR2I_MM(.1,.1));text.SetTextThickness(30000)
    text.SetPosition(pcbnew.VECTOR2I_MM(5,5))
    assert not receiver.field_contact_keys(cap,[cap],board)
    text.SetPosition(cap.FindPadByNumber('2').GetPosition());text.SetVisible(False)
    assert not receiver.field_contact_keys(cap,[cap],board)
    text.SetVisible(True);text.SetLayer(pcbnew.B_SilkS)
    assert not receiver.field_contact_keys(cap,[cap],board)
