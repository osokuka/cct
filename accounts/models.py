"""
Account models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta, time as dtime
import uuid


WEEKDAY_CHOICES = [
    (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
    (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
]


class UserProfile(models.Model):
    """
    Extended user profile with role and camp information.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Field Manager'),
        ('operations_manager', 'Operations Manager'),
        ('cleaner', 'Cleaner'),
        ('authority', 'Authority'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, help_text="User role")
    camp = models.ForeignKey('locations.Camp', on_delete=models.CASCADE, null=True, blank=True, help_text="Assigned camp")
    is_team_leader = models.BooleanField(default=False, help_text="Is this user a team leader?")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number")
    is_active = models.BooleanField(default=True, help_text="Is user active?")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        """
        Automatically assign user to appropriate Django group based on role.
        """
        super().save(*args, **kwargs)
        
        # Remove user from all role groups first
        self.user.groups.clear()
        
        # Add user to appropriate group
        group_name = self.role.title()
        group, created = Group.objects.get_or_create(name=group_name)
        self.user.groups.add(group)


class CompoundAssignment(models.Model):
    """
    Multi-tenant compound assignment for Authority users.
    Authority users can only see data from their assigned compounds.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compound_assignments')
    compound = models.ForeignKey('locations.Compound', on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_compounds',
        help_text="User who made this assignment"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['user', 'compound']
        verbose_name = "Compound Assignment"
        verbose_name_plural = "Compound Assignments"
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.user.username} → {self.compound.name}"

    def clean(self):
        """
        Validate that only Authority users can have compound assignments.
        """
        from django.core.exceptions import ValidationError
        
        if hasattr(self.user, 'profile'):
            if self.user.profile.role != 'authority':
                raise ValidationError("Only Authority users can have compound assignments")


class Team(models.Model):
    """
    Cleaning teams that work specific shifts and are assigned to compounds via routes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text="Team name")
    camp = models.ForeignKey('locations.Camp', on_delete=models.CASCADE, related_name='teams')
    shift = models.ForeignKey(
        'Shift', 
        on_delete=models.CASCADE, 
        related_name='teams',
        null=True,
        blank=True,
        help_text="Shift when this team works"
    )
    team_leader = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='led_teams',
        help_text="Team leader"
    )
    members = models.ManyToManyField(
        User, 
        related_name='teams',
        blank=True,
        help_text="Team members (optional)"
    )
    employee_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of employees on this team (including the leader)"
    )
    vehicle = models.CharField(
        max_length=120, blank=True,
        help_text="Vehicle assigned to this team (e.g. Truck GJ-123-AB)"
    )
    equipment = models.TextField(
        blank=True,
        help_text="Equipment assigned to this team"
    )
    TEAM_TYPE_CHOICES = [
        ('cleaning', 'Cleaning Team'),
        ('collection', 'Garbage Collection Team'),
    ]
    team_type = models.CharField(
        max_length=50,
        choices=TEAM_TYPE_CHOICES,
        default='cleaning',
        help_text="Type of team (Cleaning or Garbage Collection)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['camp', 'name']
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.camp.name})"

    def clean(self):
        """
        Validate team assignment rules and prevent conflicts.
        """
        from django.core.exceptions import ValidationError
        
        # Validate team leader role
        if hasattr(self.team_leader, 'profile'):
            if self.team_leader.profile.role not in ['admin', 'manager', 'cleaner']:
                raise ValidationError("Team leader must be an Admin, Manager, or Cleaner")
        
        # Validate shift belongs to the same camp
        if hasattr(self, 'shift') and self.shift and self.camp:
            if self.shift.camp != self.camp:
                raise ValidationError(
                    f"Shift '{self.shift.name}' does not belong to camp '{self.camp.name}'"
                )
        

    def save(self, *args, **kwargs):
        # Shifts are simplified to a single standard 08:00-17:00 shift per site.
        if not self.shift_id and self.camp_id:
            self.shift = Shift.get_or_create_default(self.camp)
        self.clean()
        super().save(*args, **kwargs)


