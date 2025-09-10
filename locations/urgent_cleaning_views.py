"""
Views for urgent cleaning request functionality.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator

from .models import UrgentCleaningRequest, Compound, Room
from .urgent_cleaning_forms import UrgentCleaningRequestForm
from accounts.views import check_permission
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum
from decimal import Decimal


def test_urgent_cleaning(request):
    """Simple test view to check URL routing"""
    return HttpResponse("Urgent cleaning test view works!")

def test_urgent_detail(request, request_id):
    """Test view to debug urgent cleaning detail"""
    try:
        request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
        return HttpResponse(f"Request found: {request_obj.title} - {request_obj.compound.name}")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}")


@login_required
def urgent_cleaning_request_list(request):
    """
    List all urgent cleaning requests for the current user.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return redirect('accounts:login')
    # Get user's requests based on role
    if request.user.profile.role == 'authority':
        # Authority users see all requests for their assigned compounds
        from dashboard.authority_views import get_authority_compound_ids
        authority_compound_ids = get_authority_compound_ids(request.user)
        requests = UrgentCleaningRequest.objects.filter(compound_id__in=authority_compound_ids)
    else:
        # Admin and manager see all requests
        requests = UrgentCleaningRequest.objects.all()
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        requests = requests.filter(status=status_filter)
    
    # Filter by compound if provided
    compound_filter = request.GET.get('compound')
    if compound_filter:
        requests = requests.filter(compound_id=compound_filter)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        requests = requests.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(compound__name__icontains=search_query)
        )
    
    # Order by created date (most recent first) to ensure all requests are visible
    requests = requests.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(requests, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get compounds for filter dropdown
    if request.user.profile.role == 'authority':
        compounds = Compound.objects.filter(assignments__user=request.user).distinct()
    else:
        compounds = Compound.objects.filter(is_active=True)
    
    context = {
        'page_obj': page_obj,
        'status_choices': UrgentCleaningRequest.STATUS_CHOICES,
        'compounds': compounds,
        'current_status': status_filter,
        'current_compound': compound_filter,
        'search_query': search_query,
    }
    
    return render(request, 'locations/urgent_cleaning_request_list.html', context)


@login_required
def urgent_cleaning_request_create(request):
    """
    Create a new urgent cleaning request.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return redirect('accounts:login')
    if request.method == 'POST':
        form = UrgentCleaningRequestForm(request.POST, user=request.user)
        if form.is_valid():
            # Check quota availability before saving
            compound = form.cleaned_data['compound']
            requested_sqm = form.cleaned_data['requested_sqm']
            
            # Get monthly quota
            monthly_quota = compound.monthly_urgent_sqm_quota or Decimal('0')
            
            # Calculate used quota for current month
            current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_used = UrgentCleaningRequest.objects.filter(
                compound=compound,
                created_at__gte=current_month,
                status__in=['pending', 'approved', 'in_progress', 'completed']
            ).aggregate(total=Sum('requested_sqm'))['total'] or Decimal('0')
            
            # Calculate available quota
            monthly_available = monthly_quota - monthly_used
            
            if requested_sqm > monthly_available:
                messages.error(
                    request, 
                    f'Insufficient urgent cleaning quota! Available: {monthly_available} m², Requested: {requested_sqm} m²'
                )
                return render(request, 'locations/urgent_cleaning_request_form.html', {
                    'form': form,
                    'title': 'Create Urgent Cleaning Request',
                })
            
            request_obj = form.save(commit=False)
            request_obj.requested_by = request.user
            request_obj.save()
            
            messages.success(
                request, 
                f'Urgent cleaning request "{request_obj.title}" has been submitted successfully!'
            )
            return redirect('locations:urgent_cleaning_request_detail', request_id=request_obj.id)
    else:
        form = UrgentCleaningRequestForm(user=request.user)
        
        # Pre-fill compound if provided in URL
        compound_id = request.GET.get('compound')
        if compound_id:
            try:
                compound = Compound.objects.get(id=compound_id)
                form.fields['compound'].initial = compound
                # Also set in form initial data for room loading
                form.initial['compound'] = compound
            except Compound.DoesNotExist:
                pass
    
    context = {
        'form': form,
        'title': 'Create Urgent Cleaning Request',
    }
    
    return render(request, 'locations/urgent_cleaning_request_form.html', context)


@login_required
def urgent_cleaning_request_detail(request, request_id):
    """
    View details of a specific urgent cleaning request.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return redirect('accounts:login')
    request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
    
    # Check if user has permission to view this request
    if request.user.profile.role == 'authority':
        from dashboard.authority_views import get_authority_compound_ids
        authority_compound_ids = get_authority_compound_ids(request.user)
        if request_obj.compound_id not in authority_compound_ids:
            messages.error(request, 'You do not have permission to view this request.')
            return redirect('locations:urgent_cleaning_request_list')
    
    # Calculate quota information
    compound = request_obj.compound
    monthly_quota = compound.monthly_urgent_sqm_quota or Decimal('0')
    
    # Calculate used quota for this month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_used = UrgentCleaningRequest.objects.filter(
        compound=compound,
        status='completed',  # Only count completed urgent requests for quota
        created_at__gte=month_start
    ).aggregate(total=Sum('requested_sqm'))['total'] or Decimal('0')
    
    # Calculate remaining quota
    monthly_remaining = monthly_quota - monthly_used
    
    # Calculate percentage for progress bar
    monthly_percentage = 0
    if monthly_quota > 0:
        monthly_percentage = float((monthly_used / monthly_quota) * 100)
    
    context = {
        'request_obj': request_obj,
        'monthly_quota': monthly_quota,
        'monthly_used': monthly_used,
        'monthly_remaining': monthly_remaining,
        'monthly_percentage': monthly_percentage,
    }
    
    return render(request, 'locations/urgent_cleaning_request_detail.html', context)


