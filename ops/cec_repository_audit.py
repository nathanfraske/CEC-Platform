#!/usr/bin/env python3
"""Inventory a dirty checkout without deleting, staging or printing secrets.

The inventory is a review aid, not permission to discard a generated-looking
file. Archives, source controls and fixture data can all have the same suffix.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import re


def ignored_python_dependencies(root):
    """Find source imports hidden in build/, without executing any helper."""
    root = Path(root)
    pending = set()
    references = {}
    for source in (root / "tests").glob("test_*.py"):
        try:
            tree = ast.parse(source.read_text())
        except (SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".")[0])
            for name in names:
                if (root / "build" / (name + ".py")).is_file():
                    pending.add(name)
                    references.setdefault(name, []).append(
                        str(source.relative_to(root))
                    )
    found = {}
    while pending:
        name = pending.pop()
        if name in found:
            continue
        path = root / "build" / (name + ".py")
        if not path.is_file():
            continue
        body = path.read_text()
        tree = ast.parse(body)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        found[name] = dict(
            path=str(path.relative_to(root)),
            sha256=digest,
            bytes=path.stat().st_size,
            test_references=sorted(set(references.get(name, []))),
        )
        recovered = root / "experiments/legacy_2026" / (name + ".py")
        found[name]["recovered_source"] = (
            str(recovered.relative_to(root)) if recovered.is_file() else None
        )
        found[name]["unresolved"] = not recovered.is_file()
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".")[0])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Adjacent drivers can use hyphenated filenames rather than
                # importable root_* names. Keep that finite literal closure too.
                names.extend(re.findall(r"\b([A-Za-z0-9_-]+)\.py\b", node.value))
            pending.update(
                value
                for value in names
                if value not in found and (root / "build" / (value + ".py")).is_file()
            )
    return found


def git(root, *arguments):
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=9.7,
    ).stdout


def classify(name):
    path = Path(name)
    if path.parts[0] in ("tmp", "output", "out", "build"):
        return "runtime-review-required"
    if path.name.endswith((".partial", ".lck", ".pyc")) or path.name.startswith(
        ("cec-priority-power-admit-input-", "tmp")
    ):
        return "temporary-review-required"
    if path.suffix in (".py", ".js", ".mjs", ".ts", ".sh", ".ps1", ".c", ".h"):
        return "source"
    if path.suffix in (".md", ".rst", ".html", ".css"):
        return "documentation-or-ui"
    if path.suffix in (
        ".kicad_pcb",
        ".kicad_sch",
        ".kicad_pro",
        ".kicad_dru",
        ".kicad_mod",
        ".kicad_sym",
        ".step",
        ".stp",
        ".wrl",
    ):
        return "design-source-or-asset"
    if path.parts[0] == "tests":
        return "test-fixture"
    if path.suffix in (".json", ".yaml", ".yml", ".toml", ".csv"):
        return "configuration-or-evidence-review-required"
    return "other-review-required"


def inventory(root):
    root = Path(root).resolve(strict=True)
    tracked = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
    untracked = set(
        git(root, "ls-files", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    modified = set(
        git(root, "diff", "HEAD", "--name-only", "-z").decode().split("\0")
    ) - {""}
    rows = []
    totals = Counter()
    domains = defaultdict(Counter)
    for name in sorted(tracked | untracked):
        path = root / name
        state = (
            "untracked"
            if name in untracked
            else "modified" if name in modified else "tracked"
        )
        category = classify(name)
        symlink = path.is_symlink()
        size = path.lstat().st_size if path.exists() or symlink else 0
        row = dict(
            path=name, state=state, category=category, bytes=size, symlink=symlink
        )
        rows.append(row)
        totals[state] += 1
        domains[Path(name).parts[0]][state] += 1
        domains[Path(name).parts[0]]["bytes"] += size
    return dict(
        schema=1,
        root=str(root),
        head=git(root, "rev-parse", "HEAD").decode().strip(),
        branch=git(root, "branch", "--show-current").decode().strip(),
        totals=dict(totals),
        domains={key: dict(value) for key, value in sorted(domains.items())},
        untracked_categories=dict(
            Counter(row["category"] for row in rows if row["state"] == "untracked")
        ),
        ignored_python_dependencies=ignored_python_dependencies(root),
        files=rows,
        deletion_or_staging_authority=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output", help="Optional generated JSON evidence, outside the source tree"
    )
    args = parser.parse_args()
    result = inventory(args.root)
    if args.output:
        target = Path(args.output).resolve()
        if target.is_relative_to(Path(result["root"])):
            parser.error("inventory output must be outside the audited checkout")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        result["inventory_path"] = str(target)
        result["inventory_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    print(json.dumps({key: value for key, value in result.items() if key != "files"}))


if __name__ == "__main__":
    main()
