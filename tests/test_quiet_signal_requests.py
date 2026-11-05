"""Real native/source identity; only fresh CLI export boundary is substituted."""
import hashlib
import json
import uuid
import pcbnew
import pytest
import cec_quiet_signal_requests as op
import cec_source_ground_leaf as source_roles
import cec_synth_pipeline as synth
import cec_force_current as force
from test_source_ground_leaf import module_fixture


def fixture(tmp_path, monkeypatch, *, quarter=0, back=False, pw=False):
    board, module = module_fixture(quarter=quarter, back=back)
    sensor = pcbnew.FOOTPRINT(board); board.Add(sensor)
    sensor.SetReference('arbitrary_amplifier'); sensor.SetValue('INA240A3')
    sensor.SetField('MPN', 'INA240A3PWR' if pw else 'INA240A3DR')
    sensor.SetFPID(pcbnew.LIB_ID('cec-Package_SO',
        'TSSOP-8_3x3mm_P0.65mm' if pw else 'SOIC-8_3.9x4.9mm_P1.27mm'))
    for n in range(1, 9):
        pad = pcbnew.PAD(sensor); pad.SetNumber(str(n)); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5));
        pad.SetPosition(pcbnew.VECTOR2I_MM(n, 12)); sensor.Add(pad)
    sensor.SetOrientationDegrees(quarter * 90)
    if back: sensor.Flip(pcbnew.VECTOR2I(0, 0), False)
    nets = {}
    for name in ['GND', '+3V3', '/renamed_quiet']:
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    grounds = {'1', '2', '42', '43'} | {str(n) for n in range(46, 66)}
    for pad in module.Pads():
        if pad.GetNumber() in grounds: pad.SetNet(nets['GND'])
        elif pad.GetNumber() == '3': pad.SetNet(nets['+3V3'])
    output = sensor.FindPadByNumber('8' if pw else '5'); target = module.FindPadByNumber('5')
    for pad, typ, name in [(output, 'output', 'OUT'), (target, 'bidirectional', 'IO1')]:
        pad.SetNet(nets['/renamed_quiet']); pad.SetPinType(typ); pad.SetPinFunction(name)
    pcb = tmp_path / 'source.kicad_pcb'; board.SetFileName(str(pcb))
    pcbnew.SaveBoard(str(pcb), board)
    library = []; symbols = []; components = []; native_nets = {}
    for j, fp in enumerate([sensor, module]):
        ref = fp.GetReference(); uid = str(uuid.uuid4()); lib = 'Part' + str(j)
        props = dict(Reference=ref, Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
            MPN=fp.GetField('MPN').GetText())
        pins = []
        for i, pad in enumerate(fp.Pads()):
            typ = pad.GetPinType() or 'passive'; name = pad.GetPinFunction() or 'P' + pad.GetNumber()
            pins.append('(pin ' + typ + ' line (at ' + str(i) + ' 0 0) (length 1.27) (name "' + name + '") (number "' + pad.GetNumber() + '"))')
            if pad.GetNetname(): native_nets.setdefault(pad.GetNetname(), []).append((ref, pad.GetNumber()))
        library.append('(symbol "fixture:' + lib + '" (symbol "' + lib + '_1_1" ' + ' '.join(pins) + '))')
        symbols.append('(symbol (lib_id "fixture:' + lib + '") (at ' + str(j * 100) + ' 0 0) (unit 1) (uuid "' + uid + '") ' + ' '.join('(property "' + k + '" "' + v + '")' for k, v in props.items()) + ')')
        components.append('(comp (ref "' + ref + '") (value "' + props['Value'] + '") (footprint "' + props['Footprint'] + '") (property (name "MPN") (value "' + props['MPN'] + '")) (tstamps "' + uid + '"))')
    root = tmp_path / 'root.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "' + str(uuid.uuid4()) + '") (lib_symbols ' + ' '.join(library) + ') ' + ' '.join(symbols) + ')')
    tree = synth.parse_sexpr('(export (components ' + ' '.join(components) + ') (nets ' + ' '.join('(net (name "' + n + '") ' + ' '.join('(node (ref "' + r + '") (pin "' + p + '"))' for r, p in members) + ')' for n, members in native_nets.items()) + '))')
    exporter = tmp_path / 'exporter'; exporter.write_bytes(b'fixture compiler boundary')
    def export(path, deadline):
        return tree, dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            exporter=str(exporter), exporter_sha256=force._hash(exporter))
    monkeypatch.setattr(source_roles, '_export', export)
    # Project resolver boundary, not physical/role/source-identity receiver.
    spec = dict(name='Sense', track_width=.2, clearance=.2,
        dimension_contract=dict(board_limits_mm=dict(track_width=.2)))
    monkeypatch.setattr(op.fr, '_project_netclass_resolver', lambda *a, **kw: lambda n: spec)
    return board, pcb, root, tree, spec, output, target


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('pw', [False, True])
def test_fresh_typed_requests_preserve_pose_source_and_no_ratings(tmp_path, monkeypatch, quarter, back, pw):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch, quarter=quarter, back=back, pw=pw)
    before = op.row._source_binding(board); raw = pcb.read_bytes()
    q = op.plan(board, pcb, board_hint=str(root))
    assert q['complete'] and not q['errors'], q
    assert len(q['requests']) == 1, q
    request = q['requests'][0]
    assert request['net'] == '/renamed_quiet' and request['width_nm'] == 200000
    assert request['root_pad_uuid'] == force._uid(output)
    assert request['target_pad_uuid'] == force._uid(target)
    assert request['target']['manufacturer']['adc_capable']
    assert not request['current_authority'] and not request['adc_mode_qualified']
    assert not q['admission_authority'] and op.bindings_current(q)
    assert before == op.row._source_binding(board) and raw == pcb.read_bytes()


