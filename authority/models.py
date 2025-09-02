"""
Authority models for the NATO Camp Cleaning Tracker.
Defines re-clean requests and urgent cleaning requests from contracting authorities.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from locations.models import Room


class RecleanRequest(models.Model):
    """
    Re-clean requests from contracting authorities.
    Creates extra PLANNED tasks for the same day (or next if past cut-off).
    """
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reclean_requests')
    requested_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='requested_recleans',
        help_text="Contracting authority user who requested re-clean"
    )
    reason = models.TextField(help_text="Reason for re-clean request")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='open',
        help_text="Current status of the request"
    )
    resolved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='resolved_recleans',
        help_text="Admin/Supervisor who resolved the request"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Re-clean Request"
        verbose_name_plural = "Re-clean Requests"
        indexes = [
            models.Index(fields=['room', 'status']),
            models.Index(fields=['requested_by', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Re-clean: {self.room} by {self.requested_by.get_full_name()} - {self.get_status_display()}"
    
    def resolve(self, resolved_by_user):
        """Mark request as resolved."""
        self.status = 'resolved'
        self.resolved_by = resolved_by_user
        self.resolved_at = timezone.now()
        self.save()
        
        # Create extra PLANNED task for re-cleaning
        from scans.models import DailyCleaningTask
        from datetime import date
        
        # Create task for today or tomorrow if past cut-off
        task_date = date.today()
        # TODO: Check camp cut-off time to determine if we should schedule for tomorrow
        
        # Find the next available index for this room/date
        existing_tasks = DailyCleaningTask.objects.filter(
            room=self.room, 
            date=task_date
        ).count()
        
        DailyCleaningTask.objects.create(
            room=self.room,
            date=task_date,
            index_in_day=existing_tasks + 1,
            state='planned'
        )


class UrgentCleaningRequest(models.Model):
    """
    Urgent cleaning requests from contracting authorities.
    Creates high-priority tasks that appear at top of cleaning queue.
    """
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('critical', 'Critical'),
        ('emergency', 'Emergency'),
    ]
    
    STATUS_CHOICES = [
        ('urgent_requested', 'Urgent Requested'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='urgent_requests')
    requested_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='requested_urgent_cleans',
        help_text="Contracting authority user who requested urgent cleaning"
    )
    reason = models.TextField(help_text="Reason for urgent cleaning request")
    priority_level = models.CharField(
        max_length=20, 
        choices=PRIORITY_CHOICES, 
        default='high',
        help_text="Priority level of the urgent request"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='urgent_requested',
        help_text="Current status of the urgent request"
    )
    assigned_to = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_urgent_cleans',
        help_text="Cleaner assigned to this urgent request"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Escalation tracking
    escalation_sent = models.BooleanField(default=False)
    escalation_sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-priority_level', '-created_at']
        verbose_name = "Urgent Cleaning Request"
        verbose_name_plural = "Urgent Cleaning Requests"
        indexes = [
            models.Index(fields=['room', 'status']),
            models.Index(fields=['requested_by', 'created_at']),
            models.Index(fields=['status', 'priority_level']),
            models.Index(fields=['assigned_to', 'status']),
        ]
    
    def __str__(self):
        return f"Urgent {self.get_priority_level_display()}: {self.room} by {self.requested_by.get_full_name()}"
    
    def assign_to_cleaner(self, cleaner_user):
        """Assign urgent request to a cleaner."""
        self.assigned_to = cleaner_user
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save()
        
        # Create urgent daily task
        from scans.models import DailyCleaningTask
        from datetime import date
        
        task_date = date.today()
        existing_tasks = DailyCleaningTask.objects.filter(
            room=self.room, 
            date=task_date
        ).count()
        
        urgent_task = DailyCleaningTask.objects.create(
            room=self.room,
            date=task_date,
            index_in_day=existing_tasks + 1,
            state='planned',
            assigned_to=cleaner_user
        )
        
        return urgent_task
    
    def mark_completed(self):
        """Mark urgent request as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def check_escalation(self):
        """
        Check if this urgent request needs escalation.
        Should be called by a background task.
        """
        if self.status == 'urgent_requested' and not self.escalation_sent:
            # Check if request is overdue based on priority
            time_thresholds = {
                'emergency': 30,  # 30 minutes
                'critical': 60,   # 1 hour
                'high': 120,      # 2 hours
            }
            
            threshold_minutes = time_thresholds.get(self.priority_level, 120)
            time_elapsed = timezone.now() - self.created_at
            
            if time_elapsed.total_seconds() > (threshold_minutes * 60):
                self.escalation_sent = True
                self.escalation_sent_at = timezone.now()
                self.save()
                
                # TODO: Send escalation notification to supervisors
                return True
        
        return False