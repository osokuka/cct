"""
Authority models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class RecleanRequest(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('RESOLVED', 'Resolved'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey('locations.Room', on_delete=models.CASCADE, related_name='reclean_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reclean_requests')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_reclean_requests')
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Re-clean: {self.room.room_code} - {self.status}"