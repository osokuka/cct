"""
Location models for the NATO Camp Cleaning Tracker.
Defines the camp hierarchy: Camp → Compound → Building → Floor → Room
and related entities like Shifts and cleaning schedules.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Camp(models.Model):
    """
    Top-level camp entity with policy configuration.
    Contains timezone and cut-off settings for roster generation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, help_text="Camp code (e.g., CAMP1)")
    name = models.CharField(max_length=200, help_text="Camp name")
    
    # Camp Policy Configuration
    timezone = models.CharField(
        max_length=50, 
        default='Europe/Berlin',
        help_text="Camp timezone (e.g., 'Europe/Berlin' for Kosovo/Prishtina)"
    )
    week_cutoff_day = models.IntegerField(
        default=4,  # Thursday
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Week cut-off day (0=Monday, 6=Sunday)"
    )
    week_cutoff_hour = models.IntegerField(
        default=18,  # 6 PM
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Week cut-off hour (0-23)"
    )
    month_cutoff_day = models.IntegerField(
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Month cut-off day (1-31)"
    )
    month_cutoff_hour = models.IntegerField(
        default=23,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Month cut-off hour (0-23)"
    )
    skip_holidays = models.BooleanField(
        default=True,
        help_text="Skip task generation on holidays"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['code']
        verbose_name = "Camp"
        verbose_name_plural = "Camps"
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Compound(models.Model):
    """
    Compound within a camp (e.g., Danish, German contingent).
    Used for multi-tenant data scoping.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='compounds')
    code = models.CharField(max_length=50, help_text="Compound code (e.g., DANISH)")
    name = models.CharField(max_length=200, help_text="Compound name")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['camp', 'code']
        unique_together = [['camp', 'code']]
        verbose_name = "Compound"
        verbose_name_plural = "Compounds"
    
    def __str__(self):
        return f"{self.camp.code}-{self.code} - {self.name}"


class Building(models.Model):
    """
    Building within a compound.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='buildings')
    code = models.CharField(max_length=50, help_text="Building code (e.g., BLDG-A)")
    name = models.CharField(max_length=200, help_text="Building name")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['compound', 'code']
        unique_together = [['compound', 'code']]
        verbose_name = "Building"
        verbose_name_plural = "Buildings"
    
    def __str__(self):
        return f"{self.compound.camp.code}-{self.compound.code}-{self.code} - {self.name}"


class Floor(models.Model):
    """
    Floor within a building.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    code = models.CharField(max_length=50, help_text="Floor code (e.g., FL1)")
    name = models.CharField(max_length=200, help_text="Floor name")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['building', 'code']
        unique_together = [['building', 'code']]
        verbose_name = "Floor"
        verbose_name_plural = "Floors"
    
    def __str__(self):
        return f"{self.building.compound.camp.code}-{self.building.compound.code}-{self.building.code}-{self.code} - {self.name}"


class Shift(models.Model):
    """
    Cleaning shifts defined per camp.
    Used for roster generation and task assignment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=100, help_text="Shift name (e.g., Morning, Evening)")
    start_time = models.TimeField(help_text="Shift start time")
    end_time = models.TimeField(help_text="Shift end time")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['camp', 'start_time']
        unique_together = [['camp', 'name']]
        verbose_name = "Shift"
        verbose_name_plural = "Shifts"
    
    def __str__(self):
        return f"{self.camp.code} - {self.name} ({self.start_time}-{self.end_time})"


class Room(models.Model):
    """
    Room within a floor.
    Contains cleaning frequency configuration and barcode data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='rooms')
    code = models.CharField(max_length=50, help_text="Room code (e.g., RM101)")
    name = models.CharField(max_length=200, help_text="Room name")
    sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Room area in square meters"
    )
    is_active = models.BooleanField(default=True, help_text="Is room active for cleaning")
    
    # Barcode data
    barcode_data = models.CharField(
        max_length=200, 
        unique=True, 
        blank=True, 
        null=True,
        help_text="Generated barcode data for room identification"
    )
    
    # Cleaning frequency configuration
    frequency_per_day = models.PositiveIntegerField(
        default=1,
        help_text="Number of required cleans per day"
    )
    frequency_per_week = models.PositiveIntegerField(
        default=7,
        help_text="Number of required cleans per week"
    )
    time_window_start = models.TimeField(
        blank=True, 
        null=True,
        help_text="Preferred cleaning time window start"
    )
    time_window_end = models.TimeField(
        blank=True, 
        null=True,
        help_text="Preferred cleaning time window end"
    )
    shift_binding = models.ForeignKey(
        Shift, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        help_text="Required shift for this room (optional)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['floor', 'code']
        unique_together = [['floor', 'code']]
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        indexes = [
            models.Index(fields=['barcode_data']),
        ]
    
    def __str__(self):
        return f"{self.floor.building.compound.camp.code}-{self.floor.building.compound.code}-{self.floor.building.code}-{self.floor.code}-{self.code} - {self.name}"
    
    @property
    def full_hierarchy_path(self):
        """Return the full hierarchy path for this room."""
        return f"{self.floor.building.compound.camp.code}-{self.floor.building.compound.code}-{self.floor.building.code}-{self.floor.code}-{self.code}"
    
    def generate_barcode_data(self):
        """Generate barcode data for this room."""
        self.barcode_data = self.full_hierarchy_path
        return self.barcode_data
    
    def save(self, *args, **kwargs):
        # Auto-generate barcode data if not provided
        if not self.barcode_data:
            self.generate_barcode_data()
        super().save(*args, **kwargs)