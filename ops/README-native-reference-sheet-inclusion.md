# Exact native Ground-reference inclusion

`cec_native_reference_sheet_inclusion.receive` is read-only. It handles the
case where retiring a genuinely obsolete through pickup lets the native zone
filler add Ground to an old anti-pad. Changed fill bytes alone are neither
reference degradation nor permission to bypass reference checks.

It requires the same positive fabrication stack, every actual dedicated
Ground face, the same zone UUIDs, outlines and fill settings, complete saved
native fills, exact original footprints and all surviving via primitives,
and no new or moved bores. Whole-sheet native integer polygon subtraction
must leave **zero** missing source outlines on **every** sheet. Added total
area cannot compensate for even a one-nanometre strip removed elsewhere.
There is no sampling, epsilon, area threshold, polygon healing or percentage
waiver. Retired source holes cannot introduce a new reference void.

For byte-identical pair primitives and actual drilled parts, this establishes
`pair - Ground_child` is a subset of `pair - Ground_source`. The separate
build-time pair adapter also receives exact pair primitives, continuous
geometry and all three existing metric grids. Inherited unsupported power
faces remain explicitly unqualified. Changed pair geometry is refused by
this adapter; it needs its own original typed pair receiver.

This is preservation evidence, not positive impedance/reference, plating,
current, thermal or release qualification. Independent exact conductor
ownership, native DRC, Kelvin, fields, Ground returns and stack checks remain
mandatory. Twenty synthetic native regressions cover frame changes, unknown
fills/settings/profiles, new/moved bores and actual lost metal. Read-only real
replay covers the changed ATX and unchanged Hub/immutable PCIe2 identity
controls without erasing their inherited qualification failures.
