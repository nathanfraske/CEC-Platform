"""Typed transaction composition: no live board jobs or fabricated grades."""
import ast
import copy
import importlib.util
import inspect
from pathlib import Path
import pytest
import pcbnew
import subprocess

WRAPPER=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_local_transaction',WRAPPER)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def phase(kind='complete_macro',**extra):
    options={'complete_macro':dict(options={}), 'control_shunt_tail':dict(warning_uuids=['native-warning']),
        'reference_fields':dict(proposal='/explicit/source-proposal.json'),
        'reference_map':dict(proposal='/explicit/source-proposal.json'),
        'mechanical_mount':dict(mount_uuids=['native-mount']),
        'qualified_courtyard':dict(proposal='/explicit/source-proposal.json'),
        'equivalent_courtyard':dict(proposal='/explicit/source-proposal.json')}
    return dict(kind=kind,candidate='/explicit/child.kicad_pcb',candidate_sha256='a'*64,**options[kind],**extra)


def test_finite_typed_schema_and_required_actual_order():
    rows=[phase(),phase('control_shunt_tail'),phase('reference_fields'),phase('mechanical_mount')]
    assert op.validate_phases(rows)==[r['kind']for r in rows]


@pytest.mark.parametrize('identity',['fan-limb','',True,' trailing ',None,'a'*1025])
def test_auxiliary_phase_names_only_existing_source_identity(identity):
    row=dict(kind='auxiliary_attachment',candidate='/explicit/child.kicad_pcb',
        candidate_sha256='a'*64,attachment_id=identity)
    if identity=='fan-limb':
        assert op.validate_phases([row])==['auxiliary_attachment']
        for key,value in [('amps',1),('margin',1.25),('current_qualified',True),('timeout_s',30)]:
            with pytest.raises(ValueError):op.validate_phases([dict(row,**{key:value})])
    else:
        with pytest.raises(ValueError):op.validate_phases([row])


@pytest.mark.parametrize('accepted',[False,True])
def test_auxiliary_dispatch_rederives_actual_saved_parent_contract(tmp_path,monkeypatch,accepted):
    source=tmp_path/'source.kicad_pcb';parent=tmp_path/'parent.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    for path in(source,parent,child):path.write_text(path.stem)
    row=dict(kind='auxiliary_attachment',candidate=str(child),candidate_sha256=op.force._hash(child),attachment_id='limb')
    seen=[]
    def receive(before,after,identity,**kwargs):
        seen.append((before,after,identity,kwargs));return dict(ok=accepted,complete=True)
    monkeypatch.setattr(op.auxiliary_attachment,'receive',receive)
    if accepted:assert op.receive_phase(source,parent,row,'bound')[0]==child
    else:
        with pytest.raises(AssertionError):op.receive_phase(source,parent,row,'bound')
    assert seen==[(parent,child,'limb',dict(board_hint='bound',timeout_s=10.))]


