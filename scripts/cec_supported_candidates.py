"""Stable bounded selection after a necessary constraint, before beam caps."""
import time


def select_ranked(rows, *, limit, predicate=None, max_checks=256,
                  deadline=None, diagnostics=None):
    """Return a supported prefix; never treat a cap as infeasibility proof.

    Rows must already be in deterministic objective order. The predicate is
    only a necessary-condition screen, not final admission. No predicate
    preserves historical prefix semantics. Failed/uncertain checks never
    fall back to an unchecked row. Diagnostics count only checked candidates.
    """
    limit, max_checks = max(0,int(limit)), max(0,int(max_checks))
    out=[]
    report=dict(checked=0,rejected=0,selected=0,stop_reason='domain_exhausted',
                selection_limit=limit,check_limit=max_checks,admission_authority=False)
    try:
        if limit == 0:
            report['stop_reason']='selection_limit'
            return out
        for row in rows:
            if deadline is not None and time.monotonic() >= deadline:
                report['stop_reason']='deadline_exhausted'
                break
            if predicate is not None:
                if report['checked'] >= max_checks:
                    report['stop_reason']='check_limit'
                    break
                report['checked']+=1
                # Require an explicit Boolean proof, not a truthy error dict.
                supported=predicate(row)
                if not isinstance(supported,bool):
                    raise TypeError('support predicate must return bool')
                if not supported:
                    report['rejected']+=1
                    continue
            out.append(row)
            report['selected']=len(out)
            if len(out) >= limit:
                report['stop_reason']='selection_limit'
                break
        return out
    except Exception:
        report['stop_reason']='predicate_error'
        raise
    finally:
        if diagnostics is not None:
            diagnostics.update(report)
