"""
Authority compound progress tracking views.
Provides compound-specific cleaning progress and SLA tracking for Authority users.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg
from django.http import JsonResponse
from datetime import timedelta, datetime
import json

from accounts.models import CompoundAssignment
from accounts.task_generation import DailyCleaningTask
from accounts.views import get_authority_compound_ids, check_permission
from locations.models import Compound, Room


@login_required
def authority_compound_progress(request):
    """
    Authority compound progress dashboard showing SLA-based cleaning progress.
    """
    # Check if user is authority
    if not check_permission(request, ['authority']):
        return redirect('accounts:login')
    
    # Get authority user's assigned compounds
    authority_compound_ids = get_authority_compound_ids(request.user)
    if not authority_compound_ids:
        context = {
            'no_assignments': True,
            'user': request.user,
        }
        return render(request, 'accounts/authority_compound_progress.html', context)
    
    # Get assigned compounds
    assigned_compounds = Compound.objects.filter(
        id__in=authority_compound_ids
    ).select_related('camp').order_by('name')
    
    # Get date range (default to current week)
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    
    # Get date range from request
    start_date = request.GET.get('start_date', week_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', week_end.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = week_start
        end_date = week_end
    
    # Calculate compound progress data
    compound_progress_data = []
    
    for compound in assigned_compounds:
        # Get all tasks for this compound in the date range
        tasks = DailyCleaningTask.objects.filter(
            room__compound=compound,
            task_date__range=[start_date, end_date]
        ).select_related('room', 'assigned_to_team', 'shift')
        
        # Calculate task statistics
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(state='done').count()
        in_progress_tasks = tasks.filter(state='in_progress').count()
        planned_tasks = tasks.filter(state='planned').count()
        missed_tasks = tasks.filter(state='missed').count()
        
        # Calculate SLA metrics
        if total_tasks > 0:
            completion_rate = (completed_tasks / total_tasks) * 100
            sla_performance = completion_rate  # Simple SLA based on completion rate
        else:
            completion_rate = 0
            sla_performance = 0
        
        # Calculate SQM metrics
        total_sqm = tasks.aggregate(total=Sum('room__actual_sqm'))['total'] or 0
        completed_sqm = tasks.filter(state='done').aggregate(total=Sum('room__actual_sqm'))['total'] or 0
        
        if total_sqm > 0:
            sqm_completion_rate = (completed_sqm / total_sqm) * 100
        else:
            sqm_completion_rate = 0
        
        # Get room statistics for this compound
        rooms = Room.objects.filter(compound=compound, is_active=True)
        total_rooms = rooms.count()
        total_room_sqm = rooms.aggregate(total=Sum('actual_sqm'))['total'] or 0
        
        # Calculate daily progress for the last 7 days
        daily_progress = []
        for i in range(7):
            date = start_date + timedelta(days=i)
            if date <= end_date:
                day_tasks = tasks.filter(task_date=date)
                day_completed = day_tasks.filter(state='done').count()
                day_total = day_tasks.count()
                day_rate = (day_completed / day_total * 100) if day_total > 0 else 0
                
                daily_progress.append({
                    'date': date,
                    'completed': day_completed,
                    'total': day_total,
                    'rate': round(day_rate, 1)
                })
        
        # Determine SLA status
        if sla_performance >= 95:
            sla_status = 'excellent'
            sla_color = 'green'
        elif sla_performance >= 85:
            sla_status = 'good'
            sla_color = 'blue'
        elif sla_performance >= 70:
            sla_status = 'fair'
            sla_color = 'yellow'
        else:
            sla_status = 'poor'
            sla_color = 'red'
        
        compound_progress_data.append({
            'compound': compound,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'planned_tasks': planned_tasks,
            'missed_tasks': missed_tasks,
            'completion_rate': round(completion_rate, 1),
            'sla_performance': round(sla_performance, 1),
            'sla_status': sla_status,
            'sla_color': sla_color,
            'total_sqm': total_sqm,
            'completed_sqm': completed_sqm,
            'sqm_completion_rate': round(sqm_completion_rate, 1),
            'total_rooms': total_rooms,
            'total_room_sqm': total_room_sqm,
            'daily_progress': daily_progress,
        })
    
    # Calculate overall statistics
    total_compounds = len(compound_progress_data)
    overall_completion_rate = sum(cp['completion_rate'] for cp in compound_progress_data) / total_compounds if total_compounds > 0 else 0
    overall_sla_performance = sum(cp['sla_performance'] for cp in compound_progress_data) / total_compounds if total_compounds > 0 else 0
    
    context = {
        'assigned_compounds': assigned_compounds,
        'compound_progress_data': compound_progress_data,
        'start_date': start_date,
        'end_date': end_date,
        'total_compounds': total_compounds,
        'overall_completion_rate': round(overall_completion_rate, 1),
        'overall_sla_performance': round(overall_sla_performance, 1),
        'user': request.user,
    }
    
    return render(request, 'accounts/authority_compound_progress.html', context)


@login_required
def authority_compound_detail(request, compound_id):
    """
    Detailed view of a specific compound's cleaning progress for Authority users.
    """
    # Check if user is authority
    if not check_permission(request, ['authority']):
        return redirect('accounts:login')
    
    # Verify user has access to this compound
    authority_compound_ids = get_authority_compound_ids(request.user)
    if compound_id not in [str(cid) for cid in authority_compound_ids]:
        return redirect('accounts:authority_compound_progress')
    
    compound = get_object_or_404(Compound, id=compound_id)
    
    # Get date range (default to current week)
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get date range from request
    start_date = request.GET.get('start_date', week_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', week_end.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = week_start
        end_date = week_end
    
    # Get all tasks for this compound in the date range
    tasks = DailyCleaningTask.objects.filter(
        room__compound=compound,
        task_date__range=[start_date, end_date]
    ).select_related('room', 'room__building', 'room__floor', 'assigned_to_team', 'shift').order_by('task_date', 'room__building__name', 'room__floor__name', 'room__room_code')
    
    # Group tasks by building
    buildings_data = {}
    for task in tasks:
        building = task.room.building
        if building.id not in buildings_data:
            buildings_data[building.id] = {
                'building': building,
                'tasks': [],
                'total_tasks': 0,
                'completed_tasks': 0,
                'in_progress_tasks': 0,
                'planned_tasks': 0,
                'missed_tasks': 0,
            }
        
        buildings_data[building.id]['tasks'].append(task)
        buildings_data[building.id]['total_tasks'] += 1
        
        if task.state == 'done':
            buildings_data[building.id]['completed_tasks'] += 1
        elif task.state == 'in_progress':
            buildings_data[building.id]['in_progress_tasks'] += 1
        elif task.state == 'planned':
            buildings_data[building.id]['planned_tasks'] += 1
        elif task.state == 'missed':
            buildings_data[building.id]['missed_tasks'] += 1
    
    # Calculate building completion rates
    for building_id, data in buildings_data.items():
        if data['total_tasks'] > 0:
            data['completion_rate'] = round((data['completed_tasks'] / data['total_tasks']) * 100, 1)
        else:
            data['completion_rate'] = 0
    
    # Calculate overall compound statistics
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(state='done').count()
    in_progress_tasks = tasks.filter(state='in_progress').count()
    planned_tasks = tasks.filter(state='planned').count()
    missed_tasks = tasks.filter(state='missed').count()
    
    if total_tasks > 0:
        completion_rate = round((completed_tasks / total_tasks) * 100, 1)
    else:
        completion_rate = 0
    
    # Get room statistics
    rooms = Room.objects.filter(compound=compound, is_active=True)
    total_rooms = rooms.count()
    total_room_sqm = rooms.aggregate(total=Sum('actual_sqm'))['total'] or 0
    
    context = {
        'compound': compound,
        'buildings_data': list(buildings_data.values()),
        'start_date': start_date,
        'end_date': end_date,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'planned_tasks': planned_tasks,
        'missed_tasks': missed_tasks,
        'completion_rate': completion_rate,
        'total_rooms': total_rooms,
        'total_room_sqm': total_room_sqm,
        'user': request.user,
    }
    
    return render(request, 'accounts/authority_compound_detail.html', context)


@login_required
def authority_compound_ajax(request, compound_id):
    """
    AJAX endpoint for compound progress data.
    """
    # Check if user is authority
    if not check_permission(request, ['authority']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Verify user has access to this compound
    authority_compound_ids = get_authority_compound_ids(request.user)
    if compound_id not in [str(cid) for cid in authority_compound_ids]:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    compound = get_object_or_404(Compound, id=compound_id)
    
    # Get date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date or not end_date:
        return JsonResponse({'error': 'Date range required'}, status=400)
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Get tasks for this compound
    tasks = DailyCleaningTask.objects.filter(
        room__compound=compound,
        task_date__range=[start_date, end_date]
    )
    
    # Calculate daily progress
    daily_data = []
    current_date = start_date
    while current_date <= end_date:
        day_tasks = tasks.filter(task_date=current_date)
        day_completed = day_tasks.filter(state='done').count()
        day_total = day_tasks.count()
        day_rate = (day_completed / day_total * 100) if day_total > 0 else 0
        
        daily_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'completed': day_completed,
            'total': day_total,
            'rate': round(day_rate, 1)
        })
        
        current_date += timedelta(days=1)
    
    return JsonResponse({
        'compound_name': compound.name,
        'daily_data': daily_data
    })
