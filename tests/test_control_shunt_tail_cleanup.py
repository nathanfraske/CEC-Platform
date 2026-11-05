"""A native dangling warning never supplies EN ownership or cut authority."""
from pathlib import Path
import math
import pcbnew
import pytest
import cec_control_shunt_tail_cleanup as op
import cec_field_coupling as field
from test_control_shunt_placement import fixture as control_fixture


def report(*ids):return dict(violations=[dict(type='track_dangling',items=[dict(uuid=u)])for u in ids])


def case(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,g,root,_=control_fixture(tmp_path,monkeypatch)
    cap=g.GetParentFootprint();signal=cap.FindPadByNumber('1');owner.Move(pcbnew.VECTOR2I_MM(20,20))
    g.SetPosition(pcbnew.VECTOR2I_MM(-.48,0));signal.SetPosition(pcbnew.VECTOR2I_MM(.48,0))
    def track(a,z):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(200000);t.SetNet(signal.GetNet());t.SetLayer(pcbnew.F_Cu);b.Add(t);return t
    tail=track((.48,0),(-3,0));retained=track((-2,0),(-3,0))
    track((-2,0),(20,20)).SetEnd(owner.FindPadByNumber('45').GetPosition())
    # Rigid source transformations preserve the actual source topology.
    angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T)
    for fp in b.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I(0,0),angle)
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    for t in b.GetTracks():
        t.Rotate(pcbnew.VECTOR2I(0,0),angle)
        if back:t.Flip(pcbnew.VECTOR2I(0,0),False)
    source=Path(b.GetFileName());field._save_field_snapshot(b,source)
    prefix=op.force._copy_family(source,tmp_path/'prefix');c=pcbnew.LoadBoard(str(prefix))
    selected=c.FindFootprintByReference(cap.GetReference());selected.Move(pcbnew.VECTOR2I_MM(0,3))
    endpoint=next(t for t in c.GetTracks()if op.force._uid(t)==op.force._uid(retained)).GetStart()
    new=pcbnew.PCB_TRACK(c);new.SetStart(selected.FindPadByNumber('1').GetPosition());new.SetEnd(endpoint)
    new.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);new.SetWidth(200000)
    new.SetNet(selected.FindPadByNumber('1').GetNet());c.Add(new);field._save_field_snapshot(c,prefix)
    return source,prefix,root,op.force._uid(tail),op.force._uid(retained)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_fresh_source_selected_rc_tail_exact_cut_all_rigid_faces(tmp_path,monkeypatch,turn,back):
    source,prefix,root,tail,retained=case(tmp_path,monkeypatch,turn,back)
    raw=[p.read_bytes()for p in(source,prefix)]
    r=op.construct(source,prefix,tmp_path/'cut',board_hint=str(root),original_native=report(),proposed_native=report(tail))
    assert r['ok']and r['complete']and r['changed'],r
    assert r['retired_track_uuids']==[tail]and not r['admitted']
    child=Path(r['candidate']);assert retained in{op.force._uid(t)for t in pcbnew.LoadBoard(str(child)).GetTracks()}
    assert op.receive(source,prefix,child,board_hint=str(root),warning_uuids=[tail])['ok']
    assert raw==[p.read_bytes()for p in(source,prefix)]
    assert r['whole_original_current_debt_field_native_intake_receiving_still_required']


@pytest.mark.parametrize('fault',['owner_move','unknown_part','wrong_net','locked','group','live_bridge','inherited'])
def test_warning_cannot_grant_role_or_retire_loads_protected_copper(tmp_path,monkeypatch,fault):
    source,prefix,root,tail,retained=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(prefix));track=next(t for t in b.GetTracks()if op.force._uid(t)==tail)
    if fault=='owner_move':next(f for f in b.GetFootprints()if f.GetPadCount()>2).Move(pcbnew.VECTOR2I_MM(1,0))
    elif fault=='unknown_part':next(f for f in b.GetFootprints()if f.GetPadCount()==2).SetField('MPN','unknown')
    elif fault=='wrong_net':track.SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='locked':track.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(track)
    elif fault=='live_bridge':tail=next(op.force._uid(t)for t in b.GetTracks()if t.GetLength()>10000000)
    if fault=='wrong_net':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(prefix),b)
    else:field._save_field_snapshot(b,prefix)
    r=op.construct(source,prefix,tmp_path/'refused',board_hint=str(root),
        original_native=report(tail)if fault=='inherited'else report(),proposed_native=report(tail))
    if fault=='inherited':assert r['ok']and not r['changed']and r['candidate']is None
    else:assert not r['ok']and r['errors'],r


@pytest.mark.parametrize('fault',['sidecar','unowned_copper','opaque_field','wrong_cut','source_net'])
def test_independent_saved_receiver_rejects_unowned_transaction(tmp_path,monkeypatch,fault):
    source,prefix,root,tail,retained=case(tmp_path,monkeypatch)
    r=op.construct(source,prefix,tmp_path/'initial',board_hint=str(root),original_native=report(),proposed_native=report(tail))
    assert r['ok'],r
    child=Path(r['candidate'])
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='source_net':root.write_text(root.read_text().replace('100nF','changed'))
    else:
        b=pcbnew.LoadBoard(str(child))
        if fault=='unowned_copper':
            t=next(iter(b.GetTracks()));t.SetWidth(t.GetWidth()+1)
        elif fault=='opaque_field':next(iter(b.GetFootprints())).SetField('opaque','changed')
        else:op.discard_items(b,[t for t in b.GetTracks()if op.force._uid(t)==retained])
        field._save_field_snapshot(b,child)
    proof=op.receive(source,prefix,child,board_hint=str(root),warning_uuids=[tail])
    assert not proof['ok']and proof['errors'],proof


