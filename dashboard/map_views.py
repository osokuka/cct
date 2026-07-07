"""
Map feature helpers for Gjakova operations.

Builds serializable dumpster + public-area feature lists and a data-driven map
center. Consumed by the Operations dashboard/TV endpoints. Client identity is
anonymized: only an opaque client code and payment status are exposed.
"""

from django.conf import settings


def default_center():
    """Configurable fallback map center (no site hardcoded in code).

    Set ``MAP_DEFAULT_CENTER`` in settings/env to a dict {lat,lng,zoom}. Only
    used when the scope has no geolocated points to derive a center from.
    """
    c = getattr(settings, "MAP_DEFAULT_CENTER", None) or {}
    return {
        "lat": float(c.get("lat", 0.0)),
        "lng": float(c.get("lng", 0.0)),
        "zoom": int(c.get("zoom", 13)),
    }


def center_from_rooms(rooms):
    """Data-driven map center: the centroid of the given rooms' coordinates.

    ``rooms`` may be a queryset or a materialized list of Room instances.
    Falls back to :func:`default_center` when nothing is geolocated.
    """
    lats, lngs = [], []
    for r in rooms:
        if r.latitude is not None and r.longitude is not None:
            lats.append(float(r.latitude))
            lngs.append(float(r.longitude))
    if not lats:
        return default_center()
    return {
        "lat": sum(lats) / len(lats),
        "lng": sum(lngs) / len(lngs),
        "zoom": default_center()["zoom"],
    }


def build_map_features(rooms):
    """Turn a Room queryset into serializable dumpster + public-area lists."""
    dumpsters = []
    public_areas = []

    for room in rooms:
        if room.latitude is None or room.longitude is None:
            continue

        lat = float(room.latitude)
        lng = float(room.longitude)

        if room.is_dumpster:
            client = room.client
            payment_status = client.payment_status if client else "unknown"
            dumpsters.append({
                "id": str(room.id),
                "dumpster_id": room.room_code,
                "dumpster_type": room.dumpster_type or "household",
                "dumpster_type_label": room.dumpster_type_label,
                "barcode": _safe_barcode(room),
                "client_id": client.client_code if client else None,
                "payment_status": payment_status,
                "payment_label": (
                    client.get_payment_status_display() if client else "No client / unconfirmed"
                ),
                "can_collect": room.can_collect,
                "paid_until": client.paid_until.isoformat() if client and client.paid_until else None,
                "last_collected": room.last_collected_at.isoformat() if room.last_collected_at else None,
                "lat": lat,
                "lng": lng,
                "neighbourhood": room.compound.name if room.compound_id else None,
                "street": room.building.name if room.building_id else None,
                "frequency_per_week": float(room.frequency_per_week or 0),
            })
        elif room.is_public_area:
            public_areas.append({
                "id": str(room.id),
                "name": room.room_description or room.room_code,
                "space_type": room.space_type,
                "space_type_label": room.get_space_type_display(),
                "sqm": float(room.actual_sqm or 0),
                "frequency_per_week": float(room.frequency_per_week or 0),
                "lat": lat,
                "lng": lng,
                "neighbourhood": room.compound.name if room.compound_id else None,
                "geojson": room.geo_polygon or None,
            })

    return dumpsters, public_areas


def map_counts(dumpsters, public_areas):
    return {
        "dumpsters": len(dumpsters),
        "collectable": sum(1 for d in dumpsters if d["can_collect"]),
        "blocked": sum(1 for d in dumpsters if not d["can_collect"]),
        "public_areas": len(public_areas),
    }


def _safe_barcode(room):
    try:
        return room.generate_barcode_data()
    except Exception:
        return room.room_code
