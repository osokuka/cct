"""
Operations map views for Gjakova.

Renders an interactive Leaflet map of the municipality showing:
  * public-area cleaning sites (SQM/SLA) as blue areas, and
  * garbage-collection points (dumpsters) as dots coloured by whether the billing
    client has paid (green = collect, red = do not collect / confirm).

Client identity is anonymized: only an opaque client code and payment status are
exposed, never a name.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect

from accounts.views import check_permission
from locations.models import Camp, Room


# Gjakova operations focus area (WGS84) — collection zone, ~1.5 km radius.
GJAKOVA_CENTER = {"lat": 42.37092943416372, "lng": 20.435394872814765, "zoom": 15}

_ALLOWED_ROLES = ["admin", "manager", "operations_manager", "cleaner", "authority"]


def _scoped_rooms(request):
    """Return active rooms scoped to the user's camp (admins see all)."""
    rooms = Room.objects.filter(is_active=True).select_related(
        "client", "compound", "building", "floor", "camp"
    )
    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)
    if role != "admin":
        camp = getattr(profile, "camp", None)
        if camp is not None:
            rooms = rooms.filter(camp=camp)
        else:
            rooms = rooms.none()
    return rooms


@login_required
def collection_map(request):
    """Render the operations map page."""
    if not check_permission(request, _ALLOWED_ROLES):
        return redirect("accounts:login")
    context = {
        "center": GJAKOVA_CENTER,
        "data_url": "collection_map_data",
    }
    return render(request, "dashboard/collection_map.html", context)


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


@login_required
def collection_map_data(request):
    """Return map features as JSON (dumpsters + public areas)."""
    if not check_permission(request, _ALLOWED_ROLES):
        return JsonResponse({"error": "forbidden"}, status=403)

    rooms = _scoped_rooms(request)
    dumpsters, public_areas = build_map_features(rooms)

    return JsonResponse({
        "center": GJAKOVA_CENTER,
        "dumpsters": dumpsters,
        "public_areas": public_areas,
        "counts": map_counts(dumpsters, public_areas),
    })


def _safe_barcode(room):
    try:
        return room.generate_barcode_data()
    except Exception:
        return room.room_code
