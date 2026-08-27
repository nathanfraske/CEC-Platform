#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply the reviewed XFCN terminal contract to current Standard Beta sources.

The transformation is fail-closed and idempotent.  It replaces interface
*groups* (not one footprint at a time), preserves every retained net stub, and
removes the surplus stub/label with every retired blade.  EPS is the one
topology change: its two 2x4 output headers become four one-node terminals per
cable while the post-shunt SENSEC*_LO domains remain separate.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

import cec_sch
import cec_xfcn_contract as contract
from splice_usb_ingress_common import (
    emit_hier_label,
    find_symbol_block,
    get_pin_table,
    remove_pin_stub,
    remove_symbol,
    remove_terminal_at,
    wire_and_label,
    wire_and_power,
)


ROOT = contract.ROOT
SOURCE_LIB = ROOT / "lib/vendor/Connector_Screw.kicad_sym"


def _atomic_write(path: Path, text: str):
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _source_block(name):
    return cec_sch.symbol_block(SOURCE_LIB.read_text(encoding="utf-8"), name)


def _source_properties(name):
    block = _source_block(name)
    props = {}
    for match in re.finditer(
            r'\(property\s+"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"', block):
        props[match.group(1)] = match.group(2)
    return props


def _ensure_embedded(text, name):
    lib_id = f"{contract.LIB}:{name}"
    if f'(symbol "{lib_id}"' in text:
        return text
    block = cec_sch.reindent(
        cec_sch._namespace(_source_block(name), name, contract.LIB), 2)
    start = text.index("\t(lib_symbols")
    close = text.index("\n\t)\n", start)
    return text[:close + 1] + block + "\n" + text[close + 1:]


def _drop_embedded(text, name):
    """Remove an obsolete embedded library symbol after all instances migrate."""
    lib_id = f"{contract.LIB}:{name}"
    marker = f'(symbol "{lib_id}"'
    start = text.find(marker)
    if start < 0:
        return text
    if f'(lib_id "{lib_id}")' in text:
        raise SystemExit(f"REFUSE: cannot drop embedded symbol still used by an instance: {lib_id}")
    end = start + len(cec_sch.carve(text, start))
    while start > 0 and text[start - 1] in "\t ":
        start -= 1
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + text[end:]


def _property_span(block, name):
    match = re.search(r'\(property\s+"' + re.escape(name) + r'"\s+"', block)
    if not match:
        return None
    return match.start(), match.start() + len(cec_sch.carve(block, match.start()))


def _set_property(block, name, value, x, y, hidden=True):
    span = _property_span(block, name)
    if span:
        old = block[span[0]:span[1]]
        prefix = re.match(
            r'(\(property\s+"' + re.escape(name) + r'"\s+")((?:[^"\\]|\\.)*)"', old)
        if not prefix:
            raise SystemExit(f"REFUSE: cannot parse property {name!r}")
        new = old[:prefix.start(2)] + value + old[prefix.end(2):]
        return block[:span[0]] + new + block[span[1]:]
    hide = " (hide yes)" if hidden else ""
    prop = (
        f'\t\t(property "{name}" "{value}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0)'
        f' (effects (font (size 1.27 1.27)){hide}))\n')
    pin = block.find("\t\t(pin ")
    if pin < 0:
        raise SystemExit(f"REFUSE: cannot add {name!r}; symbol has no pin anchor")
    return block[:pin] + prop + block[pin:]


def _drop_property(block, name):
    while True:
        span = _property_span(block, name)
        if not span:
            return block
        start = span[0]
        while start > 0 and block[start - 1] in "\t ":
            start -= 1
        end = span[1]
        if end < len(block) and block[end] == "\n":
            end += 1
        block = block[:start] + block[end:]


def _shift_instance_y(block, delta):
    def shift(match):
        return f"(at {match.group(1)} {cec_sch.f(float(match.group(2)) + delta)} {match.group(3)})"
    return re.sub(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)', shift, block)