@csrf_exempt
@login_required
def urgent_cleaning_request_approve(request, request_id):
    """
    Approve an urgent cleaning request (admin and manager only).
    """
    if not check_permission(request, ['admin', 'manager']):
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
    
    if request_obj.status != 'pending':
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Only pending requests can be approved.'})
        messages.error(request, 'Only pending requests can be approved.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        request_obj.status = 'approved'
        request_obj.approved_by = request.user
        request_obj.approved_at = timezone.now()
        request_obj.save()
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': f'Request "{request_obj.title}" has been approved.'})
        
        messages.success(request, f'Request "{request_obj.title}" has been approved.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    # For GET requests, redirect to the detail page
    return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)


@csrf_exempt
@login_required
def urgent_cleaning_request_reject(request, request_id):
    """
    Reject an urgent cleaning request (admin and manager only).
    """
    if not check_permission(request, ['admin', 'manager']):
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
    
    if request_obj.status != 'pending':
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Only pending requests can be rejected.'})
        messages.error(request, 'Only pending requests can be rejected.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        import json
        data = json.loads(request.body) if request.headers.get('Content-Type') == 'application/json' else request.POST
        reason = data.get('reason', 'No reason provided')
        
        request_obj.status = 'rejected'
        request_obj.approved_by = request.user
        request_obj.approved_at = timezone.now()
        request_obj.notes = f"Rejected: {reason}\n\n{request_obj.notes or ''}"
        request_obj.save()
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': f'Request "{request_obj.title}" has been rejected.'})
        
        messages.success(request, f'Request "{request_obj.title}" has been rejected.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    # For GET requests, redirect to the detail page
    return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)


@csrf_exempt
@login_required
def urgent_cleaning_request_complete(request, request_id):
    """
    Mark an urgent cleaning request as completed (admin and manager only).
    """
    if not check_permission(request, ['admin', 'manager']):
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
    
    if request_obj.status not in ['approved', 'in_progress']:
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Only approved or in-progress requests can be completed.'})
        messages.error(request, 'Only approved or in-progress requests can be completed.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        request_obj.status = 'completed'
        request_obj.completed_at = timezone.now()
        request_obj.save()
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': f'Request "{request_obj.title}" has been marked as completed.'})
        
        messages.success(request, f'Request "{request_obj.title}" has been marked as completed.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    # For GET requests, redirect to the detail page
    return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)


@csrf_exempt
@login_required
def urgent_cleaning_request_cancel(request, request_id):
    """
    Cancel an urgent cleaning request.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    request_obj = get_object_or_404(UrgentCleaningRequest, id=request_id)
    
    # Check if user has permission to cancel this request
    if (request.user.profile.role == 'authority' and 
        request_obj.requested_by != request.user):
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'You can only cancel your own requests.'})
        messages.error(request, 'You can only cancel your own requests.')
        return redirect('locations:urgent_cleaning_request_list')
    
    if request_obj.status in ['completed', 'rejected', 'cancelled']:
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'error': 'This request cannot be cancelled.'})
        messages.error(request, 'This request cannot be cancelled.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        import json
        data = json.loads(request.body) if request.headers.get('Content-Type') == 'application/json' else request.POST
        reason = data.get('reason', 'No reason provided')
        
        request_obj.status = 'cancelled'
        request_obj.notes = f"Cancelled: {reason}\n\n{request_obj.notes or ''}"
        request_obj.save()
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': f'Request "{request_obj.title}" has been cancelled.'})
        
        messages.success(request, f'Request "{request_obj.title}" has been cancelled.')
        return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)
    
    # For GET requests, redirect to the detail page
    return redirect('locations:urgent_cleaning_request_detail', request_id=request_id)


@login_required
def urgent_cleaning_request_ajax(request):
    """
    AJAX endpoint for creating urgent cleaning requests from the dashboard.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    if request.method == 'POST':
        try:
            compound_id = request.POST.get('compound_id')
            title = request.POST.get('title', 'Urgent Cleaning Request')
            description = request.POST.get('description', 'Urgent cleaning request from dashboard')
            priority = request.POST.get('priority', 'medium')
            requested_sqm = request.POST.get('requested_sqm', '10.0')
            estimated_duration = request.POST.get('estimated_duration', '2')
            
            compound = get_object_or_404(Compound, id=compound_id)
            
            # Check if user has permission to request for this compound
            if (request.user.profile.role == 'authority' and 
                not compound.assignments.filter(user=request.user).exists()):
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to request cleaning for this compound.'
                })
            
            request_obj = UrgentCleaningRequest.objects.create(
                compound=compound,
                requested_by=request.user,
                title=title,
                description=description,
                priority=priority,
                requested_sqm=requested_sqm,
                estimated_duration=estimated_duration
            )
            
            return JsonResponse({
                'success': True,
                'request_id': str(request_obj.id),
                'message': f'Urgent cleaning request submitted successfully! Request ID: {request_obj.id}'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    })


@login_required
def ajax_load_rooms(request):
    """
    AJAX endpoint to load rooms for a specific compound.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    compound_id = request.GET.get('compound_id')
    if not compound_id:
        return JsonResponse({'success': False, 'error': 'Compound ID required'})
    
    try:
        compound = get_object_or_404(Compound, id=compound_id)
        rooms = Room.objects.filter(
            floor__building__compound=compound,
            is_active=True
        ).select_related('floor', 'floor__building').order_by('room_code')
        
        rooms_data = []
        for room in rooms:
            rooms_data.append({
                'id': str(room.id),
                'name': f"{room.floor.building.name} - {room.floor.name} - {room.room_code}",
                'square_meters': float(room.square_meters)
            })
        
        return JsonResponse({
            'success': True,
            'rooms': rooms_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_http_methods(["GET"])
def urgent_requests_for_cleaners(request):
    """Get urgent cleaning requests for cleaners to see in their interface."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Get user's teams to find which compounds they work in
        user_teams = []
        if hasattr(request.user, 'profile'):
            if request.user.profile.is_team_leader:
                user_teams.extend(request.user.led_teams.all())
            user_teams.extend(request.user.teams.all())
        
        # Get compounds where user's teams work through routes
        from accounts.models import Route
        compounds = Compound.objects.filter(
            Q(routes__team__in=user_teams) | Q(routes__isnull=True)  # Include compounds with no specific team assignment
        ).distinct()
        
        # Get urgent requests for these compounds
        urgent_requests = UrgentCleaningRequest.objects.filter(
            compound__in=compounds,
            status__in=['approved', 'in_progress']
        ).select_related('compound').order_by('-priority', '-created_at')
        
        # Serialize urgent requests
        urgent_requests_data = []
        for request_obj in urgent_requests:
            urgent_requests_data.append({
                'id': str(request_obj.id),
                'title': request_obj.title,
                'description': request_obj.description,
                'priority': request_obj.priority,
                'priority_display': request_obj.get_priority_display(),
                'status': request_obj.status,
                'status_display': request_obj.get_status_display(),
                'requested_sqm': str(request_obj.requested_sqm),
                'estimated_duration': request_obj.estimated_duration,
                'compound': request_obj.compound.name,
                'created_at': request_obj.created_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'urgent_requests': urgent_requests_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def ajax_urgent_quota_info(request):
    """
    AJAX endpoint to get urgent cleaning quota information for a compound.
    """
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    compound_id = request.GET.get('compound_id')
    if not compound_id:
        return JsonResponse({'success': False, 'error': 'Compound ID required'})
    
    try:
        compound = get_object_or_404(Compound, id=compound_id)
        
        # Get monthly quota
        monthly_quota = compound.monthly_urgent_sqm_quota or Decimal('0')
        
        # Calculate used quota for current month
        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_used = UrgentCleaningRequest.objects.filter(
            compound=compound,
            created_at__gte=current_month,
            status__in=['pending', 'approved', 'in_progress', 'completed']
        ).aggregate(total=Sum('requested_sqm'))['total'] or Decimal('0')
        
        # Calculate available quota
        monthly_available = monthly_quota - monthly_used
        
        # Calculate usage percentage
        usage_percentage = (monthly_used / monthly_quota * 100) if monthly_quota > 0 else 0
        
        return JsonResponse({
            'success': True,
            'monthly_quota': float(monthly_quota),
            'monthly_used': float(monthly_used),
            'monthly_available': float(monthly_available),
            'usage_percentage': round(float(usage_percentage), 1)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_http_methods(["GET"])
def urgent_requests_for_cleaners(request):
    """Get urgent cleaning requests for cleaners to see in their interface."""
    if not check_permission(request, ['cleaner']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Get user's teams to find which compounds they work in
        user_teams = []
        if hasattr(request.user, 'profile'):
            if request.user.profile.is_team_leader:
                user_teams.extend(request.user.led_teams.all())
            user_teams.extend(request.user.teams.all())
        
        # Get compounds where user's teams work through routes
        from accounts.models import Route
        compounds = Compound.objects.filter(
            Q(routes__team__in=user_teams) | Q(routes__isnull=True)  # Include compounds with no specific team assignment
        ).distinct()
        
        # Get urgent requests for these compounds
        urgent_requests = UrgentCleaningRequest.objects.filter(
            compound__in=compounds,
            status__in=['approved', 'in_progress']
        ).select_related('compound').order_by('-priority', '-created_at')
        
        # Serialize urgent requests
        urgent_requests_data = []
        for request_obj in urgent_requests:
            urgent_requests_data.append({
                'id': str(request_obj.id),
                'title': request_obj.title,
                'description': request_obj.description,
                'priority': request_obj.priority,
                'priority_display': request_obj.get_priority_display(),
                'status': request_obj.status,
                'status_display': request_obj.get_status_display(),
                'requested_sqm': str(request_obj.requested_sqm),
                'estimated_duration': request_obj.estimated_duration,
                'compound': request_obj.compound.name,
                'created_at': request_obj.created_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'urgent_requests': urgent_requests_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
