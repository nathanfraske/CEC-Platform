"""Native saved-source geometry tests, never a synthetic hardware rating."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_centered_terminal_landing as owner
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu,diameter=900000):
    b = _board([],edge=(0,0,60,60)); b.SetCopperLayerCount(6)
    props = b.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'; b.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(b,'/RENAMED_POWER_FIXTURE'); b.Add(net)
    def at(x,y):
        if mirror: x = -x
        for _ in range(quarter): x,y = -y,x
        return pcbnew.VECTOR2I(round((30+x)*1e6),round((30+y)*1e6))
    via = pcbnew.PCB_VIA(b); via.SetNet(net); via.SetPosition(at(0,0)); via.SetWidth(diameter)
    via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetLocked(True); b.Add(via)
    fp = pcbnew.FOOTPRINT(b); b.Add(fp); fp.SetReference('Y777')
    pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNet(net); pad.SetPosition(at(-3,0))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    layers = pcbnew.LSET(); layers.AddLayer(face); pad.SetLayerSet(layers)
    zone = pcbnew.ZONE(b); zone.SetNet(net); zone.SetLayer(face); zone.SetZoneName(owner.native.ZONE_NAME)
    zone.SetAssignedPriority(0); zone.SetMinThickness(100000); zone.SetLocalClearance(200000)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); zone.SetCornerSmoothingType(0); zone.SetLocked(True)
    zone.Outline().NewOutline()
    for x,y in [(-3.5,-.2),(0,-.2),(0,.2),(-3.5,.2)]:
        point = at(x,y); zone.Outline().Append(point.x,point.y)
    b.Add(zone); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir(); field._save_field_snapshot(b,source)
    monkeypatch.setattr(owner.authority,'_model',lambda *a: ('explicit_synthetic_geometry_only',{},dict(no_hardware_current_rating=True)))
    return source,dict(via_uuid=force._uid(via),layer_id=face,allow_locked_source=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('diameter',[900000,1400000])
def test_saved_centered_native_frame_reduces_actual_visible_curve_without_source_loss(tmp_path,monkeypatch,quarter,mirror,face,diameter):
    source,target = fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,diameter=diameter)
    before = source.read_bytes(); plan = owner.plan(source,board_hint='explicit_synthetic_frame',targets=[target])
    board = owner.construct(source,plan); child = force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(board,child); proof = owner.receive_literal(source,child,plan)
    if not proof['ok']: raise ValueError(';'.join(proof['errors']))
    assert proof['complete']
    row = plan['records'][0]; center = row['source_barrel']['position_nm']; pts = row['centered_cover_nm']
    assert all([2*center[k]-p[k] for k in (0,1)] in pts for p in pts)
    assert proof['every_original_filled_record_track_pad_barrel_field_and_ground_sheet_literal']
    assert proof['actual_saved_terminal_progress'][0]['candidate_curve_runs']['longest_mm'] <= .5*proof['actual_saved_terminal_progress'][0]['source_curve_runs']['longest_mm']
    assert source.read_bytes() == before and not proof['current_or_barrel_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['via_drill','pad_pose','new_track','source_fill','text','profile','current_model','source_hash'])
def test_unowned_native_mutants_or_rehashed_geometry_do_not_receive(tmp_path,monkeypatch,fault):
    source,target = fixture(tmp_path,monkeypatch); plan = owner.plan(source,board_hint='explicit_synthetic_frame',targets=[target])
    board = owner.construct(source,plan); child = force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(board,child)
    bad = copy.deepcopy(plan)
    if fault == 'via_drill': next(t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA').SetDrill(310000)
    elif fault == 'pad_pose': next(iter(next(iter(board.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'new_track':
        t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I_MM(25,25)); t.SetEnd(pcbnew.VECTOR2I_MM(26,25)); t.SetWidth(200000); board.Add(t)
    elif fault == 'source_fill': next(iter(board.Zones())).UnFill()
    elif fault == 'text': next(iter(board.GetFootprints())).SetReference('WRONG')
    elif fault == 'profile': bad['records'][0]['points_nm'][0][0] += 1
    elif fault == 'current_model': bad['records'][0]['source_current_contract'] = dict(invented_current=True)
    else: bad['source_sha256'] = '0'*64
    field._save_field_snapshot(board,child)
    proof = owner.receive_literal(source,child,bad)
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['unowned_lock','ground_face','unregistered_keeper','ground_net'])
def test_unsupported_source_authority_stays_unchanged(tmp_path,monkeypatch,fault):
    source,target = fixture(tmp_path,monkeypatch)
    if fault == 'unowned_lock': target['allow_locked_source'] = False
    elif fault == 'ground_face': target['layer_id'] = pcbnew.In1_Cu
    else:
        board = pcbnew.LoadBoard(str(source))
        if fault == 'unregistered_keeper': next(iter(board.Zones())).SetZoneName('NOT_OWNED')
        else: board.FindNet('/RENAMED_POWER_FIXTURE').SetNetname('GND')
        field._save_field_snapshot(board,source)
    before = source.read_bytes()
    with pytest.raises(ValueError): owner.plan(source,board_hint='explicit_synthetic_frame',targets=[target])
    assert source.read_bytes() == before


@pytest.mark.parametrize('offset',[2,3,50000,250000])
def test_curvature_observation_keeps_raw_long_noncanonical_fill_edges_explicit(offset):
    from shapely.geometry import Polygon
    shape = Polygon([(0,0),(1,1-offset/1e6),(1,0)])
    result = owner.curve_runs(shape)
    assert result['longest_mm'] == 0 and result['noncanonical_edges'] == 1
    assert result['raw_long_noncanonical_fill_edges_disclosed']
    assert result['track_centerline_angle_tolerance_nm'] == 0
    assert not result['geometry_snapped_or_edited_for_observation']
