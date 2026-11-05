"""Fresh canonical wired-address roles, not an address/power-pin alias.

The Source fixture uses the real selected-device/canonical-netlist owner.
Its explicit synthetic rail budget and project are fixture authority only.
No helper result is a complete prefix, clearance or saved-board admission.
"""
import copy
import hashlib
import json
import math

import pcbnew
import pytest

import cec_connected_address_supply_prefix as subject
import cec_current_topology as topology
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_force_current as force
import cec_source_ground_leaf as source
import cec_source_netlist_semantics as semantics
import cec_source_supply_endpoint_cut as cuts
from cec_native_items import create_empty_board, discard_items
from test_source_address_supply_chain_cut import case as address_case


def fixture(tmp_path, monkeypatch, *, face=pcbnew.F_Cu, turn=0,
            ref='WIRED_ADDRESS_OWNER', net='renamed_source_rail', retire=True,
            retained_group=False):
    # Establish the default project non-actively before the older fixture's
    # native BOARD constructor; never unload a still-live Source project.
    blank = create_empty_board()
    f = address_case(tmp_path, monkeypatch, face=face, turn=turn, offset=(21, 17))
    raw = f['board']; raw.SetCopperLayerCount(6)
    old_ref, old_net = f['owner'].GetReference(), f['address'].GetNetname()
    f['owner'].SetReference(ref)
    replacement = pcbnew.NETINFO_ITEM(raw, net); raw.Add(replacement)
    for item in [*(p for fp in raw.GetFootprints() for p in fp.Pads()), *raw.GetTracks()]:
        if item.GetNetname() == old_net:
            item.SetNet(replacement)
    def rename(node):
        if isinstance(node, list):
            return [rename(value) for value in node]
        return ref if node == old_ref else net if node == old_net else node
    tree = rename(f['tree'])
    root = f['root']
    root.write_text(root.read_text().replace(old_ref, ref).replace(old_net, net))
    exporter = tmp_path / 'fixture-exporter'
    exporter.write_bytes(b'explicit synthetic canonical exporter')
    monkeypatch.setattr(source, '_export', lambda *_a: (tree, dict(
        netlist_sha256=hashlib.sha256(json.dumps(tree).encode()).hexdigest(),
        exporter=str(exporter), exporter_sha256=force._hash(exporter), **semantics.metadata(tree))))
    profile = 'jlcpcb_6l_pofv_high_current'
    monkeypatch.setenv('CEC_FAB_PROFILE', profile)
    authority = dict(amps=.200772, geometry_margin=1., margin_included=True,
        source='explicit_synthetic_whole_rail_contract')
    physical = {lid: math.ceil(fab.ipc2221_required_width_mm(authority['amps'], name,
        profile_name=profile, margin=1., rise_c=30.)*1e6)
        for lid, name in fab.COPPER_LAYER_IDS.items()}
    contract = dict(profile=profile, current_authority=authority,
        required_by_layer_nm=physical)
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *_a: copy.deepcopy(contract))
    monkeypatch.setattr(topology, 'board_current_domains', lambda *_a, **_k: {net: dict(
        complete=True, amps=authority['amps'], source_refs=(ref,), sink_refs=('FIXTURE_SINK',),
        authority_refs=(ref, 'FIXTURE_SINK'), missing_refs=())})
    monkeypatch.setattr(topology, 'current_contract_for_net', lambda *_a, **_k: copy.deepcopy(authority))
    path = tmp_path / 'source.kicad_pcb'
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name='Default', track_width=.5, clearance=.2,
            via_diameter=.6, via_drill=.3)]))))
    if retained_group:
        group = pcbnew.PCB_GROUP(raw); raw.Add(group)
        group.SetName('RetainedClassThroat'); group.AddItem(f['carrier'])
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), raw)
    parent = pcbnew.LoadBoard(str(path)); posed = pcbnew.LoadBoard(str(path))
    delta = {0:(0, .4), 90:(.4, 0), 180:(0, -.4), 270:(-.4, 0)}[turn]
    posed.FindFootprintByReference(ref).Move(pcbnew.VECTOR2I_MM(*delta))
    cut, = cuts.plan(parent, posed, board_hint=str(root),
        source_floor=lambda _t:(500000, 200000), allow_locked=True)
    if retire:
        discard_items(posed, [t for t in posed.GetTracks() if force._uid(t) in cut['retired_track_uuids']])
    pad = posed.FindFootprintByReference(ref).FindPadByNumber('2')
    request = dict(kind='source_boundary', net=net,
        a=dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()), layers=[face]),
        b=dict(at_nm=cut['retained_throat_nm'], layers=[face],
            native_uuids=cut['retained_throat_track_uuids']),
        width_nm=cut['width_nm'], clearance_nm=cut['clearance_nm'],
        unchanged_full_rail_current_contract=copy.deepcopy(contract),
        source_supply_pad_contact_lead_restoration=copy.deepcopy(cut))
    # A genuine new narrow endpoint, not a renamed inherited Source item.
    new = pcbnew.PCB_TRACK(posed); new.SetNet(pad.GetNet()); new.SetLayer(face)
    new.SetStart(pad.GetPosition())
    new.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I(0, 400000))
    new.SetWidth(200000); posed.Add(new)
    fp = pad.GetParentFootprint()
    proposal = dict(scope='source_typed_complete_cell_escape_proposal', board_hint=str(root),
        poses={ref:[fp.GetPosition().x/1e6, fp.GetPosition().y/1e6, fp.GetOrientationDegrees()]})
    received = {net:dict(profile=profile, current_authority=copy.deepcopy(authority),
        authority_refs=['explicit_synthetic_source_domain'], routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.5, 'B.Cu':.5})}
    return dict(parent=parent, posed=posed, request=request, cut=cut, pad=pad, new=new,
        proposal=proposal, contracts=received, path=path, root=root, tree=tree,
        contract=contract, resources=(blank, f, raw, replacement, exporter))


