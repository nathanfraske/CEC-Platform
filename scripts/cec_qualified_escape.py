"""Compose exact local escapes with global routing, without waiving a route.

The output is only a proposed endpoint substitution. Its caller must negotiate
the complete problem again, with unchanged obstacles and layer policy, before
using it. No copper is emitted and no failed connection is discharged here.
"""
from collections import defaultdict, deque
import hashlib
import math
from pathlib import Path


def propose(board_path, conns, terminals, blocked, stackup, failed, qualified,
            *, max_connections=16, max_portals=8):
    import pcbnew
    import cec_decoupler_cell

    report = dict(schema=1, proposed=[], skipped=[], reroute_required=True)
    output = list(conns)
    if not failed or not qualified or max_connections <= 0 or max_portals <= 0:
        return tuple(output), report
    try:
        board = pcbnew.LoadBoard(str(board_path))
        board.BuildConnectivity()
        native = board.GetConnectivity()
        pads = {p.m_Uuid.AsString(): p for fp in board.GetFootprints() for p in fp.Pads()}
        access = cec_decoupler_cell.audit_supply_access_board(board)
        board.BuildConnectivity()
        layers = tuple(stackup['layer_names'])
        origin = tuple(stackup['grid_origin_mm'])
        pitch = float(stackup['grid_mm'])
        if not math.isfinite(pitch) or pitch <= 0:
            raise ValueError('invalid grid pitch')
        graph = defaultdict(list)
        locations = {}

        def endpoint(index, side):
            conn = conns[index]
            records = tuple(terminals[index].get(side) or ())
            if not records:
                return None
            cell = tuple(conn[1 if side == 'src' else 2])
            if not 0 <= cell[0] < len(layers):
                return None
            identities = []
            for r in records:
                pad = pads.get(r.get('uuid'))
                if (pad is None or pad.GetNetname() != conn[0]
                        or pad.GetParentFootprint().GetReference() != r.get('ref')
                        or str(pad.GetNumber()) != str(r.get('pad'))):
                    return None
                xy = tuple(round(v/1e6, 6) for v in (pad.GetPosition().x, pad.GetPosition().y))
                grid = (int((xy[1]-origin[1])/pitch), int((xy[0]-origin[0])/pitch))
                if (xy != tuple(r.get('position_mm') or ()) or grid != cell[1:]
                        or not pad.IsOnLayer(board.GetLayerID(layers[cell[0]]))):
                    return None
                identities.append(r['uuid'])
            key = (str(conn[0]), tuple(sorted(set(identities))), cell[0])
            locations[key] = cell
            return key

        proved_edges = 0
        for q in qualified:
            i = int(q.get('index', -1))
            if not 0 <= i < len(conns) or q.get('net') != conns[i][0]:
                continue
            a, b = endpoint(i, 'src'), endpoint(i, 'dst')
            if a is None or b is None:
                continue
            authority = q.get('authority')
            good = False
            if authority == 'native_connected_pad_endpoints':
                ids = set(a[1]) | set(b[1])
                seed = min(ids)
                connected = {seed} | {p.m_Uuid.AsString() for p in native.GetConnectedItems(pads[seed])
                                      if p.GetClass() == 'PAD' and p.GetNetname() == q['net']}
                good = ids <= connected
            elif authority == 'exact_local_bypass_cell' and len(a[1]) == len(b[1]) == 1:
                for c in access.get('cells') or ():
                    supply = c.get('supply') or {}
                    if (c.get('status') != 'accessible' or c.get('rail') != q['net']
                            or supply.get('status') != 'linked'
                            or supply.get('layer') != layers[a[2]]
                            or a[2] != b[2]):
                        continue
                    left, right = pads[a[1][0]], pads[b[1][0]]
                    for owner, cap in ((left, right), (right, left)):
                        # The legacy compact proof names a capacitor, not its
                        # land. Refuse ambiguous same-rail multi-pad devices.
                        cap_pads = [p for p in cap.GetParentFootprint().Pads() if p.GetNetname() == q['net']]
                        if (owner.GetParentFootprint().GetReference() == c.get('owner')
                                and str(owner.GetNumber()) == str(c.get('pin'))
                                and cap.GetParentFootprint().GetReference() == c.get('cap')
                                and len(cap_pads) == 1):
                            good = True
                            break
                    if good:
                        break
            if good:
                proved_edges += 1
                graph[a].append((b, i, authority))
                graph[b].append((a, i, authority))
        report['validated_escape_edges'] = proved_edges

        def alternatives(node):
            pending = deque([(node, [])]); seen = {node}; result = []
            while pending and len(result) < max_portals:
                current, proof = pending.popleft()
                result.append((current, proof))
                for nxt, edge, authority in sorted(graph[current]):
                    if nxt not in seen:
                        seen.add(nxt)
                        pending.append((nxt, proof + [dict(index=edge, authority=authority)]))
            return result

        for row in list(failed)[:max_connections]:
            i = int(row.get('index', -1))
            if (not 0 <= i < len(conns) or row.get('net') != conns[i][0]
                    or tuple(row.get('src', ())) != tuple(conns[i][1])
                    or tuple(row.get('dst', ())) != tuple(conns[i][2])):
                continue
            a, b = endpoint(i, 'src'), endpoint(i, 'dst')
            if a is None or b is None:
                report['skipped'].append(dict(index=i, reason='endpoint_identity_unproved'))
                continue
            choices = []
            allowed = stackup['allowed_layers_by_conn'][i]
            for left, lp in alternatives(a):
                for right, rp in alternatives(b):
                    src, dst = locations[left], locations[right]
                    if (not lp and not rp) or src == dst:
                        continue
                    # These are freshly verified physical pads, not arbitrary
                    # escape coordinates. Keep the same terminal-cell rule as
                    # route_negotiated: exact terminals may share a coarse
                    # cell with neighboring copper. Do not clear their
                    # neighbors, the opposite-layer column, or ANY input mask.
                    if not allowed[src[0]] or not allowed[dst[0]]:
                        continue
                    choices.append((sum(abs(x-y) for x,y in zip(src,dst)), len(lp)+len(rp),
                                    src, dst, left[1], right[1], lp, rp))
            if not choices:
                report['skipped'].append(dict(index=i, reason='no_eligible_proved_portal',
                    src_alternatives=len(alternatives(a)), dst_alternatives=len(alternatives(b))))
                continue
            _, _, src, dst, src_ids, dst_ids, lp, rp = min(choices, key=lambda x:x[:6])
            output[i] = (conns[i][0], src, dst)
            report['proposed'].append(dict(index=i, net=conns[i][0],
                original_src=list(conns[i][1]), original_dst=list(conns[i][2]),
                src=list(src), dst=list(dst), src_pad_uuids=list(src_ids), dst_pad_uuids=list(dst_ids),
                src_escape_edges=lp, dst_escape_edges=rp,
                terminal_rule='existing_exact_terminal_cell_exemption',
                src_cell_blocked=src in blocked[i], dst_cell_blocked=dst in blocked[i]))
        report['source_sha256'] = hashlib.sha256(Path(board_path).read_bytes()).hexdigest()
    except Exception as exc:
        return tuple(conns), dict(report, proposed=[], error=type(exc).__name__+': '+str(exc))
    return tuple(output), report


def admit_retry(original_paths, retry_paths, *, independently_qualified=()):
    """Every previously reachable obligation survives; at least one improves."""
    if len(original_paths) != len(retry_paths):
        return False
    exempt = set(independently_qualified)
    before = {i for i,p in enumerate(original_paths) if p is None and i not in exempt}
    after = {i for i,p in enumerate(retry_paths) if p is None and i not in exempt}
    return after < before
