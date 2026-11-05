"""Inline topology admission and generic, bounded placement proposals."""
import math
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_precision_route as precision
import cec_synth_pipeline as synth
import cec_pcb


@pytest.mark.parametrize('angle', [0, 37, 90, 180, 270])
@pytest.mark.parametrize('off_corridor', [False, True])
def test_excursion_is_rigid_transform_invariant(angle, off_corridor):
    y = 35 if off_corridor else 0
    legs = [((0,0),(9,y),(0,1),(9,y+1)),
            ((11,y),(20,0),(11,y+1),(20,1))]
    def transform(pt):
        x,y = cec_pcb._rot(*pt,angle)
        return x+132, y-86
    transformed = [tuple(transform(p) for p in leg) for leg in legs]
    baseline = precision._flow_through_excursion(legs)
    result = precision._flow_through_excursion(transformed)
    assert result['ok'] is (not off_corridor)
    assert result['ratio'] == baseline['ratio']
    assert result['terminal_span_mm'] == baseline['terminal_span_mm']


def test_excursion_needs_inline_chain_and_has_finite_coincident_bound():
    assert precision._flow_through_excursion([]) is None
    legs = [((0,0),(10,0),(0,1),(10,1)),
            ((12,0),(0,0),(12,1),(0,1))]
    result = precision._flow_through_excursion(legs)
    assert not result['ok']
    assert math.isfinite(result['ratio'])


def test_layer_refusal_keeps_nested_evidence_out_of_message():
    rows = [{'layer':'F.Cu','reason':'deadline exhausted',
             'attempt':{'unique_geometry_witness':'x'*100000}}]
    message = precision._pair_layer_refusal_message(rows)
    assert message == 'layer ensemble exhausted: F.Cu: deadline exhausted'
    assert len(rows[0]['attempt']['unique_geometry_witness']) == 100000
    assert len(precision._pair_layer_refusal_message([
        {'layer':'SIG','reason':'y'*100000}])) < 300


@pytest.mark.parametrize('kwargs',[{'max_ratio':float('nan')},{'max_ratio':.5},
                                 {'minimum_span_mm':0}])
def test_excursion_invalid_policy_fails_closed(kwargs):
    with pytest.raises(ValueError):
        precision._flow_through_excursion([
            ((0,0),(9,0),(0,1),(9,1)),((11,0),(20,0),(11,1),(20,1))],**kwargs)


def _fixture():
    candidate = SimpleNamespace(W=40,H=30,back_refs=(),
        P={'INLINE':(30,25,0),'SOURCE':(6,8,0),'LOAD':(28,8,0)})
    row = {'kind':'flow_through_excursion','station_ref':'INLINE',
        'station_refs':['INLINE'],'pair':'ANY',
        'terminal_start_mm':[6,8],'terminal_end_mm':[28,8],
        'bank_centers_mm':[[29,25],[31,25]],'external_leg_span_mm':45,
        'limit':2.0}
    def box(_fp,x,y,rot):
        return x-1,x+1,y-1,y+1
    comps = {ref:ref for ref in candidate.P}
    return candidate,row,comps,box


def test_generic_locality_proposals_preserve_endpoints_and_orientation_budget():
    c,row,comps,box = _fixture()
    original = dict(c.P)
    with mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box), \
            mock.patch.object(cec_pcb,'local_pads',return_value={'1':(0,0)}):
        moves = synth._flow_through_locality_move_specs(c,[row],comps,max_specs=12)
        dispatched = synth._placement_craft_move_specs(c,
            {'pair_launch':{'violations':[row]}},comps=comps,
            required_stages=['critical_pair_launch'])
    assert c.P == original
    assert 0 < len(moves) <= 12
    assert {r['position'][2] for r in moves[:4]} == {0,90,180,270}
    assert any(r['kind']=='flow_through_locality_reseat' for r in dispatched)
    for move in moves:
        assert set(move['placements']) == {'INLINE'}
        assert move['predicted_external_leg_span_mm'] < 30
        assert move['required_eviction_ref'] is None


@pytest.mark.parametrize('mode',['fixed','multiple','missing_banks'])
def test_unsupported_locality_edits_fail_closed(mode):
    c,row,comps,box = _fixture()
    fixed = ['INLINE'] if mode=='fixed' else []
    if mode=='multiple': row['station_refs'].append('SECOND')
    if mode=='missing_banks': row['bank_centers_mm']=[]
    with mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box):
        assert synth._flow_through_locality_move_specs(c,[row],comps,immovable=fixed)==[]


