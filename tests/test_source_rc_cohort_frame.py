"""Native unfinished RC frames; no mocked pose/copper receiving authority."""
import copy
import json
from pathlib import Path
import uuid

import pcbnew
import pytest
import cec_force_current as force
import cec_synth_pipeline as synth
import root_source_rc_cohort_frame_20261025 as frame
from test_measurement_filter_span import fixture as observed_fixture, fixed_annotation


def fixture(tmp_path, monkeypatch, *, quarter=0):
    # Substitute only the existing fixture's fresh canonical CLI and current
    # authority boundaries. Actual part/pin/graph/map/pose checks stay native.
    f = observed_fixture(tmp_path, monkeypatch, quarter=quarter)
    b = f['board']
    ground = f['owner'].FindPadByNumber('2').GetNet()
    ground.SetNetname('GND')
    cap = pcbnew.FOOTPRINT(b); cap.SetReference('C_renamed_local')
    cap.SetValue('100nF'); cap.SetField('MPN', 'CL05B104KO5NNNC')
    cap.SetFPID(pcbnew.LIB_ID('cec-Capacitor_SMD', 'C_0402_1005Metric')); b.Add(cap)
    vs = f['owner'].FindPadByNumber('6'); at = vs.GetPosition()
    cap.SetPosition(pcbnew.VECTOR2I(at.x+500000, at.y+2000000))
    for num, net, dx in [('1', vs.GetNet(), 0), ('2', ground, 1000000)]:
        p = pcbnew.PAD(cap); p.SetNumber(num); p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I(400000, 400000))
        p.SetPosition(pcbnew.VECTOR2I(at.x+dx, at.y+2000000)); p.SetPinType('passive'); cap.Add(p)
    negative = []
    for a, z in [((8,10),(6,10)), ((6,10),(6,14)), ((6,14),(6,18)),
                 ((6,18),(6,20)), ((6,20),(7,20)), ((6,18),(9,18))]:
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(*a)); t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetLayer(pcbnew.F_Cu); t.SetWidth(250000)
        t.SetNet(f['owner'].FindPadByNumber('1').GetNet()); t.SetLocked(True)
        t.Rotate(pcbnew.VECTOR2I_MM(20,20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        b.Add(t); negative.append(t)
    supply = []
    points = [at, pcbnew.VECTOR2I(at.x, at.y+1000000), cap.FindPadByNumber('1').GetPosition()]
    for a, z in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(a); t.SetEnd(z); t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(500000); t.SetNet(vs.GetNet()); t.SetLocked(True); b.Add(t); supply.append(t)
    pcbnew.SaveBoard(str(f['source']), b)
    libraries = []; symbols = []; components = []; nodes = {}
    def quote(value):
        return json.dumps(value, ensure_ascii=False)
    for j, fp in enumerate(b.GetFootprints()):
        ref = fp.GetReference(); uid = str(uuid.uuid4()); lib = 'P'+str(j)
        props = dict(Reference=ref, Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
                     MPN=fp.GetField('MPN').GetText())
        pins = []
        for i, p in enumerate(fp.Pads()):
            pins.append('(pin '+p.GetPinType()+' line (at '+str(i)+' 0 0) (length 1) '
                        '(name "~") (number '+quote(p.GetNumber())+'))')
            nodes.setdefault(p.GetNetname(), []).append((ref, p.GetNumber()))
        libraries.append('(symbol "fixture:'+lib+'" (symbol "'+lib+'_1_1" '+' '.join(pins)+'))')
        symbols.append('(symbol (lib_id "fixture:'+lib+'") (at '+str(j*100)+' 0 0) '
                       '(unit 1) (uuid '+quote(uid)+') '+' '.join(
                           '(property '+quote(k)+' '+quote(v)+')' for k,v in props.items())+')')
        components.append('(comp (ref '+quote(ref)+') (value '+quote(props['Value'])+') '
            '(footprint '+quote(props['Footprint'])+') (property (name "MPN") (value '+quote(props['MPN'])+')) '
            '(tstamps '+quote(uid)+'))')
    f['schematic'].write_text('(kicad_sch (version 20250114) (uuid '+quote(str(uuid.uuid4()))+') '
        '(lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+')')
    f['tree'][:] = synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join(
        '(net (name '+quote(n)+') '+' '.join('(node (ref '+quote(r)+') (pin '+quote(p)+'))'
        for r,p in members)+')' for n,members in nodes.items())+'))')
    f.update(bypass=cap, negative=negative, supply=supply)
    return f


def plan(f):
    return frame.plan(f['board'], f['source'], board_hint=f['hint'],
                      owner_uuid=force._uid(f['owner']), delta_nm=[0, -500000])


@pytest.mark.parametrize('quarter', range(4))
def test_renamed_cardinal_complete_branched_nodes_and_supply_frame(tmp_path, monkeypatch, quarter):
    f = fixture(tmp_path, monkeypatch, quarter=quarter); raw = f['source'].read_bytes()
    q = plan(f)
    assert len(q['footprint_uuids']) == 5 and len(q['internal_track_uuids']) == 11
    assert len(q['retained_local_supply_graph']['track_uuids']) == 2
    b, proof = frame.project(f['source'], q)
    candidate = frame.save_diagnostic(f['source'], b, proof, tmp_path/'unfinished')
    received = frame.receive_frame(f['source'], candidate, q)
    assert received['ok'] and received['complete']
    assert not any(received[k] for k in ('routing_admitted','current_qualified',
        'return_qualified','kelvin_qualified','release_authority'))
    assert received['mandatory_contacts_current_field_native_and_measurement_receiving_pending']
    assert f['source'].read_bytes() == raw
    for uid in q['internal_track_uuids']+q['retained_local_supply_graph']['track_uuids']:
        old = next(t for t in f['board'].GetTracks() if force._uid(t) == uid)
        new = next(t for t in b.GetTracks() if force._uid(t) == uid)
        assert tuple(new.GetStart()) == (old.GetStart().x, old.GetStart().y-500000)
        assert tuple(new.GetEnd()) == (old.GetEnd().x, old.GetEnd().y-500000)
        assert old.GetWidth() == new.GetWidth() and old.IsLocked() == new.IsLocked()


@pytest.mark.parametrize('fault', ['partial_member','nonrigid','missing_edge','new_role',
                                  'forged_supply_graph','wider_scope'])
def test_worker_packets_cannot_authorize_poses_roles_or_copper(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch); q = plan(f)
    if fault == 'partial_member':q['footprint_uuids'].pop()
    elif fault == 'nonrigid':next(iter(q['target_poses'].values()))[0] += .1
    elif fault == 'missing_edge':q['internal_track_uuids'].pop()
    elif fault == 'new_role':q['current_qualified'] = True
    elif fault == 'forged_supply_graph':q['retained_local_supply_graph']['track_uuids'] = []
    elif fault == 'wider_scope':q['footprint_uuids'].append(force._uid(f['board'].FindFootprintByReference('load_terminal')))
    with pytest.raises(ValueError, match='fresh_exact_Source_RC_frame_required'):
        frame.project(f['source'], q)


@pytest.mark.parametrize('fault', ['width','lock','net','extra_edge','unowned_part'])
def test_saved_frame_receiving_rederives_exact_delta(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch); q = plan(f)
    b, proof = frame.project(f['source'], q)
    candidate = frame.save_diagnostic(f['source'], b, proof, tmp_path/'unfinished')
    uid = q['internal_track_uuids'][0]
    old = next(t for t in b.GetTracks() if force._uid(t) == uid)
    if fault == 'width':old.SetWidth(300000)
    elif fault == 'lock':old.SetLocked(not old.IsLocked())
    elif fault == 'net':old.SetNet(f['owner'].FindPadByNumber('6').GetNet())
    elif fault == 'unowned_part':b.FindFootprintByReference('load_terminal').Move(pcbnew.VECTOR2I(100000,0))
    elif fault == 'extra_edge':
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(90,90)); t.SetEnd(pcbnew.VECTOR2I_MM(91,90))
        t.SetLayer(pcbnew.F_Cu); t.SetWidth(250000); t.SetNet(old.GetNet()); b.Add(t)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate), b)
    received = frame.receive_frame(f['source'], candidate, q)
    assert not received['ok'] and not received['routing_admitted']


