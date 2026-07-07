"""
Lightweight background execution for zone street population.

There is no Celery/broker in this deployment, so the OSM population job runs in a
daemon thread. Progress is persisted on the ``Compound`` (osm_status/osm_message/
osm_last_synced_at/osm_street_count) so the UI can poll for completion, and the
same entry point is reused by the ``populate_zone_streets`` management command.
"""

import logging
import threading

from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_zone_population(compound_id, replace=False):
    """Run the OSM population synchronously, persisting status on the Compound."""
    from .models import Compound
    from .osm import populate_zone_streets, OverpassError

    try:
        compound = Compound.objects.get(pk=compound_id)
    except Compound.DoesNotExist:
        logger.warning("run_zone_population: compound %s not found", compound_id)
        return

    Compound.objects.filter(pk=compound_id).update(
        osm_status="running", osm_message="Fetching streets from OpenStreetMap…"
    )
    try:
        result = populate_zone_streets(compound, replace=replace)
        msg = (
            f"Populated {result['total']} streets "
            f"({result['created']} new, {result['updated']} updated)."
        )
        Compound.objects.filter(pk=compound_id).update(
            osm_status="done",
            osm_message=msg,
            osm_last_synced_at=timezone.now(),
            osm_street_count=result["total"],
        )
        logger.info("Zone %s populated: %s", compound_id, msg)
    except (ValueError, OverpassError) as exc:
        Compound.objects.filter(pk=compound_id).update(
            osm_status="error", osm_message=str(exc)
        )
        logger.warning("Zone %s population failed: %s", compound_id, exc)
    except Exception as exc:  # noqa: BLE001 - surface unexpected errors to the UI
        Compound.objects.filter(pk=compound_id).update(
            osm_status="error", osm_message=f"Unexpected error: {exc}"
        )
        logger.exception("Zone %s population crashed", compound_id)


def _threaded_run(compound_id, replace):
    try:
        run_zone_population(compound_id, replace=replace)
    finally:
        # Threads get their own DB connection; close it so it isn't leaked.
        connection.close()


def start_zone_population(compound_id, replace=False):
    """Mark the zone queued and kick off population in a background daemon thread."""
    from .models import Compound

    Compound.objects.filter(pk=compound_id).update(
        osm_status="queued", osm_message="Queued…"
    )
    thread = threading.Thread(
        target=_threaded_run, args=(compound_id, replace), daemon=True
    )
    thread.start()
    return thread