@pytest.mark.parametrize('fault',[None,'seed','locks','width','role','timeout'])
@pytest.mark.parametrize('kind',['source_class_ground_tail','source_ground_land_root_spur'])
def test_source_class_Ground_tail_has_no_caller_width_or_role_override(fault,kind):
    row=dict(kind=kind,candidate='/explicit/cut.kicad_pcb',candidate_sha256='a'*64,
        seed_uuid='actual-native-track',allow_locked_track_uuids=[])
    if fault=='seed':row['seed_uuid']=True
    elif fault=='locks':row['allow_locked_track_uuids']=True
    elif fault:row[fault]=.5
    if fault:
        with pytest.raises(ValueError):op.validate_phases([row])
    else:assert op.validate_phases([row])==[kind]


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_whole_ground_land_spur_dispatch_rederives_actual_saved_scope(tmp_path,angle):
    from test_source_class_ground_land_root_spur import fixture,save_child
    source,board,ids,_=fixture(tmp_path,turn=angle//90)
    q=op.source_ground_land_spur.plan(board,source,ids['seed'])
    child=save_child(source,board,q,tmp_path)
    row=dict(kind='source_ground_land_root_spur',candidate=str(child),
        candidate_sha256=op.force._hash(child),seed_uuid=ids['seed'],allow_locked_track_uuids=[])
    selected,proof=op.receive_phase(source,source,row,'unclassified-test')
    assert selected==child and proof['ok']and proof['complete']
    assert len(proof['retired_track_uuids'])==3
    assert not proof['current_qualified']and not proof['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_source_class_Ground_tail_dispatch_uses_real_saved_source_and_exact_cut(tmp_path,angle):
    from test_source_class_ground_dead_end_tail import fixture
    import cec_additive_route_receiving as additive
    import cec_field_coupling as field
    source,board,body,tip,root,_=fixture(tmp_path,angle)
    seed=op.force._uid(tip)
    q=op.source_ground_tail.plan(board,source,seed)
    op.source_ground_tail.subtract(board,q)
    child=op.force._copy_family(source,tmp_path/'typed-cut')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    row=dict(kind='source_class_ground_tail',candidate=str(child),candidate_sha256=op.force._hash(child),
        seed_uuid=seed,allow_locked_track_uuids=[])
    selected,proof=op.receive_phase(source,source,row,'unclassified-test')
    assert selected==child and proof['ok']and proof['complete']
    assert not proof['current_qualified']and not proof['release_authority']


def test_one_exact_macro_cleanup_boundary_fits_existing_four_phase_cap():
    cleanup=dict(kind='macro_tail_cleanup',candidate='/explicit/cut.kicad_pcb',
        candidate_sha256='b'*64,proposal='/explicit/saved-cut-chain.json')
    printed=dict(kind='print_context',candidate='/explicit/print.kicad_pcb',
        candidate_sha256='c'*64,proposal='/explicit/print.json')
    rows=[phase(),cleanup,phase('reference_fields'),printed]
    assert op.validate_phases(rows)==[r['kind']for r in rows]
    for bad in ([cleanup],
                [phase(),phase('control_shunt_tail'),cleanup],[phase(),cleanup,cleanup]):
        with pytest.raises(ValueError):op.validate_phases(bad)


def test_cooperative_preclear_macro_cleanup_and_print_keep_every_distinct_phase_bounded():
    prefix=dict(kind='source_ordinary_barrel_reseat',candidate='/explicit/reseat.kicad_pcb',
        candidate_sha256='a'*64,via_uuid='actual-source-barrel')
    rated=dict(kind='rated_branch',candidate='/explicit/rated.kicad_pcb',candidate_sha256='b'*64,
        retired_track_uuids=['actual-source-conductor'],options={})
    cleanup=dict(kind='macro_tail_cleanup',candidate='/explicit/clean.kicad_pcb',
        candidate_sha256='c'*64,proposal='/explicit/cleanup.json')
    printed=dict(kind='print_context',candidate='/explicit/print.kicad_pcb',
        candidate_sha256='d'*64,proposal='/explicit/print.json')
    rows=[prefix,rated,phase(),cleanup,phase('reference_fields'),printed]
    assert op.MAX_LOCAL_PHASES==6
    assert op.validate_phases(rows)==[r['kind']for r in rows]
    for invalid in (rows+[phase()],rows[:2]+[cleanup,phase(),printed],
            rows[:3]+[phase('reference_fields'),cleanup,printed],rows[:4]+[cleanup,printed]):
        with pytest.raises(ValueError):op.validate_phases(invalid)


def test_equivalent_courtyard_is_a_distinct_first_only_finite_scope():
    row=phase('equivalent_courtyard')
    assert op.validate_phases([row,phase('reference_fields')])==['equivalent_courtyard','reference_fields']
    for bad in([phase(),row],[row,row],[phase('reference_fields'),row]):
        with pytest.raises(ValueError):op.validate_phases(bad)


@pytest.mark.parametrize('accepted',[False,True])
def test_equivalent_courtyard_independently_receives_actual_saved_parent(tmp_path,monkeypatch,accepted):
    import json
    original=tmp_path/'original.kicad_pcb';parent=tmp_path/'parent.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    for p in(original,parent,child):p.write_text(p.stem)
    proposal=tmp_path/'proposal.json';proposal.write_text(json.dumps({'board_hint':'bound'}));seen=[]
    row=phase('equivalent_courtyard');row.update(candidate=str(child),candidate_sha256=op.force._hash(child),proposal=str(proposal))
    def receive(source,candidate,q,**kw):
        seen.append((source,candidate,q,kw));return dict(ok=accepted,complete=True)
    monkeypatch.setattr(op.equivalent_court,'receive',receive)
    if accepted:assert op.receive_phase(original,parent,row,'bound')[0]==child
    else:
        with pytest.raises(AssertionError):op.receive_phase(original,parent,row,'bound')
    assert seen==[(parent,child,{'board_hint':'bound'},{'timeout_s':10.})]
    with pytest.raises(AssertionError):op.receive_phase(original,parent,row,'wrong')


def test_query_equivalent_courtyard_relation_requires_typed_saved_scopes(tmp_path,monkeypatch):
    import json
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb';proposal=tmp_path/'proposal.json'
    source.write_text('source');child.write_text('child');proposal.write_text(json.dumps({'board_hint':'bound'}))
    row=phase('equivalent_courtyard');row.update(candidate=str(child),candidate_sha256=op.force._hash(child),proposal=str(proposal))
    seen=[]
    def receive(original,parent,actual,hint,**kw):
        seen.append(('phase',original,parent,actual,hint));return child,dict(ok=True,complete=True)
    monkeypatch.setattr(op,'receive_phase',receive)
    def relation(parent,candidate,q,**kw):
        seen.append(('identity',parent,candidate,q));return dict(ok=True,complete=True,comparison_complete=True,
            same_material=True,mutation_authority=False,full_kelvin_qualification=False)
    monkeypatch.setattr(op.equivalent_court,'query_input_identity',relation)
    proof=op.equivalent_courtyard_query_input_identity(source,child,[row],board_hint='bound')
    assert proof['comparison_complete']and not proof['full_kelvin_qualification']
    assert seen==[('phase',source,source,row,'bound'),('identity',source,child,{'board_hint':'bound'})]
    assert op.equivalent_courtyard_query_input_identity(source,child,[phase()],board_hint='bound')is None
    monkeypatch.setattr(op.equivalent_court,'query_input_identity',lambda *a,**k:dict(ok=True,complete=False))
    with pytest.raises(AssertionError):op.equivalent_courtyard_query_input_identity(source,child,[row],board_hint='bound')


@pytest.mark.parametrize('rows',[[],[phase()]*5,[phase(),phase()],
    [phase('control_shunt_tail')],[phase('mechanical_mount'),phase()],
    [phase(),phase('qualified_courtyard')], [phase('reference_fields'),phase('reference_map')],
    [dict(phase(),external_success=True)], [dict(phase(),kind='caller_callback')]])
def test_untyped_repeated_reordered_or_unbounded_phases_refuse(rows):
    with pytest.raises(ValueError):op.validate_phases(rows)


@pytest.mark.parametrize('digest',['','a'*63,'a'*65,'G'*64,'A'*64,'not-a-sha',True,None])
def test_exact_canonical_sha_schema_refuses_before_native_work(digest):
    row=phase();row['candidate_sha256']=digest
    with pytest.raises(ValueError):op.validate_phases([row])


@pytest.mark.parametrize('value',['',True,None])
def test_explicit_nonempty_candidate_path_schema(value):
    row=phase();row['candidate']=value
    with pytest.raises(ValueError):op.validate_phases([row])


@pytest.mark.parametrize('proof',[{},dict(ok=True),dict(ok=1,complete=True),dict(ok=True,complete=1),dict(ok=False,complete=True)])
def test_false_or_incomplete_phase_proof_never_advances_cursor(tmp_path,monkeypatch,proof):
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    source.write_text('source');child.write_text('child')
    row=phase();row.update(candidate=str(child),candidate_sha256=op.force._hash(child))
    monkeypatch.setattr(op.macro,'receive',lambda *a,**k:proof)
    with pytest.raises(AssertionError):op.receive_phase(source,source,row,'source-hint')


def test_phase_source_is_previous_cursor_not_proposal_or_worker_claim(tmp_path,monkeypatch):
    original=tmp_path/'original.kicad_pcb';parent=tmp_path/'parent.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    for p in(original,parent,child):p.write_text(p.stem)
    row=phase();row.update(candidate=str(child),candidate_sha256=op.force._hash(child));seen=[]
    def receive(source,candidate,**kwargs):
        seen.append((source,candidate,kwargs));return dict(ok=True,complete=True)
    monkeypatch.setattr(op.macro,'receive',receive)
    assert op.receive_phase(original,parent,row,'bound-hint')[0]==child
    assert seen==[(parent,child,dict(board_hint='bound-hint'))]
    row['options']={'board_hint':'wrong-source'}
    with pytest.raises(AssertionError):op.receive_phase(original,parent,row,'bound-hint')


def test_stale_child_hash_refuses_before_any_source_receiver(tmp_path,monkeypatch):
    child=tmp_path/'child.kicad_pcb';child.write_text('actual')
    row=phase();row['candidate']=str(child)
    monkeypatch.setattr(op.macro,'receive',lambda *a,**k:pytest.fail('stale child reached native scope'))
    with pytest.raises(AssertionError):op.receive_phase(tmp_path/'original',tmp_path/'parent',row,'hint')


def test_contour_call_uses_supported_real_api_keywords():
    tree=ast.parse(WRAPPER.read_text())
    calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr=='compare_contour_preservation']
    assert len(calls)==1
    kwargs={k.arg:None for k in calls[0].keywords}
    inspect.signature(op.sense.compare_contour_preservation).bind({}, {}, **kwargs)


def test_field_comparison_explicitly_guards_unsupported_related_native_arcs():
    # The summary silently skips native arcs. Its existing guarded receiver
    # requires actual resolver-based aggressor/victim rejection beforehand.
    text=WRAPPER.read_text()
    assert ('related_native_curved_copper_unsupported'in text
        or 'receive_native_transition_field'in text), 'raw summary is not an unsupported-geometry guard'


def test_contour_scope_is_actual_modified_nets_not_unbounded_all_pad_nets():
    tree=ast.parse(WRAPPER.read_text())
    calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr in('native_copper_transform_inventory','compare_contour_preservation')]
    assert len(calls)==2
    for call in calls:
        scope=next(k.value for k in call.keywords if k.arg=='modified_nets')
        assert not(isinstance(scope,ast.Name)and scope.id=='all_nets'), 'real comparator modified_nets has a64-net bound; all pad nets is not a delta'


