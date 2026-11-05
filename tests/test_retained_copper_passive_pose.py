"""Grounded passive moves retain supply copper and exact saved ownership."""
import json
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_capacitor_return_repack as caps
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pose_additive_reconstruction as receiving
import cec_smd_macro_transport as transport
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track
from test_smd_macro_transport import inventory


def fixture(tmp_path, *, back=False, quarter=0, foreign=False, delta=None):
    source, board=ground_fixture(tmp_path)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_PASSIVE_73');fp.SetValue('47k')
    fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0603_1608Metric'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(16,14));board.Add(fp)
    for pin,net,x in [('1','/CONTROL',15.2),('2','GND',16.8)]:
        pad=pcbnew.PAD(fp);pad.SetPadName(pin);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,14));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNetCode(board.GetNetcodeFromNetname(net));fp.Add(pad)
    vias=[]
    for net,x in [('GND',16.8),('/CONTROL',14.6)]:
        v=pcbnew.PCB_VIA(board);v.SetNetCode(board.GetNetcodeFromNetname(net))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetPosition(pcbnew.VECTOR2I_MM(x,14));v.SetWidth(350000);v.SetDrill(250000);board.Add(v);vias.append(v)
    lead=track(board,'/CONTROL',(14.6,14),(15.2,14))
    origin=pcbnew.VECTOR2I(fp.GetPosition());angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    fp.Rotate(origin,angle)
    for t in [*vias,lead]:t.Rotate(origin,angle)
    if back:
        fp.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT);lead.SetLayer(pcbnew.B_Cu)
        # Reflect the private copper with its Source owner as well.
        for t in [*vias,lead]:
            points=[t.GetPosition()] if t.GetClass()=='PCB_VIA' else [t.GetStart(),t.GetEnd()]
            points=[pcbnew.VECTOR2I(2*origin.x-p.x,p.y) for p in points]
            if t.GetClass()=='PCB_VIA':t.SetPosition(points[0])
            else:t.SetStart(points[0]);t.SetEnd(points[1])
    if foreign:
        at=vias[0].GetPosition()
        track(board,'/CONTROL',((at.x-700000)/1e6,(at.y+570000)/1e6),
            ((at.x+700000)/1e6,(at.y+570000)/1e6),pcbnew.In3_Cu,.2)
    assert fr.group_local_pofv_signal_vias(board,vias)
    field._save_field_snapshot(board,source)
    additive.bind_local_via_rule(board,source)
    target=force._copy_family(source,tmp_path/'trial')
    original,child=[pcbnew.LoadBoard(str(p)) for p in (source,target)]
    moved=child.FindFootprintByReference('RENAMED_PASSIVE_73')
    if delta is None:
        dx,dy=((0,.12),(.12,0),(0,-.12),(-.12,0))[quarter]
        delta=(-dx if back else dx,dy)
    moved.Move(pcbnew.VECTOR2I_MM(*delta))
    carried=transport.apply(original,child,source_path=source,board_hint='synthetic',
        maximum_shift_mm=1.,retain_source_tracks=True,carry_ground_barrels_only=True,
        allow_cardinal_rotations=True)
    additive._ground_refill(child);field._save_field_snapshot(child,target)
    return source,target,force._uid(moved),carried


def receive(source,target,uid,**kwargs):
    return receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='synthetic',
        max_shift_mm=1.,allow_source_ground_barrel_motion=True,**kwargs)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_real_same_owner_barrels_and_all_source_tracks_are_independently_replayed(tmp_path,back,quarter):
    source,target,uid,carried=fixture(tmp_path,back=back,quarter=quarter)
    before=source.read_bytes();sidecars=force._sidecars(source)
    proof=receive(source,target,uid)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_source_tracks_and_arcs_retained_exactly']
    assert proof['all_original_terminal_and_copper_partitions_preserved']
    assert proof['no_source_power_or_signal_barrel_motion_authorized']
    assert len(carried['changes'])==1 and carried['changes'][0]['net']=='GND'
    assert len(carried['stationary_non_ground_barrels'])==1
    assert carried['stationary_non_ground_barrels'][0]['same_source_native_owner_reproved']
    assert source.read_bytes()==before and force._sidecars(source)==sidecars
    assert not proof['routing_admitted'] and not proof['release_authority']
    original,child=[pcbnew.LoadBoard(str(p)) for p in (source,target)]
    first,last=inventory(original),inventory(child)
    for t in original.GetTracks():
        if t.GetClass()!='PCB_VIA' or t.GetNetname()!='GND':assert first[force._uid(t)]==last[force._uid(t)]


