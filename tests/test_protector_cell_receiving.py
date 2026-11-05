"""Native saved-receiver boundaries; no connectivity/verdict replacements.

Unit-level Source packets below exercise independent geometric subproofs,
not manufacturer/hierarchy qualification. Public receiving must still freshly
compile and rejects every unavailable/forged Source before these subproofs.
"""
from pathlib import Path
import json
import copy
import uuid
import hashlib
import time

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_force_current as force
import cec_protector_cell_receiving as op
from test_passive_protector_contract import protector_fixture
from test_native_paired_route_reconstruction import fixture as pair_fixture
from cec_native_items import discard_items


def posed_fixture(tmp_path,turn=0,face=pcbnew.F_Cu):
    b,fp,_,_=protector_fixture(turn,False,face)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    child=pcbnew.LoadBoard(str(source));target=child.FindFootprintByReference(fp.GetReference())
    at=fp.GetPosition();pose=[at.x/1e6+.75,at.y/1e6-.25,(fp.GetOrientationDegrees()+180)%360]
    target.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
    target.SetOrientationDegrees(pose[2])
    q=dict(owner_uuid=force._uid(fp),target_pose=pose)
    return b,child,q


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_only_actual_six_rigid_native_lands_rebind(tmp_path,turn,face):
    parent,child,q=posed_fixture(tmp_path,turn,face)
    before=[op.cell.row._source_binding(b) for b in (parent,child)]
    bindings=op._rebindings(parent,child,q)
    assert len(bindings)==6 and len(set(bindings.values()))==6
    assert before==[op.cell.row._source_binding(b) for b in (parent,child)]


@pytest.mark.parametrize('fault',['position','angle','face','uuid','net','size','number','shape','hole','field'])
def test_physical_pad_or_owner_drift_is_not_a_pose_alias(tmp_path,fault):
    parent,child,q=posed_fixture(tmp_path);fp=next(iter(child.GetFootprints()));p=fp.FindPadByNumber('1')
    if fault=='position':p.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='angle':fp.SetOrientationDegrees(fp.GetOrientationDegrees()+90)
    elif fault=='face':fp.SetLayer(pcbnew.B_Cu)
    elif fault=='uuid':p.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='net':p.SetNet(fp.FindPadByNumber('3').GetNet())
    elif fault=='size':p.SetSize(pcbnew.VECTOR2I(800001,700000))
    elif fault=='number':p.SetNumber('7')
    elif fault=='shape':p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault=='hole':p.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    else:fp.SetField('MPN','another-part')
    with pytest.raises(ValueError):op._rebindings(parent,child,q)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_actual_complete_saved_pair_native_and_physical_contract(tmp_path,rotation):
    source,child,plan=pair_fixture(tmp_path,rotation=rotation)
    board=pcbnew.LoadBoard(str(child))
    q=dict(pair_plan=plan,board_hint='synthetic')
    receipt=op._pair_physical(board,q,child)
    assert receipt['complete'] and receipt['native']['connected']
    assert not receipt['physical']['violations']


@pytest.mark.parametrize('fault',['one_leg','orphan_tail','wrong_width'])
def test_pair_completion_preserves_raw_native_or_contract_refusals(tmp_path,fault):
    source,child,plan=pair_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(child));tracks=[t for t in board.GetTracks() if t.GetNetname()==plan['pair']['n']]
    if fault=='one_leg':discard_items(board,tracks)
    elif fault=='orphan_tail':
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(2,19));t.SetEnd(pcbnew.VECTOR2I_MM(3,19))
        t.SetWidth(250000);t.SetLayer(pcbnew.F_Cu);t.SetNet(board.FindNet(plan['pair']['n']));board.Add(t)
    else:tracks[0].SetWidth(200000)
    op.field._save_field_snapshot(board,child)
    receipt=op._pair_physical(board,dict(pair_plan=plan,board_hint='synthetic'),child)
    assert not receipt['complete']
    assert receipt['native'] and receipt['physical'] is not None


