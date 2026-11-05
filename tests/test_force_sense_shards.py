"""Exact native shard coverage, not a new isolation or qualification oracle."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pcbnew
import pytest
import cec_force_sense_evidence as evidence
import cec_force_sense_shards as shards
from test_force_sense_evidence import fixture


@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    path=tmp_path_factory.mktemp('exact-sense-shards')/'source.kicad_pcb'
    domains=fixture(path,filtered=True)
    board=pcbnew.LoadBoard(str(path));owner=board.FindFootprintByReference('ANALOG_SENSOR')
    second=pcbnew.FOOTPRINT(board);second.SetReference('SECOND_INPUT');second.SetValue(owner.GetValue());second.SetFPID(owner.GetFPID());board.Add(second)
    for pin in ('8','1'):
        first=owner.FindPadByNumber(pin);pad=pcbnew.PAD(second);pad.SetNumber(pin);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(first.GetSize());pad.SetNet(first.GetNet());pad.SetPosition(first.GetPosition()+pcbnew.VECTOR2I_MM(3,0));second.Add(pad)
        track=pcbnew.PCB_TRACK(board);track.SetStart(first.GetPosition());track.SetEnd(pad.GetPosition());track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu);track.SetNet(first.GetNet());board.Add(track)
    pcbnew.SaveBoard(str(path),board,True)
    original=path.read_bytes()
    with patch('cec_current_topology.board_current_domains',return_value=domains),patch('cec_force_current._code_identity',return_value={'synthetic-test-epoch':'exact'}):
        prepared=shards.manifest(path,board_hint='fixture')
        legs=[shards.replay_leg(path,prepared,board_hint='fixture',input_ref=q['input_ref'],leg=q['leg']) for q in prepared['shard_inventory']['legs']]
        legacy=shards.replay_legacy(path,prepared,board_hint='fixture')
        ordinary=evidence.replay(path,board_hint='fixture',timeout_s=9.1)
        joined=shards.assemble(path,prepared,legs,legacy,board_hint='fixture')
        assert path.read_bytes()==original
        yield dict(path=path,domains=domains,prepared=prepared,legs=legs,legacy=legacy,ordinary=ordinary,joined=joined,bytes=original)


def combine(bundle,prepared=None,legs=None,legacy=None):
    # Fuzz the join against the independent, immutable fresh manifest already
    # natively produced above. Native integration is separately exercised.
    with patch.object(shards,'manifest',return_value=copy.deepcopy(bundle['prepared'])):
        return shards.assemble(bundle['path'],prepared if prepared is not None else bundle['prepared'],
            legs if legs is not None else bundle['legs'],legacy if legacy is not None else bundle['legacy'],board_hint='fixture')


def test_native_filtered_shared_rail_join_matches_unchanged_default_replay(bundle):
    report=bundle['joined'];ordinary=bundle['ordinary']
    assert ordinary['complete']and report['complete']and report['identity_stable']
    result=evidence.compare_contact_preservation(ordinary,report)
    assert result['comparison_complete']and result['same_evidence'],result
    assert report['clipped_isolation']['expected']==4
    assert report['same_net_connectivity']['expected']==8
    assert report['sharded_replay']['legacy_observations']==1
    assert not report['release_authority']and not report['electrical_rating_qualified']
    assert report['kelvin_isolation_qualified']is None
    assert bundle['path'].read_bytes()==bundle['bytes']


def test_leg_and_manifest_cannot_masquerade_as_full_replay(bundle):
    assert bundle['prepared']['shard_complete']and not bundle['prepared']['complete']
    for report in bundle['legs']:
        assert report['shard_complete']and report['complete']is False
        assert report['clipped_isolation']['expected']==4
        assert len(report['clipped_isolation']['details'])==1
        assert report['clipped_isolation']['unknown']==3
        assert not evidence.compare_contact_preservation(report,report)['comparison_complete']
        assert not evidence.admit_changed_net(report,report,report['clipped_isolation']['details'][0]['net'])['ok']


@pytest.mark.parametrize('fault',['missing','duplicate','extra','same_net_other_input_duplicate'])
def test_every_exact_physical_leg_not_just_every_net_is_mandatory(bundle,fault):
    legs=copy.deepcopy(bundle['legs'])
    if fault=='missing':legs.pop()
    elif fault=='extra':legs.append(copy.deepcopy(legs[0]))
    elif fault=='duplicate':legs[-1]=copy.deepcopy(legs[0])
    else:
        assert legs[0]['clipped_isolation']['details'][0]['net']==legs[2]['clipped_isolation']['details'][0]['net']
        legs[2]=copy.deepcopy(legs[0])
    with pytest.raises(ValueError):combine(bundle,legs=legs)


@pytest.mark.parametrize('fault',['source','family','code','hint','lineage','denominator','authority_domain','unbound','incomplete','stop','selector'])
def test_stale_or_invented_epoch_lineage_and_denominator_refused(bundle,fault):
    legs=copy.deepcopy(bundle['legs']);report=legs[0]
    if fault=='source':report['source']+='other'
    elif fault=='family':report['source_family_after']['invented']='hash'
    elif fault=='code':report['code_before']['synthetic-test-epoch']='changed'
    elif fault=='hint':report['board_hint']='other'
    elif fault=='lineage':report['lineage']['resolved']-=1
    elif fault=='denominator':report['shard_inventory']['expected_legs']-=1
    elif fault=='authority_domain':report['shard_inventory']['authority_domains'].clear()
    elif fault=='unbound':report['identity_stable']=False
    elif fault=='incomplete':report['shard_complete']=False
    elif fault=='stop':report['stop']='deadline_exhausted'
    else:report['shard_selector']=['leg','foreign','p']
    with pytest.raises(ValueError):combine(bundle,legs=legs)


@pytest.mark.parametrize('fault',['source_pad','sense_pad','cut_source','cut_authority','cut_guard','cut_error','cut_scope','cut_result','segment_pad','omitted_authority','current_authority','coverage','bool_counter','foreign_detail','duplicate_detail','missing_detail','integer_outcome','float_identity','integer_observed','float_guard','incomplete_positive_cut'])
def test_no_terminal_hole_bound_authority_or_coverage_waiver(bundle,fault):
    legs=copy.deepcopy(bundle['legs']);report=legs[0]
    clipped=report['clipped_isolation']['details'][0];proof=clipped['native']
    if fault=='source_pad':clipped['source_pad']['position_nm'][0]+=1
    elif fault=='sense_pad':clipped['sense_terminal']['uuid']='other'
    elif fault=='cut_source':proof['source']['position_nm'][0]+=1
    elif fault=='cut_authority':proof['authority'].pop()
    elif fault=='cut_guard':proof['numerical_guard_nm']-=1
    elif fault=='cut_error':proof['approximation_error_nm']-=1
    elif fault=='cut_scope':proof['scope']='centrelines_only'
    elif fault=='cut_result':proof['ok']=not proof['ok']
    elif fault=='segment_pad':report['same_net_connectivity']['details'][0]['start_pad']['uuid']='other'
    elif fault=='omitted_authority':report['shunt_pad_omitted']['details'][0]['authority_excluding_cut'].clear()
    elif fault=='current_authority':report['authority'][next(iter(report['authority']))]['source_refs']=['foreign']
    elif fault=='coverage':report['clipped_isolation']['checked']+=1
    elif fault=='bool_counter':report['clipped_isolation']['checked']=True
    elif fault=='foreign_detail':report['inner_departure']['details'][0]['input_ref']='foreign'
    elif fault=='duplicate_detail':report['inner_departure']['details'].append(copy.deepcopy(report['inner_departure']['details'][0]))
    elif fault=='missing_detail':report['inner_departure']['details'].clear()
    elif fault=='float_identity':clipped['source_pad']['position_nm'][0]=float(clipped['source_pad']['position_nm'][0])
    elif fault=='integer_observed':report['shunt_pad_omitted']['details'][0]['observed']=1
    elif fault=='float_guard':proof['numerical_guard_nm']=float(proof['numerical_guard_nm'])
    elif fault=='incomplete_positive_cut':proof['complete']=False
    else:
        clipped['ok']=proof['ok']=2
        report['clipped_isolation']=evidence._coverage(report['clipped_isolation']['details'],4)
    with pytest.raises(ValueError):combine(bundle,legs=legs)


@pytest.mark.parametrize('fault',['wrong_stage','missing','foreign_family','contains_leg'])
def test_legacy_is_one_independent_same_epoch_observation(bundle,fault):
    legacy=copy.deepcopy(bundle['legacy'])
    if fault=='wrong_stage':legacy['shard_selector']=['manifest']
    elif fault=='missing':legacy['shard_complete']=False
    elif fault=='foreign_family':legacy['source_family_before']['other']='hash'
    else:legacy['inner_departure']=copy.deepcopy(bundle['legs'][0]['inner_departure'])
    with pytest.raises(ValueError):combine(bundle,legacy=legacy)


def test_order_of_workers_does_not_change_replay_row_order(bundle):
    first=combine(bundle,legs=list(reversed(bundle['legs'])));second=combine(bundle)
    first.pop('elapsed_s');second.pop('elapsed_s')
    assert first==second


def test_input_receipts_not_mutated_by_join(bundle):
    old=copy.deepcopy((bundle['prepared'],bundle['legs'],bundle['legacy']))
    combine(bundle)
    assert old==(bundle['prepared'],bundle['legs'],bundle['legacy'])


@pytest.mark.parametrize('value',[0,-1,True,float('nan'),float('inf'),10.001])
def test_constituents_never_request_more_than_ten_seconds(bundle,value):
    with pytest.raises(ValueError):shards.manifest(bundle['path'],board_hint='fixture',timeout_s=value)


def test_foreign_selected_leg_refused_not_vacuous_complete(bundle):
    with pytest.raises(ValueError,match='selected_input_leg'):
        shards.replay_leg(bundle['path'],bundle['prepared'],board_hint='fixture',input_ref='NOT_AN_INPUT',leg='p')


@pytest.mark.parametrize('kind',['family','code'])
def test_epoch_rechecked_after_join_not_only_during_fresh_manifest(bundle,kind):
    name='_family' if kind=='family' else '_code_identity'
    with patch('cec_force_current.'+name,return_value={'changed_during_join':True}):
        with pytest.raises(ValueError,match='changed_during_coverage_join'):combine(bundle)


def test_every_receipt_content_is_bound_in_final_aggregate(bundle):
    joined=combine(bundle)
    assert joined['sharded_replay']['constituent_sha256']==[
        shards._digest(q) for q in [bundle['prepared'],*bundle['legs'],bundle['legacy']]]


def test_manifest_and_join_do_not_run_legacy_or_replace_absolute_cut(bundle):
    import cec_kelvin_copper_cut as cut
    import cec_score
    with patch.object(cut,'audit',wraps=cut.audit)as exact,patch.object(cec_score,'kelvin_topology_faults',wraps=cec_score.kelvin_topology_faults)as legacy:
        prepared=shards.manifest(bundle['path'],board_hint='fixture')
        assert exact.call_count==legacy.call_count==0
        leg=prepared['shard_inventory']['legs'][0]
        report=shards.replay_leg(bundle['path'],prepared,board_hint='fixture',input_ref=leg['input_ref'],leg=leg['leg'])
        assert exact.call_count==1 and legacy.call_count==0
        assert report['clipped_isolation']['details'][0]['native']['tracks_clipped']is True
        old=shards.replay_legacy(bundle['path'],prepared,board_hint='fixture')
        assert exact.call_count==1 and legacy.call_count==1
        shards.assemble(bundle['path'],prepared,bundle['legs'],old,board_hint='fixture')
        assert exact.call_count==1 and legacy.call_count==1


def test_manifest_does_not_bless_concurrent_code_change(bundle):
    with patch('cec_force_current._code_identity',side_effect=[{'before':'one'},{'after':'two'}]):
        report=shards.manifest(bundle['path'],board_hint='fixture')
    assert report['shard_complete']is False and report['complete']is False
    assert report['identity_stable']is False
    assert report['stop']=='concurrent_source_family_or_code_change'


def test_default_and_shards_keep_absolute_open_cut_unknown(tmp_path):
    path=tmp_path/'open.kicad_pcb';domains=fixture(path,filtered=False,fault='missing_copper')
    with patch('cec_current_topology.board_current_domains',return_value=domains),patch('cec_force_current._code_identity',return_value={'test':'open'}):
        prepared=shards.manifest(path,board_hint='fixture')
        legs=[shards.replay_leg(path,prepared,board_hint='fixture',input_ref=q['input_ref'],leg=q['leg'])for q in prepared['shard_inventory']['legs']]
        report=shards.assemble(path,prepared,legs,shards.replay_legacy(path,prepared,board_hint='fixture'),board_hint='fixture')
        ordinary=evidence.replay(path,board_hint='fixture',timeout_s=9.1)
    assert report['complete']and report['clipped_isolation']['unknown']
    assert report['same_net_connectivity']['failed']
    compared=evidence.compare_contact_preservation(ordinary,report)
    assert compared['comparison_complete']and compared['same_evidence'],compared
    assert report['clipped_isolation']['ok']is None
