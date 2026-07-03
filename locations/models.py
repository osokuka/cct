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
    
    # Additional SQM quota for urgent cleaning requests
    monthly_urgent_sqm_quota = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monthly SQM quota for urgent cleaning requests (optional)"
    )
    weekly_urgent_sqm_quota = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Weekly SQM quota for urgent cleaning requests (optional)"
    )
    
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
    
    @property
    def has_urgent_sqm_quota(self):
        """Check if compound has any urgent SQM quota allocated."""
        return self.monthly_urgent_sqm_quota is not None or self.weekly_urgent_sqm_quota is not None
    
    @property
    def urgent_sqm_quota_display(self):
        """Get formatted urgent SQM quota display string."""
        if not self.has_urgent_sqm_quota:
            return "No urgent SQM quota allocated"
        
        parts = []
        if self.monthly_urgent_sqm_quota:
            parts.append(f"Monthly: {self.monthly_urgent_sqm_quota:,.2f} m²")
        if self.weekly_urgent_sqm_quota:
            parts.append(f"Weekly: {self.weekly_urgent_sqm_quota:,.2f} m²")
        
        return " | ".join(parts)
    
    def get_urgent_sqm_quota_for_period(self, period_type='monthly'):
        """Get urgent SQM quota amount for specific period type."""
        if period_type == 'monthly':
            return self.monthly_urgent_sqm_quota
        elif period_type == 'weekly':
            return self.weekly_urgent_sqm_quota
        return None
    
    def get_remaining_urgent_sqm_quota(self, period_type='monthly', used_sqm=0):
        """Calculate remaining urgent SQM quota after usage."""
        quota = self.get_urgent_sqm_quota_for_period(period_type)
        if not quota:
            return None
        
        remaining = quota - used_sqm
        return max(remaining, 0)  # Don't go below 0
    
    def can_allocate_urgent_sqm(self, requested_sqm, period_type='monthly', used_sqm=0):
        """Check if compound can allocate requested urgent SQM."""
        remaining_quota = self.get_remaining_urgent_sqm_quota(period_type, used_sqm)
        if remaining_quota is None:
            return False
        
        return requested_sqm <= remaining_quota


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
        ('dumpster', 'Dumpster (Garbage Collection)'),
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
        
        # If space_type is dumpster, auto-fill defaults to bypass physical sqm requirements
        if self.space_type == 'dumpster':
            self.square_meters = Decimal('1.00')
            self.actual_sqm = Decimal('1.00')
            self.quantity_of_rooms = 1
            if self.frequency_per_week:
                self.weekly_required_sqm = self.frequency_per_week
            if self.max_frequency_per_month:
                self.monthly_cap_sqm = Decimal(str(self.max_frequency_per_month))

        # Date validation
        if self.service_start_date and self.service_end_date:
            if self.service_start_date > self.service_end_date:
                raise ValidationError("Start Date must be before or equal to End Date")
        
        # Frequency validation
        if self.frequency_per_week and self.max_frequency_per_month:
            if self.frequency_per_week > self.max_frequency_per_month:
                raise ValidationError("Frequency per week cannot exceed max frequency per month")
        
        # Area validation (run only for non-dumpster spaces)
        if self.space_type != 'dumpster':
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
    
    def generate_barcode_data(self) -> str:
        """
        Generate barcode data string for this room
        Format: C1-D-B87-R101 (max 16 characters)
        """
        from accounts.barcode_service import BarcodeService
        return BarcodeService.generate_barcode_data(self)
    
    def generate_barcode_image(self, width: int = 600, height: int = 240) -> bytes:
        """
        Generate barcode image as bytes
        """
        from accounts.barcode_service import BarcodeService
        barcode_data = self.generate_barcode_data()
        return BarcodeService.generate_barcode_with_text(barcode_data, width, height)
    
    @property
    def barcode_display(self) -> str:
        """
        Get barcode data for display
        """
        return self.generate_barcode_data()


class UrgentCleaningRequest(models.Model):
    """
    Model for urgent cleaning requests made by admin, manager, or authority users.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='urgent_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='urgent_requests')
    title = models.CharField(max_length=200, help_text="Brief title for the urgent cleaning request")
    description = models.TextField(help_text="Detailed description of the cleaning requirements")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="SQM area that needs urgent cleaning"
    )
    estimated_duration = models.IntegerField(
        help_text="Estimated duration in hours",
        validators=[MinValueValidator(1), MaxValueValidator(24)]
    )
    requested_date = models.DateTimeField(default=timezone.now)
    preferred_start_time = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Preferred start time for the cleaning"
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_urgent_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Additional notes or comments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Urgent Cleaning Request"
        verbose_name_plural = "Urgent Cleaning Requests"
    
    def __str__(self):
        return f"Urgent Request: {self.title} - {self.compound.name} ({self.get_status_display()})"
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def can_be_approved(self):
        return self.status == 'pending'
    
    @property
    def can_be_completed(self):
        return self.status in ['approved', 'in_progress']


class MonthlyRollup(models.Model):
    """
    Materialized rollup model for fast reporting and compliance calculations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='monthly_rollups')
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='monthly_rollups')
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='monthly_rollups')
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='monthly_rollups')
    period_start = models.DateField(help_text="Start of the rollup period")
    period_end = models.DateField(help_text="End of the rollup period")
    required_weekly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    achieved_weekly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    achieved_monthly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    capped_monthly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    sla_weekly_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    sla_monthly_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', 'room__room_code']
        unique_together = ['room', 'period_start', 'period_end']
        verbose_name = "Monthly Rollup"
        verbose_name_plural = "Monthly Rollups"

    def __str__(self):
        return f"Rollup: {self.room.room_code} ({self.period_start} to {self.period_end})"