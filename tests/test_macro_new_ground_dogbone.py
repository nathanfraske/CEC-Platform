"""A required new bypass return is not credit until actual saved copper exists."""
import copy
import pcbnew
import pytest
import cec_macro_new_ground_dogbone as op
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_cell_row_rebuild as row
import cec_force_current as force
from test_complete_macro_cell import fixture as cell_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,private,packet=cell_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    proposal=packet['source_plan']
    capref=next(iter(proposal['selected_bypasses']))
    cap=private.FindFootprintByReference(capref)
    pad=next(p for p in cap.Pads()if p.GetNetname()=='GND')
    vector=[(700000,0),(0,-700000),(-700000,0),(0,700000)][quarter]
    request=dict(owner_pad_uuid=force._uid(pad),position_nm=[pad.GetPosition().x+vector[0],
        pad.GetPosition().y+vector[1]],geometry_index=0)
    return source,parent,private,packet,pad,request


def build(board,proof,width=None,face=None,barrel=True):
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==proof['pad_uuid'])
    track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(proof['face']if face is None else face)
    track.SetStart(pcbnew.VECTOR2I(*proof['pad_point_nm']));track.SetEnd(pcbnew.VECTOR2I(*proof['point_nm']))
    track.SetWidth(proof['width_nm']if width is None else width);board.Add(track)
    items=[track]
    if barrel:
        via=op._column(board,pad,proof['point_nm'],proof['diameter_nm'],proof['drill_nm']);board.Add(via);items.append(via)
    return {force._uid(i)for i in items}


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_source_selected_new_dogbone_all_cardinal_faces(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch,quarter,back)
    before=[row._source_binding(b)for b in(parent,private)];raw=source.read_bytes()
    proofs,columns=op.plan(parent,private,packet['source_plan'],[request]);proof=proofs[0]
    assert len(columns)==1 and proof['mandatory_new_saved_barrel_and_stub']
    assert proof['maximum_surface_path_mm']==.8 and proof['width_nm']>=200000
    op.rederive(private,proof)
    assert before==[row._source_binding(b)for b in(parent,private)] and raw==source.read_bytes()
    ops=[('trk',tuple(proof['pad_point_nm']),tuple(proof['point_nm']),proof['width_nm'],proof['face']),
        ('via',tuple(proof['point_nm']),proof['drill_nm']/1e6,proof['diameter_nm']/1e6)]
    assert op.required_ops(proof,ops)
    with pytest.raises(ValueError):op.receive(private,proofs,set())
    incoming=build(private,proof)
    observed=op.receive(private,proofs,incoming)
    assert observed[0]['exact_new_return_constructed'] and not observed[0]['current_qualified']


@pytest.mark.parametrize('fault',['float','bool','long','center','bad_geometry','bool_geometry','owner_ground','supply','stationary'])
def test_bad_site_geometry_role_and_motion_never_fund_new_return(tmp_path,monkeypatch,fault):
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch)
    if fault=='float':request['position_nm'][0]=float(request['position_nm'][0])
    elif fault=='bool':request['position_nm'][0]=True
    elif fault=='long':request['position_nm'][0]+=1000000
    elif fault=='center':request['position_nm']=list(pad.GetPosition())
    elif fault=='bad_geometry':request['geometry_index']=999
    elif fault=='bool_geometry':request['geometry_index']=False
    elif fault=='owner_ground':
        owner=private.FindFootprintByReference(next(iter(packet['source_plan']['poses'])))
        if owner.GetReference()==pad.GetParentFootprint().GetReference():
            owner=next(f for f in private.GetFootprints()if f.GetReference()in packet['source_plan']['poses']and f.GetReference()!=owner.GetReference())
        request['owner_pad_uuid']=force._uid(next(p for p in owner.Pads()if p.GetNetname()=='GND'))
    elif fault=='supply':request['owner_pad_uuid']=force._uid(next(p for p in pad.GetParentFootprint().Pads()if p.GetNetname()!='GND'))
    else:
        old=next(p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==force._uid(pad));pad.SetPosition(old.GetPosition())
    before=[row._source_binding(b)for b in(parent,private)]
    with pytest.raises(ValueError):op.plan(parent,private,packet['source_plan'],[request])
    assert before==[row._source_binding(b)for b in(parent,private)]


