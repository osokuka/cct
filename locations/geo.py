"""
Lightweight geospatial helpers (no external geo libraries).

Used to place a dumpster from its GPS coordinates:
  * ``find_zone_for_point`` — which zone (Compound) boundary contains the point,
  * ``nearest_street`` — the closest street (Building) within that zone.
"""

import json
import math


def _ring_contains(lat, lng, ring):
    """Ray-casting point-in-polygon test. ``ring`` is [[lng, lat], ...]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]  # lng, lat
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_cross:
                inside = not inside
        j = i
    return inside


def find_zone_for_point(lat, lng, camp=None):
    """Return the active zone whose drawn boundary contains (lat, lng), or None."""
    from .models import Compound

    qs = Compound.objects.filter(is_active=True).exclude(geo_polygon__isnull=True).exclude(geo_polygon="")
    if camp is not None:
        qs = qs.filter(camp=camp)
    for zone in qs.select_related("camp"):
        ring = zone.boundary_ring
        if ring and _ring_contains(float(lat), float(lng), ring):
            return zone
    return None


def _m_per_deg_lng(lat):
    return 111320.0 * math.cos(math.radians(lat))


def _dist_point_to_segment_m(lat, lng, a, b):
    """Distance (m) from point to segment a->b, where a/b are [lng, lat]."""
    # Project to a local equirectangular plane in meters.
    mlat = 111130.0
    mlng = _m_per_deg_lng(lat)
    px, py = lng * mlng, lat * mlat
    ax, ay = a[0] * mlng, a[1] * mlat
    bx, by = b[0] * mlng, b[1] * mlat
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    projx, projy = ax + t * dx, ay + t * dy
    return math.hypot(px - projx, py - projy)


def _iter_lines(geom):
    """Yield coordinate lists ([[lng,lat],...]) from a LineString/MultiLineString."""
    if not geom:
        return
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "LineString":
        yield coords
    elif gtype == "MultiLineString":
        for line in coords:
            yield line


def nearest_street(compound, lat, lng):
    """Return (building, distance_m) of the closest street in the zone, or (None, None)."""
    best = None
    best_d = None
    for b in compound.buildings.filter(is_active=True):
        if not b.geo_polyline:
            continue
        try:
            geom = json.loads(b.geo_polyline)
        except (ValueError, TypeError):
            continue
        for line in _iter_lines(geom):
            for p1, p2 in zip(line, line[1:]):
                d = _dist_point_to_segment_m(float(lat), float(lng), p1, p2)
                if best_d is None or d < best_d:
                    best_d = d
                    best = b
    return best, best_d
