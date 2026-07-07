"""
Operations Manager dashboard + TV monitoring wall for Gjakova.

- /operations/       working dashboard (map + teams + live ops)
- /operations/tv/    full-screen TV wall (map + routes on the left, live team
                     progress feed on the right, auto-refreshing)
- /operations/data/  JSON feed powering both pages
"""

import json
from datetime import datetime, time as dtime

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.views import check_permission
from accounts.models import Team, Route
from accounts.task_generation import DailyCleaningTask
from locations.models import Camp, Room, OperationsConfig

from .map_views import center_from_rooms, build_map_features, map_counts

_OPS_ROLES = ["admin", "manager", "operations_manager"]

# Palette for team colours (cycled).
_ROUTE_COLORS = [
    "#2563eb", "#16a34a", "#d97706", "#db2777",
    "#0891b2", "#7c3aed", "#dc2626", "#65a30d",
]

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_polyline(geojson_str):
    """GeoJSON (Multi)LineString [lng,lat] -> list of [[lat,lng],...] segments."""
    if not geojson_str:
        return []
    try:
        g = json.loads(geojson_str)
    except (ValueError, TypeError):
        return []
    gtype = g.get("type")
    if gtype == "MultiLineString":
        return [[[lat, lng] for lng, lat in seg] for seg in g.get("coordinates", [])]
    if gtype == "LineString":
        return [[[lat, lng] for lng, lat in g.get("coordinates", [])]]
    return []


def _scoped_camps(request):
    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)
    if role == "admin":
        return Camp.objects.filter(is_active=True)
    camp = getattr(profile, "camp", None)
    return Camp.objects.filter(is_active=True, id=camp.id) if camp else Camp.objects.none()


def _scoped_center(request):
    """Data-driven map center from the user's scoped Site points."""
    rooms = Room.objects.filter(
        is_active=True, camp__in=_scoped_camps(request)
    ).only("latitude", "longitude")
    return center_from_rooms(rooms)


@login_required
def operations_dashboard(request):
    if not check_permission(request, _OPS_ROLES):
        return redirect("accounts:login")
    return render(request, "dashboard/operations_dashboard.html", {
        "center": _scoped_center(request),
    })


@login_required
def operations_tv(request):
    if not check_permission(request, _OPS_ROLES):
        return redirect("accounts:login")
    return render(request, "dashboard/operations_tv.html", {
        "center": _scoped_center(request),
    })


@login_required
def operations_settings(request):
    """Global operations settings, incl. the optional payment-tracking toggle."""
    if not check_permission(request, ["admin", "manager", "operations_manager"]):
        return redirect("accounts:login")

    config = OperationsConfig.get_solo()
    if request.method == "POST":
        config.payment_tracking_enabled = request.POST.get("payment_tracking_enabled") == "on"
        config.save()
        from django.contrib import messages
        messages.success(
            request,
            "Payment tracking " + ("enabled." if config.payment_tracking_enabled
                                   else "disabled — all points are collected and billed monthly."),
        )
        return redirect("dashboard:operations_settings")

    return render(request, "dashboard/operations_settings.html", {"config": config})