@pytest.mark.parametrize('seconds',[True,0,-1,10.01,float('nan'),float('inf')])
def test_public_receiver_cannot_extend_constituents(seconds):
    with pytest.raises(ValueError,match='bounded_protector_constituent_required'):
        op.receive('/unused','/unused',{},timeout_s=seconds)


@pytest.mark.parametrize('proposal',[None,{},dict(owner_uuid='forged'),[]])
def test_unavailable_forged_source_never_gets_partial_saved_success(tmp_path,proposal):
    source=tmp_path/'first';child=tmp_path/'second';source.write_text('not a board');child.write_text('not a board')
    receipt=op.receive(source,child,proposal)
    assert not receipt['ok'] and not receipt['complete'] and receipt['errors']
    assert receipt['failed_stage']=='source_recompile'
    assert not receipt['routing_admitted'] and not receipt['current_qualified']
    assert not receipt['release_authority'] and not receipt['barrel_ampacity_qualified']


def incoming_fixture(tmp_path):
    b,fp,nets,_=protector_fixture()
    def track(board,net,a,c,width):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*c))
        t.SetWidth(width);t.SetLayer(pcbnew.F_Cu);t.SetNet(board.FindNet(net));board.Add(t);return t
    old=track(b,'/unrelated/data_a',(1,1),(2,1),250000)
    source=tmp_path/'basis.kicad_pcb';pcbnew.SaveBoard(str(source),b);b.SetFileName(str(source));child=pcbnew.LoadBoard(str(source))
    discard_items(child,[next(t for t in child.GetTracks() if force._uid(t)==force._uid(old))])
    for index,net in enumerate(('/unrelated/data_a','/unrelated/data_b','GND','/unrelated/clamp')):
        track(child,net,(1,index+3),(2,index+3),250000 if index<2 else 500000)
    q=dict(retired_track_uuids=[force._uid(old)],retired_via_uuids=[],
        pair_plan=dict(pair=dict(p='/unrelated/data_a',n='/unrelated/data_b',width=.25)),
        clamp_request=dict(net='/unrelated/clamp'))
    return b,child,q,track


def test_saved_incoming_inventory_has_all_three_domains_without_source_mutation(tmp_path):
    parent,child,q,_=incoming_fixture(tmp_path)
    before=[op.cell.row._source_binding(b) for b in (parent,child)]
    retired,incoming,nonpair,items=op._incoming(parent,child,q)
    assert retired==set(q['retired_track_uuids']) and len(incoming)==4 and len(nonpair)==2
    assert {items[u].GetNetname() for u in nonpair}=={'GND','/unrelated/clamp'}
    assert before==[op.cell.row._source_binding(b) for b in (parent,child)]


@pytest.mark.parametrize('fault',['partial_cut','extra_cut','no_p','no_n','no_ground','no_clamp','wrong_width','unrelated_net','arc'])
def test_saved_inventory_cannot_hide_a_partial_domain_or_unrelated_delta(tmp_path,fault):
    parent,child,q,track=incoming_fixture(tmp_path)
    if fault=='partial_cut':
        original=next(iter(parent.GetTracks()));copy=pcbnew.PCB_TRACK(original);child.Add(copy)
    elif fault=='extra_cut':q['retired_track_uuids'].append('not-a-Source-item')
    elif fault.startswith('no_'):
        net={'no_p':'/unrelated/data_a','no_n':'/unrelated/data_b','no_ground':'GND','no_clamp':'/unrelated/clamp'}[fault]
        discard_items(child,[t for t in child.GetTracks() if t.GetNetname()==net])
    elif fault=='wrong_width':next(t for t in child.GetTracks() if t.GetNetname()=='/unrelated/data_a').SetWidth(249999)
    elif fault=='unrelated_net':
        net=pcbnew.NETINFO_ITEM(child,'/foreign');child.Add(net);track(child,'/foreign',(2,20),(4,20),500000)
    else:
        arc=pcbnew.PCB_ARC(child);arc.SetNet(child.FindNet('GND'));arc.SetWidth(500000);child.Add(arc)
    with pytest.raises(ValueError):op._incoming(parent,child,q)


