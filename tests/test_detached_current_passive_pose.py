"""Fresh CLI Source intent with real native contact rejection; no route proof.

Only existing aggregate-domain derivation is fixture-stubbed. Native pad,
track, via and filled-zone contact is never mocked.
"""
import json
import time
import uuid

import cec_swig_guard
cec_swig_guard.pin()
import wx
_QUIET=wx.LogNull()
import pcbnew
import pytest

import cec_detached_current_passive_pose as op
import cec_field_coupling as field
import cec_force_current as force
from test_detached_ordinary_passive_translation import fixture as resistor_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False,kind='Ferrite_Bead'):
    source,root,uid=resistor_fixture(tmp_path,quarter,back)
    text=root.read_text().replace('fixture:R"','fixture:'+kind+'"')
    text=text.replace('"R_0_1"','"'+kind+'_0_1"').replace('"R_1_1"','"'+kind+'_1_1"')
    text=text.replace('(property "MPN" "0402WGF1003TCE"',
        '(property "Manufacturer" "FIXTURE_VENDOR" (at 50 50 0) (effects (font (size 1 1))))\n'
        '(property "LCSC" "FIXTURE_LCSC" (at 50 50 0) (effects (font (size 1 1))))\n'
        '(property "MPN" "0402WGF1003TCE"')
    root.write_text(text)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    fp.SetField('Manufacturer','FIXTURE_VENDOR');fp.SetField('LCSC','FIXTURE_LCSC')
    field._save_field_snapshot(board,source)
    def model(board,source,net,hint):
        owner=board.FindFootprintByReference('RENAMED_R').GetReference()
        domain=dict(complete=True,source_refs=[owner]if net=='/BETA'else['SOURCE_PEER'],
            sink_refs=[owner]if net=='/ALPHA'else['SINK_PEER'],amps=.75)
        contract=dict(net=net,current_authority=dict(source='board_design_basis',amps=.75,
            geometry_margin=1.25,margin_included=False),routing_layers=['F.Cu','B.Cu'],
            required_by_layer_mm={'F.Cu':.5,'B.Cu':.5})
        return 'aggregate_source_sink',domain,contract
    monkeypatch.setattr(op.full,'_model',model)
    return source,root,uid


def pose(uid,at=(12,11,0)):
    return [dict(footprint_uuid=uid,target_pose=list(at))]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fresh_source_json_plan_and_whole_native_projection(tmp_path,monkeypatch,quarter,back):
    source,root,uid=fixture(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();original=pcbnew.LoadBoard(str(source))
    fp=next(iter(original.GetFootprints()));before=op._fingerprint(fp)
    q=op.plan(source,pose(uid,(12,11,quarter*90)),board_hint=str(root))
    assert q==json.loads(json.dumps(q))
    assert q['source_native_binding']==op.row._source_binding(original)
    assert q['records'][0]['source_footprint_sha256']==before
    assert q['records'][0]['canonical_source']['symbol_kind']=='Ferrite_Bead'
    assert {r['source_or_sink']for r in q['records'][0]['current_domains']}=={'source','sink'}
    padids=sorted(force._uid(p)for p in fp.Pads())
    assert op.apply(original,q)==[uid]
    assert list(fp.GetPosition())==[12000000,11000000]
    assert fp.GetOrientationDegrees()%360==quarter*90
    assert fp.IsFlipped()==back
    assert sorted(force._uid(p)for p in fp.Pads())==padids
    assert source.read_bytes()==raw
    assert not q['placement_admitted']and not q['routing_admitted']and not q['current_qualified']
    assert q['retired_copper_uuids']==[]and q['independent_original_parent_saved_receiving_required']


@pytest.mark.parametrize('kind',['L','L_Small','FerriteBead','FerriteBead_Small'])
def test_canonical_inductor_variants_not_refdes_or_part_allowlist(tmp_path,monkeypatch,kind):
    source,root,uid=fixture(tmp_path,monkeypatch,kind=kind)
    q=op.plan(source,pose(uid,(16,10,90)),board_hint=str(root))
    assert q['records'][0]['canonical_source']['symbol_kind']==kind
    board=pcbnew.LoadBoard(str(source));op.apply(board,q)
    assert board.FindFootprintByReference('RENAMED_R').GetOrientationDegrees()==90


@pytest.mark.parametrize('fault',['track','via','pad','filled','unfilled','same_net_filled'])
def test_actual_source_native_contact_or_unknown_fill_refuses(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));pad=next(iter(fp.Pads()))
    if fault=='track':
        item=pcbnew.PCB_TRACK(board);item.SetNet(pad.GetNet());item.SetLayer(pcbnew.F_Cu)
        item.SetWidth(100000);item.SetStart(pad.GetPosition());item.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0));board.Add(item)
    elif fault=='via':
        item=pcbnew.PCB_VIA(board);item.SetNet(pad.GetNet());item.SetPosition(pad.GetPosition())
        item.SetWidth(600000);item.SetDrill(300000);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(item)
    elif fault=='pad':
        peer=pcbnew.FOOTPRINT(board);board.Add(peer);peer.SetReference('UNOWNED')
        item=pcbnew.PAD(peer);peer.Add(item);item.SetNumber('1');item.SetNet(pad.GetNet())
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD);item.SetLayerSet(pad.GetLayerSet())
        item.SetShape(pcbnew.PAD_SHAPE_RECT);item.SetSize(pcbnew.VECTOR2I_MM(.2,.2));item.SetPosition(pad.GetPosition())
    else:
        item=pcbnew.ZONE(board);item.SetLayer(pcbnew.F_Cu)
        item.SetNet(pad.GetNet()if fault=='same_net_filled'else fp.FindPadByNumber('2').GetNet())
        shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline();x,y=pad.GetPosition()
        for dx,dy in[(-400000,-400000),(400000,-400000),(400000,400000),(-400000,400000)]:shape.Append(x+dx,y+dy)
        item.Outline().Append(shape)
        if fault!='unfilled':item.SetFilledPolysList(pcbnew.F_Cu,shape);item.SetIsFilled(True)
        board.Add(item)
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='contact|membership'):
        op.plan(source,pose(uid),board_hint=str(root))


