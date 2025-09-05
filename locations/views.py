"""
Location views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from .models import Camp, Compound, Building, Floor, Room
from .forms import CampCreateForm, CampEditForm, CompoundCreateForm, CompoundEditForm, BuildingCreateForm, BuildingEditForm, FloorCreateForm, FloorEditForm, RoomCreateForm, RoomEditForm


def get_user_role(request):
    """Helper function to get user role."""
    if hasattr(request.user, 'profile'):
        return request.user.profile.role
    return None


def check_permission(request, required_roles):
    """Check if user has required role."""
    user_role = get_user_role(request)
    if not user_role or user_role not in required_roles:
        messages.error(request, f"You don't have permission to access this page. Your role: {user_role}, Required: {', '.join(required_roles)}")
        return False
    return True


@login_required
def location_list(request):
    """Main location management page - simplified room-centric view."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    # Get all data for filtering and modals
    camps = Camp.objects.all().order_by('name')
    compounds = Compound.objects.select_related('camp').all().order_by('camp__name', 'name')
    rooms = Room.objects.select_related('camp', 'compound', 'building', 'floor').all().order_by('camp__name', 'compound__name', 'building__name', 'floor__name', 'room_code')
    
    # Managers can view all locations (no filtering by camp)
    # Only Authority users are restricted to their assigned camp
    user_role = get_user_role(request)
    if user_role == 'authority' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            compounds = compounds.filter(camp=camp)
            rooms = rooms.filter(camp=camp)
    
    # Apply room filters
    search_query = request.GET.get('search')
    camp_filter = request.GET.get('camp_filter')
    compound_filter = request.GET.get('compound_filter')
    status_filter = request.GET.get('status_filter')
    
    # Search functionality
    if search_query:
        rooms = rooms.filter(
            Q(room_code__icontains=search_query) |
            Q(room_description__icontains=search_query) |
            Q(camp__name__icontains=search_query) |
            Q(compound__name__icontains=search_query) |
            Q(building__name__icontains=search_query) |
            Q(floor__name__icontains=search_query)
        )
    
    # Filter by camp
    if camp_filter:
        rooms = rooms.filter(camp_id=camp_filter)
    
    # Filter by compound
    if compound_filter:
        rooms = rooms.filter(compound_id=compound_filter)
    
    # Filter by status
    if status_filter:
        if status_filter == 'active':
            rooms = rooms.filter(is_active=True)
        elif status_filter == 'inactive':
            rooms = rooms.filter(is_active=False)
    
    # Get all buildings for modals
    buildings = Building.objects.select_related('compound', 'compound__camp').all().order_by('compound__camp__name', 'compound__name', 'name')
    
    # Managers can view all buildings (no filtering by camp)
    # Only Authority users are restricted to their assigned camp
    if user_role == 'authority' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            buildings = buildings.filter(compound__camp=camp)
    
    context = {
        'camps': camps,
        'compounds': compounds,
        'buildings': buildings,
        'rooms': rooms,
        'search_query': search_query,
        'camp_filter': camp_filter,
        'compound_filter': compound_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'locations/location_list.html', context)


@login_required
def camp_list(request):
    """Camp management page - tabular view."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    # Get all camps
    camps = Camp.objects.all().order_by('name')
    
    # Apply filters
    search_query = request.GET.get('search')
    status_filter = request.GET.get('status_filter')
    
    # Search functionality
    if search_query:
        camps = camps.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by status
    if status_filter:
        if status_filter == 'active':
            camps = camps.filter(is_active=True)
        elif status_filter == 'inactive':
            camps = camps.filter(is_active=False)
    
    # Get all data for modals
    compounds = Compound.objects.select_related('camp').all().order_by('camp__name', 'name')
    buildings = Building.objects.select_related('compound', 'compound__camp').all().order_by('compound__camp__name', 'compound__name', 'name')
    
    context = {
        'camps': camps,
        'compounds': compounds,
        'buildings': buildings,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    
    return render(request, 'locations/camp_list.html', context)


@login_required
def camp_create(request):
    """Create a new camp via modal form."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        # Create camp manually since we don't have a form for it
        code = request.POST.get('code')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        location = request.POST.get('location', '')
        is_active = request.POST.get('is_active') == 'on'
        
        if code and name:
            camp = Camp.objects.create(
                code=code,
                name=name,
                description=description,
                location=location,
                is_active=is_active
            )
            messages.success(request, f'Camp "{camp.name}" created successfully.')
            return redirect('locations:camp_list')
        else:
            messages.error(request, 'Please provide both code and name.')
    else:
        messages.error(request, 'Invalid request method.')
    
    return redirect('locations:camp_list')


