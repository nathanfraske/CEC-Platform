"""Real native isolated bypass transport, not permission for grouped rip-up."""
import copy
import json

import pcbnew
import pytest

import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
import cec_smd_macro_transport as macro
import cec_source_supply_endpoint_cut as owner
from test_field_proposals import track
from test_lastmile import _board

HINT='eps-8pin-rev3'


def fixture(tmp_path,quarter=0,mirror=False,back=False):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    b.GetDesignSettings().m_TrackMinWidth=200000;b.GetDesignSettings().m_MinClearance=200000
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    for net in ('GND','+3V3','OTHER'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def part(ref,value,at,pins,package):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('NativeFixture',package));fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
        fp.SetLayer(face);b.Add(fp)
        for number,net,x,y in pins:
            pad=pcbnew.PAD(fp);pad.SetNumber(number);pad.SetNet(b.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));layers=pcbnew.LSET();layers.AddLayer(face)
            pad.SetLayerSet(layers);fp.Add(pad);pad.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        return fp
    pins=[(str(n),'OTHER',5+n*.7,6)for n in range(1,11)if n not in(6,7)]
    pins += [('6','+3V3',10,10),('7','GND',10,11)]
    ic=part('RENAMED_MONITOR','INA238AIDGST',(9,9),pins,'VSSOP-10_3x3mm_P0.5mm')
    cap=part('C_RENAMED','100nF',(12,10.5),[('1','+3V3',12,10),('2','GND',12,11)],'C_0603_1608Metric')
    strokes=[track(b,'+3V3',(10,10),(10.7,10),width=.2,layer=face),
        track(b,'+3V3',(10.7,10),(11,10),width=.2,layer=face),
        track(b,'+3V3',(11,10),(12,10),width=.5,layer=face)]
    remote=track(b,'GND',(20,20),(21,20),width=.2,layer=face)
    group=pcbnew.PCB_GROUP(b);group.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');b.Add(group)
    for t in [*strokes[:2],remote]:group.AddItem(t)
    for t in strokes:t.SetLocked(True)
    if mirror:
        # A real native mirror of the complete fixture, not a test Boolean
        # substituted for any acceptance decision.
        for fp in b.GetFootprints():
            pads=[(p,tuple(p.GetPosition()))for p in fp.Pads()]
            fp.SetPosition(pcbnew.VECTOR2I(30000000-fp.GetPosition().x,fp.GetPosition().y))
            for p,(x,y)in pads:p.SetPosition(pcbnew.VECTOR2I(30000000-x,y))
        for t in b.GetTracks():
            t.SetStart(pcbnew.VECTOR2I(30000000-t.GetStart().x,t.GetStart().y))
            t.SetEnd(pcbnew.VECTOR2I(30000000-t.GetEnd().x,t.GetEnd().y))
    if quarter:
        for i in [*b.GetFootprints(),*b.GetTracks()]:
            i.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{
        'classes':[{'name':'Default','track_width':.5,'clearance':.2}]},
        'board':{'design_settings':{'rules':{'min_track_width':.2,'min_clearance':.2}}}}))
    a=pcbnew.LoadBoard(str(source));z=pcbnew.LoadBoard(str(source))
    for fp in z.GetFootprints():fp.Move(pcbnew.VECTOR2I_MM(1.2,.8))
    return a,z,source,[force._uid(t)for t in strokes],force._uid(remote),force._uid(group)