@pytest.mark.parametrize('fault', ['class', 'current', 'pair', 'extra', 'mpn', 'output_pin',
    'native_pin', 'source_type', 'source_name', 'source_uuid', 'source_net', 'native_stale',
    'source_epoch', 'exporter_epoch', 'dnp', 'ground', 'missing_source'])
def test_no_requests_from_untyped_or_stale_authority(tmp_path, monkeypatch, fault):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    if fault == 'class': spec['name'] = 'Default'
    elif fault == 'current': monkeypatch.setattr(op.synth, 'spec_net_current_contract', lambda *a, **k: {'amps': 1})
    elif fault == 'pair': monkeypatch.setattr(op.fr, 'coupled_pair_nets', lambda b: {'/renamed_quiet'})
    elif fault == 'extra':
        pad = pcbnew.PAD(target.GetParentFootprint()); pad.SetNumber('99'); pad.SetNet(target.GetNet()); target.GetParentFootprint().Add(pad)
    elif fault == 'mpn': output.GetParentFootprint().SetField('MPN', 'INA240A3PWR')
    elif fault == 'output_pin': output.SetNumber('8')
    elif fault == 'native_pin': target.SetPinFunction('USB_D-')
    elif fault == 'source_type': root.write_text(root.read_text().replace('(pin output ', '(pin input '))
    elif fault == 'source_name': root.write_text(root.read_text().replace('(name "OUT")', '(name "IN+")'))
    elif fault == 'source_uuid':
        synth._first(list(synth._kids(synth._first(tree, 'components'), 'comp'))[0], 'tstamps')[1] = str(uuid.uuid4())
    elif fault == 'source_net':
        for net in synth._kids(synth._first(tree, 'nets'), 'net'):
            if synth._val(net, 'name', '') == '/renamed_quiet': net.append(['node', ['ref', 'unknown'], ['pin', '1']])
    elif fault == 'native_stale': target.SetPosition(pcbnew.VECTOR2I_MM(99, 99))
    elif fault in ('source_epoch', 'exporter_epoch'):
        original = source_roles._export
        def export(path, deadline):
            result = original(path, deadline)
            changed = root if fault == 'source_epoch' else tmp_path / 'exporter'
            changed.write_bytes(changed.read_bytes() + b'\n')
            return result
        monkeypatch.setattr(source_roles, '_export', export)
    elif fault == 'dnp': output.GetParentFootprint().SetDNP(True)
    elif fault == 'ground': target.SetNet(board.GetNetInfo().GetNetItem('GND'))
    else: pcb.unlink()
    if fault in ('extra', 'mpn', 'output_pin', 'native_pin', 'dnp', 'ground'):
        pcbnew.SaveBoard(str(pcb), board)
    q = op.plan(board, pcb, board_hint=str(root))
    assert not q['requests'], q


def test_json_request_and_per_request_binding_are_stable(tmp_path, monkeypatch):
    board, pcb, root, *_ = fixture(tmp_path, monkeypatch)
    q = op.plan(board, pcb, board_hint=str(root))
    encoded = json.dumps(q, sort_keys=True)
    assert json.loads(encoded)['requests'][0]['source_bindings'] == json.loads(encoded)['source_bindings']


