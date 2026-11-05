import json
import pytest
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
from shapely.geometry import Point,mapping
from cec_assembly_envelope import vent_reservations,policy_check


def test_vent_keepout_blocks_copper_not_only_components():
    b=pcbnew.BOARD()
    vents=[dict(ref='reservoir',xy=mapping(Point(8,9).buffer(3)))]
    assert not vent_reservations(b,vents)[0]['ok']
    assert vent_reservations(b,vents,install=True)[0]['ok']
    z=next(iter(b.Zones()));z.SetDoNotAllowTracks(False)
    assert not vent_reservations(b,vents)[0]['ok']


def test_vent_projected_move_invalidates_old_reservation():
    b=pcbnew.BOARD()
    vent_reservations(b,[dict(ref='cap',xy=mapping(Point(0,0).buffer(3)))],install=True)
    assert not vent_reservations(b,[dict(ref='cap',xy=mapping(Point(1,0).buffer(3)))])[0]['ok']


def test_vent_copper_cannot_hide_under_keepout():
    b=pcbnew.BOARD();vents=[dict(ref='cap',xy=mapping(Point(8,9).buffer(3)))]
    vent_reservations(b,vents,install=True)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(7,9));t.SetEnd(pcbnew.VECTOR2I_MM(9,9))
    t.SetWidth(pcbnew.FromMM(.25));t.SetLayer(pcbnew.F_Cu);b.Add(t)
    r=vent_reservations(b,vents)[0]
    assert r['native_rule_covers'] and r['copper_hits'] and not r['ok']


def test_inner_copper_is_not_facing_surface_copper():
    b=pcbnew.BOARD();vents=[dict(ref='cap',xy=mapping(Point(8,9).buffer(3)))]
    vent_reservations(b,vents,install=True)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(7,9));t.SetEnd(pcbnew.VECTOR2I_MM(9,9))
    t.SetWidth(pcbnew.FromMM(.25));t.SetLayer(pcbnew.B_Cu);b.Add(t)
    assert vent_reservations(b,vents)[0]['ok']


def test_changed_peer_refuses_before_geometry(tmp_path):
    (tmp_path/'peer.kicad_pcb').write_text('changed')
    (tmp_path/'contract.json').write_text('{}')
    (tmp_path/'pair.json').write_text(json.dumps(dict(cover=dict(path='peer.kicad_pcb',sha256='old'))))
    with pytest.raises(ValueError,match='hash mismatch'):
        policy_check(None,dict(role='carrier',contract='contract.json',pair='pair.json'),tmp_path)


def test_native_wxstring_policy_survives_temporary_filename(monkeypatch):
    import cec_constraints as c
    import cec_assembly_envelope as env
    b=pcbnew.BOARD();props=b.GetProperties()
    props['CEC_ASSEMBLY_POLICY']=json.dumps(dict(role='carrier',contract='c',pair='p'))
    b.SetProperties(props)
    seen=[]
    monkeypatch.setattr(env,'policy_check',lambda board,p,root:seen.append(p) or {'ok':True})
    assert c._chk_paired_assembly_envelope(b,'/tmp/renamed-board.kicad_pcb',{})[0] is True
    assert seen[0]['role']=='carrier'


def test_failed_vent_subgate_is_reported_not_clean_hardware(monkeypatch):
    import cec_constraints as c
    import cec_assembly_envelope as env
    b=pcbnew.BOARD();props=b.GetProperties()
    props['CEC_ASSEMBLY_POLICY']=json.dumps(dict(role='carrier',contract='c',pair='p'))
    b.SetProperties(props)
    result=dict(ok=False,violations=[],missing=[],hardware=[dict(ok=True)],
                vent_reservations=[dict(ref='RESERVOIR',native_rule_covers=False,ok=False)])
    monkeypatch.setattr(env,'policy_check',lambda *args:result)
    passed,detail=c._chk_paired_assembly_envelope(b,'/tmp/renamed.kicad_pcb',{})
    assert not passed and 'vent_reservations' in detail and 'RESERVOIR' in detail
    assert 'hardware' not in detail


