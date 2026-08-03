#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""gen-bom-outputs -- generate a board's committed bom/ outputs from its schematic.

Emits the two committed BOM artifacts (the per-board `bom/` dir convention):

  * `<board>-BOM-jlcpcb.csv`  -- assembly CSV, JLCPCB column set
    (`Comment,Designator,Footprint,LCSC Part #`), DNP excluded, quoted fields,
    full footprint ids (the pcie-8pin convention).
  * `bom.csv`                 -- the sourcing/tracking sheet (alpha-board 13-column
    header), DNP parts INCLUDED and marked, Note property carried to Notes.

Extraction runs through `kicad-cli sch export bom` (never a hand parse of the
s-expr), so hierarchical sheets, instance references, and in_bom/dnp flags are
resolved by KiCad itself. Symbols carry their LCSC number under either `LCSC`
or `LCSC Part` (two sourcing-pass generations coexist); the two are coalesced,
`LCSC` winning when both are set.

Usage: python3 scripts/gen-bom-outputs.py <board-dir> [--force]

Refuses to overwrite an existing bom/ dir without --force (the committed CSVs
may carry hand enrichment -- e.g. the EPS/PCIe shunt-row DigiKey-channel
comments -- that a regen would flatten).
"""
import argparse
import csv
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_toolchain as tc                                        # noqa: E402

FIELDS = ("Value,Reference,Footprint,LCSC,LCSC Part,MPN,Manufacturer,Datasheet,"
          "Description,Note,QUANTITY,DNP")


def _export(sch, exclude_dnp):
    out = tempfile.mktemp(suffix=".csv")
    cmd = ["kicad-cli", "sch", "export", "bom", "-o", out,
           "--fields", FIELDS, "--labels", FIELDS,
           "--group-by", "Value,Footprint,LCSC,LCSC Part,MPN",
           "--ref-range-delimiter", "", sch]
    if exclude_dnp:
        cmd.insert(-1, "--exclude-dnp")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli export bom failed:\n{r.stdout}{r.stderr}")
    with open(out, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    os.unlink(out)
    for row in rows:
        row["LCSC"] = (row.get("LCSC") or "").strip() or (row.get("LCSC Part") or "").strip()
    rows.sort(key=lambda r: (r["Reference"].split(",")[0][:2], r["Reference"]))
    return rows


def _short_fp(fpid):
    return fpid.split(":", 1)[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board_dir")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    d = a.board_dir.rstrip("/")
    sch = tc.find_root_sch(d)
    if not sch:
        raise SystemExit(f"no root schematic found under {d}")
    name = os.path.splitext(os.path.basename(sch))[0]
    bom_dir = os.path.join(d, "bom")
    if os.path.isdir(bom_dir) and os.listdir(bom_dir) and not a.force:
        raise SystemExit(f"{bom_dir} exists and is non-empty; pass --force to overwrite "
                         "(committed CSVs may carry hand enrichment)")
    os.makedirs(bom_dir, exist_ok=True)

    jlc = os.path.join(bom_dir, f"{name}-BOM-jlcpcb.csv")
    with open(jlc, "w", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for row in _export(sch, exclude_dnp=True):
            w.writerow([row["Value"], row["Reference"], row["Footprint"], row["LCSC"]])
    print(f"wrote {jlc}")

    track = os.path.join(bom_dir, "bom.csv")
    with open(track, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Reference", "Qty", "Value", "Footprint", "MPN", "Manufacturer",
                    "LCSC", "LC_Stock", "Chosen_Distributor", "Datasheet", "Validated",
                    "DNP", "Notes"])
        for row in _export(sch, exclude_dnp=False):
            w.writerow([row["Reference"], row["QUANTITY"], row["Value"],
                        _short_fp(row["Footprint"]), row.get("MPN", ""),
                        row.get("Manufacturer", ""), row["LCSC"], "", "",
                        row.get("Datasheet", ""), "",
                        row.get("DNP", ""),
                        row.get("Note", "") or row.get("Description", "")])
    print(f"wrote {track}")


if __name__ == "__main__":
    main()
