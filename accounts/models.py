"""
Account models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.utils import timezone
import uuid


class UserProfile(models.Model):
    """
    Extended user profile with role and camp information.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
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
        help_text="Team leader (must be a Manager or Admin)"
    )
    members = models.ManyToManyField(
        User, 
        related_name='teams',
        blank=True,
        help_text="Team members"
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

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time}) - {self.camp.name}"

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
    Routes assign teams to compounds.
    One team can handle multiple compounds.
    Business Rule: A team cannot be assigned to the same compound multiple times.
    Different teams can be assigned to the same compound.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='routes')
    compounds = models.ManyToManyField('locations.Compound', related_name='routes', help_text="Compounds assigned to this route")
    priority = models.IntegerField(default=1, help_text="Route priority (higher number = higher priority)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['team']
        verbose_name = "Route"
        verbose_name_plural = "Routes"
        ordering = ['-priority', 'team__name']

    def __str__(self):
        compound_names = ", ".join([c.name for c in self.compounds.all()])
        return f"{self.team.name} → {compound_names} ({self.team.shift.name})"

    def clean(self):
        """
        Validate that the same team is not assigned to the same compound multiple times.
        Allow different teams to be assigned to the same compound.
        """
        from django.core.exceptions import ValidationError
        
        if not self.pk:  # Only check for new routes
            return
            
        # Get all compounds for this route
        route_compounds = self.compounds.all()
        
        # Check if this team is already assigned to any of these compounds
        for compound in route_compounds:
            existing_routes = Route.objects.filter(
                team=self.team,
                compounds=compound,
                is_active=True
            ).exclude(pk=self.pk)
            
            if existing_routes.exists():
                raise ValidationError(
                    f"Team '{self.team.name}' is already assigned to {compound.name}. "
                    f"A team can only be assigned to each compound once."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)