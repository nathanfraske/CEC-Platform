"""Saved-copper union proof is independent of board/net/refdes identities."""
import uuid

import pytest

import cec_exact_overlap_receiving as overlap


IDS = [str(uuid.UUID(int=i)) for i in range(1, 5)]


def segment(ident, start, end, *, width='.2', net='"arbitrary-renamed"',
            layer='"F.Cu"', extra='locked'):
    return ('(segment (start %s %s) (end %s %s) (width %s) (layer %s) '
            '(net %s) (uuid "%s") %s)' % (*start, *end, width, layer, net, ident, extra))


def boards(tmp_path, old, new, *, old_fixed='', new_fixed=None):
    paths = [tmp_path / (name + '.kicad_pcb') for name in ('source', 'candidate')]
    for path, rows, fixed in zip(paths, (old, new),
                                (old_fixed, old_fixed if new_fixed is None else new_fixed)):
        path.write_text('(kicad_pcb (version 20260206) ' + fixed + ' '.join(rows) + ')')
    return paths


@pytest.mark.parametrize('layer,net', [('"F.Cu"', '"unfamiliar-net"'),
                                     ('"B.Cu"', '"/OTHER/NAME"')])
@pytest.mark.parametrize('points', [((0, 0), (2, 0), (5, 0)),
                                   ((4, 1), (4, 3), (4, 6)),
                                   ((0, 0), (2, 2), (5, 5)),
                                   ((6, 1), (4, 3), (1, 6))])
def test_exact_prefix_trim_is_bidirectionally_equivalent(tmp_path, layer, net, points):
    a, b, c = points
    old = [segment(IDS[0], a, c, layer=layer, net=net),
           segment(IDS[1], a, b, layer=layer, net=net)]
    new = [segment(IDS[0], b, c, layer=layer, net=net), old[1]]
    proof = overlap.receive(*boards(tmp_path, old, new), source_track_uuids=IDS[:2])
    assert proof['ok'] and proof['complete'] and proof['reciprocal_copper_coverage']
    assert len(proof['proofs']) == 4 and not proof['native_copper_mutated']
    assert not proof['release_authority']


def test_exact_duplicate_can_be_retired_without_modifying_other_objects(tmp_path):
    old = [segment(i, (1, 1), (3, 3)) for i in IDS[:2]]
    fixed = '(footprint "unrelated" (at 4 6) (property "MPN" "unchanged"))'
    proof = overlap.receive(*boards(tmp_path, old, old[:1], old_fixed=fixed),
                            source_track_uuids=IDS[:2])
    assert proof['ok'] and proof['source_tracks'] == 2 and proof['candidate_tracks'] == 1
    assert proof['non_scoped_board_state_unchanged']


@pytest.mark.parametrize('changed', [
    dict(start=(0, '.000001'), end=(5, '.000001')),
    dict(start=(0, 0), end=(5, 0), width='.199999'),
    dict(start=(0, 0), end=(5, 0), width='.200001'),
    dict(start=(0, 0), end=(5, 0), net='"wrong-net"'),
    dict(start=(0, 0), end=(5, 0), layer='"B.Cu"'),
    dict(start=(0, 0), end=(5, 0), extra='locked (mask_margin .001)'),
    dict(start=(0, 0), end=(5, 0), extra='(unrecognized_factory_field changed)'),
])
def test_gap_dimension_layer_net_mask_or_unknown_field_change_refuses(tmp_path, changed):
    old = [segment(IDS[0], (0, 0), (5, 0))]
    new = [segment(IDS[0], **changed)]
    proof = overlap.receive(*boards(tmp_path, old, new), source_track_uuids=IDS[:1])
    assert not proof['ok'] and not proof['reciprocal_copper_coverage']


def test_one_nanometre_interval_gap_is_not_rounded_away(tmp_path):
    old = [segment(IDS[0], (0, 0), (5, 0)), segment(IDS[1], (0, 0), (2, 0))]
    new = [segment(IDS[0], ('2.000001', 0), (5, 0)), old[1]]
    assert not overlap.receive(*boards(tmp_path, old, new), source_track_uuids=IDS[:2])['ok']


def test_reverse_track_direction_is_coverage_not_identity_failure(tmp_path):
    old = [segment(IDS[0], (0, 0), (5, 5))]
    new = [segment(IDS[0], (5, 5), (0, 0))]
    assert overlap.receive(*boards(tmp_path, old, new), source_track_uuids=IDS[:1])['ok']


@pytest.mark.parametrize('fixed', ['(footprint "other" (at 1 2))',
                                   '(zone (net "GND") (name "moved"))',
                                   '(via (at 1 2) (size .5) (drill .3))'])
def test_unrelated_board_state_is_immutable(tmp_path, fixed):
    old = [segment(IDS[0], (0, 0), (5, 0))]
    proof = overlap.receive(*boards(tmp_path, old, old, new_fixed=fixed),
                            source_track_uuids=IDS[:1])
    assert proof['errors'] == ['non_scoped_board_state_changed']


