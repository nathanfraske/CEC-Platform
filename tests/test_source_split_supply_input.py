"""Two fixed supply ports are both due; neither arm funds a width waiver."""
import copy
import math

import pcbnew
import pytest

import cec_force_current as force
import cec_source_supply_endpoint_cut as cut
from test_source_device_supply_chain import fixture as single_case


def case(tmp_path, monkeypatch, *, face=0, turn=0, offset=(0, 0)):
    f = single_case(tmp_path, monkeypatch, face=face, turn=turn, offset=offset)
    c, s = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[turn]
    root = tuple(f['pad'].GetPosition())
    def point(x, y):
        dx, dy = x - 5., y - 5.
        return pcbnew.VECTOR2I(root[0] + round((c * dx + s * dy) * 1e6),
            root[1] + round((-s * dx + c * dy) * 1e6))
    lead = f['edge']((0, 0), (1, 0), .2)
    lead.SetStart(point(5, 5)); lead.SetEnd(point(5, 5.37))
    carrier = f['edge']((0, 0), (1, 0), .5, grouped=False)
    carrier.SetStart(point(5, 5.37)); carrier.SetEnd(point(4.4, 5.97))
    old = f['posed']
    def posed():
        board = old(); board.FindFootprintByReference('RENAMED').Move(
            pcbnew.VECTOR2I(round(s * 2e6), round(c * 2e6)))
        return board
    f.update(second_lead=lead, second_carrier=carrier, posed=posed, point=point)
    return f


def plan(f, **options):
    return cut.plan(f['board'], f['posed'](), board_hint=str(f['root']),
        source_floor=lambda t: (500000, 200000), allow_locked=True, **options)


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('turn', [0, 90, 180, 270])
def test_two_short_native_arms_each_keep_whole_current_and_fixed_carrier(tmp_path, monkeypatch, face, turn):
    f = case(tmp_path, monkeypatch, face=face, turn=turn, offset=(31, -7))
    state = lambda: {force._uid(t): (list(t.GetStart()), list(t.GetEnd()), t.GetWidth(),
        t.IsLocked(), bool(t.GetParentGroup())) for t in f['board'].GetTracks()}
    before = state(); rows = plan(f)
    assert len(rows) == 2 and state() == before
    assert {u for r in rows for u in r['retired_track_uuids']} == {
        force._uid(t) for t in [*f['chain'], f['second_lead']]}
    assert {u for r in rows for u in r['retained_throat_track_uuids']} == {
        force._uid(f['carrier']), force._uid(f['second_carrier'])}
    assert sum(t.GetLength() for t in [*f['chain'], f['second_lead']]) > 1500000
    for row in rows:
        proof = row['source_split_supply_input']
        assert proof['both_replacements_carry_whole_rail_current']
        assert not proof['current_sharing_assumed'] and proof['inherited_thin_copper_not_qualified']
        assert row['unchanged_full_rail_current_contract'] == f['contract']
        assert row['width_nm'] == 500000 and row['clearance_nm'] == 200000
        assert row['remaining_group_members'] == [force._uid(f['residue'])]
        assert row['source_authority']['scope'] == 'fresh_source_manufacturer_power_input'
        assert not row['new_thin_allowance'] and not row['saved_candidate_authorized']


@pytest.mark.parametrize('fault', ['long_arm', 'many_edges', 'third_arm', 'side_tap', 'barrel',
    'zone', 'other_land', 'carrier_narrow', 'carrier_missing', 'too_many_carriers', 'mask',
    'noncanonical', 'too_narrow', 'locked_group', 'nested_group', 'overlap_group',
    'foreign_net_member', 'cycle', 'new_land_covers_throat'])
