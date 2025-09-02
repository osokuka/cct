"""
Scan models for the NATO Camp Cleaning Tracker.
Defines scan events and daily cleaning tasks for roster management.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from locations.models import Room, Shift


class DailyCleaningTask(models.Model):
    """
    Daily cleaning tasks generated from room frequencies.
    Represents the roster of cleaning work to be done.
    """
    STATE_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('missed', 'Missed'),
        ('re_clean_required', 'Re-clean Required'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='daily_tasks')
    date = models.DateField(help_text="Date for this cleaning task")
    index_in_day = models.PositiveIntegerField(
        default=1,
        help_text="Task index for the day (1st, 2nd, 3rd cleaning of the day)"
    )
    shift = models.ForeignKey(
        Shift, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Assigned shift for this task"
    )
    state = models.CharField(
        max_length=20, 
        choices=STATE_CHOICES, 
        default='planned',
        help_text="Current state of the task"
    )
    assigned_to = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_tasks',
        help_text="User assigned to this task"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['date', 'shift__start_time', 'index_in_day']
        unique_together = [['room', 'date', 'index_in_day']]
        verbose_name = "Daily Cleaning Task"
        verbose_name_plural = "Daily Cleaning Tasks"
        indexes = [
            models.Index(fields=['date', 'state']),
            models.Index(fields=['assigned_to', 'date']),
            models.Index(fields=['room', 'date']),
        ]
    
    def __str__(self):
        return f"{self.room} - {self.date} (#{self.index_in_day}) - {self.get_state_display()}"
    
    def mark_in_progress(self, user=None):
        """Mark task as in progress."""
        self.state = 'in_progress'
        self.started_at = timezone.now()
        if user:
            self.assigned_to = user
        self.save()
    
    def mark_done(self):
        """Mark task as completed."""
        self.state = 'done'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_missed(self):
        """Mark task as missed."""
        self.state = 'missed'
        self.save()
    
    def mark_re_clean_required(self):
        """Mark task as requiring re-cleaning."""
        self.state = 're_clean_required'
        self.save()


class ScanEvent(models.Model):
    """
    Scan events recorded when cleaners scan room barcodes.
    Links to daily cleaning tasks for state management.
    """
    SCAN_TYPE_CHOICES = [
        ('cleaned', 'Cleaned'),
        ('recleaned', 'Re-cleaned'),
        ('urgent_clean', 'Urgent Clean'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='scan_events')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scan_events')
    daily_task = models.ForeignKey(
        DailyCleaningTask, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='scan_events',
        help_text="Associated daily cleaning task"
    )
    
    scan_type = models.CharField(
        max_length=20, 
        choices=SCAN_TYPE_CHOICES,
        help_text="Type of scan event"
    )
    device_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Device identifier used for scanning"
    )
    barcode_scanned = models.CharField(
        max_length=200,
        help_text="Barcode data that was scanned"
    )
    is_urgent = models.BooleanField(
        default=False,
        help_text="Is this an urgent cleaning request"
    )
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Scan Event"
        verbose_name_plural = "Scan Events"
        indexes = [
            models.Index(fields=['room', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.room} - {self.get_scan_type_display()} - {self.timestamp}"
    
    def save(self, *args, **kwargs):
        # Update associated daily task state
        if self.daily_task and self.scan_type in ['cleaned', 'recleaned']:
            if self.daily_task.state == 'planned':
                self.daily_task.mark_in_progress(self.user)
            elif self.daily_task.state == 'in_progress':
                self.daily_task.mark_done()
        
        super().save(*args, **kwargs)


class ScanEventDuplicate(models.Model):
    """
    Track potential duplicate scan events to prevent spam.
    Used for validation in the scan API.
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    barcode_scanned = models.CharField(max_length=200)
    
    class Meta:
        unique_together = [['room', 'user', 'timestamp']]
        indexes = [
            models.Index(fields=['room', 'user', 'timestamp']),
        ]
    
    def __str__(self):
        return f"Duplicate check: {self.user} - {self.room} - {self.timestamp}"