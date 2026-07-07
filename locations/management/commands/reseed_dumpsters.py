"""
Wipe all dumpsters and regenerate them ONLY inside zones that have a drawn
boundary ("preselected" zones). Dumpsters are placed along the zone's real
streets (OSM geometry) at a fixed spacing and are kept only when the point falls
inside the zone boundary polygon. Each dumpster inherits the zone's collection day.

Usage:
    python manage.py reseed_dumpsters                 # default spacing 90 m
    python manage.py reseed_dumpsters --spacing 120   # sparser
    python manage.py reseed_dumpsters --communal-every 5
    python manage.py reseed_dumpsters --keep          # don't delete existing first
"""

import json
import math
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from locations.models import Compound, Building, Floor, Room
from locations.geo import _ring_contains


def _m_per_deg_lng(lat):
    return 111320.0 * math.cos(math.radians(lat))


def _seg_len_m(p1, p2):
    """Length in meters of segment p1->p2 (each [lng, lat])."""
    mlat = 111130.0
    mlng = _m_per_deg_lng((p1[1] + p2[1]) / 2.0)
    dx = (p2[0] - p1[0]) * mlng
    dy = (p2[1] - p1[1]) * mlat
    return math.hypot(dx, dy)


def _iter_lines(geom):
    if not geom:
        return
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "LineString":
        yield coords
    elif gtype == "MultiLineString":
        for line in coords:
            yield line


def _points_along(line, spacing):
    """Yield (lng, lat) points sampled every ``spacing`` meters along a line."""
    if len(line) < 2:
        if line:
            yield line[0]
        return
    yield line[0]
    carry = 0.0
    for p1, p2 in zip(line, line[1:]):
        seg = _seg_len_m(p1, p2)
        if seg == 0:
            continue
        dist = spacing - carry
        while dist <= seg:
            t = dist / seg
            yield (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
            dist += spacing
        carry = (carry + seg) % spacing


def _dumpster_defaults():
    today = date.today()
    return {
        'space_type': 'dumpster',
        'square_meters': Decimal('1.00'),
        'quantity_of_rooms': 1,
        'actual_sqm': Decimal('1.00'),
        'frequency_per_day': Decimal('1'),
        'frequency_per_week': Decimal('6'),
        'max_frequency_per_month': 24,
        'weekly_required_sqm': Decimal('6'),
        'monthly_cap_sqm': Decimal('24'),
        'service_start_date': today,
        'service_end_date': today + timedelta(days=365),
        'weeks_of_service': 52,
    }


class Command(BaseCommand):
    help = "Wipe dumpsters and regenerate them only inside zones with a drawn boundary."

    def add_arguments(self, parser):
        parser.add_argument('--spacing', type=float, default=60.0,
                            help="Meters between dumpsters along a street (default 60).")
        parser.add_argument('--communal-every', type=int, default=6,
                            help="Every Nth dumpster is communal, the rest household (default 6).")
        parser.add_argument('--keep', action='store_true',
                            help="Do not delete existing dumpsters first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        spacing = opts['spacing']
        communal_every = max(1, opts['communal_every'])

        if not opts['keep']:
            deleted, _ = Room.objects.filter(space_type='dumpster').delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing dumpster records."))

        zones = (Compound.objects.filter(is_active=True)
                 .exclude(geo_polygon__isnull=True).exclude(geo_polygon="")
                 .select_related('camp'))

        total = 0
        seq_global = 0
        for zone in zones:
            ring = zone.boundary_ring
            if not ring:
                self.stdout.write(f"  {zone.code}: boundary present but unpar. skipping.")
                continue

            streets = list(zone.buildings.filter(is_active=True)
                           .exclude(geo_polyline__isnull=True).exclude(geo_polyline=""))
            if not streets:
                self.stdout.write(f"  {zone.code}: no streets with geometry. skipping.")
                continue

            zone_seq = 0
            for b in streets:
                try:
                    geom = json.loads(b.geo_polyline)
                except (ValueError, TypeError):
                    continue

                floor = (b.floors.filter(is_active=True).first()
                         or Floor.objects.create(building=b, code='A', name='Segment A'))

                for line in _iter_lines(geom):
                    for lng, lat in _points_along(line, spacing):
                        if not _ring_contains(lat, lng, ring):
                            continue
                        zone_seq += 1
                        seq_global += 1
                        dtype = 'communal' if (seq_global % communal_every == 0) else 'household'
                        room = Room(
                            camp=zone.camp,
                            compound=zone,
                            building=b,
                            floor=floor,
                            building_code=b.code[:20],
                            room_code=f"{zone.code}-D{zone_seq:04d}",
                            room_description=f"Dumpster — {b.name}",
                            latitude=Decimal(str(round(lat, 6))),
                            longitude=Decimal(str(round(lng, 6))),
                            dumpster_type=dtype,
                            collection_weekday=zone.collection_weekday,
                            is_active=True,
                        )
                        for k, v in _dumpster_defaults().items():
                            setattr(room, k, v)
                        room.save()
                        total += 1

            self.stdout.write(self.style.SUCCESS(
                f"  {zone.code} {zone.name}: {zone_seq} dumpsters placed inside boundary."))

        self.stdout.write(self.style.SUCCESS(f"Done. {total} dumpsters created across bounded zones."))