def test_extra_contacts_arms_or_debt_never_expand_scope(tmp_path, monkeypatch, fault):
    f = case(tmp_path, monkeypatch); board = f['board']; p = f['point']
    lead = f['second_lead']; edge = f['edge']
    if fault == 'long_arm':
        lead.SetEnd(p(5, 6.500001)); f['second_carrier'].SetStart(lead.GetEnd())
    elif fault == 'many_edges':
        f['chain'][0].SetEnd(p(5.4, 5))
        edge((5.4, 5), (5.6, 5), .2); edge((5.6, 5), (6, 5), .2)
    elif fault == 'third_arm': edge((5, 5), (5, 4.63), .2)
    elif fault == 'side_tap': edge((5.8, 5), (5.8, 5.7), .2, grouped=False)
    elif fault == 'barrel':
        via = pcbnew.PCB_VIA(board); via.SetPosition(p(5, 5.22)); via.SetWidth(600000)
        via.SetDrill(300000); via.SetNet(f['pad'].GetNet()); board.Add(via)
    elif fault == 'zone':
        zone = pcbnew.ZONE(board); zone.SetLayer(f['face']); zone.SetNet(f['pad'].GetNet())
        zone.Outline().NewOutline()
        for at in ((4, 4), (7, 4), (7, 7), (4, 7)): zone.Outline().Append(p(*at).x, p(*at).y)
        board.Add(zone)
    elif fault == 'other_land': f['owner'].FindPadByNumber('10').SetPosition(p(5, 5.22))
    elif fault == 'carrier_narrow': f['second_carrier'].SetWidth(499999)
    elif fault == 'carrier_missing': f['second_carrier'].Move(pcbnew.VECTOR2I(1000000, 0))
    elif fault == 'too_many_carriers':
        for n in range(4): edge((5, 5.37), (5 + n / 10, 6.4), .5, grouped=False)
    elif fault == 'mask': lead.SetHasSolderMask(True)
    elif fault == 'noncanonical': lead.SetEnd(p(5.01, 5.37))
    elif fault == 'too_narrow': lead.SetWidth(1)
    elif fault == 'locked_group': f['group'].SetLocked(True)
    elif fault == 'nested_group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(f['group'])
    elif fault == 'overlap_group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(lead)
    elif fault == 'foreign_net_member': lead.SetNet(f['owner'].FindPadByNumber('7').GetNet())
    elif fault == 'cycle': edge((5, 5.37), (6, 5), .2)
    else:
        old = f['posed']
        def covering():
            posed = old(); posed.FindFootprintByReference('RENAMED').Move(pcbnew.VECTOR2I(0, -2030000))
            return posed
        f['posed'] = covering
    before = f['root'].read_bytes()
    with pytest.raises(ValueError): plan(f)
    assert f['root'].read_bytes() == before


@pytest.mark.parametrize('fault', ['source_mpn', 'native_mpn', 'partial_symbol', 'selected_nc',
    'other_native_net', 'power_input_type', 'source_mutation', 'no_current', 'other_face', 'larger_floor'])
def test_fresh_complete_source_and_current_cannot_be_invented(tmp_path, monkeypatch, fault):
    import cec_decoupler_cell as cells
    f = case(tmp_path, monkeypatch); root = f['root']
    if fault == 'source_mpn': root.write_text(root.read_text().replace('INA238AIDGSR', 'UNQUALIFIED'))
    elif fault == 'native_mpn': f['owner'].SetField('MPN', 'UNQUALIFIED')
    elif fault == 'partial_symbol': root.write_text(root.read_text().replace('(number "10")', '(number "9")'))
    elif fault == 'selected_nc':
        root.write_text(root.read_text()[:-1] + ' (no_connect (at 16 10) (uuid "' + str(__import__('uuid').uuid4()) + '")))')
    elif fault == 'other_native_net': f['owner'].FindPadByNumber('10').SetNet(f['pad'].GetNet())
    elif fault == 'power_input_type':
        root.write_text(root.read_text().replace('(pin power_in line (at 6', '(pin passive line (at 6'))
    elif fault == 'source_mutation':
        old = cut._power_input_owner
        def changed(*a, **kw):
            result = old(*a, **kw); root.write_text(root.read_text() + '\n'); return result
        monkeypatch.setattr(cut, '_power_input_owner', changed)
    elif fault == 'no_current': monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: None)
    elif fault == 'other_face':
        monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: dict(required_by_layer_nm={2: 500000}))
    else:
        monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: dict(required_by_layer_nm={0: 500001}))
    try: rows = plan(f)
    except ValueError: return
    assert not rows


def test_distinct_arms_compose_distinct_complete_source_contacts(tmp_path, monkeypatch):
    import cec_cell_macro_requests as compiler
    f = case(tmp_path, monkeypatch); cuts = plan(f)
    contacts = [dict(track_uuid=force._uid(t), pad_uuid=force._uid(f['pad']),
        net=f['pad'].GetNetname(), layer=0, contact_nm=list(f['pad'].GetPosition()))
        for t in (f['chain'][0], f['second_lead'])]
    proposal = dict(row_plan=dict(source_incident_boundaries=copy.deepcopy(contacts)))
    result = compiler._compose_supply_endpoint_rows(proposal, cuts)
    assert proposal['row_plan']['source_incident_boundaries'] == []
    assert len(result) == 2 and len({r['replacement_request_id'] for r in result}) == 2
    assert {r['original_source_contact']['track_uuid'] for r in result} == {r['track_uuid'] for r in contacts}


def test_cross_arm_native_contact_outside_land_is_not_a_source_port(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch)
    f['pad'].SetSize(pcbnew.VECTOR2I_MM(.3, .3))
    lead = f['second_lead']; lead.SetEnd(f['point'](5.4, 5.4))
    extra = f['edge']((5.4, 5.4), (5.4, 5), .2)
    f['second_carrier'].SetStart(extra.GetEnd()); f['second_carrier'].SetEnd(f['point'](5.4, 6))
    with pytest.raises(ValueError, match='arms_touch_outside_actual_Source_land'):
        plan(f)


