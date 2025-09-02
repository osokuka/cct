"""
Custom permissions for the NATO Camp Cleaning Tracker.
DRF permissions classes for API access control with role-based and compound scoping.
"""

from rest_framework import permissions
from accounts.models import get_user_role, get_authority_compound_ids


class IsAdmin(permissions.BasePermission):
    """
    Permission class for Admin users.
    Admins have full access to all data.
    """
    
    def has_permission(self, request, view):
        """Check if user is an admin."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role == 'admin' or request.user.is_superuser


class IsSupervisor(permissions.BasePermission):
    """
    Permission class for Supervisor users.
    Supervisors have read/write access except for user/role administration.
    """
    
    def has_permission(self, request, view):
        """Check if user is a supervisor or admin."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor']
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permissions for supervisors."""
        user_role = get_user_role(request.user)
        
        # Admins have full access
        if user_role == 'admin':
            return True
        
        # Supervisors can't modify user roles or admin accounts
        if hasattr(obj, 'user') and hasattr(obj.user, 'profile'):
            if obj.user.profile.role == 'admin':
                return False
        
        return True


class IsCleaner(permissions.BasePermission):
    """
    Permission class for Cleaner users.
    Cleaners can only access scanning endpoints and their assigned tasks.
    """
    
    def has_permission(self, request, view):
        """Check if user is a cleaner or higher."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'cleaner']
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permissions for cleaners."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors have full access
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Cleaners can only access their own tasks and scans
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
        
        if hasattr(obj, 'assigned_to') and obj.assigned_to == request.user:
            return True
        
        return False


class IsAuthorityReadOnly(permissions.BasePermission):
    """
    Permission class for Contracting Authority users.
    Authority users have read-only access to their assigned compounds.
    Can create re-clean and urgent cleaning requests.
    """
    
    def has_permission(self, request, view):
        """Check if user is an authority or higher."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'authority']
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permissions for authority users."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors have full access
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Authority users have read-only access to their assigned compounds
        if user_role == 'authority':
            # Check if object is within user's assigned compounds
            compound_ids = get_authority_compound_ids(request.user)
            
            if hasattr(obj, 'compound'):
                return obj.compound_id in compound_ids
            elif hasattr(obj, 'floor'):
                return obj.floor.building.compound_id in compound_ids
            elif hasattr(obj, 'building'):
                return obj.building.compound_id in compound_ids
            elif hasattr(obj, 'room'):
                return obj.room.floor.building.compound_id in compound_ids
            elif hasattr(obj, 'requested_by'):
                # Authority users can see their own requests
                return obj.requested_by == request.user
        
        return False


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows owners to edit their objects, others to read.
    """
    
    def has_object_permission(self, request, view, obj):
        """Check if user is the owner of the object."""
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for the owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        elif hasattr(obj, 'requested_by'):
            return obj.requested_by == request.user
        
        return False


class CanCreateRecleanRequest(permissions.BasePermission):
    """
    Permission class for creating re-clean requests.
    Authority users can create requests for rooms in their assigned compounds.
    """
    
    def has_permission(self, request, view):
        """Check if user can create re-clean requests."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'authority']
    
    def has_object_permission(self, request, view, obj):
        """Check if user can create request for this room."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors can create requests for any room
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Authority users can only create requests for rooms in their assigned compounds
        if user_role == 'authority':
            compound_ids = get_authority_compound_ids(request.user)
            return obj.floor.building.compound_id in compound_ids
        
        return False


class CanCreateUrgentRequest(permissions.BasePermission):
    """
    Permission class for creating urgent cleaning requests.
    Authority users can create urgent requests for rooms in their assigned compounds.
    """
    
    def has_permission(self, request, view):
        """Check if user can create urgent requests."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'authority']
    
    def has_object_permission(self, request, view, obj):
        """Check if user can create urgent request for this room."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors can create urgent requests for any room
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Authority users can only create urgent requests for rooms in their assigned compounds
        if user_role == 'authority':
            compound_ids = get_authority_compound_ids(request.user)
            return obj.floor.building.compound_id in compound_ids
        
        return False


class CanScanRoom(permissions.BasePermission):
    """
    Permission class for scanning rooms.
    Cleaners can scan rooms, admins and supervisors have full access.
    """
    
    def has_permission(self, request, view):
        """Check if user can scan rooms."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'cleaner']
    
    def has_object_permission(self, request, view, obj):
        """Check if user can scan this specific room."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors can scan any room
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Cleaners can scan any active room
        if user_role == 'cleaner':
            return obj.is_active
        
        return False


class CompoundScopedPermission(permissions.BasePermission):
    """
    Base permission class for compound-scoped access.
    Authority users can only access data from their assigned compounds.
    """
    
    def has_permission(self, request, view):
        """Check basic permission."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = get_user_role(request.user)
        return user_role in ['admin', 'supervisor', 'authority']
    
    def has_object_permission(self, request, view, obj):
        """Check compound-scoped permission."""
        user_role = get_user_role(request.user)
        
        # Admins and supervisors have full access
        if user_role in ['admin', 'supervisor']:
            return True
        
        # Authority users have access only to their assigned compounds
        if user_role == 'authority':
            compound_ids = get_authority_compound_ids(request.user)
            
            # Check compound access through various object relationships
            if hasattr(obj, 'compound'):
                return obj.compound_id in compound_ids
            elif hasattr(obj, 'floor'):
                return obj.floor.building.compound_id in compound_ids
            elif hasattr(obj, 'building'):
                return obj.building.compound_id in compound_ids
            elif hasattr(obj, 'room'):
                return obj.room.floor.building.compound_id in compound_ids
        
        return False
