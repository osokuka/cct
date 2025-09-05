"""
Audit models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class AuditLog(models.Model):
    """
    Comprehensive audit logging for all user actions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    method = models.CharField(max_length=10, help_text="HTTP method")
    path = models.CharField(max_length=500, help_text="Request path")
    status_code = models.IntegerField(help_text="HTTP status code")
    latency_ms = models.IntegerField(help_text="Request latency in milliseconds")
    object_ref = models.CharField(max_length=500, blank=True, null=True, help_text="Object reference (e.g., 'User:123')")
    action = models.CharField(max_length=100, blank=True, null=True, help_text="Action performed")
    details = models.JSONField(default=dict, blank=True, help_text="Additional details")
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['status_code']),
        ]
    
    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'} - {self.method} {self.path} - {self.status_code}"