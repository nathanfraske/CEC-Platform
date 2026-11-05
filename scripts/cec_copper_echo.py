"""Reconcile exact new copper echoes against surviving source identities.

This is not overlap healing or whole-net replacement. All fabrication fields
must match exactly; only identity, lock state and endpoint direction differ.
Unknown fields participate in comparison. An absent or modified original
cannot justify deleting its replacement. Group-owned proposals are refused.
"""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import tempfile


_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+')
_KINDS = frozenset({"segment", "arc", "via"})


def _parse(tokens):
    stack = []
    root = None
    for token in tokens:
        if token == "(":
            node = []
            if stack:
                stack[-1].append(node)
            elif root is not None:
                raise ValueError("multiple expressions")
            else:
                root = node
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("unbalanced expression")
            stack.pop()
        elif stack:
            stack[-1].append(token)
        else:
            raise ValueError("atom outside expression")
    if stack or root is None:
        raise ValueError("incomplete expression")
    return root


def _atom(token):
    if token.startswith('"'):
        # Preserve escaped string identity, distinct from numeric atoms.
        return ("string", token)
    try:
        number = Decimal(token)
        if number.is_finite():
            return ("number", number.normalize() if number else Decimal(0))
    except InvalidOperation:
        pass
    return ("atom", token)


def _freeze(node):
    return tuple(_freeze(x) if isinstance(x, list) else _atom(x) for x in node)


