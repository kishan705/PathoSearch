"""Search result post-processing (pure Python, unit-tested).

Old behaviour: the top 5 rows straight from LanceDB, scored as
(1 - distance) * 100 with LanceDB's default L2 distance. That number is not a
similarity (a true cosine of 0.3 showed as -40%), and the top 5 were usually
neighbouring tiles of the same spot.
"""
from config import NEIGHBOUR_DISTANCE


def cosine_from_distance(distance):
    """LanceDB cosine distance = 1 - cosine."""
    return round(1.0 - float(distance), 6)


def _near(a, b, factor):
    if a["slide_id"] != b["slide_id"]:
        return False
    reach = factor * max(a.get("size", 256), b.get("size", 256))
    return abs(a["x"] - b["x"]) < reach and abs(a["y"] - b["y"]) < reach


def diversify(hits, top_k, exclude=None, factor=NEIGHBOUR_DISTANCE):
    """Best-first, skipping hits that sit next to an already chosen hit on the same slide.

    exclude: optional (slide_id, x, y) of the query patch itself ("find similar").
    """
    chosen = []
    ex = None
    if exclude is not None:
        ex = {"slide_id": exclude[0], "x": exclude[1], "y": exclude[2], "size": 0}
    for h in sorted(hits, key=lambda r: r["cosine"], reverse=True):
        if ex is not None and _near(h, ex, factor):
            continue
        if any(_near(h, c, factor) for c in chosen):
            continue
        chosen.append(h)
        if len(chosen) >= top_k:
            break
    return chosen