@pytest.mark.parametrize('fault',['locked','group','pad_group','dnp','hole','copper','lands_overlap'])
def test_native_ownership_is_not_a_caller_permission(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));pads=list(fp.Pads())
    if fault=='locked':fp.SetLocked(True)
    elif fault in('group','pad_group'):
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(fp if fault=='group'else pads[0])
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='hole':
        pads[0].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pads[0].SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));pads[0].SetLayerSet(pcbnew.LSET.AllCuMask())
    elif fault=='lands_overlap':pads[0].SetPosition(pads[1].GetPosition())
    else:fp.Reference().SetLayer(pcbnew.F_Cu)
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):op.plan(source,pose(uid),board_hint=str(root))


@pytest.mark.parametrize('fault',['symbol','pin_type','mpn','manufacturer','lcsc','value','fp','pin_net','dnp'])
def test_fresh_canonical_source_mutations_refuse(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch)
    text=root.read_text()
    if fault=='symbol':text=text.replace('fixture:Ferrite_Bead"','fixture:R"')
    elif fault=='pin_type':text=text.replace('(pin passive line','(pin power_in line',1)
    elif fault=='mpn':text=text.replace('0402WGF1003TCE','UNMATCHED')
    elif fault=='manufacturer':text=text.replace('FIXTURE_VENDOR','UNMATCHED')
    elif fault=='lcsc':text=text.replace('FIXTURE_LCSC','UNMATCHED')
    elif fault=='value':text=text.replace('"100k"','"CHANGED"')
    elif fault=='fp':text=text.replace('fixture:R_0402','fixture:CHANGED')
    elif fault=='dnp':text=text.replace('(dnp no)','(dnp yes)')
    else:text=text.replace('"ALPHA"','"OTHER_NET"')
    root.write_text(text)
    with pytest.raises(ValueError):op.plan(source,pose(uid),board_hint=str(root))


@pytest.mark.parametrize('fault',['no_model','distributed','not_owner','incomplete','ambiguous_owner'])
def test_no_new_role_or_budget_from_passive_symbol(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch);real=op.full._model
    def model(*args):
        kind,domain,contract=real(*args)
        if fault=='no_model':raise ValueError('no_positive_existing_current_authority')
        if fault=='distributed':kind='explicit_all_terminal_distributed_supply';domain=None
        elif fault=='not_owner':domain.update(source_refs=['OTHER_SOURCE'],sink_refs=['OTHER_SINK'])
        elif fault=='incomplete':domain['complete']=False
        elif fault=='ambiguous_owner':domain.update(source_refs=['RENAMED_R'],sink_refs=['RENAMED_R'])
        return kind,domain,contract
    monkeypatch.setattr(op.full,'_model',model)
    with pytest.raises(ValueError):op.plan(source,pose(uid),board_hint=str(root))


