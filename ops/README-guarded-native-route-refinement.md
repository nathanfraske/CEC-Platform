# Whole-route guarded octilinear refinement

The native maze's internal heading policy does not prove that its off-grid
terminal hooks obey the same policy. `cec_guarded_octilinear_refinement.py`
therefore treats the COMPLETE returned polyline as an unaccepted proposal.

It keeps exact integer end ports, never silently snaps non-45-degree input,
and enumerates a bounded set of 0/45-degree visibility shortcuts. Every new
leg must receive a literal positive result from the caller's unchanged native
edge, hole, rule-area and foreign-copper guards. Native geometry/clearance
checks are not replaced by a coarse congestion-map or picture-based test.
Ranking first reduces invalid turns, then length and redundant vertices.

Only a complete non-self-crossing path with all turns at most 45 degrees is
returned. Failed, timed-out or exhausted searches cannot return a partial
route or reclassify a remaining hard corner as finished. The finite menu is
not a global shortest-path/no-path certificate. The helper owns no PCB
mutation, net, current budget, barrel, terminal move or admission; the typed
source owner and all whole-board receiving still run independently.
