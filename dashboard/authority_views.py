"""
Authority-specific dashboard views.
Provides a restricted interface for contracting authority users.
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.db.models import Count, Q, Sum
from datetime import timedelta, datetime
import json
import calendar
import pytz

from accounts.task_generation import DailyCleaningTask
from accounts.views import get_authority_compound_ids
from accounts.views import check_permission
from locations.models import Compound, Room


def calculate_week_range(today, cutoff_day, cutoff_hour):
    """Calculate week start and end based on camp's week cutoff settings."""
    # cutoff_day: 0=Monday, 6=Sunday
    # cutoff_hour: 0-23
    
    # Get the current day of week (0=Monday, 6=Sunday)
    current_weekday = today.weekday()
    
    # Calculate days to subtract to get to the cutoff day
    days_to_subtract = (current_weekday - cutoff_day) % 7
    
    # Calculate the week start (cutoff day)
    week_start = today - timedelta(days=days_to_subtract)
    
    # If we're before the cutoff hour on the cutoff day, go back one week
    tz = pytz.timezone(settings.TIME_ZONE)
    current_hour = timezone.now().astimezone(tz).hour
    if today == week_start and current_hour < cutoff_hour:
        week_start = week_start - timedelta(days=7)
    
    # Week end is 6 days after week start
    week_end = week_start + timedelta(days=6)
    
    return week_start, week_end


def calculate_month_range(today, cutoff_day, cutoff_hour):
    """Calculate month start and end based on camp's month cutoff settings."""
    # cutoff_day: 0=End of Month, 1-31=specific day
    # cutoff_hour: 0-23
    
    if cutoff_day == 0:
        # End of month cutoff
        month_start = today.replace(day=1)
        # Get last day of current month
        last_day = calendar.monthrange(today.year, today.month)[1]
        month_end = today.replace(day=last_day)
    else:
        # Specific day cutoff
        if today.day >= cutoff_day:
            # We're in the current period
            month_start = today.replace(day=cutoff_day)
            # Next month's cutoff day - 1
            next_month = today.replace(day=1) + timedelta(days=32)
            next_month = next_month.replace(day=1)
            if cutoff_day > calendar.monthrange(next_month.year, next_month.month)[1]:
                # If cutoff day doesn't exist in next month, use last day
                month_end = next_month.replace(day=calendar.monthrange(next_month.year, next_month.month)[1])
            else:
                month_end = next_month.replace(day=cutoff_day) - timedelta(days=1)
        else:
            # We're in the previous period
            prev_month = today.replace(day=1) - timedelta(days=1)
            month_start = prev_month.replace(day=cutoff_day)
            month_end = today.replace(day=cutoff_day) - timedelta(days=1)
    
    # Check if we're before the cutoff hour on the cutoff day
    tz = pytz.timezone(settings.TIME_ZONE)
    current_hour = timezone.now().astimezone(tz).hour
    if today == month_end and current_hour < cutoff_hour:
        # We're before the cutoff, so we're still in the previous period
        # Move to the previous period
        if cutoff_day == 0:
            # End of month cutoff
            prev_month = today.replace(day=1) - timedelta(days=1)
            month_start = prev_month.replace(day=1)
            month_end = today.replace(day=1) - timedelta(days=1)
        else:
            # Specific day cutoff
            prev_month = today.replace(day=1) - timedelta(days=1)
            month_start = prev_month.replace(day=cutoff_day)
            month_end = today.replace(day=cutoff_day) - timedelta(days=1)
    
    return month_start, month_end


