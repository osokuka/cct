"""
Task Generation System for NATO Camp Cleaning Tracker.

This module handles the generation of daily cleaning tasks based on the 
Sample_Acceptance_List.csv requirements and SLA calculations.
"""

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Optional
import uuid
import logging

logger = logging.getLogger(__name__)


class DailyCleaningTask(models.Model):
    """
    Daily cleaning task generated from room requirements.
    """
    TASK_STATE_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('missed', 'Missed'),
        ('re_clean_required', 'Re-clean Required'),
    ]
    
    TASK_TYPE_CHOICES = [
        ('regular', 'Regular'),
        ('requested', 'Requested'),
        ('urgent', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Room reference
    room = models.ForeignKey('locations.Room', on_delete=models.CASCADE, related_name='daily_tasks')
    
    # Task details
    task_date = models.DateField(help_text="Date for this cleaning task")
    index_in_day = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Index of this task within the day (1, 2, 3, etc.)"
    )
    task_type = models.CharField(
        max_length=20, 
        choices=TASK_TYPE_CHOICES, 
        default='regular',
        help_text="Type of cleaning task"
    )
    state = models.CharField(
        max_length=20, 
        choices=TASK_STATE_CHOICES, 
        default='planned',
        help_text="Current state of the task"
    )
    
    # Assignment
    shift = models.ForeignKey(
        'Shift',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_tasks',
        help_text="Shift assigned to this task"
    )
    assigned_to_team = models.ForeignKey(
        'Team', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_tasks',
        help_text="Team assigned to this task"
    )
    assigned_to_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_tasks',
        help_text="User assigned to this task (if individual assignment)"
    )
    
    # SLA tracking
    sla_credit_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="SLA credit earned for completing this task (in sqm)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    is_urgent = models.BooleanField(default=False, help_text="Is this an urgent task?")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes")
    
    class Meta:
        ordering = ['task_date', 'index_in_day', 'room__room_code']
        unique_together = ['room', 'task_date', 'index_in_day']
        verbose_name = "Daily Cleaning Task"
        verbose_name_plural = "Daily Cleaning Tasks"
    
    def __str__(self):
        return f"{self.room.room_code} - {self.task_date} ({self.get_state_display()})"
    
    def clean(self):
        """Validate task data."""
        if self.task_date and self.room:
            # Check if task is within service period
            if (self.room.service_start_date and self.task_date < self.room.service_start_date) or \
               (self.room.service_end_date and self.task_date > self.room.service_end_date):
                raise ValidationError("Task date must be within room service period")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        """Check if task is overdue based on camp cut-off time."""
        if self.state in ['done', 'missed']:
            return False
        
        camp = self.room.camp
        now = timezone.now()
        task_datetime = timezone.make_aware(
            datetime.combine(self.task_date, datetime.min.time())
        )
        
        # Calculate cut-off time for this task's date
        cutoff_datetime = task_datetime.replace(
            hour=camp.week_cutoff_hour,
            minute=0,
            second=0,
            microsecond=0
        )
        
        return now > cutoff_datetime


def generate_tasks_from_routes(camp, start_date: date, end_date: date, logger_=None):
    """
    Generate per-dumpster Tasks from each team's daily Routes for a date range.

    Corporate model: a Route = Team + weekday + a set of Streets. For every date
    in [start_date, end_date], for each route whose weekday matches, we create one
    Task per active dumpster on each of the route's streets, assigned to the
    route's team. Idempotent (get_or_create on room+date+index).
    """
    from .models import Route
    from locations.models import Room

    routes = (
        Route.objects.filter(team__camp=camp, is_active=True, weekday__isnull=False)
        .select_related('team', 'team__shift')
        .prefetch_related('streets')
    )
    by_weekday = {}
    for route in routes:
        by_weekday.setdefault(route.weekday, []).append(route)

    created = updated = 0
    current = start_date
    while current <= end_date:
        for route in by_weekday.get(current.weekday(), []):
            rooms = Room.objects.filter(
                building__in=route.streets.all(),
                space_type='dumpster',
                is_active=True,
            )
            for room in rooms:
                # Respect the room's service window when present.
                if room.service_start_date and current < room.service_start_date:
                    continue
                if room.service_end_date and current > room.service_end_date:
                    continue
                task, was_created = DailyCleaningTask.objects.get_or_create(
                    room=room,
                    task_date=current,
                    index_in_day=1,
                    defaults={
                        'sla_credit_sqm': room.actual_sqm or Decimal('1'),
                        'task_type': 'regular',
                        'state': 'planned',
                        'assigned_to_team': route.team,
                        'shift': route.team.shift,
                    },
                )
                if was_created:
                    created += 1
                elif task.assigned_to_team_id != route.team_id:
                    task.assigned_to_team = route.team
                    task.shift = route.team.shift
                    task.save(update_fields=['assigned_to_team', 'shift', 'updated_at'])
                    updated += 1
                if room.collection_weekday != current.weekday():
                    room.collection_weekday = current.weekday()
                    room.save(update_fields=['collection_weekday'])
        current += timedelta(days=1)

    if logger_:
        logger_(f"{camp.name}: {created} tasks created, {updated} reassigned "
                f"({start_date} → {end_date})")
    return {'created': created, 'updated': updated}


