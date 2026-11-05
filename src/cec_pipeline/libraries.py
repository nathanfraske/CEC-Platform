"""Relocate actual referenced footprint libraries, never synthesize parity.

Only URI locations change. Nicknames, enable/hidden flags and footprint file
bytes remain exact. Missing source files remain missing; no embedded board
land is turned into a fake library match. All declared libraries are bundled
because KiCad may enumerate unused libraries during rule startup.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from .legacy import bootstrap

bootstrap()


def export(board, table, destination, *, pool=None):
    import cec_native_library_context as context
    from .checkpoint import sha, require

    table = Path(table).resolve(strict=True)
    destination = Path(destination)
    require(not destination.exists(), "fresh_library_snapshot_directory_required")
    destination.mkdir(parents=True)
    observed, rendered = context._snapshot(board, table, dict(os.environ))
    shutil.copy2(table, destination / "origin-fp-lib-table")
    paths = {row["path"] for row in observed["rows"].values()}
    pool = Path(pool) if pool is not None else destination / "libraries"
    relative = {}
    copied = {}
    total_bytes = 0
    # KiCad loads declared libraries asynchronously during rule startup,
    # including unused nicknames. Missing those directories is not faithful
    # relocation. Preserve every declared .kicad_mod, sharing content-addressed
    # directories across boards instead of duplicating the vendor tree.
    for name in sorted(paths):
        source = Path(name)
        files = sorted(source.glob("*.kicad_mod")) if source.is_dir() else []
        require(
            len(files) <= context.MAX_DIRECTORY_ITEMS,
            "native_library_directory_inventory_bound",
        )
        inventory = {item.name: sha(item) for item in files}
        identity = hashlib.sha256(
            json.dumps(
                dict(exists=source.is_dir(), files=inventory),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        target = pool / (identity[:24] + ".pretty")
        relative[name] = os.path.relpath(target, destination)
        if not source.is_dir():
            continue
        target.mkdir(parents=True, exist_ok=True)
        for item in files:
            total_bytes += item.stat().st_size
            require(
                total_bytes <= 64 * 1024 * 1024,
                "bounded_declared_footprint_snapshot_required",
            )
            asset = target / item.name
            if not asset.exists():
                shutil.copy2(item, asset)
            require(
                sha(asset) == inventory[item.name],
                "native_library_snapshot_copy_changed",
            )
            copied[os.path.relpath(asset, destination)] = inventory[item.name]
        if not files:
            marker = target / ".keep"
            if not marker.exists():
                marker.write_text("No substitute footprint is supplied.\n")
            copied[os.path.relpath(marker, destination)] = sha(marker)

    def relocate(match):
        old = json.loads(match.group(1))
        require(old in relative, "native_library_URI_outside_observed_context")
        return "(uri " + json.dumps("${KIPRJMOD}/" + relative[old]) + ")"

    portable = re.sub(r'\(uri\s+("(?:[^"\\]|\\.)*")\)', relocate, rendered)
    result = destination / "fp-lib-table"
    result.write_text(portable)
    # Re-read through the SAME native checker parser. Every reference has
    # identical bytes or the same missing-item condition after relocation.
    received, _ = context._snapshot(board, result, dict(os.environ))
    expected = {
        (nick, item): observed["referenced_files"][
            str(Path(observed["rows"][nick]["path"]) / (item + ".kicad_mod"))
        ]["sha256"]
        for nick, item in observed["references"]
        if nick in observed["rows"] and observed["rows"][nick]["enabled"]
    }
    actual = {
        (nick, item): received["referenced_files"][
            str(Path(received["rows"][nick]["path"]) / (item + ".kicad_mod"))
        ]["sha256"]
        for nick, item in received["references"]
        if nick in received["rows"] and received["rows"][nick]["enabled"]
    }
    require(expected == actual, "relocated_library_references_changed")
    return dict(
        path=str(result),
        sha256=sha(result),
        original_table_sha256=observed["table_sha256"],
        referenced_assets=copied,
        reference_count=len(expected),
        missing_reference_count=sum(value is None for value in expected.values()),
        scope="actual_declared_library_files_not_new_part_or_footprint_qualification",
    )
