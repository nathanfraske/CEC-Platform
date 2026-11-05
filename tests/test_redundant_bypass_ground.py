"""A redundant bypass departure is a typed, saved, non-regressing cut."""
from unittest import mock

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_redundant_bypass_ground as repair
import cec_source_cut_chain as chain
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, rotation=0, prefix='', back=False, cap_via=True):
    board = _board([], edge=(0,0,30,30)); board.SetCopperLayerCount(6)
    nets = {}
    for name in ('GND','+3V3'):
        n=pcbnew.NETINFO_ITEM(board,name); board.Add(n); nets[name]=n
    for ref,value,x in (('IC'+prefix,'INA238AIDGST',10),('C'+prefix,'100nF',12)):
        fp=pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,10.5))
        if value=='100nF':fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
        for pin,net,y in (('6' if value.startswith('INA') else '1','+3V3',10),
                          ('7' if value.startswith('INA') else '2','GND',11)):
            p=pcbnew.PAD(fp); p.SetNumber(pin); p.SetNet(nets[net]); p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8)); p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); layers=pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            p.SetLayerSet(layers); fp.Add(p)
        board.Add(fp)
    selected=track(board,'GND',(12,11),(10,11))
    for a,b in (((12,11),(12,13)),((12,13),(10,13)),((10,13),(10,11))):track(board,'GND',a,b)
    track(board,'+3V3',(10,10),(12,10))
    for x in ((10,12) if cap_via else (10,)):
        v=pcbnew.PCB_VIA(board); v.SetPosition(pcbnew.VECTOR2I_MM(x,11)); v.SetNet(nets['GND'])
        v.SetWidth(600000); v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetViaType(pcbnew.VIATYPE_THROUGH); board.Add(v)
    cap=board.FindFootprintByReference('C'+prefix); pad=cap.FindPadByNumber('2')
    if back:
        for fp in board.GetFootprints():fp.Flip(fp.GetPosition(),False)
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    if rotation:
        at=pcbnew.VECTOR2I_MM(15,15); a=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(at,a)
    source=tmp_path/'source.kicad_pcb'; field._save_field_snapshot(board,source)
    p=repair.plan(pcbnew.LoadBoard(str(source)),force._uid(pad),force._uid(selected))
    target=force._copy_family(source,tmp_path/'cut'); b=pcbnew.LoadBoard(str(target)); repair.subtract(b,p)
    field._save_field_snapshot(b,target)
    return source,target,force._uid(pad),force._uid(selected),p


@pytest.mark.parametrize('rotation,prefix,back',[(0,'A',False),(90,'Other',False),
    (180,'Renamed',False),(270,'Last',False),(0,'Bottom',True)])
def test_typed_saved_removal_preserves_all_surviving_native_partitions_and_returns(tmp_path,rotation,prefix,back):
    source,target,pad,edge,_=fixture(tmp_path,rotation,prefix,back)
    before=source.read_bytes()
    proof=repair.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_partitions_and_proved_short_returns_preserved']
    assert proof['retired_track_uuids']==[edge] and not proof['added_native_uuids']
    assert not proof['current_authority'] and not proof['release_authority']
    assert not proof['independently_measured_local_PI_progress'] and source.read_bytes()==before
    assert not additive.receive(source,target)['ok']


def test_native_connectivity_is_not_enough_if_capacitor_short_return_worsens(tmp_path):
    source,target,pad,edge,_=fixture(tmp_path,cap_via=False)
    result=repair.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert not result['ok'] and 'short_ground_return_worsened' in result['errors'][0],result