@login_required
def operations_data(request):
    if not check_permission(request, _OPS_ROLES):
        return JsonResponse({"error": "forbidden"}, status=403)

    camps = list(_scoped_camps(request))
    today = timezone.localdate()

    # -- selected date ----------------------------------------------------
    date_str = request.GET.get("date")
    try:
        sel_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else today
    except (ValueError, TypeError):
        sel_date = today
    is_today = sel_date == today
    is_past = sel_date < today
    is_future = sel_date > today
    plan_day = sel_date.weekday()          # 0=Mon..6=Sun (collection scheduled Mon-Fri)
    is_working_day = plan_day <= 4
    past_dt = timezone.make_aware(datetime.combine(sel_date, dtime(12, 0)))

    rooms = list(
        Room.objects.filter(is_active=True, camp__in=camps).select_related(
            "client", "compound", "building"
        )
    )

    teams = list(
        Team.objects.filter(is_active=True, camp__in=camps)
        .select_related("shift")
        .prefetch_related("members")
    )
    team_color = {t.id: _ROUTE_COLORS[i % len(_ROUTE_COLORS)] for i, t in enumerate(teams)}
    team_color_str = {str(k): v for k, v in team_color.items()}

    # Collection is planned per Street per weekday via Routes: a Street (Building)
    # is serviced by the route's team on the route's weekday.
    street_team = {}       # building_id -> Team (collection)
    street_weekday = {}    # building_id -> weekday (0..6)
    for route in Route.objects.filter(
        team__camp__in=camps, is_active=True, weekday__isnull=False,
        team__team_type="collection",
    ).select_related("team").prefetch_related("streets"):
        for b in route.streets.all():
            street_team[b.id] = route.team
            street_weekday[b.id] = route.weekday

    # Cleaning teams cover Zones (compounds); public areas are always shown.
    compound_team = {"collection": {}, "cleaning": {}}
    for route in Route.objects.filter(
        team__camp__in=camps, is_active=True
    ).select_related("team").prefetch_related("compounds"):
        for comp in route.compounds.all():
            compound_team[route.team.team_type][comp.id] = route.team

    # Live task state exists for TODAY only. Past days are treated as fully
    # serviced; future days can never have completed work.
    room_state = {}
    room_completed = {}
    if is_today:
        for task in DailyCleaningTask.objects.filter(
            task_date=today, room__camp__in=camps
        ).only("room_id", "state", "completed_at"):
            room_state[task.room_id] = task.state
            room_completed[task.room_id] = task.completed_at

    # -- per-team aggregation --------------------------------------------
    stats = {t.id: {"done": 0, "in_progress": 0, "planned": 0, "missed": 0,
                    "total": 0, "last": None} for t in teams}
    unassigned = {"done": 0, "in_progress": 0, "planned": 0, "missed": 0, "total": 0}
    feed_events = []

    def _bump(team, state, when=None):
        bucket = stats.get(team.id) if team else unassigned
        if bucket is None:
            bucket = unassigned
        bucket["total"] += 1
        bucket[state] = bucket.get(state, 0) + 1
        if team and when is not None and bucket is not unassigned:
            if bucket["last"] is None or when > bucket["last"]:
                bucket["last"] = when

    def _feed(team, r, state, when):
        if state in ("done", "in_progress"):
            feed_events.append({
                "time": (when or timezone.now()).isoformat(),
                "team": team.name if team else "Unassigned",
                "team_type": team.team_type if team else None,
                "room_code": r.room_code,
                "space_type": r.space_type,
                "is_dumpster": r.space_type == "dumpster",
                "street": r.building.name if r.building_id else None,
                "state": state,
            })

    # -- dumpsters (dots) + per-street route aggregation -------------------
    dumpsters = []
    street_agg = {}          # building_id -> aggregate dict
    building_geo = {}        # building_id -> parsed segments

    for r in rooms:
        if r.space_type != "dumpster" or r.latitude is None or r.longitude is None:
            continue
        # A dumpster is scheduled on the selected day if its Street belongs to a
        # collection route running on that weekday.
        if street_weekday.get(r.building_id) != plan_day:
            continue
        client = r.client
        team = street_team.get(r.building_id)
        can_collect = r.can_collect

        if is_today:
            st = room_state.get(r.id)
            if st == "done":
                status, state = "collected", "done"
            elif not can_collect:
                status, state = "skip", "planned"
            elif st == "in_progress":
                status, state = "awaiting", "in_progress"
            else:
                status, state = "awaiting", "planned"
            completed = room_completed.get(r.id)
            last_collected = completed or r.last_collected_at
            when = completed
        elif is_past:
            # Past day: collectable points were serviced; unpaid were skipped.
            if can_collect:
                status, state, last_collected, when = "collected", "done", past_dt, past_dt
            else:
                status, state, last_collected, when = "skip", "planned", r.last_collected_at, None
        else:
            # Future day: nothing can be completed yet.
            status = "awaiting" if can_collect else "skip"
            state = "planned"
            last_collected = r.last_collected_at
            when = None

        _bump(team, state, when)
        _feed(team, r, state, when)

        dumpsters.append({
            "id": str(r.id),
            "dumpster_id": r.room_code,
            "dumpster_type": r.dumpster_type or "household",
            "dumpster_type_label": r.dumpster_type_label,
            "client_id": client.client_code if client else None,
            "payment_status": client.payment_status if client else "unknown",
            "payment_label": client.get_payment_status_display() if client else "No client / unconfirmed",
            "paid": bool(client and client.payment_status in ("paid", "exempt")),
            "can_collect": can_collect,
            "status": status,
            "weekday": r.collection_weekday,
            "last_collected": last_collected.isoformat() if last_collected else None,
            "lat": float(r.latitude),
            "lng": float(r.longitude),
            "street": r.building.name if r.building_id else None,
            "street_code": r.building.code if r.building_id else None,
            "team_id": str(team.id) if team else None,
        })

        if team is not None and r.building_id:
            agg = street_agg.get(r.building_id)
            if agg is None:
                if r.building_id not in building_geo:
                    building_geo[r.building_id] = _parse_polyline(r.building.geo_polyline)
                agg = street_agg[r.building_id] = {
                    "team_id": team.id,
                    "street_code": r.building.code,
                    "street_name": r.building.name,
                    "total": 0, "collected": 0, "awaiting": 0, "skip": 0,
                    "segments": building_geo[r.building_id],
                    "lats": [], "lngs": [],
                }
            agg["total"] += 1
            agg[status] += 1
            agg["lats"].append(float(r.latitude))
            agg["lngs"].append(float(r.longitude))

    # group street aggregates by team
    streets_by_team = {}
    for agg in street_agg.values():
        streets_by_team.setdefault(agg["team_id"], []).append(agg)

    # -- public areas (dots only, green when collected) -------------------
    public_areas = []
    for r in rooms:
        if r.space_type not in Room.PUBLIC_AREA_TYPES or r.latitude is None or r.longitude is None:
            continue
        cteam = compound_team["cleaning"].get(r.compound_id)
        if is_today:
            st = room_state.get(r.id)
            status = "collected" if st == "done" else "awaiting"
            state = st if st in ("done", "in_progress", "planned") else "planned"
            when = room_completed.get(r.id)
        elif is_past:
            status, state, when = "collected", "done", past_dt
        else:
            status, state, when = "awaiting", "planned", None
        _bump(cteam, state, when)
        _feed(cteam, r, state, when)
        public_areas.append({
            "id": str(r.id),
            "name": r.room_description or r.room_code,
            "space_type": r.space_type,
            "space_type_label": r.get_space_type_display(),
            "sqm": float(r.actual_sqm or 0),
            "status": status,
            "lat": float(r.latitude),
            "lng": float(r.longitude),
            "team_id": str(cteam.id) if cteam else None,
        })

    # -- weekly plan (per team, dumpsters per weekday) --------------------
    weekly = {}   # team_id -> {weekday: count}
    for r in rooms:
        if r.space_type != "dumpster":
            continue
        team = street_team.get(r.building_id)
        wd = street_weekday.get(r.building_id)
        if not team or wd is None:
            continue
        weekly.setdefault(team.id, {}).setdefault(wd, 0)
        weekly[team.id][wd] += 1

    teams_payload = []
    for t in teams:
        s = stats[t.id]
        total = s["total"]
        pct = round((s["done"] / total * 100) if total else 0, 1)
        # today's route streets (collection teams only), sorted by name
        route_streets = sorted(
            streets_by_team.get(t.id, []),
            key=lambda a: a["street_name"],
        )
        streets_payload = [{
            "street_code": a["street_code"],
            "street_name": a["street_name"],
            "total": a["total"],
            "collected": a["collected"],
            "awaiting": a["awaiting"],
            "skip": a["skip"],
            "segments": a["segments"],
        } for a in route_streets]
        weekly_plan = {str(k): v for k, v in sorted(weekly.get(t.id, {}).items())}
        teams_payload.append({
            "id": str(t.id),
            "name": t.name,
            "team_type": t.team_type,
            "team_type_label": t.get_team_type_display(),
            "color": team_color[t.id],
            "shift": t.shift.name if t.shift_id else None,
            "members": t.employee_count,
            "total": total,
            "done": s["done"],
            "in_progress": s["in_progress"],
            "planned": s["planned"],
            "missed": s["missed"],
            "percent": pct,
            "last_activity": s["last"].isoformat() if s["last"] else None,
            "streets": streets_payload,
            "weekly_plan": weekly_plan,
        })
    teams_payload.sort(key=lambda x: (x["team_type"] != "collection", x["name"]))
    # Stable "Team 1/2/3" numbering for collection teams (for route labels).
    _n = 0
    for tp in teams_payload:
        if tp["team_type"] == "collection":
            _n += 1
            tp["team_no"] = _n
        else:
            tp["team_no"] = None

    # attach team colour to dumpster dots for optional highlighting
    for d in dumpsters:
        d["color"] = team_color_str.get(d["team_id"], "#888")

    # -- activity feed ----------------------------------------------------
    feed_events.sort(key=lambda e: e["time"], reverse=True)
    activity = feed_events[:30]

    # -- totals by stream (derived from per-team stats) -------------------
    def stream_totals(is_collection):
        total = done = in_progress = 0
        for t in teams:
            if (t.team_type == "collection") == is_collection:
                s = stats[t.id]
                total += s["total"]
                done += s["done"]
                in_progress += s["in_progress"]
        return {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "percent": round((done / total * 100) if total else 0, 1),
        }

    totals = {
        "collection": stream_totals(True),
        "cleaning": stream_totals(False),
    }

    return JsonResponse({
        "generated_at": timezone.now().isoformat(),
        "center": center_from_rooms(rooms),
        "date": sel_date.isoformat(),
        "today": today.isoformat(),
        "is_today": is_today,
        "is_past": is_past,
        "is_future": is_future,
        "is_working_day": is_working_day,
        "plan_day": plan_day,
        "plan_day_label": _WEEKDAYS[plan_day],
        "weekday_labels": _WEEKDAYS,
        "payment_tracking": OperationsConfig.payment_tracking_on(),
        "dumpsters": dumpsters,
        "public_areas": public_areas,
        "counts": {
            "dumpsters": len(dumpsters),
            "collected": sum(1 for d in dumpsters if d["status"] == "collected"),
            "awaiting": sum(1 for d in dumpsters if d["status"] == "awaiting"),
            "skip": sum(1 for d in dumpsters if d["status"] == "skip"),
            "public_areas": len(public_areas),
        },
        "teams": teams_payload,
        "unassigned": unassigned,
        "activity": activity,
        "totals": totals,
    })
