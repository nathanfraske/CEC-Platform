"""Source ownership mocked at manufacturer boundary; copper proofs are native."""
import copy
import time
import pcbnew
import pytest
import cec_saved_ground_hierarchy as subject
import cec_cell_escape_replan as escape
import cec_decoupler_cell as cells
import cec_complete_cell_receiving as complete
import cec_force_current as force
from cec_native_items import discard_items


def fixture(tmp_path, monkeypatch, rotation=0):
    b=pcbnew.BOARD();b.GetDesignSettings().m_TrackMinWidth=200000
    for name in ('GND','RAIL'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    model={'device':'manufacturer-typed-fixture','pins':{'1':'ground','2':'reference','3':'power_input'},'source':'fixture manufacturer'}
    def fp(ref,value,lands):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value);b.Add(f)
        for pin,at,net in lands:
            p=pcbnew.PAD(f);p.SetNumber(pin);p.SetNet(b.FindNet(net));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(*at));f.Add(p)
        return f
    owner=fp('renamed_owner','typed', [('1',(10,10),'GND'),('2',(8.5,10),'GND'),('3',(10,12),'RAIL')])
    cap=fp('renamed_cap','100n',[('1',(13,12),'RAIL'),('2',(13,10),'GND')])
    def track(a,z,width=200000):
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('GND'));t.SetLayer(pcbnew.F_Cu);t.SetWidth(width);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);return t
    track((8.5,10),(10,10));track((10,10),(13,10));track((13,10),(13.5,10))
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(13.5,10));via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(pcbnew.In1_Cu)
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for at in ((0,0),(30,0),(30,30),(0,30)):poly.Append(*[pcbnew.FromMM(v)for v in at])
    z.Outline().Append(poly);z.SetFilledPolysList(pcbnew.In1_Cu,poly);z.SetIsFilled(True);b.Add(z)
    if rotation:
        angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for i in [*b.GetFootprints(),*b.GetTracks(),*b.Zones()]:i.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    path=tmp_path/'parent.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    parent,child=[pcbnew.LoadBoard(str(path))for _ in range(2)]
    monkeypatch.setattr('cec_device_power_roles.footprint_contract',lambda f:copy.deepcopy(model)if f.GetReference()=='renamed_owner'else None)
    assignment={'assigned':{'source':{'cap_ref':'renamed_cap','requirement':{'ref':'renamed_owner','pin':'3','rail':'RAIL'}}}}
    monkeypatch.setattr('cec_constraints._device_bypass_assignment',lambda *a,**k:copy.deepcopy(assignment))
    monkeypatch.setattr('cec_ground_return_policy.owner_policy',lambda hint:dict(max_mm=1.5,source='positive source fixture'))
    monkeypatch.setattr(cells,'_netclass',lambda *a:{'width':200000,'clearance':200000})
    selected={'renamed_cap':{'owner':'renamed_owner','pin':'3','rail':'RAIL'}}
    entries=escape.assigned_ground_entries(child,selected,board_hint='fixture')
    requests={}
    import cec_ground_return_policy as policy
    for f in child.GetFootprints():
        for p in f.Pads():
            if p.GetNetname()!='GND':continue
            u=force._uid(p);r=dict(kind='ground',net='GND',a={'pad_uuid':u},reach_mm=policy.reach(p,entries))
            if u in entries:r['selected_bypass_entry']=entries[u]
            requests['ground:'+u]=r
    return parent,child,requests,assignment


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_native_reference_owner_cap_hierarchy_and_common_saved_caller(tmp_path,monkeypatch,rotation):
    parent,child,requests,_=fixture(tmp_path,monkeypatch,rotation)
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2');r=requests['ground:'+force._uid(ref)]
    assert cells._existing_return(child,ref,.8,allow_native_track_body=True)is None
    proof=subject.receive(parent,child,r,requests,board_hint='fixture',deadline=time.monotonic()+10)
    assert proof['ok']and len(proof['links'])==2 and proof['root_return_mm']<=.8
    proofs=complete._receive_paths(parent,child,requests,set(),'fixture',time.monotonic()+10,allow_retained_no_additions=True)
    assert sum('source_ground_hierarchy'in p for p in proofs)==2


@pytest.mark.parametrize('fault',['missing_cap_request','missing_cap_via','wrong_owner','forged_request','wrong_source',
    'zone_only','width','cycle'])