@pytest.mark.parametrize('fault',['owner','cap_value','cap_dnp','cap_net','width','group','sole_edge','stale'])
def test_proposal_does_not_grant_arbitrary_mesh_or_bulk_ripup(tmp_path,fault):
    source,_target,pad,edge,proposal=fixture(tmp_path); b=pcbnew.LoadBoard(str(source))
    cap=b.FindFootprintByReference('C'); t=next(t for t in b.GetTracks() if force._uid(t)==edge)
    if fault=='owner':b.FindFootprintByReference('IC').SetValue('UNKNOWN')
    elif fault=='cap_value':cap.SetValue('1000uF')
    elif fault=='cap_dnp':cap.SetDNP(True)
    elif fault=='cap_net':cap.FindPadByNumber('1').SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='width':t.SetWidth(400000)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b); g.SetName('retained'); b.Add(g); g.AddItem(t)
    elif fault=='sole_edge':
        from cec_native_items import discard_items
        discard_items(b,[x for x in b.GetTracks() if x.GetClass()=='PCB_TRACK'
            and x.GetNetname()=='GND' and force._uid(x)!=edge])
    else:
        t.SetWidth(250000)
        with pytest.raises(ValueError,match='source_binding_changed'):repair.subtract(b,proposal)
        return
    with pytest.raises(ValueError):repair.plan(b,pad,edge)


@pytest.mark.parametrize('fault',['pose','width','via','added','second_cut','outline','project'])
def test_receiver_refuses_unowned_edits_and_additional_removals(tmp_path,fault):
    source,target,pad,edge,_=fixture(tmp_path); b=pcbnew.LoadBoard(str(target))
    if fault=='pose':b.FindFootprintByReference('C').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(300000)
    elif fault=='via':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(700000)
    elif fault=='added':track(b,'GND',(10,11),(11,11))
    elif fault=='second_cut':
        from cec_native_items import discard_items
        discard_items(b,[next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')])
    elif fault=='outline':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I_MM(.1,0))
    else:target.with_suffix('.kicad_pro').write_text('{}')
    field._save_field_snapshot(b,target)
    result=repair.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert not result['ok'] and not result['complete'] and result['errors'],result


def test_exact_locked_source_edge_is_typed_not_a_blanket_locked_ripup_allowlist(tmp_path):
    source,target,pad,edge,_=fixture(tmp_path); b=pcbnew.LoadBoard(str(source))
    next(t for t in b.GetTracks() if force._uid(t)==edge).SetLocked(True)
    field._save_field_snapshot(b,source)
    result=repair.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert result['ok'] and result['source_proposal']['source_locked'],result


def test_unbranched_source_tail_is_derived_not_left_as_a_dead_end_or_caller_allowlist(tmp_path):
    source,_target,pad,edge,_=fixture(tmp_path); b=pcbnew.LoadBoard(str(source))
    t=next(t for t in b.GetTracks() if force._uid(t)==edge)
    t.SetEnd(pcbnew.VECTOR2I_MM(11,11)); tail=track(b,'GND',(11,11),(10,11))
    field._save_field_snapshot(b,source)
    p=repair.plan(pcbnew.LoadBoard(str(source)),pad,edge)
    assert p['retired_track_uuids']==[edge,force._uid(tail)]
    target=force._copy_family(source,tmp_path/'trimmed'); c=pcbnew.LoadBoard(str(target))
    repair.subtract(c,p); field._save_field_snapshot(c,target)
    result=repair.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert result['ok'] and result['retired_track_uuids']==p['retired_track_uuids'],result


def test_chain_requires_reconstruction_not_removal_alone_and_binds_repair_policy(tmp_path):
    source,target,pad,edge,_=fixture(tmp_path)
    row=dict(kind='redundant_bypass_ground',candidate=str(target),pad_uuid=pad,track_uuid=edge)
    assert not chain.receive(source,target,board_hint='synthetic',phases=[row])['ok']
    final=force._copy_family(target,tmp_path/'routed'); b=pcbnew.LoadBoard(str(final))
    track(b,'+3V3',(10,10),(11,10)); field._save_field_snapshot(b,final)
    phases=[row,dict(kind='additive',candidate=str(final))]
    result=chain.receive(source,final,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert result['ok'] and result['full_phase_lineage_received'],result
    with mock.patch.object(repair,'receive',return_value=dict(ok=False,complete=False,errors=['policy changed'])):
        stale=chain.receive(source,final,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert not stale['ok'] and stale['errors'],stale


@pytest.mark.parametrize('value',[True,0,11,float('nan'),float('inf'),'10'])
def test_inventory_requires_a_finite_typed_work_lease(tmp_path,value):
    source,_target,pad,edge,_=fixture(tmp_path)
    with pytest.raises(ValueError):repair.plan(pcbnew.LoadBoard(str(source)),pad,edge,timeout_s=value)
