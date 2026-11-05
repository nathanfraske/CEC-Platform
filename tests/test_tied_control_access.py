"""Manufacturer/source-owned control leaves never become power authority."""
from pathlib import Path

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_tied_control_access as control
from test_lastmile import _board


def fixture(tmp_path,*,angle=0,back=False,extra=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    nets={}
    for name in ('GND','RAIL_OTHER','OUTPUT_OTHER'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    lib=Path(__file__).resolve().parents[1]/'lib/vendor/Package_SON.pretty'
    owners=[]
    for index,y in enumerate((10,20) if extra else (10,)):
        fp=pcbnew.FootprintLoad(str(lib),'WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm')
        assert fp is not None
        fp.SetReference('OWNER_RENAMED_'+str(index));fp.SetValue('TLV75533PDRVR')
        fp.SetFPID(pcbnew.LIB_ID('cec-Package_SON',fp.GetFPID().GetLibItemName()))
        fp.SetPosition(pcbnew.VECTOR2I_MM(10,y));b.Add(fp);owners.append(fp)
        for p in fp.Pads():
            p.SetNet(nets['RAIL_OTHER' if p.GetNumber() in ('4','6') else 'OUTPUT_OTHER' if p.GetNumber()=='1' else 'GND'])
        sink=pcbnew.FOOTPRINT(b);sink.SetReference('POWER_CONTACT_'+str(index));b.Add(sink)
        pad=pcbnew.PAD(sink);pad.SetNumber('1');pad.SetPosition(pcbnew.VECTOR2I_MM(14,y-.65))
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNet(nets['RAIL_OTHER']);sink.Add(pad)
        t=pcbnew.PCB_TRACK(b);t.SetNet(nets['RAIL_OTHER']);t.SetLayer(pcbnew.F_Cu);t.SetWidth(250000)
        t.SetStart(fp.FindPadByNumber('6').GetPosition());t.SetEnd(pad.GetPosition());b.Add(t)
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if back:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,owners[0].GetReference()


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_native_renamed_rotated_faces_receive_only_a_control_leaf(tmp_path,angle,back):
    source,ref=fixture(tmp_path,angle=angle,back=back);before=source.read_bytes()
    tasks=control.targets(pcbnew.LoadBoard(str(source)));assert len(tasks)==1
    assert tasks[0]['owner']==ref and tasks[0]['manufacturer']['current_max_a'] is None
    report=control.run(source,tmp_path/'trial',board_hint='synthetic',source_sha256=force._hash(source))
    assert report['ok'],report
    proof=report['receiving'];assert proof['ok'] and proof['complete']
    assert proof['opens']==proof['source_opens']-1 and not proof['new_native_faults']
    assert not proof['new_field_blockers'] and proof['all_original_poses_power_copper_and_partitions_preserved']
    assert not proof['branch_current_qualified'] and not proof['rail_current_qualified'] and not proof['release_authority']
    assert proof['manufacturer_maximum_current_unknown'] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['wrong_package','ambiguous_mpn','contradictory_display','wrong_enable_net',
    'no_input_conductor','duplicate_enable','wrong_pin_number'])
def test_task_is_not_inferred_from_a_supply_name_or_untrusted_part(tmp_path,fault):
    source,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference(ref)
    if fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('other','SOT-23-5'))
    elif fault=='ambiguous_mpn':fp.SetValue('TLV75533P')
    elif fault=='contradictory_display':fp.SetValue('TLV75533PDBVR')
    elif fault=='wrong_enable_net':fp.FindPadByNumber('4').SetNet(b.FindNet('GND'))
    elif fault=='no_input_conductor':
        for t in list(b.GetTracks()):b.Delete(t)
    elif fault=='duplicate_enable':
        p=pcbnew.PAD(fp);p.SetNumber('4');fp.Add(p)
    else:fp.FindPadByNumber('4').SetNumber('44')
    assert not control.targets(b)


def test_known_enable_never_uses_its_typical_current_as_a_maximum(tmp_path):
    source,ref=fixture(tmp_path);fp=pcbnew.LoadBoard(str(source)).FindFootprintByReference(ref)
    model=roles.tied_enable_contract(fp)
    assert model['current_max_a'] is None and model['typical_current_is_not_maximum_authority']
    assert model['enable_pin']=='4' and model['input_pin']=='6' and not model['branch_current_qualified']


def test_same_rail_controls_receive_one_bounded_leaf_per_transaction(tmp_path):
    source,_=fixture(tmp_path,extra=True)
    assert len(control.targets(pcbnew.LoadBoard(str(source))))==2
    report=control.run(source,tmp_path/'trial',board_hint='synthetic',source_sha256=force._hash(source))
    assert report['ok'],report
    assert len(report['receiving']['gained_controls'])==1
    assert len(control.targets(pcbnew.LoadBoard(report['board'])))==1


