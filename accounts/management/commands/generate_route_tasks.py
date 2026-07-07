"""
Generate upcoming per-dumpster tasks from team routes.

Intended to run automatically every Sunday 00:01 (see docker/cron). For each
Site (Camp) with an active PlanGenerationConfig it generates the coming period's
tasks, honouring the weekly / bi-weekly cadence chosen by management.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import PlanGenerationConfig
from accounts.task_generation import generate_tasks_from_routes
from locations.models import Camp


class Command(BaseCommand):
    help = "Generate per-dumpster tasks from team routes for the upcoming period."

    def add_arguments(self, parser):
        parser.add_argument('--camp', type=str, default=None,
                            help="Limit to a single Site by code or id")
        parser.add_argument('--days', type=int, default=None,
                            help="Override horizon (days ahead) instead of cadence default")
        parser.add_argument('--start', type=str, default=None,
                            help="Start date YYYY-MM-DD (default: today)")
        parser.add_argument('--force', action='store_true',
                            help="Generate even if this is not a bi-weekly generation week")

    def handle(self, *args, **opts):
        today = timezone.localdate()
        start = today
        if opts.get('start'):
            start = timezone.datetime.strptime(opts['start'], '%Y-%m-%d').date()

        camps = Camp.objects.filter(is_active=True)
        if opts.get('camp'):
            key = opts['camp']
            camps = camps.filter(code=key) if not key.isdigit() else camps.filter(id=key)

        total_created = total_updated = 0
        for camp in camps:
            config, _ = PlanGenerationConfig.objects.get_or_create(camp=camp)
            if not config.is_active:
                self.stdout.write(f"skip {camp.name}: plan generation disabled")
                continue
            if not opts.get('force') and not config.is_generation_week(today):
                self.stdout.write(f"skip {camp.name}: not a generation week ({config.get_cadence_display()})")
                continue

            horizon = opts['days'] if opts.get('days') is not None else config.horizon_days
            end = start + timedelta(days=horizon - 1)
            result = generate_tasks_from_routes(camp, start, end, logger_=self.stdout.write)
            total_created += result['created']
            total_updated += result['updated']
            config.last_generated_on = today
            config.save(update_fields=['last_generated_on', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f"Done. {total_created} tasks created, {total_updated} reassigned."
        ))