def test_scope_does_not_authorize_new_ids_or_extra_copper(tmp_path):
    old = [segment(IDS[0], (0, 0), (5, 0))]
    new = old + [segment(IDS[2], (0, 1), (5, 1))]
    proof = overlap.receive(*boards(tmp_path, old, new), source_track_uuids=IDS[:1])
    assert not proof['ok']


def test_group_owner_requires_upstream_recompile_even_with_identical_copper(tmp_path):
    old = [segment(i, (0, 0), (5, 0)) for i in IDS[:2]]
    group = '(group "any-owner" (members "%s" "%s"))' % tuple(IDS[:2])
    proof = overlap.receive(*boards(tmp_path, old, old[:1], old_fixed=group),
                            source_track_uuids=IDS[:2])
    assert proof['errors'] == ['group_owner_recompile_required']


@pytest.mark.parametrize('net,width', [('""', '.2'), ('0', '.2'), ('"assigned"', '0')])
def test_unassigned_or_zero_width_native_segment_refuses(tmp_path, net, width):
    old = [segment(IDS[0], (0, 0), (5, 0), net=net, width=width)]
    assert not overlap.receive(*boards(tmp_path, old, old), source_track_uuids=IDS[:1])['ok']


def test_exhausted_time_and_pair_budget_are_unknown_not_coverage_pass(tmp_path):
    old = [segment(i, (0, 0), (5, 0)) for i in IDS[:2]]
    paths = boards(tmp_path, old, old)
    for policy in (dict(timeout_s=0), dict(max_pairs=1)):
        proof = overlap.receive(*paths, source_track_uuids=IDS[:2], **policy)
        assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('scope', [[], IDS[:1] * 2, ['"not-a-native-id"']])
def test_invalid_scope_is_not_an_ownership_grant(tmp_path, scope):
    old = [segment(IDS[0], (0, 0), (5, 0))]
    with pytest.raises(ValueError):
        overlap.receive(*boards(tmp_path, old, old), source_track_uuids=scope)


@pytest.mark.parametrize('points', [((0,0),(2,0),(5,0)),((4,1),(4,3),(4,6)),
    ((0,0),(2,2),(5,5)),((6,1),(4,3),(1,6))])
@pytest.mark.parametrize('layer',['"F.Cu"','"B.Cu"'])
@pytest.mark.parametrize('locks',[('locked',''),('','locked'),('(locked yes)',''),('', '(locked yes)')])
def test_separate_lock_proof_preserves_each_source_lock_without_changing_capsule_union(tmp_path,points,layer,locks):
    a,b,c=points
    old=[segment(IDS[0],a,c,layer=layer,extra=locks[0]),segment(IDS[1],a,b,layer=layer,extra=locks[1])]
    new=[segment(IDS[0],b,c,layer=layer,extra=locks[0]),old[1]]
    source,child=boards(tmp_path,old,new);original=[p.read_bytes() for p in (source,child)]
    assert not overlap.receive(source,child,source_track_uuids=IDS[:2])['ok']
    r=overlap.receive(source,child,source_track_uuids=IDS[:2],retain_per_item_locks=True)
    assert r['ok'] and r['complete'] and r['every_surviving_source_track_lock_retained'],r
    assert r['reciprocal_copper_coverage'] and not r['release_authority']
    assert original==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('fault',['unlock_long','lock_short','alter_lock_syntax','unknown_field','mask',
    'width','foreign_net','ambiguous_locks','nonbool'])
def test_lock_separation_cannot_mask_lock_fabrication_or_unknown_field_changes(tmp_path,fault):
    old=[segment(IDS[0],(0,0),(5,0),extra='locked'),segment(IDS[1],(0,0),(2,0),extra='')]
    first=dict(ident=IDS[0],start=(2,0),end=(5,0),extra='locked')
    second=dict(ident=IDS[1],start=(0,0),end=(2,0),extra='')
    if fault=='unlock_long':first['extra']=''
    elif fault=='lock_short':second['extra']='locked'
    elif fault=='alter_lock_syntax':first['extra']='(locked yes)'
    elif fault=='unknown_field':second['extra']='(unrecognized_factory_field changed)'
    elif fault=='mask':second['extra']='(mask_margin .001)'
    elif fault=='width':second['width']='.200001'
    elif fault=='foreign_net':second['net']='"other-net"'
    elif fault=='ambiguous_locks':old[0]=segment(IDS[0],(0,0),(5,0),extra='locked locked')
    paths=boards(tmp_path,old,[segment(**first),segment(**second)])
    if fault=='nonbool':
        with pytest.raises(ValueError):overlap.receive(*paths,source_track_uuids=IDS[:2],retain_per_item_locks=1)
    else:
        r=overlap.receive(*paths,source_track_uuids=IDS[:2],retain_per_item_locks=True)
        assert not r['ok'] and not r['complete'],r