def test_final_identity_work_is_inside_the_same_lease(monkeypatch):
    clock=[0.]
    monkeypatch.setattr(op.cell.time,'monotonic',lambda:clock[0])
    end=op.cell._deadline(10.)
    clock[0]=10.
    with pytest.raises(ValueError,match='protector_constituent_deadline'):op.cell._remaining(end)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_original_islands_follow_only_received_six_pad_rebindings(tmp_path,turn,face):
    parent,child,q=posed_fixture(tmp_path,turn,face)
    old_fp=next(iter(parent.GetFootprints()));new_fp=next(iter(child.GetFootprints()))
    def join(board,a,c):
        t=pcbnew.PCB_TRACK(board);t.SetStart(a.GetPosition());t.SetEnd(c.GetPosition())
        t.SetWidth(250000);t.SetLayer(face);t.SetNet(a.GetNet());board.Add(t);return t
    cut=[]
    for a,c in (('1','6'),('3','4')):
        cut.append(force._uid(join(parent,old_fp.FindPadByNumber(a),old_fp.FindPadByNumber(c))))
        join(child,new_fp.FindPadByNumber(a),new_fp.FindPadByNumber(c))
    proof=op.partitions.compare(parent,child,retired_uuids=cut,
        identity_rebindings=op._rebindings(parent,child,q),timeout_s=10.)
    assert proof['preserved'] and proof['exact_positive_native_island_overlap']
    assert proof['whole_zone_uuid_connectivity_credit'] is False
    # A missing restored physical leg cannot be hidden by the same net names.
    discard_items(child,[next(t for t in child.GetTracks() if t.GetNetname()=='/unrelated/data_a')])
    lost=op.partitions.compare(parent,child,retired_uuids=cut,
        identity_rebindings=op._rebindings(parent,child,q),timeout_s=10.)
    assert not lost['preserved']


@pytest.mark.parametrize('net',['GND','/unrelated/clamp'])
def test_new_nonpair_barrel_cannot_inherit_only_board_minimum_geometry(tmp_path,net):
    parent,child,q,_=incoming_fixture(tmp_path)
    parent.GetDesignSettings().m_ViasMinSize=600000
    via=pcbnew.PCB_VIA(child);via.SetWidth(500000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(18,20));via.SetNet(child.FindNet(net));child.Add(via)
    with pytest.raises(ValueError,match='protector_subfloor_requires_exact_source_six_pad_context'):
        op._incoming(parent,child,q)


@pytest.mark.parametrize('net',['GND','/unrelated/clamp'])
def test_constructor_sized_ordinary_barrel_does_not_inherit_preferred_netclass_size(tmp_path,net):
    parent,child,q,_=incoming_fixture(tmp_path)
    settings=parent.GetDesignSettings();settings.m_ViasMinSize=500000
    settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    via=pcbnew.PCB_VIA(child);via.SetWidth(500000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(18,20));via.SetNet(child.FindNet(net));child.Add(via)
    proof=op._barrel_process(parent,child,q,via)
    assert proof['basis']=='unchanged_original_ordinary_process_floors'
    assert proof['diameter_nm']==500000 and proof['drill_nm']==300000
    assert not proof['current_capacity_inferred']


@pytest.mark.parametrize('diameter,drill',[(500000,400000),(499999,300000),(500000,299999)])
def test_actual_drill_and_ring_are_recomputed_before_any_local_rule(tmp_path,diameter,drill):
    parent,child,q,_=incoming_fixture(tmp_path)
    settings=parent.GetDesignSettings();settings.m_ViasMinSize=500000
    settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    via=pcbnew.PCB_VIA(child);via.SetWidth(diameter);via.SetDrill(drill)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(18,20));via.SetNet(child.FindNet('GND'));child.Add(via)
    with pytest.raises(ValueError,match='protector_subfloor_requires_exact_source_six_pad_context'):
        op._barrel_process(parent,child,q,via)