@pytest.mark.parametrize('fault',['missing_barrel','thin','wrong_face','wrong_drill','land_changed'])
def test_actual_saved_new_return_not_an_unguarded_operation_claim(tmp_path,monkeypatch,fault):
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,private,packet['source_plan'],[request]);proof=proofs[0]
    incoming=build(private,proof,width=100000 if fault=='thin'else None,
        face=pcbnew.B_Cu if fault=='wrong_face'else None,barrel=fault!='missing_barrel')
    if fault=='wrong_drill':next(t for t in private.GetTracks()if force._uid(t)in incoming and t.GetClass()=='PCB_VIA').SetDrill(400000)
    elif fault=='land_changed':pad.SetSize(pcbnew.VECTOR2I_MM(.6,.5))
    with pytest.raises(ValueError):op.receive(private,proofs,incoming)


def test_source_changed_and_forged_width_rederive_refuse(tmp_path,monkeypatch):
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,private,packet['source_plan'],[request]);proof=proofs[0]
    forged=copy.deepcopy(proof);forged['width_nm']-=1
    with pytest.raises(ValueError):op.rederive(private,forged)
    source.write_bytes(source.read_bytes()+b'\n')
    with pytest.raises(ValueError):op.rederive(private,proof)


@pytest.mark.parametrize('back',[False,True])
def test_whole_compiler_screen_and_saved_receiving_require_actual_dogbone(tmp_path,monkeypatch,back):
    source,parent,private,oldpacket,pad,request=fixture(tmp_path,monkeypatch,back=back)
    raw=source.read_bytes()
    draft,packet=compiler.compile(source,oldpacket['source_plan']['poses'],board_hint='opaque',
        required_new_ground_dogbones=[request])
    proofs=packet['required_new_ground_dogbones']
    assert len(proofs)==1
    req=packet['requests']['ground:'+request['owner_pad_uuid']]
    assert req['required_new_ground_dogbone']==proofs[0]
    offer,detail=op.entry_ops(draft,proofs[0])
    assert detail['found'] and op.required_ops(proofs[0],offer),detail
    screened=macro.screen(source,draft,packet,board_hint='opaque')
    assert screened['complete'],__import__('json').dumps({
        'errors':screened['errors'],'native_frame':screened.get('independent_macro_native_frame')},indent=2)
    macro.escape.construct_private(draft,screened['packet'],screened['selection'])
    macro.additive._ground_refill(draft)
    child=force._copy_family(source,tmp_path/'new-dogbone-child')
    macro.save_private(draft,child,packet)
    received=macro.receive(source,child,board_hint='opaque',required_new_ground_dogbones=[request])
    assert received['ok'] and received['complete'],received['errors']
    assert source.read_bytes()==raw


def test_unknown_original_return_stays_unknown_until_new_material_received(tmp_path,monkeypatch):
    from cec_native_items import discard_items
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch)
    discard_items(parent,[t for t in parent.GetTracks()if t.GetNetname()=='GND'])
    field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source));private=pcbnew.LoadBoard(str(source))
    for ref,pose in packet['source_plan']['poses'].items():
        fp=private.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));fp.SetOrientationDegrees(pose[2])
    proposal=copy.deepcopy(packet['source_plan']);proposal['source_native_binding']=row._source_binding(parent)
    proofs,_=op.plan(parent,private,proposal,[request]);proof=proofs[0]
    assert proof['source_return_mm'] is None and proof['original_unknown_return_not_promoted_to_known']
    with pytest.raises(ValueError):op.receive(private,proofs,set())
    result=op.receive(private,proofs,build(private,proof))
    assert result[0]['original_unknown_return_not_promoted_to_known']


