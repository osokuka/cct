"""
Audit models for the NATO Camp Cleaning Tracker.
Defines audit logging for security and compliance tracking.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class AuditLog(models.Model):
    """
    Comprehensive audit log for all user actions and system events.
    Captures user, IP, method, path, status, latency, and object references.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # User information
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='audit_logs',
        help_text="User who performed the action (null for anonymous)"
    )
    
    # Request information
    ip_address = models.GenericIPAddressField(
        null=True, 
        blank=True,
        help_text="IP address of the request"
    )
    user_agent = models.TextField(
        blank=True, 
        null=True,
        help_text="User agent string from the request"
    )
    method = models.CharField(
        max_length=10,
        help_text="HTTP method (GET, POST, PUT, DELETE, etc.)"
    )
    path = models.CharField(
        max_length=500,
        help_text="Request path/URL"
    )
    
    # Response information
    status_code = models.IntegerField(
        help_text="HTTP status code of the response"
    )
    latency_ms = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Request latency in milliseconds"
    )
    
    # Action details
    action = models.CharField(
        max_length=100,
        help_text="Action performed (e.g., 'login', 'scan_room', 'export_report')"
    )
    object_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Type of object affected (e.g., 'Room', 'ScanEvent', 'User')"
    )
    object_id = models.CharField(
        max_length=100,
        blank=True, 
        null=True,
        help_text="ID of the object affected"
    )
    object_ref = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Human-readable reference to the object"
    )
    
    # Additional context
    request_data = models.JSONField(
        blank=True, 
        null=True,
        help_text="Request data (excluding sensitive information)"
    )
    response_data = models.JSONField(
        blank=True, 
        null=True,
        help_text="Response data (excluding sensitive information)"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if the request failed"
    )
    
    # Metadata
    session_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Django session key"
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        help_text="When the action occurred"
    )
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['method', 'path']),
            models.Index(fields=['status_code', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        user_str = self.user.get_full_name() if self.user else "Anonymous"
        return f"{user_str} - {self.method} {self.path} - {self.status_code} - {self.timestamp}"
    
    @classmethod
    def log_action(cls, request, action, status_code, latency_ms=None, 
                   object_type=None, object_id=None, object_ref=None,
                   request_data=None, response_data=None, error_message=None):
        """
        Convenience method to log an action.
        """
        # Extract user information
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            user = user
        else:
            user = None
        
        # Extract request information
        ip_address = cls._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        method = request.method
        path = request.path
        session_key = request.session.session_key
        
        # Clean request data (remove sensitive information)
        if request_data is None:
            request_data = cls._clean_request_data(request)
        
        return cls.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_ref=object_ref,
            request_data=request_data,
            response_data=response_data,
            error_message=error_message,
            session_key=session_key,
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def _clean_request_data(request):
        """Clean request data to remove sensitive information."""
        sensitive_fields = ['password', 'token', 'secret', 'key', 'auth']
        
        if request.method == 'GET':
            data = dict(request.GET)
        else:
            try:
                data = dict(request.POST)
            except:
                data = {}
        
        # Remove sensitive fields
        cleaned_data = {}
        for key, value in data.items():
            if not any(sensitive in key.lower() for sensitive in sensitive_fields):
                cleaned_data[key] = value
        
        return cleaned_data if cleaned_data else None


class AuditLogExport(models.Model):
    """
    Track audit log exports for compliance and security.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exported_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='audit_exports'
    )
    export_type = models.CharField(
        max_length=50,
        help_text="Type of export (CSV, PDF, etc.)"
    )
    filters_applied = models.JSONField(
        help_text="Filters that were applied to the export"
    )
    record_count = models.IntegerField(
        help_text="Number of records exported"
    )
    file_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Path to the exported file"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Log Export"
        verbose_name_plural = "Audit Log Exports"
    
    def __str__(self):
        return f"Export by {self.exported_by.get_full_name()} - {self.record_count} records - {self.created_at}"