@pytest.mark.parametrize('changes',[
    {'poses':[]},{'poses':[{}]},{'poses':[{'footprint_uuid':'x','target_pose':[1,2,True]}]},
    {'max_shift_mm':True},{'max_shift_mm':0},{'max_shift_mm':32.01},{'timeout_s':11},
    {'timeout_s':float('nan')},{'poses':[{'footprint_uuid':'x','target_pose':[1,2,0],'role':True}]},
])
def test_schema_and_lease_bounds(tmp_path,monkeypatch,changes):
    source,root,uid=fixture(tmp_path,monkeypatch)
    args=dict(poses=pose(uid),board_hint=str(root));args.update(changes)
    with pytest.raises(ValueError):op.plan(source,**args)


@pytest.mark.parametrize('at',[(10,10,0),(16.000001,10,0),(12,11,45)])
def test_nonzero_cardinal_bounded_actual_pose(tmp_path,monkeypatch,at):
    source,root,uid=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):op.plan(source,pose(uid,at),board_hint=str(root))


def test_explicit_larger_pose_budget_changes_no_source_current_or_admission_authority(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch)
    request=pose(uid,(17.5,10,0));original=source.read_bytes()
    with pytest.raises(ValueError,match='bounded_nonzero_cardinal'):
        op.plan(source,request,board_hint=str(root))
    q=op.plan(source,request,board_hint=str(root),max_shift_mm=8.)
    board=pcbnew.LoadBoard(str(source));op.apply(board,q)
    assert q['request']['max_shift_mm']==8. and source.read_bytes()==original
    assert list(next(iter(board.GetFootprints())).GetPosition())==[17500000,10000000]
    assert all(c['contract']['current_authority']['amps']==.75 for c in q['records'][0]['current_domains'])
    assert not q['placement_admitted']and not q['routing_admitted']and not q['current_qualified']


@pytest.mark.parametrize('fault',['request','proof','current','source_field','caller_pad','caller_field','caller_pose','caller_contact'])
def test_apply_revalidates_fresh_source_and_every_owner_before_mutation(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch)
    q=op.plan(source,pose(uid),board_hint=str(root));board=pcbnew.LoadBoard(str(source))
    fp=next(iter(board.GetFootprints()))
    if fault=='request':q['request']['poses'][0]['target_pose'][0]+=1
    elif fault=='proof':q['records'][0]['actual_native_source_isolated']=False
    elif fault=='current':q['records'][0]['current_domains'][0]['contract']['current_authority']['amps']=.1
    elif fault=='source_field':root.write_text(root.read_text().replace('FIXTURE_VENDOR','CHANGED'))
    elif fault=='caller_pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='caller_field':fp.SetField('Manufacturer','CHANGED')
    elif fault=='caller_pose':fp.SetPosition(pcbnew.VECTOR2I_MM(10.1,10))
    else:
        pad=next(iter(fp.Pads()));track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(100000);track.SetStart(pad.GetPosition());track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0));board.Add(track)
    before=op.row._source_binding(board);fp_before=op._fingerprint(fp)
    with pytest.raises(ValueError):op.apply(board,q)
    assert op.row._source_binding(board)==before and op._fingerprint(fp)==fp_before


def test_apply_allows_unrelated_private_projection_but_grants_it_no_authority(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch)
    q=op.plan(source,pose(uid),board_hint=str(root));board=pcbnew.LoadBoard(str(source))
    other=pcbnew.FOOTPRINT(board);other.SetReference('UNRELATED_PROJECTION');board.Add(other)
    other.SetPosition(pcbnew.VECTOR2I_MM(25,25));before=op._fingerprint(other)
    assert op.apply(board,q)==[uid]and op._fingerprint(other)==before


def test_duplicate_or_excess_owners_never_project(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch)
    for records in [pose(uid)*2,[dict(footprint_uuid=str(uuid.uuid4()),target_pose=[12,11,0])for _ in range(5)]]:
        with pytest.raises(ValueError):op.plan(source,records,board_hint=str(root))


