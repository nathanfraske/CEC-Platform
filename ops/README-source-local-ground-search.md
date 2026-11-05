# Bounded source-local Ground entry search

`cec_source_local_ground_search.discover` observes the actual saved populated
SMD Ground terminals, including IC pins, not a capacitor/refdes whitelist.
Known returns longer than the requested reach are tried longest first. Unknown
returns remain declared unknown, not electrical opens or infinite distances.

The finite parameterized menu contains the exact Source pad centre and cardinal
or 45-degree offsets. Only a literal existing saved local POFV rule enables its
scoped dogbone geometry. Otherwise the unchanged ordinary entry producer is
used. All-layer copper, holes, edges, process ownership and reference-plane
contacts remain mandatory. This search does not move power buses or parts.

The worker `build/root_run_source_local_ground_search_20261019.py` binds the
actual complete native Source report, constructs at most one proposal, and
replays it with `cec_ground_access_completion.receive` and fresh uncapped native
DRC. A failure or exhausted menu is a durable bounded receipt, not a no-path
proof. Whole-parent current, Kelvin, fields, stack, dimensions and qualification
are separate gates. No automatic source selection or fab-ready flag is set.

Negative POFV sites are pruned with the same native guards on one unchanged
read-only Source snapshot. Only its foreign-shape indices are reused. Each
attempt retains edge, hole, via and surface results and literal via-blocker
IDs/layers. Every positive site still calls the fresh Source-bound planner;
the pruning cache cannot grant construction or receiving permission.