def test_final_identity_and_actual_native_all_findings_are_not_optional():
    text=WRAPPER.read_text()
    for required in("g['live']","g['all_phase_source_families_live']","g['suite_live']",
        "g['code_and_inputs_live']",'native_findings_delta','source_and_context_unchanged',
        'source_candidate_intake','source_intake'):
        # Last two are emitted dynamically by the existing source loop.
        if required in('source_candidate_intake','source_intake'):continue
        assert required in text
    assert 'all(v is True for v in g.values())'in text


def native_pair(tmp_path,nets=1):
    board=pcbnew.BOARD()
    for i in range(nets):
        net=pcbnew.NETINFO_ITEM(board,'renamed_delta_'+str(i));board.Add(net)
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(i*2,0));t.SetEnd(pcbnew.VECTOR2I_MM(i*2+1,0))
        t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetNet(net);board.Add(t)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_package');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('odd');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    pad.SetNet(board.FindNet('renamed_delta_0'));pad.SetPosition(pcbnew.VECTOR2I_MM(0,4));fp.Add(pad)
    path=tmp_path/'native.kicad_pcb';op.coupling._save_field_snapshot(board,path)
    return board,pcbnew.LoadBoard(str(path))


def test_actual_same_uuid_track_pose_is_a_changed_net(tmp_path):
    before,after=native_pair(tmp_path);track=next(iter(after.GetTracks()));uid=op.force._uid(track)
    track.Move(pcbnew.VECTOR2I(1,0))
    assert uid in{op.force._uid(t)for t in before.GetTracks()}
    assert op.changed_native_nets(before,after)==['renamed_delta_0']


