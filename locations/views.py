"""
Location views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import json

from .models import Camp, Compound, Building, Floor, Room
from .forms import (
    CampCreateForm, CampEditForm, CompoundCreateForm, CompoundEditForm,
    BuildingCreateForm, BuildingEditForm, FloorCreateForm, FloorEditForm,
    RoomCreateForm, RoomEditForm, SiteForm, ZoneForm, DumpsterForm,
)
from .tasks import start_zone_population
from . import geo


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


def _default_map_center():
    """Configurable fallback map center (no site hardcoded in code)."""
    from django.conf import settings
    c = getattr(settings, "MAP_DEFAULT_CENTER", None) or {}
    return {
        "lat": float(c.get("lat", 0.0)),
        "lng": float(c.get("lng", 0.0)),
        "zoom": int(c.get("zoom", 13)),
    }


def _site_map_center(camp):
    """Center the map on a site (city).

    Explicit site coordinates win; otherwise the center is derived from the site's
    own data (zone boundary centroids, then dumpster GPS) so the map always lands on
    the city without hardcoding any coordinates.
    """
    if camp is None:
        return _default_map_center()
    if camp.center_lat is not None and camp.center_lng is not None:
        return camp.map_center

    lats, lngs = [], []
    for z in camp.compounds.all():
        ring = z.boundary_ring
        if ring:
            for p in ring:
                lngs.append(p[0])
                lats.append(p[1])
    if not lats:
        coords = Room.objects.filter(
            camp=camp, latitude__isnull=False, longitude__isnull=False
        ).values_list('latitude', 'longitude')
        for la, lo in coords:
            lats.append(float(la))
            lngs.append(float(lo))
    if lats and lngs:
        return {
            "lat": sum(lats) / len(lats),
            "lng": sum(lngs) / len(lngs),
            "zoom": camp.default_zoom or 13,
        }
    return camp.map_center


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
    """Site (city) management — full-page tabular view with zone counts."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')

    camps = Camp.objects.all().order_by('name')

    search_query = request.GET.get('search')
    status_filter = request.GET.get('status_filter')
    if search_query:
        camps = camps.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))
    if status_filter == 'active':
        camps = camps.filter(is_active=True)
    elif status_filter == 'inactive':
        camps = camps.filter(is_active=False)

    sites = []
    for camp in camps:
        zones = camp.compounds.all()
        sites.append({
            'camp': camp,
            'zone_count': zones.count(),
            'street_count': Building.objects.filter(compound__camp=camp, is_active=True).count(),
        })

    context = {
        'sites': sites,
        'search_query': search_query or '',
        'status_filter': status_filter or '',
    }
    return render(request, 'locations/site_list.html', context)


