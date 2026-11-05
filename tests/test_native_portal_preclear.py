"""Future native via seats are source-bound geometric demands, not waivers."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_future_pose_clearance as future
import cec_cell_row_rebuild as row
import cec_source_cut_chain as chain
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,angle=0,prefix='/renamed/',locked=False):
    signal,control=prefix+'PORTAL',prefix+'CONTROL'
    b=_board([(15,15,signal),(12,15,control),(18,15,control)],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for fp in b.GetFootprints():next(iter(fp.Pads())).SetNumber('1')
    blocker=track(b,control,(12,15),(18,15));blocker.SetLayer(pcbnew.In2_Cu);blocker.SetLocked(locked)
    for at in ((12,15),(18,15)):
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*at))
        via.SetNet(blocker.GetNet());via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    portal=next(iter(b.FindFootprintByReference('X1').Pads()))
    return pcbnew.LoadBoard(str(source)),source,force._uid(portal),force._uid(blocker)


def plan(b,source,uid,**kwargs):
    return future.plan_native_portals(b,[uid],source=source,board_hint='synthetic',
        via_diameter_nm=300000,via_drill_nm=200000,**kwargs)


@pytest.mark.parametrize('angle,prefix',[(0,'/a/'),(90,'/b/'),(180,'/unknown/'),(270,'/z/')])
def test_whole_stack_portal_finds_actual_inner_route_without_board_special_cases(tmp_path,angle,prefix):
    b,source,uid,blocked=fixture(tmp_path,angle,prefix)
    before=row._source_binding(b);saved=source.read_bytes();p=plan(b,source,uid)
    assert p['ok'] and p['retired_track_uuids']==[blocked],p
    assert len(p['lands'])==6 and {r['layer'] for r in p['lands']}=={b.GetLayerName(l) for l in b.GetEnabledLayers().CuStack()}
    assert p['portals'][0]['at_nm']==list(next(iter(b.FindFootprintByReference('X1').Pads())).GetPosition())
    assert p['proposed_barrels_not_constructed'] and not p['current_authority'] and not p['release_authority']
    assert before==row._source_binding(b) and saved==source.read_bytes()


@pytest.mark.parametrize('fault',['locked','group','wide','barrel','ground'])
def test_portal_never_authorizes_protected_source_material(tmp_path,fault):
    b,source,uid,blocked=fixture(tmp_path,locked=fault=='locked')
    edge=next(t for t in b.GetTracks() if force._uid(t)==blocked)
    if fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(edge)
    elif fault=='wide':edge.SetWidth(1000000)
    elif fault=='ground':
        ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground);edge.SetNet(ground)
    elif fault=='barrel':
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(15,15));via.SetNet(edge.GetNet())
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    result=plan(b,source,uid)
    assert not result['ok'] and any(not r['ordinary_retirement_allowed'] for r in result['blockers']),result
    if fault=='barrel':assert any(r['kind']=='PCB_VIA' for r in result['blockers'])
    if fault=='locked':assert plan(b,source,uid,allow_locked_track_uuids=[blocked])['ok']


@pytest.mark.parametrize('fault',['missing','dnp','hole','profile','tiny','unassigned','unrelated_unlock'])
def test_native_factory_land_identity_and_permissions_cannot_be_invented(tmp_path,fault):
    b,source,uid,blocked=fixture(tmp_path);fp=b.FindFootprintByReference('X1');pad=next(iter(fp.Pads()))
    if fault=='missing':uid='not-an-actual-pad'
    elif fault=='dnp':fp.SetAttributes(fp.GetAttributes()|pcbnew.FP_DNP)
    elif fault=='hole':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l';b.SetProperties(props)
    elif fault=='tiny':pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='unassigned':pad.SetNetCode(0)
    with pytest.raises(ValueError):
        plan(b,source,uid,allow_locked_track_uuids=['unknown'] if fault=='unrelated_unlock' else ())


@pytest.mark.parametrize('diameter,drill',[(True,200000),(300000,True),(200000,300000),
    (300000,0),(2100000,200000),(300000.0,200000)])
def test_portal_geometry_is_explicit_and_bounded(tmp_path,diameter,drill):
    b,source,uid,_=fixture(tmp_path)
    with pytest.raises(ValueError):
        future.plan_native_portals(b,[uid],source=source,board_hint='synthetic',
            via_diameter_nm=diameter,via_drill_nm=drill)


def test_preclear_restores_real_source_boundaries_and_does_not_construct_a_portal(tmp_path):
    b,source,uid,blocked=fixture(tmp_path,locked=True);before=source.read_bytes()
    result=future.prepare(source,{},tmp_path/'prefix',board_hint='synthetic',
        portal_pad_uuids=[uid],via_diameter_nm=300000,via_drill_nm=200000,
        allow_locked_track_uuids=[blocked],refine_maze=True)
    assert result['ok'] and result['source_opens']==result['opens'],result
    assert not result['future_blockers'] and not result['new_native_faults']
    child=pcbnew.LoadBoard(result['board'])
    assert len([t for t in child.GetTracks() if t.GetClass()=='PCB_VIA'])==2
    phase=dict(kind='ordinary',candidate=result['board'],retired_track_uuids=[blocked],allow_locked_track_uuids=[blocked])
    proof=chain.receive(source,result['board'],board_hint='synthetic',phases=[phase])
    assert proof['ok'] and proof['complete'],proof
    assert before==source.read_bytes()


def test_forged_portal_proposal_cannot_change_native_geometry_at_construction(tmp_path):
    b,source,uid,blocked=fixture(tmp_path);p=plan(b,source,uid)
    p['via_diameter_nm']=350000
    with pytest.raises(ValueError,match='identity_changed'):future.construct(b,p,source=source)


def test_cut_extension_budget_can_reach_a_clean_external_anchor_after_reserved_ends(tmp_path):
    b,source,uid,blocked=fixture(tmp_path);edge=next(t for t in b.GetTracks() if force._uid(t)==blocked)
    # Remove a source terminal witness at one end and continue the same
    # ordinary branch. The endpoint is outside the demand, but is still an
    # obsolete bend that may need rebuilding to avoid a covered backtrack.
    b.Remove(b.FindFootprintByReference('X3'))
    from cec_native_items import discard_items
    discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==(18000000,15000000)])
    continuation=track(b,edge.GetNetname(),(18,15),(19,15));continuation.SetLayer(pcbnew.In2_Cu)
    p=plan(b,source,uid,cut_extension_mm=1.)
    assert set(p['retired_track_uuids'])=={blocked,force._uid(continuation)},p
