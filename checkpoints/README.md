# Native review controls

`current.json` pins one receipt by its exact SHA-256, never by file age. The
November 4 snapshot contains nine saved PCB families, their actual footprint
libraries, fresh native DRC reports, original reports and source provenance.
It is a portable review checkpoint, **not a fabrication release**. Its native
totals are zero opens, zero errors, zero exclusions and 283 warnings. Retained
EPS field-policy findings are separate from native DRC.

`review-20261104-final` preserves the pre-overhaul layout controls.
`review-20261104-overhaul` adds the independently received, visually reviewed
Hub route-shortening pilot; all other board geometry is identical. Its origin
receipt retains the explicit work order, parent/child identities and plot
identities. `current.json` selects this newer review checkpoint explicitly.

The frontier-directed workbench copies these controls into private jobs. It
cannot overwrite them or silently select a different schematic/PCB revision.
`fork` changes only the campaign's selected working parent after receiving
and visual review. Runtime jobs and plots belong outside this directory.

Footprint-library URIs are relocated; actual footprint file bytes, library
names and enable flags are retained. No library is synthesized from the
embedded board pads. A fresh checkout requires KiCad 10.x and the documented
native reporting build to repeat measurements, but not the original author's
Windows review directory to inspect the saved evidence.
