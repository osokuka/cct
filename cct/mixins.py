"""
Custom mixins for the NATO Camp Cleaning Tracker.
Includes ScopedQuerysetMixin for automatic data filtering and other utility mixins.
"""

from django.db import models
from django.http import JsonResponse
from django.contrib.auth.models import AnonymousUser
from accounts.models import get_user_role, get_authority_compound_ids


class ScopedQuerysetMixin:
    """
    Mixin for views to automatically filter querysets based on user role and compound scope.
    Authority users only see data from their assigned compounds.
    """
    
    def get_queryset(self):
        """Filter queryset based on user role and compound scope."""
        queryset = super().get_queryset()
        
        # Get user role and scope from request
        user_role = getattr(self.request, 'role', None)
        scope = getattr(self.request, 'scope', None)
        compound_ids = getattr(scope, 'compound_ids', []) if scope else []
        
        # Apply compound scoping for Authority users
        if user_role == 'authority' and compound_ids:
            queryset = self._apply_compound_filter(queryset, compound_ids)
        
        return queryset
    
    def _apply_compound_filter(self, queryset, compound_ids):
        """Apply compound filtering based on model relationships."""
        model = queryset.model
        
        # Direct compound relationship
        if hasattr(model, 'compound'):
            return queryset.filter(compound_id__in=compound_ids)
        
        # Through floor -> building -> compound
        elif hasattr(model, 'floor'):
            return queryset.filter(floor__building__compound_id__in=compound_ids)
        
        # Through building -> compound
        elif hasattr(model, 'building'):
            return queryset.filter(building__compound_id__in=compound_ids)
        
        # Through room -> floor -> building -> compound
        elif hasattr(model, 'room'):
            return queryset.filter(room__floor__building__compound_id__in=compound_ids)
        
        # For user-related objects, filter by user's compound assignments
        elif hasattr(model, 'user') or hasattr(model, 'requested_by') or hasattr(model, 'assigned_to'):
            from accounts.models import CompoundAssignment
            user_compound_ids = list(
                CompoundAssignment.objects
                .filter(user=self.request.user)
                .values_list('compound_id', flat=True)
            )
            
            if hasattr(model, 'room'):
                return queryset.filter(room__floor__building__compound_id__in=user_compound_ids)
            elif hasattr(model, 'user'):
                return queryset.filter(user__compound_assignments__compound_id__in=user_compound_ids)
            elif hasattr(model, 'requested_by'):
                return queryset.filter(requested_by__compound_assignments__compound_id__in=user_compound_ids)
            elif hasattr(model, 'assigned_to'):
                return queryset.filter(assigned_to__compound_assignments__compound_id__in=user_compound_ids)
        
        # For audit logs, filter by user's compound assignments
        elif model.__name__ == 'AuditLog':
            from accounts.models import CompoundAssignment
            user_compound_ids = list(
                CompoundAssignment.objects
                .filter(user=self.request.user)
                .values_list('compound_id', flat=True)
            )
            # Filter audit logs by users in the same compounds
            return queryset.filter(
                user__compound_assignments__compound_id__in=user_compound_ids
            )
        
        return queryset