def test_actual_moved_pad_position_key_still_rebinds_its_positive_net(tmp_path):
    before,after=native_pair(tmp_path)
    pad=next(p for fp in after.GetFootprints()for p in fp.Pads());pad.Move(pcbnew.VECTOR2I(1,0))
    assert op.changed_native_nets(before,after)==['renamed_delta_0']


@pytest.mark.parametrize('changed',['outline','fill'])
def test_actual_zone_outline_and_saved_fill_changes_are_not_ignored(tmp_path,changed):
    before,after=native_pair(tmp_path)
    for board in(before,after):
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(board.FindNet('renamed_delta_0'))
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in((3,3),(5,3),(5,5),(3,5)):poly.Append(x*1000000,y*1000000)
        zone.Outline().Append(poly);zone.SetFilledPolysList(pcbnew.F_Cu,poly);zone.SetIsFilled(True);board.Add(zone)
    first=next(iter(before.Zones()));child=next(iter(after.Zones()));child.m_Uuid.Clone(first.m_Uuid)
    if changed=='outline':child.Outline().Append(4000000,6000000)
    else:
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in((3,3),(4,3),(4,4),(3,4)):poly.Append(x*1000000,y*1000000)
        child.SetFilledPolysList(pcbnew.F_Cu,poly)
    assert op.changed_native_nets(before,after)==['renamed_delta_0']


