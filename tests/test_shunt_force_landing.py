"""Full-width source force geometry is replayable across renamed rotations."""
from unittest.mock import patch
import pcbnew
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_shunt_force_landing as seat
import cec_rectilinear_copper as contour
import cec_force_current as force
import cec_field_coupling as field
import cec_zone_fill


def fixture(tmp_path,angle=0,flush=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(2)
    nets={}
    for name in ('RENAMED_X','RENAMED_Y','UNRELATED'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    fps={}
    def land(ref,pin,net,at,size,value='',resistor=False):
        if ref not in fps:
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
            fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD' if resistor else 'Fixture','Native'))
            board.Add(fp);fps[ref]=fp
        pad=pcbnew.PAD(fps[ref]);pad.SetNumber(pin);pad.SetNet(nets[net])
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(pcbnew.VECTOR2I_MM(*at))
        pad.SetSize(pcbnew.VECTOR2I_MM(*size));fps[ref].Add(pad);return pad
    source_pad=land('RENAMED_SHUNT','1','RENAMED_X',(20,30),(3,1.5),resistor=True)
    land('RENAMED_SHUNT','2','RENAMED_Y',(20,24),(3,1.5),resistor=True)
    land('RENAMED_SENSOR','8','RENAMED_X',(16,27),(.3,1.4),'INA240A3')
    land('RENAMED_SENSOR','1','RENAMED_Y',(16,25),(.3,1.4),'INA240A3')
    fps['RENAMED_SENSOR'].SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    land('RENAMED_CABLE','1','RENAMED_X',(16,33.9),(2,2))
    tracks=[]
    edges=(((20,30.253),(20,33.25)),((20,33.25),(20,36.25))) if flush else (((20,30),(19.9,30)),((19.9,30),(16,33.9)))
    for a,b in edges:
        t=pcbnew.PCB_TRACK(board);t.SetNet(nets['RENAMED_X']);t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(2000000);t.SetLocked(True);t.SetStart(pcbnew.VECTOR2I_MM(*a))
        t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t);tracks.append(t)
    combined=unary_union([Polygon(contour.purposeful_envelope(contour._native_capsule(t),
        style='chamfer45',margin_nm=1000,grid_nm=1000)) for t in tracks])
    if flush:combined=Polygon([(19000000,29249000),(21000000,29249000),(21000000,37251000),(19000000,37251000)])
    zone=pcbnew.ZONE(board);zone.SetNet(nets['RENAMED_X']);zone.SetLayer(pcbnew.F_Cu)
    zone.SetZoneName(contour.ZONE_NAME);zone.SetMinThickness(100000);zone.SetLocalClearance(200000)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);zone.Outline().NewOutline()
    for x,y in list(combined.exterior.coords)[:-1]:zone.Outline().Append(int(x),int(y))
    board.Add(zone)
    for a,b in (((0,0),(50,0)),((50,0),(50,50)),((50,50),(0,50)),((0,50),(0,0))):
        e=pcbnew.PCB_SHAPE(board);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(e)
    origin=pcbnew.VECTOR2I(0,0);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for fp in board.GetFootprints():fp.Rotate(origin,rotation);fp.Move(pcbnew.VECTOR2I_MM(80,70))
    for i in [*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        i.Rotate(origin,rotation);i.Move(pcbnew.VECTOR2I_MM(80,70))
    cec_zone_fill.fill_with_report(board)
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(board,path)
    scope=dict(board_hint='synthetic',pad_uuid=force._uid(source_pad),zone_uuid=force._uid(zone),
        track_uuids=[force._uid(t) for t in tracks])
    domain=dict(complete=True,source_refs=['RENAMED_CABLE'],sink_refs=['RENAMED_SHUNT'],
        authority_refs=['RENAMED_CABLE','RENAMED_SHUNT'])
    contract=dict(required_by_layer_mm={'F.Cu':2.},authority_refs=domain['authority_refs'])
    return path,scope,domain,contract


def constructed(tmp_path,angle=0):
    path,scope,domain,contract=fixture(tmp_path,angle)
    with patch.object(seat.topology,'board_current_domains',return_value={'RENAMED_X':domain}), \
         patch.object(seat.topology,'route_width_contracts',return_value={'RENAMED_X':contract}):
        board=pcbnew.LoadBoard(str(path));proposal=seat.plan(board,path,**scope)
        target=force._copy_family(path,tmp_path/'child');seat.materialize(board,proposal)
        field._save_field_snapshot(board,target);seat.compile_saved(target,proposal)
    return path,target,scope,domain,contract


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_source_force_landing_owns_exact_native_equal_width_geometry(tmp_path,angle):
    source,child,scope,domain,contract=constructed(tmp_path,angle)
    hashes=[force._hash(p) for p in (source,child)]
    with patch.object(seat.topology,'board_current_domains',return_value={'RENAMED_X':domain}), \
         patch.object(seat.topology,'route_width_contracts',return_value={'RENAMED_X':contract}):
        result=seat.receive(source,child,**scope)
    assert result['ok'] and result['complete'],result
    assert result['proposal']['required_width_nm']==2000000
    assert len(result['modified_native_uuids'])==3 and not result['added_native_uuids']
    assert hashes==[force._hash(p) for p in (source,child)]
    assert not result['current_authority'] and not result['release_authority']


@pytest.mark.parametrize('fault',['pad_move','thin_force','old_force_change','keeper_settings','foreign_pose',
    'source_authority','source_width','unsupported_sensor'])
def test_exact_force_geometry_does_not_grant_unowned_mutation_or_current_credit(tmp_path,fault):
    source,child,scope,domain,contract=constructed(tmp_path)
    board=pcbnew.LoadBoard(str(child))
    if fault=='pad_move':board.FindFootprintByReference('RENAMED_SHUNT').Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='thin_force':next(t for t in board.GetTracks()).SetWidth(1999999)
    elif fault=='old_force_change':next(t for t in board.GetTracks()).SetEnd(pcbnew.VECTOR2I_MM(15,34))
    elif fault=='keeper_settings':next(z for z in board.Zones()).SetLocalClearance(190000)
    elif fault=='foreign_pose':board.FindFootprintByReference('RENAMED_CABLE').Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='source_authority':domain['complete']=False
    elif fault=='source_width':contract['required_by_layer_mm']['F.Cu']=2.01
    else:
        original=pcbnew.LoadBoard(str(source));original.FindFootprintByReference('RENAMED_SENSOR').SetValue('UNKNOWN')
        field._save_field_snapshot(original,source)
    field._save_field_snapshot(board,child)
    with patch.object(seat.topology,'board_current_domains',return_value={'RENAMED_X':domain}), \
         patch.object(seat.topology,'route_width_contracts',return_value={'RENAMED_X':contract}):
        result=seat.receive(source,child,**scope)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_existing_flush_keeper_trims_only_microscopic_grid_cap_without_reseating_native_tracks(tmp_path,angle):
    source,scope,domain,contract=fixture(tmp_path,angle,flush=True)
    before,_=force._preservation_snapshot(source)
    scope=dict(scope,mode='existing_outer_keeper')
    with patch.object(seat.topology,'board_current_domains',return_value={'RENAMED_X':domain}), \
         patch.object(seat.topology,'route_width_contracts',return_value={'RENAMED_X':contract}):
        board=pcbnew.LoadBoard(str(source));proposal=seat.plan(board,source,**scope)
        child=force._copy_family(source,tmp_path/'keeper');seat.materialize(board,proposal)
        field._save_field_snapshot(board,child);seat.compile_saved(child,proposal)
        result=seat.receive(source,child,**scope)
    after,_=force._preservation_snapshot(child)
    assert result['ok'] and result['complete'],result
    assert proposal['source_inner_overhang_trimmed_nm']==2000
    assert proposal['path_nm']==[] and proposal['native_tracks_and_full_width_collector_unchanged']
    assert result['modified_native_uuids']==[scope['zone_uuid']]
    assert all(before[uid]==after[uid] for uid in scope['track_uuids'])
    assert not proposal['new_capacity_credited']


def test_existing_keeper_mode_cannot_claim_original_unretracted_force_geometry(tmp_path):
    source,scope,domain,contract=fixture(tmp_path)
    with patch.object(seat.topology,'board_current_domains',return_value={'RENAMED_X':domain}), \
         patch.object(seat.topology,'route_width_contracts',return_value={'RENAMED_X':contract}):
        with pytest.raises(ValueError,match='already_outer_and_flush'):
            seat.plan(pcbnew.LoadBoard(str(source)),source,**scope,mode='existing_outer_keeper')
