"""
Account models for the NATO Camp Cleaning Tracker.
Extends Django's User model and defines compound assignments for multi-tenant access.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from locations.models import Compound


class UserProfile(models.Model):
    """
    Extended user profile with additional fields.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('supervisor', 'Supervisor'),
        ('cleaner', 'Cleaner'),
        ('authority', 'Contracting Authority'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cleaner')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_supervisor(self):
        return self.role == 'supervisor'
    
    @property
    def is_cleaner(self):
        return self.role == 'cleaner'
    
    @property
    def is_authority(self):
        return self.role == 'authority'


class CompoundAssignment(models.Model):
    """
    Links users to specific compounds for multi-tenant data scoping.
    Authority users are restricted to their assigned compounds only.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compound_assignments')
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='user_assignments')
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_assignments'
    )
    
    class Meta:
        unique_together = [['user', 'compound']]
        verbose_name = "Compound Assignment"
        verbose_name_plural = "Compound Assignments"
        indexes = [
            models.Index(fields=['user', 'compound']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} → {self.compound}"


def get_authority_compound_ids(user):
    """
    Utility function to get compound IDs for Authority users.
    Returns empty list for non-Authority users.
    """
    if not user.is_authenticated:
        return []
    
    try:
        profile = user.profile
        if profile.is_authority:
            return list(
                CompoundAssignment.objects
                .filter(user=user)
                .values_list('compound_id', flat=True)
            )
    except UserProfile.DoesNotExist:
        pass
    
    return []


def get_user_role(user):
    """
    Utility function to get user role.
    Returns 'admin' for superusers, otherwise returns profile role.
    """
    if not user.is_authenticated:
        return None
    
    if user.is_superuser:
        return 'admin'
    
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'cleaner'  # Default role


def create_user_groups():
    """
    Create default user groups for RBAC.
    This should be called in a data migration or management command.
    """
    groups_data = [
        ('Admin', 'Full system access'),
        ('Supervisor', 'Team management and reporting'),
        ('Cleaner', 'Scanning and task execution'),
        ('Authority', 'Read-only access to assigned compounds'),
    ]
    
    for group_name, description in groups_data:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            group.save()
    
    return Group.objects.all()