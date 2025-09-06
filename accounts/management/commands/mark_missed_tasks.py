"""
Django management command to mark past due tasks as missed.
This command should be run daily (e.g., via cron job) to automatically
update task states from 'planned' to 'missed' for tasks that are past due.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from accounts.task_generation import DailyCleaningTask
from datetime import timedelta


class Command(BaseCommand):
    help = 'Mark past due tasks as missed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=1,
            help='Number of days back to check for missed tasks (default: 1)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days_back = options['days_back']
        
        # Calculate the cutoff date
        today = timezone.now().date()
        cutoff_date = today - timedelta(days=days_back)
        
        self.stdout.write(f"Checking for missed tasks before {cutoff_date}")
        
        # Find tasks that should be marked as missed
        # These are tasks that are:
        # 1. Still in 'planned' state
        # 2. Have a task_date on or before the cutoff date
        # 3. Are not already marked as 'done' or 'missed'
        tasks_to_update = DailyCleaningTask.objects.filter(
            state='planned',
            task_date__lte=cutoff_date
        ).exclude(
            state__in=['done', 'missed']
        )
        
        total_tasks = tasks_to_update.count()
        
        if total_tasks == 0:
            self.stdout.write(
                self.style.SUCCESS('No tasks need to be marked as missed.')
            )
            return
        
        # Group by date for reporting
        tasks_by_date = {}
        for task in tasks_to_update:
            date_str = task.task_date.strftime('%Y-%m-%d')
            if date_str not in tasks_by_date:
                tasks_by_date[date_str] = []
            tasks_by_date[date_str].append(task)
        
        # Show what will be updated
        self.stdout.write(f"\nFound {total_tasks} tasks to mark as missed:")
        for date_str in sorted(tasks_by_date.keys()):
            tasks_count = len(tasks_by_date[date_str])
            self.stdout.write(f"  {date_str}: {tasks_count} tasks")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'\nDRY RUN: Would update {total_tasks} tasks to "missed" state')
            )
            return
        
        # Confirm the update
        confirm = input(f"\nAre you sure you want to mark {total_tasks} tasks as missed? (y/N): ")
        if confirm.lower() != 'y':
            self.stdout.write('Operation cancelled.')
            return
        
        # Update the tasks
        updated_count = tasks_to_update.update(state='missed')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully marked {updated_count} tasks as missed.'
            )
        )
        
        # Show summary by compound
        self.stdout.write("\nSummary by compound:")
        compound_summary = {}
        for task in tasks_to_update:
            compound_name = task.room.compound.name
            if compound_name not in compound_summary:
                compound_summary[compound_name] = 0
            compound_summary[compound_name] += 1
        
        for compound_name, count in sorted(compound_summary.items()):
            self.stdout.write(f"  {compound_name}: {count} tasks")
