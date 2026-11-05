"""Joint-cell endpoint ownership is geometric AND source-current preserving."""
import copy
import math
import time
import pcbnew
import pytest
import cec_cell_endpoint_groups as subject
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
from cec_native_items import discard_items
from cec_route_dimensions import current_trace_widths
from test_full_current_supply_prefix import example


def supply(monkeypatch,*,back=False,angle=0):
    board,launch,via,trunk,prefix,contracts=example(back=back,angle=angle,
        netname='/arbitrary/SOURCE_RAIL',ref='RENAMED_INPUT')
    authored=next(iter(contracts.values()));authority=copy.deepcopy(authored['current_authority'])
    widths=current_trace_widths(authority,tuple(board.GetLayerName(l)for l in board.GetEnabledLayers().CuStack()),
        'jlcpcb_6l_pofv_signal',rise_c=30.)
    raw=dict(current_authority=authority,profile='jlcpcb_6l_pofv_signal',
        required_by_layer_nm={board.GetLayerID(n):math.ceil(w*1e6)for n,w in widths.items()})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda*b:copy.deepcopy(raw))
    monkeypatch.setattr(cells,'_netclass',lambda*b:{'width':1000000,'clearance':200000})
    req={'arbitrary':dict(kind='local_supply',net=launch.GetNetname(),a={'pad_uuid':force._uid(launch)},
        width_nm=1000000,unchanged_full_rail_current_contract=copy.deepcopy(raw))}
    return board,launch,via,trunk,prefix,raw,req


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_group_loss_repaired_and_saved_supply_current_reproved(monkeypatch,back,angle):
    board,launch,via,trunk,prefix,raw,req=supply(monkeypatch,back=back,angle=angle)
    prefix.GetParentGroup().RemoveItem(prefix)
    proofs=subject.group(board,[prefix],board_hint='renamed')
    assert proofs and prefix.GetParentGroup().GetName()==fr.ENDPOINT_NECKDOWN_GROUP
    result=subject.receive(board,board,req,[prefix],board_hint='renamed',deadline=time.monotonic()+10)
    assert result['track_uuids']==[force._uid(prefix)]
    assert not result['current_budget_lowered']
    assert result['proofs'][0]['kind']=='whole_original_current_endpoint_prefix'


@pytest.mark.parametrize('fault',['ungrouped','unknown_current','under_current','long','midspan','branch','changed_current','changed_parent_current'])
def test_saved_supply_labels_cannot_waive_scope_current_or_geometry(monkeypatch,fault):
    board,launch,via,trunk,prefix,raw,req=supply(monkeypatch)
    items=[prefix]
    if fault=='ungrouped':prefix.GetParentGroup().RemoveItem(prefix)
    elif fault=='unknown_current':monkeypatch.setattr(cells,'_supply_current_widths',lambda*b:None)
    elif fault=='under_current':prefix.SetWidth(prefix.GetWidth()-1)
    elif fault=='long':prefix.SetStart(prefix.GetStart()+pcbnew.VECTOR2I_MM(-2,0))
    elif fault=='midspan':prefix.SetStart(prefix.GetStart()+pcbnew.VECTOR2I_MM(-.6,0))
    elif fault=='branch':
        end=prefix.GetEnd();mid=pcbnew.VECTOR2I((prefix.GetStart().x+end.x)//2,(prefix.GetStart().y+end.y)//2);prefix.SetEnd(mid)
        for at in(end,mid+pcbnew.VECTOR2I_MM(0,.5)):
            t=pcbnew.PCB_TRACK(board);t.SetNet(prefix.GetNet());t.SetLayer(prefix.GetLayer());t.SetWidth(prefix.GetWidth())
            t.SetStart(mid);t.SetEnd(at);board.Add(t);prefix.GetParentGroup().AddItem(t);items.append(t)
    elif fault=='changed_current':
        req['arbitrary']['unchanged_full_rail_current_contract']['current_authority']['amps']+=.1
    else:
        changed=copy.deepcopy(raw);changed['current_authority']['amps']+=.1
        values=iter([raw,changed]);monkeypatch.setattr(cells,'_supply_current_widths',lambda*b:copy.deepcopy(next(values)))
    with pytest.raises(ValueError):subject.receive(board,board,req,items,board_hint='renamed',deadline=time.monotonic()+10)


def test_group_cannot_invent_unknown_supply_current(monkeypatch):
    board,launch,via,trunk,prefix,raw,req=supply(monkeypatch)
    prefix.GetParentGroup().RemoveItem(prefix)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda*b:None)
    with pytest.raises(ValueError,match='positive_source_current'):
        subject.group(board,[prefix],board_hint='renamed')


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('alias',['SIG2','ARBITRARY_INNER_SIGNAL'])
def test_saved_supply_current_uses_physical_stack_layer_not_display_alias(monkeypatch,back,alias):
    board,launch,via,trunk,prefix,raw,req=supply(monkeypatch,back=back)
    assert board.SetLayerName(pcbnew.In2_Cu,alias)
    proof=subject.receive(board,board,req,[prefix],board_hint='renamed',deadline=time.monotonic()+10)
    assert proof['track_uuids']==[force._uid(prefix)]
    actual=proof['proofs'][0]['proof']
    assert actual['complete']and not actual['current_budget_lowered']
    assert actual['proofs'][0]['current_authority']==raw['current_authority']


