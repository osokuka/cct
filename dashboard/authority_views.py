"""
Authority-specific dashboard views.
Provides a restricted interface for contracting authority users.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
import json

from accounts.task_generation import DailyCleaningTask
from accounts.views import get_authority_compound_ids
from accounts.views import check_permission
from locations.models import Compound


@login_required
def authority_dashboard(request):
    """Dedicated dashboard for authority users - restricted and focused."""
    # Check if user is authority
    if not hasattr(request.user, 'profile') or request.user.profile.role != 'authority':
        return redirect('accounts:login')
    
    # Get authority user's assigned compounds
    authority_compound_ids = get_authority_compound_ids(request.user)
    if not authority_compound_ids:
        context = {
            'no_assignments': True,
            'user': request.user,
        }
        return render(request, 'dashboard/authority_dashboard.html', context)
    
    # Get assigned compounds
    assigned_compounds = Compound.objects.filter(
        id__in=authority_compound_ids
    ).select_related('camp')
    
    # Get today's date and calculate time periods
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week
    week_end = week_start + timedelta(days=6)  # Sunday of current week
    month_start = today.replace(day=1)  # First day of current month
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)  # Last day of current month
    
    # Get all tasks from assigned compounds
    all_tasks = DailyCleaningTask.objects.filter(
        room__compound_id__in=authority_compound_ids
    ).select_related('room', 'room__compound', 'room__building', 'assigned_to_team', 'shift')
    
    # Filter tasks based on show_all parameter
    show_all_tasks = request.GET.get('show_all', 'false').lower() == 'true'
    if show_all_tasks:
        filtered_tasks = all_tasks
    else:
        # Show only today's tasks by default
        filtered_tasks = all_tasks.filter(task_date=today)
    
    # Calculate comprehensive statistics
    total_tasks = filtered_tasks.count()
    completed_tasks = filtered_tasks.filter(state='completed').count()
    in_progress_tasks = filtered_tasks.filter(state='in_progress').count()
    planned_tasks = filtered_tasks.filter(state='planned').count()
    missed_tasks = filtered_tasks.filter(
        state__in=['planned', 'in_progress'],
        task_date__lt=today
    ).count()
    urgent_tasks = filtered_tasks.filter(is_urgent=True).count()
    reclean_tasks = filtered_tasks.filter(task_type='reclean').count()
    
    # Calculate completion rate
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # Group tasks by compound for detailed view
    tasks_by_compound = {}
    for compound in assigned_compounds:
        compound_tasks = filtered_tasks.filter(room__compound=compound)
        tasks_by_compound[compound] = {
            'total': compound_tasks.count(),
            'completed': compound_tasks.filter(state='completed').count(),
            'in_progress': compound_tasks.filter(state='in_progress').count(),
            'planned': compound_tasks.filter(state='planned').count(),
            'missed': compound_tasks.filter(
                state__in=['planned', 'in_progress'],
                task_date__lt=today
            ).count(),
            'urgent': compound_tasks.filter(is_urgent=True).count(),
            'reclean': compound_tasks.filter(task_type='reclean').count(),
        }
    
    # Calculate weekly and monthly statistics
    weekly_tasks = all_tasks.filter(
        task_date__gte=week_start,
        task_date__lte=week_end
    )
    monthly_tasks = all_tasks.filter(
        task_date__gte=month_start,
        task_date__lte=month_end
    )
    
    weekly_completed = weekly_tasks.filter(state='completed').count()
    monthly_completed = monthly_tasks.filter(state='completed').count()
    
    weekly_completion_rate = (weekly_completed / weekly_tasks.count() * 100) if weekly_tasks.count() > 0 else 0
    monthly_completion_rate = (monthly_completed / monthly_tasks.count() * 100) if monthly_tasks.count() > 0 else 0
    
    # Prepare chart data
    chart_data = {
        'daily': {
            'labels': ['Completed', 'In Progress', 'Planned', 'Missed'],
            'data': [completed_tasks, in_progress_tasks, planned_tasks, missed_tasks],
            'colors': ['#10B981', '#F59E0B', '#3B82F6', '#EF4444']
        },
        'weekly': {
            'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            'data': []
        },
        'monthly': {
            'labels': [],
            'data': []
        }
    }
    
    # Calculate weekly data
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_tasks = weekly_tasks.filter(task_date=day)
        chart_data['weekly']['data'].append(day_tasks.filter(state='completed').count())
    
    # Calculate monthly data (last 30 days)
    for i in range(30):
        day = today - timedelta(days=29-i)
        day_tasks = all_tasks.filter(task_date=day)
        chart_data['monthly']['labels'].append(day.strftime('%m/%d'))
        chart_data['monthly']['data'].append(day_tasks.filter(state='completed').count())
    
    # Recent activity (last 10 tasks)
    recent_tasks = all_tasks.order_by('-created_at')[:10]
    
    context = {
        'user': request.user,
        'assigned_compounds': assigned_compounds,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'planned_tasks': planned_tasks,
        'missed_tasks': missed_tasks,
        'urgent_tasks': urgent_tasks,
        'reclean_tasks': reclean_tasks,
        'completion_rate': round(completion_rate, 1),
        'tasks_by_compound': tasks_by_compound,
        'weekly_completion_rate': round(weekly_completion_rate, 1),
        'monthly_completion_rate': round(monthly_completion_rate, 1),
        'chart_data': json.dumps(chart_data),
        'recent_tasks': recent_tasks,
        'show_all_tasks': show_all_tasks,
        'today': today,
    }
    
    return render(request, 'dashboard/authority_dashboard.html', context)


@login_required
def authority_compound_detail(request, compound_id):
    """Detailed view of a specific compound for authority users."""
    # Check if user is authority
    if not hasattr(request.user, 'profile') or request.user.profile.role != 'authority':
        return redirect('accounts:login')
    
    # Check if user has access to this compound
    authority_compound_ids = get_authority_compound_ids(request.user)
    if compound_id not in [str(cid) for cid in authority_compound_ids]:
        return redirect('dashboard:authority_dashboard')
    
    try:
        compound = Compound.objects.get(id=compound_id)
    except Compound.DoesNotExist:
        return redirect('dashboard:authority_dashboard')
    
    # Get tasks for this compound
    today = timezone.now().date()
    show_all_tasks = request.GET.get('show_all', 'false').lower() == 'true'
    
    tasks = DailyCleaningTask.objects.filter(
        room__compound=compound
    ).select_related('room', 'room__building', 'assigned_to_team', 'shift')
    
    if not show_all_tasks:
        tasks = tasks.filter(task_date=today)
    
    # Group tasks by building
    tasks_by_building = {}
    for task in tasks:
        building = task.room.building
        if building not in tasks_by_building:
            tasks_by_building[building] = []
        tasks_by_building[building].append(task)
    
    context = {
        'compound': compound,
        'tasks_by_building': tasks_by_building,
        'show_all_tasks': show_all_tasks,
        'today': today,
    }
    
    return render(request, 'dashboard/authority_compound_detail.html', context)
