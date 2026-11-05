"""Reject nonproductive generated point-to-point walks; no route authority."""


def productive(ops):
    """A reverse duplicate is the same manufactured capsule, not two legs.

    Closing a surface excursion back to its own origin cannot connect two
    different terminal components. Empty operations remain possible ONLY for
    independently witnessed retained connections in the owning producer.
    Layer transitions and distinct-width/face metal remain distinct here.
    """
    if type(ops)not in(list,tuple):return False
    tracks=[];vias=[]
    for op in ops:
        if type(op)not in(list,tuple)or not op:return False
        if op[0]=='trk'and len(op)==5:
            try:key=(int(op[4]),int(op[3]),tuple(sorted((tuple(op[1]),tuple(op[2])))))
            except(TypeError,ValueError):return False
            if op[1]==op[2]:return False
            if key in tracks:return False
            tracks.append(key)
        elif op[0]=='via'and len(op)==4:
            key=(tuple(op[1]),op[2],op[3])
            if key in vias:return False
            vias.append(key)
        else:return False
    if tracks and not vias:
        first,last=ops[0],ops[-1]
        if first[0]==last[0]=='trk'and tuple(first[1])==tuple(last[2]):return False
    return True
