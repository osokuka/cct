"""
One-off processor: turn raw Overpass exports into a compact seed dataset with a
weekly collection plan.

Reads:
  * _raw_streets.json  -> drivable streets within 1.5 km of the focus point
                          (Overpass `out geom`), and
  * _raw_public.json   -> parks / schools / squares across town.

Writes gjakova_osm.json containing:
  * streets[]        -> real road geometry (segments) + dumpster coordinates
                        (~80 m apart) + a weekly-plan assignment:
                          team  (0..NUM_TEAMS-1)  = one of 3 non-overlapping zones,
                          day   (0..WORK_DAYS-1 or None) = weekday (Mon-Fri) or
                                                           unscheduled this week
  * public_areas[]   -> centroid + approximate area (m²) for town-wide cleaning

Plan logic:
  1. Streets are sorted by bearing from the zone centre and split into 3 contiguous
     angular zones balanced by dumpster count -> teams never cross each other's roads.
  2. Within each zone, nearby streets are grouped (nearest-neighbour) into vicinity
     clusters of <= STREETS_PER_DAY and one cluster is assigned per weekday (Mon-Fri).
     Each team therefore works ~5 adjacent streets per day; streets beyond the 5-day
     plan are left unscheduled.

Run inside Docker:
    docker compose exec web python locations/management/commands/data/build_gjakova_osm.py
"""

import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

CENTER_LAT = 42.37092943416372
CENTER_LNG = 20.435394872814765
ZONE_RADIUS_M = 1500
SEGMENT_BUFFER_M = 200         # keep road segments this far outside the zone edge
DUMPSTER_SPACING_M = 80
DEDUP_M = 45

NUM_TEAMS = 3                  # 3 collection teams / zones
WORK_DAYS = 5                  # Mon..Fri
STREETS_PER_DAY = 5            # max streets per team per day (a vicinity cluster)

STREET_TYPES = {
    "residential", "living_street", "service", "unclassified",
    "tertiary", "secondary", "primary",
}


def m_per_deg_lng(lat):
    return 111320.0 * math.cos(math.radians(lat))


def dist_m(a, b, c, d):
    return math.hypot((c - a) * 111130.0, (d - b) * m_per_deg_lng(a))


def within(lat, lng, extra=0.0):
    return dist_m(CENTER_LAT, CENTER_LNG, lat, lng) <= ZONE_RADIUS_M + extra


def code_from_name(name, used):
    base = re.sub(r"[^A-Za-z0-9]", "", (name or "").upper())[:10] or "ST"
    code = base
    i = 1
    while code in used:
        i += 1
        code = f"{base}{i}"
    used.add(code)
    return code


def interpolate_points(segment, spacing):
    if len(segment) < 2:
        return list(segment)
    pts = [segment[0]]
    carry = 0.0
    for (lat1, lng1), (lat2, lng2) in zip(segment, segment[1:]):
        seg_len = dist_m(lat1, lng1, lat2, lng2)
        if seg_len == 0:
            continue
        pos = spacing - carry
        while pos < seg_len:
            frac = pos / seg_len
            pts.append((lat1 + (lat2 - lat1) * frac, lng1 + (lng2 - lng1) * frac))
            pos += spacing
        carry = (carry + seg_len) % spacing
    return pts


def load_streets():
    with open(os.path.join(HERE, "_raw_streets.json")) as fh:
        data = json.load(fh)
    by_name = {}
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        if tags.get("highway") not in STREET_TYPES:
            continue
        name = tags.get("name")
        if not name:
            continue
        geom = [(g["lat"], g["lon"]) for g in el.get("geometry", [])]
        if len(geom) < 2:
            continue
        by_name.setdefault(name, {"highway": tags["highway"], "segments": []})
        by_name[name]["segments"].append(geom)
    return by_name


def build_streets():
    by_name = load_streets()
    used_codes = set()
    streets = []
    for name in sorted(by_name):
        info = by_name[name]
        placed = []
        segments = []
        for seg in info["segments"]:
            # keep the road segment only if part of it is inside/near the zone
            if not any(within(lat, lng, SEGMENT_BUFFER_M) for lat, lng in seg):
                continue
            segments.append([[round(lat, 6), round(lng, 6)] for lat, lng in seg])
            for lat, lng in interpolate_points(seg, DUMPSTER_SPACING_M):
                if not within(lat, lng):
                    continue
                if any(dist_m(lat, lng, p[0], p[1]) < DEDUP_M for p in placed):
                    continue
                placed.append((round(lat, 6), round(lng, 6)))
        if not placed:
            continue
        clat = sum(p[0] for p in placed) / len(placed)
        clng = sum(p[1] for p in placed) / len(placed)
        streets.append({
            "name": name,
            "code": code_from_name(name, used_codes),
            "highway": info["highway"],
            "dumpsters": placed,
            "segments": segments,
            "_clat": clat,
            "_clng": clng,
            "_angle": math.atan2(clat - CENTER_LAT, clng - CENTER_LNG),
        })
    return streets


