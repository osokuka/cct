"""
Field-operator scan views (minimal mobile UI for dumpster collection).
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


def _user_teams(user):
    """Teams the field operator leads or belongs to."""
    teams = []
    if hasattr(user, 'profile'):
        if user.profile.is_team_leader:
            teams.extend(list(user.led_teams.all()))
        teams.extend(list(user.teams.all()))
    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for t in teams:
        if t.id not in seen:
            seen.add(t.id)
            unique.append(t)
    return unique


def _today_dumpster_tasks(user, task_date=None):
    """Today's dumpster collection tasks for the operator's teams."""
    today = task_date or timezone.localdate()
    teams = _user_teams(user)
    return (
        DailyCleaningTask.objects.filter(
            Q(assigned_to_team__in=teams) | Q(assigned_to_user=user),
            task_date=today,
            room__space_type='dumpster',
        )
        .select_related(
            'room', 'room__compound', 'room__building', 'room__client',
            'assigned_to_team',
        )
        .order_by('room__compound__name', 'room__building__name', 'room__room_code')
    )


def _can_scan_task(user, task):
    teams = _user_teams(user)
    return task.assigned_to_user_id == user.id or (
        task.assigned_to_team_id and task.assigned_to_team in teams
    )


@login_required
def barcode_scanner(request):
    """Minimal field-operator home: scan + today's dumpster list (todo / done)."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')

    today = timezone.localdate()
    teams = _user_teams(request.user)
    today_tasks = _today_dumpster_tasks(request.user, today)

    pending = [t for t in today_tasks if t.state != 'done']
    completed = [t for t in today_tasks if t.state == 'done']
    team_names = ', '.join(t.name for t in teams) if teams else 'Unassigned'

    context = {
        'today': today,
        'team_names': team_names,
        'teams': teams,
        'today_tasks': today_tasks,
        'pending_tasks': pending,
        'completed_tasks': completed,
        'pending_count': len(pending),
        'completed_count': len(completed),
        'total_count': len(today_tasks),
    }
    return render(request, 'accounts/barcode_scanner.html', context)


def _resolve_room_by_barcode(barcode):
    """Resolve a barcode to a Room (room_code first, then generated barcode)."""
    barcode = (barcode or '').strip()
    if not barcode:
        return None
    room = Room.objects.filter(room_code=barcode).select_related(
        'compound', 'building', 'floor', 'client'
    ).first()
    if room:
        return room
    from accounts.barcode_service import BarcodeService
    for candidate in Room.objects.filter(is_active=True, space_type='dumpster').select_related(
        'compound', 'building', 'floor', 'client'
    ):
        try:
            if BarcodeService.generate_barcode_data(candidate) == barcode:
                return candidate
        except Exception:
            continue
    return None


@login_required
def barcode_lookup(request, barcode):
    """Look up today's dumpster task by barcode for field operators."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        room = _resolve_room_by_barcode(barcode)
        if not room:
            return JsonResponse({'success': False, 'error': 'Dumpster not found for this barcode'})

        today = timezone.localdate()
        task = DailyCleaningTask.objects.filter(
            room=room, task_date=today
        ).select_related('room', 'assigned_to_team', 'assigned_to_user').first()

        if not task:
            return JsonResponse({
                'success': False,
                'error': f'No collection task for {room.room_code} today',
            })

        if not _can_scan_task(request.user, task):
            return JsonResponse({
                'success': False,
                'error': 'This dumpster is not on your team route today',
            })

        return JsonResponse({
            'success': True,
            'room': {
                'code': room.room_code,
                'zone': room.compound.name if room.compound_id else '',
                'street': room.building.name if room.building_id else '',
                'dumpster_type': room.dumpster_type or 'household',
                'dumpster_type_label': room.dumpster_type_label,
            },
            'task': {
                'id': str(task.id),
                'state': task.state,
                'state_display': task.get_state_display(),
                'already_done': task.state == 'done',
            },
            'redirect': f"/accounts/scan/task/{task.id}/",
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Lookup failed: {e}'})


@login_required
def scan_task(request, task_id):
    """Confirm/complete a specific dumpster collection task."""
    if not check_permission(request, ['cleaner']):
        messages.error(request, "You don't have permission to access this page.")
        return redirect('dashboard:dashboard')

    task = get_object_or_404(
        DailyCleaningTask.objects.select_related(
            'room', 'room__compound', 'room__building', 'room__client'
        ),
        id=task_id,
    )

    if not _can_scan_task(request.user, task):
        messages.error(request, "This dumpster is not on your team route.")
        return redirect('accounts:barcode_scanner')

    return render(request, 'accounts/scan_task.html', {
        'task': task,
        'room': task.room,
        'compound': task.room.compound,
        'building': task.room.building,
    })


@login_required
@require_http_methods(["POST"])
def mark_task_scanned(request, task_id):
    """Mark a dumpster collection task as completed after scanning."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        task = DailyCleaningTask.objects.select_related('room').get(id=task_id)
        if not _can_scan_task(request.user, task):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        if task.state != 'done':
            task.state = 'done'
            task.completed_at = timezone.now()
            task.assigned_to_user = request.user
            task.save(update_fields=['state', 'completed_at', 'assigned_to_user', 'updated_at'])
            if task.room_id:
                task.room.last_collected_at = timezone.now()
                task.room.save(update_fields=['last_collected_at'])

            log_audit_event(
                request,
                'DUMPSTER_COLLECTED',
                object_ref=f'task:{task.id}',
                details=f'Dumpster {task.room.room_code} collected via scan',
            )

        return JsonResponse({
            'success': True,
            'message': f'Dumpster {task.room.room_code} collected',
            'task_id': str(task.id),
            'room_code': task.room.room_code,
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
