"""Unassigned mechanical pads never acquire a net through library repair."""
import json
import time

import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_source_mount_stitch_reconcile as op
import cec_unassigned_mount_isolation as isolation
import test_source_mount_stitch_reconcile as grounded


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False):
    monkeypatch.setattr(grounded,'ITEM','MountingHole_2.2mm_M2_Pad_Via')
    source,uid,vendor=grounded.fixture(tmp_path,quarter=quarter,back=back)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    for pad in fp.Pads():pad.SetNetCode(0)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),board)
    return source,uid,vendor,str(source.parent)


def ground_net(board):
    # SaveBoard correctly drops the original now-unused Ground net. Negative
    # mutations must create a REAL assigned net instead of SetNet(None), which
    # silently leaves the unassigned pad unchanged.
    net=board.FindNet('GND')
    if net is None:
        net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    return net


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_canonical_unassigned_repair_preserves_no_net_and_all_source_properties(tmp_path,monkeypatch,quarter,back):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    before=source.read_bytes()
    with pytest.raises(ValueError,match='existing_ground'):
        op.plan(source,board_hint=hint,mount_uuids=[uid])
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    assert proposal['changed_pad_count']==8 and proposal['terminal_mode']==isolation.MODE
    assert proposal['rows'][0]['unassigned_isolation']['net0_not_used_as_a_shared_net']
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    received=op.receive(source,child,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    assert received['ok']and received['complete'],received
    physical=op.receive_physical(source,child,proposal)
    assert physical['ok']and physical['complete']and len(physical['unassigned_isolation_reports'])==2
    saved=pcbnew.LoadBoard(str(child));owner=next(iter(saved.GetFootprints()))
    assert owner.IsLocked()and all(p.GetNetCode()==0 and not p.GetNetname()for p in owner.Pads())
    assert source.read_bytes()==before and not physical['current_qualified']


@pytest.mark.parametrize('declaration',[
    {'mount_net':'GND'},{'mount_contact_diameter_mm':4.4},{'mount_contact':True},
    {'mount_function':'grounding'},{'mount_electrical_role':'chassis'},
    {'mount_electrical_unknown':None},{'source_sync_extra_pad_nets':{'ARBITRARY7.1':'GND'}},
    {'source_sync_extra_pad_nets':None},{'mount_net':False}])
@pytest.mark.parametrize('where',['policy','manifest'])
def test_electrical_or_ambiguous_policy_cannot_be_overridden_by_mode(tmp_path,monkeypatch,declaration,where):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    if where=='manifest':(tmp_path/'board-manifest.json').write_text(json.dumps({'placement_directives':declaration}))
    else:
        import cec_board_policy as policy
        (tmp_path/policy.POLICY_FILENAME).write_text(json.dumps(
            dict(schema=policy.SCHEMA,board=tmp_path.name,params=declaration)))
    with pytest.raises(ValueError):op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)


@pytest.mark.parametrize('bad',['null','[]','{"placement_directives":null}',
    '{"placement_directives":{},"placement_directives":{}}'])
def test_manifest_parse_failure_is_not_absence_of_authority(tmp_path,monkeypatch,bad):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    (tmp_path/'board-manifest.json').write_text(bad)
    with pytest.raises(ValueError):op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)


@pytest.mark.parametrize('bad',['null','[]','{"schema":1,"board":"OTHER","params":{}}',
    '{"schema":1,"board":"OTHER","params":{},"params":{}}'])
def test_local_policy_outside_repository_is_still_strict_authority(tmp_path,monkeypatch,bad):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    (tmp_path/'pipeline-policy.json').write_text(bad)
    with pytest.raises(ValueError):op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)


