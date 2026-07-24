"""
Recurring tasks list.

Each active dumpster is a recurring collection task. This page simply lists those
tasks with all their details (zone, street, team, day, type, GPS, client). Teams
and collection days are assigned on the Zone edit form, not here.
"""

from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .views import check_permission, get_user_role, log_audit_event
from .scoping import scoped_camps, is_platform_user
from locations.models import Camp, Compound, Room
from .models import Team
from .task_generation import DailyCleaningTask, generate_tasks_from_zones


@login_required
def task_assignment_dashboard(request):
    """List recurring collection tasks — one per dumpster — with full details."""
    if not check_permission(request, ['admin', 'manager', 'supervisor', 'authority']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')

    user_role = get_user_role(request)
    camps = scoped_camps(request.user)

    tasks = (Room.objects.filter(space_type='dumpster', camp__in=camps)
             .select_related('camp', 'compound', 'compound__assigned_team',
                             'compound__assigned_team__team_leader', 'building', 'client')
             .order_by('compound__name', 'building__name', 'room_code'))

    # Filters
    search = (request.GET.get('search') or '').strip()
    camp_filter = request.GET.get('camp') or ''
    zone_filter = request.GET.get('zone') or ''
    team_filter = request.GET.get('team') or ''
    day_filter = request.GET.get('day') or ''
    type_filter = request.GET.get('type') or ''
    status_filter = request.GET.get('status') or ''

    if search:
        tasks = tasks.filter(
            Q(room_code__icontains=search) | Q(room_description__icontains=search) |
            Q(building__name__icontains=search) | Q(compound__name__icontains=search)
        )
    if camp_filter:
        tasks = tasks.filter(camp_id=camp_filter)
    if zone_filter:
        tasks = tasks.filter(compound_id=zone_filter)
    if team_filter == 'unassigned':
        tasks = tasks.filter(compound__assigned_team__isnull=True)
    elif team_filter:
        tasks = tasks.filter(compound__assigned_team_id=team_filter)
    if day_filter == 'unscheduled':
        tasks = tasks.filter(compound__collection_weekday__isnull=True)
    elif day_filter != '':
        tasks = tasks.filter(compound__collection_weekday=day_filter)
    if type_filter:
        tasks = tasks.filter(dumpster_type=type_filter)
    if status_filter == 'active':
        tasks = tasks.filter(is_active=True)
    elif status_filter == 'inactive':
        tasks = tasks.filter(is_active=False)

    total_count = tasks.count()

    paginator = Paginator(tasks, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    zones = Compound.objects.filter(is_active=True, camp__in=camps).order_by('name')
    teams = Team.objects.filter(camp__in=camps).select_related('team_leader').order_by('name')

    # Generation readiness: schedulable dumpsters (zone + team + day) vs orphans.
    all_dumpsters = Room.objects.filter(space_type='dumpster', is_active=True, camp__in=camps)
    schedulable_count = all_dumpsters.filter(
        compound__assigned_team__isnull=False,
        compound__collection_weekday__isnull=False,
    ).count()
    orphan_count = all_dumpsters.filter(
        Q(compound__isnull=True)
        | Q(compound__assigned_team__isnull=True)
        | Q(compound__collection_weekday__isnull=True)
    ).count()
    existing_task_count = DailyCleaningTask.objects.filter(
        room__camp__in=camps,
    ).count()

    context = {
        'page_obj': page_obj,
        'total_count': total_count,
        'camps': camps,
        'zones': zones,
        'teams': teams,
        'schedulable_count': schedulable_count,
        'orphan_count': orphan_count,
        'existing_task_count': existing_task_count,
        'weekday_choices': Compound.COLLECTION_WEEKDAY_CHOICES,
        'filters': {
            'search': search, 'camp': camp_filter, 'zone': zone_filter,
            'team': team_filter, 'day': day_filter, 'type': type_filter,
            'status': status_filter,
        },
        'user_role': user_role,
        'page_title': 'RECURRING TASKS',
        'page_subtitle': 'Each dumpster is a recurring collection task',
    }
    return render(request, 'accounts/task_assignment_dashboard.html', context)


@login_required
def manage_recurring_tasks(request):
    """Clear and/or (re)generate collection tasks from zone assignments.

    Actions (POST):
      - clear:      delete all collection (dumpster) tasks in scope
      - generate:   create tasks for the horizon from zone assignments
      - regenerate: clear then generate

    Only zones that have BOTH a team and a collection day produce tasks; orphaned
    dumpsters are skipped.
    """
    if not check_permission(request, ['admin', 'manager', 'operations_manager']):
        messages.error(request, "You don't have permission to do this.")
        return redirect('accounts:task_assignment_dashboard')
    if request.method != 'POST':
        return redirect('accounts:task_assignment_dashboard')

    action = request.POST.get('action', 'regenerate')
    try:
        horizon_days = int(request.POST.get('horizon_days', 28))
    except (TypeError, ValueError):
        horizon_days = 28
    horizon_days = max(1, min(horizon_days, 90))

    user_role = get_user_role(request)
    camps = list(scoped_camps(request.user))

    if not camps:
        messages.error(request, 'No Site in scope.')
        return redirect('accounts:task_assignment_dashboard')

    deleted = 0
    if action in ('clear', 'regenerate'):
        qs = DailyCleaningTask.objects.filter(room__camp__in=camps)
        deleted = qs.count()
        qs.delete()

    result = {'created': 0, 'updated': 0, 'skipped_orphans': 0}
    if action in ('generate', 'regenerate'):
        start = timezone.localdate()
        end = start + timedelta(days=horizon_days - 1)
        result = generate_tasks_from_zones(start, end, camps=camps)

    log_audit_event(
        request, 'RECURRING_TASKS_MANAGED',
        object_ref=f'Sites:{",".join(str(c.id) for c in camps)}',
        details={'action': action, 'deleted': deleted, **result,
                 'horizon_days': horizon_days},
    )

    if action == 'clear':
        messages.success(request, f'Cleared {deleted} collection task(s).')
    elif action == 'generate':
        messages.success(
            request,
            f"Generated {result['created']} task(s) over {horizon_days} days "
            f"({result['skipped_orphans']} orphan dumpster(s) skipped)."
        )
    else:
        messages.success(
            request,
            f"Cleared {deleted} and generated {result['created']} task(s) over "
            f"{horizon_days} days ({result['skipped_orphans']} orphan dumpster(s) skipped)."
        )
    return redirect('accounts:task_assignment_dashboard')