@login_required
def authority_dashboard(request):
    """Dedicated dashboard for authority users - restricted and focused."""
    try:
        # Check if user has proper role (authority, admin, or manager)
        if not hasattr(request.user, 'profile') or request.user.profile.role not in ['authority', 'admin', 'manager']:
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
        
        # Get today's date and calculate time periods based on camp cutoff settings
        tz = pytz.timezone(settings.TIME_ZONE)
        today = timezone.now().astimezone(tz).date()
        
        # Get the camp for cutoff date calculations (assuming all compounds belong to the same camp)
        camp = None
        if assigned_compounds.exists():
            camp = assigned_compounds.first().camp
        
        if camp:
            # Calculate week start/end based on camp's week cutoff settings
            week_start, week_end = calculate_week_range(today, camp.week_cutoff_day, camp.week_cutoff_hour)
            # Calculate month start/end based on camp's month cutoff settings  
            month_start, month_end = calculate_month_range(today, camp.month_cutoff_day, camp.month_cutoff_hour)
        else:
            # Fallback to calendar weeks/months if no camp found
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
            # Show all tasks from assigned compounds, ordered by date (newest first)
            filtered_tasks = all_tasks.order_by('-task_date', '-created_at')
        else:
            # Show only today's tasks by default
            filtered_tasks = all_tasks.filter(task_date=today).order_by('-created_at')
        
        # Calculate comprehensive statistics
        total_tasks = filtered_tasks.count()
        completed_tasks = filtered_tasks.filter(state='done').count()
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
        
        # Calculate weekly and monthly completion rates
        weekly_tasks = all_tasks.filter(task_date__range=[week_start, week_end])
        monthly_tasks = all_tasks.filter(task_date__range=[month_start, month_end])
        
        weekly_completion_rate = (weekly_tasks.filter(state='done').count() / weekly_tasks.count() * 100) if weekly_tasks.count() > 0 else 0
        monthly_completion_rate = (monthly_tasks.filter(state='done').count() / monthly_tasks.count() * 100) if monthly_tasks.count() > 0 else 0
        
        # Build tasks_by_compound data structure
        tasks_by_compound = {}
        for compound in assigned_compounds:
            compound_tasks = all_tasks.filter(room__compound=compound)
            filtered_compound_tasks = compound_tasks.filter(task_date=today) if not show_all_tasks else compound_tasks
            
            # Calculate compound statistics
            total_rooms = compound.rooms.filter(is_active=True).count()
            total_sqm = compound.total_sqm
            
            # Calculate SQM caps based on room cleaning requirements
            from decimal import Decimal
            # Sum up the weekly and monthly requirements from all rooms
            weekly_sqm_cap = compound.rooms.filter(is_active=True).aggregate(
                total=Sum('weekly_required_sqm')
            )['total'] or 0
            monthly_sqm_cap = compound.rooms.filter(is_active=True).aggregate(
                total=Sum('monthly_cap_sqm')
            )['total'] or 0
            
            # Calculate daily SQM completion
            daily_sqm_completed = filtered_compound_tasks.filter(state='done').aggregate(
                total=Sum('room__actual_sqm')
            )['total'] or 0
            
            daily_sqm_completion_rate = min((daily_sqm_completed / total_sqm * 100), 100) if total_sqm > 0 else 0
            
            # Calculate weekly SQM completion
            weekly_sqm_completed = compound_tasks.filter(
                task_date__range=[week_start, week_end],
                state='done'
            ).aggregate(total=Sum('room__actual_sqm'))['total'] or 0
            

            weekly_sqm_completion_rate = min((weekly_sqm_completed / weekly_sqm_cap * 100), 100) if weekly_sqm_cap > 0 else 0
            
            # Calculate monthly SQM completion
            monthly_sqm_completed = compound_tasks.filter(
                task_date__range=[month_start, month_end],
                state='done'
            ).aggregate(total=Sum('room__actual_sqm'))['total'] or 0
            
            monthly_sqm_completion_rate = min((monthly_sqm_completed / monthly_sqm_cap * 100), 100) if monthly_sqm_cap > 0 else 0
            
            # Calculate urgent SQM usage
            urgent_sqm_used = 0
            urgent_sqm_available = 0
            urgent_sqm_usage_percentage = 0
            
            if compound.has_urgent_sqm_quota:
                # Get urgent cleaning requests for this compound
                from locations.models import UrgentCleaningRequest
                urgent_requests = UrgentCleaningRequest.objects.filter(
                    compound=compound,
                    status='completed'  # Only count completed urgent requests for quota
                )
                
                urgent_sqm_used = sum(float(req.requested_sqm) for req in urgent_requests)
                urgent_sqm_available = float(compound.monthly_urgent_sqm_quota or 0) - urgent_sqm_used
                urgent_sqm_usage_percentage = (urgent_sqm_used / float(compound.monthly_urgent_sqm_quota or 1) * 100) if compound.monthly_urgent_sqm_quota else 0
            
            # Daily task statistics
            daily_total = filtered_compound_tasks.count()
            daily_completed = filtered_compound_tasks.filter(state='done').count()
            daily_completion_rate = (daily_completed / daily_total * 100) if daily_total > 0 else 0
            
            # Weekly task statistics
            weekly_compound_tasks = compound_tasks.filter(task_date__range=[week_start, week_end])
            weekly_total = weekly_compound_tasks.count()
            weekly_completed = weekly_compound_tasks.filter(state='done').count()
            weekly_task_completion_rate = (weekly_completed / weekly_total * 100) if weekly_total > 0 else 0
            
            # Monthly task statistics
            monthly_compound_tasks = compound_tasks.filter(task_date__range=[month_start, month_end])
            monthly_total = monthly_compound_tasks.count()
            monthly_completed = monthly_compound_tasks.filter(state='done').count()
            monthly_task_completion_rate = (monthly_completed / monthly_total * 100) if monthly_total > 0 else 0
            
            tasks_by_compound[compound] = {
                # Compound infrastructure data
                'total_rooms': total_rooms,
                'total_sqm': round(total_sqm, 2),
                'weekly_sqm_cap': round(weekly_sqm_cap, 2),
                'monthly_sqm_cap': round(monthly_sqm_cap, 2),
                'has_urgent_sqm_quota': getattr(compound, 'has_urgent_sqm_quota', False),
                'monthly_urgent_sqm_quota': getattr(compound, 'monthly_urgent_sqm_quota', None),
                'weekly_urgent_sqm_quota': getattr(compound, 'weekly_urgent_sqm_quota', None),
                
                # Daily SQM completion metrics
                'daily_sqm_completed': round(daily_sqm_completed, 2),
                'daily_sqm_completion_rate': round(daily_sqm_completion_rate, 1),
                
                # Weekly SQM completion metrics
                'weekly_sqm_completed': round(weekly_sqm_completed, 2),
                'weekly_sqm_completion_rate': round(weekly_sqm_completion_rate, 1),
                
                # Monthly SQM completion metrics
                'monthly_sqm_completed': round(monthly_sqm_completed, 2),
                'monthly_sqm_completion_rate': round(monthly_sqm_completion_rate, 1),
                
                # Urgent SQM usage metrics
                'urgent_sqm_used': round(urgent_sqm_used, 2),
                'urgent_sqm_available': round(urgent_sqm_available, 2),
                'urgent_sqm_usage_percentage': round(urgent_sqm_usage_percentage, 1),
                
                # Time-based task statistics
                'daily_tasks': {
                    'total': daily_total,
                    'completed': daily_completed,
                    'completion_rate': round(daily_completion_rate, 1),
                    'pending': daily_total - daily_completed,
                },
                'weekly_tasks': {
                    'total': weekly_total,
                    'completed': weekly_completed,
                    'completion_rate': round(weekly_task_completion_rate, 1),
                    'pending': weekly_total - weekly_completed,
                },
                'monthly_tasks': {
                    'total': monthly_total,
                    'completed': monthly_completed,
                    'completion_rate': round(monthly_task_completion_rate, 1),
                    'pending': monthly_total - monthly_completed,
                },
            }
        
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
            'recent_tasks': recent_tasks,
            'filtered_tasks': filtered_tasks,  # Add filtered_tasks to context
            'show_all_tasks': show_all_tasks,
            'today': today,
        }
        
        return render(request, 'dashboard/authority_dashboard.html', context)
    
    except Exception as e:
        print(f"Error in authority_dashboard: {e}")
        import traceback
        traceback.print_exc()
        return render(request, 'dashboard/authority_dashboard.html', {
            'error': str(e),
            'user': request.user,
        })


