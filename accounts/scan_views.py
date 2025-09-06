"""
Scan views for cleaner interface.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib import messages

from .task_generation import DailyCleaningTask
from .views import check_permission, log_audit_event


@login_required
def scan_task(request, task_id):
    """Scan interface for a specific task."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    task = get_object_or_404(DailyCleaningTask, id=task_id)
    
    # Check if task is assigned to the user or their team
    user_can_scan = False
    if hasattr(request.user, 'profile') and request.user.profile.is_team_leader:
        # Team leader can scan team tasks
        team = Team.objects.filter(team_leader=request.user).first()
        if team and task.assigned_to_team == team:
            user_can_scan = True
    elif task.assigned_to_user == request.user:
        # Individual cleaner can scan their own tasks
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
        if hasattr(request.user, 'profile') and request.user.profile.is_team_leader:
            team = Team.objects.filter(team_leader=request.user).first()
            if team and task.assigned_to_team == team:
                user_can_scan = True
        elif task.assigned_to_user == request.user:
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
