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
        hinted = _named_board_dir(board_hint)
        if hinted:
            candidate = os.path.join(hinted, POLICY_FILENAME)
            return candidate if os.path.isfile(candidate) else None
    if subject is None:
        return None
    raw = os.fspath(subject)
    if os.path.exists(raw):
        return _walk_policy(raw)
    named = _named_board_dir(raw)
    if named:
        candidate = os.path.join(named, POLICY_FILENAME)
        return candidate if os.path.isfile(candidate) else None
    return None


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
    expected = board_hint or os.path.basename(os.path.dirname(path))
    if expected and board != expected:
        raise BoardPolicyError(
            "%s declares board %r, expected %r" % (path, board, expected))
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise BoardPolicyError("%s params must be a JSON object" % path)
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