def test_literal_translation_preserves_unknown_metadata_comments_and_locks():
    raw = '(segment (start 1 2) (end 3 4) (width .25) (locked yes) ;keep\n (unknown "x") (uuid "a"))'
    moved = frame._literal_translation(raw, [500000, -250000])
    assert moved == raw.replace('(start 1 2)', '(start 1.5 1.75)').replace('(end 3 4)', '(end 3.5 3.75)')


def test_multiple_closed_Source_maps_transport_in_one_unmodified_Source_preflight(tmp_path,monkeypatch):
    f = fixture(tmp_path,monkeypatch)
    # Two short renamed references fit the fixture's small native court;
    # do not reduce text size or bypass the readable-leader checks.
    first = f['owner'].GetReference(); f['owner'].SetReference('K9')
    f['schematic'].write_text(f['schematic'].read_text().replace('"'+first+'"','"K9"'))
    def rename(node):
        return [rename(v) for v in node] if isinstance(node,list) else 'K9' if node == first else node
    f['tree'][:] = rename(f['tree'])
    fixed_annotation(f)
    second = fixed_annotation(dict(f,cap=f['owner']))
    # The reusable small-court fixture draws at one fixed location. Put this
    # second synthetic court and its guides around its own owner; otherwise
    # native loading rightly deduplicates coincident board strokes.
    delta = pcbnew.VECTOR2I(f['owner'].GetPosition().x-9500000,
                          f['owner'].GetPosition().y-18000000)
    for item in f['owner'].GraphicalItems():
        if item.GetLayer() == pcbnew.F_CrtYd:
            item.Move(delta)
    for item in second.GetItems():
        if item.GetClass() != 'FOOTPRINT':
            item.Move(delta)
    pcbnew.SaveBoard(str(f['source']),f['board'])
    # This test starts from the actual saved board, including KiCad's native
    # reference-field serialization, not the producer's pre-save proxies.
    f['board'] = pcbnew.LoadBoard(str(f['source']))
    q = plan(f)
    assert len(q['reference_maps']) == 2
    b, proof = frame.project(f['source'],q)
    candidate = frame.save_diagnostic(f['source'],b,proof,tmp_path/'mapped-frame')
    r = frame.receive_frame(f['source'],candidate,q)
    assert r['ok'] and r['complete'],r['errors']


@pytest.mark.parametrize('delta', [[True,0],[0,0],[6000001,0],[1.0,0]])
def test_nonliteral_or_unbounded_translation_refuses(tmp_path, monkeypatch, delta):
    f = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='explicit_nonzero_bounded_rigid_RC_translation_required'):
        frame.plan(f['board'], f['source'], board_hint=f['hint'],
                   owner_uuid=force._uid(f['owner']), delta_nm=delta)
