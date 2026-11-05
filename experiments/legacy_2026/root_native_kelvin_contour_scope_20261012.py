"""Freeze every positively inventoried native Kelvin net during cosmetic work.

This selector grants no copper mutation or electrical qualification. A caller
must freshly replay the exact saved source, retain its identity and independently
receive the complete saved child. Unknown cuts are frozen, never exempted.
"""


def frozen_nets(report):
    if (not isinstance(report, dict) or report.get('complete') is not True
            or report.get('identity_stable') is not True
            or report.get('source_unchanged') is not True
            or report.get('code_unchanged') is not True
            or report.get('errors') != []):
        raise ValueError('fresh_identity_stable_native_kelvin_inventory_required')
    clipped = report.get('clipped_isolation')
    if not isinstance(clipped, dict):
        raise ValueError('native_clipped_scope_required')
    expected, details = clipped.get('expected'), clipped.get('details')
    if (type(expected) is not int or not 0 <= expected <= 4096
            or not isinstance(details, list) or len(details) != expected):
        raise ValueError('complete_bounded_native_kelvin_scope_required')
    frozen, identities = set(), set()
    for row in details:
        if not isinstance(row, dict):
            raise ValueError('positive_native_kelvin_leg_required')
        net = row.get('net')
        source, sense = row.get('source_pad'), row.get('sense_terminal')
        if (not isinstance(net, str) or not net
                or not isinstance(source, dict) or not isinstance(sense, dict)
                or source.get('net') != net or sense.get('net') != net
                or any(not isinstance(p.get('uuid'), str) or not p['uuid'] for p in (source, sense))
                or source['uuid'] == sense['uuid']):
            raise ValueError('exact_native_kelvin_terminal_identity_required')
        identity = (source['uuid'], sense['uuid'])
        if identity in identities:
            raise ValueError('ambiguous_native_kelvin_leg_inventory')
        identities.add(identity)
        frozen.add(net)
    return frozen


def positive_contour_scope(report):
    """Permit revalidation only for complete, already-positive native cohorts.

    This is a read-only search filter, not permission to change a cut. The
    final receiver must rederive the actual new zones and absolutely re-admit
    both saved boards. One unknown/failing leg freezes its entire shared net.
    """
    import cec_force_sense_evidence as evidence
    native = frozen_nets(report)
    self_check = evidence.compare_contact_preservation(report, report)
    if (self_check.get('comparison_complete') is not True
            or self_check.get('same_evidence') is not True):
        raise ValueError('complete_self_consistent_native_contact_scope_required')
    permitted, refused, admissions = set(), set(), {}
    for net in sorted(native):
        legs = [row for row in report['clipped_isolation']['details'] if row['net'] == net]
        prior = evidence.admit_changed_net(report, report, net)
        admissions[net] = prior
        if (legs and all(row.get('ok') is True for row in legs)
                and prior.get('ok') is True and prior.get('applicable') is True
                and prior.get('checked') == len(legs)
                and len(prior.get('expected_legs', ())) == len(legs)):
            permitted.add(net)
        else:
            refused.add(net)
    return dict(native_kelvin_nets=sorted(native), permitted_nets=sorted(permitted),
                frozen_nets=sorted(refused), positive_source_admissions=admissions,
                search_filter_only=True, qualification_granted=False, release_authority=False)
