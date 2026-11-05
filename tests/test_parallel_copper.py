import pytest
from cec_parallel_copper import connected_proposals, normalize_proposals


@pytest.mark.parametrize('offset', [0.,31.7])
@pytest.mark.parametrize('reverse', [False,True])
def test_unconnected_mirror_branch_does_not_become_copper(offset,reverse):
    segments = [(offset,0,offset+3,0,.5), (offset+3,0,offset+6,0,.5),
                (offset+3,0,offset+3,2,.5)]
    if reverse: segments = [(*s[2:4],*s[:2],s[4]) for s in segments[::-1]]
    contacts = {(offset,0),(offset+6,0)}
    indices = connected_proposals(segments,lambda p:p in contacts)
    assert len(indices) == 2
    assert all(segments[i][1] == segments[i][3] == 0 for i in indices)


def test_open_single_contact_path_and_orphan_loop_refused():
    assert connected_proposals([(0,0,3,0,.5),(3,0,6,0,.5)],lambda p:p==(0,0)) == []
    loop=[(0,0,2,0,.5),(2,0,2,2,.5),(2,2,0,2,.5),(0,2,0,0,.5)]
    assert connected_proposals(loop,lambda p:False) == []
    assert connected_proposals(loop,lambda p:p==(0,0)) == []


def test_direct_dual_anchor_and_mid_segment_t_contacts():
    segments=[(0,0,6,0,.5),(3,0,3,4,.5)]
    assert connected_proposals(segments,lambda p:p in {(0,0),(6,0),(3,4)}) == [0,1]


def test_coincident_proposals_do_not_invent_primary_contacts():
    assert connected_proposals([(0,0,3,0,.5),(0,0,3,0,.5)],lambda p:False) == []


@pytest.mark.parametrize('reverse',[False,True])
def test_overlapping_drops_cannot_provide_fake_anchor_to_each_other(reverse):
    rows=[(1.,0.,1.,10.5,1.4),(1.,0.,1.,5.,1.4)]
    if reverse: rows=[(*r[2:4],*r[:2],r[4]) for r in rows[::-1]]
    clean=normalize_proposals(rows)
    selected=connected_proposals(clean,lambda p:p in {(1.,5.),(1.,10.5)})
    assert [clean[i] for i in selected] == [(1.,5.,1.,10.5,1.4)]


def test_normalization_preserves_widest_width_in_every_covered_interval():
    rows=[(0,0,10,0,1.),(2,0,6,0,2.),(6,0,2,0,2.)]
    assert normalize_proposals(rows) == [(0.,0.,2.,0.,1.),(2.,0.,6.,0.,2.),(6.,0.,10.,0.,1.)]


def test_collapsed_collector_has_no_optional_parallel_path():
    assert normalize_proposals([(1.,2.,1.,2.,.5)]) == []


def test_round_caps_cannot_fake_junctions_on_a_wide_segment_chain():
    segments=[(0,0,1,0,5.),(1,0,2,0,5.),(2,0,3,0,5.),(3,0,6,0,5.)]
    selected=connected_proposals(segments,lambda p:p in {(3,0),(6,0)})
    assert selected == [3]
