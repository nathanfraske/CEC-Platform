#!/usr/bin/env python3
"""POUR-FIRST demonstrator (owner ruling 2026-07-25): strip a board to its
anchor skeleton -- connectors, blueprint sense stamps, MCU -- solve the pours
TIGHT on that open field, and save the pour state as an owner-reviewable
artifact. This is the compute core of the coming pour-first placement rung
("pours are the first rung after connectors + stamps + MCU; then re-add
everything else"); as a standalone script it answers "save the pour state
for me to look at" on any existing variant board.

Usage (in the routing container):
    python3 scripts/cec_pourfirst.py <board.kicad_pcb> [--out-dir DIR]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KEEP_VALUE_SUBSTR = ("ESP32", "INA238", "INA181", "TLV7011")


def _keep_footprint(fp):
    ref = fp.GetReference() or ""
    val = (fp.GetValue() or "").upper()
    if ref.startswith(("TB", "J", "RS", "H", "FID")):
        return True                      # connectors, blades, shunts, furniture
    return any(s in val for s in KEEP_VALUE_SUBSTR)


def sparse_pour_state(board_path, out_dir, *, manifolds=False):
    import pcbnew
    import cec_slab_pour
    import cec_fr

    board = pcbnew.LoadBoard(board_path)
    dropped_fps = [fp for fp in board.GetFootprints() if not _keep_footprint(fp)]
    for fp in dropped_fps:
        board.Delete(fp)
    # FR output goes; LOCKED pre-route copper (force rails, taps) stays --
    # it is board truth the pours coexist with.
    doomed = [t for t in board.GetTracks() if not t.IsLocked()]
    for t in doomed:
        board.Delete(t)
    old_zones = [z for z in board.Zones() if z.GetNetname() != "GND"]
    for z in old_zones:
        board.Delete(z)
    board.BuildConnectivity()
    print(f"[pourfirst] skeleton: dropped {len(dropped_fps)} footprint(s), "
          f"{len(doomed)} track/via(s), {len(old_zones)} non-GND zone(s); "
          f"kept {len(list(board.GetFootprints()))} anchor footprint(s)")

    nets = sorted(n for n in
                  (ni.GetNetname() for ni in
                   board.GetNetInfo().NetsByNetcode().values())
                  if n.startswith("/SENSE") or n in ("+5V_MAIN", "+5VSB", "+3V3"))
    asks = [{"net": n, "layer": "In2.Cu", "provenance": "placer_ask"}
            for n in nets]
    print(f"[pourfirst] asks: {nets}")

    # --manifolds: the v3.1 connector-manifold stage 0 + width-margin attach
    # (docs/slab-pour-design-2026-07-24.md v3.1) -- the A/B lever for the
    # three recorded skeleton no-paths (+5VSB, /SENSE12V_HI, /SENSE5V_HI).
    lanes, vias, rep = cec_slab_pour.synthesize_overunder_pours(
        board, asks, manifolds=manifolds)
    patches = cec_slab_pour.guaranteed_shunt_patches(board)
    if vias:
        cec_fr.add_overunder_vias(board, vias)
    cec_fr.add_power_pours(board, list(lanes) + patches, fill=False)
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    base = os.path.splitext(os.path.basename(board_path))[0]
    os.makedirs(out_dir, exist_ok=True)
    out_pcb = os.path.join(out_dir, f"POURFIRST-{base}.kicad_pcb")
    pcbnew.SaveBoard(out_pcb, board)
    for n in nets:
        v = rep.get(n, {})
        print(f"[pourfirst] {n}: path_found={v.get('path_found')} "
              f"segments={v.get('segments', 0)} bridges={v.get('bridges', 0)} "
              f"layers={v.get('layers_used', [])}"
              + (f" bottleneck={v.get('bottleneck')}"
                 if not v.get("path_found") else ""))
    print(f"[pourfirst] saved {out_pcb} ({len(lanes)} lane(s), "
          f"{len(patches)} patch(es), {len(vias)} bridge via(s))")
    try:
        import cec_render
        png = cec_render.hex_panel(
            out_pcb, os.path.join(out_dir, f"POURFIRST-{base}-hex.png"))
        print(f"[pourfirst] render: {png}")
    except Exception as e:                                 # noqa: BLE001
        print(f"[pourfirst] render skipped ({e})")
    return out_pcb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--manifolds", action="store_true",
                    help="v3.1 connector manifolds + width-margin attach")
    a = ap.parse_args()
    out = a.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "build", "wave-snaps",
        os.path.basename(os.path.dirname(a.board)) or "pourfirst")
    sparse_pour_state(a.board, os.path.normpath(out), manifolds=a.manifolds)


if __name__ == "__main__":
    main()
