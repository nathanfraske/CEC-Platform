"""Exact bounded merge of finite, already-ranked proposal streams."""
from heapq import merge
from itertools import islice
from operator import itemgetter


def take_ranked(rows, limit):
    """Take the stable best K without building the discarded Cartesian tail.

    Each input stream must be ordered by its first field. Equal-ranked items
    retain stream order and then within-stream order, exactly as concatenating
    the streams followed by a stable full sort. Admission stays in the stream
    producer: rejected candidates must not occupy the beam.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("ranked frontier limit must be a positive integer")
    return list(islice(merge(*rows, key=itemgetter(0)), limit))