def _instance_origin(block):
    match = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)', block)
    if not match:
        raise SystemExit("REFUSE: symbol instance has no placement")
    return float(match.group(1)), float(match.group(2)), int(match.group(3))


def _replace_instance(text, ref, part_name, preserve_pin=True):
    _start, old = find_symbol_block(text, ref)
    x, y, angle = _instance_origin(old)
    if angle != 0:
        raise SystemExit(f"REFUSE: {ref} has unsupported schematic rotation {angle}")
    old_lib = re.search(r'\(lib_id\s+"([^"]+)"\)', old).group(1)
    new_lib = f"{contract.LIB}:{part_name}"
    old_pins = get_pin_table(text, old_lib)
    new_pins = cec_sch.pin_table(_source_block(part_name))
    if preserve_pin:
        old_pin = old_pins.get("1")
        new_pin = new_pins.get("1")
        if not old_pin or not new_pin:
            raise SystemExit(f"REFUSE: {ref} does not have a one-node pin contract")
        # Schematic Y is inverted from symbol-local Y.  Move the whole symbol
        # so the existing wire endpoint is exactly preserved.
        dx = old_pin[0] - new_pin[0]
        dy = new_pin[1] - old_pin[1]
        if abs(dx) > 1e-9:
            raise SystemExit(f"REFUSE: {ref} replacement requires unsupported X shift {dx}")
        if abs(dy) > 1e-9:
            old = _shift_instance_y(old, dy)
            y += dy
    old = old.replace(f'(lib_id "{old_lib}")', f'(lib_id "{new_lib}")', 1)
    source_props = _source_properties(part_name)
    for stale in ("Note", "Integration Note", "Source Drawing"):
        old = _drop_property(old, stale)
    for name, value in source_props.items():
        if name == "Reference" or name.startswith("ki_"):
            continue
        old = _set_property(old, name, value, x, y, hidden=name not in {"Value"})
    # Non-BOM daughterboard lands deliberately have no manufacturer ordering
    # identity.  A lib-id swap must not leave the retired TE MPN/LCSC fields
    # attached to the project-authored copper land.
    for name in ("Manufacturer", "MPN", "LCSC"):
        if name not in source_props:
            old = _drop_property(old, name)
    old = _set_property(
        old, "Integration Note",
        "Prototype XFCN interface; TE blade architecture remains the ratified fallback until owner ratification and qualification",
        x, y)
    source_pdf = (
        "lib/datasheets/XFCN_T34069_C481452.pdf" if part_name.startswith("XFCN_T34069")
        else "lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf")
    old = _set_property(old, "Source Drawing", source_pdf, x, y)
    in_bom = contract.PARTS[part_name]["in_bom"]
    old = re.sub(r'\(in_bom\s+(yes|no)\)', f'(in_bom {"yes" if in_bom else "no"})', old, count=1)
    return text.replace(find_symbol_block(text, ref)[1], old, 1)


def _replace_aux_metadata(text, ref, part_name):
    """Retarget a topology-identical companion connector without moving pins."""
    _start, old = find_symbol_block(text, ref)
    x, y, _angle = _instance_origin(old)
    part = contract.PARTS[part_name]
    expected_lib = part["lib_id"]
    actual_lib = re.search(r'\(lib_id\s+"([^"]+)"\)', old).group(1)
    if actual_lib != expected_lib:
        raise SystemExit(
            f"REFUSE: {ref} logical symbol {actual_lib!r}, expected {expected_lib!r}")
    for name, value in (
            ("Value", part["value"]), ("Footprint", part["footprint"]),
            ("Datasheet", part["datasheet_url"]),
            ("Manufacturer", part["manufacturer"]), ("MPN", part["mpn"]),
            ("Description", part["description"]), ("Note", part["note"])):
        old = _set_property(old, name, value, x, y, hidden=name != "Value")
    old = _drop_property(old, "LCSC")
    old = re.sub(r'\(in_bom\s+(yes|no)\)', '(in_bom yes)', old, count=1)
    return text.replace(find_symbol_block(text, ref)[1], old, 1)