def _nn_order(zone):
    """Greedy nearest-neighbour ordering of streets so consecutive streets are
    spatial neighbours (produces tight vicinity clusters when chunked)."""
    if not zone:
        return []
    remaining = zone[:]
    cx = sum(s["_clat"] for s in remaining) / len(remaining)
    cy = sum(s["_clng"] for s in remaining) / len(remaining)
    start = min(remaining, key=lambda s: dist_m(cx, cy, s["_clat"], s["_clng"]))
    order = [start]
    remaining.remove(start)
    while remaining:
        last = order[-1]
        nxt = min(remaining, key=lambda s: dist_m(last["_clat"], last["_clng"], s["_clat"], s["_clng"]))
        order.append(nxt)
        remaining.remove(nxt)
    return order


def assign_weekly_plan(streets):
    """Split streets into NUM_TEAMS balanced, non-overlapping angular zones (teams
    never cross each other's roads). Within each zone, group nearby streets into
    daily clusters of <= STREETS_PER_DAY and assign one cluster per weekday (Mon-Fri).
    Streets beyond the 5-day plan are left unscheduled (day = None)."""
    streets.sort(key=lambda s: s["_angle"])
    total = sum(len(s["dumpsters"]) for s in streets)
    target = total / NUM_TEAMS

    # 1) contiguous angular zones balanced by dumpster count -> team
    team = 0
    run = 0
    for s in streets:
        s["team"] = team
        run += len(s["dumpsters"])
        if team < NUM_TEAMS - 1 and run >= target * (team + 1):
            team += 1

    # 2) vicinity clusters per zone -> one cluster (<=5 streets) per weekday
    plan = {}
    for t in range(NUM_TEAMS):
        zone = [s for s in streets if s["team"] == t]
        ordered = _nn_order(zone)
        per_day = {}
        for idx, s in enumerate(ordered):
            group = idx // STREETS_PER_DAY
            day = group if group < WORK_DAYS else None
            s["day"] = day
            if day is not None:
                per_day.setdefault(day, {"streets": 0, "points": 0})
                per_day[day]["streets"] += 1
                per_day[day]["points"] += len(s["dumpsters"])
        plan[t] = per_day

    # 3) points carry their street's weekday (None if unscheduled this week)
    for s in streets:
        d = s["day"]
        s["points"] = [[lat, lng, d] for (lat, lng) in s["dumpsters"]]
        del s["dumpsters"]
    return plan


def polygon_area_m2(coords):
    if len(coords) < 3:
        return 0.0
    lat0 = sum(c[0] for c in coords) / len(coords)
    mlat, mlng = 111130.0, m_per_deg_lng(lat0)
    xy = [((lng - CENTER_LNG) * mlng, (lat - CENTER_LAT) * mlat) for lat, lng in coords]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def classify(tags):
    if tags.get("amenity") in ("school", "university", "college", "kindergarten"):
        return "school_yard"
    if tags.get("place") == "square" or tags.get("highway") == "pedestrian":
        return "city_center"
    return "park"


def build_public_areas():
    with open(os.path.join(HERE, "_raw_public.json")) as fh:
        data = json.load(fh)
    used_codes = set()
    areas, seen = [], set()
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        geom = [(g["lat"], g["lon"]) for g in el.get("geometry", [])]
        if len(geom) < 3:
            continue
        lat = sum(g[0] for g in geom) / len(geom)
        lng = sum(g[1] for g in geom) / len(geom)
        area = polygon_area_m2(geom)
        if area < 150:
            continue
        space_type = classify(tags)
        name = tags.get("name") or {
            "park": "Park", "school_yard": "School yard", "city_center": "Public square"
        }[space_type] + " (Gjakovë)"
        key = (round(lat, 4), round(lng, 4), name)
        if key in seen:
            continue
        seen.add(key)
        areas.append({
            "name": name,
            "code": code_from_name(name, used_codes),
            "space_type": space_type,
            "sqm": int(min(max(area, 200), 80000)),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
        })
    return areas


def main():
    streets = build_streets()
    plan = assign_weekly_plan(streets)
    public_areas = build_public_areas()

    # strip private helper keys
    for s in streets:
        for k in ("_clat", "_clng", "_angle"):
            s.pop(k, None)

    out = {
        "center": {"lat": CENTER_LAT, "lng": CENTER_LNG, "zoom": 15},
        "zone_radius_m": ZONE_RADIUS_M,
        "spacing_m": DUMPSTER_SPACING_M,
        "num_teams": NUM_TEAMS,
        "work_days": WORK_DAYS,
        "streets_per_day": STREETS_PER_DAY,
        "streets": streets,
        "public_areas": public_areas,
    }
    with open(os.path.join(HERE, "gjakova_osm.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    total = sum(len(s["points"]) for s in streets)
    scheduled = sum(1 for s in streets if s["day"] is not None)
    print(f"streets: {len(streets)} (scheduled {scheduled}) | dumpsters: {total} | public areas: {len(public_areas)}")
    dow = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for t in range(NUM_TEAMS):
        per_day = plan[t]
        days = ", ".join(f"{dow[d]}:{per_day[d]['streets']}st/{per_day[d]['points']}pt" for d in sorted(per_day))
        print(f"  Team {t}: {days}")


if __name__ == "__main__":
    main()
