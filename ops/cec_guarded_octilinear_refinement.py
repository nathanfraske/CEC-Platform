"""Finite exact-guard cleanup of complete native route proposals.

Grid-internal heading policy need not cover off-grid terminal hooks. Check
the COMPLETE proposed path, keep literal ports, and return nothing partial.
This geometry helper supplies no electrical, current or admission authority.
"""
import math
import time
import cec_fr as fr
import cec_route_quality as quality
import cec_sensitive_scalar_path_reflow as shape


def clean(points):
    result=[]
    for p in points:
        p=tuple(p)
        if result and p==result[-1]:
            continue
        while len(result)>1:
            a,z=result[-2:];u=(z[0]-a[0],z[1]-a[1]);v=(p[0]-z[0],p[1]-z[1])
            if u[0]*v[1]!=u[1]*v[0] or u[0]*v[0]+u[1]*v[1]<=0:
                break
            result.pop()
        result.append(p)
    return result


def score(points):
    bad=0
    for a,b,c in zip(points,points[1:],points[2:]):
        u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
        dot=u[0]*v[0]+u[1]*v[1];cross=u[0]*v[1]-u[1]*v[0]
        bad+=int(dot<=0 or abs(cross)>dot)
    return bad,sum(math.dist(a,z) for a,z in zip(points,points[1:])),len(points)


def refine(points_nm, clear, *, max_trials=2048, max_passes=8, timeout_s=5., max_points=16):
    if (type(points_nm) is not list or not 2<=len(points_nm)<=32 or not callable(clear)
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points_nm)
            or type(max_trials) is not int or not 1<=max_trials<=4096
            or type(max_passes) is not int or not 1<=max_passes<=16
            or type(max_points) is not int or not 2<=max_points<=32
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10):
        raise ValueError('bounded_complete_native_path_refinement_required')
    points=clean(points_nm)
    if len(points)<2 or any(not quality.is_canonical_stroke(a,z,tolerance_nm=0) for a,z in zip(points,points[1:])):
        raise ValueError('literal_nonzero_native_0_45_strokes_required')
    ports=(points[0],points[-1]);before=score(points);deadline=time.monotonic()+timeout_s
    cache={};trials=0;passes=0;stop='pass_bound'
    def legal(path):
        for a,z in zip(path,path[1:]):
            if time.monotonic()>=deadline:
                return False
            key=(tuple(a),tuple(z))
            if key not in cache:
                cache[key]=clear(list(a),list(z)) is True
            if not cache[key]:
                return False
        return True
    for passes in range(max_passes):
        best=None;best_score=score(points)
        for i in range(len(points)-2):
            for j in range(len(points)-1,i+1,-1):
                for middle in fr._canonical_45_xy_paths(points[i],points[j]):
                    if trials>=max_trials or time.monotonic()>=deadline:
                        break
                    trials+=1
                    candidate=clean([*points[:i],*middle,*points[j+1:]])
                    rank=score(candidate)
                    if rank>=best_score or not legal(candidate):
                        continue
                    best=candidate;best_score=rank
                if trials>=max_trials or time.monotonic()>=deadline:
                    break
            if trials>=max_trials or time.monotonic()>=deadline:
                break
        if best is not None:
            points=best
        if trials>=max_trials or time.monotonic()>=deadline:
            stop='work_bound';break
        if best is None:
            stop='no_further_guarded_shortcut';break
    valid=False
    if len(points)<=max_points and (points[0],points[-1])==ports and legal(points):
        try:
            shape._points([list(p) for p in points]);valid=True
        except ValueError:
            pass
    return dict(complete=True, points_nm=[list(p) for p in points] if valid else None,
        whole_route_canonical=valid, source_ports_unchanged=(points[0],points[-1])==ports,
        initial_bad_turns=before[0], remaining_bad_turns=score(points)[0],
        initial_length_nm=before[1], final_length_nm=score(points)[1],
        trials=trials, passes=passes+1, clear_queries=len(cache), stop=stop,
        partial_route_returned=False, global_shortest_or_no_path_proof=False,
        acceptance_or_current_authority_granted=False)
