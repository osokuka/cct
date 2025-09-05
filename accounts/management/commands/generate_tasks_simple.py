"""
Simple task generation command using existing room data.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from locations.models import Room, Camp
from accounts.task_generation import TaskGenerationService, DailyCleaningTask

class Command(BaseCommand):
    help = 'Generate tasks from existing room data based on SLA requirements'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--camp-id',
            type=str,
            help='Camp ID to generate tasks for (if not provided, shows available camps)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to generate tasks for (default: 7)'
        )
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Preview tasks without creating them'
        )
    
    def handle(self, *args, **options):
        # Show available camps and rooms
        camps = Camp.objects.filter(is_active=True)
        self.stdout.write("Available Camps:")
        for camp in camps:
            room_count = Room.objects.filter(camp=camp, is_active=True).count()
            self.stdout.write(f"  {camp.name} ({camp.code}) - {room_count} rooms")
        
        if not camps.exists():
            self.stdout.write(self.style.ERROR("No active camps found. Create some rooms first."))
            return
        
        # If no camp specified, show room details
        if not options['camp_id']:
            self.stdout.write("\nRoom Details:")
            for camp in camps:
                self.stdout.write(f"\n{camp.name}:")
                rooms = Room.objects.filter(camp=camp, is_active=True)[:5]
                for room in rooms:
                    self.stdout.write(f"  {room.room_code}: {room.actual_sqm}m², {room.frequency_per_week}/week, {room.weekly_required_sqm}m² required")
                if Room.objects.filter(camp=camp, is_active=True).count() > 5:
                    remaining = Room.objects.filter(camp=camp, is_active=True).count() - 5
                    self.stdout.write(f"  ... and {remaining} more rooms")
            return
        
        # Generate tasks for specific camp
        try:
            camp = Camp.objects.get(id=options['camp_id'])
        except Camp.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Camp with ID '{options['camp_id']}' not found"))
            return
        
        # Check if camp has rooms
        rooms = Room.objects.filter(camp=camp, is_active=True)
        if not rooms.exists():
            self.stdout.write(self.style.ERROR(f"No active rooms found for camp {camp.name}"))
            return
        
        # Show room details
        self.stdout.write(f"\nGenerating tasks for {camp.name}:")
        self.stdout.write(f"Total rooms: {rooms.count()}")
        
        # Show SLA summary
        total_weekly_required = sum(room.weekly_required_sqm for room in rooms)
        total_monthly_cap = sum(room.monthly_cap_sqm for room in rooms)
        
        self.stdout.write(f"Weekly Required SQM: {total_weekly_required}")
        self.stdout.write(f"Monthly Cap SQM: {total_monthly_cap}")
        
        # Show room breakdown
        self.stdout.write("\nRoom Breakdown:")
        for room in rooms[:10]:  # Show first 10 rooms
            self.stdout.write(f"  {room.room_code}: {room.actual_sqm}m², {room.frequency_per_week}/week, {room.weekly_required_sqm}m² required")
        
        if rooms.count() > 10:
            self.stdout.write(f"  ... and {rooms.count() - 10} more rooms")
        
        # Generate tasks
        start_date = date.today()
        end_date = start_date + timedelta(days=options['days'] - 1)
        
        self.stdout.write(f"\nGenerating tasks from {start_date} to {end_date}")
        
        if options['preview']:
            self.stdout.write("PREVIEW MODE - No tasks will be created")
        
        # Use the task generation service
        service = TaskGenerationService(camp)
        results = service.generate_tasks_for_period(start_date, end_date, preview_only=options['preview'])
        
        # Show results
        self.stdout.write(f"\nResults:")
        self.stdout.write(f"  Rooms processed: {results['total_rooms']}")
        self.stdout.write(f"  Tasks created: {results['tasks_created']}")
        self.stdout.write(f"  Tasks updated: {results['tasks_updated']}")
        self.stdout.write(f"  Errors: {len(results['errors'])}")
        
        if results['errors']:
            self.stdout.write(self.style.WARNING("Errors:"))
            for error in results['errors']:
                self.stdout.write(f"  - {error}")
        
        # Show SLA summary
        sla = results['sla_summary']
        self.stdout.write(f"\nSLA Summary:")
        self.stdout.write(f"  Weekly Required SQM: {sla['total_weekly_required_sqm']}")
        self.stdout.write(f"  Monthly Cap SQM: {sla['total_monthly_cap_sqm']}")
        self.stdout.write(f"  Estimated Weekly Tasks: {sla['estimated_weekly_tasks']}")
        self.stdout.write(f"  Estimated Monthly Tasks: {sla['estimated_monthly_tasks']}")
        
        if not options['preview']:
            self.stdout.write(self.style.SUCCESS("Tasks generated successfully!"))
        else:
            self.stdout.write(self.style.WARNING("This was a preview - no tasks were created"))
