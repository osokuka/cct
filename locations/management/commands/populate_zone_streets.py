"""
Populate a zone's streets from OpenStreetMap (synchronously).

Shares the same service as the UI's async button, so it can be used for manual
runs, scripting, or a scheduled job. Example:

    docker compose exec web python manage.py populate_zone_streets --zone <uuid>
    docker compose exec web python manage.py populate_zone_streets --all --replace
"""

from django.core.management.base import BaseCommand, CommandError

from locations.models import Compound
from locations.tasks import run_zone_population


class Command(BaseCommand):
    help = "Populate zone (Compound) streets from OpenStreetMap within its boundary."

    def add_arguments(self, parser):
        parser.add_argument("--zone", help="Compound (zone) UUID to populate")
        parser.add_argument(
            "--all", action="store_true",
            help="Populate every active zone that has a boundary",
        )
        parser.add_argument(
            "--replace", action="store_true",
            help="Deactivate streets no longer returned by OSM (default: merge)",
        )

    def handle(self, *args, **options):
        replace = options["replace"]

        if options["all"]:
            zones = Compound.objects.filter(is_active=True).exclude(geo_polygon__isnull=True).exclude(geo_polygon="")
            if not zones:
                self.stdout.write("No zones with a boundary to populate.")
                return
            for zone in zones:
                self.stdout.write(f"Populating {zone.name}…")
                run_zone_population(zone.pk, replace=replace)
                zone.refresh_from_db()
                self.stdout.write(self.style.SUCCESS(f"  {zone.osm_status}: {zone.osm_message}"))
            return

        zone_id = options["zone"]
        if not zone_id:
            raise CommandError("Provide --zone <uuid> or --all.")
        try:
            zone = Compound.objects.get(pk=zone_id)
        except Compound.DoesNotExist:
            raise CommandError(f"Zone {zone_id} not found.")

        self.stdout.write(f"Populating {zone.name}…")
        run_zone_population(zone.pk, replace=replace)
        zone.refresh_from_db()
        style = self.style.SUCCESS if zone.osm_status == "done" else self.style.ERROR
        self.stdout.write(style(f"{zone.osm_status}: {zone.osm_message}"))