def test_typed_adapter_delegates_exact_original_phase_paths_only(tmp_path,monkeypatch):
    import root_complete_protector_phase_20261026 as phase
    source=tmp_path/'source';child=tmp_path/'child';source.write_text('source');child.write_text('child')
    proposal=tmp_path/'q.json';q=dict(source=str(source),source_sha256=force._hash(source),board_hint='arbitrary')
    proposal.write_text(json.dumps(q));calls=[]
    # Adapter wiring only: this spy is deliberately NOT an electrical/native
    # success fixture and never enters any public Source receiving tests.
    monkeypatch.setattr(phase.protector,'receive',lambda *a,**k:calls.append((a,k)) or {'delegated':True})
    row=dict(kind=phase.KIND,candidate=str(child),candidate_sha256=force._hash(child),proposal=str(proposal))
    assert phase.receive_phase(source,source,row,'arbitrary')=={'delegated':True}
    assert calls==[((source,child,q),{'timeout_s':10.})]


@pytest.mark.parametrize('fault',['unknown_kind','extra_budget','wrong_hash','wrong_hint','wrong_source','same_path'])
def test_typed_adapter_rejects_unowned_options_or_stale_saved_identity_before_receiver(tmp_path,monkeypatch,fault):
    import root_complete_protector_phase_20261026 as phase
    source=tmp_path/'source';child=tmp_path/'child';source.write_text('source');child.write_text('child')
    proposal=tmp_path/'q.json';q=dict(source=str(source),source_sha256=force._hash(source),board_hint='arbitrary')
    row=dict(kind=phase.KIND,candidate=str(child),candidate_sha256=force._hash(child),proposal=str(proposal))
    if fault=='unknown_kind':row['kind']='ordinary_join'
    elif fault=='extra_budget':row['current_amps']=100
    elif fault=='wrong_hash':row['candidate_sha256']='stale'
    elif fault=='wrong_hint':q['board_hint']='other'
    elif fault=='wrong_source':q['source_sha256']='stale'
    else:row.update(candidate=str(source),candidate_sha256=force._hash(source))
    proposal.write_text(json.dumps(q))
    def forbidden(*a,**k):raise AssertionError('unowned adapter inputs reached receiver')
    monkeypatch.setattr(phase.protector,'receive',forbidden)
    with pytest.raises(ValueError):phase.receive_phase(source,source,row,'arbitrary')