def _remove_one_pin(text, ref):
    _start, block = find_symbol_block(text, ref)
    lib_id = re.search(r'\(lib_id\s+"([^"]+)"\)', block).group(1)
    x, y, angle = _instance_origin(block)
    if angle != 0:
        raise SystemExit(f"REFUSE: {ref} has unsupported schematic rotation {angle}")
    pins = get_pin_table(text, lib_id)
    text, _kind, _info = remove_pin_stub(text, pins, ref, "1", x, y)
    text, _block = remove_symbol(text, ref)
    return text


def _parse_project_path(block):
    project = re.search(r'\(project\s+"([^"]+)"', block)
    path = re.search(r'\(path\s+"/([^"]+)"', block)
    if not project or not path:
        raise SystemExit("REFUSE: cannot preserve symbol instance hierarchy path")
    return project.group(1), path.group(1)


def _emit_clean_symbol(ref, part_name, x, y, project, root_path):
    props = _source_properties(part_name)
    block = cec_sch.emit_symbol(
        ref, contract.LIB, part_name, props["Value"], x, y,
        ["1"], project, root_path, props["Footprint"],
        {**props,
         "Integration Note": "Prototype XFCN interface; production release remains qualification-gated",
         "Source Drawing": (
             "lib/datasheets/XFCN_T34069_C481452.pdf" if part_name.startswith("XFCN_T34069")
             else "lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf")})
    block = re.sub(
        r'\(property "Reference" "' + re.escape(ref) + r'" \(at [^)]+\)',
        f'(property "Reference" "{ref}" (at {cec_sch.f(x)} {cec_sch.f(y - 5.08)} 0)', block, count=1)
    block = re.sub(
        r'\(property "Value" "([^"]*)" \(at [^)]+\)',
        lambda m: f'(property "Value" "{m.group(1)}" (at {cec_sch.f(x)} {cec_sch.f(y + 5.08)} 0)',
        block, count=1)
    return block


def _next_power_ref(text):
    numbers = [int(value) for value in re.findall(r'\(property "Reference" "#PWR(\d+)"', text)]
    value = max(numbers, default=0) + 1
    while f'#PWR{value:04d}' in text:
        value += 1
    return f"#PWR{value:04d}"


def _insert_items(text, items):
    marker = "\t(sheet_instances"
    if marker in text:
        at = text.rindex(marker)
    else:
        at = text.rfind("\n)") + 1
    return text[:at] + "\n".join(items) + "\n" + text[at:]


def _rewrite_eps(text):
    if all(f'(property "Reference" "{ref}"' in text
           for ref in contract.PROJECTS["eps-main"]["refs"]):
        return text
    donors = {}
    for connector in ("J_OUT1", "J_OUT2"):
        _start, block = find_symbol_block(text, connector)
        donors[connector] = _parse_project_path(block)
        lib_id = re.search(r'\(lib_id\s+"([^"]+)"\)', block).group(1)
        x, y, angle = _instance_origin(block)
        if angle != 0:
            raise SystemExit(f"REFUSE: {connector} has unsupported rotation {angle}")
        pins = get_pin_table(text, lib_id)
        for pin in map(str, range(1, 9)):
            text, _kind, _info = remove_pin_stub(text, pins, connector, pin, x, y)
        text, _removed = remove_symbol(text, connector)

    part = contract.T340
    pins = cec_sch.pin_table(_source_block(part))
    items = []
    # GND, +12, +12, GND mirrors the daughterboard pattern and makes the two
    # members of each parallel polarity geometrically equivalent.
    rows = (
        (87.63, donors["J_OUT1"], [
            ("TB13", "GND"), ("TB11", "SENSEC1_LO"),
            ("TB12", "SENSEC1_LO"), ("TB14", "GND")]),
        (135.89, donors["J_OUT2"], [
            ("TB23", "GND"), ("TB21", "SENSEC2_LO"),
            ("TB22", "SENSEC2_LO"), ("TB24", "GND")]),
    )
    for y, (project, root_path), terminals in rows:
        for x, (ref, net) in zip((181.61, 194.31, 207.01, 219.71), terminals):
            items.append(_emit_clean_symbol(ref, part, x, y, project, root_path))
            if net == "GND":
                pwr_ref = _next_power_ref(text + "\n".join(items))
                items.append(wire_and_power(pins, ref, "1", x, y, "GND", project, root_path, pwr_ref))
            else:
                items.append(wire_and_label(pins, ref, "1", x, y, net))
    return _insert_items(text, items)


