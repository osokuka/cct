"""
Custom admin site configuration to restrict access to admin users only.
"""

from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

User = get_user_model()


class RestrictedAdminSite(AdminSite):
    """Custom admin site that restricts access to admin users only."""
    
    def login(self, request, extra_context=None):
        """Override login to redirect non-admin users."""
        if request.user.is_authenticated:
            if hasattr(request.user, 'profile') and request.user.profile.role == 'admin':
                return super().login(request, extra_context)
            else:
                # Redirect non-admin users to the main dashboard
                return redirect('dashboard:dashboard')
        return super().login(request, extra_context)
    
    def index(self, request, extra_context=None):
        """Override index to check admin role."""
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        
        if not (hasattr(request.user, 'profile') and request.user.profile.role == 'admin'):
            return HttpResponseForbidden("Access denied. Admin role required.")
        
        return super().index(request, extra_context)
    
    def each_context(self, request):
        """Add custom context to admin pages."""
        context = super().each_context(request)
        context['site_title'] = 'NATO Camp Cleaning Tracker - Admin'
        context['site_header'] = 'NATO Camp Cleaning Tracker'
        context['index_title'] = 'Administration Panel'
        return context


# Create custom admin site instance
admin_site = RestrictedAdminSite(name='restricted_admin')

# Register models with the custom admin site
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import UserProfile, CompoundAssignment, Team, Shift, Route
from accounts.admin import UserProfileInline, UserAdmin

# Register User with custom admin
admin_site.register(User, UserAdmin)

# Register other models
admin_site.register(UserProfile)
admin_site.register(CompoundAssignment)
admin_site.register(Team)
admin_site.register(Shift)
admin_site.register(Route)