def local_process_fixture(tmp_path,turn=0,face=pcbnew.F_Cu):
    import cec_fr as fr
    parent,fp,_,_=protector_fixture(turn,False,face)
    props=parent.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';parent.SetProperties(props)
    # A real saved process seed, separate from the six-pin owner. It never
    # transfers ownership to an arbitrary new land.
    seedfp=pcbnew.FOOTPRINT(parent);seedfp.SetReference('unrelated_process_seed');parent.Add(seedfp)
    pad=pcbnew.PAD(seedfp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    pad.SetNet(parent.FindNet('GND'));pad.SetPosition(pcbnew.VECTOR2I_MM(27,27));seedfp.Add(pad)
    seed=pcbnew.PCB_VIA(parent);seed.SetViaType(pcbnew.VIATYPE_THROUGH)
    seed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);seed.SetPosition(pad.GetPosition())
    seed.SetWidth(300000);seed.SetDrill(200000);seed.SetNet(pad.GetNet());parent.Add(seed)
    evidence=fr.group_local_pofv_signal_vias(parent,[seed]);assert evidence
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    op.field._save_field_snapshot(parent,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)]},
        'board':{'design_settings':{'rules':dict(min_via_diameter=.5,
            min_through_hole_diameter=.3,min_via_annular_width=.1)}}}))
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    parent=pcbnew.LoadBoard(str(source));child_path=force._copy_family(source,tmp_path/'child')
    child=pcbnew.LoadBoard(str(child_path));target=child.FindFootprintByReference(fp.GetReference())
    at=target.GetPosition();pose=[at.x/1e6+.75,at.y/1e6-.25,(target.GetOrientationDegrees()+180)%360]
    target.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])));target.SetOrientationDegrees(pose[2])
    ground=target.FindPadByNumber('2')
    via=pcbnew.PCB_VIA(child);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(ground.GetPosition())
    via.SetWidth(350000);via.SetDrill(250000);via.SetNet(ground.GetNet());child.Add(via)
    group=next(g for g in child.Groups()if g.GetName()==op.local_rule.GROUP);group.AddItem(via)
    q=dict(source=str(source),owner_uuid=force._uid(fp),owner_ref=fp.GetReference(),target_pose=pose)
    return parent,child,q,via,source,child_path


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_subfloor_rule_is_rederived_on_all_six_rigid_source_lands(tmp_path,turn,face):
    parent,child,q,via,source,path=local_process_fixture(tmp_path,turn,face)
    before=source.read_bytes();binding=op.cell.row._source_binding(child)
    receipt=op._barrel_process(parent,child,q,via)
    assert receipt['basis']=='exact_original_local_rule_on_source_rigid_six_pad_projection'
    assert receipt['owner_pad_uuid']==force._uid(child.FindFootprintByReference(q['owner_ref']).FindPadByNumber('2'))
    assert receipt['source_rule']['source_sha256']==force._hash(source)
    assert not receipt['current_capacity_inferred'] and not receipt['release_authority']
    assert source.read_bytes()==before and op.cell.row._source_binding(child)==binding


@pytest.mark.parametrize('fault',['below_ring','below_drill','unowned_seed','offpad','partial_overlap',
    'group_missing','group_identity','retained_member_missing','rule_changed','source_rule_missing','sixth_pad_drift','blind'])
def test_small_local_barrels_need_original_rule_group_and_exact_owned_pad(tmp_path,fault):
    parent,child,q,via,source,path=local_process_fixture(tmp_path)
    if fault=='below_ring':via.SetWidth(349999)
    elif fault=='below_drill':via.SetDrill(199999)
    elif fault=='unowned_seed':via.SetPosition(pcbnew.VECTOR2I_MM(27,27))
    elif fault in ('offpad','partial_overlap'):via.Move(pcbnew.VECTOR2I(800000 if fault=='offpad' else 300000,0))
    elif fault=='group_missing':next(g for g in child.Groups()if g.GetName()==op.local_rule.GROUP).RemoveItem(via)
    elif fault=='group_identity':next(g for g in child.Groups()if g.GetName()==op.local_rule.GROUP).m_Uuid.Clone(pcbnew.KIID())
    elif fault=='retained_member_missing':
        group=next(g for g in child.Groups()if g.GetName()==op.local_rule.GROUP)
        group.RemoveItem(next(i for i in group.GetItems()if force._uid(i)!=force._uid(via)))
    elif fault=='rule_changed':path.with_suffix('.kicad_dru').write_text(source.with_suffix('.kicad_dru').read_text()+'\n# changed\n')
    elif fault=='source_rule_missing':source.with_suffix('.kicad_dru').unlink()
    elif fault=='sixth_pad_drift':child.FindFootprintByReference(q['owner_ref']).FindPadByNumber('6').Move(pcbnew.VECTOR2I(1,0))
    else:via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    with pytest.raises(ValueError):op._barrel_process(parent,child,q,via)