@pytest.mark.parametrize('timeout',[0,11,True,float('nan'),float('inf')])
def test_nonfinite_or_ambiguous_bounds_refuse_without_outputs(tmp_path,timeout):
    r=op.construct(tmp_path/'old',tmp_path/'prefix',tmp_path/'out',board_hint='synthetic',
        original_native=report(),proposed_native=report(),timeout_s=timeout)
    assert not r['ok']and not(tmp_path/'out').exists()


def cycle_case(tmp_path,monkeypatch):
    source,prefix,root,tail,retained=case(tmp_path,monkeypatch)
    first=pcbnew.LoadBoard(str(source));second=pcbnew.LoadBoard(str(prefix));net=first.GetNetcodeFromNetname('arbitrary_control')
    items=[]
    for x in(-3,0):
        via=pcbnew.PCB_VIA(first);via.SetPosition(pcbnew.VECTOR2I_MM(x,0));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(net);first.Add(via);items.append(via)
    t=pcbnew.PCB_TRACK(first);t.SetStart(pcbnew.VECTOR2I_MM(-3,0));t.SetEnd(pcbnew.VECTOR2I_MM(0,0))
    t.SetLayer(pcbnew.B_Cu);t.SetWidth(200000);t.SetNetCode(net);first.Add(t);items.append(t)
    for item in items:
        cloned=item.Duplicate();cloned.m_Uuid.Clone(item.m_Uuid);second.Add(cloned)
    field._save_field_snapshot(first,source);field._save_field_snapshot(second,prefix)
    return source,prefix,root,tail,retained,op.force._uid(t)


def test_source_typed_multilayer_alternative_is_independently_received(tmp_path,monkeypatch):
    source,prefix,root,tail,retained,bridge=cycle_case(tmp_path,monkeypatch)
    r=op.construct(source,prefix,tmp_path/'cycle-cut',board_hint=str(root),original_native=report(),proposed_native=report(tail))
    assert r['ok']and r['complete'],r
    proof=r['source_proof']['source_typed_singleton_cycle_hints']
    assert len(proof)==1 and proof[0]['track_uuid']==tail
    assert proof[0]['full_stack_retained_contacts_joined']and proof[0]['all_surviving_native_partitions_exact']
    # Whole topology closure now also removes the unused B bridge and its
    # two routing ports, not a warning-trading intermediate.
    assert bridge in r['retired_track_uuids']and len(r['retired_via_uuids'])==2
    assert r['source_proof']['compound_source_native_port_closure']['no_native_warning_chasing']


@pytest.mark.parametrize('fault',['sole_bridge','wrongnet','locked','group','wide','partialboard','expired'])
def test_multilayer_fallback_has_no_new_retirement_authority(tmp_path,monkeypatch,fault):
    source,prefix,root,tail,retained,bridge=cycle_case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(prefix));live={op.force._uid(t):t for t in b.GetTracks()};t=live[tail]
    if fault=='sole_bridge':op.discard_items(b,[live[bridge]])
    elif fault=='wrongnet':t.SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='locked':t.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    elif fault=='wide':t.SetWidth(300000)
    elif fault=='partialboard':b.Remove(next(fp for fp in b.GetFootprints()if fp.GetPadCount()>2))
    if fault=='wrongnet':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(prefix),b)
    else:field._save_field_snapshot(b,prefix)
    if fault=='expired':
        with pytest.raises(ValueError,match='deadline'):
            op._singleton_cycle(b,prefix,tail,{'arbitrary_control'},200000,op.time.monotonic()-1)
        return
    r=op.construct(source,prefix,tmp_path/'cycle-refused',board_hint=str(root),original_native=report(),proposed_native=report(tail))
    assert not r['ok']and r['errors'],r


@pytest.mark.parametrize('fault',['lock','group','foreign_face','plane','pad','partialstack','truncated'])
def test_compound_port_geometry_cannot_retire_unowned_port_contacts(tmp_path,monkeypatch,fault):
    source,prefix,root,tail,retained,bridge=cycle_case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(prefix));port=next(v for v in b.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition().x==0)
    if fault=='lock':port.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(port)
    elif fault=='foreign_face':
        t=pcbnew.PCB_TRACK(b);t.SetStart(port.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(0,-2))
        t.SetWidth(200000);t.SetLayer(pcbnew.B_Cu);t.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(t)
    elif fault=='plane':
        zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.B_Cu);zone.SetNet(port.GetNet());poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in((-1,-1),(1,-1),(1,1),(-1,1)):poly.Append(x*1000000,y*1000000)
        zone.Outline().Append(poly);zone.SetFilledPolysList(pcbnew.B_Cu,poly);zone.SetIsFilled(True);b.Add(zone)
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layers)
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(port.GetPosition());pad.SetNet(port.GetNet());fp.Add(pad)
    elif fault=='partialstack':port.SetViaType(pcbnew.VIATYPE_MICROVIA)
    else:
        monkeypatch.setattr(op.tails,'_discover_native_leaf_chains',lambda *a,**k:dict(complete=False,proposed_exact_track_uuids=[],attempts=[]))
    # This targets the physical helper only. The public entry point also
    # rederives canonical source identity and would reject added source pads.
    with pytest.raises(ValueError):
        op._compound_ports(b,prefix,{tail},{'arbitrary_control'},{'arbitrary_control':200000},op.time.monotonic()+10)