def _read(path):
    text = Path(path).read_text(encoding="utf-8")
    depth, start = 0, None
    records, nets, grouped = [], {}, set()
    root_seen = False
    for token in _TOKEN.finditer(text):
        value = token.group()
        if value == "(":
            if depth == 0 and root_seen:
                raise ValueError("multiple board expressions")
            depth += 1
            if depth == 2:
                start = token.start()
        elif value == ")":
            if depth == 2:
                block = text[start:token.end()]
                head = [m.group() for _, m in zip(range(2), _TOKEN.finditer(block))]
                kind = head[1] if len(head) == 2 else ""
                if kind in _KINDS or kind in {"net", "group"}:
                    node = _parse(_TOKEN.findall(block))
                    fields = {x[0]: x for x in node[1:] if isinstance(x, list) and x}
                    if kind == "net" and len(node) == 3:
                        nets[node[1]] = node[2]
                    elif kind == "group":
                        grouped.update(fields.get("members", [])[1:])
                    elif kind in _KINDS:
                        uid = fields.get("uuid", [])
                        net = fields.get("net", [])
                        if len(uid) != 2 or len(net) != 2:
                            raise ValueError("copper lacks identity or net")
                        records.append({"uuid": uid[1], "net": net[1],
                                        "kind": kind, "node": node,
                                        "start": start, "end": token.end()})
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced board")
        elif depth == 1 and not root_seen:
            if value != "kicad_pcb":
                raise ValueError("not a board")
            root_seen = True
        elif depth == 0:
            raise ValueError("atom outside board")
    if depth or not root_seen:
        raise ValueError("incomplete board")
    for row in records:
        row["net"] = nets.get(row["net"], row["net"])
    ids = [row["uuid"] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source/candidate copper UUIDs")
    return text, records, grouped


def _key(row):
    children = []
    ends = []
    for child in row["node"][1:]:
        if child == "locked":
            continue
        if isinstance(child, list):
            if child[0] in {"uuid", "locked", "net"}:
                continue
            if row["kind"] in {"segment", "arc"} and child[0] in {"start", "end"}:
                ends.append(_freeze(child[1:]))
                continue
            children.append(_freeze(child))
        else:
            children.append((_atom(child),))
    return (row["kind"], row["net"], tuple(sorted(ends, key=repr)),
            tuple(sorted(children, key=repr)))


def remove_exact_echoes(source_path, candidate_path, *, generated_uuids=None):
    """Remove only ungrouped new exact copies of unchanged surviving items.

    Files are edited as a serialized delta: source bytes, original UUIDs,
    groups, placements, zones, sidecars and unrelated proposals stay intact.
    The caller must still run normal independent DRC/topology admission.
    """
    _, source, _ = _read(source_path)
    text, current, grouped = _read(candidate_path)
    before = {row["uuid"]: _key(row) for row in source}
    allowed = (None if generated_uuids is None else
               {'"' + str(uid).strip('"') + '"' for uid in generated_uuids})
    surviving = {}
    for row in current:
        key = _key(row)
        if row["uuid"] in before and key == before[row["uuid"]]:
            surviving.setdefault(key, row["uuid"])
    removed, grouped_echoes, doomed = [], [], []
    for row in current:
        uid = row["uuid"]
        if uid in before or (allowed is not None and uid not in allowed):
            continue
        owner = surviving.get(_key(row))
        if owner is None:
            continue
        detail = {"uuid": uid.strip('"'), "original_uuid": owner.strip('"'),
                  "kind": row["kind"], "net": row["net"].strip('"')}
        if uid in grouped:
            grouped_echoes.append(detail)
        else:
            removed.append(detail)
            doomed.append(row)
    for row in sorted(doomed, key=lambda x: x["start"], reverse=True):
        text = text[:row["start"]] + text[row["end"]:]
    if doomed:
        Path(candidate_path).write_text(text, encoding="utf-8", newline="\n")
    return {"schema": 1, "removed": removed, "removed_count": len(removed),
            "group_owned_echoes_retained": grouped_echoes}


def remove_exact_echoes_board(source_path, board):
    """Reconcile immediately after native import, before downstream producers.

    Serialize the one live BOARD rather than loading a second SWIG owner.
    SaveBoard's skip-settings flag keeps the source project untouched.
    """
    import pcbnew
    from cec_native_items import discard_items
    with tempfile.TemporaryDirectory(prefix="cec-exact-copper-echo-") as temp:
        candidate = Path(temp) / "board.kicad_pcb"
        pcbnew.SaveBoard(str(candidate), board, True)
        report = remove_exact_echoes(source_path, candidate)
    selected = {row["uuid"] for row in report["removed"]}
    doomed = [item for item in board.GetTracks()
              if str(item.m_Uuid.AsString()) in selected]
    if len(doomed) != len(selected):
        raise RuntimeError("echo identities changed during native reconciliation")
    discard_items(board, doomed)
    return report


def reconcile_locked_additions(candidate_path, *, locked_uuids,
                               complete_net_candidate_uuids=(), source_path=None):
    """Remove exact locked copies or explicitly new whole-owned-net additions.

    The caller supplies a native locked-connectivity proof for complete-net
    candidates. Without a separate source artifact there is no provenance for
    deleting nonexact copper, even on a complete net. Original source UUIDs and
    group-owned items are retained. Exact echo identity includes net, layer,
    width, arc midpoint, full via padstack and unknown serialized fields.
    """
    text, rows, grouped = _read(candidate_path)
    quote = lambda uid: '"' + str(uid).strip('"') + '"'
    locked = {quote(uid) for uid in locked_uuids}
    candidates = {quote(uid) for uid in complete_net_candidate_uuids}
    present = {row['uuid'] for row in rows}
    if not locked <= present or not candidates <= present or locked & candidates:
        raise ValueError('locked reconciliation identities disagree with artifact')
    originals = None
    if source_path is not None:
        _, source_rows, _ = _read(source_path)
        originals = {row['uuid'] for row in source_rows}
    locked_geometry = {_key(row): row['uuid'] for row in rows if row['uuid'] in locked}
    doomed, removed, retained_groups = [], [], []
    for row in rows:
        uid = row['uuid']
        if uid in locked:
            continue
        original = locked_geometry.get(_key(row))
        reason = ('exact_locked_echo' if original is not None else
                  'new_addition_to_native_complete_locked_net'
                  if originals is not None and uid not in originals and uid in candidates else None)
        if reason is None:
            continue
        detail = dict(uuid=uid.strip('"'), net=row['net'].strip('"'), kind=row['kind'],
                      reason=reason, original_uuid=original.strip('"') if original else None)
        if uid in grouped:
            retained_groups.append(detail)
            continue
        # Source copper may carry authored width/capacity intent. Even exact
        # source duplicates are the earlier source's responsibility to repair.
        if originals is not None and uid in originals:
            continue
        doomed.append(row); removed.append(detail)
    for row in sorted(doomed, key=lambda r: r['start'], reverse=True):
        text = text[:row['start']] + text[row['end']:]
    if doomed:
        Path(candidate_path).write_text(text, encoding='utf-8', newline='\n')
    return dict(schema=1, removed=removed, removed_count=len(removed),
                group_owned_retained=retained_groups,
                nonexact_source_authority=source_path is not None)
