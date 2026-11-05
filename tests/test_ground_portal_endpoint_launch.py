"""Typed local GND endpoint geometry never becomes an inherited thin waiver."""
import copy
import math
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_saved_ground_hierarchy as hierarchy
import cec_decoupler_cell as cells
import cec_cell_endpoint_groups as groups
import cec_force_current as force
import cec_fr as fr
from cec_native_items import discard_items
from test_saved_ground_hierarchy import fixture as source_fixture


def fixture(tmp_path,monkeypatch,*,back=False,rotation=0):
    parent,child,requests,_=source_fixture(tmp_path,monkeypatch)
    for b in(parent,child):
        b.GetDesignSettings().m_MinClearance=200000
        b.GetDesignSettings().m_TrackMinWidth=200000
        discard_items(b,[t for t in b.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetLength()>600000])
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetWidth(500000)
        owner=b.FindFootprintByReference('renamed_owner');owner.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        foreign=pcbnew.NETINFO_ITEM(b,'FOREIGN_ACTUAL_PAD');b.Add(foreign)
        f=pcbnew.FOOTPRINT(b);f.SetReference('RENAMED_FOREIGN');f.SetPosition(pcbnew.VECTOR2I_MM(9.55,10));b.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetNet(foreign);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.1,.1));p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(f.GetPosition());f.Add(p)
        for a,z in[((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
            edge=pcbnew.PCB_SHAPE();edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
        if back:
            for fp in b.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            for t in b.GetTracks():t.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if rotation:
            angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
            for i in[*b.GetFootprints(),*b.GetTracks(),*b.Zones()]:i.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    monkeypatch.setattr(cells,'_netclass',lambda*a:{'width':500000,'clearance':200000})
    selected={'renamed_cap':{'owner':'renamed_owner','pin':'3','rail':'RAIL'}}
    entries=escape.assigned_ground_entries(child,selected,board_hint='fixture')
    import cec_ground_return_policy as policy
    for req in requests.values():
        u=req['a']['pad_uuid'];p=next(p for f in child.GetFootprints()for p in f.Pads()if force._uid(p)==u)
        req['reach_mm']=policy.reach(p,entries)
        if u in entries:req['selected_bypass_entry']=entries[u]
    owner=child.FindFootprintByReference('renamed_owner').FindPadByNumber('1');cap=child.FindFootprintByReference('renamed_cap').FindPadByNumber('2')
    plan=dict(scope='source_typed_complete_cell_escape_proposal',board_hint='fixture',max_shift_mm=6.,
        poses={ref:[child.FindFootprintByReference(ref).GetPosition().x/1e6,child.FindFootprintByReference(ref).GetPosition().y/1e6,child.FindFootprintByReference(ref).GetOrientationDegrees()]for ref in('renamed_owner','renamed_cap')})
    # Mock only the independent manufacturer/source compiler boundary. All
    # resulting native path, throat, group, foreign and return gates are real.
    frozen_requests=copy.deepcopy(requests)
    monkeypatch.setattr(escape,'prepare',lambda*a,**k:copy.deepcopy(plan))
    monkeypatch.setattr(escape,'obligations',lambda*a,**k:copy.deepcopy(frozen_requests))
    return parent,child,owner,cap,requests,plan


def construct(child,owner,cap):
    choices=escape.ground_link_ops(child,owner,cap,deadline=time.monotonic()+1,max_link_mm=4.)
    assert choices,'actual full-class obstruction must permit the pad-local profile'
    ops=choices[0];assert all(op[0]=='trk'and op[3]>=200000 for op in ops)
    assert any(op[3]<500000 for op in ops)and any(op[3]>=500000 for op in ops)
    return escape._native_ops(child,ops,'GND')


def test_fixture_has_real_class_obstruction_and_geometrically_legal_bounded_profile(tmp_path,monkeypatch):
    parent,child,owner,cap,requests,plan=fixture(tmp_path,monkeypatch)
    layer=next(iter(owner.GetLayerSet().CuStack()))
    escapes=[fr._pad_local_escape(p,500000,200000,200000)for p in(owner,cap)]
    legs=fr._profiled_lastmile_path([owner.GetPosition(),cap.GetPosition()],500000,*escapes)
    assert any(w<500000 for a,z,w in legs)and any(w==500000 for a,z,w in legs)
    assert all(w>=200000 and fr._edge_leg_clear(child,a,z,w/2+200000)
        and fr._tap_foreign_clear(child,a,z,w,layer,200000,{owner.GetNetCode()},foreign_cache={})for a,z,w in legs)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_native_fine_ground_launch_has_bounded_prefix_full_body_and_saved_ownership(tmp_path,monkeypatch,back,rotation):
    parent,child,owner,cap,requests,plan=fixture(tmp_path,monkeypatch,back=back,rotation=rotation)
    layer=next(iter(owner.GetLayerSet().CuStack()))
    assert not fr._tap_foreign_clear(child,owner.GetPosition(),cap.GetPosition(),500000,layer,200000,{owner.GetNetCode()},foreign_cache={})
    binding=escape.row._source_binding(parent);made=construct(child,owner,cap)
    assert all(fr._tap_foreign_clear(child,t.GetStart(),t.GetEnd(),t.GetWidth(),layer,200000,{owner.GetNetCode()},foreign_cache={})for t in made)
    groups.group(child,made,board_hint='fixture')
    narrow=[t for t in made if t.GetWidth()<500000]
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(child,narrow,500000,required_clearance=200000)
    assert not rejected and {force._uid(t)for t in qualified}=={force._uid(t)for t in narrow}
    assert sum(t.GetLength()for t in narrow)<=1500000
    proof=hierarchy.receive(parent,child,requests['ground:'+force._uid(owner)],requests,board_hint='fixture',deadline=time.monotonic()+5,source_proposal=plan)
    assert proof['ok']and proof['root_return_mm']<=.8 and not proof['current_authority']
    assert escape.row._source_binding(parent)==binding


@pytest.mark.parametrize('fault',['ungrouped','long','narrow_body','source_thin','wrong_launch','missing_cap_root','missing_source_plan','forged_source_plan','stale_requests'])
def test_new_prefix_never_waives_inherited_source_or_bad_ground_geometry(tmp_path,monkeypatch,fault):
    parent,child,owner,cap,requests,plan=fixture(tmp_path,monkeypatch);made=construct(child,owner,cap);groups.group(child,made,board_hint='fixture')
    narrow=[t for t in made if t.GetWidth()<500000];wide=[t for t in made if t.GetWidth()>=500000]
    if fault=='ungrouped':
        for t in narrow:t.GetParentGroup().RemoveItem(t)
    elif fault=='long':
        # Extend the same narrow launch into the body, not a fake width label.
        first=narrow[0];end=wide[0].GetEnd();first.SetEnd(end);wide[0].SetStart(end)
    elif fault=='narrow_body':
        for t in wide:t.SetWidth(200000)
    elif fault=='source_thin':
        # Exact same UUIDs already in parent: they are not incoming scope.
        for t in made:
            item=t.Duplicate();item.m_Uuid.Clone(pcbnew.KIID(force._uid(t)));item.SetNetCode(parent.GetNetcodeFromNetname('GND'));parent.Add(item)
    elif fault=='wrong_launch':requests['ground:'+force._uid(owner)]['selected_bypass_entry']['owner_ground_pad_uuid']='forged'
    elif fault=='missing_cap_root':
        root=requests['ground:'+force._uid(owner)]['selected_bypass_entry']['root_portal_pad_uuid'];del requests['ground:'+root]
    elif fault=='missing_source_plan':plan=None
    elif fault=='forged_source_plan':plan=dict(plan,max_shift_mm=7.)
    else:requests['ground:'+force._uid(owner)]['unexpected_forgery']=True
    with pytest.raises(ValueError):hierarchy.receive(parent,child,requests['ground:'+force._uid(owner)],requests,board_hint='fixture',deadline=time.monotonic()+5,source_proposal=plan)
