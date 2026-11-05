"""Priority pair copper may not strand a non-pair pin on the same package."""
import pcbnew
import pytest

import cec_future_pin_access as access
import cec_fr as fr
import cec_precision_route as precision
from cec_local_copper_cell import copper_inventory


def fixture(*, angle=0, back=False, prefix='RENAMED', extra_pads=0):
    board = pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    settings=board.GetDesignSettings();settings.m_MinClearance=200000
    settings.m_TrackMinWidth=200000;settings.m_HoleToHoleMin=200000
    nets={}
    for name in ('P','N','SUPPLY','RETURN'):
        net=pcbnew.NETINFO_ITEM(board,'/'+prefix+'/'+name);board.Add(net);nets[name]=net
    for a,b in [((0,0),(50,0)),((50,0),(50,50)),((50,50),(0,50)),((0,50),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(prefix+'_PACKAGE');board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20));pads=[]
    for i,(x,y,name) in enumerate([(0,-.95,'N'),(0,0,'SUPPLY'),(0,.95,'P'),
                                  (2.275,-.95,'N'),(2.275,0,'RETURN'),(2.275,.95,'P')]):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(i+1));pad.SetNet(nets[name])
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1.325,.6))
        pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(x,y));fp.Add(pad);pads.append(pad)
    for i in range(extra_pads):
        pad=pcbnew.PAD(fp);pad.SetNumber('unused-%d'%i);pad.SetNetCode(0)
        pad.SetPosition(pcbnew.VECTOR2I_MM(35+i*.5,35));pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    remote=pcbnew.FOOTPRINT(board);remote.SetReference(prefix+'_REMOTE');board.Add(remote)
    for i,net in enumerate(nets.values()):
        pad=pcbnew.PAD(remote);pad.SetNumber(str(i));pad.SetNet(net)
        pad.SetPosition(pcbnew.VECTOR2I_MM(40,10+i));pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());remote.Add(pad)
    pair=dict(name='arbitrary_pair',kind='usb',p=nets['P'].GetNetname(),n=nets['N'].GetNetname(),
              width=.2,gap=.34,clearance=.2)
    return board,fp,pads,nets,pair


def foreign_track(board,pad,net,layer=pcbnew.In2_Cu,dy=0):
    at=pad.GetPosition()+pcbnew.VECTOR2I_MM(0,dy)
    item=pcbnew.PCB_TRACK(board);item.SetStart(at-pcbnew.VECTOR2I_MM(1,0))
    item.SetEnd(at+pcbnew.VECTOR2I_MM(1,0));item.SetLayer(layer)
    item.SetWidth(200000);item.SetNet(net);item.SetLocked(True);board.Add(item)
    return item


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('extra_pads',[0,10])
def test_native_column_is_reserved_without_names_size_or_side_shortcuts(angle,back,extra_pads):
    board,fp,pads,nets,pair=fixture(angle=angle,back=back,extra_pads=extra_pads)
    before=copper_inventory(board)
    report=access.plan(board,pair)
    port=next(row for row in report['ports'] if row['net']==nets['SUPPLY'].GetNetname())
    assert port['ref']==fp.GetReference() and len(port['clear_rays'])<=2
    assert report['complete'] and not report['release_authority'] and not report['no_path_proof']
    assert access.preserve(board,report)['ok'] and copper_inventory(board)==before
    x,y=port['at_mm']
    assert precision._crosses_avoid([(x-1,y),(x+1,y)],
        precision._avoid_for_layer(report['reservations'],'In2.Cu'),.2)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
def test_all_layer_recheck_catches_new_foreign_copper_and_keeps_it_visible(layer):
    board,fp,pads,nets,pair=fixture();report=access.plan(board,pair)
    foreign_track(board,pads[1],nets['P'],layer)
    before=copper_inventory(board)
    result=access.preserve(board,report)
    assert not result['ok'] and any(row['pad']=='2' for row in result['losses'])
    assert copper_inventory(board)==before


def test_existing_inner_obstruction_is_not_falsely_reserved_or_called_impossible():
    board,fp,pads,nets,pair=fixture();foreign_track(board,pads[1],nets['P'])
    report=access.plan(board,pair)
    assert not any(row['pad']=='2' for row in report['ports'])
    row=next(row for row in report['unavailable'] if row['pad']=='2')
    assert row['conclusion']=='no_sampled_port_not_no_path'
    # The native floors collapse the two profile-menu sizes to ONE legal
    # column. It is still refused by the actual inner-layer obstruction.
    assert row['via_refusal_causes']['foreign copper excludes via land']['layers']=={'In2.Cu':1}


