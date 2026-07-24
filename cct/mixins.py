"""
Custom mixins for the CCT Cleaning Tracker.
"""

from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.contrib import messages

from accounts.scoping import is_platform_user


class AdminRequiredMixin(AccessMixin):
    """
    CBV mixin that requires an authenticated site admin (role=admin) or platform superuser.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if is_platform_user(request.user):
            return super().dispatch(request, *args, **kwargs)

        role = request.user.profile.role if hasattr(request.user, 'profile') else None
        if role != 'admin':
            messages.error(request, "You don't have permission to access this page.")
            if role in ['manager', 'cleaner', 'authority', 'supervisor', 'operations_manager']:
                return redirect('dashboard:dashboard')
            return redirect('accounts:login')

        return super().dispatch(request, *args, **kwargs)