def endpoint(f, **kwargs):
    return subject.endpoint_context(f['parent'], f['posed'], f['request'],
        board_hint=str(f['root']), timeout_s=9.1, **kwargs)


def receiver(f, *, scope=None):
    return subject.receiver_roles(f['parent'], f['posed'], f['proposal'], f['contracts'],
        track_uuid_scope=[force._uid(f['new'])] if scope is None else scope, timeout_s=9.1)


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('turn', [0, 90, 180, 270])
def test_real_source_connected_address_to_literal_throat_is_not_a_power_alias(tmp_path, monkeypatch, face, turn):
    f = fixture(tmp_path, monkeypatch, face=face, turn=turn,
        ref='OTHER_OWNER_'+str(turn), net='/OTHER_SCOPE/RAIL_'+str(face))
    before = f['path'].read_bytes(), copy.deepcopy(f['request'])
    context = endpoint(f)
    assert context['pad_uuid'] == force._uid(f['pad'])
    assert context['role'] == subject.ROLE and context['class_only_eligibility']
    assert context['retired_track_uuids'] == f['cut']['retired_track_uuids']
    assert not context['source_retirement_authority'] and not context['saved_candidate_authorized']
    assert not context['current_budget_lowered']
    assert receiver(f) == {force._uid(f['pad']):subject.ROLE}
    assert f['path'].read_bytes() == before[0] and f['request'] == before[1]
    import cec_full_current_supply_prefix as prefix
    assert prefix.supply_terminal_role(f['pad']) is None


