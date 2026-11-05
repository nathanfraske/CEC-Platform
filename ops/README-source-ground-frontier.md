# Source Ground search coverage

`cec_source_ground_frontier` preserves the existing Ground-entry planner,
constructor and independent saved-board receiver. It changes search coverage,
not electrical, process, current, clearance or qualification limits.

The original longest-first search only examines up to sixteen terminals.
An empty prefix can therefore hide legal short returns. The new finite
inventory contains every eligible observed populated SMD Ground terminal and
every configured cardinal/45-degree site. Unknown witnesses remain declared;
they are not counted as opens or assigned infinite length.

Pages continue at a literal site index, including when a budget stops within
one terminal's stencil. Continuations bind the exact saved Source family,
runtime epoch, helpers, observed witnesses, process-derived geometry and
search settings. Any changed Source or setting requires a fresh inventory.
Coverage validates contiguous actual attempt records; it does not establish
that a refused route is impossible. A bounded stop is not a plateau or no-path
proof. The finite menu itself is not a global optimal-placement search.

Every positive proposal still passes the original all-layer native geometry
guards, original additive reconstruction, all known Ground-return
nonregression, actual plane contact checks and saved-board native DRC. Full
parent current, clipped Kelvin, field, stack and fabrication receiving remain
separate. No original conductor is retired by this discovery extension.

The small operational driver is
`build/root_run_paged_source_ground_search_20261020.py`. Use explicit finite
page bounds, run headless, and do not promote its private candidate based on
the search result alone. Regression fixtures do not assign hardware ratings.