def test_more_than_64_unchanged_source_nets_do_not_expand_contour_scope(tmp_path):
    before,after=native_pair(tmp_path,65)
    assert op.changed_native_nets(before,after)==[]
    next(iter(after.GetTracks())).SetWidth(210000)
    assert len(op.changed_native_nets(before,after))==1


def test_more_than_64_actual_changed_nets_refuse_not_truncate(tmp_path):
    before,after=native_pair(tmp_path,65)
    for t in after.GetTracks():t.SetWidth(210000)
    with pytest.raises(ValueError,match='bounded_changed_native_net_scope'):
        op.changed_native_nets(before,after)


def test_changed_unbound_net_material_refuses(tmp_path):
    before,after=native_pair(tmp_path)
    for board in(before,after):next(iter(board.GetTracks())).SetNetCode(0)
    next(iter(after.GetTracks())).SetWidth(210000)
    with pytest.raises(ValueError,match='without_positive_net'):
        op.changed_native_nets(before,after)


@pytest.mark.parametrize('side',[0,1])
def test_actual_related_native_arc_on_either_endpoint_board_refuses(tmp_path,monkeypatch,side):
    boards=native_pair(tmp_path);board=boards[side]
    arc=pcbnew.PCB_ARC(board);arc.SetStart(pcbnew.VECTOR2I_MM(0,8));arc.SetMid(pcbnew.VECTOR2I_MM(1,9));arc.SetEnd(pcbnew.VECTOR2I_MM(2,8))
    arc.SetWidth(200000);arc.SetLayer(pcbnew.F_Cu);arc.SetNet(board.FindNet('renamed_delta_0'));board.Add(arc)
    # The neutral net name is not authority: actual source netclass says SENSE.
    seen=[]
    def resolver(path):
        seen.append(path);return lambda net:dict(name='SENSE')
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',resolver)
    with pytest.raises(ValueError,match='related_native_curved_copper_unsupported'):
        op.field_geometry_scope(boards,['source-explicit','child-explicit'])
    assert seen[-1]==('source-explicit'if side==0 else'child-explicit')


def test_neutral_native_arc_is_observed_not_misclassified_or_globally_banned(tmp_path,monkeypatch):
    boards=native_pair(tmp_path);board=boards[1]
    arc=pcbnew.PCB_ARC(board);arc.SetStart(pcbnew.VECTOR2I_MM(0,8));arc.SetMid(pcbnew.VECTOR2I_MM(1,9));arc.SetEnd(pcbnew.VECTOR2I_MM(2,8))
    arc.SetWidth(200000);arc.SetLayer(pcbnew.F_Cu);arc.SetNet(board.FindNet('renamed_delta_0'));board.Add(arc)
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda path:lambda net:dict(name='Default'))
    rows=op.field_geometry_scope(boards,['source-explicit','child-explicit'])
    assert rows[0]['neutral_unsupported_geometry_uuids']==[]
    assert rows[1]['neutral_unsupported_geometry_uuids']==[op.force._uid(arc)]


def test_native_field_geometry_inventory_is_bounded(tmp_path,monkeypatch):
    boards=native_pair(tmp_path,2)
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda path:lambda net:dict(name='Default'))
    with pytest.raises(ValueError,match='native_replacement_field_item_budget'):
        op.field_geometry_scope(boards,['source','child'],maximum_native_items=1)


