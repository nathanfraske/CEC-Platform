# Legacy annotation group round-trip repair

The previous rear-reference producer put actual footprint-child silk graphics
in a board-level `CEC_READABLE_COMPONENT_REFERENCE_MAPPING` group. KiCad saved
that membership once but reloaded the group empty. A later unrelated save
dropped it, so exact routing receivers rejected an extra unowned group cut.
Some negative annotation tests also failed for that unrelated reason.

The producer now relies exclusively on native footprint-child ownership for
rear marks. Front charts still have a durable rigid group containing actual
board drawings and footprints. Receiving and new frame tests require a second
save/reload to preserve the entire saved board, not just visible copper.

`cec_annotation_group_roundtrip.py` owns only that legacy producer's locked,
unresolved groups whose raw members are actual retained non-copper footprint
silkscreen graphics. Every literal Source item except the exact broken group
metadata must be identical. A second native save must then remain identical.
Unknown, functional, copper-owning, mixed or parent-owned groups are refused.
No glyph, field, component, pad, copper, rule, budget or valid group is changed.
This is not generic permission to discard empty groups or to admit routing.
