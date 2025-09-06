"""
Django management command for daily task maintenance.
This command handles end-of-day task processing including:
- Marking past due tasks as missed
- Generating next day's tasks (if needed)
- Sending notifications (future enhancement)
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from accounts.task_generation import DailyCleaningTask
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Daily task maintenance - mark missed tasks and perform end-of-day processing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--mark-missed',
            action='store_true',
            default=True,
            help='Mark past due tasks as missed (default: True)',
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=1,
            help='Number of days back to check for missed tasks (default: 1)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        mark_missed = options['mark_missed']
        days_back = options['days_back']
        
        today = timezone.now().date()
        self.stdout.write(f"Daily Task Maintenance - {today}")
        self.stdout.write("=" * 50)
        
        if mark_missed:
            self.mark_missed_tasks(today, days_back, dry_run)
        
        # Future enhancements can be added here:
        # - Generate next day's tasks
        # - Send daily reports
        # - Clean up old data
        # - Send notifications
        
        self.stdout.write("\nDaily maintenance completed successfully!")

    def mark_missed_tasks(self, today, days_back, dry_run):
        """Mark past due tasks as missed"""
        cutoff_date = today - timedelta(days=days_back)
        
        self.stdout.write(f"\n1. Marking missed tasks (before {cutoff_date})")
        
        # Find tasks that should be marked as missed
        tasks_to_update = DailyCleaningTask.objects.filter(
            state='planned',
            task_date__lte=cutoff_date
        ).exclude(
            state__in=['done', 'missed']
        )
        
        total_tasks = tasks_to_update.count()
        
        if total_tasks == 0:
            self.stdout.write("   ✓ No tasks need to be marked as missed.")
            return
        
        # Group by date for reporting
        tasks_by_date = {}
        for task in tasks_to_update:
            date_str = task.task_date.strftime('%Y-%m-%d')
            if date_str not in tasks_by_date:
                tasks_by_date[date_str] = []
            tasks_by_date[date_str].append(task)
        
        # Show what will be updated
        self.stdout.write(f"   Found {total_tasks} tasks to mark as missed:")
        for date_str in sorted(tasks_by_date.keys()):
            tasks_count = len(tasks_by_date[date_str])
            self.stdout.write(f"     {date_str}: {tasks_count} tasks")
        
        if dry_run:
            self.stdout.write(f"   DRY RUN: Would update {total_tasks} tasks to 'missed' state")
            return
        
        # Update the tasks
        updated_count = tasks_to_update.update(state='missed')
        
        self.stdout.write(f"   ✓ Successfully marked {updated_count} tasks as missed.")
        
        # Show summary by compound
        compound_summary = {}
        for task in tasks_to_update:
            compound_name = task.room.compound.name
            if compound_name not in compound_summary:
                compound_summary[compound_name] = 0
            compound_summary[compound_name] += 1
        
        if compound_summary:
            self.stdout.write("   Summary by compound:")
            for compound_name, count in sorted(compound_summary.items()):
                self.stdout.write(f"     {compound_name}: {count} tasks")
        
        # Log the action
        logger.info(f"Marked {updated_count} tasks as missed on {today}")