def test_foreign_column_blockage_and_exact_operation_dimensions(tmp_path,monkeypatch):
    source,parent,private,packet,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,private,packet['source_plan'],[request]);proof=proofs[0]
    ops=[('trk',proof['pad_point_nm'],proof['point_nm'],proof['width_nm'],proof['face']),
        ('via',proof['point_nm'],proof['drill_nm']/1e6,proof['diameter_nm']/1e6)]
    for index,value in [(2,proof['drill_nm']/1e6+.001),(3,proof['diameter_nm']/1e6+.001)]:
        forged=copy.deepcopy(ops);forged[1]=list(forged[1]);forged[1][index]=value
        assert not op.required_ops(proof,forged)
    forged=copy.deepcopy(ops);forged[0]=list(forged[0]);forged[0][3]-=1
    assert not op.required_ops(proof,forged)
    track=pcbnew.PCB_TRACK(private);track.SetNet(private.FindNet('OUT'));track.SetLayer(proof['face'])
    track.SetStart(pcbnew.VECTOR2I(*proof['point_nm']));track.SetEnd(pcbnew.VECTOR2I(
        proof['point_nm'][0]+500000,proof['point_nm'][1]));track.SetWidth(200000);private.Add(track)
    before=row._source_binding(private);offer,detail=op.entry_ops(private,proof)
    assert not offer and not detail['found'] and row._source_binding(private)==before


def device_fixture(tmp_path,monkeypatch,quarter=0,back=False):
    """A real long SMD ground land with a known external Source stub.

    Native geometry and manufacturer roles remain real. Only the enclosing
    synthetic supply catalog comes from the existing complete-cell fixture.
    No locality/return verdict is mocked.
    """
    from cec_native_items import discard_items
    source,parent,unused,packet=cell_fixture(tmp_path,monkeypatch,quarter=quarter,
        back=back,ground_class_width_mm=.5)
    ref=next(iter(packet['source_plan']['device_contracts']))
    owner=parent.FindFootprintByReference(ref);pad=owner.FindPadByNumber('2')
    assert pad.GetNetname()=='GND'
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    cap=parent.FindFootprintByReference(next(iter(packet['source_plan']['selected_bypasses'])))
    cap_ground=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    # Retain all unrelated native material, but author this TEST Source's
    # local connection explicitly instead of inheriting its via-in-pad zero.
    discard_items(parent,[t for t in parent.GetTracks() if t.GetNetname()=='GND'
        and (t.GetClass()=='PCB_TRACK' or tuple(t.GetPosition())!=tuple(cap_ground.GetPosition()))])
    directions=[(-1,0),(0,1),(1,0),(0,-1)]
    dx,dy=directions[quarter];center=tuple(pad.GetPosition());face=next(iter(pad.GetLayerSet().CuStack()))
    points=[pcbnew.VECTOR2I(center[0]+dx*offset,center[1]+dy*offset)
        for offset in (0,700000,1050000,1300000)]
    for index,(a,b) in enumerate(zip(points,points[1:])):
        item=pcbnew.PCB_TRACK(parent);item.SetNet(pad.GetNet());item.SetLayer(face)
        item.SetStart(a);item.SetEnd(b);item.SetWidth(200000 if index==0 else 500000)
        parent.Add(item)
    parent.Add(op._column(parent,pad,tuple(points[-1]),600000,300000))
    field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source))
    poses=packet['source_plan']['poses']
    private,fresh=compiler.compile(source,poses,board_hint='opaque')
    macro.additive._ground_refill(private)
    pad=private.FindFootprintByReference(ref).FindPadByNumber('2')
    request=dict(owner_pad_uuid=force._uid(pad),geometry_index=0,
        position_nm=[pad.GetPosition().x-dx*1300000,pad.GetPosition().y-dy*1300000])
    proposal=fresh['source_plan']
    return source,parent,private,proposal,pad,request


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_long_device_land_uses_native_contact_not_expanded_electrical_reach(
        tmp_path,monkeypatch,quarter,back):
    source,parent,private,proposal,pad,request=device_fixture(tmp_path,monkeypatch,quarter,back)
    before=[row._source_binding(b) for b in (parent,private)];raw=source.read_bytes()
    proofs,_=op.plan(parent,private,proposal,[request]);proof=proofs[0]
    assert proof['scope']=='source_required_new_immediate_device_ground_attachment_dogbone'
    assert proof['source_bypass_owner'] is None
    assert proof['source_device_attachment']['manufacturer_role']=='power_return'
    assert proof['maximum_surface_path_mm']==proof['source_return_mm']<.8
    assert proof['maximum_centerline_work_nm']>1300000
    op.rederive(private,proof)
    offer,detail=op.entry_ops(private,proof)
    assert offer and detail['found'],__import__('json').dumps(detail,indent=2)
    assert op.required_ops(proof,offer)
    assert detail['incoming_native_surface_path_mm']<=proof['source_return_mm']
    tracks=[o for o in offer if o[0]=='trk']
    assert {o[3] for o in tracks}=={200000,500000}
    assert sum(__import__('math').dist(o[1],o[2]) for o in tracks)>800000
    assert before==[row._source_binding(b) for b in (parent,private)] and raw==source.read_bytes()
    incoming=set()
    for item in macro.escape._native_ops(private,offer,'GND'):incoming.add(force._uid(item))
    observed=op.receive(private,proofs,incoming)
    assert observed[0]['incoming_native_surface_path_mm']<=proof['source_return_mm']
    assert not observed[0]['current_qualified']