def ground(monkeypatch,*,back=False,angle=0):
    b=pcbnew.BOARD();b.GetDesignSettings().m_TrackMinWidth=200000
    net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
    f=pcbnew.FOOTPRINT(b);f.SetReference('ARBITRARY_GROUND_DEVICE');f.SetPosition(pcbnew.VECTOR2I_MM(10,10));b.Add(f)
    p=pcbnew.PAD(f);p.SetNumber('7');p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(10,10));f.Add(p)
    def track(a,z,w):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(pcbnew.FromMM(w));t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);return t
    narrow=track((10,10),(10.4,10),.28);trunk=track((10.4,10),(12,10),1.)
    if back:
        f.Flip(f.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for t in(narrow,trunk):t.SetLayer(pcbnew.B_Cu)
    if angle:
        for i in(f,narrow,trunk):i.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    monkeypatch.setattr(cells,'_netclass',lambda*b:{'width':1000000,'clearance':200000})
    req={'ground:'+force._uid(p):dict(kind='ground',net='GND',a={'pad_uuid':force._uid(p)},width_nm=1000000)}
    return b,p,narrow,trunk,req


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_ground_prefix_requires_actual_recompiled_ground_launch(monkeypatch,back,angle):
    b,p,narrow,trunk,req=ground(monkeypatch,back=back,angle=angle)
    subject.group(b,[narrow],board_hint='renamed')
    proof=subject.receive(b,b,req,[narrow],board_hint='renamed',deadline=time.monotonic()+10)
    assert proof['track_uuids']==[force._uid(narrow)]
    assert not proof['proofs'][0]['aggregate_ground_current_inferred']


@pytest.mark.parametrize('fault',['missing_launch','wrong_launch','ungrouped','long','midspan','branch'])
def test_ground_prefix_no_untyped_or_interior_launch(monkeypatch,fault):
    b,p,narrow,trunk,req=ground(monkeypatch);subject.group(b,[narrow],board_hint='renamed');items=[narrow]
    if fault=='missing_launch':req={}
    elif fault=='wrong_launch':next(iter(req.values()))['a']['pad_uuid']='unknown-source-land'
    elif fault=='ungrouped':narrow.GetParentGroup().RemoveItem(narrow)
    elif fault=='long':narrow.SetEnd(pcbnew.VECTOR2I_MM(11.8,10));trunk.SetStart(narrow.GetEnd())
    elif fault=='midspan':narrow.SetStart(pcbnew.VECTOR2I_MM(10.6,10))
    else:
        end=narrow.GetEnd();mid=pcbnew.VECTOR2I_MM(10.2,10);narrow.SetEnd(mid)
        for at in(end,mid+pcbnew.VECTOR2I_MM(0,.3)):
            t=pcbnew.PCB_TRACK(b);t.SetNet(narrow.GetNet());t.SetLayer(narrow.GetLayer());t.SetWidth(narrow.GetWidth());t.SetStart(mid);t.SetEnd(at);b.Add(t);narrow.GetParentGroup().AddItem(t);items.append(t)
    with pytest.raises(ValueError):subject.receive(b,b,req,items,board_hint='renamed',deadline=time.monotonic()+10)
