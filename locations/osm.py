"""
OpenStreetMap street population for zones (Compounds).

Given a zone's drawn boundary (GeoJSON polygon), query the Overpass API for the
drivable streets inside it and materialize them as ``Building`` records (one per
named street) with real road geometry stored in ``geo_polyline``.

No third-party geo library is required: Overpass performs the spatial filtering
server-side via its ``poly:`` filter, so we only send the boundary ring and parse
the returned way geometry.
"""

import json
import re

import requests

# Overpass mirrors, tried in order. The primary occasionally rate-limits, so we
# fall back to community mirrors (the mail.ru mirror proved reliable previously).
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Real, drivable streets — mirrors the offline pipeline (excludes tracks/paths).
STREET_TYPES = [
    "residential", "living_street", "service", "unclassified",
    "tertiary", "secondary", "primary",
]

DEFAULT_TIMEOUT = 180


class OverpassError(RuntimeError):
    """Raised when every Overpass endpoint fails."""


def ring_to_overpass_poly(ring):
    """Convert a GeoJSON outer ring ([[lng, lat], ...]) to an Overpass poly string.

    Overpass expects space-separated ``lat lng`` pairs: "lat1 lng1 lat2 lng2 ...".
    """
    coords = []
    for pt in ring:
        # GeoJSON is [lng, lat]; Overpass wants "lat lng".
        lng, lat = float(pt[0]), float(pt[1])
        coords.append(f"{lat} {lng}")
    return " ".join(coords)


def build_query(ring, timeout=DEFAULT_TIMEOUT):
    poly = ring_to_overpass_poly(ring)
    types = "|".join(STREET_TYPES)
    return (
        f"[out:json][timeout:{timeout}];"
        f'way["highway"~"^({types})$"]["name"](poly:"{poly}");'
        f"out geom;"
    )


def fetch_streets(ring, timeout=DEFAULT_TIMEOUT):
    """Query Overpass and return streets grouped by name.

    Returns a list of dicts: ``{"name", "highway", "segments"}`` where segments
    is a list of polylines, each a list of ``[lat, lng]`` points.
    """
    query = build_query(ring, timeout=timeout)
    last_error = None
    for url in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(url, data={"data": query}, timeout=timeout + 20)
            resp.raise_for_status()
            data = resp.json()
            return _group_by_name(data)
        except Exception as exc:  # network/JSON/HTTP — try the next mirror
            last_error = exc
            continue
    raise OverpassError(f"All Overpass endpoints failed: {last_error}")


def _group_by_name(data):
    by_name = {}
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        name = tags.get("name")
        highway = tags.get("highway")
        if not name or highway not in STREET_TYPES:
            continue
        geom = [[g["lat"], g["lon"]] for g in el.get("geometry", [])]
        if len(geom) < 2:
            continue
        entry = by_name.setdefault(name, {"name": name, "highway": highway, "segments": []})
        entry["segments"].append([[round(lat, 6), round(lng, 6)] for lat, lng in geom])
    return list(by_name.values())


def _code_from_name(name, used):
    base = re.sub(r"[^A-Za-z0-9]", "", (name or "").upper())[:10] or "ST"
    code = base
    i = 1
    while code in used:
        i += 1
        code = f"{base}{i}"[:50]
    used.add(code)
    return code


def _segments_to_geojson(segments):
    return json.dumps({
        "type": "MultiLineString",
        "coordinates": [[[lng, lat] for lat, lng in seg] for seg in segments],
    })


def populate_zone_streets(compound, replace=False):
    """Populate ``compound`` with streets from OSM inside its drawn boundary.

    * ``replace=False`` (default): merge — existing streets are matched by name
      (case-insensitive), their geometry refreshed, and only new streets created.
    * ``replace=True``: deactivate streets no longer returned by OSM.

    Returns ``{"created", "updated", "total"}``. Raises ``ValueError`` when the
    zone has no boundary, and ``OverpassError`` on network failure.
    """
    # Local import avoids a circular import (models imports nothing from here).
    from .models import Building, Floor

    ring = compound.boundary_ring
    if not ring or len(ring) < 3:
        raise ValueError("Zone has no boundary polygon. Draw the zone boundary first.")

    streets = fetch_streets(ring)

    existing = {
        b.name.strip().lower(): b
        for b in compound.buildings.all()
    }
    used_codes = set(compound.buildings.values_list("code", flat=True))

    created = updated = 0
    seen_keys = set()

    for street in streets:
        name = street["name"].strip()[:200]
        key = name.lower()
        seen_keys.add(key)
        geojson = _segments_to_geojson(street["segments"])

        building = existing.get(key)
        if building:
            changed = False
            if building.geo_polyline != geojson:
                building.geo_polyline = geojson
                changed = True
            if not building.is_active:
                building.is_active = True
                changed = True
            if changed:
                building.save(update_fields=["geo_polyline", "is_active"])
            updated += 1
        else:
            code = _code_from_name(name, used_codes)
            building = Building.objects.create(
                compound=compound, code=code, name=name, geo_polyline=geojson,
            )
            # A default segment so service points can later be attached.
            Floor.objects.get_or_create(
                building=building, code="A", defaults={"name": "Segment A"}
            )
            created += 1

    if replace:
        for key, building in existing.items():
            if key not in seen_keys and building.is_active:
                building.is_active = False
                building.save(update_fields=["is_active"])

    return {"created": created, "updated": updated, "total": len(streets)}
