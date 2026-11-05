import math

import cec_precision_route as route


def test_all_eight_escape_headings_preserve_local_polarity():
    for rotate in range(8):
        angle = rotate * math.pi / 4
        def transform(p):
            x, y = p
            return (9 + x*math.cos(angle)-y*math.sin(angle),
                    12 + x*math.sin(angle)+y*math.cos(angle))
        plan = route._paired_portal_candidates(
            *map(transform, [(0, -.5), (0, .5), (20, -.9), (20, .9)]),
            width=.2, gap=.3, portal_separation=.85)
        for sign in (1, -1):
            representatives = {}
            for side in ('start', 'end'):
                rows = plan['by_sign'][sign][side]
                assert {r['escape_heading_step'] for r in rows} == {0,4,1,-1,2,-2,3,-3}
                representatives[side] = {}
                for row in rows:
                    hx, hy = row['route_heading']
                    dx, dy = row['p'][0]-row['n'][0], row['p'][1]-row['n'][1]
                    assert abs(hx*dx + hy*dy) < 1e-8
                    assert math.isclose(math.hypot(dx,dy), .85)
                    assert (hx*dy-hy*dx)*sign*(1 if side=='start' else -1) > 0
                    representatives[side][row['escape_heading_step']] = row
            for start in representatives['start'].values():
                for end in representatives['end'].values():
                    assert route._paired_portal_lane_compatible(start, end)
                    swapped = dict(end, p=end['n'], n=end['p'])
                    assert not route._paired_portal_lane_compatible(start, swapped)


def test_bounded_screen_order_covers_sideways_headings_before_repeated_depth():
    plan = route._paired_portal_candidates((0,-.5),(0,.5),(20,-.5),(20,.5),width=.2,gap=.3)
    rows = route._fair_portal_screen_order(plan['by_sign'][1]['start'],
                                         lambda r: abs(r['lateral_mm']))
    assert {r['escape_heading_step'] for r in rows[:8]} == {0,4,1,-1,2,-2,3,-3}