@login_required
def authority_all_tasks(request):
    """Dedicated page for authority users to view all tasks grouped by compound."""
    try:
        # Check if user has proper role (authority, admin, or manager)
        if not hasattr(request.user, 'profile') or request.user.profile.role not in ['authority', 'admin', 'manager']:
            return redirect('accounts:login')
        
        # Get authority user's assigned compounds
        authority_compound_ids = get_authority_compound_ids(request.user)
        if not authority_compound_ids:
            context = {
                'no_assignments': True,
                'user': request.user,
            }
            return render(request, 'dashboard/authority_all_tasks.html', context)
        
        # Get assigned compounds
        assigned_compounds = Compound.objects.filter(
            id__in=authority_compound_ids
        ).select_related('camp').order_by('name')
        
        # Get all tasks from assigned compounds, ordered by compound and date
        all_tasks = DailyCleaningTask.objects.filter(
            room__compound_id__in=authority_compound_ids
        ).select_related('room', 'room__compound', 'room__building', 'assigned_to_team', 'shift')
        
        # Apply date range filtering
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        status_filter = request.GET.get('status')
        
        if start_date:
            all_tasks = all_tasks.filter(task_date__gte=start_date)
        if end_date:
            all_tasks = all_tasks.filter(task_date__lte=end_date)
        if status_filter:
            if status_filter == 'missed':
                # For missed tasks, we need to filter after marking them
                pass  # We'll handle this after marking missed tasks
            else:
                all_tasks = all_tasks.filter(state=status_filter)
            
        all_tasks = all_tasks.order_by('room__compound__name', '-task_date', '-created_at')
        
        # Filter by missed status if requested (now using actual database state)
        if status_filter == 'missed':
            all_tasks = all_tasks.filter(state='missed')
        
        # Group tasks by compound
        tasks_by_compound = {}
        for task in all_tasks:
            compound = task.room.compound
            if compound.id not in tasks_by_compound:
                tasks_by_compound[compound.id] = {
                    'compound': compound,
                    'tasks': []
                }
            tasks_by_compound[compound.id]['tasks'].append(task)
        
        # Calculate summary statistics
        total_tasks = all_tasks.count()
        completed_tasks = all_tasks.filter(state='done').count()
        in_progress_tasks = all_tasks.filter(state='in_progress').count()
        planned_tasks = all_tasks.filter(state='planned').count()
        urgent_tasks = all_tasks.filter(is_urgent=True).count()
        
        context = {
            'user': request.user,
            'assigned_compounds': assigned_compounds,
            'tasks_by_compound': tasks_by_compound,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'planned_tasks': planned_tasks,
            'urgent_tasks': urgent_tasks,
        }
        
        return render(request, 'dashboard/authority_all_tasks.html', context)
    
    except Exception as e:
        print(f"Error in authority_all_tasks: {e}")
        import traceback
        traceback.print_exc()
        return render(request, 'dashboard/authority_all_tasks.html', {
            'error': str(e),
            'user': request.user,
        })