@pytest.mark.parametrize('key,value',[('min_via_diameter',.7),('min_through_hole_diameter',.4),('min_via_annular_width',.2)])
def test_literal_project_floor_cannot_be_lost_to_stale_native_settings(tmp_path,key,value):
    parent,child,q,via,source,path=local_process_fixture(tmp_path)
    settings=json.loads(source.with_suffix('.kicad_pro').read_text())
    settings['board']['design_settings']['rules'][key]=value
    source.with_suffix('.kicad_pro').write_text(json.dumps(settings))
    limits=op._ordinary_source_limits(parent)
    mapped={'min_via_diameter':'via_diameter','min_through_hole_diameter':'via_drill','min_via_annular_width':'annular'}
    assert limits[mapped[key]]>=value


def complete_saved_fixture(tmp_path,monkeypatch):
    """Real canonical parser/native CAD; only export/current catalogs synthetic.

    The deliberately explicit TEST authority is not a protector load budget.
    No compiler, connectivity, route, saved receiver or verdict is patched.
    """
    import cec_fr as fr
    import cec_synth_pipeline as synth
    import cec_current_topology as topology
    import cec_source_ground_leaf as source_pin
    import cec_fab_profile as fab
    b,fp,nets,_=protector_fixture()
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    oldnames={'/unrelated/data_a':'/renamed/USB_D_P','/unrelated/data_b':'/renamed/USB_D_N',
        '/unrelated/clamp':'/renamed/supply'}
    for old,new in oldnames.items():
        net=pcbnew.NETINFO_ITEM(b,new);b.Add(net)
        for pad in fp.Pads():
            if pad.GetNetname()==old:pad.SetNet(net)
    pn,nn,rail=[oldnames[k] for k in ('/unrelated/data_a','/unrelated/data_b','/unrelated/clamp')]
    def onepad(ref,net,xy):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue('fixture');f.SetField('MPN','fixture-part')
        f.SetFPID(pcbnew.LIB_ID('fixture','Terminal'));f.SetPosition(pcbnew.VECTOR2I_MM(*xy));b.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);p.SetPosition(f.GetPosition())
        p.SetNet(b.FindNet(net));f.Add(p);return f,p
    terminals=[]
    for ref,net,xy in [('leftP',pn,(2,14.05)),('leftN',nn,(2,15.95)),
            ('rightP',pn,(70,14.05)),('rightN',nn,(70,15.95)),
            ('SRC',rail,(20,20)),('SINK',rail,(21.5,20))]:
        terminals.append(onepad(ref,net,xy))
    def track(board,net,a,c,width=.5,face=pcbnew.F_Cu):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*c))
        t.SetWidth(round(width*1e6));t.SetLayer(face);t.SetNet(board.FindNet(net));board.Add(t);return t
    def via(board,net,xy,diameter=.5,drill=.3):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(*xy));v.SetWidth(round(diameter*1e6))
        v.SetDrill(round(drill*1e6));v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(board.FindNet(net));board.Add(v);return v
    # An intentionally incomplete old pair is legitimate complete-pair work.
    track(b,pn,(2,14.05),(2.2,14.05),.2)
    track(b,'GND',(10.9,12),(8.5,12));via(b,'GND',(8.5,12),.9,.5)
    track(b,rail,(20,20),(21.5,20))
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(b.FindNet('GND'))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER);z.SetMinThickness(100000);z.SetLocalClearance(200000)
        z.Outline().NewOutline()
        for x,y in ((.5,.5),(74,.5),(74,29.5),(.5,29.5)):z.Outline().Append(round(x*1e6),round(y*1e6))
        b.Add(z)
    for a,c in [((0,0),(75,0)),((75,0),(75,30)),((75,30),(0,30)),((0,30),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*c));edge.SetWidth(50000);b.Add(edge)
    court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT);court.SetLayer(pcbnew.F_CrtYd)
    court.SetStart(pcbnew.VECTOR2I_MM(10.3,10.5));court.SetEnd(pcbnew.VECTOR2I_MM(13.7,13.5));court.SetWidth(50000);fp.Add(court)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    project={'net_settings':{'classes':[
        dict(name='Default',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5),
        dict(name='USB',track_width=.2,diff_pair_width=.2,diff_pair_gap=.2,clearance=.2,via_diameter=.6,via_drill=.3)],
        'netclass_patterns':[dict(pattern=pn,netclass='USB'),dict(pattern=nn,netclass='USB')]},
        'board':{'design_settings':{'rules':dict(min_via_diameter=.5,min_through_hole_diameter=.3,
            min_via_annular_width=.1,min_clearance=.2,min_hole_to_hole=.25)}}}
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    # Canonical embedded manufacturer source, complete exported actual peers.
    root=source.with_suffix('.kicad_sch');libs=[];symbols=[];comps=[];libparts=[];netnodes={}
    manufacturer=op.cell.roles.passive_steering_protector_contract(fp)
    for index,f in enumerate(b.GetFootprints()):
        lib='fixture:Part'+str(index);uid=str(uuid.uuid4());pins=[];ref=f.GetReference()
        properties=[('Reference',ref),('Value',f.GetValue()),('Footprint',f.GetFPIDAsString()),
            ('MPN',f.GetField('MPN').GetText())]
        if ref==fp.GetReference():properties.extend([('Manufacturer','UMW'),('LCSC','C2687116')])
        for number,pad in enumerate(f.Pads()):
            pin=pad.GetNumber();function=manufacturer['source_pin_functions'][pin]if ref==fp.GetReference()else'PIN'+pin
            pins.append('(pin passive line (at '+str(number*2)+' 0 0) (length 1) (name "'+function+'") (number "'+pin+'"))')
            netnodes.setdefault(pad.GetNetname(),[]).append((ref,pin))
        libs.append('(symbol "'+lib+'" (symbol "unit_1_1" '+' '.join(pins)+'))')
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 10 0) (unit 1) (uuid "'+uid+'") '+
            ' '.join('(property "'+k+'" "'+v+'")'for k,v in properties)+')')
        comps.append('(comp (ref "'+ref+'") (value "'+f.GetValue()+'") (footprint "'+f.GetFPIDAsString()+'") '+
            ' '.join('(property (name "'+k+'") (value "'+v+'"))'for k,v in properties if k not in ('Reference','Value','Footprint'))+
            ' (libsource (lib "fixture") (part "Part'+str(index)+'")) (tstamps "'+uid+'"))')
        # Real KiCad exports carry this exact selected symbol pin inventory.
        # Keep synthetic Source ownership complete, not a parser waiver.
        libparts.append('(libpart (lib "fixture") (part "Part'+str(index)+'") (pins '+
            ' '.join('(pin (num "'+pad.GetNumber()+'"))'for pad in f.Pads())+'))')
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+
        ' '.join(libs)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(comps)+') (libparts '+' '.join(libparts)+') (nets '+
        ' '.join('(net (name "'+net+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'"))'for ref,pin in rows)+')'
            for net,rows in netnodes.items())+'))')
    def export(path,deadline):
        return copy.deepcopy(tree),dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            exporter='/synthetic-canonical-export',exporter_sha256='a'*64)
    monkeypatch.setattr(source_pin,'_export',export)
    authority=dict(amps=.75,geometry_margin=1.25,margin_included=False,source='board_design_basis')
    profile='jlcpcb_6l_pofv_high_current'
    required=op.dimensions.current_trace_widths(authority,tuple(fab.enabled_copper_layers(b)),profile,rise_c=30.)
    contract=dict(net=rail,current_authority=authority,required_by_layer_mm=required,
        routing_layers=['F.Cu','In2.Cu','B.Cu'])
    domain=dict(net=rail,complete=True,source_refs=['SRC'],sink_refs=['SINK'],missing_refs=[],amps=.75)
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:{rail:copy.deepcopy(domain)})
    monkeypatch.setattr(topology,'route_width_contracts',lambda *a,**k:{rail:copy.deepcopy(contract)})
    old_current=topology.current_contract_for_net
    monkeypatch.setattr(topology,'current_contract_for_net',lambda net,*a,**k:
        copy.deepcopy(authority)if net==rail else old_current(net,*a,**k))
    additive=op.additive
    additive._ground_refill(b);op.field._save_field_snapshot(b,source)
    pair_name=next(row['name'] for row in op.precision.derive_coupled_pairs(str(source),board=b) if row['p']==pn)
    _,q=op.cell.compile(source,owner_uuid=force._uid(fp),board_hint=str(root),pair_name=pair_name,
        target_pose=[12.,15.,0.],timeout_s=10.)
    child,_=op.cell._project(b,q,q['target_pose'],q['max_shift_mm'])
    # Symmetric native 45-degree fanouts and long nominal-pitch trunks.
    pp=[(2,14.05),(2.75,14.8),(10.15,14.8),(10.9,14.05),(11.65,14.8),
        (12.35,14.8),(13.1,14.05),(13.85,14.8),(69.25,14.8),(70,14.05)]
    np=[(x,30-y)for x,y in pp]
    for net,points in ((pn,pp),(nn,np)):
        for a,c in zip(points,points[1:]):track(child,net,a,c,.2).SetLocked(True)
    via(child,'GND',(10.9,15))
    via(child,rail,(13.1,15));via(child,rail,(20,20))
    track(child,rail,(13.1,15),(20,15),face=pcbnew.B_Cu)
    track(child,rail,(20,15),(20,20),face=pcbnew.B_Cu)
    additive._ground_refill(child)
    candidate=force._copy_family(source,tmp_path/'child')
    op.field._save_field_snapshot(child,candidate)
    import cec_source_literal_footprint_retention as retain
    import cec_source_retaining_ses_import as text
    text.write_raw(candidate,retain.retain(text.raw_text(source),text.raw_text(candidate),[q['owner_uuid']]))
    return source,candidate,q,contract


