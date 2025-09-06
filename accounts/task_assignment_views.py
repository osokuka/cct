"""
Task assignment views for assigning tasks to routes.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
import json

from .views import check_permission, log_audit_event
from .task_generation import DailyCleaningTask
from locations.models import Camp, Compound
from .models import Route, Shift, Team

def calculate_shift_distribution(compound, tasks):
    """Calculate task distribution by shift for a compound"""
    shift_distribution = []
    
    # Get all shifts for this compound's camp
    shifts = Shift.objects.filter(camp=compound.camp, is_active=True).order_by('start_time')
    
    for shift in shifts:
        # Get routes for teams that work this shift and handle this compound
        routes = Route.objects.filter(
            team__shift=shift,
            compounds=compound,
            is_active=True
        ).select_related('team')
        
        # Count tasks assigned to teams that work this shift
        shift_task_count = 0
        shift_sqm_credit = 0
        
        for task in tasks:
            if task.assigned_to_team and task.assigned_to_team.shift == shift:
                # Check if this task's team has a route for this compound
                team_routes = Route.objects.filter(
                    team=task.assigned_to_team,
                    compounds=compound,
                    is_active=True
                )
                if team_routes.exists():
                    shift_task_count += 1
                    shift_sqm_credit += float(task.sla_credit_sqm)
        
        # Get team name if route exists
        team_name = None
        if routes.exists():
            team_name = routes.first().team.name
        
        shift_distribution.append({
            'shift_name': shift.name,
            'shift_id': shift.id,
            'task_count': shift_task_count,
            'sqm_credit': shift_sqm_credit,
            'team_name': team_name,
            'routes': list(routes)
        })
    
    return shift_distribution


@login_required
def task_assignment_dashboard(request):
    """Task assignment dashboard for assigning tasks to routes."""
    if not check_permission(request, ['admin', 'manager']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    # Get user's camp
    user_camp = request.user.profile.camp if hasattr(request.user, 'profile') else None
    
    # Get camps for dropdown
    if request.user.profile.role == 'admin':
        camps = Camp.objects.filter(is_active=True)
    else:
        camps = Camp.objects.filter(is_active=True, id=user_camp.id) if user_camp else Camp.objects.none()
    
    # Get selected camp
    selected_camp_id = request.GET.get('camp')
    selected_camp = None
    if selected_camp_id:
        try:
            selected_camp = Camp.objects.get(id=selected_camp_id)
        except Camp.DoesNotExist:
            pass
    
    # Get all tasks (not just unassigned) for comprehensive view
    all_tasks = DailyCleaningTask.objects.filter(
        room__camp__in=camps
    ).select_related('room', 'room__compound', 'room__building', 'room__floor', 'assigned_to_team', 'shift')
    
    if selected_camp:
        all_tasks = all_tasks.filter(room__camp=selected_camp)
    
    # Filter by authority user compound assignments
    if request.user.profile.role == 'authority':
        from accounts.views import get_authority_compound_ids
        authority_compound_ids = get_authority_compound_ids(request.user)
        if authority_compound_ids:
            all_tasks = all_tasks.filter(room__compound_id__in=authority_compound_ids)
        else:
            # If no compound assignments, show no tasks
            all_tasks = all_tasks.none()
    
    # Get unassigned tasks for assignment
    unassigned_tasks = all_tasks.filter(
        assigned_to_team__isnull=True,
        state__in=['planned', 'in_progress']
    )
    
    # Group all tasks by compound and calculate comprehensive metrics
    tasks_by_compound = {}
    
    # First, initialize all compounds with tasks
    for task in all_tasks:
        compound = task.room.compound
        if compound not in tasks_by_compound:
            # Initialize compound data
            tasks_by_compound[compound] = {
                'tasks': [],
                'unassigned_tasks': [],
                'assigned_tasks': [],
                'completed_tasks': [],
                'missed_tasks': [],
                'urgent_tasks': [],
                'reclean_tasks': [],
                'task_count': 0,
                'unassigned_count': 0,
                'assigned_count': 0,
                'completed_count': 0,
                'missed_count': 0,
                'urgent_count': 0,
                'reclean_count': 0,
                'weekly_required_sqm': 0,
                'monthly_cap_sqm': 0,
                'total_sla_credit': 0,
                'completed_sla_credit': 0,
                'sla_compliance': 0,
                'shift_distribution': []
            }
        
        # Add task to appropriate categories
        tasks_by_compound[compound]['tasks'].append(task)
        tasks_by_compound[compound]['task_count'] += 1
        tasks_by_compound[compound]['total_sla_credit'] += float(task.sla_credit_sqm)
        
        # Categorize tasks
        if task.assigned_to_team is None:
            tasks_by_compound[compound]['unassigned_tasks'].append(task)
            tasks_by_compound[compound]['unassigned_count'] += 1
        else:
            tasks_by_compound[compound]['assigned_tasks'].append(task)
            tasks_by_compound[compound]['assigned_count'] += 1
            
            if task.state == 'done':
                tasks_by_compound[compound]['completed_tasks'].append(task)
                tasks_by_compound[compound]['completed_count'] += 1
                tasks_by_compound[compound]['completed_sla_credit'] += float(task.sla_credit_sqm)
            elif task.state == 'missed':
                tasks_by_compound[compound]['missed_tasks'].append(task)
                tasks_by_compound[compound]['missed_count'] += 1
        
        # Check for urgent or reclean tasks
        if hasattr(task, 'is_urgent') and task.is_urgent:
            tasks_by_compound[compound]['urgent_tasks'].append(task)
            tasks_by_compound[compound]['urgent_count'] += 1
        
        if task.task_type == 'requested':
            tasks_by_compound[compound]['reclean_tasks'].append(task)
            tasks_by_compound[compound]['reclean_count'] += 1
    
    # Calculate SLA metrics for each compound
    from locations.models import Room
    for compound, data in tasks_by_compound.items():
        # Get all rooms in this compound to calculate required SQM
        compound_rooms = Room.objects.filter(compound=compound, is_active=True)
        
        # Calculate weekly required SQM from room data
        weekly_required = sum(float(room.weekly_required_sqm) for room in compound_rooms)
        monthly_cap = sum(float(room.monthly_cap_sqm) for room in compound_rooms)
        
        data['weekly_required_sqm'] = weekly_required
        data['monthly_cap_sqm'] = monthly_cap
        
        # Calculate SLA compliance (based on completed tasks vs required)
        if weekly_required > 0:
            data['sla_compliance'] = min(100, (data['completed_sla_credit'] / weekly_required) * 100)
        else:
            data['sla_compliance'] = 100
        
        # Calculate shift distribution for this compound
        data['shift_distribution'] = calculate_shift_distribution(compound, data['tasks'])
    
    # Get routes for the selected camp (or all camps if none selected) and group by team
    routes_queryset = []
    if selected_camp:
        routes_queryset = Route.objects.filter(
            team__camp=selected_camp,
            is_active=True
        ).select_related('team', 'team__shift').prefetch_related('compounds')
    else:
        # If no camp selected, show routes from all available camps
        routes_queryset = Route.objects.filter(
            team__camp__in=camps,
            is_active=True
        ).select_related('team', 'team__shift').prefetch_related('compounds')
    
    # Filter routes by authority user compound assignments
    if request.user.profile.role == 'authority':
        authority_compound_ids = get_authority_compound_ids(request.user)
        if authority_compound_ids:
            # Filter routes that have compounds assigned to the authority user
            routes_queryset = routes_queryset.filter(compounds__id__in=authority_compound_ids).distinct()
        else:
            # If no compound assignments, show no routes
            routes_queryset = routes_queryset.none()
    
    # Group routes by team to avoid duplicates
    team_data = {}
    for route in routes_queryset:
        team = route.team
        if team.id not in team_data:
            team_data[team.id] = {
                'team': team,
                'compounds': set(),
                'routes': [],
                'total_priority': 0,
                'is_active': False
            }
        
        # Add compounds from this route
        team_data[team.id]['compounds'].update(route.compounds.all())
        team_data[team.id]['routes'].append(route)
        team_data[team.id]['total_priority'] += route.priority
        if route.is_active:
            team_data[team.id]['is_active'] = True
    
    # Convert to list and sort by team name
    routes = []
    for team_id, data in team_data.items():
        routes.append({
            'team': data['team'],
            'compounds': list(data['compounds']),
            'routes': data['routes'],
            'total_priority': data['total_priority'],
            'is_active': data['is_active'],
            'route_count': len(data['routes'])
        })
    
    routes.sort(key=lambda x: x['team'].name)
    
    # Get compounds for route assignment (or all compounds if none selected)
    compounds = []
    if selected_camp:
        compounds = Compound.objects.filter(camp=selected_camp, is_active=True)
    else:
        # If no camp selected, show compounds from all available camps
        compounds = Compound.objects.filter(camp__in=camps, is_active=True)
    
    # Paginate unassigned tasks (for backward compatibility)
    paginator = Paginator(unassigned_tasks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate overall statistics
    total_tasks = all_tasks.count()
    total_unassigned = unassigned_tasks.count()
    total_assigned = all_tasks.filter(assigned_to_team__isnull=False).count()
    total_completed = all_tasks.filter(state='done').count()
    total_missed = all_tasks.filter(state='missed').count()
    total_urgent = all_tasks.filter(is_urgent=True).count() if hasattr(DailyCleaningTask, 'is_urgent') else 0
    total_reclean = all_tasks.filter(task_type='requested').count()
    
    context = {
        'camps': camps,
        'selected_camp': selected_camp,
        'routes': routes,
        'compounds': compounds,
        'page_obj': page_obj,
        'tasks_by_compound': tasks_by_compound,
        'unassigned_count': total_unassigned,
        'total_tasks': total_tasks,
        'total_assigned': total_assigned,
        'total_completed': total_completed,
        'total_missed': total_missed,
        'total_urgent': total_urgent,
        'total_reclean': total_reclean,
        'page_title': 'TASK ASSIGNMENT',
        'page_subtitle': 'Comprehensive task management and assignment'
    }
    
    return render(request, 'accounts/task_assignment_dashboard.html', context)


@login_required
def assign_tasks_to_route(request):
    """Assign multiple tasks to a route."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        data = json.loads(request.body)
        task_ids = data.get('task_ids', [])
        team_id = data.get('team_id')
        
        if not task_ids or not team_id:
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        # Get the team
        team = Team.objects.get(id=team_id)
        
        # Get the first active route for this team (for assignment purposes)
        route = team.routes.filter(is_active=True).first()
        if not route:
            return JsonResponse({'success': False, 'error': 'No active routes found for this team'})
        
        # Get tasks
        tasks = DailyCleaningTask.objects.filter(
            id__in=task_ids,
            assigned_to_team__isnull=True
        )
        
        # Check if tasks can be assigned to this route
        assigned_count = 0
        errors = []
        
        for task in tasks:
            # Assign task to route team
            task.assigned_to_team = route.team
            task.shift = route.team.shift
            task.save()
            assigned_count += 1
            
            # Add compound to route if not already there
            if task.room.compound not in route.compounds.all():
                route.compounds.add(task.room.compound)
            
            # Log audit event
            log_audit_event(
                request,
                'TASK_ASSIGNED_TO_ROUTE',
                object_ref=f'task:{task.id}',
                details=f'Task {task.id} assigned to team {route.team.name} via route {route.id}'
            )
        
        return JsonResponse({
            'success': True,
            'assigned_count': assigned_count,
            'errors': errors,
            'message': f'Successfully assigned {assigned_count} tasks to route'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def bulk_task_assignment(request):
    """Bulk assign tasks based on route coverage."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})
    
    try:
        data = json.loads(request.body)
        camp_id = data.get('camp_id')
        
        if not camp_id:
            return JsonResponse({'success': False, 'error': 'Camp ID required'})
        
        camp = Camp.objects.get(id=camp_id)
        
        # Get all unassigned tasks for this camp
        unassigned_tasks = DailyCleaningTask.objects.filter(
            room__camp=camp,
            assigned_to_team__isnull=True,
            state__in=['planned', 'in_progress']
        ).select_related('room', 'room__compound')
        
        # Get all active routes for this camp
        routes = Route.objects.filter(
            team__camp=camp,
            is_active=True
        ).prefetch_related('compounds')
        
        assigned_count = 0
        errors = []
        
        for task in unassigned_tasks:
            # Find a route that covers this task's compound
            assigned = False
            for route in routes:
                if task.room.compound in route.compounds.all():
                    task.assigned_to_team = route.team
                    task.shift = route.team.shift
                    task.save()
                    assigned_count += 1
                    assigned = True
                    break
            
            if not assigned:
                errors.append(f'No route found for task {task.room.room_code} in compound {task.room.compound.name}')
        
        # Log audit event
        log_audit_event(
            request,
            'BULK_TASK_ASSIGNMENT',
            object_ref=f'camp:{camp.id}',
            details=f'Bulk assigned {assigned_count} tasks for camp {camp.name}'
        )
        
        return JsonResponse({
            'success': True,
            'assigned_count': assigned_count,
            'errors': errors,
            'message': f'Successfully assigned {assigned_count} tasks'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