@login_required
def authority_tasks_by_date(request, date_str):
    """Get tasks for a specific date for authority users (AJAX endpoint)."""
    try:
        # Check if user has proper role (authority, admin, or manager)
        if not hasattr(request.user, 'profile') or request.user.profile.role not in ['authority', 'admin', 'manager']:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Get authority user's assigned compounds
        authority_compound_ids = get_authority_compound_ids(request.user)
        if not authority_compound_ids:
            return JsonResponse({'success': False, 'error': 'No compound assignments'}, status=403)
        
        # Parse the date
        from datetime import datetime
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid date format'}, status=400)
        
        # Get tasks for the selected date
        tasks = DailyCleaningTask.objects.filter(
            room__compound_id__in=authority_compound_ids,
            task_date=selected_date
        ).select_related('room', 'room__compound', 'room__building', 'assigned_to_team').order_by('room__compound__name', 'room__room_code')
        
        # Group tasks by compound
        tasks_by_compound = {}
        for task in tasks:
            compound = task.room.compound
            compound_id_str = str(compound.id)  # Convert UUID to string
            if compound_id_str not in tasks_by_compound:
                tasks_by_compound[compound_id_str] = {
                    'compound': {
                        'id': str(compound.id),  # Convert UUID to string
                        'name': compound.name,
                        'camp': compound.camp.name
                    },
                    'tasks': []
                }
            
            # Convert task to dictionary
            task_data = {
                'id': str(task.id),
                'room_code': task.room.room_code,
                'state': task.state,
                'state_display': task.get_state_display(),
                'actual_sqm': float(task.room.actual_sqm) if task.room.actual_sqm else None,
                'assigned_team': task.assigned_to_team.name if task.assigned_to_team else None,
                'is_urgent': task.is_urgent,
                'task_type': task.task_type,
                'created_at': task.created_at.isoformat() if task.created_at else None,
            }
            tasks_by_compound[compound_id_str]['tasks'].append(task_data)
        
        # Calculate summary statistics for the date
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(state='done').count()
        in_progress_tasks = tasks.filter(state='in_progress').count()
        planned_tasks = tasks.filter(state='planned').count()
        urgent_tasks = tasks.filter(is_urgent=True).count()
        
        return JsonResponse({
            'success': True,
            'date': selected_date.isoformat(),
            'tasks_by_compound': tasks_by_compound,
            'summary': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'in_progress_tasks': in_progress_tasks,
                'planned_tasks': planned_tasks,
                'urgent_tasks': urgent_tasks,
            }
        })
    
    except Exception as e:
        print(f"Error in authority_tasks_by_date: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
    tz = pytz.timezone(settings.TIME_ZONE)
    today = timezone.now().astimezone(tz).date()
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


@login_required
def authority_daily_tasks(request, compound_id):
    """Get daily tasks for a specific compound (AJAX endpoint)."""
    try:
        # Check if user is authority
        if not hasattr(request.user, 'profile') or request.user.profile.role != 'authority':
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Get authority user's assigned compounds
        authority_compound_ids = get_authority_compound_ids(request.user)
        if not authority_compound_ids:
            return JsonResponse({'success': False, 'error': 'No compound assignments'}, status=403)
        
        # Check if the requested compound is assigned to this authority user
        if int(compound_id) not in authority_compound_ids:
            return JsonResponse({'success': False, 'error': 'Compound not assigned to user'}, status=403)
        
        # Get the compound
        compound = get_object_or_404(Compound, id=compound_id)
        
        # Get today's tasks for this compound
        tz = pytz.timezone(settings.TIME_ZONE)
        today = timezone.now().astimezone(tz).date()
        daily_tasks = DailyCleaningTask.objects.filter(
            room__compound=compound,
            task_date=today
        ).select_related('room', 'room__building', 'room__compound', 'assigned_to_team')
        
        # Convert to list of dictionaries for JSON response
        tasks_data = []
        for task in daily_tasks:
            tasks_data.append({
                'id': task.id,
                'room': {
                    'name': task.room.name,
                    'building': {
                        'name': task.room.building.name
                    },
                    'compound': {
                        'name': task.room.compound.name
                    },
                    'actual_sqm': float(task.room.actual_sqm) if task.room.actual_sqm else None
                },
                'state': task.state,
                'state_display': task.get_state_display(),
                'task_date': task.task_date.strftime('%Y-%m-%d'),
                'is_urgent': task.is_urgent,
                'task_type': task.task_type,
                'assigned_to_team': task.assigned_to_team.name if task.assigned_to_team else None
            })
        
        return JsonResponse({
            'success': True,
            'tasks': tasks_data,
            'compound_name': compound.name,
            'total_tasks': len(tasks_data)
        })
        
    except Exception as e:
        print(f"Error in authority_daily_tasks: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
