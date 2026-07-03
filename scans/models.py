"""
Scan models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from accounts.task_generation import DailyCleaningTask
import uuid

class ScanEvent(models.Model):
    SCAN_TYPE_CHOICES = [
        ('CLEANED', 'Cleaned'),
        ('RECLEANED', 'Recleaned'),
        ('URGENT_CLEAN', 'Urgent Clean'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey('locations.Room', on_delete=models.CASCADE, related_name='scan_events')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scan_events')
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, default='CLEANED')
    device_id = models.CharField(max_length=200, blank=True, null=True)
    barcode_scanned = models.CharField(max_length=200, blank=True, null=True)
    is_urgent = models.BooleanField(default=False)
    daily_task = models.ForeignKey(DailyCleaningTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='scan_events')
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['room', 'timestamp']),
        ]

    def __str__(self):
        return f"Scan: {self.room.room_code} by {self.user.username} at {self.timestamp}"