"""
Custom middleware for the CCT Cleaning Tracker.
"""

from django.utils.deprecation import MiddlewareMixin

from accounts.scoping import is_platform_user, user_camp


class SiteScopeMiddleware(MiddlewareMixin):
    """
    Attach site-scope attributes to every authenticated request:

    - request.is_platform: True for Django superusers (all sites)
    - request.site: the user's assigned Camp, or None for platform / unscoped
    """

    def process_request(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.is_platform = is_platform_user(user)
            request.site = None if request.is_platform else user_camp(user)
        else:
            request.is_platform = False
            request.site = None
        return None
