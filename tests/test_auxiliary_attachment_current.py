"""Explicit minima cannot silently become rail allocations or load models."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

import pcbnew
import pytest

import cec_auxiliary_attachment_current as aux
import cec_field_coupling as field
import cec_force_current as force
import cec_synth_pipeline as synth


@pytest.mark.parametrize('boundary,timeout_s', [(128.,10.),(2048.,10.),(16.,.25),(256.,.5)])
def test_reported_stage_lease_roundoff_cannot_exceed_declared_bound(monkeypatch,boundary,timeout_s):
    clock=[math.nextafter(boundary,-math.inf)]
    monkeypatch.setattr(aux.time,'monotonic',lambda:clock[0])
    result=dict(stages=[])
    stages=aux._ReceiveStages(result,timeout_s)
    start=clock[0]
    with stages.stage('geometry') as deadline:
        # Exercise real binary subtraction overflow, not a tolerance or
        # changed deadline. Only the public duration report is bounded.
        assert deadline==start+timeout_s
        assert deadline-start>timeout_s
        assert result['stages'][0]['lease_s']==timeout_s
        assert result['budget']['constituent_timeout_s']==timeout_s
        assert result['budget']['aggregate_timeout_s']==4*timeout_s
        clock[0]=start+timeout_s/2
    assert result['stages'][0]['complete'] and not stages.failed


def test_bounded_stage_report_does_not_accept_actual_deadline_expiry(monkeypatch):
    clock=[math.nextafter(2048.,-math.inf)]
    monkeypatch.setattr(aux.time,'monotonic',lambda:clock[0])
    result=dict(stages=[])
    stages=aux._ReceiveStages(result,10.)
    start=clock[0]
    with pytest.raises(ValueError,match='auxiliary_attachment_deadline'):
        with stages.stage('geometry') as deadline:
            assert deadline==start+10.
            clock[0]=deadline
    assert stages.failed and not result['stages'][0]['complete']
    assert result['stages'][0]['error']=='ValueError:auxiliary_attachment_deadline'
    assert result['stages'][0]['lease_s']==10.


def test_bounded_stage_report_does_not_inflate_short_aggregate_remainder(monkeypatch):
    clock=[1.]
    monkeypatch.setattr(aux.time,'monotonic',lambda:clock[0])
    result=dict(stages=[])
    stages=aux._ReceiveStages(result,10.)
    clock[0]=stages.deadline-.25
    with stages.stage('geometry') as deadline:
        assert deadline==stages.deadline
        assert result['stages'][0]['lease_s']==.25
        clock[0]+=.125
    assert result['stages'][0]['complete']
    assert result['budget']['aggregate_timeout_s']==40.


def fixture(tmp_path, monkeypatch, *, context='alpha', angle=0, flip=False, via=False):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_high_current'; board.SetProperties(props)
    settings = board.GetDesignSettings(); settings.m_TrackMinWidth = 150000
    settings.m_MinClearance = 200000; settings.m_ViasMinSize = 500000
    settings.m_MinThroughDrill = 200000; settings.m_ViasMinAnnularWidth = 100000
    netname = '/unrelated_'+context+'/FEED'; net = pcbnew.NETINFO_ITEM(board, netname); board.Add(net)
    fps = []
    def part(ref, xy, pth=False):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(context+'_'+ref); fp.SetValue('selected_'+ref)
        fp.SetField('MPN', context+'-'+ref+'-MPN'); fp.SetFPID(pcbnew.LIB_ID('Selected', context+'_'+ref))
        fp.GetField('MPN').SetTextThickness(150000)
        board.Add(fp); pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('7'); pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE if pth else pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.8,1.8)); pad.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        pad.SetLayerSet(pcbnew.PAD.PTHMask() if pth else pcbnew.PAD.SMDMask())
        if pth: pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
        fps.append(fp); return pad
    source = part('producer', (10,10)); sink = part('main_terminal', (20,10))
    tap = part('attachment_port', (20,16), pth=via); isolated = part('isolated_part', (10,16))
    def track(a,b,width,layer=pcbnew.F_Cu):
        obj = pcbnew.PCB_TRACK(board); obj.SetNet(net); obj.SetLayer(layer)
        obj.SetStart(pcbnew.VECTOR2I_MM(*a)); obj.SetEnd(pcbnew.VECTOR2I_MM(*b)); obj.SetWidth(round(width*1e6))
        board.Add(obj); return obj
    trunk = track((10,10),(20,10),2.5); spur = track((20,10),(20,16),.5)
    for obj in [*fps, *board.GetTracks()]:
        obj.Rotate(pcbnew.VECTOR2I_MM(15,15), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        if flip: obj.Flip(pcbnew.VECTOR2I_MM(15,15), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for a,b in [((0,0),(35,0)),((35,0),(35,30)),((35,30),(0,30)),((0,30),(0,0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b)); edge.SetWidth(50000); board.Add(edge)
    declaration = dict(id='selected-external-limb', net=netname, minimum_continuous_amps=1., basis='explicit reviewed conductor minimum')
    for name,pad in [('attached_terminal',isolated),('tap_terminal',tap)]:
        fp = pad.GetParentFootprint()
        declaration[name] = dict(ref=fp.GetReference(), pin=pad.GetNumber(), mpn=fp.GetField('MPN').GetText(), footprint=fp.GetFPIDAsString())
    policy_path = tmp_path/'policy.json'
    policy_payload = dict(params={aux.POLICY_KEY:[declaration]})
    policy_path.write_text(json.dumps(policy_payload))
    monkeypatch.setattr(aux.policy,'load',lambda *a,**k:json.loads(policy_path.read_text()))
    monkeypatch.setattr(aux.policy,'policy_path',lambda *a,**k:str(policy_path))
    current = dict(amps=9.2, geometry_margin=1.25, margin_included=False, source='board_design_basis')
    domain = dict(net=netname, complete=True, missing_refs=[], authority_refs=[source.GetParentFootprint().GetReference(),sink.GetParentFootprint().GetReference()],
        source_refs=[source.GetParentFootprint().GetReference()], sink_refs=[sink.GetParentFootprint().GetReference()], amps=8.33)
    monkeypatch.setattr(aux.topology,'board_current_domains',lambda *a,**k:{netname:deepcopy(domain)})
    monkeypatch.setattr(aux.topology,'current_contract_for_net',lambda *a,**k:deepcopy(current))
    source_dir = tmp_path/'source'; source_dir.mkdir(); path = source_dir/'board.kicad_pcb'
    board.SetFileName(str(path)); pcbnew.SaveBoard(str(path),board)
    # A synthetic initial source is defined by its actual native saved bytes,
    # including KiCad's cardinal/thermal-angle serialization normalization.
    board=pcbnew.LoadBoard(str(path))
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    library=[]; symbols=[]; comps=[]; nodes=[]
    for index,fp in enumerate(fps):
        uid = str(uuid.uuid4()); ref=fp.GetReference(); value=fp.GetValue(); fpid=fp.GetFPIDAsString(); mpn=fp.GetField('MPN').GetText()
        library.append('(symbol "fixture:P'+str(index)+'" (symbol "P'+str(index)+'_1_1" (pin passive line (at 0 0 0) (length 1.27) (name "terminal") (number "7"))))')
        props=' '.join('(property "'+k+'" "'+v+'")' for k,v in [('Reference',ref),('Value',value),('Footprint',fpid),('MPN',mpn)])
        symbols.append('(symbol (lib_id "fixture:P'+str(index)+'") (at '+str(10+10*index)+' 10 0) (unit 1) (uuid "'+uid+'") '+props+')')
        comps.append('(comp (ref "'+ref+'") (value "'+value+'") (footprint "'+fpid+'") (property (name "MPN") (value "'+mpn+'")) (tstamps "'+uid+'"))')
        nodes.append('(node (ref "'+ref+'") (pin "7"))')
    root=tmp_path/'canonical.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(library)+') '+' '.join(symbols)+')')
    tree=synth.parse_sexpr('(export (components '+' '.join(comps)+') (nets (net (name "'+netname+'") '+' '.join(nodes)+')) )')
    exporter=tmp_path/'exporter'; exporter.write_text('fixture-export-identity')
    def export(path,deadline):
        return deepcopy(tree),dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),exporter=str(exporter),exporter_sha256=force._hash(exporter))
    monkeypatch.setattr(aux.canonical,'_export',export)
    return dict(board=board,path=path,root=root,policy=policy_path,payload=policy_payload,decl=declaration,
        current=current,domain=domain,tap=force._uid(tap),attached=force._uid(isolated),trunk=force._uid(trunk),
        spur=force._uid(spur),tree=tree,exporter=exporter,via=via)


def save_candidate(data,tmp_path,*,width=.5,via_size=(.6,.3),extra=None,deliberately_invalid=False):
    path=force._copy_family(data['path'],tmp_path/'candidate')
    board=pcbnew.LoadBoard(str(path)); pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    start,end=pads[data['attached']],pads[data['tap']]
    layer=next(int(l) for l in start.GetLayerSet().CuStack())
    if data['via']:
        layer=pcbnew.B_Cu if layer==pcbnew.F_Cu else pcbnew.F_Cu
        via=pcbnew.PCB_VIA(board);via.SetPosition(start.GetPosition());via.SetNet(start.GetNet())
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetWidth(round(via_size[0]*1e6));via.SetDrill(round(via_size[1]*1e6));board.Add(via)
    track=pcbnew.PCB_TRACK(board);track.SetNet(start.GetNet());track.SetLayer(layer)
    track.SetStart(start.GetPosition());track.SetEnd(end.GetPosition());track.SetWidth(round(width*1e6));board.Add(track)
    if extra:extra(board,start,end,track)
    if deliberately_invalid:
        # Preserve the deliberately contradictory authored net for receiver tests.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    else:
        field._save_field_snapshot(board,path)
    return path


@pytest.mark.parametrize('context,via,angle,flip',[
    ('alpha',False,0,False),('beta',True,0,False),('arbitrary',False,90,True),('different',True,270,True)])
def test_source_minimum_is_separate_from_aggregate_and_saved_chain_is_received(tmp_path,monkeypatch,context,via,angle,flip):
    d=fixture(tmp_path,monkeypatch,context=context,via=via,angle=angle,flip=flip)
    original=d['path'].read_bytes(); q=aux.source_contract(d['board'],d['decl']['id'],board_hint=str(d['root']))
    assert q['aggregate_current_authority']==d['current']
    assert q['aggregate_domain']['amps']==8.33  # Do not replace the 9.2 A sizing authority with thermal flow.
    assert q['minimum_conductor_authority']['amps']==1 and q['minimum_conductor_authority']['geometry_margin']==1.25
    assert q['required_by_layer_mm']['F.Cu']==.2
    assert q['required_by_layer_mm']['In2.Cu']>.2
    assert q['source_topology']['inherited_tap_and_aggregate_capacity_obligations_retained']
    child=save_candidate(d,tmp_path)
    result=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert result['ok'] and result['complete'],result['errors']
    assert result['contacts']['physical_tap_count']==1 and result['original_terminal_partitions_preserved']
    assert len(result['received_track_uuids'])==1 and len(result['received_via_uuids'])==int(via)
    assert result['new_craft']['issue_count']==0
    assert [s['name'] for s in result['stages']]==list(aux.RECEIVE_STAGES)
    assert all(s['complete'] and 0<s['lease_s']<=10 for s in result['stages']), result['stages']
    assert result['budget']['aggregate_timeout_s']==40 and result['budget']['retries']==0
    assert set(result['sense_audits'])=={'source','candidate'}
    assert all(r['complete'] and r['identity_stable'] and r['loaded_board_identity_verified']
        for r in result['sense_audits'].values())
    manifest=result['native_copper_transforms'][0]
    assert len(manifest['added_track_uuids'])==1+int(via) and len(manifest['added_via_uuids'])==int(via)
    for key in ('current_total_qualified','barrel_current_qualified','whole_fan_supply_qualified',
                'kelvin_qualified','load_model_qualified','thermal_or_transient_qualified','release_authority','aggregate_budget_reduced'):
        assert result[key] is False
    assert d['path'].read_bytes()==original


@pytest.mark.parametrize('fault',['missing','bool','nan','zero','extra_key','bad_endpoint','duplicate_id','duplicate_pair','same_endpoint','wrong_mpn','wrong_pin','wrong_net','above_aggregate'])
def test_policy_is_exact_and_caller_cannot_infer_local_current(tmp_path,monkeypatch,fault):
    d=fixture(tmp_path,monkeypatch); row=d['payload']['params'][aux.POLICY_KEY][0]
    if fault=='missing':d['payload']['params'].clear()
    elif fault=='bool':row['minimum_continuous_amps']=True
    elif fault=='nan':row['minimum_continuous_amps']=float('nan')
    elif fault=='zero':row['minimum_continuous_amps']=0
    elif fault=='extra_key':row['allow_full_current']=True
    elif fault=='bad_endpoint':row['attached_terminal']['uuid']='caller_identity'
    elif fault=='duplicate_id':d['payload']['params'][aux.POLICY_KEY].append(dict(row,tap_terminal=dict(row['tap_terminal'],ref='other')))
    elif fault=='duplicate_pair':d['payload']['params'][aux.POLICY_KEY].append(dict(row,id='other'))
    elif fault=='same_endpoint':row['tap_terminal']=deepcopy(row['attached_terminal'])
    elif fault=='wrong_mpn':row['attached_terminal']['mpn']='different'
    elif fault=='wrong_pin':row['attached_terminal']['pin']='8'
    elif fault=='wrong_net':row['net']='other'
    else:row['minimum_continuous_amps']=100
    d['policy'].write_text(json.dumps(d['payload']))
    with pytest.raises(ValueError):aux.source_contract(d['board'],d['decl']['id'],board_hint=str(d['root']))


@pytest.mark.parametrize('fault',['unknown','bool_amps','margin','double_margin','missing_margin','incomplete_domain','source_mpn','source_pin_net','source_no_connect','stale_export'])
def test_current_and_fresh_canonical_source_cannot_be_overridden(tmp_path,monkeypatch,fault):
    d=fixture(tmp_path,monkeypatch)
    if fault=='unknown':d['current']['source']='guessed'
    elif fault=='bool_amps':d['current']['amps']=True
    elif fault=='margin':d['current']['geometry_margin']=.5
    elif fault=='double_margin':d['current']['margin_included']=True
    elif fault=='missing_margin':d['current'].pop('geometry_margin')
    elif fault=='incomplete_domain':d['domain']['complete']=False
    elif fault=='source_mpn':d['root'].write_text(d['root'].read_text().replace(d['decl']['attached_terminal']['mpn'],'WRONG'))
    elif fault=='source_pin_net':
        nets=synth._first(d['tree'],'nets');synth._first(nets,'net')[1]=['name','wrong_export_net']
    elif fault=='source_no_connect':d['root'].write_text(d['root'].read_text()[:-1]+' (no_connect (at 40 10) (uuid "'+str(uuid.uuid4())+'")))')
    else:
        original=aux.canonical._export
        def changed(*a,**k):
            out=original(*a,**k);d['root'].write_text(d['root'].read_text()+'\n');return out
        monkeypatch.setattr(aux.canonical,'_export',changed)
    with pytest.raises(ValueError):aux.source_contract(d['board'],d['decl']['id'],board_hint=str(d['root']))


@pytest.mark.parametrize('fault',['thin','new_branch','loop','disconnect','wrong_net','new_inner','old_trunk_changed','old_pose_changed','extra_zone','sidecar','new_via_midchain'])
def test_saved_topology_and_material_are_independently_received(tmp_path,monkeypatch,fault):
    d=fixture(tmp_path,monkeypatch)
    def change(board,start,end,track):
        if fault=='thin':track.SetWidth(199999)
        elif fault=='disconnect':track.SetStart(pcbnew.VECTOR2I(track.GetStart().x+2000000,track.GetStart().y))
        elif fault=='wrong_net':
            foreign=pcbnew.NETINFO_ITEM(board,'FOREIGN');board.Add(foreign);track.SetNet(foreign)
        elif fault=='new_inner':track.SetLayer(pcbnew.In2_Cu)
        elif fault=='old_trunk_changed':next(t for t in board.GetTracks() if force._uid(t)==d['trunk']).SetWidth(2000000)
        elif fault=='old_pose_changed':start.GetParentFootprint().Move(pcbnew.VECTOR2I(100000,0))
        elif fault=='extra_zone':
            z=pcbnew.ZONE(board);z.SetNet(start.GetNet());z.SetLayer(pcbnew.F_Cu);z.Outline().NewOutline()
            for xy in [(25000000,20000000),(27000000,20000000),(27000000,22000000),(25000000,22000000)]:z.Outline().Append(*xy)
            board.Add(z)
        elif fault=='new_via_midchain':
            v=pcbnew.PCB_VIA(board);v.SetNet(start.GetNet());v.SetPosition(pcbnew.VECTOR2I_MM(15,16));v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
        elif fault in ('new_branch','loop'):
            points=[(10,16),(10,19)] if fault=='new_branch' else [(25,23),(26,23),(26,24),(25,24),(25,23)]
            for a,b in zip(points,points[1:]):
                t=pcbnew.PCB_TRACK(board);t.SetNet(start.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000)
                t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t)
    child=save_candidate(d,tmp_path,extra=change,deliberately_invalid=fault=='wrong_net')
    if fault=='sidecar':child.with_suffix('.unknown').write_text('unexpected authority')
    q=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert not q['ok'] and not q['complete'] and q['errors'],q


def test_physical_second_tap_without_graph_vertex_is_refused(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch)
    # Put an unchanged isolated same-net island in the proposed straight path.
    b=pcbnew.LoadBoard(str(d['path']));t=pcbnew.PCB_TRACK(b);t.SetNetCode(next(iter(b.GetTracks())).GetNetCode())
    t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000);t.SetStart(pcbnew.VECTOR2I_MM(15,15));t.SetEnd(pcbnew.VECTOR2I_MM(15,17));b.Add(t)
    field._save_field_snapshot(b,d['path']);child=save_candidate(d,tmp_path)
    q=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert not q['ok'] and any('second_tap' in e for e in q['errors']),q['errors']


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),1e-9])
def test_budget_is_bounded_and_expiration_is_not_approval(tmp_path,monkeypatch,seconds):
    d=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):aux.source_contract(d['board'],d['decl']['id'],board_hint=str(d['root']),timeout_s=seconds)


def test_no_public_current_or_success_override(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch)
    with pytest.raises(TypeError):aux.source_contract(d['board'],d['decl']['id'],board_hint=str(d['root']),amps=.01)
    with pytest.raises(TypeError):aux.receive(d['path'],d['path'],d['decl']['id'],board_hint=str(d['root']),current_ok=True)


def test_identity_drift_during_receiving_refuses(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch);child=save_candidate(d,tmp_path)
    old=aux._contacts
    def change(*a,**k):
        result=old(*a,**k);d['exporter'].write_text('changed exporter epoch');return result
    monkeypatch.setattr(aux,'_contacts',change)
    q=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert not q['ok'] and any('family_or_code_changed' in e for e in q['errors']),q['errors']


@pytest.mark.parametrize('context,via,angle,flip',[
    ('rail_alpha',False,0,False),('other_name',True,90,True)])
def test_saved_inventory_rederives_single_limb_and_preserves_every_source_assignment(tmp_path,monkeypatch,context,via,angle,flip):
    d=fixture(tmp_path,monkeypatch,context=context,via=via,angle=angle,flip=flip)
    monkeypatch.setattr(pcbnew.BOARD,'BuildConnectivity',lambda *a,**k:pytest.fail('global net propagation forbidden'))
    absent=aux.inventory(d['board'],board_hint=str(d['root']),timeout_s=10.)
    assert absent['complete'] and len(absent['absent_attachments'])==1 and not absent['track_requirements'],absent
    child=save_candidate(d,tmp_path); board=pcbnew.LoadBoard(str(child)); before=field._field_snapshot_inventory(board)
    packet=aux.inventory(board,board_hint=str(d['root']),timeout_s=10.)
    assert packet['complete'] and len(packet['track_requirements'])==1,packet['refusals']
    assert packet['proofs'][0]['contacts']['physical_tap_count']==1
    assert packet['proofs'][0]['projected_source']['aggregate_native_terminals_connected']
    requirement=next(iter(packet['track_requirements'].values()))
    assert requirement['current_authority']['amps']==1
    assert requirement['aggregate_current_authority']==d['current']
    assert requirement['required_mm']==.2
    assert field._field_snapshot_inventory(board)==before
    assert not packet['current_total_qualified'] and not packet['barrel_current_qualified']
    assert not packet['retirement_authority'] and not packet['release_authority']
    replay=aux.inventory(pcbnew.LoadBoard(str(child)),board_hint=str(d['root']),timeout_s=10.)
    assert replay==packet


@pytest.mark.parametrize('fault',['partial','fork','second_tap','thin','declared_mpn','canonical_net','aggregate_open','stale_loaded','deadline'])
def test_inventory_unknown_or_partial_never_lowers_any_aggregate_track(tmp_path,monkeypatch,fault):
    d=fixture(tmp_path,monkeypatch)
    def change(board,start,end,track):
        if fault=='partial':track.SetEnd(pcbnew.VECTOR2I_MM(15,16))
        elif fault=='thin':track.SetWidth(199999)
        elif fault in ('fork','second_tap'):
            t=pcbnew.PCB_TRACK(board);t.SetNet(start.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000)
            t.SetStart(start.GetPosition() if fault=='fork' else pcbnew.VECTOR2I_MM(15,15))
            t.SetEnd(pcbnew.VECTOR2I_MM(15,17));board.Add(t)
        elif fault=='aggregate_open':
            next(t for t in board.GetTracks() if force._uid(t)==d['trunk']).SetStart(pcbnew.VECTOR2I_MM(13,10))
    child=save_candidate(d,tmp_path,extra=change);board=pcbnew.LoadBoard(str(child))
    if fault=='declared_mpn':
        d['payload']['params'][aux.POLICY_KEY][0]['attached_terminal']['mpn']='OTHER_CONTEXT_PART'
        d['policy'].write_text(json.dumps(d['payload']))
    elif fault=='canonical_net':
        synth._first(synth._first(d['tree'],'nets'),'net')[1]=['name','OTHER_CONTEXT_NET']
    elif fault=='stale_loaded':next(iter(board.GetTracks())).SetWidth(177777)
    packet=aux.inventory(board,board_hint=str(d['root']),timeout_s=1e-9 if fault=='deadline' else 10.)
    assert not packet['complete'] and packet['refusals'] and not packet['track_requirements'],packet


def test_no_auxiliary_policy_is_neutral_without_native_or_export_work(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch);d['payload']['params'].clear();d['policy'].write_text(json.dumps(d['payload']))
    monkeypatch.setattr(aux,'_intent',lambda *a,**k:pytest.fail('no declared attachment'))
    packet=aux.inventory(d['board'],board_hint=str(d['root']))
    assert packet['complete'] and packet['neutral'] and not packet['track_requirements']


@pytest.mark.parametrize('size,expected', [((.6,.3),False),((.8,.3),True),((.9,.4),True),((.8,.2),False),((2.,.3),False)])
def test_actual_ordinary_via_may_grow_but_source_floor_full_web_and_containment_still_bind(tmp_path,monkeypatch,size,expected):
    d=fixture(tmp_path,monkeypatch,via=True)
    project=d['path'].with_suffix('.kicad_pro');config=json.loads(project.read_text())
    config['net_settings']['classes'][0]['track_width']=.5;project.write_text(json.dumps(config))
    child=save_candidate(d,tmp_path,via_size=size)
    packet=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    actual=aux.inventory(pcbnew.LoadBoard(str(child)),board_hint=str(d['root']),timeout_s=10.)
    assert packet['ok'] is expected,packet['errors']
    assert actual['complete'] is expected,actual['refusals']
    if expected:
        web=actual['proofs'][0]['actual_via_contact_webs'][0]
        assert set(web['actual_contact_layers'])=={'F.Cu','B.Cu'}
        assert len(web['unused_copper_layers_not_assumed_to_carry_current'])==4
        assert web['source_required_local_web_nm']==500000 and not web['plated_barrel_current_qualified']
    else:
        assert not actual['track_requirements']


def test_inventory_identity_drift_does_not_leave_partially_classified_ids(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch);child=save_candidate(d,tmp_path);old=aux._contacts
    def changed(*a,**k):
        proof=old(*a,**k);d['exporter'].write_text('new-source-exporter');return proof
    monkeypatch.setattr(aux,'_contacts',changed)
    packet=aux.inventory(pcbnew.LoadBoard(str(child)),board_hint=str(d['root']),timeout_s=10.)
    assert not packet['complete'] and not packet['track_requirements']
    assert any('canonical_epoch_changed' in e for e in packet['refusals'])


def current_packet(d,path,monkeypatch,*,consumer_tracks=None):
    """Keep other typed owners neutral; exercise the actual current checker."""
    import cec_constraints as constraints
    import cec_measurement_current_branch as measurement
    import cec_resistive_monitor_branch as resistive
    import cec_control_current_branch as control
    import cec_supply_consumer_branch as consumer
    for module in (measurement,resistive,control):
        monkeypatch.setattr(module,'inventory',lambda *a,**k:dict(complete=True,uuids=[]))
    monkeypatch.setattr(consumer,'inventory',lambda *a,**k:dict(complete=True,all_owned_track_requirements=consumer_tracks or {}))
    monkeypatch.setattr(constraints,'_legal_neckdown_uuids',lambda *a,**k:set())
    monkeypatch.setattr(constraints,'_validated_current_supply_escape_uuids',lambda *a,**k:set())
    monkeypatch.setattr(constraints,'_filtered_kelvin_force_stub_uuids',lambda *a,**k:set())
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT',str(d['root']))
    return constraints.CHECKERS['trace-width-high-current'](pcbnew.LoadBoard(str(path)),str(path),{})


@pytest.mark.parametrize('context,angle,flip',[('independent_alpha',0,False),('independent_beta',90,True)])
def test_current_debt_uses_only_rederived_limb_minimum_and_keeps_all_original_faults(tmp_path,monkeypatch,context,angle,flip):
    import cec_current_debt as debt
    d=fixture(tmp_path,monkeypatch,context=context,angle=angle,flip=flip)
    source=pcbnew.LoadBoard(str(d['path']))
    next(t for t in source.GetTracks() if force._uid(t)==d['trunk']).SetWidth(200000)
    field._save_field_snapshot(source,d['path']);child=save_candidate(d,tmp_path)
    before=current_packet(d,d['path'],monkeypatch);after=current_packet(d,child,monkeypatch)
    assert before[0] is False and after[0] is False
    for packet in (before,after):
        summary=next(r for r in packet[2] if r['type']=='current_debt_inventory')
        assert summary['typed_auxiliary_attachment_receiving']['complete']
        faults=next(r for r in packet[2] if r['type']=='current_domain_path')
        assert {s['uuid'] for s in faults['undersized_segments']}=={d['trunk'],d['spur']}
        assert faults['current_authority']==d['current']
    comparison=debt.evaluate(before,after)
    assert comparison['ok'] and comparison['complete'] and not comparison['current_qualified'],comparison
    assert comparison['before_fault_objects']==comparison['after_fault_objects']==3


def test_incomplete_declared_inventory_remains_aggregate_and_cannot_compare_as_current_success(tmp_path,monkeypatch):
    import cec_current_debt as debt
    d=fixture(tmp_path,monkeypatch)
    source=pcbnew.LoadBoard(str(d['path']))
    next(t for t in source.GetTracks() if force._uid(t)==d['trunk']).SetWidth(200000)
    field._save_field_snapshot(source,d['path']);child=save_candidate(d,tmp_path,width=.1)
    before=current_packet(d,d['path'],monkeypatch);after=current_packet(d,child,monkeypatch)
    summary=next(r for r in after[2] if r['type']=='current_debt_inventory')
    assert not summary['typed_auxiliary_attachment_receiving']['complete']
    faults=next(r for r in after[2] if r['type']=='current_domain_path')
    assert len(faults['undersized_segments'])==3 and faults['current_authority']==d['current']
    comparison=debt.evaluate(before,after)
    assert not comparison['ok'] and not comparison['complete']
    assert 'typed_auxiliary_attachment_receiving' in comparison['errors'][0]


@pytest.mark.parametrize('complete',[False,None,0,True])
def test_current_debt_validates_auxiliary_completeness_literally(complete):
    import cec_current_debt as debt
    authority=dict(amps=9.2,geometry_margin=1.25,margin_included=False,source='board_design_basis')
    summary=dict(type='current_debt_inventory',schema=1,complete=True,violation_count=1,
        trace_fault_count=1,domain_fault_count=0,
        typed_auxiliary_attachment_receiving=dict(complete=complete))
    fault=dict(type='keepout',reserve='pour_or_widen',net='arbitrary',uuid='actual_saved_track',
        layer='F.Cu',actual_mm=.2,required_mm=2.,current_authority=authority)
    result=(False,'existing fault',[summary,fault]);comparison=debt.evaluate(result,result)
    assert comparison['ok'] is (complete is True)
    assert comparison['complete'] is (complete is True)


def test_unknown_attachment_is_not_a_positive_current_check_even_without_width_faults(tmp_path,monkeypatch):
    import cec_current_debt as debt
    d=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(d['path']))
    for t in board.GetTracks():t.SetWidth(6000000)
    field._save_field_snapshot(board,d['path']);child=save_candidate(d,tmp_path,width=6.)
    d['payload']['params'][aux.POLICY_KEY][0]['attached_terminal']['mpn']='unverified-part'
    d['policy'].write_text(json.dumps(d['payload']))
    packet=current_packet(d,child,monkeypatch)
    assert packet[0] is None and not packet[2][0]['typed_auxiliary_attachment_receiving']['complete']
    comparison=debt.evaluate(packet,packet)
    assert not comparison['ok'] and not comparison['complete'] and not comparison['current_qualified']


def test_competing_local_owners_fall_back_to_aggregate_not_the_cheaper_requirement(tmp_path,monkeypatch):
    d=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(d['path']))
    next(t for t in board.GetTracks() if force._uid(t)==d['trunk']).SetWidth(200000)
    field._save_field_snapshot(board,d['path']);child=save_candidate(d,tmp_path)
    proof=aux.inventory(pcbnew.LoadBoard(str(child)),board_hint=str(d['root']),timeout_s=10.)
    assert proof['complete']
    packet=current_packet(d,child,monkeypatch,consumer_tracks=proof['track_requirements'])
    summary=next(r for r in packet[2] if r['type']=='current_debt_inventory')
    unknown=summary['typed_auxiliary_attachment_receiving']
    assert not unknown['complete'] and not unknown['track_requirements']
    assert unknown['overlapping_track_uuids']==sorted(proof['track_requirements'])
    faults=next(r for r in packet[2] if r['type']=='current_domain_path')
    assert set(proof['track_requirements']) <= {r['uuid'] for r in faults['undersized_segments']}
    assert faults['current_authority']==d['current']


def test_receiving_stages_have_independent_leases_but_one_finite_aggregate_cap(monkeypatch):
    clock=[100.];monkeypatch.setattr(aux.time,'monotonic',lambda:clock[0])
    result=dict(stages=[]);stages=aux._ReceiveStages(result,1.)
    for name in aux.RECEIVE_STAGES:
        with stages.stage(name) as deadline:
            assert deadline-clock[0]==pytest.approx(1.)
            clock[0]+=.9
    assert all(s['complete'] for s in result['stages'])
    assert result['budget']['aggregate_timeout_s']==4.
    with pytest.raises(ValueError):
        with stages.stage('geometry'):pass
    clock[0]=200.;result=dict(stages=[]);stages=aux._ReceiveStages(result,1.)
    with stages.stage('geometry'):clock[0]+=.5
    clock[0]+=3.2  # External time still consumes the single aggregate budget.
    with pytest.raises(ValueError,match='deadline'):
        with stages.stage('source_sense_audit') as deadline:
            assert deadline-clock[0]==pytest.approx(.3)
            clock[0]+=.4
    assert not result['stages'][-1]['complete']
    with pytest.raises(ValueError):
        with stages.stage('candidate_sense_audit'):pass


@pytest.mark.parametrize('target,defect',[('source','partial'),('candidate','partial'),
    ('source','unbound'),('candidate','wrong_family'),('candidate','physics')])
def test_raw_audits_survive_refusal_and_no_partial_unbound_or_physical_change_is_laundered(tmp_path,monkeypatch,target,defect):
    d=fixture(tmp_path,monkeypatch);child=save_candidate(d,tmp_path);original=aux.sense.replay
    seen=[]
    def replay(path,**kw):
        assert 0<kw['timeout_s']<=10
        q=original(path,**kw)
        label='source' if Path(path)==d['path'] else 'candidate'
        if label==target:
            if defect=='partial':q.update(complete=False,stop='deadline_exhausted')
            elif defect=='unbound':q['identity_stable']=False
            elif defect=='wrong_family':q['source_family_after']={'unreceived':'family'}
            else:q['lineage']['inputs']=1
        seen.append((label,deepcopy(q)));return q
    monkeypatch.setattr(aux.sense,'replay',replay)
    packet=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert not packet['ok'] and not packet['complete'] and not packet['identity_stable']
    assert packet['sense_audits']==dict(seen)
    assert packet['sense_audits'][target]==dict(seen)[target]
    if defect=='partial':
        assert packet['sense_audits'][target]['complete'] is False
        assert any('sense_evidence_incomplete:deadline_exhausted' in e for e in packet['errors'])
    elif defect=='physics':
        assert packet['stages'][-1]['name']=='sense_comparison'
        assert not packet['sense_preservation']['same_evidence']
    else:assert any('saved_identity_unbound' in e for e in packet['errors'])


@pytest.mark.parametrize('angle,via',[(0,False),(90,True)])
def test_native_sense_cohort_requires_the_exact_added_trace_and_via_manifest(tmp_path,monkeypatch,angle,via):
    d=fixture(tmp_path,monkeypatch,context='native_sense_'+str(angle),via=via)
    board=pcbnew.LoadBoard(str(d['path']));feed=d['decl']['net'];net=board.FindNet(feed)
    load_name=feed+'_RETURN';load=pcbnew.NETINFO_ITEM(board,load_name);board.Add(load)
    anchor=next(f for f in board.GetFootprints() if f.GetReference()==d['domain']['sink_refs'][0])
    anchor.SetFPID(pcbnew.LIB_ID('Resistor_SMD','Native_Shunt'));anchor.SetValue('0.001')
    def pad(fp,pin,n,xy,size=.6):
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber(pin);p.SetNet(n);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(size,size));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy));return p
    pad(anchor,'8',load,(20,24),1.8)
    sensor=pcbnew.FOOTPRINT(board);sensor.SetReference('arbitrary_sensor');sensor.SetValue('INA240A3DR')
    sensor.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'));board.Add(sensor)
    pad(sensor,'8',net,(22,13));pad(sensor,'1',load,(22,21))
    outlet=pcbnew.FOOTPRINT(board);outlet.SetReference('unrelated_load_port');outlet.SetValue('outlet');board.Add(outlet)
    pad(outlet,'9',load,(20,28))
    def trace(n,a,b,w):
        t=pcbnew.PCB_TRACK(board);t.SetNet(n);t.SetLayer(pcbnew.F_Cu);t.SetWidth(round(w*1e6))
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t)
    next(t for t in board.GetTracks() if force._uid(t)==d['trunk']).SetWidth(600000)
    for n,points in ((net,[(20,10),(20,12),(21,13),(22,13)]),(load,[(20,24),(20,22),(21,21),(22,21)])):
        for a,b in zip(points,points[1:]):trace(n,a,b,.2)
    trace(load,(20,24),(20,28),.6)
    domains={feed:d['domain'],load_name:dict(net=load_name,complete=True,missing_refs=[],
        source_refs=[anchor.GetReference()],sink_refs=[outlet.GetReference()],
        authority_refs=[anchor.GetReference(),outlet.GetReference()])}
    monkeypatch.setattr(aux.topology,'board_current_domains',lambda *a,**k:deepcopy(domains))
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(17.5,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    field._save_field_snapshot(board,d['path']);child=save_candidate(d,tmp_path)
    packet=aux.receive(d['path'],child,d['decl']['id'],board_hint=str(d['root']))
    assert packet['ok'] and packet['complete'],packet['errors']
    for raw in packet['sense_audits'].values():
        assert raw['clipped_isolation']['passed']==2 and raw['same_net_connectivity']['passed']==2
    a,b=packet['sense_audits']['source'],packet['sense_audits']['candidate']
    missing=aux.sense.compare_contour_preservation(a,b,modified_nets=[feed])
    assert missing['comparison_complete'] and not missing['same_evidence']
    assert packet['sense_preservation']['same_evidence']