def generate_tasks_for_zone(zone, start_date: date, end_date: date):
    """Generate tasks for a single zone's dumpsters AND public-area rooms.

    Requires the zone to have both an assigned team and a collection weekday;
    otherwise nothing is generated. Idempotent.
    """
    from locations.models import Room

    team = zone.assigned_team
    wd = zone.collection_weekday
    if team is None or wd is None:
        return {'created': 0, 'updated': 0}

    rooms = list(
        Room.objects.filter(compound=zone, is_active=True).filter(
            models.Q(space_type='dumpster')
            | models.Q(space_type__in=Room.PUBLIC_AREA_TYPES)
        )
    )
    if not rooms:
        return {'created': 0, 'updated': 0}

    created = updated = 0
    current = start_date
    while current <= end_date:
        if current.weekday() == wd:
            for room in rooms:
                if room.service_start_date and current < room.service_start_date:
                    continue
                if room.service_end_date and current > room.service_end_date:
                    continue
                task, was_created = DailyCleaningTask.objects.get_or_create(
                    room=room,
                    task_date=current,
                    index_in_day=1,
                    defaults={
                        'sla_credit_sqm': room.actual_sqm or Decimal('1'),
                        'task_type': 'regular',
                        'state': 'planned',
                        'assigned_to_team': team,
                        'shift': team.shift,
                    },
                )
                if was_created:
                    created += 1
                elif task.assigned_to_team_id != team.id:
                    task.assigned_to_team = team
                    task.shift = team.shift
                    task.save(update_fields=['assigned_to_team', 'shift', 'updated_at'])
                    updated += 1
                if room.collection_weekday != wd:
                    room.collection_weekday = wd
                    room.save(update_fields=['collection_weekday'])
        current += timedelta(days=1)
    return {'created': created, 'updated': updated}


def generate_tasks_from_zones(start_date: date, end_date: date, camps=None, logger_=None):
    """
    Generate per-dumpster Tasks from Zone assignments for a date range.

    New corporate model: a Zone (Compound) is assigned a Team and a collection
    weekday on the Zone edit form. Every active dumpster inside that zone becomes
    a recurring task on the zone's weekday, assigned to the zone's team.

    Orphaned dumpsters — those with no zone, or in a zone without a team or without
    a collection day — are skipped (never generate tasks). Idempotent.
    """
    from locations.models import Compound, Room

    zones = (
        Compound.objects.filter(
            is_active=True,
            assigned_team__isnull=False,
            collection_weekday__isnull=False,
        )
        .select_related('assigned_team', 'assigned_team__shift', 'camp')
    )
    if camps is not None:
        zones = zones.filter(camp__in=camps)

    created = updated = 0
    for zone in zones:
        res = generate_tasks_for_zone(zone, start_date, end_date)
        created += res['created']
        updated += res['updated']

    # Count orphan dumpsters (for reporting only — never generated).
    orphans = Room.objects.filter(space_type='dumpster', is_active=True).filter(
        models.Q(compound__isnull=True)
        | models.Q(compound__assigned_team__isnull=True)
        | models.Q(compound__collection_weekday__isnull=True)
    )
    if camps is not None:
        orphans = orphans.filter(camp__in=camps)
    skipped_orphans = orphans.count()

    if logger_:
        logger_(f"{created} created, {updated} reassigned, "
                f"{skipped_orphans} orphan dumpsters skipped "
                f"({start_date} → {end_date})")
    return {'created': created, 'updated': updated, 'skipped_orphans': skipped_orphans}