@pytest.mark.parametrize('fault',['spur','old_supply','pad_net','unqualified_via','wrong_group','extra_consumer'])
def test_saved_receiver_rejects_scope_leakage_even_with_a_closed_control(tmp_path,fault):
    source,ref=fixture(tmp_path)
    report=control.run(source,tmp_path/'seed',board_hint='synthetic',source_sha256=force._hash(source));assert report['ok'],report
    candidate=force._copy_family(report['board'],tmp_path/'bad');b=pcbnew.LoadBoard(str(candidate))
    fp=b.FindFootprintByReference(ref);task=control.targets(pcbnew.LoadBoard(str(source)))[0]
    added=set(report['receiving']['exact_additive_receiving']['added_native_uuids'])
    tracks=[t for t in b.GetTracks() if force._uid(t) in added]
    if fault=='old_supply':
        next(t for t in b.GetTracks() if force._uid(t) not in added).SetWidth(150000)
    elif fault=='pad_net':fp.FindPadByNumber('4').SetNet(b.FindNet('GND'))
    elif fault=='unqualified_via':
        via=pcbnew.PCB_VIA(b);via.SetPosition(fp.FindPadByNumber('4').GetPosition());via.SetWidth(250000);via.SetDrill(220000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNet(b.FindNet(task['net']));b.Add(via)
    elif fault=='wrong_group':
        g=pcbnew.PCB_GROUP(b);g.SetName('ARBITRARY_OWNER');g.AddItem(tracks[0]);b.Add(g)
    elif fault=='extra_consumer':
        # Move an originally unrelated same-net land onto the new corridor;
        # exact old primitive replay must refuse, regardless of open counts.
        pad=fp.FindPadByNumber('2');pad.SetNet(b.FindNet(task['net']))
    else:
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(task['net']));t.SetLayer(tracks[0].GetLayer())
        t.SetWidth(tracks[0].GetWidth());t.SetStart(tracks[0].GetStart())
        t.SetEnd(pcbnew.VECTOR2I(t.GetStart().x+500000,t.GetStart().y));b.Add(t)
    field._save_field_snapshot(b,candidate)
    proof=control.receive(source,candidate,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('budget',[0,True,float('nan'),11])
def test_control_deadlines_are_never_longer_than_ten_seconds(tmp_path,budget):
    source,_=fixture(tmp_path)
    with pytest.raises(ValueError):control.run(source,tmp_path/'trial',board_hint='synthetic',source_sha256=force._hash(source),timeout_s=budget)


def captured_fixture(tmp_path,*,angle=0,back=False,bridge=False,unrelated=False):
    source,ref=fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source));owner=parent.FindFootprintByReference(ref)
    contact=parent.FindFootprintByReference('POWER_CONTACT_0').FindPadByNumber('1')
    contact.SetPosition(pcbnew.VECTOR2I_MM(12,9.35))
    next(iter(parent.GetTracks())).SetEnd(contact.GetPosition())
    if unrelated:
        rogue=pcbnew.FOOTPRINT(parent);rogue.SetReference('UNRELATED_SAME_NET');parent.Add(rogue)
        pad=pcbnew.PAD(rogue);pad.SetNumber('1');pad.SetNet(contact.GetNet())
        pad.SetPosition(pcbnew.VECTOR2I_MM(12,10.65));pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());rogue.Add(pad)
    def transform(board):
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            if angle:item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
            if back:item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # Serialize SOURCE before adding any control copper. Capture discovery
    # must never be run on the candidate's already-joined same-net graph.
    field._save_field_snapshot(parent,source)
    child=pcbnew.LoadBoard(str(source))
    enable=child.FindFootprintByReference(ref).FindPadByNumber('4')
    start=enable.GetPosition();finish=child.FindFootprintByReference('POWER_CONTACT_0').FindPadByNumber('1').GetPosition()
    width=max(child.GetDesignSettings().m_TrackMinWidth,int(control.cells._netclass(child,enable.GetNetname())['width']))
    points=([start,pcbnew.VECTOR2I(finish.x,start.y)] if unrelated or bridge else
        [start,pcbnew.VECTOR2I(finish.x-300000,start.y),
         pcbnew.VECTOR2I(finish.x,start.y-300000),finish])
    def edge(a,b,layer):
        t=pcbnew.PCB_TRACK(child);t.SetStart(a);t.SetEnd(b);t.SetWidth(width)
        t.SetLayer(layer);t.SetNetCode(enable.GetNetCode());t.SetLocked(True);child.Add(t)
    for a,b in zip(points,points[1:]):edge(a,b,pcbnew.F_Cu)
    if bridge:
        edge(points[-1],finish,pcbnew.B_Cu)
        for at in (points[-1],finish):
            v=pcbnew.PCB_VIA(child);v.SetPosition(at);v.SetWidth(600000);v.SetDrill(300000)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetNetCode(enable.GetNetCode());v.SetLocked(True);child.Add(v)
    transform(parent);transform(child)
    field._save_field_snapshot(parent,source)
    candidate=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(child,candidate)
    return source,candidate


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
@pytest.mark.parametrize('bridge',[False,True])
def test_receiver_accepts_exact_source_input_capture_without_duplicate_pin_route(tmp_path,angle,back,bridge):
    source,candidate=captured_fixture(tmp_path,angle=angle,back=back,bridge=bridge)
    before=source.read_bytes()
    proof=control.receive(source,candidate,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    gain=proof['gained_controls'][0]
    assert gain['retained_input_capture']['native_uuids']!=[gain['task']['input_uuid']]
    assert gain['path_mm']<=4. and proof['opens']==proof['source_opens']-1
    assert not proof['branch_current_qualified'] and not proof['rail_current_qualified']
    assert source.read_bytes()==before and not proof['release_authority']


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_receiver_rejects_nearby_same_net_land_not_on_source_input_island(tmp_path,angle,back):
    source,candidate=captured_fixture(tmp_path,angle=angle,back=back,unrelated=True)
    proof=control.receive(source,candidate,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'],proof