def test_moving_cover_vent_checks_reservation_on_pinned_carrier(tmp_path,monkeypatch):
    import hashlib
    import cec_assembly_envelope as env
    import cec_stack_fit_screen
    carrier=pcbnew.BOARD();cover=pcbnew.BOARD()
    vent_reservations(carrier,[dict(ref='RESERVOIR',xy=mapping(Point(8,9).buffer(3)))],install=True)
    peer_path=tmp_path/'peer.kicad_pcb';pcbnew.SaveBoard(str(peer_path),carrier)
    (tmp_path/'pair.json').write_text(json.dumps(dict(carrier=dict(path=peer_path.name,
        sha256=hashlib.sha256(peer_path.read_bytes()).hexdigest()))))
    (tmp_path/'contract.json').write_text(json.dumps(dict(transform=[-1,0,0,1,30,0],vertical={})))
    def evaluated(*args):
        return dict(ok=True,vents=[dict(side='cover',ref='RESERVOIR',
            xy=mapping(Point(9,9).buffer(3)))]),[]
    monkeypatch.setattr(env,'evaluate_boards',evaluated)
    monkeypatch.setattr(cec_stack_fit_screen,'vertical_screen',lambda **kw:dict(ok=True))
    result=env.policy_check(cover,dict(role='cover',contract='contract.json',pair='pair.json'),tmp_path)
    assert not result['ok']
    assert result['vent_reservations'][0]['receiver']=='carrier'
    assert not result['vent_reservations'][0]['native_rule_covers']


def test_assembly_failure_cannot_be_deferred_to_local_copper_repair():
    import cec_synth_pipeline as synth
    clean=dict(ok=True,paired_assembly=dict(ok=True,violations=[]))
    blocked=dict(ok=False,paired_assembly=dict(ok=False,violations=[]),
                 decoupler=dict(violations=[('BYPASS','local-cell-access')]))
    assert synth.placement_craft_key(clean)<synth.placement_craft_key(blocked)
    gate=synth.placement_craft_admission(blocked,allow_route_access_repair=True)
    assert not gate['ok'] and 'paired_assembly placement evidence failed' in gate['blockers']


def reservation_fixture(tmp_path,monkeypatch):
    import cec_assembly_envelope as env
    from shapely.geometry import box
    b=pcbnew.BOARD();policy=dict(role='carrier',contract='geometry.json',pair='pair.json')
    props=b.GetProperties();props['CEC_ASSEMBLY_POLICY']=json.dumps(policy);b.SetProperties(props)
    vents=[dict(ref='renamed-storage-part',side='cover',xy=mapping(Point(8,9).buffer(3)))]
    env.vent_reservations(b,vents,install=True);guard=next(iter(b.Zones()))
    guard.SetZoneName('a name with no product-specific meaning')
    old=pcbnew.ZONE(b);old.SetIsRuleArea(True);old.SetLayer(pcbnew.F_Cu)
    old.SetDoNotAllowFootprints(True);old.SetDoNotAllowTracks(False)
    old.SetDoNotAllowVias(False);old.SetDoNotAllowZoneFills(False)
    out=old.Outline();out.NewOutline()
    for x,y in list(box(3,4,13,14).exterior.coords)[:-1]:out.Append(round(x*1e6),round(y*1e6))
    b.Add(old)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    (tmp_path/'geometry.json').write_text(json.dumps(dict(transform=[-1,0,0,1,25,3])))
    (tmp_path/'pair.json').write_text(json.dumps(dict(cover=dict(path=source.name))))
    monkeypatch.setattr(env,'policy_check',lambda *a:dict(ok=True,authority_unchanged=True,vents=vents))
    updates=[dict(reservation_uuid=old.m_Uuid.AsString(),replacement_guard_uuid=guard.m_Uuid.AsString())]
    return b,old,guard,source,updates,env


def test_explicit_reservation_reconciliation_uses_native_guard_not_names(tmp_path,monkeypatch):
    b,old,guard,source,updates,env=reservation_fixture(tmp_path,monkeypatch)
    source_bytes=source.read_bytes();original_guard=guard.Outline().Format()
    receipt=env.reconcile_placement_reservations(b,source_path=source,updates=updates,root=tmp_path)
    assert receipt['ok'] and receipt['all_current_vent_guards_unchanged']
    assert old.Outline().Format()==original_guard==guard.Outline().Format()
    assert old.GetDoNotAllowFootprints() and not old.GetDoNotAllowTracks()
    assert receipt['updates'][0]['opposing_vent_ref']=='renamed-storage-part'
    assert source.read_bytes()==source_bytes and not receipt['routing_admitted']


