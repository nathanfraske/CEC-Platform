# Mask-aware dense reference mapping

The general dense-area rule is unchanged: try a readable nearby component map
first; otherwise print an actual-position projected courtyard and reference on
the opposite silkscreen. Back text must read normally from the back. These are
annotation outlines, not relocated components. Values and MPNs remain on Fab.

For current runs use `build/root_run_mask_guarded_reference_mapping_20261020.py`
with the CLI arguments documented in `README-dense-reference-mapping.md`.
It adds the source-bound native-mask-artwork filter in
`cec_reference_mask_obstacles.py` before construction. Solder-mask graphics,
including exposed logos without a pad or net, are obstacles too. Both member ink
and chart decorations are checked. This is an additional conservative preflight,
not a substitute for complete native DRC or permission to close a mask opening.
The original owner and its documentation remain unchanged for historical replay.

`build/root_run_mask_guarded_bounded_reference_pass_20261020.py` advances only
received children. A rejected next child ends the finite pass while retaining
the last passing board and report; it does not lose good work or repeatedly try
the same rejected proposal. Remaining unrepresented references stay visible.
The default pass is finite; a failed bounded search is not a global infeasibility
proof. Neither a lower marking count nor zero opens grants fabrication release.

After a pass, independently reconstruct every saved annotation phase, verify
native-mask witnesses, perform full native and whole-board checks, and inspect
the actual native front/back glyphs. The current progress registry binds the
exact candidate hashes, source boards, review resources, control replay and
test packet; do not infer that a historical screenshot is the current board.
