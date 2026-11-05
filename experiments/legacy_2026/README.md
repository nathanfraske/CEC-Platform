# Preserved 2026 development operators

These historical helper modules were required by the regression suite but
lived under Git-ignored `build/`. They are promoted here so a clean checkout
can run the tests and inspect the original work. Their date-stamped names
are compatibility identifiers, not the active pipeline API.

The model-directed control plane is `src/cec_pipeline`. Reusable construction
and independent physical validators belong there or behind its explicit
legacy adapter, not in a new date-stamped operator. Historical board work
orders and experiment drivers are not generalized merely by being preserved.

The promotion inventory records original paths and hashes. Only a repository
root discovery expression is mechanically adjusted for this new directory.
No current requirement, native rule or receiving predicate is relaxed.