@pytest.mark.parametrize('fault',['copper_rule','missing_guard_rule','locked','other_face',
    'unknown_uuid','duplicate','changed_policy','unadmitted_source','ambiguous_vent',
    'authority_changed','not_contained'])
def test_reservation_transition_refuses_incomplete_or_unbound_authority(tmp_path,monkeypatch,fault):
    b,old,guard,source,updates,env=reservation_fixture(tmp_path,monkeypatch)
    if fault=='copper_rule':old.SetDoNotAllowVias(True)
    elif fault=='missing_guard_rule':guard.SetDoNotAllowTracks(False)
    elif fault=='locked':old.SetLocked(True)
    elif fault=='other_face':old.SetLayer(pcbnew.B_Cu)
    elif fault=='unknown_uuid':updates[0]['reservation_uuid']='unknown'
    elif fault=='duplicate':updates=updates+updates
    elif fault=='changed_policy':
        props=b.GetProperties();props['CEC_ASSEMBLY_POLICY']='{}';b.SetProperties(props)
    elif fault=='unadmitted_source':
        monkeypatch.setattr(env,'policy_check',lambda *a:dict(ok=False,authority_unchanged=True))
    elif fault=='ambiguous_vent':
        vent=dict(side='cover',xy=mapping(Point(8,9).buffer(3)))
        monkeypatch.setattr(env,'policy_check',lambda *a:dict(ok=True,authority_unchanged=True,
            vents=[dict(vent,ref='one'),dict(vent,ref='two')]))
    elif fault=='authority_changed':
        def changed(*args):
            (tmp_path/'geometry.json').write_text('{"transform":[-1,0,0,1,26,3]}')
            return dict(ok=True,authority_unchanged=True,
                vents=[dict(ref='renamed',side='cover',xy=mapping(Point(8,9).buffer(3)))])
        monkeypatch.setattr(env,'policy_check',changed)
    else:guard.Move(pcbnew.VECTOR2I_MM(4,0))
    original={z.m_Uuid.AsString():z.Outline().Format() for z in b.Zones()}
    with pytest.raises(ValueError):
        env.reconcile_placement_reservations(b,source_path=source,updates=updates,root=tmp_path)
    assert original=={z.m_Uuid.AsString():z.Outline().Format() for z in b.Zones()}


@pytest.mark.parametrize('receiver',['carrier','cover'])
def test_opposing_vent_projection_uses_real_flip_and_inverse(receiver):
    from shapely.geometry import shape
    from cec_assembly_envelope import facing_vents
    vents=[dict(side='cover',ref='a',xy=mapping(Point(8,9).buffer(3))),
           dict(side='carrier',ref='b',xy=mapping(Point(8,9).buffer(3)))]
    rows=facing_vents(dict(vents=vents),dict(transform=[-1,0,0,1,25,3]),receiver)
    assert len(rows)==1
    point=shape(rows[0]['xy']).centroid
    assert (point.x,point.y)==pytest.approx((8,9) if receiver=='carrier' else (17,6))


@pytest.mark.parametrize('back,tht,expected',[(False,False,False),(True,False,True),(True,True,False)])
def test_no_footprint_reservation_has_native_face_and_plated_land_coverage(back,tht,expected):
    import cec_assembly_envelope as env
    b=pcbnew.BOARD();env.vent_reservations(b,
        [dict(ref='guarded-volume',xy=mapping(Point(8,9).buffer(3)))],install=True)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('unrelated-fixture-name')
    fp.SetPosition(pcbnew.VECTOR2I_MM(8,9))
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if tht else pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.PTHMask() if tht else pcbnew.PAD.SMDMask())
    pad.SetPosition(fp.GetPosition())
    if tht:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    fp.Add(pad);b.Add(fp)
    if back:fp.Flip(fp.GetPosition(),False)
    result=env.footprint_reservation_check(b)
    assert result['ok'] is expected