def test_hostile_or_missing_native_hierarchy(tmp_path,monkeypatch,fault):
    parent,child,requests,assignment=fixture(tmp_path,monkeypatch)
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2');r=requests['ground:'+force._uid(ref)]
    root=r['selected_bypass_entry']['root_portal_pad_uuid']
    if fault=='missing_cap_request':del requests['ground:'+root]
    elif fault=='missing_cap_via':discard_items(child,[t for t in child.GetTracks()if t.GetClass()=='PCB_VIA'])
    elif fault=='wrong_owner':r['selected_bypass_entry']['selected_owner']='unrelated'
    elif fault=='forged_request':r['reach_mm']=1.5
    elif fault=='wrong_source':assignment['assigned']['source']['requirement']['ref']='unrelated'
    elif fault in ('zone_only','width'):
        tracks=[t for t in child.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetLength()>2000000]
        if fault=='zone_only':discard_items(child,tracks)
        else:
            for t in tracks:t.SetWidth(100000)
    else:
        # Even a compromised dependency compiler cannot turn a directed cycle
        # into a ground root. Its source/candidate calls are both rederived.
        original=escape.assigned_ground_entries
        def cyclic(*a,**k):
            entries=original(*a,**k)
            entry=entries[force._uid(ref)];peer=entry['portal_pad_uuid'];entries[peer]['portal_pad_uuid']=force._uid(ref)
            return entries
        monkeypatch.setattr(escape,'assigned_ground_entries',cyclic)
        r['selected_bypass_entry']=cyclic(child,{'renamed_cap':{'owner':'renamed_owner','pin':'3','rail':'RAIL'}},board_hint='fixture')[force._uid(ref)]
    with pytest.raises(ValueError):subject.receive(parent,child,r,requests,board_hint='fixture',deadline=time.monotonic()+10)


@pytest.mark.parametrize('value',[None,True,float('nan'),float('inf'),4.01])
def test_chain_rejects_missing_nonfinite_or_overlong_link(value):
    with pytest.raises(ValueError):subject._chain('a',{'a':{'portal_pad_uuid':'c'}},'c',lambda*a:(value,4.))


@pytest.mark.parametrize('scope',[(),('41d39129-c02a-5577-8550-5589fdfb5455',)])
def test_new_prefix_replay_preserves_exact_reference_ownership_scope(tmp_path,monkeypatch,scope):
    parent,child,requests,_=fixture(tmp_path,monkeypatch)
    thin=pcbnew.PCB_TRACK(child);thin.SetNet(child.FindNet('GND'));thin.SetLayer(pcbnew.F_Cu)
    thin.SetWidth(100000);thin.SetStart(pcbnew.VECTOR2I_MM(13,10));thin.SetEnd(pcbnew.VECTOR2I_MM(13.1,10))
    child.Add(thin)
    cap=child.FindFootprintByReference('renamed_cap')
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',board_hint='fixture',
        poses={'renamed_cap':[*[v/1e6 for v in cap.GetPosition()],cap.GetOrientationDegrees()]},
        max_shift_mm=6.,reference_group_uuids=scope)
    observed=[]
    def fresh(board,poses,**options):
        assert board is parent and poses==proposal['poses']
        assert options['reference_group_uuids']==scope
        observed.append(options)
        return copy.deepcopy(proposal)
    monkeypatch.setattr(escape,'prepare',fresh)
    monkeypatch.setattr(escape,'obligations',lambda *a,**k:copy.deepcopy(requests))
    import cec_cell_endpoint_groups as endpoints
    def receive(before,after,actual,items,**options):
        assert before is parent and after is child and actual==requests
        assert [force._uid(t)for t in items]==[force._uid(thin)]
        return dict(track_uuids=[force._uid(thin)],proofs=['independent exact new prefix'])
    monkeypatch.setattr(endpoints,'receive',receive)
    result=subject._new_ground_prefixes(parent,child,requests,board_hint='fixture',
        deadline=time.monotonic()+10,source_proposal=proposal)
    assert observed and result['track_uuids']==[force._uid(thin)]
    # Passing ownership context is not accepting it: the fresh source compiler
    # must still return the entire exact proposal, not a caller's group waiver.
    monkeypatch.setattr(escape,'prepare',lambda *a,**k:dict(proposal,reference_group_uuids=('forged',)))
    with pytest.raises(ValueError,match='source_plan_changed_or_forged'):
        subject._new_ground_prefixes(parent,child,requests,board_hint='fixture',
            deadline=time.monotonic()+10,source_proposal=proposal)