def test_complete_saved_pair_ground_and_clamp_use_actual_process_not_preferences(tmp_path,monkeypatch):
    source,child,q,contract=complete_saved_fixture(tmp_path,monkeypatch)
    before=[source.read_bytes(),child.read_bytes()]
    receipt=op.receive(source,child,q,timeout_s=10.)
    assert receipt['ok'] and receipt['complete'],(receipt.get('failed_stage'),receipt['errors'])
    assert receipt['all_six_physical_lands_received'] and receipt['all_original_native_partitions_preserved']
    assert not receipt['barrel_ampacity_qualified'] and not receipt['release_authority']
    assert before==[source.read_bytes(),child.read_bytes()]


@pytest.mark.parametrize('fault',['below_floor','larger_drill_ring','weak_clamp','missing_ground','changed_group'])
def test_complete_saved_receiver_refuses_process_and_mandatory_domain_damage(tmp_path,monkeypatch,fault):
    source,path,q,_=complete_saved_fixture(tmp_path,monkeypatch)
    child=pcbnew.LoadBoard(str(path));rail=q['clamp_request']['net']
    clamp_via=next(t for t in child.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetNetname()==rail)
    if fault=='below_floor':clamp_via.SetWidth(499999)
    elif fault=='larger_drill_ring':clamp_via.SetDrill(400000)
    elif fault=='weak_clamp':
        next(t for t in child.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()==rail
            and t.GetLayer()==pcbnew.B_Cu).SetWidth(499999)
    elif fault=='missing_ground':
        import cec_native_items as items
        items.discard_items(child,[t for t in child.GetTracks()if t.GetClass()=='PCB_VIA'
            and t.GetNetname()=='GND'and t.GetWidth()==500000])
    else:
        group=pcbnew.PCB_GROUP(child);group.SetName('unrelated-new-group');child.Add(group);group.AddItem(clamp_via)
    op.field._save_field_snapshot(child,path)
    receipt=op.receive(source,path,q,timeout_s=10.)
    assert not receipt['ok'] and not receipt['complete'],receipt.get('stages')