def options():return dict(board_hint=HINT,source_floor=lambda t:(500000,200000),allow_locked=True,timeout_s=10.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_native_complete_component_is_carried_by_actual_macro_and_saved_rederived(tmp_path,quarter,mirror,back):
    a,b,source,ids,remote,group=fixture(tmp_path,quarter,mirror,back)
    before=source.read_bytes();untouched=next(t for t in b.GetTracks()if force._uid(t)==remote)
    remote_at=(tuple(untouched.GetStart()),tuple(untouched.GetEnd()))
    result=macro.apply(a,b,source_path=source,board_hint=HINT,
        rebuild_source_ground_endpoints=True,rebuild_source_supply_endpoints=True,
        allow_owned_locked_ground_endpoints=True)
    proof=result['rigid_isolated_selected_bypass_supply_components']
    assert len(proof)==1 and set(proof[0]['track_uuids'])==set(ids)
    assert proof[0]['delta_nm']==[1200000,800000]
    assert not proof[0]['inherited_neckdown_debt_qualified']and not proof[0]['new_thin_allowance']
    assert proof[0]['unchanged_full_rail_current_contract']['current_authority']['amps']>0
    assert (tuple(untouched.GetStart()),tuple(untouched.GetEnd()))==remote_at
    assert set(proof[0]['partial_source_groups'][0]['stationary_members'])=={remote}
    assert all(next(t for t in b.GetTracks()if force._uid(t)==u).IsLocked()for u in ids)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    saved=pcbnew.LoadBoard(str(child))
    # Independent saved rederivation rechecks the real native component,
    # selected bypass and current contract, not constructor success flags.
    assert owner.verify_isolated_components(a,saved,proof,**options())
    assert source.read_bytes()==before
    # The actual compiler must retain EVERY component member rather than
    # retiring just its ungrouped full-width tail as an ordinary boundary.
    extras=compiler._extra_ownership(a,source,result,{'retired_track_uuids':[],
        'board_hint':HINT},__import__('time').monotonic()+5.)
    assert extras==[]


@pytest.mark.parametrize('fault',['missing','third_pad','via','zone','branch','wrong_group',
    'locked_group','no_lock_permission','width_changed','lock_changed','different_delta',
    'rotation','remote_group_motion','missing_current','forged_proof','cut_overlap'])
def test_real_source_or_saved_counterexamples_never_gain_group_transport(tmp_path,fault):
    a,b,source,ids,remote,group=fixture(tmp_path);kw=options()
    if fault=='missing':
        from cec_native_items import discard_items
        discard_items(b,[next(t for t in b.GetTracks()if force._uid(t)==ids[0])])
    elif fault in('third_pad','via','zone','branch'):
        # Add real native Source contact, and independently identical child
        # contact, never a mocked native graph.
        for board in(a,):
            if fault=='third_pad':
                f=pcbnew.FOOTPRINT(board);f.SetReference('THIRD');board.Add(f)
                p=pcbnew.PAD(f);p.SetNumber('1');p.SetNet(board.FindNet('+3V3'))
                p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
                p.SetSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetPosition(pcbnew.VECTOR2I_MM(10.7,10));f.Add(p)
            elif fault=='via':
                v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet('+3V3'));v.SetPosition(pcbnew.VECTOR2I_MM(10.7,10))
                v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
            elif fault=='zone':
                z=pcbnew.ZONE(board);z.SetNet(board.FindNet('+3V3'));z.SetLayer(pcbnew.F_Cu)
                z.Outline().NewOutline()
                for x,y in[(10,9.8),(11,9.8),(11,10.2),(10,10.2)]:z.Outline().Append(round(x*1e6),round(y*1e6))
                board.Add(z)
            else:track(board,'+3V3',(10.7,10),(10.7,10.7),width=.2)
        field._save_field_snapshot(a,source)
        a=pcbnew.LoadBoard(str(source));b=pcbnew.LoadBoard(str(source))
        for fp in b.GetFootprints():fp.Move(pcbnew.VECTOR2I_MM(1.2,.8))
    elif fault in('wrong_group','locked_group'):
        for board in(a,b):
            g=next(iter(board.Groups()))
            if fault=='wrong_group':g.SetName('UNQUALIFIED')
            else:g.SetLocked(True)
    elif fault=='no_lock_permission':kw['allow_locked']=False
    elif fault=='width_changed':next(t for t in b.GetTracks()if force._uid(t)==ids[0]).SetWidth(200001)
    elif fault=='lock_changed':next(t for t in b.GetTracks()if force._uid(t)==ids[0]).SetLocked(False)
    elif fault=='different_delta':b.FindFootprintByReference('C_RENAMED').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='rotation':b.FindFootprintByReference('C_RENAMED').SetOrientationDegrees(90)
    elif fault=='remote_group_motion':next(t for t in b.GetTracks()if force._uid(t)==remote).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_current':kw['board_hint']='no_current_authority_fixture'
    if fault in('forged_proof','cut_overlap'):
        r=macro.apply(a,b,source_path=source,board_hint=HINT,rebuild_source_ground_endpoints=True,
            rebuild_source_supply_endpoints=True,allow_owned_locked_ground_endpoints=True)
        proof=copy.deepcopy(r['rigid_isolated_selected_bypass_supply_components'])
        if fault=='forged_proof':
            proof[0]['tracks'][0]['width_nm']+=1
            with pytest.raises(ValueError):owner.verify_isolated_components(a,b,proof,**kw)
        else:
            with pytest.raises(ValueError,match='overlaps_source_planned_cut'):
                compiler._extra_ownership(a,source,r,{'retired_track_uuids':[ids[0]],'board_hint':HINT},
                    __import__('time').monotonic()+5.)
        return
    try:r=owner.isolated_components(a,b,**kw)
    except ValueError:return
    # Non-isolated or unowned input must remain outside this owner's scope;
    # the macro's existing grouped-motion gate still refuses such a route.
    assert r==[]


@pytest.mark.parametrize('same_net',[False,True])
def test_macro_refuses_new_native_destination_contact_and_rolls_back_all_strokes(tmp_path,same_net):
    a,b,source,ids,remote,group=fixture(tmp_path)
    # Real Source foreign material is clear of the old component but lies
    # exactly on its translated destination. No success path is mocked.
    track(a,'+3V3'if same_net else 'OTHER',(11.4,10.8),(11.4,10.9),width=.2)
    # The macro requires the literal saved Source before any mutation.
    field._save_field_snapshot(a,source)
    b=pcbnew.LoadBoard(str(source))
    for fp in b.GetFootprints():fp.Move(pcbnew.VECTOR2I_MM(1.2,.8))
    before={force._uid(t):(tuple(t.GetStart()),tuple(t.GetEnd()))for t in b.GetTracks()}
    with pytest.raises(ValueError,match='transported_isolated_supply'):
        macro.apply(a,b,source_path=source,board_hint=HINT,rebuild_source_ground_endpoints=True,
            rebuild_source_supply_endpoints=True,allow_owned_locked_ground_endpoints=True)
    assert {force._uid(t):(tuple(t.GetStart()),tuple(t.GetEnd()))for t in b.GetTracks()}==before
