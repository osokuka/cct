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
from locations.models import Room, UrgentCleaningRequest

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
        
        # Check for urgent cleaning requests for this room's compound
        urgent_request = UrgentCleaningRequest.objects.filter(
            compound=room.floor.building.compound,
            status__in=['approved', 'in_progress']
        ).order_by('-priority', '-created_at').first()
        
        if not task and not urgent_request:
            return JsonResponse({
                'success': True,
                'task': None,
                'urgent_request': None,
                'message': f'No task or urgent request found for room {room.room_code} today'
            })
        
        # Prepare response data
        response_data = {
            'success': True,
            'room': {
                'code': room.room_code,
                'compound': room.compound.name,
                'building': room.floor.building.name,
                'floor': room.floor.name
            }
        }
        
        # Handle regular task
        if task:
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
            
            response_data['task'] = {
                'id': str(task.id),
                'type': 'regular',
                'state': task.state,
                'state_display': task.get_state_display()
            }
        
        # Handle urgent request
        if urgent_request:
            response_data['urgent_request'] = {
                'id': str(urgent_request.id),
                'type': 'urgent',
                'title': urgent_request.title,
                'description': urgent_request.description,
                'priority': urgent_request.priority,
                'priority_display': urgent_request.get_priority_display(),
                'status': urgent_request.status,
                'status_display': urgent_request.get_status_display(),
                'requested_sqm': str(urgent_request.requested_sqm),
                'estimated_duration': urgent_request.estimated_duration
            }
        
        return JsonResponse(response_data)
        
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


@login_required
@require_http_methods(["POST"])
def mark_urgent_request_completed(request, urgent_request_id):
    """Mark an urgent cleaning request as completed after scanning.
    Requires a scanned barcode that resolves to a room within the same compound.
    """
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        urgent_request = UrgentCleaningRequest.objects.get(id=urgent_request_id)
        
        # Check if the urgent request is in a completable state
        if urgent_request.status not in ['approved', 'in_progress']:
            return JsonResponse({
                'error': f'Cannot complete urgent request in {urgent_request.get_status_display()} status'
            }, status=400)
        
        # Parse JSON body for barcode
        import json
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}
        scanned_barcode = (payload.get('barcode') or '').strip()
        if not scanned_barcode:
            return JsonResponse({'error': 'Scanned barcode is required to complete this urgent request'}, status=400)
        
        # Resolve barcode to a Room (support direct room_code or generated barcode format)
        from accounts.barcode_service import BarcodeService
        from locations.models import Room
        matched_room = Room.objects.filter(room_code=scanned_barcode).select_related('floor__building__compound').first()
        if not matched_room:
            rooms = Room.objects.filter(is_active=True).select_related('floor__building__compound')
            for candidate in rooms:
                try:
                    if BarcodeService.generate_barcode_data(candidate) == scanned_barcode:
                        matched_room = candidate
                        break
                except Exception:
                    continue
        if not matched_room:
            return JsonResponse({'error': 'Barcode did not match any room'}, status=400)
        
        # Enforce room belongs to the same compound as the urgent request
        if matched_room.floor.building.compound_id != urgent_request.compound_id:
            return JsonResponse({'error': 'Scanned room is not in the correct compound for this urgent request'}, status=400)
        
        # Mark urgent request as completed
        urgent_request.status = 'completed'
        urgent_request.completed_at = timezone.now()
        urgent_request.save()
        
        # Log audit event with room details
        log_audit_event(
            request,
            'URGENT_REQUEST_COMPLETED',
            object_ref=f'urgent_request:{urgent_request.id}',
            details=(
                f'Urgent request "{urgent_request.title}" completed via barcode scan. '
                f'Room: {matched_room.room_code} / Building: {matched_room.floor.building.name}'
            )
        )
        
        return JsonResponse({
            'success': True, 
            'message': f'Urgent request "{urgent_request.title}" completed successfully!',
            'urgent_request_id': str(urgent_request.id),
            'room': {
                'code': matched_room.room_code,
                'building': matched_room.floor.building.name,
                'compound': matched_room.floor.building.compound.name,
            }
        })
        
    except UrgentCleaningRequest.DoesNotExist:
        return JsonResponse({'error': 'Urgent request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def urgent_requests_list(request):
    """Cleaner-facing list of active urgent requests (approved or in progress)."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')
    
    # Determine compounds via routes of user's teams
    user_teams = []
    if hasattr(request.user, 'profile'):
        if request.user.profile.is_team_leader:
            user_teams.extend(request.user.led_teams.all())
        user_teams.extend(request.user.teams.all())
    
    from locations.models import Compound
    compounds = Compound.objects.filter(
        Q(routes__team__in=user_teams) | Q(routes__isnull=True)
    ).distinct()
    
    urgent_requests = UrgentCleaningRequest.objects.filter(
        compound__in=compounds,
        status__in=['approved', 'in_progress']
    ).select_related('compound').order_by('-priority', '-created_at')
    
    return render(request, 'accounts/urgent_requests_cleaner.html', {
        'urgent_requests': urgent_requests,
    })
