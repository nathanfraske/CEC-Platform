import hashlib
from pathlib import Path

import pytest
import pcbnew
import cec_source_series_link_placement as series


def valid():
    return {'current_authority': {'amps': 3., 'geometry_margin': 1.25,
                                 'margin_included': False},
            'required_by_layer_mm': {'F.Cu': .47737, 'B.Cu': .47737}}


def test_whole_contract_copied_without_transfer_or_equalization():
    a = valid()
    assert series._contract('explicit_all_terminal_distributed_supply', a) == a
    b = series._contract('aggregate_source_sink', a)
    b['current_authority']['amps'] = 2.5
    assert a['current_authority']['amps'] == 3


@pytest.mark.parametrize('key,value', [('amps', 0), ('amps', True),
    ('amps', float('nan')), ('geometry_margin', 0), ('geometry_margin', True),
    ('margin_included', 1)])
def test_invalid_authority_refuses(key, value):
    c = valid(); c['current_authority'][key] = value
    with pytest.raises(ValueError):
        series._contract('explicit_all_terminal_distributed_supply', c)


def test_unknown_role_or_empty_widths_refuse():
    with pytest.raises(ValueError):
        series._contract('low_power_pin', valid())
    c = valid(); c['required_by_layer_mm'] = {}
    with pytest.raises(ValueError):
        series._contract('aggregate_source_sink', c)
    c = valid(); c['current_authority']['margin_included'] = True
    with pytest.raises(ValueError):
        series._contract('aggregate_source_sink', c)


def test_actual_source_zero_link_retains_independent_domains_and_all_contacts():
    source = Path('experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == '7908e5c235157f5456d5a06a45c3df8c05bbbc30b6cec48629e0f727d8416d3e'
    board = pcbnew.LoadBoard(str(source))
    uid = board.FindFootprintByReference('FB2').m_Uuid.AsString()
    r = series.compile(source, uid, board_hint='atx-24pin-rev3')
    assert [p['unchanged_full_current_contract']['current_authority']['amps']
            for p in r['pins']] == [3., 2.5]
    assert [len(p['retained_native_contacts']) for p in r['pins']] == [2, 1]
    assert r['every_source_contact_mandatory']
    assert not r['current_transfer_authority']
    assert not r['source_trace_retirement_authority']
    assert not r['current_qualified']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_actual_nonzero_passive_not_reclassified():
    source = Path('experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb')
    board = pcbnew.LoadBoard(str(source))
    uid = board.FindFootprintByReference('R59').m_Uuid.AsString()
    with pytest.raises(ValueError):
        series.compile(source, uid, board_hint='atx-24pin-rev3')


def source_context():
    source=Path('experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb')
    board=pcbnew.LoadBoard(str(source))
    poses={'FB2':[27.7,62.2,180]}
    selected=series.plan(board,poses,board_hint='atx-24pin-rev3')
    proposal=dict(poses=poses,board_hint='atx-24pin-rev3',selected_source_series_links=selected)
    child=pcbnew.LoadBoard(str(source));fp=child.FindFootprintByReference('FB2')
    fp.SetPosition(pcbnew.VECTOR2I(27700000,62200000));fp.SetOrientationDegrees(180)
    return board,child,proposal


def test_actual_plan_and_requests_keep_every_contact_without_cuts():
    parent,child,proposal=source_context()
    before=series.row._source_binding(parent)
    requests=series.requests(parent,child,proposal)
    assert len(requests)==3
    assert sorted(r['width_nm'] for r in requests.values())==[371227,477370,477370]
    assert all(r['every_original_contact_mandatory'] for r in requests.values())
    assert not any(r['source_trace_retirement_authority'] for r in requests.values())
    assert series.row._source_binding(parent)==before


@pytest.mark.parametrize('mutation',['retired_contact','changed_width','changed_pad','forged_proposal'])
def test_actual_requests_reject_lost_contact_nonrigid_or_forged(mutation):
    parent,child,proposal=source_context()
    contacts=next(iter(proposal['selected_source_series_links'].values()))['pins'][0]['source_terminal_contacts']
    track=next(t for t in child.GetTracks()if t.m_Uuid.AsString()==contacts[0]['item_uuid'])
    if mutation=='retired_contact':child.Remove(track)
    elif mutation=='changed_width':track.SetWidth(track.GetWidth()+1)
    elif mutation=='changed_pad':child.FindFootprintByReference('FB2').FindPadByNumber('1').SetSize(pcbnew.VECTOR2I(1000000,1000000))
    else:proposal['selected_source_series_links']['FB2']['pins'][0]['net']='invented'
    with pytest.raises(ValueError):series.requests(parent,child,proposal)


def test_plan_rejects_mutated_unsaved_native_source_and_invalid_deadline():
    parent,child,proposal=source_context()
    with pytest.raises(ValueError,match='exact_saved'):
        series.plan(child,proposal['poses'],board_hint='atx-24pin-rev3')
    for value in (0,11,True,float('nan')):
        with pytest.raises(ValueError):
            series.plan(parent,proposal['poses'],board_hint='atx-24pin-rev3',timeout_s=value)


def test_literal_r_canonical_branch_preserves_full_pin_and_net_checks(monkeypatch):
    source=Path('experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb')
    board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference('R59')
    deadline=series.passive._deadline(10)
    root=series.leaf.source_nc._root(board,'atx-24pin-rev3').resolve()
    _,_,instances=series.leaf._hierarchy(root,deadline)
    tree,_=series.leaf._export(root,deadline)
    comps,nets,node_net=series.leaf._tables(tree)
    c=series._canonical(board,fp,comps,nets,node_net,instances,tree,deadline)
    assert c['symbol_kind'] in ('R','R_Small')
    # R recognition alone never grants the zero-ohm role.
    assert not series._zero(fp.GetValue())
    bad=dict(nets);bad[fp.FindPadByNumber('1').GetNetname()]=set()
    with pytest.raises(ValueError,match='membership'):
        series._canonical(board,fp,comps,bad,node_net,instances,tree,deadline)
    props=series.footprint_properties(fp);props['LCSC']='wrong'
    monkeypatch.setattr(series,'footprint_properties',lambda _:props)
    with pytest.raises(ValueError,match='LCSC'):
        series._canonical(board,fp,comps,nets,node_net,instances,tree,deadline)


@pytest.mark.parametrize('value',['0R','0Ω','0R (DEFAULT)'])
def test_only_explicit_zero_values(value):
    assert series._zero(value)
    for wrong in ('0.1R','0R5','1R','0R\nextra','DNP','ferrite'):
        assert not series._zero(wrong)