class TaskGenerationService:
    """
    Service class for generating daily cleaning tasks based on room requirements.
    """
    
    def __init__(self, camp):
        self.camp = camp
        self.logger = logging.getLogger(f'{__name__}.{camp.code}')
    
    def generate_tasks_for_period(
        self, 
        start_date: date, 
        end_date: date,
        preview_only: bool = False
    ) -> Dict:
        """
        Generate tasks for a specific period.
        
        Args:
            start_date: Start date for task generation
            end_date: End date for task generation
            preview_only: If True, only return preview data without creating tasks
            
        Returns:
            Dict with generation results and statistics
        """
        self.logger.info(f"Generating tasks for {start_date} to {end_date} (preview: {preview_only})")
        
        # Get all active rooms in the camp
        rooms = self.camp.rooms.filter(
            is_active=True,
            service_start_date__lte=end_date,
            service_end_date__gte=start_date
        ).select_related('compound', 'building', 'floor')
        
        results = {
            'total_rooms': rooms.count(),
            'tasks_created': 0,
            'tasks_updated': 0,
            'errors': [],
            'room_details': [],
            'sla_summary': {
                'total_weekly_required_sqm': Decimal('0'),
                'total_monthly_cap_sqm': Decimal('0'),
                'estimated_weekly_tasks': 0,
                'estimated_monthly_tasks': 0
            }
        }
        
        for room in rooms:
            try:
                room_result = self._generate_tasks_for_room(
                    room, start_date, end_date, preview_only
                )
                results['room_details'].append(room_result)
                results['tasks_created'] += room_result['tasks_created']
                results['tasks_updated'] += room_result['tasks_updated']
                
                # Update SLA summary
                results['sla_summary']['total_weekly_required_sqm'] += room.weekly_required_sqm
                results['sla_summary']['total_monthly_cap_sqm'] += room.monthly_cap_sqm
                results['sla_summary']['estimated_weekly_tasks'] += room_result['weekly_tasks']
                results['sla_summary']['estimated_monthly_tasks'] += room_result['monthly_tasks']
                
            except Exception as e:
                error_msg = f"Error generating tasks for room {room.room_code}: {str(e)}"
                self.logger.error(error_msg)
                results['errors'].append(error_msg)
        
        self.logger.info(f"Task generation completed: {results['tasks_created']} created, {results['tasks_updated']} updated")
        return results
    
    def _generate_tasks_for_room(
        self, 
        room, 
        start_date: date, 
        end_date: date,
        preview_only: bool = False
    ) -> Dict:
        """Generate tasks for a specific room."""
        room_result = {
            'room_code': room.room_code,
            'room_description': room.room_description,
            'tasks_created': 0,
            'tasks_updated': 0,
            'weekly_tasks': 0,
            'monthly_tasks': 0,
            'task_dates': [],
            'errors': []
        }
        
        # Calculate task distribution
        if room.frequency_per_day > 0:
            # Daily frequency - distribute across shifts
            task_dates = self._distribute_daily_tasks(room, start_date, end_date)
        else:
            # Weekly frequency - distribute with 2-day spacing
            task_dates = self._distribute_weekly_tasks(room, start_date, end_date)
        
        room_result['weekly_tasks'] = len([d for d in task_dates if self._is_within_week(d, start_date)])
        room_result['monthly_tasks'] = len([d for d in task_dates if self._is_within_month(d, start_date)])
        room_result['task_dates'] = [d.isoformat() for d in task_dates]
        
        if not preview_only:
            # Create or update tasks
            for task_date in task_dates:
                for index_in_day in range(1, int(room.frequency_per_day) + 1):
                    task, created = DailyCleaningTask.objects.get_or_create(
                        room=room,
                        task_date=task_date,
                        index_in_day=index_in_day,
                        defaults={
                            'sla_credit_sqm': room.actual_sqm,
                            'task_type': 'regular',
                            'state': 'planned'
                        }
                    )
                    
                    if created:
                        room_result['tasks_created'] += 1
                    else:
                        room_result['tasks_updated'] += 1
        
        return room_result
    
    def _distribute_daily_tasks(self, room, start_date: date, end_date: date) -> List[date]:
        """Distribute daily tasks across different shifts."""
        task_dates = []
        current_date = start_date
        
        while current_date <= end_date:
            # Check if within service period
            if (room.service_start_date <= current_date <= room.service_end_date):
                # Add task for this date
                task_dates.append(current_date)
            
            current_date += timedelta(days=1)
        
        return task_dates
    
    def _distribute_weekly_tasks(self, room, start_date: date, end_date: date) -> List[date]:
        """Distribute weekly tasks with 2-day minimum spacing."""
        task_dates = []
        current_date = start_date
        
        # Calculate how many tasks we need for the period
        total_weeks = (end_date - start_date).days // 7
        tasks_needed = int(room.frequency_per_week * total_weeks)
        
        # Distribute tasks with 2-day spacing
        days_between_tasks = max(2, 7 // int(room.frequency_per_week))
        
        while current_date <= end_date and len(task_dates) < tasks_needed:
            # Check if within service period
            if (room.service_start_date <= current_date <= room.service_end_date):
                task_dates.append(current_date)
                current_date += timedelta(days=days_between_tasks)
            else:
                current_date += timedelta(days=1)
        
        return task_dates
    
    def _is_within_week(self, task_date: date, reference_date: date) -> bool:
        """Check if task date is within the same week as reference date."""
        week_start = reference_date - timedelta(days=reference_date.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start <= task_date <= week_end
    
    def _is_within_month(self, task_date: date, reference_date: date) -> bool:
        """Check if task date is within the same month as reference date."""
        return task_date.year == reference_date.year and task_date.month == reference_date.month
    
    def calculate_sla_metrics(self, start_date: date, end_date: date) -> Dict:
        """Calculate SLA metrics for the period."""
        # Get all tasks in the period
        tasks = DailyCleaningTask.objects.filter(
            room__camp=self.camp,
            task_date__gte=start_date,
            task_date__lte=end_date
        ).select_related('room')
        
        # Calculate metrics
        total_required_sqm = sum(task.room.weekly_required_sqm for task in tasks)
        total_completed_sqm = sum(
            task.sla_credit_sqm for task in tasks 
            if task.state == 'done'
        )
        total_missed_sqm = sum(
            task.sla_credit_sqm for task in tasks 
            if task.state == 'missed'
        )
        
        sla_percentage = (total_completed_sqm / total_required_sqm * 100) if total_required_sqm > 0 else 0
        
        return {
            'total_required_sqm': total_required_sqm,
            'total_completed_sqm': total_completed_sqm,
            'total_missed_sqm': total_missed_sqm,
            'sla_percentage': sla_percentage,
            'total_tasks': tasks.count(),
            'completed_tasks': tasks.filter(state='done').count(),
            'missed_tasks': tasks.filter(state='missed').count(),
            'planned_tasks': tasks.filter(state='planned').count()
        }
    
    def validate_room_requirements(self, room) -> List[str]:
        """Validate room requirements against SLA thresholds."""
        errors = []
        
        # Check weekly vs monthly frequency consistency
        if room.frequency_per_week > room.max_frequency_per_month:
            errors.append(f"Weekly frequency ({room.frequency_per_week}) exceeds monthly cap ({room.max_frequency_per_month})")
        
        # Check SLA calculation consistency (2% tolerance)
        expected_weekly_sqm = room.actual_sqm * room.frequency_per_week
        tolerance = expected_weekly_sqm * Decimal('0.02')
        if abs(room.weekly_required_sqm - expected_weekly_sqm) > tolerance:
            errors.append(f"Weekly required SQM ({room.weekly_required_sqm}) doesn't match calculation ({expected_weekly_sqm})")
        
        # Check monthly cap consistency
        expected_monthly_sqm = room.actual_sqm * room.max_frequency_per_month
        tolerance = expected_monthly_sqm * Decimal('0.02')
        if abs(room.monthly_cap_sqm - expected_monthly_sqm) > tolerance:
            errors.append(f"Monthly cap SQM ({room.monthly_cap_sqm}) doesn't match calculation ({expected_monthly_sqm})")
        
        return errors
