"""
Seed the Gjakova demo dataset from real OpenStreetMap geometry + a weekly plan.

Data source: `data/gjakova_osm.json` (produced by `data/build_gjakova_osm.py`).
It contains real drivable streets (with road geometry + collection points spaced
~80 m apart and a weekly-plan assignment: team 0..2, day 0..5) and town-wide
public areas.

Model mapping:
  * Camp     -> Municipality (GJ)
  * Compound -> collection zone (Z1/Z2/Z3, one per team) + 2 public-area zones (N/S)
  * Building -> street (with geo_polyline road geometry) / "Public areas"
  * Room     -> dumpster (collection, weekday-scheduled) or public area (cleaning)

Collection: 3 non-overlapping zones, <= 50 points/team/day, whole area covered weekly.
Cleaning: public areas, no routes (shown green when collected).

Idempotent: wipes previous GJ seed data first. Run inside Docker:
    docker compose exec web python manage.py seed_gjakova
"""

import json
import os
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.task_generation import DailyCleaningTask
from locations.models import (
    Camp, Compound, Building, Floor, Room, CollectionClient,
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "gjakova_osm.json")

SERVICE_START = date(2026, 1, 1)
SERVICE_END = date(2026, 12, 31)

PAYMENT_CYCLE = ["paid", "paid", "unpaid", "paid", "overdue", "exempt", "paid", "unpaid"]

# Collection zones (one per team) — teams never cross each other's roads.
ZONES = {
    0: ("Z1", "Zona 1 — Ekipi A"),
    1: ("Z2", "Zona 2 — Ekipi B"),
    2: ("Z3", "Zona 3 — Ekipi C"),
}
# Public-area cleaning zones (north/south) — no routes, serviced daily.
PUB = {
    "N": ("PUBN", "Hapësirat publike — Veri"),
    "S": ("PUBS", "Hapësirat publike — Jug"),
}


