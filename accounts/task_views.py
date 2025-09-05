"""
Task generation and management views.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from datetime import date, timedelta
from decimal import Decimal
import json

from .task_generation import TaskGenerationService, DailyCleaningTask
# Import functions from existing views.py
from .views import check_permission, log_audit_event
from locations.models import Camp, Compound
from .models import Team, Shift, Route


@login_required
def task_generation_dashboard(request):
    """Task generation dashboard."""
    if not check_permission(request, ['admin', 'manager']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    # Get user's camp
    user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
    
    # Get camps for dropdown
    if request.user.profile.role == 'admin':
        camps = Camp.objects.filter(is_active=True)
    else:
        camps = Camp.objects.filter(is_active=True, id=user_camp.id) if user_camp else []
    
    # Get recent task generation stats
    recent_tasks = DailyCleaningTask.objects.filter(
        room__camp__in=camps,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).select_related('room', 'assigned_to_team')
    
    stats = {
        'total_tasks': recent_tasks.count(),
        'completed_tasks': recent_tasks.filter(state='done').count(),
        'missed_tasks': recent_tasks.filter(state='missed').count(),
        'planned_tasks': recent_tasks.filter(state='planned').count(),
    }
    
    # Calculate SLA percentage
    if stats['total_tasks'] > 0:
        stats['sla_percentage'] = (stats['completed_tasks'] / stats['total_tasks']) * 100
    else:
        stats['sla_percentage'] = 0
    
    # Get additional stats for the dashboard
    from locations.models import Room
    from .models import Route
    
    total_rooms = Room.objects.filter(camp__in=camps, is_active=True).count()
    pending_tasks = DailyCleaningTask.objects.filter(
        room__camp__in=camps,
        state__in=['planned', 'in_progress']
    ).count()
    active_routes = Route.objects.filter(team__camp__in=camps, is_active=True).count()
    
    context = {
        'camps': camps,
        'stats': stats,
        'total_rooms': total_rooms,
        'pending_tasks': pending_tasks,
        'active_routes': active_routes,
        'page_title': 'TASK GENERATION',
        'page_subtitle': 'Generate and manage daily cleaning tasks'
    }
    
    return render(request, 'accounts/task_generation_dashboard.html', context)


@login_required
def task_generation_preview(request):
    """Preview task generation without creating tasks."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        camp_id = data.get('camp_id')
        start_date = date.fromisoformat(data.get('start_date'))
        end_date = date.fromisoformat(data.get('end_date'))
        
        # Get camp
        try:
            camp = Camp.objects.get(id=camp_id)
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        
        # Generate preview
        service = TaskGenerationService(camp)
        results = service.generate_tasks_for_period(start_date, end_date, preview_only=True)
        
        # Format results for display
        formatted_results = {
            'total_rooms': results['total_rooms'],
            'tasks_created': results['tasks_created'],
            'tasks_updated': results['tasks_updated'],
            'errors': results['errors'],
            'sla_summary': {
                'total_weekly_required_sqm': float(results['sla_summary']['total_weekly_required_sqm']),
                'total_monthly_cap_sqm': float(results['sla_summary']['total_monthly_cap_sqm']),
                'estimated_weekly_tasks': results['sla_summary']['estimated_weekly_tasks'],
                'estimated_monthly_tasks': results['sla_summary']['estimated_monthly_tasks']
            },
            'room_details': results['room_details']
        }
        
        return JsonResponse(formatted_results)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def task_generation_execute(request):
    """Execute task generation."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        camp_id = data.get('camp_id')
        start_date = date.fromisoformat(data.get('start_date'))
        end_date = date.fromisoformat(data.get('end_date'))
        
        # Get camp
        try:
            camp = Camp.objects.get(id=camp_id)
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        
        # Execute task generation
        service = TaskGenerationService(camp)
        results = service.generate_tasks_for_period(start_date, end_date, preview_only=False)
        
        # Log audit event
        log_audit_event(
            request,
            'TASK_GENERATION_EXECUTED',
            object_ref=f'camp:{camp.id}',
            details=f'Generated tasks for {start_date} to {end_date}: {results["tasks_created"]} created, {results["tasks_updated"]} updated'
        )
        
        # Format results for display
        formatted_results = {
            'success': True,
            'total_rooms': results['total_rooms'],
            'tasks_created': results['tasks_created'],
            'tasks_updated': results['tasks_updated'],
            'errors': results['errors'],
            'sla_summary': {
                'total_weekly_required_sqm': float(results['sla_summary']['total_weekly_required_sqm']),
                'total_monthly_cap_sqm': float(results['sla_summary']['total_monthly_cap_sqm']),
                'estimated_weekly_tasks': results['sla_summary']['estimated_weekly_tasks'],
                'estimated_monthly_tasks': results['sla_summary']['estimated_monthly_tasks']
            }
        }
        
        return JsonResponse(formatted_results)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def task_list(request):
    """List all daily cleaning tasks."""
    if not check_permission(request, ['admin', 'manager', 'supervisor']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    # Get user's camp
    user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
    
    # Build queryset
    tasks = DailyCleaningTask.objects.select_related(
        'room', 'room__compound', 'room__building', 'room__floor', 'assigned_to_team'
    ).order_by('-task_date', 'room__room_code')
    
    # Filter by camp if not admin
    if request.user.profile.role != 'admin' and user_camp:
        tasks = tasks.filter(room__camp=user_camp)
    
    # Apply filters
    search = request.GET.get('search', '')
    if search:
        tasks = tasks.filter(
            Q(room__room_code__icontains=search) |
            Q(room__room_description__icontains=search) |
            Q(assigned_to_team__name__icontains=search)
        )
    
    state_filter = request.GET.get('state', '')
    if state_filter:
        tasks = tasks.filter(state=state_filter)
    
    date_filter = request.GET.get('date', '')
    if date_filter:
        try:
            filter_date = date.fromisoformat(date_filter)
            tasks = tasks.filter(task_date=filter_date)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(tasks, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    stats = {
        'total_tasks': tasks.count(),
        'completed_tasks': tasks.filter(state='done').count(),
        'missed_tasks': tasks.filter(state='missed').count(),
        'planned_tasks': tasks.filter(state='planned').count(),
        'in_progress_tasks': tasks.filter(state='in_progress').count(),
    }
    
    # Calculate SLA percentage
    if stats['total_tasks'] > 0:
        stats['sla_percentage'] = (stats['completed_tasks'] / stats['total_tasks']) * 100
    else:
        stats['sla_percentage'] = 0
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'state_filter': state_filter,
        'date_filter': date_filter,
        'page_title': 'DAILY CLEANING TASKS',
        'page_subtitle': 'Manage and monitor cleaning tasks'
    }
    
    return render(request, 'accounts/task_list.html', context)


@login_required
def task_detail(request, task_id):
    """View task details."""
    if not check_permission(request, ['admin', 'manager', 'supervisor']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    try:
        task = DailyCleaningTask.objects.select_related(
            'room', 'room__compound', 'room__building', 'room__floor', 
            'assigned_to_team', 'assigned_to_user'
        ).get(id=task_id)
    except DailyCleaningTask.DoesNotExist:
        messages.error(request, "Task not found.")
        return redirect('accounts:task_list')
    
    # Check camp access
    user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
    if request.user.profile.role != 'admin' and user_camp and task.room.camp != user_camp:
        messages.error(request, "You don't have permission to view this task.")
        return redirect('accounts:task_list')
    
    context = {
        'task': task,
        'page_title': 'TASK DETAILS',
        'page_subtitle': f'Task for {task.room.room_code} on {task.task_date}'
    }
    
    return render(request, 'accounts/task_detail.html', context)


@login_required
def task_mark_done(request, task_id):
    """Mark a task as done."""
    if not check_permission(request, ['admin', 'manager', 'supervisor']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        task = DailyCleaningTask.objects.get(id=task_id)
        
        # Check camp access
        user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
        if request.user.profile.role != 'admin' and user_camp and task.room.camp != user_camp:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Update task
        task.state = 'done'
        task.completed_at = timezone.now()
        task.save()
        
        # Log audit event
        log_audit_event(
            request,
            'TASK_MARKED_DONE',
            object_ref=f'task:{task.id}',
            details=f'Marked task {task.room.room_code} as done'
        )
        
        return JsonResponse({'success': True, 'message': 'Task marked as done'})
        
    except DailyCleaningTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def task_assign_team(request, task_id):
    """Assign a task to a team."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        team_id = data.get('team_id')
        
        task = DailyCleaningTask.objects.get(id=task_id)
        
        # Check camp access
        user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
        if request.user.profile.role != 'admin' and user_camp and task.room.camp != user_camp:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Update task
        if team_id:
            from .models import Team
            team = Team.objects.get(id=team_id)
            task.assigned_to_team = team
        else:
            task.assigned_to_team = None
        
        task.save()
        
        # Log audit event
        log_audit_event(
            request,
            'TASK_ASSIGNED_TEAM',
            object_ref=f'task:{task.id}',
            details=f'Assigned task {task.room.room_code} to team {team.name if team_id else "None"}'
        )
        
        return JsonResponse({'success': True, 'message': 'Task assignment updated'})
        
    except DailyCleaningTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
