"""Receive new authority-pad joins without mistaking thin copper for progress.

Pure bounded partition comparison. Existing unrated debt remains debt; any
NEW trace-only authority join must also exist in the independent rated graph.
This is not a zone, barrel, electrical-load or release certificate.
"""


def compare(before, after):
    result=dict(ok=False, complete=False, new_joins=[], unrated_new_joins=[],
                errors=[], release_authority=False, inherited_debt_qualified=False)
    try:
        def partition(graph, kind):
            proof=graph[kind]
            parts=proof['components']
            if type(parts) is not list or not 1<=len(parts)<=512:
                raise ValueError('missing_or_unbounded_current_partition')
            lookup={}; identities={}
            for index, part in enumerate(parts):
                if type(part) is not list or not part:
                    raise ValueError('empty_current_partition')
                for row in part:
                    uid=row.get('uuid') if type(row) is dict else None
                    if type(uid) is not str or not uid or uid in lookup or len(lookup)>=512:
                        raise ValueError('ambiguous_or_unbounded_current_terminal')
                    lookup[uid]=index; identities[uid]=row
            return lookup,identities
        bt,bi=partition(before,'trace_connectivity');br,bri=partition(before,'rated_connectivity')
        at,ai=partition(after,'trace_connectivity');ar,ari=partition(after,'rated_connectivity')
        if not bi==bri==ai==ari:
            raise ValueError('physical_current_authority_inventory_changed')
        if before['required_by_layer_mm']!=after['required_by_layer_mm']:
            raise ValueError('current_width_contract_changed')
        ids=sorted(bi)
        for i,left in enumerate(ids):
            for right in ids[i+1:]:
                if bt[left]==bt[right] and at[left]!=at[right]:
                    raise ValueError('prior_trace_authority_connection_lost')
                if br[left]==br[right] and ar[left]!=ar[right]:
                    raise ValueError('prior_rated_authority_connection_lost')
                if bt[left]!=bt[right] and at[left]==at[right]:
                    pair=[left,right];result['new_joins'].append(pair)
                    if ar[left]!=ar[right]:result['unrated_new_joins'].append(pair)
        result.update(complete=True,ok=not result['unrated_new_joins'])
    except (KeyError,TypeError,ValueError) as exc:
        result['errors'].append(str(exc))
    return result