@login_required
def camp_edit(request, camp_id):
    """Edit a camp - admin only."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    camp = get_object_or_404(Camp, id=camp_id)
    
    if request.method == 'POST':
        form = CampEditForm(request.POST, instance=camp)
        if form.is_valid():
            form.save()
            messages.success(request, f'Camp "{camp.name}" updated successfully.')
            return redirect('locations:camp_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CampEditForm(instance=camp)
    
    context = {
        'form': form,
        'camp': camp,
        'title': f'Edit Camp: {camp.name}'
    }
    
    return render(request, 'locations/camp_edit.html', context)


@login_required
def camp_breakdown(request, camp_id):
    """Get camp breakdown data for AJAX requests."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        camp = get_object_or_404(Camp, id=camp_id)
        
        # Get compounds for this camp
        compounds = Compound.objects.filter(camp=camp).select_related('camp')
        
        # Get buildings for compounds in this camp
        buildings = Building.objects.filter(compound__camp=camp).select_related('compound')
        
        # Get rooms for this camp (rooms have direct camp relationship)
        rooms = Room.objects.filter(camp=camp).select_related('compound', 'building', 'floor')
        
        # Calculate statistics
        total_compounds = compounds.count()
        total_buildings = buildings.count()
        total_rooms = rooms.count()
        
        # Calculate total SQM safely
        total_sqm = 0
        for room in rooms:
            if room.square_meters:
                total_sqm += room.square_meters
        
        active_rooms = rooms.filter(is_active=True).count()
        
        # Calculate breakdown by compound
        compound_breakdown = []
        for compound in compounds:
            compound_buildings = buildings.filter(compound=compound)
            compound_rooms = rooms.filter(compound=compound)
            
            # Calculate compound SQM safely
            compound_sqm = 0
            for room in compound_rooms:
                if room.square_meters:
                    compound_sqm += room.square_meters
            
            compound_breakdown.append({
                'id': compound.id,
                'name': compound.name,
                'code': compound.code,
                'buildings_count': compound_buildings.count(),
                'rooms_count': compound_rooms.count(),
                'total_sqm': compound_sqm
            })
        
        # Calculate breakdown by building
        building_breakdown = []
        for building in buildings:
            building_rooms = rooms.filter(building=building)
            
            # Calculate building SQM safely
            building_sqm = 0
            for room in building_rooms:
                if room.square_meters:
                    building_sqm += room.square_meters
            
            building_breakdown.append({
                'id': building.id,
                'name': building.name,
                'code': building.code,
                'compound_name': building.compound.name,
                'rooms_count': building_rooms.count(),
                'total_sqm': building_sqm
            })
        
        data = {
            'camp': {
                'id': camp.id,
                'name': camp.name,
                'code': camp.code,
                'timezone': camp.timezone,
                'is_active': camp.is_active,
                'week_cutoff_day': camp.week_cutoff_day,
                'week_cutoff_hour': camp.week_cutoff_hour,
                'month_cutoff_day': camp.month_cutoff_day,
                'month_cutoff_hour': camp.month_cutoff_hour,
                'skip_holidays': camp.skip_holidays,
                'created_at': camp.created_at.strftime('%B %d, %Y') if camp.created_at else 'Unknown'
            },
            'statistics': {
                'total_compounds': total_compounds,
                'total_buildings': total_buildings,
                'total_rooms': total_rooms,
                'total_sqm': total_sqm,
                'active_rooms': active_rooms
            },
            'compound_breakdown': compound_breakdown,
            'building_breakdown': building_breakdown
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in camp_breakdown: {error_details}")
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)


