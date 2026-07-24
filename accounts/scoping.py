"""
Site (Camp) scoping helpers.

Platform users (Django superusers) see all sites.
Everyone else is locked to UserProfile.camp.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404


def is_platform_user(user):
    """True if the user may access all sites."""
    return bool(user and user.is_authenticated and user.is_superuser)


def user_camp(user):
    """Return the user's assigned Camp, or None for platform users / missing profile."""
    if not user or not user.is_authenticated:
        return None
    if is_platform_user(user):
        return None
    profile = getattr(user, "profile", None)
    return getattr(profile, "camp", None) if profile else None


def scoped_camps(user, active_only=True):
    """
    QuerySet of Camps the user may access.
    Platform → all (optionally active); otherwise → their camp only.
    """
    from locations.models import Camp

    qs = Camp.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)

    if is_platform_user(user):
        return qs.order_by("name")

    camp = user_camp(user)
    if camp:
        return qs.filter(id=camp.id)
    return Camp.objects.none()


def filter_by_camp(qs, user, camp_lookup="camp"):
    """
    Restrict a queryset to the user's site(s).
    Platform users get the queryset unchanged.
    """
    if is_platform_user(user):
        return qs
    camp = user_camp(user)
    if not camp:
        return qs.none()
    return qs.filter(**{camp_lookup: camp})


def camp_ids_for(user):
    """List of camp UUIDs the user may access (empty if none)."""
    return list(scoped_camps(user).values_list("id", flat=True))


def user_in_scope(actor, target_user):
    """
    Whether actor may manage/view target_user.
    Platform sees everyone; others only users whose profile.camp matches.
    """
    if is_platform_user(actor):
        return True
    actor_camp = user_camp(actor)
    if not actor_camp:
        return False
    target_profile = getattr(target_user, "profile", None)
    if not target_profile:
        return False
    return target_profile.camp_id == actor_camp.id


def get_scoped_object(model, user, pk, camp_lookups=None, **kwargs):
    """
    get_object_or_404 that also enforces site scope.

    camp_lookups: list of ORM paths that must resolve to a Camp in scope,
    e.g. ['camp'], ['compound__camp'], ['room__camp'], ['team__camp'].
    If omitted, tries 'camp' then common alternates.
    """
    obj = get_object_or_404(model, pk=pk, **kwargs)
    if is_platform_user(user):
        return obj

    allowed = set(camp_ids_for(user))
    if not allowed:
        raise Http404()

    if camp_lookups is None:
        camp_lookups = ["camp", "compound__camp", "room__camp", "team__camp", "building__compound__camp"]

    for lookup in camp_lookups:
        camp = _resolve_camp(obj, lookup)
        if camp is not None:
            if camp.id in allowed:
                return obj
            raise Http404()

    # No resolvable camp path — deny for non-platform
    raise Http404()


def _resolve_camp(obj, lookup):
    """Follow dotted attribute path; return Camp or None."""
    current = obj
    for part in lookup.split("__"):
        current = getattr(current, part, None)
        if current is None:
            return None
    # current should be a Camp instance (has id and typically code/name)
    return current if hasattr(current, "id") else None


def require_platform(user):
    """Return True if user is platform; useful for create-site gates."""
    return is_platform_user(user)
