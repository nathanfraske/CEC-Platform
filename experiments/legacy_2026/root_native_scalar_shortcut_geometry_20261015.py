"""Untrusted finite 0/45 construction paths; no saved-copper permission."""
def paths(start,end):
    for point in (start,end):
        if (type(point) not in (tuple,list) or len(point)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in point)):
            raise ValueError('exact_bounded_native_endpoints_required')
    start,end=tuple(start),tuple(end)
    if start==end:raise ValueError('distinct_native_endpoints_required')
    dx,dy=end[0]-start[0],end[1]-start[1]
    d=min(abs(dx),abs(dy));sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
    result=[]
    for middle in ((start[0]+sx*d,start[1]+sy*d),(end[0]-sx*d,end[1]-sy*d)):
        path=[start]+([] if middle in (start,end) else [middle])+[end]
        if path not in result:result.append(path)
    return result