def test_single_chain_keeps_legacy_shape_and_request_identity(tmp_path, monkeypatch):
    f = single_case(tmp_path, monkeypatch)
    rows = cut.plan(f['board'], f['posed'](), board_hint=str(f['root']),
        source_floor=lambda t: (500000, 200000), allow_locked=True)
    assert len(rows) == 1 and 'source_split_supply_input' not in rows[0]


def body_case(tmp_path, monkeypatch):
    f = case(tmp_path, monkeypatch)
    # The first full current endpoint occurs BEFORE the two final grouped
    # thin Source strokes. Those strokes and all three real full carriers
    # stay literal. Each carrier cap/body genuinely touches the original VS
    # land, while none of their centreline endpoints falls inside that land.
    f['carrier'].SetStart(f['chain'][0].GetEnd())
    f['carrier'].SetEnd(f['point'](5.68, 5.32))
    third = f['edge']((5, 5.37), (5.65, 5.37), .5, grouped=False)
    f['body_carriers'] = [f['carrier'], f['second_carrier'], third]
    return f


def test_first_full_ports_keep_overshoots_and_all_three_actual_owner_body_contacts(tmp_path, monkeypatch):
    f = body_case(tmp_path, monkeypatch); rows = plan(f)
    assert len(rows) == 2
    assert {u for r in rows for u in r['retired_track_uuids']} == {
        force._uid(f['chain'][0]), force._uid(f['second_lead'])}
    untouched = {force._uid(t) for t in [*f['chain'][1:], f['residue']]}
    assert all(set(row['remaining_group_members']) == untouched for row in rows)
    for t in f['body_carriers']:
        assert t.GetEffectiveShape(0).Collide(f['pad'].GetEffectiveShape(0), 0)
        assert not any(f['pad'].HitTest(at, 0) for at in (t.GetStart(), t.GetEnd()))
    contacts = cut.retained_throat_contacts(f['board'], f['posed'](), rows, board_hint=str(f['root']))
    assert {r['uuid'] for r in contacts} == {force._uid(t) for t in f['body_carriers']}
    for record in contacts:
        contact, = record['lost_moving_contacts']
        owning = next(row for row in rows if record['uuid'] in row['retained_throat_track_uuids'])
        assert contact['pad_uuid'] == force._uid(f['pad'])
        assert contact['source_contact_nm'] == [owning['retained_throat_nm']]
        assert contact['exact_old_port_reconstruction_mandatory']
        assert not record['current_authority'] and not record['saved_candidate_authorized']


@pytest.mark.parametrize('fault', ['kind', 'pad_identity', 'first_port_policy', 'cut_scope',
    'carrier_identity', 'one_nm_nonendpoint', 'carrier_below_floor'])
def test_body_contact_mapping_cannot_be_borrowed_by_nonliteral_cut_records(tmp_path, monkeypatch, fault):
    f = body_case(tmp_path, monkeypatch); rows = copy.deepcopy(plan(f))
    # Both carriers in this row have only a real body/cap contact, so a
    # missing typed first-port proof must hit the unchanged endpoint guard.
    row = next(r for r in rows if force._uid(f['second_carrier']) in r['retained_throat_track_uuids'])
    proof = row['source_split_supply_input']
    if fault == 'kind': proof['kind'] = 'ordinary_alias_not_authority'
    elif fault == 'pad_identity': proof['pad_uuid'] = 'a-different-pad'
    elif fault == 'first_port_policy': proof['first_literal_full_current_junctions_only'] = False
    elif fault == 'cut_scope': proof['complete_retired_track_uuids'] = []
    elif fault == 'carrier_identity': proof['complete_retained_carrier_uuids'] = []
    elif fault == 'one_nm_nonendpoint': row['retained_throat_nm'][0] += 1
    else: f['second_carrier'].SetWidth(499999)
    with pytest.raises(ValueError, match='needs_exact_source_endpoint'):
        cut.retained_throat_contacts(f['board'], f['posed'](), [row], board_hint=str(f['root']))


def test_late_split_success_never_becomes_a_plan(tmp_path, monkeypatch):
    import cec_source_split_supply_input as split
    f = case(tmp_path, monkeypatch); clock = cut.time.monotonic; shift = [0.]
    monkeypatch.setattr(cut.time, 'monotonic', lambda: clock() + shift[0])
    original = split.chains
    def late(*a, **kw):
        result = original(*a, **kw); shift[0] = 11.; return result
    monkeypatch.setattr(split, 'chains', late)
    with pytest.raises(ValueError, match='deadline'): plan(f)


@pytest.mark.parametrize('seconds', [0, -1, 10.001, True, math.nan, math.inf])
def test_all_public_deadlines_remain_finite_ten_seconds(tmp_path, monkeypatch, seconds):
    f = case(tmp_path, monkeypatch)
    with pytest.raises(ValueError): plan(f, timeout_s=seconds)