def test_native_launch_evidence_catches_remote_inline_with_no_foreign_blockers():
    class Board:
        def GetFootprints(self): return []
    legs = [((0,0),(9,35),(0,1),(10,35)),
            ((9,37),(20,0),(10,37),(20,1))]
    pads = {'P':[('INLINE','1',(9,35),None),('INLINE','2',(9,37),None)],
            'N':[('INLINE','3',(10,35),None),('INLINE','4',(10,37),None)]}
    with mock.patch.object(precision,'derive_coupled_pairs',return_value=[
            {'name':'ANY','p':'P','n':'N','width':.2,'gap':.2}]), \
            mock.patch.object(precision,'_flow_through_pair_legs',return_value=(legs,['INLINE'])), \
            mock.patch.object(precision,'_pads_on_net',side_effect=lambda b,n:pads[n]):
        result = precision.flow_through_launch_evidence('unused',board=Board())
    assert not result['ok']
    assert all(not ch['blockers'] for ch in result['channels'])
    assert result['violations'][0]['kind']=='flow_through_excursion'
    assert len(result['violations'][0]['bank_centers_mm'])==2
    gate = synth.placement_craft_admission({'ok':False,'pair_launch':result},
                                          allow_route_access_repair=True)
    assert not gate['ok']
    assert 'pair_launch placement evidence failed' in gate['blockers']


@pytest.mark.parametrize('name,offset',[('INLINE',(0,0)),('RENAMED',(13,7))])
def test_route_refusal_includes_bounded_in_place_rotation_before_reseating(name,offset):
    c,row,comps,box=_fixture()
    dx,dy=offset;c.W+=dx;c.H+=dy
    c.P={name if r=='INLINE' else r:(x+dx,y+dy,a) for r,(x,y,a) in c.P.items()}
    c.P[name]=(17+dx,8+dy,0)
    comps={r:r for r in c.P}
    row.update(kind='flow_through_routing_refusal',station_ref=name,station_refs=[name],
        terminal_start_mm=[6+dx,8+dy],terminal_end_mm=[28+dx,8+dy],
        bank_centers_mm=[[16+dx,8+dy],[18+dx,8+dy]],external_leg_span_mm=20)
    before=dict(c.P)
    with mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box), \
            mock.patch.object(cec_pcb,'local_pads',return_value={'1':(0,0)}):
        moves=synth._flow_through_locality_move_specs(c,[row],comps,max_specs=4)
        old=synth._flow_through_locality_move_specs(c,[row],comps,max_specs=4,
                                                   include_in_place_rotations=False)
    assert len(moves)==4 and c.P==before
    assert [m['position'][2] for m in moves[:3]]==[180,90,270]
    assert all(m['orientation_only'] and m['position'][:2]==c.P[name][:2]
               and m['required_eviction_ref'] is None for m in moves[:3])
    assert not any(m.get('orientation_only') for m in old)


def test_in_place_rotation_still_respects_rotated_body_collision():
    c,row,comps,_box=_fixture()
    c.P['INLINE']=(17,8,0);c.P['OBSTACLE']=(17,10,0);comps['OBSTACLE']='OBSTACLE'
    row.update(kind='flow_through_routing_refusal',bank_centers_mm=[[16,8],[18,8]])
    def box(fp,x,y,rot):
        hw,hh=(2,.5) if fp=='INLINE' and rot%180==0 else (.5,2) if fp=='INLINE' else (.3,.3)
        return x-hw,x+hw,y-hh,y+hh
    with mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box), \
            mock.patch.object(cec_pcb,'local_pads',return_value={'1':(0,0)}):
        moves=synth._flow_through_locality_move_specs(c,[row],comps,max_specs=4)
    assert [m['position'][2] for m in moves if m.get('orientation_only')]==[180]


def test_in_place_rotation_does_not_impose_new_translation_packing_margin():
    c,row,comps,box=_fixture()
    c.P['INLINE']=(17,8,0);c.P['NEAR']=(19.05,8,0);comps['NEAR']='NEAR'
    row.update(kind='flow_through_routing_refusal',bank_centers_mm=[[16,8],[18,8]])
    with mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box), \
            mock.patch.object(cec_pcb,'local_pads',return_value={'1':(0,0)}):
        moves=synth._flow_through_locality_move_specs(c,[row],comps,max_specs=4)
        stricter=synth._flow_through_locality_move_specs(c,[row],comps,max_specs=4,in_place_clearance_mm=.1)
    assert moves[0].get('orientation_only')
    assert not any(m.get('orientation_only') for m in stricter)


@pytest.mark.parametrize('clearance',[-1,float('nan'),float('inf')])
def test_invalid_in_place_proposal_clearance_refuses(clearance):
    c,row,comps,box=_fixture()
    with pytest.raises(ValueError,match='proposal clearance'):
        synth._flow_through_locality_move_specs(c,[row],comps,in_place_clearance_mm=clearance)