@login_required
def compound_list(request):
    """Compound management page - tabular view."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    # Get all compounds with related data
    compounds = Compound.objects.select_related('camp').all().order_by('camp__name', 'name')
    
    # Managers can view all compounds (no filtering by camp)
    # Only Authority users are restricted to their assigned camp
    user_role = get_user_role(request)
    if user_role == 'authority' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            compounds = compounds.filter(camp=camp)
    
    # Apply filters
    search_query = request.GET.get('search')
    camp_filter = request.GET.get('camp_filter')
    status_filter = request.GET.get('status_filter')
    
    # Search functionality
    if search_query:
        compounds = compounds.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(camp__name__icontains=search_query)
        )
    
    # Filter by camp
    if camp_filter:
        compounds = compounds.filter(camp_id=camp_filter)
    
    # Filter by status
    if status_filter:
        if status_filter == 'active':
            compounds = compounds.filter(is_active=True)
        elif status_filter == 'inactive':
            compounds = compounds.filter(is_active=False)
    
    # Get all camps for filter dropdown
    camps = Camp.objects.all().order_by('name')
    
    # Get all data for modals
    buildings = Building.objects.select_related('compound', 'compound__camp').all().order_by('compound__camp__name', 'compound__name', 'name')
    
    context = {
        'compounds': compounds,
        'camps': camps,
        'buildings': buildings,
        'search_query': search_query,
        'camp_filter': camp_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'locations/compound_list.html', context)


@login_required
def compound_breakdown(request, compound_id):
    """Get compound breakdown data for AJAX requests."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        compound = get_object_or_404(Compound, id=compound_id)
        
        # Get buildings for this compound
        buildings = Building.objects.filter(compound=compound).select_related('compound')
        
        # Get rooms for this compound
        rooms = Room.objects.filter(compound=compound).select_related('compound', 'building', 'floor')
        
        # Calculate statistics
        total_buildings = buildings.count()
        total_rooms = rooms.count()
        
        # Calculate total SQM safely
        total_sqm = 0
        for room in rooms:
            if room.square_meters:
                total_sqm += room.square_meters
        
        active_rooms = rooms.filter(is_active=True).count()
        
        # Calculate breakdown by building
        building_breakdown = []
        for building in buildings:
            building_rooms = rooms.filter(building=building)
            
            # Calculate building SQM safely
            building_sqm = 0
            for room in building_rooms:
                if room.square_meters:
                    building_sqm += room.square_meters
            
            building_breakdown.append({
                'id': building.id,
                'name': building.name,
                'code': building.code,
                'rooms': building_rooms.count(),
                'sqm': round(building_sqm, 2)
            })
        
        data = {
            'compound': {
                'id': compound.id,
                'name': compound.name,
                'code': compound.code,
                'camp': compound.camp.name,
                'is_active': compound.is_active,
                'created_at': compound.created_at.strftime('%B %d, %Y') if compound.created_at else 'Unknown'
            },
            'statistics': {
                'total_buildings': total_buildings,
                'total_rooms': total_rooms,
                'total_sqm': round(total_sqm, 2),
                'active_rooms': active_rooms
            },
            'building_breakdown': building_breakdown
        }
        return JsonResponse(data)
        
    except Exception as e:
        print(f"Error in compound_breakdown: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Failed to load compound breakdown data'}, status=500)


@login_required
def compound_view(request, compound_id):
    """View compound details with breakdown information."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    compound = get_object_or_404(Compound, id=compound_id)
    
    # Get buildings and rooms for this compound
    buildings = Building.objects.filter(compound=compound).select_related('compound')
    rooms = Room.objects.filter(compound=compound).select_related('building', 'floor')
    
    # Calculate statistics
    total_buildings = buildings.count()
    total_rooms = rooms.count()
    total_sqm = sum(room.square_meters for room in rooms if room.square_meters)
    active_rooms = rooms.filter(is_active=True).count()
    
    # Get building breakdown
    building_breakdown = []
    for building in buildings:
        building_rooms = rooms.filter(building=building)
        building_sqm = sum(room.square_meters for room in building_rooms if room.square_meters)
        
        building_breakdown.append({
            'id': building.id,
            'name': building.name,
            'code': building.code,
            'rooms_count': building_rooms.count(),
            'total_sqm': building_sqm
        })
    
    context = {
        'compound': compound,
        'total_buildings': total_buildings,
        'total_rooms': total_rooms,
        'total_sqm': total_sqm,
        'active_rooms': active_rooms,
        'building_breakdown': building_breakdown,
    }
    
    return render(request, 'locations/compound_view.html', context)


@login_required
def compound_edit(request, compound_id):
    """Edit compound details - restricted to admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')
    
    compound = get_object_or_404(Compound, id=compound_id)
    
    if request.method == 'POST':
        form = CompoundEditForm(request.POST, instance=compound)
        if form.is_valid():
            form.save()
            messages.success(request, f'Compound "{compound.name}" updated successfully!')
            return redirect('locations:compound_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CompoundEditForm(instance=compound)
    
    context = {
        'form': form,
        'compound': compound,
        'title': f'Edit Compound: {compound.name}'
    }
    
    return render(request, 'locations/compound_edit.html', context)


@login_required
def building_view(request, building_id):
    """View building details - accessible to admin and manager."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    building = get_object_or_404(Building, id=building_id)
    
    # Get rooms for this building
    rooms = Room.objects.filter(building=building).select_related('floor', 'compound', 'camp')
    
    # Calculate statistics
    total_rooms = rooms.count()
    total_sqm = sum(room.square_meters for room in rooms if room.square_meters)
    active_rooms = rooms.filter(is_active=True).count()
    
    # Get floors for this building with room counts
    floors = Floor.objects.filter(building=building).order_by('name')
    floors_with_counts = []
    for floor in floors:
        floor_room_count = rooms.filter(floor=floor).count()
        floors_with_counts.append({
            'floor': floor,
            'room_count': floor_room_count
        })
    
    context = {
        'building': building,
        'rooms': rooms,
        'floors': floors,
        'floors_with_counts': floors_with_counts,
        'total_rooms': total_rooms,
        'total_sqm': total_sqm,
        'active_rooms': active_rooms,
    }
    
    return render(request, 'locations/building_view.html', context)


@login_required
def building_edit(request, building_id):
    """Edit building details - restricted to admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')
    
    building = get_object_or_404(Building, id=building_id)
    
    if request.method == 'POST':
        form = BuildingEditForm(request.POST, instance=building)
        if form.is_valid():
            form.save()
            messages.success(request, f'Building "{building.name}" updated successfully!')
            return redirect('locations:compound_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BuildingEditForm(instance=building)
    
    context = {
        'form': form,
        'building': building,
        'title': f'Edit Building: {building.name}'
    }
    
    return render(request, 'locations/building_edit.html', context)


@login_required
def floor_view(request, floor_id):
    """View floor details - accessible to admin and manager."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    floor = get_object_or_404(Floor, id=floor_id)
    
    # Get rooms for this floor
    rooms = Room.objects.filter(floor=floor).select_related('building', 'compound', 'camp')
    
    # Calculate statistics
    total_rooms = rooms.count()
    total_sqm = sum(room.square_meters for room in rooms if room.square_meters)
    active_rooms = rooms.filter(is_active=True).count()
    
    context = {
        'floor': floor,
        'rooms': rooms,
        'total_rooms': total_rooms,
        'total_sqm': total_sqm,
        'active_rooms': active_rooms,
    }
    
    return render(request, 'locations/floor_view.html', context)


@login_required
def floor_edit(request, floor_id):
    """Edit floor details - restricted to admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')
    
    floor = get_object_or_404(Floor, id=floor_id)
    
    if request.method == 'POST':
        form = FloorEditForm(request.POST, instance=floor)
        if form.is_valid():
            form.save()
            messages.success(request, f'Floor "{floor.name}" updated successfully!')
            return redirect('locations:compound_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = FloorEditForm(instance=floor)
    
    context = {
        'form': form,
        'floor': floor,
        'title': f'Edit Floor: {floor.name}'
    }
    
    return render(request, 'locations/floor_edit.html', context)


@login_required
def compound_create(request):
    """Create a new compound via modal form."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = CompoundCreateForm(request.POST)
        if form.is_valid():
            compound = form.save()
            messages.success(request, f'Compound "{compound.name}" created successfully.')
            return redirect('locations:location_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CompoundCreateForm()
    
    return render(request, 'locations/location_list.html', {'form': form})


@login_required
def building_create(request):
    """Create a new building via modal form."""
    if not check_permission(request, ['admin', 'manager']):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = BuildingCreateForm(request.POST)
        if form.is_valid():
            building = form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'building_id': str(building.id),
                    'building_name': building.name,
                    'building_code': building.code
                })
            messages.success(request, f'Building "{building.name}" created successfully.')
            return redirect('locations:location_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Please correct the errors below.',
                    'errors': form.errors
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BuildingCreateForm()
    
    return render(request, 'locations/location_list.html', {'form': form})


@login_required
def floor_create(request):
    """Create a new floor via modal form."""
    if not check_permission(request, ['admin', 'manager']):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = FloorCreateForm(request.POST)
        if form.is_valid():
            floor = form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'floor_id': str(floor.id),
                    'floor_name': floor.name
                })
            messages.success(request, f'Floor "{floor.name}" created successfully.')
            return redirect('locations:location_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Please correct the errors below.',
                    'errors': form.errors
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = FloorCreateForm()
    
    return render(request, 'locations/location_list.html', {'form': form})


@login_required
def room_create(request):
    """Create a new room."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = RoomCreateForm(request.POST, request=request)
        if form.is_valid():
            room = form.save()
            messages.success(request, f'Room "{room.room_code}" created successfully.')
            return redirect('locations:location_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RoomCreateForm(request=request)
    
    context = {
        'form': form,
        'camps': Camp.objects.all().order_by('name'),
        'compounds': Compound.objects.select_related('camp').all().order_by('camp__name', 'name'),
        'buildings': Building.objects.select_related('compound', 'compound__camp').all().order_by('compound__camp__name', 'compound__name', 'name'),
        'floors': Floor.objects.select_related('building', 'building__compound', 'building__compound__camp').all().order_by('building__compound__camp__name', 'building__compound__name', 'building__name', 'name'),
    }
    
    return render(request, 'locations/room_create.html', context)


@login_required
def room_update(request, room_id):
    """Update an existing room - admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')
    
    room = get_object_or_404(Room, id=room_id)
    
    if request.method == 'POST':
        form = RoomEditForm(request.POST, instance=room, request=request)
        if form.is_valid():
            # Get location data from hidden fields
            camp_id = request.POST.get('camp')
            compound_id = request.POST.get('compound')
            building_id = request.POST.get('building')
            floor_id = request.POST.get('floor')
            
            # Update location fields manually
            if camp_id:
                room.camp_id = camp_id
            if compound_id:
                room.compound_id = compound_id
            if building_id:
                room.building_id = building_id
            if floor_id:
                room.floor_id = floor_id
            
            # Save the form and room
            room = form.save()
            messages.success(request, f'Room "{room.room_code}" updated successfully.')
            return redirect('locations:location_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RoomEditForm(instance=room, request=request)
    
    context = {
        'form': form,
        'room': room,
    }
    
    return render(request, 'locations/room_edit.html', context)


@login_required
def room_view(request, room_id):
    """View room details."""
    if not check_permission(request, ['admin', 'manager', 'supervisor']):
        return redirect('accounts:login')
    
    room = get_object_or_404(Room, id=room_id)
    
    context = {
        'room': room,
    }
    
    return render(request, 'locations/room_view.html', context)


@login_required
def room_delete(request, room_id):
    """Delete a room - admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')
    
    room = get_object_or_404(Room, id=room_id)
    
    if request.method == 'POST':
        room_code = room.room_code
        room.delete()
        messages.success(request, f'Room "{room_code}" deleted successfully.')
        return redirect('locations:location_list')
    
    context = {'room': room}
    return render(request, 'locations/room_confirm_delete.html', context)


# AJAX endpoints for cascading dropdowns
@require_http_methods(["GET"])
def ajax_load_compounds(request):
    """Load compounds for a specific camp."""
    camp_id = request.GET.get('camp_id')
    if camp_id:
        compounds = Compound.objects.filter(camp_id=camp_id).order_by('name')
        data = [{'id': compound.id, 'name': compound.name} for compound in compounds]
    else:
        data = []
    return JsonResponse(data, safe=False)


@require_http_methods(["GET"])
def ajax_load_buildings(request):
    """Load buildings for a specific compound."""
    compound_id = request.GET.get('compound_id')
    if compound_id:
        buildings = Building.objects.filter(compound_id=compound_id).order_by('name')
        data = [{'id': building.id, 'name': building.name, 'building_code': building.code} for building in buildings]
    else:
        data = []
    return JsonResponse(data, safe=False)


@require_http_methods(["GET"])
def ajax_load_floors(request):
    """Load floors for a specific building."""
    building_id = request.GET.get('building_id')
    if building_id:
        floors = Floor.objects.filter(building_id=building_id).order_by('name')
        data = [{'id': floor.id, 'name': floor.name} for floor in floors]
    else:
        data = []
    return JsonResponse(data, safe=False)