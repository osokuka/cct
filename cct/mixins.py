"""
Custom mixins for the NATO Camp Cleaning Tracker.
"""

from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.contrib import messages

class AdminRequiredMixin(AccessMixin):
    """
    CBV mixin that requires the user to be authenticated and have the role 'admin'.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
            
        role = request.user.profile.role if hasattr(request.user, 'profile') else None
        if role != 'admin':
            messages.error(request, "You don't have permission to access this page.")
            # Redirect to login or home
            if role in ['manager', 'cleaner', 'authority', 'supervisor']:
                return redirect('dashboard:dashboard')
            return redirect('accounts:login')
            
        return super().dispatch(request, *args, **kwargs)