class Shift(models.Model):
    """
    Work shifts for teams.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.ForeignKey('locations.Camp', on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=100, help_text="Shift name (e.g., Morning, Afternoon, Night)")
    start_time = models.TimeField(help_text="Shift start time")
    end_time = models.TimeField(help_text="Shift end time")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['camp', 'name']
        verbose_name = "Shift"
        verbose_name_plural = "Shifts"
        ordering = ['start_time']

    #: Canonical shift used across the app now that shifts are simplified.
    DEFAULT_NAME = "Standard"
    DEFAULT_START = dtime(8, 0)
    DEFAULT_END = dtime(17, 0)

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time}) - {self.camp.name}"

    @classmethod
    def get_or_create_default(cls, camp):
        """Return the single standard 08:00-17:00 shift for a Site (Camp)."""
        shift, _ = cls.objects.get_or_create(
            camp=camp, name=cls.DEFAULT_NAME,
            defaults={"start_time": cls.DEFAULT_START,
                      "end_time": cls.DEFAULT_END, "is_active": True},
        )
        return shift

    def clean(self):
        """
        Validate that end time is after start time.
        Note: For overnight shifts, we'll allow end time to be before start time.
        """
        from django.core.exceptions import ValidationError
        
        if self.start_time and self.end_time:
            # Allow overnight shifts (end time before start time)
            # This is valid for shifts that cross midnight
            pass

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Route(models.Model):
    """
    A team's daily route: a set of streets a team services on a given weekday.

    Corporate model: a Team gets one Route per weekday. Each Route contains N
    Streets (``locations.Building``) and their geolocated Service Points
    (dumpsters). Per-dumpster Tasks are generated in the backend from these
    routes for reporting and tracking.

    ``compounds`` (Zones) is retained for backward compatibility and is derived
    from the streets' zones.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='routes')
    name = models.CharField(max_length=120, blank=True, help_text="Optional route label")
    weekday = models.IntegerField(
        null=True, blank=True,
        choices=WEEKDAY_CHOICES,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Weekday this route runs (0=Mon..6=Sun)"
    )
    streets = models.ManyToManyField(
        'locations.Building', through='RouteStreet',
        related_name='routes', blank=True,
        help_text="Streets serviced on this route"
    )
    compounds = models.ManyToManyField('locations.Compound', related_name='routes', blank=True, help_text="Zones assigned to this route (derived from streets)")
    priority = models.IntegerField(default=1, help_text="Route priority (higher number = higher priority)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['team', 'weekday']
        verbose_name = "Route"
        verbose_name_plural = "Routes"
        ordering = ['team__name', 'weekday']

    def __str__(self):
        day = self.get_weekday_display() if self.weekday is not None else "Unscheduled"
        return f"{self.team.name} — {day} route"

    @property
    def street_count(self):
        return self.streets.count()

    @property
    def dumpster_count(self):
        from locations.models import Room
        return Room.objects.filter(
            building__in=self.streets.all(), space_type='dumpster', is_active=True
        ).count()


class RouteStreet(models.Model):
    """Ordered membership of a Street (Building) within a Route."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='route_streets')
    building = models.ForeignKey('locations.Building', on_delete=models.CASCADE, related_name='route_memberships')
    order = models.IntegerField(default=0, help_text="Order of this street within the route")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['route', 'building']
        ordering = ['route', 'order']
        verbose_name = "Route Street"
        verbose_name_plural = "Route Streets"

    def __str__(self):
        return f"{self.route} · {self.building.name} (#{self.order})"


class PlanGenerationConfig(models.Model):
    """
    Per-Site configuration for automatic route-task generation.

    A scheduled job runs every Sunday 00:01 and generates the upcoming
    per-dumpster tasks from each team's routes. Management chooses the cadence.
    """
    CADENCE_CHOICES = [
        ('weekly', 'Every week'),
        ('biweekly', 'Every second week'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.OneToOneField('locations.Camp', on_delete=models.CASCADE, related_name='plan_config')
    cadence = models.CharField(max_length=20, choices=CADENCE_CHOICES, default='weekly')
    anchor_date = models.DateField(
        help_text="Reference Monday used to compute bi-weekly parity",
        default=timezone.localdate,
    )
    last_generated_on = models.DateField(null=True, blank=True, help_text="Last date tasks were generated")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plan Generation Config"
        verbose_name_plural = "Plan Generation Configs"

    def __str__(self):
        return f"{self.camp.name} — {self.get_cadence_display()}"

    @property
    def horizon_days(self):
        return 14 if self.cadence == 'biweekly' else 7

    def is_generation_week(self, ref_date=None):
        """Whether the week of ref_date is a generation week for this cadence."""
        ref_date = ref_date or timezone.localdate()
        if self.cadence == 'weekly':
            return True
        # bi-weekly: generate on even-numbered weeks relative to anchor
        week_start = ref_date - timedelta(days=ref_date.weekday())
        anchor_start = self.anchor_date - timedelta(days=self.anchor_date.weekday())
        weeks = (week_start - anchor_start).days // 7
        return weeks % 2 == 0