@pytest.mark.parametrize('net',['GND',''])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.In3_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('kind',['track','pad','filled_zone','copper_graphic'])
def test_native_isolation_checks_all_actual_faces_and_foreign_net_zero_too(tmp_path,monkeypatch,net,face,kind):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));owner=next(iter(b.GetFootprints()));at=owner.GetPosition()
    if net:ground_net(b)
    if kind=='track':
        item=pcbnew.PCB_TRACK(b);item.SetLayer(face);item.SetWidth(200000)
        item.SetStart(at);item.SetEnd(at+pcbnew.VECTOR2I_MM(3,0));item.SetNetCode(b.GetNetcodeFromNetname(net)if net else 0);b.Add(item)
    elif kind=='pad':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('FOREIGN0');b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetNumber('1')
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(at)
        pad.SetNetCode(b.GetNetcodeFromNetname(net)if net else 0);fp.Add(pad)
    elif kind=='copper_graphic':
        item=pcbnew.PCB_SHAPE(b);item.SetLayer(face);item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(at);item.SetEnd(at+pcbnew.VECTOR2I_MM(3,0));item.SetWidth(200000);b.Add(item)
    else:
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNetCode(b.GetNetcodeFromNetname(net)if net else 0)
        poly=pcbnew.SHAPE_POLY_SET();idx=poly.NewOutline()
        for x,y in((-1,-1),(1,-1),(1,1),(-1,1)):
            poly.Outline(idx).Append(at.x+round(x*1e6),at.y+round(y*1e6))
        z.Outline().Append(poly);z.SetFilledPolysList(face,poly);z.SetIsFilled(True);b.Add(z)
    # Direct native guard is intentional: SaveBoard may discard net-zero
    # synthetic zone fill caches, which must never become a false positive.
    main,sat=op._inventory(owner)
    with pytest.raises(ValueError):isolation.isolated(b,owner,main,list(sat.values()),deadline=time.monotonic()+2.)


@pytest.mark.parametrize('which',['manifest','code'])
def test_fresh_receiver_binds_manifest_absence_and_code_not_caller_booleans(tmp_path,monkeypatch,which):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    if which=='manifest':(tmp_path/'board-manifest.json').write_text('{"placement_directives":{}}')
    else:
        actual=force._code_identity()
        monkeypatch.setattr(force,'_code_identity',lambda:dict(actual,unowned_epoch='changed'))
    with pytest.raises(ValueError):op._fresh(proposal)


@pytest.mark.parametrize('fault',['mixed_net','layers','main_bore','group','pad_lock'])
def test_mode_never_retypes_or_discards_a_source_geometry_restriction(tmp_path,monkeypatch,fault):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));main,sat=op._inventory(fp);p=next(iter(sat.values()))
    if fault=='mixed_net':p.SetNet(ground_net(b))
    elif fault=='layers':p.SetLayerSet(pcbnew.PAD.SMDMask())
    elif fault=='main_bore':main.SetDrillSize(pcbnew.VECTOR2I_MM(2.1,2.1))
    elif fault=='pad_lock':pass
    else:
        group=pcbnew.PCB_GROUP(b);group.SetName('unowned');b.Add(group);group.AddItem(fp)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    if fault=='pad_lock':
        # This KiCad version does not serialize PAD.SetLocked separately from
        # the footprint lock. Exercise an explicit accepted literal pad flag;
        # it must not disappear merely because the native writer omits it.
        import cec_additive_route_receiving as literal
        root,nodes=literal._nodes(source)
        pad=next(n for n in nodes[uid][1:]if isinstance(n,list)and n and n[0]=='pad'
            and op._uuid(n)==force._uid(p))
        pad.append(['locked','yes']);source.write_text(literal._render(root))
    with pytest.raises(ValueError):op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)


def test_named_mechanical_field_receiver_preserves_explicit_unassigned_mode(tmp_path,monkeypatch):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    proof=field.assess_native_mechanical_mount(source,child,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    assert proof['ok']and proof['complete'],proof
    assert proof['source_delta_receiving']['physical_receiving']['unassigned_isolation_reports']
    assert not proof['release_authority']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.In3_Cu,pcbnew.B_Cu])
def test_real_saved_zone_hole_is_not_a_solid_envelope_obstruction(tmp_path,monkeypatch,face):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));owner=next(iter(b.GetFootprints()));at=owner.GetPosition()
    net=ground_net(b)
    poly=pcbnew.SHAPE_POLY_SET();idx=poly.NewOutline()
    for x,y in((0,0),(40,0),(40,40),(0,40)):poly.Outline(idx).Append(round(x*1e6),round(y*1e6))
    hole=poly.NewHole(idx)
    for x,y in((-4,-4),(-4,4),(4,4),(4,-4)):
        poly.Hole(idx,hole).Append(at.x+round(x*1e6),at.y+round(y*1e6))
    z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(net)
    z.Outline().Append(poly);z.SetFilledPolysList(face,poly);z.SetIsFilled(True);b.Add(z)
    main,sat=op._inventory(owner)
    result=isolation.isolated(b,owner,main,list(sat.values()),deadline=time.monotonic()+2.)
    assert result['isolated']and result['complete']and len(result['actual_zone_fill_identities'])==1