def test_final_source_digest_and_json_work_belong_to_plan_lease(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch)
    real_clock=time.monotonic;offset=[0.];real_hash=op.force._hash
    monkeypatch.setattr(op.time,'monotonic',lambda:real_clock()+offset[0])
    def slow_hash(path):
        import inspect
        value=real_hash(path)
        if str(path)==str(source)and inspect.currentframe().f_back.f_code.co_name=='plan':offset[0]=11.
        return value
    monkeypatch.setattr(op.force,'_hash',slow_hash)
    with pytest.raises(ValueError,match='deadline'):
        op.plan(source,pose(uid),board_hint=str(root))


def test_apply_last_native_setter_cannot_return_late_positive(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch)
    q=op.plan(source,pose(uid),board_hint=str(root));board=pcbnew.LoadBoard(str(source))
    real_clock=time.monotonic;offset=[0.];real_set=pcbnew.FOOTPRINT.SetOrientationDegrees
    monkeypatch.setattr(op.time,'monotonic',lambda:real_clock()+offset[0])
    def slow_set(fp,angle):
        result=real_set(fp,angle);offset[0]=11.;return result
    monkeypatch.setattr(pcbnew.FOOTPRINT,'SetOrientationDegrees',slow_set)
    with pytest.raises(ValueError,match='deadline'):op.apply(board,q)


def test_actual_native_copper_artwork_is_not_an_isolated_pad(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(source))
    pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_Cu)
    line.SetStart(pad.GetPosition());line.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0));line.SetWidth(200000)
    board.Add(line);field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='artwork_contact'):op.plan(source,pose(uid),board_hint=str(root))


def test_four_actual_owners_share_one_fresh_export_and_validate_before_any_move(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(source))
    original=next(iter(board.GetFootprints()));text=root.read_text()
    block=next(child for tag,child in op.leaf.sch.iter_children(text)if tag=='symbol')
    import re
    ids=re.findall(r'\(uuid "([^"]+)"\)',block)
    records=pose(uid,(11,10,0));refs=['RENAMED_R'];extras=[]
    for index in range(1,4):
        fp=pcbnew.FOOTPRINT(original);fp.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid4())))
        for item in[*fp.Pads(),*fp.GraphicalItems(),*fp.GetFields()]:item.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid4())))
        ref='RENAMED_INDUCTOR_'+str(index);refs.append(ref);fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(10+5*index,20));board.Add(fp)
        modified=block.replace('RENAMED_R',ref)
        for old in ids:modified=modified.replace(old,str(uuid.uuid4()))
        extras.append(modified)
        records.extend(pose(force._uid(fp),(11+5*index,20,90)))
    root.write_text(text.replace(block,block+'\n'+'\n'.join(extras),1))
    field._save_field_snapshot(board,source)
    real_model=op.full._model
    def model(*args):
        kind,domain,contract=real_model(*args)
        domain['source_refs']=refs if args[2]=='/BETA'else['SOURCE_PEER']
        domain['sink_refs']=refs if args[2]=='/ALPHA'else['SINK_PEER']
        return kind,domain,contract
    monkeypatch.setattr(op.full,'_model',model)
    real_export=op.leaf._export;calls=[]
    def export(*args):calls.append(1);return real_export(*args)
    monkeypatch.setattr(op.leaf,'_export',export)
    q=op.plan(source,records,board_hint=str(root))
    assert len(q['records'])==4 and len(calls)==1
    projected=pcbnew.LoadBoard(str(source));assert len(op.apply(projected,q))==4
    # A late owner mutation refuses before the first earlier owner moves.
    bad=pcbnew.LoadBoard(str(source));bad.FindFootprintByReference(refs[-1]).SetField('MPN','CHANGED')
    before=op.row._source_binding(bad)
    with pytest.raises(ValueError,match='owner_changed'):op.apply(bad,q)
    assert op.row._source_binding(bad)==before


def test_embedded_alias_with_unreviewed_extends_is_not_complete_source_authority(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch,kind='FerriteBead_Small')
    root.write_text(root.read_text().replace('(symbol "fixture:FerriteBead_Small"',
        '(symbol "fixture:FerriteBead_Small" (extends "fixture:UNREVIEWED")',1))
    with pytest.raises(ValueError):op.plan(source,pose(uid),board_hint=str(root))