@pytest.mark.parametrize('fault',['all_thin','thin_body','wrong_face','long_body','forged_reach','unknown_role'])
def test_device_attachment_never_waives_width_surface_role_or_known_return(tmp_path,monkeypatch,fault):
    source,parent,private,proposal,pad,request=device_fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,private,proposal,[request]);proof=proofs[0]
    offer,detail=op.entry_ops(private,proof)
    assert offer,detail
    bad=copy.deepcopy(offer)
    if fault in ('all_thin','thin_body'):
        if fault=='all_thin':
            bad=[(o[0],o[1],o[2],200000,o[4]) if o[0]=='trk' else o for o in bad]
        else:
            index=next(i for i,o in enumerate(bad) if o[0]=='trk' and o[3]==500000)
            o=bad[index];bad[index]=(o[0],o[1],o[2],200000,o[4])
        assert not op.required_ops(proof,bad)
    elif fault=='wrong_face':
        bad=[(o[0],o[1],o[2],o[3],pcbnew.B_Cu) if o[0]=='trk' else o for o in bad]
        assert not op.required_ops(proof,bad)
    elif fault=='long_body':
        forged=copy.deepcopy(proof);forged['maximum_centerline_work_nm']=1
        assert not op.required_ops(forged,bad)
    elif fault=='forged_reach':
        forged=copy.deepcopy(proof);forged['maximum_surface_path_mm']=.8
        with pytest.raises(ValueError):op.rederive(private,forged)
    else:
        source_owner=parent.FindFootprintByReference(pad.GetParentFootprint().GetReference())
        source_owner.SetValue('Unregistered device')
        field._save_field_snapshot(parent,source)
        proposal['source_native_binding']=row._source_binding(parent)
        with pytest.raises(ValueError):op.plan(parent,private,proposal,[request])