class Command(BaseCommand):
    help = "Seed Gjakova from OSM: 3 collection zones (weekly plan) + town-wide public areas."

    def add_arguments(self, parser):
        parser.add_argument("--camp-code", default="GJ")

    @transaction.atomic
    def handle(self, *args, **options):
        if not os.path.exists(DATA_FILE):
            self.stderr.write("Missing data/gjakova_osm.json — run data/build_gjakova_osm.py first.")
            return

        with open(DATA_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        self.center = data["center"]

        camp = self._reset_camp(options["camp_code"])
        zones, pub = self._seed_compounds(camp)
        d_count = self._seed_dumpsters(camp, zones, data["streets"])
        a_count = self._seed_public_areas(camp, pub, data["public_areas"])

        self.stdout.write(self.style.SUCCESS("Gjakova OSM data seeded."))
        self.stdout.write(
            f"  Zone centre: {self.center['lat']:.5f}, {self.center['lng']:.5f} "
            f"(r={data.get('zone_radius_m')} m, {data.get('num_teams')} teams, "
            f"{data.get('streets_per_day')} streets/team/day, Mon-Fri)"
        )
        self.stdout.write(
            f"  Streets: {len(data['streets'])} | Dumpsters: {d_count} | "
            f"Public areas: {a_count} | Clients: {CollectionClient.objects.count()}"
        )

    # -- wipe + base -------------------------------------------------------

    def _reset_camp(self, code):
        camp, _ = Camp.objects.get_or_create(
            code=code, defaults={"name": "Komuna e Gjakovës", "timezone": "Europe/Belgrade"}
        )
        DailyCleaningTask.objects.filter(room__camp=camp).delete()
        Room.objects.filter(camp=camp).delete()
        CollectionClient.objects.all().delete()
        Floor.objects.filter(building__compound__camp=camp).delete()
        Building.objects.filter(compound__camp=camp).delete()
        Compound.objects.filter(camp=camp).delete()
        camp.name = "Komuna e Gjakovës"
        camp.timezone = "Europe/Belgrade"
        camp.save()
        return camp

    def _seed_compounds(self, camp):
        zones = {
            t: Compound.objects.create(camp=camp, code=code, name=name)
            for t, (code, name) in ZONES.items()
        }
        pub = {
            key: Compound.objects.create(camp=camp, code=code, name=name)
            for key, (code, name) in PUB.items()
        }
        return zones, pub

    # -- dumpsters ---------------------------------------------------------

    def _dumpster_defaults(self):
        return {
            "space_type": "dumpster",
            "square_meters": Decimal("1.00"),
            "quantity_of_rooms": 1,
            "actual_sqm": Decimal("1.00"),
            "frequency_per_day": Decimal("1"),
            "frequency_per_week": Decimal("6"),
            "max_frequency_per_month": 24,
            "weekly_required_sqm": Decimal("6"),
            "monthly_cap_sqm": Decimal("24"),
            "service_start_date": SERVICE_START,
            "service_end_date": SERVICE_END,
            "weeks_of_service": 52,
            "is_active": True,
        }

    def _seed_dumpsters(self, camp, zones, streets):
        today = timezone.localdate()
        last_week = timezone.now() - timedelta(days=7)
        pay_i = 0
        client_seq = 1
        total = 0

        for street in streets:
            points = street.get("points", [])
            if not points:
                continue
            compound = zones[street["team"]]

            geojson = json.dumps({
                "type": "MultiLineString",
                "coordinates": [
                    [[lng, lat] for lat, lng in seg] for seg in street.get("segments", [])
                ],
            })
            building = Building.objects.create(
                compound=compound, code=street["code"][:50], name=street["name"][:200],
                geo_polyline=geojson,
            )
            floor = Floor.objects.create(building=building, code="A", name="Segment A")

            for n, pt in enumerate(points, start=1):
                lat, lng = pt[0], pt[1]
                day = int(pt[2]) if pt[2] is not None else None
                status = PAYMENT_CYCLE[pay_i % len(PAYMENT_CYCLE)]
                pay_i += 1
                paid_until = None
                if status == "paid":
                    paid_until = today + timedelta(days=180)
                elif status == "overdue":
                    paid_until = today - timedelta(days=20)

                client = CollectionClient.objects.create(
                    client_code=f"GJ-CL-{client_seq:05d}",
                    compound=compound, payment_status=status, paid_until=paid_until,
                    internal_note="Demo client (seed_gjakova / OSM)",
                )
                client_seq += 1

                Room.objects.create(
                    camp=camp, compound=compound, building=building, floor=floor,
                    room_code=f"{street['code']}-{n:03d}"[:100],
                    building_code=street["code"][:20],
                    room_description=f"Kontejner {n} — {street['name']}",
                    latitude=Decimal(str(lat)), longitude=Decimal(str(lng)),
                    client=client, collection_weekday=day, last_collected_at=last_week,
                    **self._dumpster_defaults(),
                )
                total += 1
        return total

    # -- public areas (town-wide, north/south) -----------------------------

    def _seed_public_areas(self, camp, pub, areas):
        buildings, floors = {}, {}

        def area_building(key):
            if key not in buildings:
                b = Building.objects.create(
                    compound=pub[key], code="AREAS", name="Public areas (town)"
                )
                buildings[key] = b
                floors[key] = Floor.objects.create(building=b, code="A", name="Areas")
            return buildings[key], floors[key]

        total = 0
        for a in areas:
            key = "N" if a["lat"] >= self.center["lat"] else "S"
            compound = pub[key]
            building, floor = area_building(key)
            sqm = Decimal(str(a["sqm"]))
            freq = Decimal("5") if a["space_type"] == "city_center" else Decimal("3")
            weekly = (sqm * freq).quantize(Decimal("0.01"))
            Room.objects.create(
                camp=camp, compound=compound, building=building, floor=floor,
                room_code=a["code"][:100], building_code=a["code"][:20],
                space_type=a["space_type"], room_description=a["name"][:500],
                square_meters=sqm, quantity_of_rooms=1, actual_sqm=sqm,
                frequency_per_day=Decimal("1"), frequency_per_week=freq,
                max_frequency_per_month=max(1, int(round(float(freq) * 4))),
                weekly_required_sqm=weekly,
                monthly_cap_sqm=(weekly * 4).quantize(Decimal("0.01")),
                service_start_date=SERVICE_START, service_end_date=SERVICE_END,
                weeks_of_service=52,
                latitude=Decimal(str(a["lat"])), longitude=Decimal(str(a["lng"])),
                is_active=True,
            )
            total += 1
        return total
