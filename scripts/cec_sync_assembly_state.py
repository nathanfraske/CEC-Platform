#!/usr/bin/env python3
"""Synchronize KiCad PCB footprint DNP/BOM attributes from the schematic.

This is deliberately a text-preserving mutator. Loading and saving a board
through pcbnew can normalize unrelated stackup and zone formatting. This tool
changes only each footprint's ``attr`` tokens, then verifies the result.
"""
import argparse
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_sch_gates  # noqa: E402
import cec_toolchain  # noqa: E402


def _sexpr_end(text, start):
    """Return the exclusive end of one S-expression, respecting strings."""
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
    raise ValueError("unterminated footprint S-expression")


def _updated_attr(block, *, dnp, excluded):
    # Do not consume the line ending. The PCB may use CRLF, and replacing an
    # otherwise identical attr line with LF made every footprint look changed.
    match = re.search(
        r"(?m)^([ \t]*)\(attr[ \t]+([^\r\n)]*)\)[ \t]*(?=\r?$)",
        block,
    )
    if not match:
        raise ValueError("footprint has no attr clause")
    original_tokens = match.group(2).split()
    actual_dnp = "dnp" in original_tokens
    actual_excluded = "exclude_from_bom" in original_tokens
    if actual_dnp == dnp and actual_excluded == excluded:
        return block
    tokens = [token for token in original_tokens
              if token not in ("dnp", "exclude_from_bom")]
    if excluded:
        tokens.append("exclude_from_bom")
    if dnp:
        tokens.append("dnp")
    replacement = "%s(attr %s)" % (match.group(1), " ".join(tokens))
    return block[:match.start()] + replacement + block[match.end():]


def synchronize_text(text, inventory):
    """Return (updated_text, changed_refs) without reformatting the board."""
    pieces = []
    cursor = 0
    changed = []
    for match in re.finditer(r"(?m)^\s*\(footprint\s+", text):
        start = match.start() + len(match.group(0)) - len("(footprint ")
        start = text.rfind("(footprint", match.start(), match.end())
        end = _sexpr_end(text, start)
        block = text[start:end]
        ref_match = re.search(
            r'\(property\s+"Reference"\s+"((?:[^"\\]|\\.)*)"', block)
        if not ref_match:
            continue
        ref = ref_match.group(1)
        record = inventory.get(ref)
        if record is None:
            continue
        updated = _updated_attr(
            block,
            dnp=bool(record.get("dnp")),
            excluded=not bool(record.get("in_bom", True)),
        )
        if updated != block:
            pieces.append(text[cursor:start])
            pieces.append(updated)
            cursor = end
            changed.append(ref)
    pieces.append(text[cursor:])
    return "".join(pieces), changed


def _find_schematic(board_path, explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    directory = os.path.dirname(os.path.abspath(board_path))
    for candidate_dir in (directory, os.path.dirname(directory)):
        schematic = cec_toolchain.find_root_sch(candidate_dir)
        if schematic:
            return schematic
    return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("--schematic")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    board = os.path.abspath(args.board)
    schematic = _find_schematic(board, args.schematic)
    if not schematic:
        parser.error("could not resolve the root schematic")
    with open(board, encoding="utf-8", newline="") as handle:
        original = handle.read()
    updated, changed = synchronize_text(
        original, cec_sch_gates.inventory(schematic))
    if not changed:
        print("assembly state already in sync")
        return 0
    if not args.write:
        print("assembly state differs for: %s" % ", ".join(sorted(changed)))
        return 1

    directory = os.path.dirname(board)
    fd, temporary = tempfile.mkstemp(prefix=".cec-assembly-", suffix=".tmp",
                                     dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
        os.replace(temporary, board)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    verify, remaining = synchronize_text(
        updated, cec_sch_gates.inventory(schematic))
    if remaining or verify != updated:
        raise RuntimeError("post-write assembly-state verification failed")
    print("updated assembly state for: %s" % ", ".join(sorted(changed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
