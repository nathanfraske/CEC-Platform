"""Expose native report truncation without changing a rule or a fault identity.

The verified KiCad 10.0.5 engine has per-category limits of 199 and extended
limits of 499 for clearance/unconnected items. A saturated report cannot prove
that its item-pair list is exhaustive. Do not silently carry this limit table
across an unverified native version. This diagnostic grants no mutation, debt
qualification, reconstruction, routing or release permission.

Verified primary source:
https://gitlab.com/kicad/code/kicad/-/blob/10.0.5/pcbnew/drc/drc_engine.cpp
"""
from collections import Counter


VERIFIED_VERSION = '10.0.5'
PRIMARY_SOURCE = 'https://gitlab.com/kicad/code/kicad/-/blob/10.0.5/pcbnew/drc/drc_engine.cpp'


def assess(report):
    return _assess_verified_limits(report,199,499,PRIMARY_SOURCE)


def _assess_verified_limits(report,ordinary_limit,extended_limit,limit_source):
    """Internal diagnostic for a producer that independently bound its engine.

    This cannot waive any fault or grant admission. Callers should use assess()
    for an unbound report, or cec_native_drc_runner.run() for its exact verified
    reporting build; a version string alone does not identify a custom engine.
    """
    result=dict(schema=1, category_limits_checked=False, errors=[],
        potentially_truncated=None, saturated_categories=[],
        counts_are_reported_observations_not_exhaustive_totals=True,
        full_native_inventory_proved=False, faults_suppressed=0,
        admission_unchanged=True, release_authority=False)
    if type(report) is not dict:
        result['errors'].append('native_drc_report_mapping_required')
        return result
    version=report.get('kicad_version')
    result['native_version']=version if type(version) is str else None
    violations=report.get('violations')
    opens=report.get('unconnected_items')
    if (type(violations) is not list or type(opens) is not list
            or len(violations)>65536 or len(opens)>65536
            or any(type(row) is not dict or type(row.get('type')) is not str
                   or not row['type'] for row in violations)
            or any(type(row) is not dict for row in opens)):
        result['errors'].append('bounded_native_drc_report_rows_required')
        return result
    counts=dict(Counter(row['type'] for row in violations))
    result['reported_violation_counts']=counts
    result['reported_unconnected_count']=len(opens)
    if version!=VERIFIED_VERSION:
        result['errors'].append('native_version_error_limits_not_verified')
        return result
    limits={kind:extended_limit if kind in ('clearance','unconnected_items') else ordinary_limit for kind in counts}
    result['saturated_categories']=[dict(type=kind,reported_count=count,limit=limits[kind])
        for kind,count in sorted(counts.items()) if count>=limits[kind]]
    if len(opens)>=extended_limit:
        result['saturated_categories'].append(dict(type='unconnected_items',reported_count=len(opens),limit=extended_limit))
    result.update(category_limits_checked=True,
        potentially_truncated=bool(result['saturated_categories']),
        verified_native_limit_source=limit_source)
    return result