class RoleRequiredMixin:
    """
    Mixin to require specific roles for view access.
    """
    required_roles = []
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has required role."""
        if isinstance(request.user, AnonymousUser) or not request.user.is_authenticated:
            return JsonResponse(
                {'error': 'Authentication required'}, 
                status=401
            )
        
        user_role = get_user_role(request.user)
        
        if not user_role or user_role not in self.required_roles:
            return JsonResponse(
                {'error': 'Insufficient permissions'}, 
                status=403
            )
        
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    """Mixin requiring admin role."""
    required_roles = ['admin']


class SupervisorRequiredMixin(RoleRequiredMixin):
    """Mixin requiring supervisor or admin role."""
    required_roles = ['admin', 'supervisor']


class AuthorityRequiredMixin(RoleRequiredMixin):
    """Mixin requiring authority, supervisor, or admin role."""
    required_roles = ['admin', 'supervisor', 'authority']


class CleanerRequiredMixin(RoleRequiredMixin):
    """Mixin requiring cleaner, supervisor, or admin role."""
    required_roles = ['admin', 'supervisor', 'cleaner']


class ExportMixin:
    """
    Mixin for handling data exports with proper authorization and logging.
    """
    
    def export_queryset(self, queryset, format_type, user, filters=None):
        """
        Centralized export function that enforces scoping and logs exports.
        """
        from audit.models import AuditLog
        
        # Ensure queryset is properly scoped
        if hasattr(self, 'get_queryset'):
            scoped_queryset = self.get_queryset()
            # Verify the export queryset is a subset of the scoped queryset
            if not queryset.model == scoped_queryset.model:
                raise ValueError("Export queryset must be from the same model as scoped queryset")
        
        # Log the export
        export_filters = filters or {}
        record_count = queryset.count()
        
        AuditLog.objects.create(
            user=user,
            action='export_data',
            object_type=queryset.model.__name__,
            object_ref=f"Export of {record_count} {queryset.model.__name__} records",
            request_data={
                'format': format_type,
                'filters': export_filters,
                'record_count': record_count
            }
        )
        
        return queryset, record_count


class CompoundScopedMixin:
    """
    Mixin for views that need compound scoping.
    Provides utility methods for compound-based filtering.
    """
    
    def get_user_compound_ids(self):
        """Get compound IDs for the current user."""
        user_role = getattr(self.request, 'role', None)
        
        if user_role == 'authority':
            return get_authority_compound_ids(self.request.user)
        elif user_role in ['admin', 'supervisor']:
            # Admins and supervisors can see all compounds
            from locations.models import Compound
            return list(Compound.objects.values_list('id', flat=True))
        
        return []
    
    def filter_by_compounds(self, queryset):
        """Filter queryset by user's assigned compounds."""
        compound_ids = self.get_user_compound_ids()
        
        if not compound_ids:
            return queryset.none()
        
        # Apply compound filtering based on model relationships
        model = queryset.model
        
        if hasattr(model, 'compound'):
            return queryset.filter(compound_id__in=compound_ids)
        elif hasattr(model, 'floor'):
            return queryset.filter(floor__building__compound_id__in=compound_ids)
        elif hasattr(model, 'building'):
            return queryset.filter(building__compound_id__in=compound_ids)
        elif hasattr(model, 'room'):
            return queryset.filter(room__floor__building__compound_id__in=compound_ids)
        
        return queryset


class AuditMixin:
    """
    Mixin for views that need to set audit references.
    """
    
    def set_audit_ref(self, obj):
        """Set audit reference for the current request."""
        if hasattr(self.request, 'audit_ref'):
            self.request.audit_ref = str(obj)
        else:
            self.request.audit_ref = str(obj)
    
    def get_audit_ref(self):
        """Get audit reference from the current request."""
        return getattr(self.request, 'audit_ref', None)


class RosterMixin:
    """
    Mixin for roster-related views.
    Provides utility methods for roster generation and management.
    """
    
    def get_camp_policy(self, camp):
        """Get camp policy for roster generation."""
        return {
            'timezone': camp.timezone,
            'week_cutoff_day': camp.week_cutoff_day,
            'week_cutoff_hour': camp.week_cutoff_hour,
            'month_cutoff_day': camp.month_cutoff_day,
            'month_cutoff_hour': camp.month_cutoff_hour,
            'skip_holidays': camp.skip_holidays,
        }
    
    def validate_roster_generation(self, camp, start_date, end_date):
        """Validate roster generation parameters."""
        from datetime import date
        
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")
        
        if start_date < date.today():
            raise ValueError("Cannot generate roster for past dates")
        
        # Check if roster already exists for this period
        from scans.models import DailyCleaningTask
        existing_tasks = DailyCleaningTask.objects.filter(
            room__floor__building__compound__camp=camp,
            date__range=[start_date, end_date]
        ).exists()
        
        if existing_tasks:
            raise ValueError("Roster already exists for this period")
        
        return True
