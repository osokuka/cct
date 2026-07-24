"""
Custom admin site configuration — platform superusers only.
"""

from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

User = get_user_model()


class RestrictedAdminSite(AdminSite):
    """Django admin restricted to is_superuser (platform). Site admins use the app UI."""

    def has_permission(self, request):
        return bool(
            request.user.is_active
            and request.user.is_authenticated
            and request.user.is_superuser
        )

    def login(self, request, extra_context=None):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                return super().login(request, extra_context)
            return redirect('dashboard:dashboard')
        return super().login(request, extra_context)

    def index(self, request, extra_context=None):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                "Access denied. Platform superuser required."
            )
        return super().index(request, extra_context)

    def each_context(self, request):
        context = super().each_context(request)
        context['site_title'] = 'CCT — Platform Admin'
        context['site_header'] = 'CCT Platform Administration'
        context['index_title'] = 'Administration Panel'
        return context


admin_site = RestrictedAdminSite(name='restricted_admin')

from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import UserProfile, CompoundAssignment, Team, Shift, Route
from accounts.admin import UserProfileInline, UserAdmin

admin_site.register(User, UserAdmin)
admin_site.register(UserProfile)
admin_site.register(CompoundAssignment)
admin_site.register(Team)
admin_site.register(Shift)
admin_site.register(Route)
