"""Native two-ended absolute cuts and strict re-landing comparison negatives."""
import copy
import time

import pcbnew
import pytest
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_measurement_leaf_relanding as reland
import cec_measurement_relanding_evidence as evidence
from test_force_sense_evidence import fixture as native_fixture


def case(tmp_path, monkeypatch, quarter=0):
    source = tmp_path / 'source' / 'board.kicad_pcb'
    source.parent.mkdir()
    domains = native_fixture(source, filtered=False, angle=quarter*90)
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **k: copy.deepcopy(domains))
    board = pcbnew.LoadBoard(str(source))
    # The older contact-only fixture omits package support pads. Give this
    # Source policy fixture all eight native pin identities so the monitor
    # cannot masquerade as the two-pad shunt selected by the generator.
    owner = board.FindFootprintByReference('ANALOG_SENSOR')
    for number in ('2','3','4','5','6','7'):
        net = pcbnew.NETINFO_ITEM(board, 'separate_support_'+number); board.Add(net)
        pad = pcbnew.PAD(owner); pad.SetNumber(number); pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        pad.SetPosition(pcbnew.VECTOR2I_MM(115+int(number),110)); owner.Add(pad)
    for a,b in [((0,0),(150,0)),((150,0),(150,150)),((150,150),(0,150)),((0,150),(0,0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    field._save_field_snapshot(board, source)
    root = board.FindFootprintByReference('ANALOG_SENSOR').FindPadByNumber('8')
    uid = force._uid(root)
    def transform(p):
        x,y = p
        for _ in range(quarter): x,y = y,-x
        return [x+70000000,y+55000000]
    points = [transform(p) for p in ((20000000,24000000),(20400000,23600000),(20400000,20600000))]
    child = force._copy_family(source, tmp_path/'child')
    reland.construct_private(source, child, board_hint='generic-native-direct-shunt',
        pad_uuid=uid, points_nm=points, timeout_s=9.)
    saved = reland.receive(source, child, board_hint='generic-native-direct-shunt', pad_uuid=uid, timeout_s=9.)
    assert saved['ok'] is True and saved['complete'] is True, saved
    before, after = [sense.replay(path, board_hint='generic-native-direct-shunt', timeout_s=9.)
        for path in (source,child)]
    transforms = sense.native_copper_transform_inventory(
        *[pcbnew.LoadBoard(str(p)) for p in (source,child)],
        modified_nets=[saved['source_scope']['demand']['net']])
    return source,child,uid,before,after,saved,transforms


@pytest.mark.parametrize('quarter', range(4))
def test_native_relanding_requires_both_absolute_cuts_and_changes_no_raw_report(tmp_path,monkeypatch,quarter):
    source, child, uid, before, after, saved, transforms = case(tmp_path,monkeypatch,quarter)
    original = copy.deepcopy((before,after,saved,transforms))
    result = evidence._compare(before,after,saved,transforms)
    assert result['same_evidence'] is True and result['comparison_complete'] is True, result
    assert result['independently_absolute_before']['checked'] == 1
    assert result['independently_absolute_after']['checked'] == 1
    assert (before,after,saved,transforms) == original
    assert not result['raw_evidence_equal_claimed'] and result['raw_reports_not_modified']
    assert not result['full_kelvin_qualification'] and not result['release_authority']


def test_public_receiver_rederives_saved_scope_and_runs_fresh_native_audits(tmp_path,monkeypatch):
    source, child, uid, before, after, saved, transforms = case(tmp_path,monkeypatch)
    original = sense.replay
    called = []
    def observed(path, **kwargs):
        called.append(str(path))
        return original(path, **kwargs)
    monkeypatch.setattr(sense, 'replay', observed)
    result = evidence.receive(source,child,board_hint='generic-native-direct-shunt',
        pad_uuid=uid,timeout_s=9.)
    assert result['ok'] is True and result['complete'] is True, result
    assert called == [str(source),str(child)]
    assert result['independent_saved_relanding']['ok'] is True
    assert all(value < 9. for value in result['timings_s'].values())
    assert result['Source_families_and_code_unchanged']


@pytest.mark.parametrize('fault', ['before_unknown','after_unknown','direction','wrong_root','foreign_path',
    'pad_identity','guard','unrelated_failure','current_authority','policy'])
def test_received_geometry_cannot_hide_any_absolute_or_unaffected_evidence_change(tmp_path,monkeypatch,fault):
    source, child, uid, before, after, saved, transforms = case(tmp_path,monkeypatch)
    key = saved['source_scope']['demand']['net']
    row = next(r for r in after['inner_departure']['details'] if r['net']==key)
    cut = next(r for r in after['clipped_isolation']['details'] if r['net']==key)
    if fault == 'before_unknown':
        item = next(r for r in before['clipped_isolation']['details'] if r['net']==key)
        item.update(ok=None,status='unknown'); item['native'].update(ok=None,complete=False)
    elif fault == 'after_unknown':
        cut.update(ok=None,status='unknown'); cut['native'].update(ok=None,complete=False)
    elif fault == 'direction': row['native']['departures'][0]['inward_direction'][0] += 1
    elif fault == 'wrong_root': row['native']['departures'][0]['reachable_input_pad_uuids']=['not-the-source-input']
    elif fault == 'foreign_path': row['native']['departures'][0]['input_contact_paths'][uid][0]='unowned'
    elif fault == 'pad_identity': row['source_pad']['uuid']='different-shunt'
    elif fault == 'guard': cut['native']['numerical_guard_nm']+=1
    elif fault == 'unrelated_failure':
        other=next(r for r in after['clipped_isolation']['details'] if r['net']!=key)
        other['native']['complete']=False
    elif fault == 'current_authority': after['authority'][key]['source_refs']=['unrated-worker-choice']
    else: after['geometry_policy']['inner_min_mm']=0
    try:
        result=evidence._compare(before,after,saved,transforms)
    except (ValueError,KeyError): return
    assert result['same_evidence'] is False or result['comparison_complete'] is False,result


@pytest.mark.parametrize('fault', ['order','extra','duplicate','other_root','not_a_path','missing','wrong_departure'])
def test_ordered_leaf_witness_is_not_an_arbitrary_UUID_whitelist(fault):
    owned=['root-stub','outer','last']; root='actual-input'
    departure=dict(uuid='last',reachable_input_pad_uuids=[root],
        input_contact_paths={root:['last','outer','root-stub',root]})
    evidence._witness(departure,owned,root)
    path=departure['input_contact_paths'][root]
    if fault=='order':path[0],path[1]=path[1],path[0]
    elif fault=='extra':path.insert(1,'unowned')
    elif fault=='duplicate':path.insert(1,'last')
    elif fault=='other_root':path[-1]='other-input'
    elif fault=='not_a_path':departure['input_contact_paths'][root]=True
    elif fault=='missing':departure['input_contact_paths']={}
    else:departure['uuid']='different-departure'
    with pytest.raises(ValueError):evidence._witness(departure,owned,root)


@pytest.mark.parametrize('value',[True,False,0,-1,11,float('nan'),float('inf')])
def test_public_contact_receiver_cannot_gain_unbounded_work_or_missing_authority(value):
    result=evidence.receive('missing-source','missing-child',board_hint='not-a-board',
        pad_uuid='unknown',timeout_s=value)
    assert result['ok'] is False and result['complete'] is False and result['errors']