def test_actual_saved_posed_child_rederives_role_and_json_request(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f['request'] = json.loads(json.dumps(f['request']))
    path = tmp_path / 'actual-child.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), f['posed'])
    child = pcbnew.LoadBoard(str(path)); f['posed'] = child
    assert endpoint(f)['pad_uuid'] == force._uid(f['pad'])
    assert receiver(f) == {force._uid(f['pad']):subject.ROLE}


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('change', [None, 'name', 'lock'])
def test_exact_concrete_native_throat_group_is_preserved(tmp_path, monkeypatch, face, change):
    f = fixture(tmp_path, monkeypatch, face=face, retained_group=True)
    group = next(g for g in f['posed'].Groups() if g.GetName() == 'RetainedClassThroat')
    if change == 'name':
        group.SetName('UnownedChangedGroup')
    elif change == 'lock':
        group.SetLocked(True)
    if change:
        with pytest.raises(ValueError, match='retained_throat_group_changed'):
            endpoint(f)
    else:
        assert endpoint(f)['pad_uuid'] == force._uid(f['pad'])
        assert receiver(f) == {force._uid(f['pad']):subject.ROLE}


@pytest.mark.parametrize('fault', ['cut_proof', 'cut_scope', 'partial_ids', 'a', 'b', 'throat_uuid',
    'width', 'clearance', 'current', 'bool_width', 'float_width', 'kind', 'net'])
def test_request_labels_or_copied_authority_never_supply_a_cut(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch); request = f['request']; cut = request['source_supply_pad_contact_lead_restoration']
    if fault == 'cut_proof':cut['source_authority']['power_input_pin'] = '2'
    elif fault == 'cut_scope':cut['source_authority']['scope'] = 'fresh_source_manufacturer_power_input'
    elif fault == 'partial_ids':cut['retired_track_uuids'] = cut['retired_track_uuids'][:1]
    elif fault == 'a':request['a']['at_nm'][0] += 1
    elif fault == 'b':request['b']['at_nm'][0] += 1
    elif fault == 'throat_uuid':request['b']['native_uuids'] = ['other-native-item']
    elif fault == 'width':request['width_nm'] -= 1
    elif fault == 'clearance':request['clearance_nm'] -= 1
    elif fault == 'current':request['unchanged_full_rail_current_contract']['current_authority']['amps'] /= 2
    elif fault == 'bool_width':request['width_nm'] = True
    elif fault == 'float_width':request['width_nm'] = float(request['width_nm'])
    elif fault == 'kind':request['kind'] = 'ordinary'
    else:request['net'] = 'another-rail'
    with pytest.raises(ValueError):endpoint(f)


@pytest.mark.parametrize('fault', ['retained_chain', 'partial_retirement', 'throat_width', 'throat_xy',
    'throat_lock', 'throat_group', 'pad_xy', 'pad_size', 'pad_mask', 'pad_pin', 'owner_mpn',
    'owner_role', 'source_ram', 'export_tie', 'source_tie', 'profile', 'factory_floor'])
def test_source_chain_rigid_lands_fixed_throat_and_process_are_not_caller_claims(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch, retire=fault not in ('retained_chain','partial_retirement'))
    if fault == 'partial_retirement':
        ids = f['cut']['retired_track_uuids'][:-1]
        discard_items(f['posed'], [t for t in f['posed'].GetTracks() if force._uid(t) in ids])
    elif fault.startswith('throat_'):
        throat = next(t for t in f['posed'].GetTracks() if force._uid(t) in f['cut']['retained_throat_track_uuids'])
        if fault == 'throat_width':throat.SetWidth(throat.GetWidth()+1)
        elif fault == 'throat_xy':throat.SetEnd(throat.GetEnd()+pcbnew.VECTOR2I(1, 0))
        elif fault == 'throat_lock':throat.SetLocked(not throat.IsLocked())
        else:
            g = pcbnew.PCB_GROUP(f['posed']); f['posed'].Add(g); g.SetName('changed-group'); g.AddItem(throat)
    elif fault == 'pad_xy':f['pad'].SetPosition(f['pad'].GetPosition()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_size':f['pad'].SetSize(f['pad'].GetSize()+pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_mask':f['pad'].SetLocalSolderMaskMargin(1)
    elif fault == 'pad_pin':f['pad'].SetPinFunction('different_function')
    elif fault == 'owner_mpn':f['pad'].GetParentFootprint().SetField('MPN','UNKNOWN')
    elif fault == 'owner_role':f['pad'].GetParentFootprint().SetValue('UNMODELED')
    elif fault == 'source_ram':
        old = next(t for t in f['parent'].GetTracks() if force._uid(t) in f['cut']['retired_track_uuids'])
        old.SetWidth(old.GetWidth()+1)
    elif fault == 'export_tie':
        import cec_synth_pipeline as synth
        for row in synth._kids(synth._first(f['tree'],'nets'),'net'):
            row[:] = [node for node in row if not (isinstance(node,list) and node and node[0]=='node'
                and synth._val(node,'pin','')=='2')]
    elif fault == 'source_tie':f['root'].write_text(f['root'].read_text().replace('(pin input line (at 2 ', '(pin output line (at 2 '))
    elif fault == 'profile':
        props = f['posed'].GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
        f['posed'].SetProperties(props)
    elif fault == 'factory_floor':f['posed'].GetDesignSettings().m_TrackMinWidth += 1
    with pytest.raises(ValueError):endpoint(f)


@pytest.mark.parametrize('fault', ['under_current', 'not_delta', 'missing_delta', 'no_scope',
    'wrong_net', 'wrong_face', 'not_narrow', 'wrong_owner', 'wrong_pose', 'contract_current',
    'contract_profile', 'contract_width'])
def test_receiver_roles_only_observes_actual_delta_narrow_source_launches(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch); scope = None
    if fault == 'under_current':f['new'].SetWidth(1)
    elif fault == 'not_delta':scope = f['cut']['retained_throat_track_uuids']
    elif fault == 'missing_delta':scope = ['missing-native-id']
    elif fault == 'no_scope':scope = []
    elif fault == 'wrong_net':f['new'].SetNet(f['posed'].FindFootprintByReference('WIRED_ADDRESS_OWNER').FindPadByNumber('7').GetNet())
    elif fault == 'wrong_face':f['new'].SetLayer(pcbnew.B_Cu)
    elif fault == 'not_narrow':f['new'].SetWidth(500000)
    elif fault == 'wrong_owner':f['proposal']['poses'] = {'OTHER':[0, 0, 0]}
    elif fault == 'wrong_pose':next(iter(f['proposal']['poses'].values()))[0] += .001
    elif fault == 'contract_current':next(iter(f['contracts'].values()))['current_authority']['amps'] /= 2
    elif fault == 'contract_profile':next(iter(f['contracts'].values()))['profile'] = 'jlcpcb_6l_pofv_signal'
    else:next(iter(f['contracts'].values()))['required_by_layer_mm']['F.Cu'] = .2
    if fault in ('not_delta', 'missing_delta', 'wrong_pose', 'contract_current', 'contract_profile', 'contract_width'):
        with pytest.raises(ValueError):receiver(f, scope=scope)
    else:
        assert receiver(f, scope=scope) == {}


def test_unrelated_delta_does_not_demand_retirement_of_an_untouched_wired_address(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, retire=False)
    # Actual new, ordinary-width metal elsewhere is not a connected-address
    # prefix. Retained Source address copper must remain outside this scope.
    f['new'].Move(pcbnew.VECTOR2I_MM(10, 10))
    assert receiver(f) == {}


@pytest.mark.parametrize('mutation', ['source_file','source_schematic','source_native','posed_native','exporter'])
def test_live_and_external_source_fences_run_on_return_and_refusal(tmp_path, monkeypatch, mutation):
    f = fixture(tmp_path, monkeypatch); derive = subject.cuts.plan
    def changed(*args, **kwargs):
        result = derive(*args, **kwargs)
        if mutation == 'source_file':f['path'].write_text(f['path'].read_text()+'\n')
        elif mutation == 'source_schematic':f['root'].write_text(f['root'].read_text()+'\n')
        elif mutation == 'source_native':f['parent'].FindFootprintByReference('WIRED_ADDRESS_OWNER').SetValue('CHANGED')
        elif mutation == 'posed_native':f['pad'].SetSize(f['pad'].GetSize()+pcbnew.VECTOR2I(1, 0))
        else:f['resources'][-1].write_bytes(b'changed exporter')
        return result
    monkeypatch.setattr(subject.cuts, 'plan', changed)
    with pytest.raises(ValueError):endpoint(f)


@pytest.mark.parametrize('seconds', [0, -1, True, float('inf'), float('nan'), 10.1])
def test_applicable_observer_has_no_unbounded_or_renewed_lease(tmp_path, monkeypatch, seconds):
    f = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        subject.endpoint_context(f['parent'], f['posed'], f['request'], board_hint=str(f['root']), timeout_s=seconds)


def test_legacy_unwired_and_non_address_requests_do_not_gain_this_role(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    assert subject.endpoint_context(f['parent'],f['posed'],{},board_hint=str(f['root'])) is None
    assert subject.receiver_roles(f['parent'],f['posed'],f['proposal'],f['contracts'],track_uuid_scope=()) == {}
    request = copy.deepcopy(f['request'])
    supply = f['posed'].FindFootprintByReference('WIRED_ADDRESS_OWNER').FindPadByNumber('6')
    request['a']['pad_uuid'] = force._uid(supply)
    assert subject.endpoint_context(f['parent'], f['posed'], request, board_hint=str(f['root'])) is None