def test_zero_delta_calls_actual_strict_contact_comparator_not_contour_rebinding(tmp_path,monkeypatch):
    before,after=native_pair(tmp_path);modified_nets=op.changed_native_nets(before,after)
    assert modified_nets==[]
    calls=[]
    monkeypatch.setattr(op.sense,'compare_contact_preservation',lambda a,b:(calls.append((a,b))or dict(same_evidence=True,comparison_complete=True)))
    monkeypatch.setattr(op.sense,'compare_contour_preservation',lambda *a,**k:pytest.fail('zero delta rebinds unrelated contours'))
    result=op.strict_contact_transition({'strict':1},{'strict':1},modified_nets,[])
    assert result['same_evidence']and calls==[({'strict':1},{'strict':1})]


@pytest.mark.parametrize('fault',[None,'source_changed','final_contact_changed','macro_refused','boundary_hash'])
def test_macro_repair_authority_never_waives_strict_source_or_final_boundary(tmp_path,monkeypatch,fault):
    boundary=tmp_path/'macro.kicad_pcb';final=tmp_path/'final.kicad_pcb'
    board=pcbnew.BOARD();pcbnew.SaveBoard(str(boundary),board);pcbnew.SaveBoard(str(final),board)
    row=phase();row.update(candidate=str(boundary),candidate_sha256=op.force._hash(boundary))
    source_raw={'value':'source'};macro_raw={'value':'macro'}
    result=dict(ok=fault!='macro_refused',complete=True,raw_native_evidence=[source_raw,macro_raw])
    monkeypatch.setattr(op.macro_contact,'receive',lambda *a,**k:result)
    seen=[]
    def strict(a,b,nets,transforms):
        seen.append((a,b,nets,transforms))
        return dict(comparison_complete=True,same_evidence=a==b)
    monkeypatch.setattr(op,'strict_contact_transition',strict)
    evidence=[{'value':'changed'if fault=='source_changed'else'source'},
        {'value':'changed'if fault=='final_contact_changed'else'macro'}]
    if fault=='boundary_hash':
        row['candidate_sha256']='0'*64
        with pytest.raises(ValueError,match='macro_contact_boundary_changed'):
            op.complete_macro_contact_transition(tmp_path/'source',final,[row],evidence,board_hint='opaque')
        assert not seen;return
    received=op.complete_macro_contact_transition(tmp_path/'source',final,[row],evidence,board_hint='opaque')
    assert received['same_evidence']==(fault is None)
    if fault=='macro_refused':assert not seen
    else:assert len(seen)==2


def test_saved_craft_uses_actual_fresh_native_file_and_preserves_source_bytes(tmp_path):
    path=tmp_path/'source.kicad_pcb';board=pcbnew.BOARD()
    pcbnew.SaveBoard(str(path),board);frozen=path.read_bytes()
    proof=op.saved_craft(path,tmp_path/'craft.json',board_hint='explicit-native-fixture')
    assert proof['complete']and proof['source_and_code_unchanged']
    assert proof['report']['issue_count']==proof['report']['non_octilinear_count']==0
    assert path.read_bytes()==frozen


@pytest.mark.parametrize('failure',['crash','timeout','missing_report','forged_identity'])
def test_saved_craft_never_treats_native_process_failure_as_success(tmp_path,monkeypatch,failure):
    path=tmp_path/'source.kicad_pcb';board=pcbnew.BOARD();pcbnew.SaveBoard(str(path),board)
    out=tmp_path/'craft.json'
    def child(command,**kwargs):
        assert kwargs['timeout']==10.
        if failure=='timeout':raise subprocess.TimeoutExpired(command,10.)
        if failure=='forged_identity':op.force._write(out,dict(complete=True,source='not-the-saved-board'))
        return subprocess.CompletedProcess(command,-11 if failure=='crash'else 0,stdout='native-diagnostic')
    monkeypatch.setattr(op.subprocess,'run',child)
    with pytest.raises(ValueError):op.saved_craft(path,out,board_hint='explicit-native-fixture')
    if failure!='forged_identity':
        proof=op.json.loads(out.with_suffix('.failure.json').read_text())
        assert not proof['complete']and not proof['release_authority']
