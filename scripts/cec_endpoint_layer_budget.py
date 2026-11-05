"""Optimistic new-via lower bounds for an explicitly supplied route graph.

This is search pruning/ordering only. Source-provided retained barrel spans
may lower the bound even when they prove unreachable or a later guard refuses
them. They grant no physical access, current capacity or route admission.
All newly proposed graph transitions are through vias, with unit via count.
"""


def minimum_new_vias(layers, end_layers, *, retained_spans=()):
    if type(layers)not in(list,tuple)or type(end_layers)not in(list,tuple):
        raise ValueError('bounded_explicit_endpoint_layer_budget_required')
    faces=tuple(layers);goals=tuple(end_layers)
    if (not 1<=len(faces)<=8 or any(type(l)is not int or l<0 for l in faces)
            or len(set(faces))!=len(faces)
            or not 1<=len(goals)<=8 or any(type(l)is not int or l not in faces for l in goals)
            or len(set(goals))!=len(goals)
            or type(retained_spans)not in(list,tuple)or len(retained_spans)>256):
        raise ValueError('bounded_explicit_endpoint_layer_budget_required')
    access={l:{l}for l in faces}
    for span in retained_spans:
        if (type(span)not in(list,tuple)or not 2<=len(span)<=8
                or any(type(l)is not int or l not in faces for l in span)or len(set(span))!=len(span)):
            raise ValueError('actual_supplied_retained_layer_span_required')
        for face in span:access[face].update(span)
    # Ignore positions, planar obstacles and later retained-barrel guard
    # refusals. This deliberately optimistic closure cannot wrongly spend
    # another via or eliminate a possible zero-new-via continuation.
    for through in faces:
        for face in faces:
            if through in access[face]:access[face].update(access[through])
    return {face:int(not bool(access[face]&set(goals)))for face in faces}
