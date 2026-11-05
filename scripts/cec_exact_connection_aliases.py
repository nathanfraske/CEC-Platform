"""Exact ordinary Source-request aliases, not connection or copper authority.

Retain the complete Source inventory for every saved receiver. A separate
routing view may construct one path for byte-equivalent JSON requests. Same
net, nearby endpoints, reversed endpoints or similar operations are NOT
equivalence. Ground/dependency and specialized/current-bearing requests are
deliberately outside this first scope. Saved native endpoints remain due.
"""
import hashlib
import json
import math
import time


def _literal(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _sha(value):
    return hashlib.sha256(_literal(value).encode()).hexdigest()


def _port(value):
    if type(value)is not dict:return False
    keys=set(value)
    if keys not in ({'at_nm','layers','pad_uuid'},{'at_nm','layers','native_uuids'}):return False
    at=value['at_nm'];layers=value['layers']
    if (type(at)is not list or len(at)!=2 or any(type(n)is not int for n in at)
            or type(layers)is not list or not 1<=len(layers)<=64
            or any(type(n)is not int for n in layers)or len(set(layers))!=len(layers)):return False
    ids=[value['pad_uuid']]if 'pad_uuid'in value else value['native_uuids']
    return (type(ids)is list and 1<=len(ids)<=16 and all(type(u)is str and u for u in ids)
        and len(set(ids))==len(ids))


def _eligible(request):
    return (set(request)=={'kind','net','a','b','width_nm'}
        and request['kind']=='source_boundary'and type(request['net'])is str
        and bool(request['net'])and request['net']!='GND'
        and type(request['width_nm'])is int and 0<request['width_nm']<=100000000
        and _port(request['a'])and _port(request['b']))


def derive(requests):
    """Deterministic full-inventory binding; never delete original requests."""
    if (type(requests)is not dict or not 1<=len(requests)<=64
            or any(type(k)is not str or not k or type(v)is not dict for k,v in requests.items())):
        raise ValueError('bounded_complete_source_request_inventory_required')
    literal=_literal(requests)
    if len(literal)>4*1024*1024:raise ValueError('bounded_source_request_literal_required')
    groups={};canonical={k:k for k in requests}
    for key,request in sorted(requests.items()):
        if _eligible(request):groups.setdefault(_literal(request),[]).append(key)
    aliases=[]
    for literal,members in sorted(groups.items()):
        if len(members)<2:continue
        first=min(members)
        for key in members:canonical[key]=first
        aliases.append(dict(canonical=first,members=sorted(members),
            request_sha256=hashlib.sha256(literal.encode()).hexdigest()))
    return dict(schema=1,scope='exact_plain_non_ground_source_boundary_request_aliases',
        source_inventory_sha256=_sha(requests),canonical_by_original=dict(sorted(canonical.items())),
        groups=sorted(aliases,key=lambda q:q['canonical']),original_count=len(requests),
        routing_count=len(set(canonical.values())),all_original_requests_retained=True,
        native_endpoint_receiving_still_required=True,copper_authority=False,release_authority=False)


def routing_view(requests):
    proof=derive(requests)
    keys=set(proof['canonical_by_original'].values())
    return {k:requests[k]for k in sorted(keys)},proof


def verify(requests,proof,canonical_keys):
    fresh=derive(requests)
    if fresh!=proof or set(canonical_keys)!=set(fresh['canonical_by_original'].values()):
        raise ValueError('exact_full_source_request_alias_coverage_required')
    return fresh


def packet_coverage(packet):
    """Construction metadata is rederived, never accepted as connectivity."""
    fields={'original_source_requests','exact_source_request_aliases'}
    if not fields.intersection(packet):return None
    if not fields<=packet.keys():raise ValueError('complete_source_alias_packet_required')
    return verify(packet['original_source_requests'],packet['exact_source_request_aliases'],packet['domains'])


def receive_paths(board,requests,*,timeout_s=10.):
    """Independently witness EVERY original alias member on actual copper.

    The caller must independently recompile Source requests. No caller alias
    allowlist, success flag, synthetic zone or implicit same-net connectivity
    participates. The observer excludes zones/foreign nets and checks every
    named native pad/track/barrel at its exact layer/contact. This relation
    alone grants no width, current, Kelvin, routing or release permission.
    """
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_source_alias_native_receiving_required')
    started=time.monotonic();proof=derive(requests);witnesses=[]
    if proof['groups']:
        import cec_cell_escape_replan as escape
        binding=escape.row._source_binding(board)
        for group in proof['groups']:
            for member in group['members']:
                remaining=timeout_s-(time.monotonic()-started)
                if remaining<=0:raise ValueError('source_alias_native_receiving_deadline')
                native=escape.retained_native_boundary_connection(board,requests[member],timeout_s=remaining)
                if (type(native)is not dict or native.get('all_named_contacts_connected')is not True
                        or native.get('zone_and_foreign_net_edges_excluded')is not True):
                    raise ValueError('original_alias_source_boundary_not_natively_connected:'+member)
                witnesses.append(dict(original_obligation=member,canonical=group['canonical'],
                    request_sha256=group['request_sha256'],native_endpoint_connection=native))
        if binding!=escape.row._source_binding(board):
            raise ValueError('source_alias_native_observer_changed_board')
    if proof!=derive(requests):raise ValueError('source_alias_requests_changed_during_receiving')
    if time.monotonic()-started>=timeout_s:raise ValueError('source_alias_native_receiving_deadline')
    return dict(ok=True,complete=True,alias_coverage=proof,witnesses=witnesses,
        all_original_alias_members_connected=True,material_unchanged=True,
        current_qualified=False,release_authority=False)
