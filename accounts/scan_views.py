"""
Scan views for cleaner interface.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from locations.models import Room

from .task_generation import DailyCleaningTask
from .views import check_permission, log_audit_event


@login_required
def barcode_scanner(request):
    """Main barcode scanner interface for cleaners."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    # Get today's tasks for the cleaner
    today = timezone.now().date()
    user_teams = []
    
    # Get teams where user is leader or member
    if hasattr(request.user, 'profile'):
        if request.user.profile.is_team_leader:
            user_teams.extend(request.user.led_teams.all())
        user_teams.extend(request.user.teams.all())
    
    # Get tasks for today from user's teams
    today_tasks = DailyCleaningTask.objects.filter(
        Q(assigned_to_team__in=user_teams) | Q(assigned_to_user=request.user),
        task_date=today
    ).select_related('room', 'room__compound', 'room__building').order_by('room__compound__name', 'room__room_code')
    
    context = {
        'today_tasks': today_tasks,
    }
    
    return render(request, 'accounts/barcode_scanner.html', context)


@login_required
def barcode_lookup(request, barcode):
    """Look up task by barcode for cleaners."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Find room by barcode - need to check generated barcode data
        # First try direct room_code match
        room = Room.objects.filter(room_code=barcode).select_related('floor__building__compound__camp').first()
        
        # If not found, check if barcode matches the generated format
        if not room:
            # Parse barcode format: C1-D-B87-R101
            # Try to find room by matching the generated barcode data
            from accounts.barcode_service import BarcodeService
            rooms = Room.objects.filter(is_active=True).select_related('floor__building__compound__camp')
            
            for room_candidate in rooms:
                try:
                    generated_barcode = BarcodeService.generate_barcode_data(room_candidate)
                    if generated_barcode == barcode:
                        room = room_candidate
                        break
                except Exception:
                    continue
        
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found for this barcode'
            })
        
        # Find today's task for this room
        today = timezone.now().date()
        task = DailyCleaningTask.objects.filter(
            room=room,
            task_date=today
        ).select_related('room', 'assigned_to_team', 'assigned_to_user').first()
        
        if not task:
            return JsonResponse({
                'success': True,
                'task': None,
                'message': f'No task found for room {room.room_code} today'
            })
        
        # Check if user can scan this task
        user_can_scan = False
        user_teams = []
        
        if hasattr(request.user, 'profile'):
            if request.user.profile.is_team_leader:
                user_teams.extend(request.user.led_teams.all())
            user_teams.extend(request.user.teams.all())
        
        if task.assigned_to_team in user_teams or task.assigned_to_user == request.user:
            user_can_scan = True
        
        if not user_can_scan:
            return JsonResponse({
                'success': False,
                'error': 'This task is not assigned to you or your team'
            })
        
        return JsonResponse({
            'success': True,
            'task': {
                'id': str(task.id),
                'room_code': task.room.room_code,
                'compound': task.room.compound.name,
                'building': task.room.building.name,
                'state': task.state,
                'state_display': task.get_state_display()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error looking up barcode: {str(e)}'
        })


@login_required
def scan_task(request, task_id):
    """Scan interface for a specific task."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    task = get_object_or_404(DailyCleaningTask, id=task_id)
    
    # Check if task is assigned to the user or their team
    user_can_scan = False
    user_teams = []
    
    if hasattr(request.user, 'profile'):
        if request.user.profile.is_team_leader:
            user_teams.extend(request.user.led_teams.all())
        user_teams.extend(request.user.teams.all())
    
    if task.assigned_to_team in user_teams or task.assigned_to_user == request.user:
        user_can_scan = True
    
    if not user_can_scan:
        messages.error(request, "You don't have permission to scan this task.")
        return redirect('dashboard:dashboard')
    
    context = {
        'task': task,
        'room': task.room,
        'compound': task.room.compound,
        'building': task.room.building,
    }
    
    return render(request, 'accounts/scan_task.html', context)


@login_required
@require_http_methods(["POST"])
def mark_task_scanned(request, task_id):
    """Mark a task as completed after scanning."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        task = DailyCleaningTask.objects.get(id=task_id)
        
        # Check if task is assigned to the user or their team
        user_can_scan = False
        user_teams = []
        
        if hasattr(request.user, 'profile'):
            if request.user.profile.is_team_leader:
                user_teams.extend(request.user.led_teams.all())
            user_teams.extend(request.user.teams.all())
        
        if task.assigned_to_team in user_teams or task.assigned_to_user == request.user:
            user_can_scan = True
        
        if not user_can_scan:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Mark task as done
        task.state = 'done'
        task.completed_at = timezone.now()
        task.save()
        
        # Log audit event
        log_audit_event(
            request,
            'TASK_SCANNED_COMPLETED',
            object_ref=f'task:{task.id}',
            details=f'Task {task.room.room_code} marked as completed via scan'
        )
        
        return JsonResponse({
            'success': True, 
            'message': f'Task {task.room.room_code} completed successfully!',
            'task_id': str(task.id)
        })
        
    except DailyCleaningTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