@login_required
def site_create(request):
    """Create a new Site (city)."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')

    if request.method == 'POST':
        form = SiteForm(request.POST)
        if form.is_valid():
            camp = form.save()
            messages.success(request, f'Site "{camp.name}" created successfully.')
            return redirect('locations:camp_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = SiteForm()

    return render(request, 'locations/site_form.html', {'form': form, 'title': 'Add Site'})


@login_required
def camp_edit(request, camp_id):
    """Edit a Site (city)."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')

    camp = get_object_or_404(Camp, id=camp_id)
    if request.method == 'POST':
        form = SiteForm(request.POST, instance=camp)
        if form.is_valid():
            form.save()
            messages.success(request, f'Site "{camp.name}" updated successfully.')
            return redirect('locations:camp_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = SiteForm(instance=camp)

    return render(request, 'locations/site_form.html',
                  {'form': form, 'camp': camp, 'title': f'Edit Site: {camp.name}'})


@login_required
def site_delete(request, camp_id):
    """Delete a Site (city) and its zones/streets — admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:camp_list')

    camp = get_object_or_404(Camp, id=camp_id)
    if request.method == 'POST':
        name = camp.name
        camp.delete()
        messages.success(request, f'Site "{name}" deleted.')
        return redirect('locations:camp_list')

    return render(request, 'locations/site_confirm_delete.html', {
        'camp': camp,
        'zone_count': camp.compounds.count(),
        'room_count': camp.rooms.count(),
    })


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
    """Zone (city zone) management — full-page tabular view with OSM status."""
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return redirect('accounts:login')

    compounds = Compound.objects.select_related('camp').all().order_by('camp__name', 'name')

    user_role = get_user_role(request)
    if user_role == 'authority' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            compounds = compounds.filter(camp=camp)

    search_query = request.GET.get('search')
    camp_filter = request.GET.get('camp_filter')
    status_filter = request.GET.get('status_filter')
    if search_query:
        compounds = compounds.filter(
            Q(name__icontains=search_query) | Q(code__icontains=search_query) |
            Q(camp__name__icontains=search_query)
        )
    if camp_filter:
        compounds = compounds.filter(camp_id=camp_filter)
    if status_filter == 'active':
        compounds = compounds.filter(is_active=True)
    elif status_filter == 'inactive':
        compounds = compounds.filter(is_active=False)

    context = {
        'zones': compounds,
        'camps': Camp.objects.all().order_by('name'),
        'search_query': search_query or '',
        'camp_filter': camp_filter or '',
        'status_filter': status_filter or '',
    }
    return render(request, 'locations/zone_list.html', context)


@login_required
def zone_create(request):
    """Create a new Zone (city zone) with a map-drawn boundary."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')

    if request.method == 'POST':
        form = ZoneForm(request.POST, request=request)
        if form.is_valid():
            zone = form.save()
            area = zone.compute_area_sqm()
            if area is not None:
                zone.area_sqm = area
                zone.save(update_fields=['area_sqm'])
            Room.objects.filter(compound=zone, space_type='dumpster').update(
                collection_weekday=zone.collection_weekday)
            messages.success(request, f'Zone "{zone.name}" created successfully.')
            return redirect('locations:compound_view', compound_id=zone.id)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ZoneForm(request=request)

    default_camp = None
    if hasattr(request.user, 'profile') and request.user.profile.camp:
        default_camp = request.user.profile.camp
    if default_camp is None:
        default_camp = Camp.objects.filter(is_active=True).order_by('name').first()

    return render(request, 'locations/zone_form.html', {
        'form': form, 'title': 'Add Zone',
        'map_center': _site_map_center(default_camp),
    })


@login_required
def compound_breakdown(request, compound_id):
    """Get compound breakdown data for AJAX requests."""
    if not check_permission(request, ['admin', 'manager', 'authority']):
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
            if room.actual_sqm:
                total_sqm += room.actual_sqm
        
        active_rooms = rooms.filter(is_active=True).count()
        
        # Calculate breakdown by building
        building_breakdown = []
        for building in buildings:
            building_rooms = rooms.filter(building=building)
            
            # Calculate building SQM safely
            building_sqm = 0
            for room in building_rooms:
                if room.actual_sqm:
                    building_sqm += room.actual_sqm
            
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
        return JsonResponse({
            'error': 'Failed to load compound breakdown data',
            'details': str(e)
        }, status=500)


@login_required
def compound_view(request, compound_id):
    """Zone detail: boundary map, streets list, and OSM population control."""
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return redirect('accounts:login')

    compound = get_object_or_404(Compound.objects.select_related('camp'), id=compound_id)

    ring = compound.boundary_ring

    def _street_in_zone(geom):
        """A street belongs to the zone if any part of its geometry falls inside the
        boundary. With no boundary drawn, we can't filter, so keep everything."""
        if not ring:
            return True
        if not geom:
            return True  # manually-added streets with no geometry stay with their zone
        for line in geo._iter_lines(geom):
            for lng, lat in line:
                if geo._ring_contains(lat, lng, ring):
                    return True
            # Also test segment midpoints to catch streets that only cross the edge.
            for p1, p2 in zip(line, line[1:]):
                mlat, mlng = (p1[1] + p2[1]) / 2.0, (p1[0] + p2[0]) / 2.0
                if geo._ring_contains(mlat, mlng, ring):
                    return True
        return False

    buildings = Building.objects.filter(compound=compound).order_by('name')
    street_rows = []
    map_streets = []
    active_in_zone = 0
    for b in buildings:
        geom = None
        if b.geo_polyline:
            try:
                geom = json.loads(b.geo_polyline)
            except (ValueError, TypeError):
                geom = None
        if not _street_in_zone(geom):
            continue
        street_rows.append({
            'building': b,
            'dumpster_count': b.rooms.filter(space_type='dumpster', is_active=True).count(),
        })
        if b.is_active:
            active_in_zone += 1
        if geom:
            map_streets.append({'name': b.name, 'geometry': geom, 'active': b.is_active})

    boundary = None
    if compound.geo_polygon:
        try:
            boundary = json.loads(compound.geo_polygon)
        except (ValueError, TypeError):
            boundary = None

    # Dumpsters in this zone (list + map markers).
    dumpsters = list(
        Room.objects.filter(compound=compound, space_type='dumpster')
        .select_related('building', 'client')
        .order_by('building__name', 'room_code')
    )
    dumpsters_geo = [
        {
            'code': d.room_code,
            'lat': float(d.latitude),
            'lng': float(d.longitude),
            'type': d.dumpster_type,
            'street': d.building.name if d.building else '',
            'client': d.client.client_code if d.client else '',
            'active': d.is_active,
        }
        for d in dumpsters
        if d.latitude is not None and d.longitude is not None
    ]

    context = {
        'zone': compound,
        'streets': street_rows,
        'street_count': active_in_zone,
        'dumpster_count': sum(1 for d in dumpsters if d.is_active),
        'dumpsters': dumpsters,
        'dumpsters_geo': dumpsters_geo,
        'map_center': compound.boundary_center,
        'map_streets': map_streets,
        'boundary': boundary,
        'can_edit': get_user_role(request) in ['admin', 'manager'],
    }
    return render(request, 'locations/zone_detail.html', context)


@login_required
def compound_edit(request, compound_id):
    """Edit a Zone (city zone), including its boundary."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('locations:compound_list')

    compound = get_object_or_404(Compound, id=compound_id)
    if request.method == 'POST':
        form = ZoneForm(request.POST, instance=compound, request=request)
        if form.is_valid():
            zone = form.save()
            area = zone.compute_area_sqm()
            if area is not None:
                zone.area_sqm = area
                zone.save(update_fields=['area_sqm'])
            Room.objects.filter(compound=zone, space_type='dumpster').update(
                collection_weekday=zone.collection_weekday)
            messages.success(request, f'Zone "{compound.name}" updated successfully.')
            return redirect('locations:compound_view', compound_id=compound.id)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ZoneForm(instance=compound, request=request)

    return render(request, 'locations/zone_form.html', {
        'form': form, 'zone': compound, 'title': f'Edit Zone: {compound.name}',
        'map_center': compound.boundary_center if compound.has_boundary else _site_map_center(compound.camp),
    })


@login_required
def zone_delete(request, compound_id):
    """Delete a Zone (city zone) and its streets/service points — admin only."""
    if not check_permission(request, ['admin']):
        return redirect('locations:compound_list')

    compound = get_object_or_404(Compound, id=compound_id)
    if request.method == 'POST':
        name = compound.name
        compound.delete()
        messages.success(request, f'Zone "{name}" deleted.')
        return redirect('locations:compound_list')

    return render(request, 'locations/zone_confirm_delete.html', {
        'zone': compound,
        'street_count': compound.buildings.count(),
        'room_count': compound.rooms.count(),
    })


@login_required
def zone_populate(request, compound_id):
    """Kick off async OSM street population for a zone."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    compound = get_object_or_404(Compound, id=compound_id)
    if not compound.has_boundary:
        msg = 'Draw the zone boundary before populating streets.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('locations:compound_view', compound_id=compound.id)

    if compound.osm_status in ('queued', 'running'):
        msg = 'A population job is already running for this zone.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=409)
        messages.warning(request, msg)
        return redirect('locations:compound_view', compound_id=compound.id)

    replace = request.POST.get('replace') in ('1', 'true', 'on')
    start_zone_population(compound.id, replace=replace)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': 'queued'})
    messages.success(request, 'Street population started. This may take a moment.')
    return redirect('locations:compound_view', compound_id=compound.id)


@login_required
def zone_populate_status(request, compound_id):
    """Poll OSM population status for a zone (JSON)."""
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    compound = get_object_or_404(Compound, id=compound_id)
    return JsonResponse({
        'status': compound.osm_status,
        'message': compound.osm_message or '',
        'street_count': compound.street_count,
        'last_synced_at': compound.osm_last_synced_at.isoformat() if compound.osm_last_synced_at else None,
    })


@login_required
def zone_measure_area(request, compound_id):
    """Measure the zone's surface area (m²) from its boundary, save it, and
    (optionally) generate cleaning/collection tasks for the zone."""
    if not check_permission(request, ['admin', 'manager']):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    if request.method != 'POST':
        return redirect('locations:compound_view', compound_id=compound_id)

    compound = get_object_or_404(Compound, id=compound_id)
    area = compound.compute_area_sqm()
    if area is None:
        msg = 'Draw the zone boundary first so the area can be measured.'
        messages.error(request, msg)
        return redirect('locations:compound_view', compound_id=compound.id)

    compound.area_sqm = area
    compound.save(update_fields=['area_sqm'])

    generate = request.POST.get('generate') in ('1', 'true', 'on')
    result = {'created': 0, 'updated': 0}
    gen_msg = ''
    if generate:
        if compound.assigned_team_id is None or compound.collection_weekday is None:
            gen_msg = (' Assign a team and a collection day to this zone to '
                       'generate tasks.')
        else:
            from datetime import timedelta as _td
            from accounts.task_generation import generate_tasks_for_zone
            try:
                horizon = int(request.POST.get('horizon_days', 28))
            except (TypeError, ValueError):
                horizon = 28
            horizon = max(1, min(horizon, 90))
            start = timezone.localdate()
            result = generate_tasks_for_zone(compound, start, start + _td(days=horizon - 1))
            gen_msg = (f' Generated {result["created"]} task(s) for '
                       f'{compound.assigned_team.name} on '
                       f'{compound.collection_schedule_display}.')

    messages.success(
        request,
        f'Area measured: {area:,.0f} m² ({compound.area_hectares} ha).{gen_msg}'
    )
    return redirect('locations:compound_view', compound_id=compound.id)


# --- Dumpsters (GPS-placed, auto-assigned to zone + nearest street) -----------

def _dumpster_defaults():
    """Sensible service defaults so a GPS-only dumpster satisfies Room validation."""
    from datetime import date, timedelta
    today = date.today()
    return {
        'space_type': 'dumpster',
        'square_meters': Decimal('1.00'),
        'quantity_of_rooms': 1,
        'actual_sqm': Decimal('1.00'),
        'frequency_per_day': Decimal('1'),
        'frequency_per_week': Decimal('6'),
        'max_frequency_per_month': 24,
        'weekly_required_sqm': Decimal('6'),
        'monthly_cap_sqm': Decimal('24'),
        'service_start_date': today,
        'service_end_date': today + timedelta(days=365),
        'weeks_of_service': 52,
    }


def _dumpster_marker(d):
    """Compact payload for rendering a dumpster as a map marker."""
    return {
        'id': str(d.id),
        'code': d.room_code,
        'type': d.dumpster_type or 'household',
        'type_label': d.dumpster_type_label,
        'lat': float(d.latitude) if d.latitude is not None else None,
        'lng': float(d.longitude) if d.longitude is not None else None,
        'zone': d.compound.name if d.compound_id else '',
        'street': d.building.name if d.building_id else '',
    }


def _default_dumpster_street(compound):
    """Fallback street/segment for manually-added dumpsters when a zone has no
    OSM streets nearby."""
    building, _ = Building.objects.get_or_create(
        compound=compound, code='MANUAL',
        defaults={'name': 'Manually added dumpsters'},
    )
    floor, _ = Floor.objects.get_or_create(
        building=building, code='A', defaults={'name': 'Segment A'}
    )
    return building, floor


def _unique_room_code(floor, base):
    """Ensure room_code is unique within the floor."""
    code = base[:100]
    if not Room.objects.filter(floor=floor, room_code=code).exists():
        return code
    i = 1
    while True:
        candidate = f"{base}-{i}"[:100]
        if not Room.objects.filter(floor=floor, room_code=candidate).exists():
            return candidate
        i += 1


@login_required
def dumpster_create(request):
    """Add a single dumpster from GPS; auto-assign to the containing zone and the
    nearest street within it."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = DumpsterForm(request.POST, request=request)
        if form.is_valid():
            lat = form.cleaned_data['latitude']
            lng = form.cleaned_data['longitude']
            zone = geo.find_zone_for_point(lat, lng)
            if zone is None:
                err = ("This GPS point is not inside any zone boundary. "
                       "Pick a point within a drawn zone.")
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': {'__all__': [err]}}, status=400)
                form.add_error(None, err)
            else:
                building, dist = geo.nearest_street(zone, lat, lng)
                if building is None:
                    building, floor = _default_dumpster_street(zone)
                else:
                    floor = building.floors.filter(is_active=True).first() or \
                        Floor.objects.create(building=building, code='A', name='Segment A')

                dumpster = form.save(commit=False)
                dumpster.camp = zone.camp
                dumpster.compound = zone
                dumpster.building = building
                dumpster.floor = floor
                dumpster.building_code = building.code[:20]
                for key, value in _dumpster_defaults().items():
                    setattr(dumpster, key, value)
                # Inherit the zone's collection schedule (day).
                dumpster.collection_weekday = zone.collection_weekday
                base_code = (form.cleaned_data.get('room_code') or f"{zone.code}-D").strip()
                if not form.cleaned_data.get('room_code'):
                    count = Room.objects.filter(compound=zone, space_type='dumpster').count() + 1
                    base_code = f"{zone.code}-D{count:04d}"
                dumpster.room_code = _unique_room_code(floor, base_code)
                if not dumpster.room_description:
                    dumpster.room_description = f"Dumpster — {building.name}"
                dumpster.save()
                msg = (f'Dumpster "{dumpster.room_code}" added to zone "{zone.name}" '
                       f'(street: {building.name}, schedule: {zone.collection_schedule_display}).')
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': msg,
                        'dumpster': _dumpster_marker(dumpster),
                    })
                messages.success(request, msg)
                return redirect('locations:compound_view', compound_id=zone.id)
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DumpsterForm(request=request)

    # Zone boundaries for the click-map + client-side preview.
    zones_payload = []
    zqs = Compound.objects.filter(is_active=True).exclude(geo_polygon__isnull=True).exclude(geo_polygon="").select_related('camp')
    for z in zqs:
        ring = z.boundary_ring
        if ring:
            zones_payload.append({'id': str(z.id), 'name': z.name, 'site': z.camp.name, 'ring': ring})

    # Existing dumpsters so they show on the map right away.
    dumpsters_payload = [
        _dumpster_marker(d)
        for d in Room.objects.filter(
            space_type='dumpster', is_active=True,
            latitude__isnull=False, longitude__isnull=False,
        ).select_related('compound', 'building')
    ]

    return render(request, 'locations/dumpster_form.html', {
        'form': form,
        'title': 'Add Dumpster',
        'zones': zones_payload,
        'dumpsters': dumpsters_payload,
        'map_center': _default_map_center(),
    })


@login_required
def detect_zone(request):
    """AJAX: given lat/lng, report the containing zone + nearest street (for live UI)."""
    if not check_permission(request, ['admin', 'manager', 'authority']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid coordinates'}, status=400)

    zone = geo.find_zone_for_point(lat, lng)
    if zone is None:
        return JsonResponse({'found': False})
    building, dist = geo.nearest_street(zone, lat, lng)
    return JsonResponse({
        'found': True,
        'zone_id': str(zone.id),
        'zone_name': zone.name,
        'site': zone.camp.name,
        'street': building.name if building else None,
        'street_distance_m': round(dist, 1) if dist is not None else None,
        'schedule': zone.collection_schedule_display,
        'scheduled': zone.collection_weekday is not None,
    })


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