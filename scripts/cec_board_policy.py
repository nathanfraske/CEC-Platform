#!/usr/bin/env python3
"""Declarative, board-local policy shared by placement, routing and review.

Historically the fresh-wave driver carried board policy in a Python mapping.
That made direct synthesis and archived/dashboard analysis depend on which
entry point happened to be used.  This module gives every pipeline consumer a
small, deterministic loader for ``pipeline-policy.json`` beside a board.

The loader is deliberately dependency-free.  A caller may identify a board by
name, board directory, PCB path, or an explicit ``board_hint`` when an archive
has renamed the PCB.  Returned mappings are deep copies, so size sweeps and
workers cannot mutate process-global policy.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any, Mapping


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_FILENAME = "pipeline-policy.json"
SCHEMA = 1

_BOARD_ROOTS = (
    ("beta",),
    ("modules",),
    ("hubs",),
    ("beta", "output-daughterboards"),
    ("modules", "output-daughterboards"),
)


class BoardPolicyError(ValueError):
    """A board policy exists but is malformed or identifies another board."""


def _named_board_dir(name: str) -> str | None:
    clean = str(name or "").strip()
    if not clean or clean in (".", "..") or os.path.basename(clean) != clean:
        return None
    for parts in _BOARD_ROOTS:
        candidate = os.path.join(ROOT, *parts, clean)
        if os.path.isdir(candidate):
            return candidate
    return None


def _policy_paths():
    """Yield board-local policies without maintaining a product registry."""
    seen = set()
    for parts in _BOARD_ROOTS:
        root = os.path.join(ROOT, *parts)
        if not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.scandir(root), key=lambda row: row.name)
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            path = os.path.join(entry.path, POLICY_FILENAME)
            resolved = os.path.realpath(path)
            if os.path.isfile(path) and resolved not in seen:
                seen.add(resolved)
                yield path


def _policy_identifiers(path: str) -> tuple[str, ...]:
    """Read only the declared board identity/aliases for path resolution."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    board = payload.get("board")
    aliases = payload.get("aliases") or []
    if not isinstance(board, str) or not isinstance(aliases, list):
        return ()
    return tuple(value for value in (board, *aliases)
                 if isinstance(value, str) and value.strip())


def _identity_policy(subject: str) -> str | None:
    """Resolve renamed build artifacts by declared identity, never heuristics."""
    identity = str(subject or "").replace("\\", "/").lower()
    matches = []
    for path in _policy_paths():
        for key in _policy_identifiers(path):
            token = key.lower()
            exact = identity == token
            component = ("/" + token + "/") in ("/" + identity.strip("/") + "/")
            filename = os.path.basename(identity).startswith(token + "-")
            if exact or component or filename:
                matches.append((len(token), path))
    return max(matches)[1] if matches else None


def _walk_policy(path: str) -> str | None:
    current = os.path.abspath(path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    repo = os.path.realpath(ROOT)
    while os.path.commonpath((repo, os.path.realpath(current))) == repo:
        candidate = os.path.join(current, POLICY_FILENAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def policy_path(subject: str | os.PathLike[str] | None,
                *, board_hint: str | None = None) -> str | None:
    """Resolve a policy without guessing from a renamed archive filename."""
    if board_hint:
        # A hint has the same documented input forms as the subject. Resolve
        # directories/PCB paths through their real owner, not only a registry
        # token extracted from the string.
        hinted = policy_path(board_hint)
        if hinted:
            return hinted
    if subject is None:
        return None
    raw = os.fspath(subject)
    if os.path.exists(raw) or "/" in raw or "\\" in raw:
        walked = _walk_policy(raw)
        if walked:
            return walked
    named = _named_board_dir(raw)
    if named:
        candidate = os.path.join(named, POLICY_FILENAME)
        return candidate if os.path.isfile(candidate) else None
    return _identity_policy(raw)


def _canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def load(subject: str | os.PathLike[str] | None, *,
         board_hint: str | None = None, required: bool = False) -> dict:
    """Load and validate a policy, returning an isolated canonical mapping."""
    path = policy_path(subject, board_hint=board_hint)
    if path is None:
        if required:
            raise FileNotFoundError(
                "no %s for %r (board_hint=%r)" % (
                    POLICY_FILENAME, subject, board_hint))
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardPolicyError("cannot read %s: %s" % (path, exc)) from exc
    if not isinstance(payload, dict):
        raise BoardPolicyError("%s must contain a JSON object" % path)
    if payload.get("schema") != SCHEMA:
        raise BoardPolicyError(
            "%s schema must be %d, got %r" % (
                path, SCHEMA, payload.get("schema")))
    board = payload.get("board")
    if not isinstance(board, str) or not board.strip():
        raise BoardPolicyError("%s must declare a non-empty board" % path)
    aliases = payload.get("aliases") or []
    if (not isinstance(aliases, list)
            or any(not isinstance(value, str) or not value.strip()
                   for value in aliases)):
        raise BoardPolicyError("%s aliases must be a string array" % path)
    expected = board_hint or os.path.basename(os.path.dirname(path))
    if board_hint and ("/" in os.fspath(board_hint)
                       or "\\" in os.fspath(board_hint)
                       or os.fspath(board_hint).lower().endswith(".kicad_pcb")):
        hinted = policy_path(board_hint)
        if hinted is None or os.path.realpath(hinted) != os.path.realpath(path):
            raise BoardPolicyError("unresolved policy path hint %r" % board_hint)
        # Validate the resolved policy's physical owner against its declared
        # identity/aliases. Comparing the original full PCB path to a board
        # name rejected correct inputs; accepting the payload's name blindly
        # would instead conceal a misfiled policy.
        expected = os.path.basename(os.path.dirname(hinted))
    if expected and expected not in (board, *aliases):
        raise BoardPolicyError(
            "%s declares board %r, expected %r" % (path, board, expected))
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise BoardPolicyError("%s params must be a JSON object" % path)
    if ('respect_antenna_keepout' in params
            and type(params['respect_antenna_keepout']) is not bool):
        raise BoardPolicyError('%s respect_antenna_keepout must be boolean' % path)
    normalized = copy.deepcopy(payload)
    normalized["params"] = params
    normalized["source"] = os.path.abspath(path)
    normalized["fingerprint"] = hashlib.sha256(
        _canonical_payload(payload)).hexdigest()
    return normalized


def params(subject: str | os.PathLike[str] | None, *,
           board_hint: str | None = None, required: bool = False) -> dict:
    """Return only policy parameters as a deep copy."""
    policy = load(subject, board_hint=board_hint, required=required)
    return copy.deepcopy(policy.get("params") or {})


def merge_params(base: Mapping[str, Any] | None,
                 subject: str | os.PathLike[str] | None, *,
                 board_hint: str | None = None,
                 required: bool = False) -> dict:
    """Overlay board-local policy without mutating ``base``."""
    merged = copy.deepcopy(dict(base or {}))
    merged.update(params(subject, board_hint=board_hint, required=required))
    return merged


def critical_net_selectors(subject: str | os.PathLike[str] | None, *,
                           board_hint: str | None = None) -> tuple[str, ...]:
    """The same declared critical-control selectors for every entry point."""
    values = params(subject, board_hint=board_hint).get(
        "critical_route_nets", ()) or ()
    if isinstance(values, str):
        values = (values,)
    return tuple(str(value) for value in values if str(value).strip())