def test_missing_native_annotations_use_mandatory_fresh_source_not_inference(tmp_path, monkeypatch):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    for pad in (output, target):
        pad.SetPinType(''); pad.SetPinFunction('')
    pcbnew.SaveBoard(str(pcb), board)
    q = op.plan(board, pcb, board_hint=str(root))
    assert q['complete'] and len(q['requests']) == 1, q
    root.write_text(root.read_text().replace('(name "OUT")', '(name "IN+")'))
    assert not op.plan(board, pcb, board_hint=str(root))['requests']


@pytest.mark.parametrize('endpoint', ['output', 'target'])
def test_nonempty_native_type_contradiction_refuses(tmp_path, monkeypatch, endpoint):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    (output if endpoint == 'output' else target).SetPinType('power_in')
    pcbnew.SaveBoard(str(pcb), board)
    assert not op.plan(board, pcb, board_hint=str(root))['requests']


@pytest.mark.parametrize('native_name', ['', '~', 'OUT'])
def test_explicit_unnamed_source_output_is_manufacturer_owned_not_named_out(tmp_path, monkeypatch, native_name):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    root.write_text(root.read_text().replace('(name "OUT")', '(name "~")'))
    output.SetPinType(''); output.SetPinFunction(native_name)
    pcbnew.SaveBoard(str(pcb), board)
    q = op.plan(board, pcb, board_hint=str(root))
    assert q['complete'] and len(q['requests']) == 1, q
    endpoint = q['requests'][0]['root']
    assert endpoint['actual_source_pin'] == dict(type='output', name='~')
    assert endpoint['manufacturer_function'] == 'OUT'
    assert endpoint['unnamed_source_placeholder'] is True
    root.write_text(root.read_text().replace('(name "~")', '(name "IN+")'))
    assert not op.plan(board, pcb, board_hint=str(root))['requests']


def test_named_source_cannot_authorize_native_unnamed_annotation(tmp_path, monkeypatch):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    output.SetPinFunction('~'); pcbnew.SaveBoard(str(pcb), board)
    assert not op.plan(board, pcb, board_hint=str(root))['requests']


def test_actual_saved_native_join_has_no_pending_request(tmp_path, monkeypatch):
    board, pcb, root, tree, spec, output, target = fixture(tmp_path, monkeypatch)
    track = pcbnew.PCB_TRACK(board); track.SetNetCode(output.GetNetCode())
    track.SetStart(output.GetPosition()); track.SetEnd(target.GetPosition())
    track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000); board.Add(track)
    pcbnew.SaveBoard(str(pcb), board)
    q = op.plan(board, pcb, board_hint=str(root))
    assert q['complete'] and not q['requests'] and not q['errors'], q


def test_actual_project_dimension_resolver_not_caller_width(tmp_path, monkeypatch):
    real = op.fr._project_netclass_resolver
    board, pcb, root, *_ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(op.fr, '_project_netclass_resolver', real)
    pcb.with_suffix('.kicad_pro').write_text(json.dumps(dict(
        board=dict(design_settings=dict(rules=dict(min_track_width=.2))),
        net_settings=dict(classes=[dict(name='Default', track_width=.22, clearance=.2),
            dict(name='Sense', track_width=.25, clearance=.3)],
            netclass_assignments={'/renamed_quiet':['Sense']}))))
    q = op.plan(board, pcb, board_hint=str(root))
    assert q['complete'] and len(q['requests']) == 1, q
    assert q['requests'][0]['width_nm'] == 250000
    assert q['requests'][0]['clearance_nm'] == 300000
    assert op.bindings_current(q)
    pcb.with_suffix('.kicad_pro').write_text('{}')
    assert not op.bindings_current(q)


@pytest.mark.parametrize('bad', [None, [], {}, 'old-netlist'])
def test_malformed_fresh_export_shape_refuses(tmp_path, monkeypatch, bad):
    board, pcb, root, *_ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(source_roles, '_export', lambda *a: ([], bad))
    q = op.plan(board, pcb, board_hint=str(root))
    assert not q['complete'] and not q['requests'] and q['errors']


@pytest.mark.parametrize('timeout', [True, False, 0, -1, 11, float('nan'), float('inf')])
def test_bounded_arguments(tmp_path, monkeypatch, timeout):
    board, pcb, root, *_ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError): op.plan(board, pcb, board_hint=str(root), timeout_s=timeout)
