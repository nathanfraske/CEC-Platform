import cec_fr


def anchor(x, y, layers=(0,), escape=None, kind="trk", uid="one"):
    return (x, y, frozenset(layers), escape, {"kind": kind, "uuid": uid})


def test_track_junction_aliases_do_not_consume_the_anchor_frontier():
    left = [anchor(0, 0, kind="pad")]
    right = [anchor(1000000, 0, uid=str(i)) for i in range(20)]
    right.append(anchor(2000000, 1000000, uid="alternative"))
    rows = cec_fr._bounded_route_aware_anchor_pairs(left, right, limit=4, max_mm=10)
    assert len(rows) == 2
    assert rows[1][2][4]["uuid"] == "alternative"


def test_exact_layers_and_escape_authority_are_not_coalesced():
    variants = [anchor(0, 0), anchor(0, 0, layers=(2,)),
        anchor(0, 0, layers=(0,2)), anchor(1, 0),
        anchor(0, 0, escape=(150000, 600000)),
        anchor(0, 0, escape=(150000, 700000))]
    assert cec_fr._unique_route_anchors(variants) == variants


def test_physical_owner_wins_without_reordering_other_geometry():
    track = anchor(0, 0)
    pad = anchor(0, 0, kind="pad", uid="physical")
    different = anchor(1, 1)
    assert cec_fr._unique_route_anchors([track, different, pad]) == [pad, different]
    assert cec_fr._unique_route_anchors([pad, different, track]) == [pad, different]


def test_spanning_duplicates_do_not_fake_a_large_rail_portfolio():
    pad = anchor(0, 0, escape=(150000, 600000), kind="pad")
    via = anchor(1000000, 1000000, layers=(0,2), kind="via")
    other = anchor(2000000, 0, uid="surface")
    rows = cec_fr._bounded_route_aware_anchor_pairs(
        [pad], [via]*30 + [other], limit=8, max_mm=10)
    assert len(rows) == 2 and {id(row[2]) for row in rows} == {id(via), id(other)}
