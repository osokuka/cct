"""
Location models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid


class Camp(models.Model):
    """
    Top-level camp entity with timezone and policy settings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, help_text="Unique camp code")
    name = models.CharField(max_length=200, help_text="Camp name")
    timezone = models.CharField(max_length=50, default='Europe/Berlin', help_text="Camp timezone")
    week_cutoff_day = models.IntegerField(
        default=6, 
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Week cutoff day (0=Monday, 6=Sunday)"
    )
    week_cutoff_hour = models.IntegerField(
        default=23,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Week cutoff hour (0-23)"
    )
    month_cutoff_day = models.IntegerField(
        default=31,
        validators=[MinValueValidator(0), MaxValueValidator(31)],
        help_text="Month cutoff day (0=End of Month, 1-31=specific day)"
    )
    month_cutoff_hour = models.IntegerField(
        default=23,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Month cutoff hour (0-23)"
    )
    skip_holidays = models.BooleanField(default=True, help_text="Skip holidays in scheduling")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Camp"
        verbose_name_plural = "Camps"

    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this camp."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Compound(models.Model):
    """
    Compound within a camp.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='compounds')
    code = models.CharField(max_length=50, help_text="Compound code")
    name = models.CharField(max_length=200, help_text="Compound name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['camp', 'code']
        verbose_name = "Compound"
        verbose_name_plural = "Compounds"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.camp.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this compound."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Building(models.Model):
    """
    Building within a compound.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='buildings')
    code = models.CharField(max_length=50, help_text="Building code")
    name = models.CharField(max_length=200, help_text="Building name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['compound', 'code']
        verbose_name = "Building"
        verbose_name_plural = "Buildings"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.compound.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this building."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Floor(models.Model):
    """
    Floor within a building.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    code = models.CharField(max_length=50, help_text="Floor code")
    name = models.CharField(max_length=200, help_text="Floor name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['building', 'code']
        verbose_name = "Floor"
        verbose_name_plural = "Floors"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.building.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms on this floor."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Room(models.Model):
    """
    Room/Area within a floor - the smallest unit for cleaning tasks.
    """
    SPACE_TYPE_CHOICES = [
        ('room', 'Room'),
        ('office', 'Office'),
        ('meeting_room', 'Meeting Room'),
        ('corridor', 'Corridor'),
        ('laundry_room', 'Laundry Room'),
        ('toilet', 'Toilet'),
        ('balcony', 'Balcony'),
        ('front_yard', 'Front Yard'),
        ('garage', 'Garage'),
        ('container', 'Container'),
        ('mwa', 'MWA'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Location hierarchy
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='rooms')
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='rooms')
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='rooms')
    
    # Basic information
    room_code = models.CharField(max_length=100, help_text="Room code/identifier")
    room_description = models.TextField(blank=True, null=True, help_text="Room description")
    space_type = models.CharField(max_length=50, choices=SPACE_TYPE_CHOICES, help_text="Type of space")
    building_code = models.CharField(max_length=20, help_text="Building code reference")
    
    # Physical properties
    square_meters = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Square meters (m²)"
    )
    quantity_of_rooms = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantity of rooms"
    )
    actual_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Actual Sqm (m2) for SLA calculations"
    )
    
    # Cleaning schedule
    frequency_per_day = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Frequency Per Day"
    )
    frequency_per_week = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Frequency Per Week"
    )
    max_frequency_per_month = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Max Frequency Per Month"
    )
    
    # SLA calculations
    weekly_required_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total m² Week"
    )
    monthly_cap_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="EoM Invoicing max. Sqm (m2)"
    )
    
    # Service period
    service_start_date = models.DateField(help_text="Start Date")
    service_end_date = models.DateField(help_text="End Date")
    weeks_of_service = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="# Weeks of service"
    )
    
    # Custom field (named by Admin/Manager)
    custom_field_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Custom field name (set by Admin/Manager)"
    )
    custom_field_value = models.TextField(
        blank=True, 
        null=True,
        help_text="Custom field value"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room_code']
        unique_together = ['floor', 'room_code']
        verbose_name = "Room"
        verbose_name_plural = "Rooms"

    def __str__(self):
        return f"{self.room_code} - {self.room_description or 'No description'}"

    def clean(self):
        """
        Business logic validation.
        """
        from django.core.exceptions import ValidationError
        
        # Date validation
        if self.service_start_date and self.service_end_date:
            if self.service_start_date > self.service_end_date:
                raise ValidationError("Start Date must be before or equal to End Date")
        
        # Frequency validation
        if self.frequency_per_week and self.max_frequency_per_month:
            if self.frequency_per_week > self.max_frequency_per_month:
                raise ValidationError("Frequency per week cannot exceed max frequency per month")
        
        # Area validation
        if self.actual_sqm and self.square_meters:
            if self.actual_sqm > self.square_meters:
                raise ValidationError("Actual Sqm cannot exceed Square Meters")
        
        # SLA validation (with tolerance)
        if self.actual_sqm and self.frequency_per_week and self.weekly_required_sqm:
            expected_weekly_sqm = self.actual_sqm * self.frequency_per_week
            tolerance = expected_weekly_sqm * Decimal('0.02')  # 2% tolerance
            if abs(self.weekly_required_sqm - expected_weekly_sqm) > tolerance:
                raise ValidationError(
                    f"Weekly required Sqm ({self.weekly_required_sqm}) should be approximately "
                    f"Actual Sqm × Frequency Per Week ({expected_weekly_sqm})"
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)