@pytest.mark.parametrize('fault',['trace','positive_via','ground_size','pad','peer','group','addition','sidecar'])
def test_exact_reconstruction_refuses_unowned_saved_changes(tmp_path,fault):
    source,target,uid,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(target))
    if fault=='trace':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(210000)
    elif fault=='positive_via':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()!='GND').Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='ground_size':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND').SetDrill(200000)
    elif fault=='pad':next(iter(b.FindFootprintByReference('RENAMED_PASSIVE_73').Pads())).SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    elif fault=='peer':
        props=b.GetProperties();props['SOURCE_METADATA']='unowned';b.SetProperties(props)
    elif fault=='group':next(iter(b.Groups())).SetName('forged-process-authority')
    elif fault=='addition':track(b,'/CONTROL',(22,14),(22.2,14))
    if fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'changed':True}))
    else:field._save_field_snapshot(b,target)
    proof=receive(source,target,uid)
    assert not proof['ok'] and proof['errors'],proof


def test_actual_inner_foreign_copper_is_not_an_automatic_antipad_permission(tmp_path):
    source,target,uid,_=fixture(tmp_path,foreign=True)
    proof=receive(source,target,uid)
    assert not proof['ok'] and 'foreign_copper_collision' in proof['errors'][0],proof


@pytest.mark.parametrize('fault',['not_passive','dnp','tht','no_ground','locked'])
def test_ground_label_alone_cannot_authorize_arbitrary_package_motion(tmp_path,fault):
    source,target,uid,_=fixture(tmp_path)
    for path in (source,target):
        b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('RENAMED_PASSIVE_73')
        if fault=='not_passive':fp.SetFPID(pcbnew.LIB_ID('Package_SO','SOT-23'))
        elif fault=='dnp':fp.SetAttributes(pcbnew.FP_DNP)
        elif fault=='tht':
            pad=next(iter(fp.Pads()));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.PAD.PTHMask())
        elif fault=='locked':fp.SetLocked(True)
        else:
            net=pcbnew.NETINFO_ITEM(b,'/RENAMED_RETURN');b.Add(net)
            next(p for p in fp.Pads() if p.GetNetname()=='GND').SetNet(net)
            next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND').SetNet(net)
        additive._ground_refill(b)
        field._save_field_snapshot(b,path)
    proof=receive(source,target,uid)
    assert not proof['ok'] and proof['errors'],proof


def test_source_selected_capacitor_assignment_cannot_be_lost(tmp_path,monkeypatch):
    source,target,uid,_=fixture(tmp_path)
    before=force._hash(source);calls=[]
    def assignments(board,hint):
        calls.append(1);return {'actual_source_assignment':len(calls)==1}
    monkeypatch.setattr(caps,'_assignments',assignments)
    proof=receive(source,target,uid)
    assert not proof['ok'] and 'assignments_changed' in proof['errors'][0],proof
    assert before==force._hash(source)


def test_fixed_supply_axis_cannot_be_laundered_into_partial_pad_overlap(tmp_path):
    with pytest.raises(ValueError,match='stationary_source_barrel_destination_POFV_refused'):
        fixture(tmp_path,quarter=1,delta=(0,.12))


@pytest.mark.parametrize('kw',[{'carry_ground_barrels_only':1},
    {'carry_ground_barrels_only':True},{'retain_source_tracks':1},
    {'carry_ground_barrels_only':True,'retain_source_tracks':True,'ordinary_via_poses':[{}]}])
def test_constructor_ground_only_mode_is_explicit_and_bounded(tmp_path,kw):
    source,target,_,_=fixture(tmp_path)
    a,b=[pcbnew.LoadBoard(str(p)) for p in (source,target)];before=inventory(b)
    with pytest.raises(ValueError):transport.apply(a,b,**kw)
    assert before==inventory(b)