def _ensure_eps_hier_labels(text):
    # The parent sheet exposes SENSEC1_LO/SENSEC2_LO pins.  Keep one output
    # hierarchical label per rail in addition to the repeated local labels
    # used to make the parallel terminals visually explicit.
    for net, x, y in (
            ("SENSEC1_LO", 194.31, 95.25),
            ("SENSEC2_LO", 194.31, 143.51)):
        if f'(hierarchical_label "{net}"' in text:
            continue
        text, kind, info = remove_terminal_at(text, x, y)
        if kind != "label" or info != net:
            raise SystemExit(
                f"REFUSE: expected local {net} label at ({x},{y}), got {kind} {info!r}")
        text = _insert_items(text, [emit_hier_label(net, x, y, 90, "output")])
    return text


def _ensure_table(path, kind):
    text = path.read_text(encoding="utf-8")
    if f'(name "{contract.LIB}")' in text:
        return False
    daughterboard = "output-daughterboards" in path.parts
    depth = "../../../" if daughterboard else "../../"
    target = (
        f'${{KIPRJMOD}}/{depth}lib/vendor/Connector_Screw.kicad_sym' if kind == "sym"
        else f'${{KIPRJMOD}}/{depth}lib/vendor/Connector_Screw.pretty')
    noun = "symbols" if kind == "sym" else "footprints"
    line = (
        f'  (lib (name "{contract.LIB}")(type "KiCad")(uri "{target}")'
        f'(options "")(descr "CEC reviewed XFCN high-current screw-terminal {noun}; prototype qualification gated"))\n')
    close = text.rfind(")")
    _atomic_write(path, text[:close] + line + text[close:])
    return True


def apply_project(name):
    plan = contract.PROJECTS[name]
    schematic = ROOT / plan["leaf_schematic"]
    text = schematic.read_text(encoding="utf-8")
    before = text
    for expectation in plan["refs"].values():
        text = _ensure_embedded(text, expectation["part"])
    if name == "eps-main":
        text = _rewrite_eps(text)
        text = _ensure_eps_hier_labels(text)
    else:
        for ref in plan["remove_refs"]:
            if f'(property "Reference" "{ref}"' in text:
                text = _remove_one_pin(text, ref)
        for ref, expectation in plan["refs"].items():
            text = _replace_instance(text, ref, expectation["part"])
    for ref, expectation in plan.get("aux_refs", {}).items():
        text = _replace_aux_metadata(text, ref, expectation["part"])
    # The first integration draft misread T34069 as an internal board clamp.
    # Once every instance uses the corrected through-bolt symbol, remove the
    # obsolete embedded definition so it cannot remain as a selectable ghost.
    text = _drop_embedded(text, "XFCN_T34069_DB_ClampLand")
    if text != before:
        _atomic_write(schematic, text)
    project_dir = (ROOT / plan["root_schematic"]).parent
    table_changes = 0
    table_changes += _ensure_table(project_dir / "sym-lib-table", "sym")
    table_changes += _ensure_table(project_dir / "fp-lib-table", "fp")
    return {"schematic_changed": text != before, "library_tables_changed": table_changes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", choices=sorted(contract.PROJECTS))
    args = parser.parse_args(argv)
    for name in args.project or contract.PROJECTS:
        report = apply_project(name)
        print(f"{name}: {report}")


if __name__ == "__main__":
    main()
