#!/usr/bin/env python3
"""Repair ESP32-C6-MINI-1 schematic pin electrical types.

The imported vendor symbol marked every pin ``unspecified``. Espressif marks
the IO pins as I/O, the supply pins as power, EN as input, and NC pins as NC.
KiCad therefore could not prove that CAN_TX was driven. This text-preserving
mutator updates both the source library and cached schematic symbol copies.
"""
import argparse
import glob
import os
import re
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "ESP32-C6-MINI-1-N4"


def _sexpr_end(text, start):
    depth = 0
    quoted = False
    escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
    raise ValueError("unterminated S-expression")


def _wanted_type(pin_name):
    if pin_name in ("GND", "3V3"):
        return "power_in"
    if pin_name == "NC":
        return "no_connect"
    if pin_name == "EN":
        return "input"
    if pin_name in ("RXD0", "TXD0") or re.fullmatch(r"IO\d+", pin_name):
        return "bidirectional"
    raise ValueError("unclassified ESP32-C6 pin name %r" % pin_name)


def update_text(text):
    """Return (updated text, number of corrected pin declarations)."""
    symbol_re = re.compile(
        r'\(symbol\s+"(?:cec-vendor:)?ESP32-C6-MINI-1-N4"')
    output = []
    cursor = 0
    changes = 0
    for symbol_match in symbol_re.finditer(text):
        start = symbol_match.start()
        end = _sexpr_end(text, start)
        block = text[start:end]
        block_output = []
        block_cursor = 0
        for pin_match in re.finditer(r"\(pin\s+(\w+)\s+(\w+)", block):
            pin_start = pin_match.start()
            pin_end = _sexpr_end(block, pin_start)
            pin_block = block[pin_start:pin_end]
            name_match = re.search(r'\(name\s+"([^"]+)"', pin_block)
            if not name_match:
                raise ValueError("ESP32-C6 pin has no name")
            wanted = _wanted_type(name_match.group(1))
            if pin_match.group(1) == wanted:
                continue
            updated_pin = (pin_block[:pin_match.start(1) - pin_start]
                           + wanted
                           + pin_block[pin_match.end(1) - pin_start:])
            block_output.append(block[block_cursor:pin_start])
            block_output.append(updated_pin)
            block_cursor = pin_end
            changes += 1
        block_output.append(block[block_cursor:])
        updated_block = "".join(block_output)
        output.append(text[cursor:start])
        output.append(updated_block)
        cursor = end
    output.append(text[cursor:])
    return "".join(output), changes


def _default_paths():
    paths = [os.path.join(ROOT, "lib", "vendor", "cec-vendor.kicad_sym")]
    for path in glob.glob(os.path.join(ROOT, "beta", "**", "*.kicad_sch"),
                          recursive=True):
        with open(path, encoding="utf-8", errors="replace") as handle:
            if TARGET in handle.read():
                paths.append(path)
    return paths


def _write_atomic(path, text):
    fd, temporary = tempfile.mkstemp(prefix=".cec-symbol-", suffix=".tmp",
                                     dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    changed_files = []
    for path in args.paths or _default_paths():
        with open(path, encoding="utf-8", newline="") as handle:
            original = handle.read()
        updated, changes = update_text(original)
        if not changes:
            continue
        changed_files.append((path, changes))
        if args.write:
            _write_atomic(path, updated)
    if changed_files:
        verb = "updated" if args.write else "needs update"
        for path, changes in changed_files:
            print("%s: %s (%d pins)" %
                  (verb, os.path.relpath(path, ROOT), changes))
        return 0 if args.write else 1
    print("ESP32-C6 symbol electrical types already correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
