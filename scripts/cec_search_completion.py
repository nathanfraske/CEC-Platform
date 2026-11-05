"""Full-tree search-interruption evidence, independent of board and geometry.

A shortened diagnostic trace cannot prove the absence of a timeout. Scan the
raw refusal first, carry its bounded summary through projection, and never use
an interrupted negative query as a geometric proof or a negative cache entry.
This is diagnostic/ranking evidence, not a copper admission certificate.
"""
import re


_FLAGS = frozenset((
    "deadline_exhausted", "budget_exhausted", "search_budget_exhausted",
    "pair_search_budget_exhausted", "flow_leg_budget_exhausted",
    "timed_out", "round_limit_reached", "search_inconclusive",
))
_TEXT_FIELDS = frozenset(("refused", "status", "reason", "error"))
_COUNT_FIELDS = frozenset(("rejection_counts", "status_counts", "grid_status_counts"))
_INTERRUPTED = re.compile(
    r"\b(?:deadline|budget)(?:\s+(?:was|is))?\s+(?:exhausted|exceeded|expired)\b"
    r"|\b(?:timed?\s+out|timeout)\b")
_NEGATED = re.compile(
    r"\b(?:no|not|without)\s+(?:a\s+)?(?:deadline|budget|timeout|timed?\s+out)\b"
    r"|\b(?:deadline|budget|timeout)\s+(?:(?:was|is)\s+)?not\b")


def _interruption_text(value):
    if not isinstance(value, str):
        return False
    text = value.lower().replace("_", " ").replace("-", " ")
    return bool(_INTERRUPTED.search(text) and not _NEGATED.search(text))


def search_completion_evidence(value, *, witness_limit=16):
    """Scan all nodes; only the stored witnesses, never the scan, are bounded.

    Finite grid/search exhaustion is not time-budget exhaustion. An unfinished
    positive portal domain alone is not an interruption either: the consumer
    may have already found and qualified a route. Preserved summaries are read
    so that a second projection cannot lose a late, now-discarded interruption.
    """
    limit = max(0, min(64, int(witness_limit)))
    count, witnesses = 0, []
    pending = [(value, ())]
    seen = set()

    def record(path, cause, occurrences=1):
        nonlocal count
        count += occurrences
        if len(witnesses) < limit:
            witnesses.append(dict(path="/".join(str(p) for p in path[-8:]), cause=cause))

    while pending:
        node, path = pending.pop()
        if not isinstance(node, (dict, list, tuple)) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, (list, tuple)):
            pending.extend((child, path + (index,)) for index, child in reversed(list(enumerate(node))))
            continue
        saved = node.get("search_completion")
        has_summary = isinstance(saved, dict) and saved.get("schema") == 1
        if has_summary and saved.get("inconclusive"):
            record(path + ("search_completion",), "preserved_interruption",
                   max(1, int(saved.get("interruption_count", 1) or 1)))
        for key, item in node.items():
            if key == "search_completion" or (key == "search_inconclusive" and has_summary):
                continue
            if key in _FLAGS and item is True:
                record(path + (key,), key)
            elif key in _TEXT_FIELDS and _interruption_text(item):
                record(path + (key,), str(item)[:160])
            elif key in _COUNT_FIELDS and isinstance(item, dict):
                for reason, occurrences in item.items():
                    if (isinstance(occurrences, (int, float)) and occurrences > 0
                            and _interruption_text(reason)):
                        record(path + (key, reason), str(reason)[:160])
            if isinstance(item, (dict, list, tuple)):
                pending.append((item, path + (key,)))
    return dict(schema=1, inconclusive=bool(count), interruption_count=count,
                witnesses=witnesses, truncated=count > len(witnesses))


def annotate_refusal(row, *, witness_limit=16):
    """Never reject a qualified success because an earlier attempt timed out."""
    if not isinstance(row, dict) or not row.get("refused"):
        return row
    completion = search_completion_evidence(row, witness_limit=witness_limit)
    return dict(row, search_completion=completion,
                search_inconclusive=completion["inconclusive"])


def pair_probe_completion(report, *, pair_names=None, witness_limit=16):
    """Classify only refusals actually measured, never carried baseline pairs."""
    names = None if pair_names is None else set(pair_names)
    pairs = (report or {}).get("pairs", report or {})
    rows = [row for row in pairs.get("refused", ())
            if isinstance(row, dict) and (names is None or (
                names and (not row.get("name") or row["name"] in names)))]
    return search_completion_evidence(rows, witness_limit=witness_limit)


def probe_is_inconclusive(row):
    """One policy for candidate ranking, with checker failures kept distinct."""
    return bool(row.get("error") or row.get("pair_search_budget_exhausted")
                or row.get("search_inconclusive")
                or (row.get("search_completion") or {}).get("inconclusive"))
