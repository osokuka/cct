"""
Dashboard views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from accounts.models import User, UserProfile, Team, Shift, Route
from accounts.task_generation import DailyCleaningTask
from accounts.views import check_permission
from locations.models import Camp, Compound, Room, UrgentCleaningRequest


@login_required
def dashboard(request):
    """Main dashboard view with comprehensive management data."""
    # Check permissions - admin, manager, cleaner, and authority can access dashboard
    if not check_permission(request, ['admin', 'manager', 'operations_manager', 'cleaner', 'authority']):
        return redirect('accounts:login')
    
    # Redirect authority users to their dedicated dashboard
    if hasattr(request.user, 'profile') and request.user.profile.role == 'authority':
        return redirect('dashboard:authority_dashboard')
    
    # Redirect operations managers to the operations dashboard
    if hasattr(request.user, 'profile') and request.user.profile.role == 'operations_manager':
        return redirect('dashboard:operations_dashboard')

    # Field operators (cleaners) use the minimal scan UI
    if hasattr(request.user, 'profile') and request.user.profile.role == 'cleaner':
        return redirect('accounts:barcode_scanner')
    
    context = {}
    
    # Get user role and camp
    user_role = None
    user_camp = None
    if hasattr(request.user, 'profile'):
        user_role = request.user.profile.role
        user_camp = request.user.profile.camp
    
    # Get camps for filtering
    if user_role == 'admin':
        camps = Camp.objects.filter(is_active=True)
    else:
        camps = Camp.objects.filter(is_active=True, id=user_camp.id) if user_camp else []
    
    # Get today's date and calculate time periods
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week
    week_end = week_start + timedelta(days=6)  # Sunday of current week
    month_start = today.replace(day=1)  # First day of current month
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)  # Last day of current month
    
    # Get filter parameter from request
    show_all_tasks = request.GET.get('show_all', 'false').lower() == 'true'
    show_all_cleaner_tasks = request.GET.get('show_all_cleaner', 'false').lower() == 'true'
    
    # Get all tasks for the user's scope
    all_tasks = DailyCleaningTask.objects.select_related(
        'room', 'room__compound', 'room__building', 'assigned_to_team', 'shift'
    )
    
    # Filter tasks based on user role
    if user_role == 'cleaner':
        # Cleaners see their team's tasks for today (if they're a team member)
        # Get all teams the user is associated with (as leader or member)
        user_teams = []
        
        # Check if they're a team leader
        leader_team = Team.objects.filter(team_leader=request.user).first()
        if leader_team:
            user_teams.append(leader_team)
        
        # Check if they're a member of any team
        member_teams = Team.objects.filter(members=request.user)
        user_teams.extend(member_teams)
        
        if user_teams:
            # Get compounds from the cleaner's routes
            from accounts.models import Route
            cleaner_routes = Route.objects.filter(
                team__in=user_teams,
                is_active=True
            ).prefetch_related('compounds')
            
            # Get all compounds from the cleaner's routes
            route_compounds = []
            for route in cleaner_routes:
                route_compounds.extend(route.compounds.all())
            
            # Filter tasks by team AND by compounds in their routes
            if route_compounds and not show_all_cleaner_tasks:
                # Show only tasks from compounds in their routes (default) - today only
                all_tasks = all_tasks.filter(
                    Q(assigned_to_team__in=user_teams) | Q(assigned_to_user=request.user),
                    task_date=today,
                    room__compound__in=route_compounds
                )
            else:
                # Show all tasks from their teams (when "Show All Tasks" is clicked) - today only
                all_tasks = all_tasks.filter(
                    Q(assigned_to_team__in=user_teams) | Q(assigned_to_user=request.user),
                    task_date=today
                )
        else:
            # If not in any team, show tasks assigned directly to their user account
            all_tasks = all_tasks.filter(assigned_to_user=request.user, task_date=today)
    elif user_role == 'authority':
        # Authority users see tasks from their assigned compou        from accounts.views import get_authority_compound_ids
        authority_compound_ids = get_authority_compound_ids(request.user)
        if authority_compound_ids:
            all_tasks = all_tasks.filter(room__compound_id__in=authority_compound_ids)
        else:
            # If no compound assignments, show no tasks
            all_tasks = all_tasks.none()
    elif user_role != 'admin' and user_camp:
        # Managers see their camp's tasks
        all_tasks = all_tasks.filter(room__camp=user_camp)
    
    # Filter tasks based on show_all parameter
    if show_all_tasks and user_role != 'cleaner':
        # Show all tasks across all dates (not for cleaners)
        filtered_tasks = all_tasks
    else:
        # Show only today's tasks by default (or cleaner's tasks are already filtered)
        if user_role == 'cleaner':
            filtered_tasks = all_tasks  # Already filtered to today and user's tasks
        else:
            filtered_tasks = all_tasks.filter(task_date=today)
    
    # Today's tasks
    today_tasks = all_tasks.filter(task_date=today)
    
    # Week's tasks
    week_tasks = all_tasks.filter(task_date__range=[week_start, week_end])
    
    # Month's tasks
    month_tasks = all_tasks.filter(task_date__range=[month_start, month_end])
    
    # Task statistics based on filter
    # Use filtered_tasks for all users (today's tasks by default)
    stats_tasks = filtered_tasks
    
    # Calculate missed tasks (tasks that are past due and still in planned state)
    # For missed tasks, we need to look at all tasks, not just filtered ones
    missed_tasks = all_tasks.filter(
        Q(state='missed') | 
        (Q(state='planned') & Q(task_date__lt=today))
    )
    
    task_stats = {
        'total_tasks': stats_tasks.count(),
        'today_tasks': today_tasks.count(),
        'completed_tasks': stats_tasks.filter(state='done').count(),
        'missed_tasks': missed_tasks.count(),
        # Split overdue work into missed garbage collections vs missed cleaning deadlines.
        'missed_collection_tasks': missed_tasks.filter(room__space_type='dumpster').count(),
        'missed_cleaning_tasks': missed_tasks.exclude(room__space_type='dumpster').count(),
        'planned_tasks': stats_tasks.filter(state='planned').count(),
        'in_progress_tasks': stats_tasks.filter(state='in_progress').count(),
        'urgent_tasks': stats_tasks.filter(task_type='requested').count(),
        'unassigned_tasks': stats_tasks.filter(assigned_to_team__isnull=True).count(),
    }
    
    # Calculate SLA percentage
    if task_stats['total_tasks'] > 0:
        task_stats['sla_percentage'] = (task_stats['completed_tasks'] / task_stats['total_tasks']) * 100
    else:
        task_stats['sla_percentage'] = 0
    
    # Get compound-level statistics for different time periods
    compounds_data = []
    for compound in Compound.objects.filter(camp__in=camps, is_active=True):
        # Filtered data (based on show_all parameter)
        filtered_compound_tasks = filtered_tasks.filter(room__compound=compound)
        # Today's data
        today_compound_tasks = all_tasks.filter(room__compound=compound, task_date=today)
        # Week's data
        week_compound_tasks = all_tasks.filter(room__compound=compound, task_date__range=[week_start, week_end])
        # Month's data
        month_compound_tasks = all_tasks.filter(room__compound=compound, task_date__range=[month_start, month_end])
        
        # Calculate missed tasks for each time period
        filtered_missed = filtered_compound_tasks.filter(
            Q(state='missed') | 
            (Q(state='planned') & Q(task_date__lt=today))
        )
        today_missed = today_compound_tasks.filter(
            Q(state='missed') | 
            (Q(state='planned') & Q(task_date__lt=today))
        )
        week_missed = week_compound_tasks.filter(
            Q(state='missed') | 
            (Q(state='planned') & Q(task_date__lt=today))
        )
        month_missed = month_compound_tasks.filter(
            Q(state='missed') | 
            (Q(state='planned') & Q(task_date__lt=today))
        )
        
        compound_stats = {
            'compound': compound,
            # Filtered data (based on show_all parameter)
            'filtered': {
                'total_tasks': filtered_compound_tasks.count(),
                'completed_tasks': filtered_compound_tasks.filter(state='done').count(),
                'missed_tasks': filtered_missed.count(),
                'planned_tasks': filtered_compound_tasks.filter(state='planned').count(),
                'urgent_tasks': filtered_compound_tasks.filter(task_type='requested').count(),
                'unassigned_tasks': filtered_compound_tasks.filter(assigned_to_team__isnull=True).count(),
            },
            # Today's data
            'today': {
                'total_tasks': today_compound_tasks.count(),
                'completed_tasks': today_compound_tasks.filter(state='done').count(),
                'missed_tasks': today_missed.count(),
                'planned_tasks': today_compound_tasks.filter(state='planned').count(),
                'urgent_tasks': today_compound_tasks.filter(task_type='requested').count(),
                'unassigned_tasks': today_compound_tasks.filter(assigned_to_team__isnull=True).count(),
            },
            # Week's data
            'week': {
                'total_tasks': week_compound_tasks.count(),
                'completed_tasks': week_compound_tasks.filter(state='done').count(),
                'missed_tasks': week_missed.count(),
                'planned_tasks': week_compound_tasks.filter(state='planned').count(),
                'urgent_tasks': week_compound_tasks.filter(task_type='requested').count(),
                'unassigned_tasks': week_compound_tasks.filter(assigned_to_team__isnull=True).count(),
            },
            # Month's data
            'month': {
                'total_tasks': month_compound_tasks.count(),
                'completed_tasks': month_compound_tasks.filter(state='done').count(),
                'missed_tasks': month_missed.count(),
                'planned_tasks': month_compound_tasks.filter(state='planned').count(),
                'urgent_tasks': month_compound_tasks.filter(task_type='requested').count(),
                'unassigned_tasks': month_compound_tasks.filter(assigned_to_team__isnull=True).count(),
            }
        }
        
        # Calculate SLA for each time period
        for period in ['filtered', 'today', 'week', 'month']:
            period_data = compound_stats[period]
            if period_data['total_tasks'] > 0:
                period_data['sla_percentage'] = (period_data['completed_tasks'] / period_data['total_tasks']) * 100
            else:
                period_data['sla_percentage'] = 0
            
        compounds_data.append(compound_stats)
    
    # Get active teams
    active_teams = Team.objects.filter(is_active=True, camp__in=camps).select_related('team_leader', 'camp')
    
    # Get recent activity - use filtered tasks
    # For cleaners, show all their tasks; for others, limit to 10
    if user_role == 'cleaner':
        # For cleaners, show all their tasks for today
        recent_activity = filtered_tasks.order_by('-updated_at')
    else:
        recent_activity = filtered_tasks.order_by('-updated_at')[:10]
    
    # Get urgent/re-clean requests - include missed tasks from all dates
    urgent_requests = all_tasks.filter(
        Q(task_type='requested') | 
        Q(state='missed') | 
        (Q(state='planned') & Q(task_date__lt=today))
    ).order_by('-created_at')[:5]
    
    # Get cleaner's team and route information
    cleaner_teams = []
    cleaner_routes = []
    urgent_cleaning_requests_count = 0
    if user_role == 'cleaner':
        # Get teams the cleaner is associated with
        user_teams = []
        leader_team = Team.objects.filter(team_leader=request.user).first()
        if leader_team:
            user_teams.append(leader_team)
        member_teams = Team.objects.filter(members=request.user)
        user_teams.extend(member_teams)
        
        cleaner_teams = user_teams
        
        # Get routes for these teams
        from accounts.models import Route
        cleaner_routes = Route.objects.filter(
            team__in=user_teams,
            is_active=True
        ).select_related('team', 'team__shift').prefetch_related('compounds')
        
        # Get urgent cleaning requests count for cleaner's compounds
        compounds = Compound.objects.filter(
            Q(routes__team__in=user_teams) | Q(routes__isnull=True)
        ).distinct()
        
        urgent_cleaning_requests_count = UrgentCleaningRequest.objects.filter(
            compound__in=compounds,
            status__in=['approved', 'in_progress']
        ).count()
    
    # Determine active team types in the field
    active_teams = Team.objects.filter(is_active=True, camp__in=camps)
    has_cleaning_teams = active_teams.filter(team_type='cleaning').exists()
    has_collection_teams = active_teams.filter(team_type='collection').exists()
    
    # Default to cleaning if no teams are configured yet
    if not has_cleaning_teams and not has_collection_teams:
        has_cleaning_teams = True
        
    # Calculate cleaning-specific KPIs (SQM)
    cleaning_stats = {}
    if has_cleaning_teams:
        cleaning_rooms = Room.objects.filter(is_active=True, camp__in=camps).exclude(space_type='dumpster')
        cleaning_tasks = stats_tasks.exclude(room__space_type='dumpster')
        cleaning_completed = cleaning_tasks.filter(state='done')
        
        total_sqm = cleaning_rooms.aggregate(total=Sum('actual_sqm'))['total'] or Decimal('0.0')
        completed_sqm = cleaning_completed.aggregate(total=Sum('sla_credit_sqm'))['total'] or Decimal('0.0')
        
        cleaning_stats = {
            'total_sqm': total_sqm,
            'completed_sqm': completed_sqm,
            'completion_rate': float((completed_sqm / total_sqm * 100) if total_sqm > 0 else 0)
        }
        
    # Calculate garbage collection-specific KPIs (Dumpster counts)
    collection_stats = {}
    if has_collection_teams:
        collection_rooms = Room.objects.filter(is_active=True, camp__in=camps, space_type='dumpster')
        collection_tasks = stats_tasks.filter(room__space_type='dumpster')
        collection_completed = collection_tasks.filter(state='done')
        
        total_dumpsters = collection_rooms.count()
        collected_dumpsters = collection_completed.count()
        planned_dumpsters = collection_tasks.count()
        
        collection_stats = {
            'total_dumpsters': total_dumpsters,
            'collected_dumpsters': collected_dumpsters,
            'planned_dumpsters': planned_dumpsters,
            'completion_rate': float((collected_dumpsters / planned_dumpsters * 100) if planned_dumpsters > 0 else 0)
        }

    # Per-team daily achievement (today) — powers the team performance chart.
    teams_data = []
    for team in active_teams.select_related('team_leader'):
        tteam = today_tasks.filter(assigned_to_team=team)
        t_total = tteam.count()
        t_done = tteam.filter(state='done').count()
        t_prog = tteam.filter(state='in_progress').count()
        t_remaining = t_total - t_done - t_prog
        if t_remaining < 0:
            t_remaining = 0
        teams_data.append({
            'id': str(team.id),
            'name': team.name,
            'team_type': team.team_type,
            'leader': (team.team_leader.get_full_name() or team.team_leader.username) if team.team_leader else '—',
            'employee_count': team.employee_count,
            'total': t_total,
            'done': t_done,
            'in_progress': t_prog,
            'remaining': t_remaining,
            'completion_rate': round((t_done / t_total * 100) if t_total else 0, 1),
        })
    # Show teams with work first, highest completion on top.
    teams_data.sort(key=lambda t: (t['total'] == 0, -t['completion_rate']))

    # Basic statistics
    context.update({
        'teams_data': teams_data,
        'total_users': User.objects.filter(is_active=True).count(),
        'total_camps': Camp.objects.filter(is_active=True).count(),
        'total_compounds': Compound.objects.filter(is_active=True).count(),
        'total_rooms': Room.objects.filter(is_active=True).count(),
        'total_teams': Team.objects.filter(is_active=True).count(),
        'task_stats': task_stats,
        'compounds_data': compounds_data,
        'active_teams': active_teams,
        'recent_activity': recent_activity,
        'urgent_requests': urgent_requests,
        'today': today,
        'show_all_tasks': show_all_tasks,
        'user_role': user_role,
        'cleaner_teams': cleaner_teams,
        'cleaner_routes': cleaner_routes,
        'show_all_cleaner_tasks': show_all_cleaner_tasks,
        'urgent_cleaning_requests_count': urgent_cleaning_requests_count,
        'has_cleaning_teams': has_cleaning_teams,
        'has_collection_teams': has_collection_teams,
        'cleaning_stats': cleaning_stats,
        'collection_stats': collection_stats,
    })
    
    return render(request, 'dashboard/dashboard.html', context)