def test_ground_strapped_address_retains_manufacturer_role_not_bypass_alias(tmp_path,monkeypatch):
    source,parent,private,proposal,pad,request=device_fixture(tmp_path,monkeypatch)
    ref=pad.GetParentFootprint().GetReference()
    # A complete REAL INA238 package table, not a mocked address-role
    # verdict. Geometry is intentionally synthetic; the Source's known
    # Ground2 connection remains exactly the same physical native material.
    renumber={'1':'3','2':'2','3':'9','4':'10','5':'6'}
    additional=[]
    for board in (parent,private):
        fp=board.FindFootprintByReference(ref);fp.SetValue('INA238')
        fp.SetFPID(pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'))
        for p in fp.Pads():p.SetNumber(renumber[p.GetNumber()])
        for index,number in enumerate(('1','4','5','7','8')):
            item=pcbnew.PAD(fp);item.SetNumber(number)
            item.SetNet(board.FindNet('GND' if number in ('1','7') else 'OUT'))
            item.SetShape(pcbnew.PAD_SHAPE_RECT);item.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
            item.SetAttribute(pcbnew.PAD_ATTRIB_SMD);item.SetLayerSet(pcbnew.PAD.SMDMask())
            item.SetPosition(pcbnew.VECTOR2I(fp.GetPosition().x-3000000,
                fp.GetPosition().y+index*500000));fp.Add(item)
            if board is parent:additional.append(item.m_Uuid.AsString())
            else:item.m_Uuid.Clone(pcbnew.KIID(additional[index]))
    field._save_field_snapshot(parent,source);parent=pcbnew.LoadBoard(str(source))
    proposal['source_native_binding']=row._source_binding(parent)
    proofs,_=op.plan(parent,private,proposal,[request]);proof=proofs[0]
    assert proof['source_device_attachment']['manufacturer_role']=='address'
    assert proof['source_device_attachment']['actual_role_not_reclassified']
    assert proof['source_bypass_owner'] is None
    assert proof['maximum_surface_path_mm']==proof['source_return_mm']
    op.rederive(private,proof)


@pytest.mark.parametrize('unknown',[False,True])
def test_device_ground_new_attachment_cannot_invent_or_lengthen_source_zero(tmp_path,monkeypatch,unknown):
    from cec_native_items import discard_items
    source,parent,private,packet,cap_pad,unused=fixture(tmp_path,monkeypatch)
    ref=next(iter(packet['source_plan']['device_contracts']))
    pad=private.FindFootprintByReference(ref).FindPadByNumber('2')
    if unknown:
        discard_items(parent,[t for t in parent.GetTracks() if t.GetNetname()=='GND'])
        field._save_field_snapshot(parent,source);parent=pcbnew.LoadBoard(str(source))
    proposal=copy.deepcopy(packet['source_plan']);proposal['source_native_binding']=row._source_binding(parent)
    request=dict(owner_pad_uuid=force._uid(pad),geometry_index=0,
        position_nm=[pad.GetPosition().x-700000,pad.GetPosition().y])
    with pytest.raises(ValueError,match='known_positive_source_device_attachment_return_required'):
        op.plan(parent,private,proposal,[request])


@pytest.mark.parametrize('back',[False,True])
def test_complete_saved_device_attachment_recompiles_and_measures_actual_new_path(tmp_path,monkeypatch,back):
    source,parent,unused,proposal,pad,request=device_fixture(tmp_path,monkeypatch,back=back)
    raw=source.read_bytes()
    draft,packet=compiler.compile(source,proposal['poses'],board_hint='opaque',
        required_new_ground_dogbones=[request])
    macro.additive._ground_refill(draft)
    proof=packet['required_new_ground_dogbones'][0]
    assert proof['source_device_attachment']['manufacturer_role']=='power_return'
    screened=macro.screen(source,draft,packet,board_hint='opaque')
    assert screened['complete'],__import__('json').dumps({
        'errors':screened['errors'],'native_frame':screened.get('independent_macro_native_frame')},indent=2)
    macro.escape.construct_private(draft,screened['packet'],screened['selection'])
    macro.additive._ground_refill(draft)
    child=force._copy_family(source,tmp_path/'new-device-attachment-child')
    macro.save_private(draft,child,packet)
    received=macro.receive(source,child,board_hint='opaque',required_new_ground_dogbones=[request])
    assert received['ok'] and received['complete'],received['errors']
    assert source.read_bytes()==raw
