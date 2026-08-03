#!/usr/bin/env python3
"""Repair evidence-backed BOM metadata on the legacy flat EPS rev3 schematic.

The file was generated with the Manufacturer and LCSC values reversed on
assembled parts.  This repair only swaps a pair when one side is an LCSC
identifier (``C`` followed by digits) and the other side is not.  It also
backfills two selections already encoded elsewhere in the same design line:

* the connector footprint names the exact Molex 87427-0802 header;
* the hierarchical EPS schematic locks RS1/RS2 to Bourns
  CSS2H-2512R-L500F.

No electrical values, substitutions, or unselected parts are inferred.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_sch_layout as L  # noqa: E402
import cec_sch  # noqa: E402


DEFAULT = os.path.join(
    ROOT, "old-revisions", "beta", "eps-8pin-rev3-flat-2026-08-02",
    "eps-8pin-rev3.kicad_sch")
LCSC_RE = re.compile(r"^C\d+$")

MOLEX_87427 = {
    "Manufacturer": "Molex",
    "MPN": "87427-0802",
    "Datasheet": (
        "https://www.molex.com/content/dam/molex/molex-dot-com/products/"
        "automated/en-us/productspecificationpdf/874/87427/"
        "PS-87427-0001-001.pdf"
    ),
}

BOURNS_L500 = {
    "Manufacturer": "Bourns",
    "MPN": "CSS2H-2512R-L500F",
    "Datasheet": "https://www.bourns.com/docs/product-datasheets/css2h-2512.pdf",
    "Note": (
        "OQ-11 locked selection on the single current EPS product: 0.5mOhm, "
        "CSS2H-2512R-L500F. Distributor availability remains a BOM-freeze check."
    ),
}

BACKFILL = {
    **{ref: MOLEX_87427 for ref in ("J_IN1", "J_OUT1", "J_IN2", "J_OUT2")},
    **{ref: BOURNS_L500 for ref in ("RS1", "RS2")},
}

# The beta lock register and the hierarchical EPS implementation both select
# this exact receptacle.  The flat rev3 file still carried the rejected
# C2765186 line, while its footprint already used KiCad's verified 16XN name
# for the U262-161N body.  This is an explicit stale-selection correction,
# not a package inference.
FORCE = {
    "J5": {
        "Manufacturer": "XKB Connection",
        "MPN": "U262-161N-4BVC11",
        "LCSC": "C319148",
        "Datasheet": (
            "https://datasheet.lcsc.com/szlcsc/1811141824_XKB-Enterprise-"
            "U262-161N-4BVC11_C319148.pdf"
        ),
    }
}


def _unescape(value: str) -> str:
    return L._unescape(value)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _properties(block: str) -> dict[str, str]:
    return {
        _unescape(m.group(1)): _unescape(m.group(2))
        for m in re.finditer(
            r'\(property\s+"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"',
            block,
        )
    }


def _set_property(block: str, name: str, value: str) -> str:
    encoded = _escape(value)
    pattern = re.compile(
        r'(\(property\s+"' + re.escape(name) + r'"\s+")'
        r'((?:[^"\\]|\\.)*)(")'
    )
    if pattern.search(block):
        return pattern.sub(lambda m: m.group(1) + encoded + m.group(3), block, count=1)

    # Insert after the complete Datasheet S-expression.  Some native KiCad
    # files format properties across many lines, so inserting after only the
    # `(at ...)` line would split and corrupt the existing property.
    anchor = re.search(
        r'(?m)^(\s*)\(property\s+"Datasheet"\s+"(?:[^"\\]|\\.)*"', block
    )
    if not anchor:
        raise ValueError(f"cannot add {name}: no Datasheet property")
    anchor_block = cec_sch.carve(block, anchor.start())
    insert_at = anchor.start() + len(anchor_block)
    indent = anchor.group(1)
    line = (
        f'{indent}(property "{name}" "{encoded}" (at 0 0 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))'
    )
    return block[:insert_at] + "\n" + line + block[insert_at:]


def repair_text(text: str) -> tuple[str, list[str]]:
    work = L._strip_lib_symbols(text)
    changed: list[str] = []
    spans = L._symbol_spans(work)
    for start, end, _at, ref, _rot, _lib_id, _mir in reversed(spans):
        block = text[start:end]
        props = _properties(block)
        manufacturer = props.get("Manufacturer", "")
        lcsc = props.get("LCSC", "")
        touched = False

        if LCSC_RE.fullmatch(manufacturer) and lcsc and not LCSC_RE.fullmatch(lcsc):
            block = _set_property(block, "Manufacturer", lcsc)
            block = _set_property(block, "LCSC", manufacturer)
            touched = True

        for name, value in BACKFILL.get(ref, {}).items():
            current = _properties(block).get(name, "")
            if not current:
                block = _set_property(block, name, value)
                touched = True

        for name, value in FORCE.get(ref, {}).items():
            if _properties(block).get(name, "") != value:
                block = _set_property(block, name, value)
                touched = True

        if touched:
            text = text[:start] + block + text[end:]
            changed.append(ref)
    return text, sorted(changed)


def repair_file(path: str, *, check: bool = False) -> list[str]:
    with open(path, encoding="utf-8", errors="strict") as handle:
        before = handle.read()
    after, changed = repair_text(before)
    if check:
        return changed
    if after != before:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(after)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=DEFAULT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    changed = repair_file(args.path, check=args.check)
    if args.check:
        if changed:
            print("repair required: " + ", ".join(changed))
            return 1
        print("EPS rev3 BOM fields already normalized")
        return 0
    print("repaired: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