@pytest.mark.parametrize('fault',['retype','extra_track','reference'])
def test_saved_unassigned_receiver_has_no_extra_edit_or_grounding_authority(tmp_path,monkeypatch,fault):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    b=pcbnew.LoadBoard(str(child));owner=next(iter(b.GetFootprints()))
    if fault=='retype':
        net=ground_net(b)
        for p in owner.Pads():p.SetNet(net)
    elif fault=='reference':owner.SetReference('OTHER_OWNER')
    else:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(2,2));t.SetEnd(pcbnew.VECTOR2I_MM(3,2))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(b.FindNet('GND'));b.Add(t)
    field._save_field_snapshot(b,child)
    assert not op.receive(source,child,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)['ok']


@pytest.mark.parametrize('header',['general','setup','layers'])
@pytest.mark.parametrize('mode',['existing_ground',isolation.MODE])
def test_unchanged_uuid_map_cannot_hide_a_modified_board_header(tmp_path,monkeypatch,header,mode):
    if mode==isolation.MODE:source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    else:
        source,uid,vendor=grounded.fixture(tmp_path);hint='synthetic'
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    import cec_additive_route_receiving as native
    root,items=native._nodes(child)
    node=next(n for n in root if isinstance(n,list)and n and n[0]==header)
    node.append(['unowned_header_change','1'])
    child.write_text(native._render(root))
    assert {k:op.syntax._freeze(v)for k,v in native._nodes(child)[1].items()}=={
        k:op.syntax._freeze(v)for k,v in items.items()}
    received=op.receive(source,child,board_hint=hint,mount_uuids=[uid],terminal_mode=mode)
    assert not received['ok']and any('complete_source_root'in e for e in received['errors'])


def test_late_manifest_declaration_cannot_leave_field_receiving_green(tmp_path,monkeypatch):
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    original=field.field_coupling_summary;calls=[]
    def summary(*args,**kwargs):
        value=original(*args,**kwargs);calls.append(args)
        if len(calls)==2:(tmp_path/'board-manifest.json').write_text(
            '{"placement_directives":{"mount_net":"GND"}}')
        return value
    monkeypatch.setattr(field,'field_coupling_summary',summary)
    result=field.assess_native_mechanical_mount(source,child,board_hint=hint,
        mount_uuids=[uid],terminal_mode=isolation.MODE)
    assert len(calls)==2 and result['ok']is not True and not result['complete']
    assert 'declared_mount_net'in result['reason']


def test_manifest_mutation_during_final_full_identity_collection_is_refused(tmp_path,monkeypatch):
    """Negative orchestration test, not a mocked positive DRC certificate.

    Literal/physical/field scope is real. Unrelated outer gates are isolated
    solely to reach the late identity callback; no admission is credited.
    """
    source,uid,vendor,hint=fixture(tmp_path,monkeypatch)
    proposal=op.plan(source,board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    child=force._copy_family(source,tmp_path/'child');op.construct_private(source,child,proposal)
    import cec_received_private_stage as stage
    import cec_native_drc_runner as native
    import cec_current_debt as debt
    import cec_constraints as constraints
    ids=[];reports=[]
    def identity(*args,**kwargs):
        ids.append(args)
        if len(ids)==4:(tmp_path/'board-manifest.json').write_text(
            '{"placement_directives":{"mount_net":"GND"}}')
        return {'native_library_authority':{}}
    def report(path,dest,**kwargs):
        reports.append(path);force._write(dest,dict(violations=[{'severity':'warning'}]if len(reports)==1 else[],
            unconnected_items=[],excluded_violations=[]))
        return dict(native_library_context=dict(bound=True,source_and_context_unchanged=True,authority={}))
    monkeypatch.setattr(stage,'identity',identity)
    monkeypatch.setattr(stage,'receive_intakes',lambda *_a,**_k:({
        name+'_intake':dict(ok=True,intake=dict(ok=True))for name in('source','candidate')},None))
    monkeypatch.setattr(stage,'require_native_tool',lambda *_a:None)
    monkeypatch.setattr(stage,'native_findings_delta',lambda *_a:dict(ok=True))
    monkeypatch.setattr(native,'_describe_build',lambda *_a:{})
    monkeypatch.setattr(native,'run',report)
    monkeypatch.setattr(debt,'receive',lambda *_a,**_k:dict(ok=True,complete=True))
    monkeypatch.setattr(constraints,'_chk_sch_pcb_sync',lambda *_a:(True,{}))
    result=op.receive_full(source,child,tmp_path/'full',board_hint=hint,mount_uuids=[uid],terminal_mode=isolation.MODE)
    assert len(ids)==4 and len(reports)==2,result
    assert result['gates']['source_live']is True and not result['complete']and not result['ok']
    assert 'declared_mount_net'in result['error']and not result['admitted']
