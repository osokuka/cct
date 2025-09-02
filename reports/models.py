"""
Report models for the NATO Camp Cleaning Tracker.
Defines report templates and scheduled reports.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from locations.models import Camp, Compound


class ReportTemplate(models.Model):
    """
    Predefined report templates for different types of reports.
    """
    REPORT_TYPE_CHOICES = [
        ('daily_cleaning', 'Daily Cleaning Report'),
        ('weekly_summary', 'Weekly Summary Report'),
        ('monthly_sla', 'Monthly SLA Report'),
        ('roster_status', 'Roster Status Report'),
        ('audit_summary', 'Audit Summary Report'),
        ('custom', 'Custom Report'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Report template name")
    description = models.TextField(blank=True, help_text="Report description")
    report_type = models.CharField(
        max_length=50, 
        choices=REPORT_TYPE_CHOICES,
        help_text="Type of report"
    )
    
    # Report configuration
    camp = models.ForeignKey(
        Camp, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Camp this template is for (null for global templates)"
    )
    compound = models.ForeignKey(
        Compound, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Compound this template is for (null for camp-wide templates)"
    )
    
    # Report parameters
    parameters = models.JSONField(
        default=dict,
        help_text="Report parameters and filters"
    )
    
    # Access control
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='created_report_templates'
    )
    is_public = models.BooleanField(
        default=False,
        help_text="Can other users use this template"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Report Template"
        verbose_name_plural = "Report Templates"
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class ScheduledReport(models.Model):
    """
    Scheduled reports that run automatically.
    """
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Scheduled report name")
    template = models.ForeignKey(
        ReportTemplate, 
        on_delete=models.CASCADE,
        related_name='scheduled_reports'
    )
    
    # Scheduling
    frequency = models.CharField(
        max_length=20, 
        choices=FREQUENCY_CHOICES,
        help_text="How often to run the report"
    )
    day_of_week = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Day of week (0=Monday, 6=Sunday) for weekly reports"
    )
    day_of_month = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day of month for monthly reports"
    )
    time_of_day = models.TimeField(
        default=timezone.now().time(),
        help_text="Time of day to run the report"
    )
    
    # Recipients
    recipients = models.JSONField(
        default=list,
        help_text="List of email addresses to send reports to"
    )
    
    # Status
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='active'
    )
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    # Access control
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='created_scheduled_reports'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Scheduled Report"
        verbose_name_plural = "Scheduled Reports"
    
    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"


class ReportExecution(models.Model):
    """
    Track individual report executions.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scheduled_report = models.ForeignKey(
        ScheduledReport, 
        on_delete=models.CASCADE,
        null=True, 
        blank=True,
        related_name='executions'
    )
    template = models.ForeignKey(
        ReportTemplate, 
        on_delete=models.CASCADE,
        related_name='executions'
    )
    
    # Execution details
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Results
    record_count = models.IntegerField(null=True, blank=True)
    file_path = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Path to the generated report file"
    )
    file_size_bytes = models.BigIntegerField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True, null=True)
    error_traceback = models.TextField(blank=True, null=True)
    
    # Parameters used
    parameters_used = models.JSONField(
        default=dict,
        help_text="Parameters used for this execution"
    )
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = "Report Execution"
        verbose_name_plural = "Report Executions"
    
    def __str__(self):
        return f"Report execution {self.id} - {self.get_status_display()}"
    
    def mark_completed(self, file_path=None, record_count=None, file_size=None):
        """Mark report execution as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        
        if file_path:
            self.file_path = file_path
        if record_count is not None:
            self.record_count = record_count
        if file_size is not None:
            self.file_size_bytes = file_size
        
        self.save()
    
    def mark_failed(self, error_message, error_traceback=None):
        """Mark report execution as failed."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.error_message = error_message
        self.error_traceback = error_traceback
        self.save()