def test_tht_singleton_and_other_pair_members_do_not_get_redundant_vias():
    board,fp,pads,nets,pair=fixture()
    pads[1].SetAttribute(pcbnew.PAD_ATTRIB_PTH);pads[1].SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    pads[1].SetLayerSet(pcbnew.PAD.PTHMask())
    report=access.plan(board,pair,excluded_nets=[nets['RETURN'].GetNetname()])
    assert not report['ports']


def test_existing_real_barrel_is_reused_but_a_dead_stub_is_not_escape_proof():
    board,fp,pads,nets,pair=fixture()
    stub=foreign_track(board,pads[1],nets['SUPPLY'],pcbnew.F_Cu)
    assert any(row['pad']=='2' for row in access.plan(board,pair)['ports'])
    via=pcbnew.PCB_VIA(board);via.SetPosition(pads[1].GetPosition())
    via.SetWidth(350000);via.SetDrill(250000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(nets['SUPPLY']);board.Add(via)
    report=access.plan(board,pair)
    assert report['skipped_connected']>=1 and not any(row['pad']=='2' for row in report['ports'])


def test_longer_existing_path_to_plated_terminal_is_not_a_redundant_via_request():
    board,fp,pads,nets,pair=fixture()
    start=pads[1].GetPosition()
    other=pcbnew.FOOTPRINT(board);other.SetReference('PLATED_OTHER');board.Add(other)
    terminal=pcbnew.PAD(other);terminal.SetNumber('1');terminal.SetNet(nets['SUPPLY'])
    terminal.SetPosition(start+pcbnew.VECTOR2I_MM(-3,2));terminal.SetSize(pcbnew.VECTOR2I_MM(1,1))
    terminal.SetDrillSize(pcbnew.VECTOR2I_MM(.5,.5));terminal.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    terminal.SetLayerSet(pcbnew.PAD.PTHMask());other.Add(terminal)
    points=[start,start+pcbnew.VECTOR2I_MM(-2,0),start+pcbnew.VECTOR2I_MM(-2,2),terminal.GetPosition()]
    for a,b in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(200000)
        t.SetLayer(pcbnew.F_Cu);t.SetNet(nets['SUPPLY']);board.Add(t)
    before=copper_inventory(board)
    report=access.plan(board,pair)
    assert not any(row['pad']=='2' for row in report['ports'])
    assert report['skipped_connected'] and copper_inventory(board)==before


def test_same_net_shortcut_cannot_cross_a_foreign_net_branch():
    board,fp,pads,nets,pair=fixture()
    p=pads[1].GetPosition()
    first=foreign_track(board,pads[1],nets['SUPPLY'],pcbnew.F_Cu)
    first.SetEnd(p+pcbnew.VECTOR2I_MM(2,0))
    foreign=foreign_track(board,pads[1],nets['P'],pcbnew.F_Cu)
    foreign.SetStart(first.GetEnd());foreign.SetEnd(p+pcbnew.VECTOR2I_MM(3,0))
    via=pcbnew.PCB_VIA(board);via.SetPosition(foreign.GetEnd())
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(nets['SUPPLY']);board.Add(via)
    before=copper_inventory(board)
    assert not access._attached_escape(board,pads[1])
    assert copper_inventory(board)==before


def test_declared_profile_and_geometry_are_required():
    board,fp,pads,nets,pair=fixture()
    pads[1].SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    assert not any(row['pad']=='2' for row in access.plan(board,pair)['ports'])
    props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    report=access.plan(board,pair)
    assert report['not_applicable']=='no_declared_pofv_process' and not report['ports']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_future_column_uses_native_board_hard_floors_instead_of_rejecting_the_profile_menu(angle,back):
    board,fp,pads,nets,pair=fixture(angle=angle,back=back,prefix='OTHER_NATIVE_FLOOR')
    settings=board.GetDesignSettings()
    settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=300000
    settings.m_ViasMinAnnularWidth=100000
    before=copper_inventory(board)
    report=access.plan(board,pair,max_free_rays=8)
    port=next(row for row in report['ports'] if row['net']==nets['SUPPLY'].GetNetname())
    assert (port['diameter_mm'],port['drill_mm'])==(.5,.3)
    assert report['complete'] and not report['release_authority'] and not report['no_path_proof']
    assert access.preserve(board,report)['ok'] and copper_inventory(board)==before
    assert settings.m_ViasMinSize==500000 and settings.m_MinThroughDrill==300000
    # A larger, actually occupied column is reserved on every copper face.
    x,y=port['at_mm']
    assert any(row[:4]==(x-.45,y-.45,x+.45,y+.45) for row in report['reservations'])


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
def test_board_floor_clamped_future_column_still_requires_all_layer_clearance(layer):
    board,fp,pads,nets,pair=fixture()
    settings=board.GetDesignSettings()
    settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=300000
    settings.m_ViasMinAnnularWidth=100000
    foreign_track(board,pads[1],nets['P'],layer)
    before=copper_inventory(board);report=access.plan(board,pair,max_free_rays=8)
    assert not any(row['pad']=='2' and row['ref']==fp.GetReference() for row in report['ports'])
    row=next(row for row in report['unavailable'] if row['pad']=='2' and row['ref']==fp.GetReference())
    assert row['conclusion']=='no_sampled_port_not_no_path'
    assert 'foreign copper excludes via land' in row['via_refusal_causes']
    assert copper_inventory(board)==before


def test_board_floor_reservation_does_not_shrink_a_barrel_to_fit_a_tiny_pad():
    board,fp,pads,nets,pair=fixture()
    settings=board.GetDesignSettings()
    settings.m_ViasMinSize=700000;settings.m_MinThroughDrill=400000
    settings.m_ViasMinAnnularWidth=150000
    report=access.plan(board,pair,max_free_rays=8)
    assert not report['ports']  # .7 mm cannot be contained in a .6 mm land.
    assert not report['release_authority'] and not report['no_path_proof']


def test_final_pair_gate_rejects_lost_column_before_claiming_pair_success():
    board,fp,pads,nets,pair=fixture();planned=access.plan(board,pair)
    before=set(copper_inventory(board));foreign_track(board,pads[1],nets['P'])
    result=precision._qualify_pair_candidate(board,pair,dict(pair),pair_pre_ids=before,
        board_path='',pair_avoid=planned['reservations'],endpoint_stations=[],future_pin_access=planned)
    assert result['refused'] and result['failure_certificate']['classification']==['future_pin_access']


def test_production_pair_entry_passes_reservations_and_rolls_back_rogue_generator(monkeypatch):
    board,fp,pads,nets,pair=fixture();seen=[]
    fixed=foreign_track(board,pads[1],nets['RETURN'],pcbnew.B_Cu,dy=10)
    before=copper_inventory(board)
    monkeypatch.setattr(precision,'derive_coupled_pairs',lambda *a,**k:[pair])
    monkeypatch.setattr(precision,'_flow_through_pair_legs',lambda *a:None)
    monkeypatch.setattr(precision,'_multidrop_pair_plan',lambda *a:None)
    def bad_generator(b,p,**kwargs):
        seen.extend(kwargs['avoid'])
        foreign_track(b,pads[1],nets['P'],pcbnew.In2_Cu)
        return dict(pair,segments=1)
    monkeypatch.setattr(precision,'route_coupled_pair',bad_generator)
    report=precision.precision_route_board(board,do_kelvin=False,verbose=False)
    assert any('future-pin:' in row[4] for row in seen)
    assert not report['pairs_ok']
    assert report['pairs']['refused'][0]['failure_certificate']['classification']==['future_pin_access']
    assert copper_inventory(board)==before


def test_bounded_incomplete_search_cannot_claim_a_complete_plan():
    board,fp,pads,nets,pair=fixture()
    result=access.plan(board,pair,max_pads=1)
    assert not result['complete'] and not access.preserve(board,result)['ok']
    assert not access.plan(board,pair,deadline_monotonic=0)['complete']


@pytest.mark.parametrize('kwargs',[dict(max_pads=0),dict(max_pads=True),
    dict(escape_mm=float('nan')),dict(escape_mm=0),dict(max_free_rays=9),
    dict(deadline_monotonic=float('nan'))])
def test_invalid_parameters_fail_closed(kwargs):
    board,fp,pads,nets,pair=fixture()
    with pytest.raises(ValueError):access.plan(board,pair,**kwargs)


def test_shared_neckdown_helper_keeps_exact_existing_contract():
    board,fp,pads,nets,pair=fixture();pad=pads[1]
    assert fr._pad_local_escape(pad,1000000,200000,200000)==(300000,1500000)
    assert fr._pad_local_escape(pad,200000,200000,200000) is None
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    assert fr._pad_local_escape(pad,1000000,200000,200000) is None
