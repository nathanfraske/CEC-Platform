"""Actual pad copper removes centre detours, never the 4 mm wire limit."""
import math,time
import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_endpoint_groups as groups
import cec_ground_package_pad_contacts as subject
import cec_force_current as force
import cec_fr as fr
from test_escape_pose_frontier import native_part


def fixture(*,quarter=0,back=False,barrel=False,separation=4.4):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_MinClearance=200000
    board.GetDesignSettings().m_TrackMinWidth=200000
    for name in ('GND','RAIL','HI','LO','DATA','CLOCK','NC','OBSTACLE'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    klass=pcbnew.NETCLASS('Ground_body');klass.SetTrackWidth(500000);klass.SetClearance(200000)
    board.FindNet('GND').SetNetClass(klass)
    owner=native_part(board,'ARBITRARY_MONITOR','INA238',(15,15),
        [(str(p),-separation/2,-1+(p-1)*.5) for p in range(1,6)]+
        [(str(p),separation/2,1-(p-6)*.5) for p in range(6,11)],
        'Package_SO','VSSOP-10_3x3mm_P0.5mm',3.3,1.8)
    nets={'1':'GND','2':'RAIL','3':'NC','4':'DATA','5':'CLOCK',
        '6':'RAIL','7':'GND','8':'LO','9':'LO','10':'HI'}
    for p in owner.Pads():
        p.SetNet(board.FindNet(nets[p.GetNumber()]))
        p.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    for a,b in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE();edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    if barrel:
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('OBSTACLE'))
        via.SetPosition(pcbnew.VECTOR2I_MM(14.2,14.7));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if back:
        owner.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for track in board.GetTracks():track.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [owner,*board.GetTracks()]:item.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    return board,owner.FindPadByNumber('1'),owner.FindPadByNumber('7')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_port_links_have_full_body_and_no_larger_reach(quarter,back):
    board,left,right=fixture(quarter=quarter,back=back)
    before=escape.row._source_binding(board)
    assert math.dist(tuple(left.GetPosition()),tuple(right.GetPosition()))>4000000
    proof=subject.contacts(board,left,right)
    assert proof and proof['minimum_octilinear_wire_mm']<=4.
    choices=escape.ground_link_ops(board,left,right,deadline=time.monotonic()+2.,max_link_mm=4.)
    assert choices
    for ops in choices:
        assert sum(math.dist(a,b) for kind,a,b,w,layer in ops)<=4000000+1e-3
        assert any(w==500000 for kind,a,b,w,layer in ops)
        assert left.HitTest(pcbnew.VECTOR2I(*ops[0][1]),0)
        assert right.HitTest(pcbnew.VECTOR2I(*ops[-1][2]),0)
        assert all(kind=='trk' and w>=200000 and
            fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),w,
                layer,200000,{left.GetNetCode()},foreign_cache={}) for kind,a,b,w,layer in ops)
    assert escape.row._source_binding(board)==before


@pytest.mark.parametrize('quarter',range(4))
def test_existing_profiled_maze_uses_no_waived_foreign_barrel(quarter):
    board,left,right=fixture(quarter=quarter,barrel=True)
    choices=subject.links(board,left,right,deadline=time.monotonic()+2.)
    assert choices
    for ops in choices:
        assert sum(math.dist(a,b) for kind,a,b,w,layer in ops)<=4000000+1e-3
        assert any(w==500000 for kind,a,b,w,layer in ops)


@pytest.mark.parametrize('fault',['unknown_part','wrong_role','different_owner','foreign_net',
    'tht','offset','custom','empty','too_far'])
def test_no_same_net_or_nearby_pad_authority(fault):
    board,left,right=fixture(separation=5.0 if fault=='too_far' else 4.4)
    if fault=='unknown_part':left.GetParentFootprint().SetValue('UNKNOWN')
    elif fault=='wrong_role':left=left.GetParentFootprint().FindPadByNumber('6');left.SetNet(board.FindNet('GND'))
    elif fault=='different_owner':
        other=pcbnew.FOOTPRINT(board);other.SetReference('OTHER_PACKAGE');board.Add(other)
        copy=right.Duplicate();copy.SetParent(other);other.Add(copy);right=copy
    elif fault=='foreign_net':right.SetNet(board.FindNet('RAIL'))
    elif fault=='tht':left.SetAttribute(pcbnew.PAD_ATTRIB_PTH);left.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='offset':left.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='custom':left.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='empty':left.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
    before=escape.row._source_binding(board)
    assert subject.contacts(board,left,right) is None
    assert not subject.links(board,left,right,deadline=time.monotonic()+1.)
    assert escape.row._source_binding(board)==before


@pytest.mark.parametrize('limit',[True,0,4.000001,float('nan'),float('inf')])
def test_wire_limit_is_not_an_extension_or_truthy_option(limit):
    board,left,right=fixture()
    with pytest.raises(ValueError):subject.contacts(board,left,right,maximum_wire_mm=limit)


def test_expired_proposal_not_no_path_and_no_mutation():
    board,left,right=fixture();before=escape.row._source_binding(board)
    assert subject.contacts(board,left,right,deadline=time.monotonic()-1.) is None
    assert escape.row._source_binding(board)==before


def test_complete_native_endpoint_prefixes_are_still_independently_qualified():
    board,left,right=fixture(barrel=True)
    choices=subject.links(board,left,right,deadline=time.monotonic()+2.)
    assert choices
    made=escape._native_ops(board,choices[0],'GND')
    narrow=[item for item in made if item.GetWidth()<500000]
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,narrow,500000,required_clearance=200000)
    assert not rejected
    assert {force._uid(item) for item in qualified}=={force._uid(item) for item in narrow}


def test_source_assignment_rederives_port_entry_but_preserves_directed_real_root(monkeypatch):
    board,left,right=fixture()
    cap=native_part(board,'C_SOURCE_SELECTED','100nF',(17.9,17.2),
        [('1',-.48,0),('2',.48,0)],'Capacitor_SMD','C_0603_1608Metric',.96,.51)
    cap.FindPadByNumber('1').SetNet(board.FindNet('RAIL'))
    cap.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    # Mock only Source assignment/policy, not manufacturer pin roles, native
    # pad geometry, emitted wire, endpoint or final hierarchy predicates.
    selected={cap.GetReference():dict(owner=left.GetParentFootprint().GetReference(),pin='6',rail='RAIL')}
    assignment={'assigned':{'source':dict(cap_ref=cap.GetReference(),
        requirement=dict(ref=left.GetParentFootprint().GetReference(),pin='6',rail='RAIL'))}}
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:assignment)
    entries=escape.assigned_ground_entries(board,selected,board_hint='opaque')
    entry=entries[force._uid(left)]
    assert entry['typed_reference_or_address_to_package_ground']
    assert entry['portal_pad_uuid']==force._uid(right)
    assert entry['root_portal_pad_uuid']==force._uid(cap.FindPadByNumber('2'))
    assert entry['max_link_mm']==4. and entry['immediate_portal_reach_mm']==.8
    assert entry['native_package_pad_contact_frontier']==subject.contacts(board,left,right)
    assert force._uid(right) in entries


def test_functional_return_cannot_borrow_the_nonreturn_portfolio():
    board,left,right=fixture()
    assert subject.contacts(board,right,left) is None
    assert not escape.ground_link_ops(board,right,left,deadline=time.monotonic()+1.,max_link_mm=4.)
