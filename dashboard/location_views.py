"""
Location management views for CRUD operations on Camp, Compound, Building, Floor, and Room.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime
import json

from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Floor, Room


@method_decorator(login_required, name='dispatch')
class LocationManagementView(AdminRequiredMixin, TemplateView):
    """
    Main location management interface with tabs for each entity type.
    """
    template_name = 'dashboard/location_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get counts for dashboard
        context['camps_count'] = Camp.objects.count()
        context['compounds_count'] = Compound.objects.count()
        context['buildings_count'] = Building.objects.count()
        context['floors_count'] = Floor.objects.count()
        context['rooms_count'] = Room.objects.filter(is_active=True).count()
        
        return context


@method_decorator(login_required, name='dispatch')
class CampListView(AdminRequiredMixin, View):
    """
    API endpoint for listing camps with pagination and search.
    """
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        per_page = int(request.GET.get('per_page', 25))
        
        camps = Camp.objects.all().order_by('name')
        
        if search:
            camps = camps.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(timezone__icontains=search)
            )
        
        paginator = Paginator(camps, per_page)
        page_obj = paginator.get_page(page)
        
        camps_data = []
        for camp in page_obj:
            camps_data.append({
                'id': str(camp.id),
                'name': camp.name,
                'code': camp.code,
                'timezone': camp.timezone,
                'week_cutoff_day': camp.week_cutoff_day,
                'week_cutoff_hour': camp.week_cutoff_hour,
                'compounds_count': camp.compounds.count(),
                'created_at': camp.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': camp.updated_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({
            'camps': camps_data,
            'total': paginator.count,
            'pages': paginator.num_pages,
            'current_page': page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })
    
    def post(self, request):
        """Create new camp."""
        try:
            data = json.loads(request.body)
            
            camp = Camp.objects.create(
                name=data.get('name'),
                code=data.get('code'),
                timezone=data.get('timezone', 'Europe/Berlin'),
                week_cutoff_day=data.get('week_cutoff_day', 4),
                week_cutoff_hour=data.get('week_cutoff_hour', 18),
                month_cutoff_day=data.get('month_cutoff_day', 25),
                month_cutoff_hour=data.get('month_cutoff_hour', 23),
                skip_holidays=data.get('skip_holidays', True),
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Camp created successfully',
                'camp': {
                    'id': str(camp.id),
                    'name': camp.name,
                    'code': camp.code,
                    'timezone': camp.timezone,
                    'week_cutoff_day': camp.week_cutoff_day,
                    'week_cutoff_hour': camp.week_cutoff_hour,
                    'month_cutoff_day': camp.month_cutoff_day,
                    'month_cutoff_hour': camp.month_cutoff_hour,
                    'skip_holidays': camp.skip_holidays,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class CampCRUDView(AdminRequiredMixin, View):
    """
    CRUD operations for Camp.
    """
    
    def get(self, request, camp_id=None):
        """Get single camp."""
        if camp_id:
            try:
                camp = Camp.objects.get(id=camp_id)
                return JsonResponse({
                    'id': str(camp.id),
                    'name': camp.name,
                    'code': camp.code,
                    'timezone': camp.timezone,
                    'week_cutoff_day': camp.week_cutoff_day,
                    'week_cutoff_hour': camp.week_cutoff_hour,
                    'month_cutoff_day': camp.month_cutoff_day,
                    'month_cutoff_hour': camp.month_cutoff_hour,
                    'skip_holidays': camp.skip_holidays,
                    'created_at': camp.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': camp.updated_at.strftime('%Y-%m-%d %H:%M'),
                })
            except Camp.DoesNotExist:
                return JsonResponse({'error': 'Camp not found'}, status=404)
        else:
            return JsonResponse({'error': 'Camp ID required'}, status=400)
    
    def put(self, request, camp_id):
        """Update camp."""
        try:
            camp = get_object_or_404(Camp, id=camp_id)
            data = json.loads(request.body)
            
            camp.name = data.get('name', camp.name)
            camp.code = data.get('code', camp.code)
            camp.timezone = data.get('timezone', camp.timezone)
            camp.week_cutoff_day = data.get('week_cutoff_day', camp.week_cutoff_day)
            camp.week_cutoff_hour = data.get('week_cutoff_hour', camp.week_cutoff_hour)
            camp.month_cutoff_day = data.get('month_cutoff_day', camp.month_cutoff_day)
            camp.month_cutoff_hour = data.get('month_cutoff_hour', camp.month_cutoff_hour)
            camp.skip_holidays = data.get('skip_holidays', camp.skip_holidays)
            camp.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Camp updated successfully',
                'camp': {
                    'id': str(camp.id),
                    'name': camp.name,
                    'code': camp.code,
                    'timezone': camp.timezone,
                    'week_cutoff_day': camp.week_cutoff_day,
                    'week_cutoff_hour': camp.week_cutoff_hour,
                    'month_cutoff_day': camp.month_cutoff_day,
                    'month_cutoff_hour': camp.month_cutoff_hour,
                    'skip_holidays': camp.skip_holidays,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def delete(self, request, camp_id):
        """Delete camp."""
        try:
            camp = get_object_or_404(Camp, id=camp_id)
            
            # Check if camp has compounds
            if camp.compounds.exists():
                return JsonResponse({
                    'error': 'Cannot delete camp with existing compounds. Please delete compounds first.'
                }, status=400)
            
            camp.delete()
            return JsonResponse({
                'success': True,
                'message': 'Camp deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class CompoundListView(AdminRequiredMixin, View):
    """
    API endpoint for listing compounds with pagination and search.
    """
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        camp_id = request.GET.get('camp_id', '')
        per_page = int(request.GET.get('per_page', 25))
        
        compounds = Compound.objects.select_related('camp').all().order_by('camp__name', 'name')
        
        if search:
            compounds = compounds.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(camp__name__icontains=search)
            )
        
        if camp_id:
            compounds = compounds.filter(camp_id=camp_id)
        
        paginator = Paginator(compounds, per_page)
        page_obj = paginator.get_page(page)
        
        compounds_data = []
        for compound in page_obj:
            compounds_data.append({
                'id': str(compound.id),
                'name': compound.name,
                'code': compound.code,
                'camp_name': compound.camp.name,
                'camp_id': str(compound.camp.id),
                'buildings_count': compound.buildings.count(),
                'created_at': compound.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': compound.updated_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({
            'compounds': compounds_data,
            'total': paginator.count,
            'pages': paginator.num_pages,
            'current_page': page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })


@method_decorator(login_required, name='dispatch')
class CompoundCRUDView(AdminRequiredMixin, View):
    """
    CRUD operations for Compound.
    """
    
    def get(self, request, compound_id=None):
        """Get single compound."""
        if compound_id:
            try:
                compound = Compound.objects.select_related('camp').get(id=compound_id)
                return JsonResponse({
                    'id': str(compound.id),
                    'name': compound.name,
                    'code': compound.code,
                    'camp_id': str(compound.camp.id),
                    'camp_name': compound.camp.name,
                    'is_active': compound.is_active,
                    'description': compound.description,
                    'created_at': compound.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': compound.updated_at.strftime('%Y-%m-%d %H:%M'),
                })
            except Compound.DoesNotExist:
                return JsonResponse({'error': 'Compound not found'}, status=404)
        else:
            return JsonResponse({'error': 'Compound ID required'}, status=400)
    
    def post(self, request):
        """Create new compound."""
        try:
            data = json.loads(request.body)
            
            camp = get_object_or_404(Camp, id=data.get('camp_id'))
            
            compound = Compound.objects.create(
                name=data.get('name'),
                code=data.get('code'),
                camp=camp,
                is_active=data.get('is_active', True),
                description=data.get('description', ''),
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Compound created successfully',
                'compound': {
                    'id': str(compound.id),
                    'name': compound.name,
                    'code': compound.code,
                    'camp_id': str(compound.camp.id),
                    'camp_name': compound.camp.name,
                    'is_active': compound.is_active,
                    'description': compound.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def put(self, request, compound_id):
        """Update compound."""
        try:
            compound = get_object_or_404(Compound, id=compound_id)
            data = json.loads(request.body)
            
            compound.name = data.get('name', compound.name)
            compound.code = data.get('code', compound.code)
            compound.is_active = data.get('is_active', compound.is_active)
            compound.description = data.get('description', compound.description)
            
            if 'camp_id' in data:
                camp = get_object_or_404(Camp, id=data['camp_id'])
                compound.camp = camp
            
            compound.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Compound updated successfully',
                'compound': {
                    'id': str(compound.id),
                    'name': compound.name,
                    'code': compound.code,
                    'camp_id': str(compound.camp.id),
                    'camp_name': compound.camp.name,
                    'is_active': compound.is_active,
                    'description': compound.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def delete(self, request, compound_id):
        """Delete compound."""
        try:
            compound = get_object_or_404(Compound, id=compound_id)
            
            # Check if compound has buildings
            if compound.buildings.exists():
                return JsonResponse({
                    'error': 'Cannot delete compound with existing buildings. Please delete buildings first.'
                }, status=400)
            
            compound.delete()
            return JsonResponse({
                'success': True,
                'message': 'Compound deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class BuildingListView(AdminRequiredMixin, View):
    """
    API endpoint for listing buildings with pagination and search.
    """
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        compound_id = request.GET.get('compound_id', '')
        per_page = int(request.GET.get('per_page', 25))
        
        buildings = Building.objects.select_related('compound__camp').all().order_by('compound__camp__name', 'compound__name', 'name')
        
        if search:
            buildings = buildings.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(compound__name__icontains=search) |
                Q(compound__camp__name__icontains=search)
            )
        
        if compound_id:
            buildings = buildings.filter(compound_id=compound_id)
        
        paginator = Paginator(buildings, per_page)
        page_obj = paginator.get_page(page)
        
        buildings_data = []
        for building in page_obj:
            buildings_data.append({
                'id': str(building.id),
                'name': building.name,
                'code': building.code,
                'compound_name': building.compound.name,
                'compound_id': str(building.compound.id),
                'camp_name': building.compound.camp.name,
                'floors_count': building.floors.count(),
                'created_at': building.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': building.updated_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({
            'buildings': buildings_data,
            'total': paginator.count,
            'pages': paginator.num_pages,
            'current_page': page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })


@method_decorator(login_required, name='dispatch')
class BuildingCRUDView(AdminRequiredMixin, View):
    """
    CRUD operations for Building.
    """
    
    def get(self, request, building_id=None):
        """Get single building."""
        if building_id:
            try:
                building = Building.objects.select_related('compound__camp').get(id=building_id)
                return JsonResponse({
                    'id': str(building.id),
                    'name': building.name,
                    'code': building.code,
                    'compound_id': str(building.compound.id),
                    'compound_name': building.compound.name,
                    'camp_name': building.compound.camp.name,
                    'created_at': building.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': building.updated_at.strftime('%Y-%m-%d %H:%M'),
                })
            except Building.DoesNotExist:
                return JsonResponse({'error': 'Building not found'}, status=404)
        else:
            return JsonResponse({'error': 'Building ID required'}, status=400)
    
    def post(self, request):
        """Create new building."""
        try:
            data = json.loads(request.body)
            
            compound = get_object_or_404(Compound, id=data.get('compound_id'))
            
            building = Building.objects.create(
                name=data.get('name'),
                code=data.get('code'),
                compound=compound,
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Building created successfully',
                'building': {
                    'id': str(building.id),
                    'name': building.name,
                    'code': building.code,
                    'compound_id': str(building.compound.id),
                    'compound_name': building.compound.name,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def put(self, request, building_id):
        """Update building."""
        try:
            building = get_object_or_404(Building, id=building_id)
            data = json.loads(request.body)
            
            building.name = data.get('name', building.name)
            building.code = data.get('code', building.code)
            
            if 'compound_id' in data:
                compound = get_object_or_404(Compound, id=data['compound_id'])
                building.compound = compound
            
            building.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Building updated successfully',
                'building': {
                    'id': str(building.id),
                    'name': building.name,
                    'code': building.code,
                    'compound_id': str(building.compound.id),
                    'compound_name': building.compound.name,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def delete(self, request, building_id):
        """Delete building."""
        try:
            building = get_object_or_404(Building, id=building_id)
            
            # Check if building has floors
            if building.floors.exists():
                return JsonResponse({
                    'error': 'Cannot delete building with existing floors. Please delete floors first.'
                }, status=400)
            
            building.delete()
            return JsonResponse({
                'success': True,
                'message': 'Building deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class FloorListView(AdminRequiredMixin, View):
    """
    API endpoint for listing floors with pagination and search.
    """
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        building_id = request.GET.get('building_id', '')
        per_page = int(request.GET.get('per_page', 25))
        
        floors = Floor.objects.select_related('building__compound__camp').all().order_by('building__compound__camp__name', 'building__compound__name', 'building__name', 'code')
        
        if search:
            floors = floors.filter(
                Q(name__icontains=search) |
                Q(building__name__icontains=search) |
                Q(building__compound__name__icontains=search) |
                Q(building__compound__camp__name__icontains=search)
            )
        
        if building_id:
            floors = floors.filter(building_id=building_id)
        
        paginator = Paginator(floors, per_page)
        page_obj = paginator.get_page(page)
        
        floors_data = []
        for floor in page_obj:
            floors_data.append({
                'id': str(floor.id),
                'name': floor.name,
                'code': floor.code,
                'building_name': floor.building.name,
                'building_id': str(floor.building.id),
                'compound_name': floor.building.compound.name,
                'camp_name': floor.building.compound.camp.name,
                'rooms_count': floor.rooms.filter(is_active=True).count(),
                'created_at': floor.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': floor.updated_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({
            'floors': floors_data,
            'total': paginator.count,
            'pages': paginator.num_pages,
            'current_page': page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })


@method_decorator(login_required, name='dispatch')
class FloorCRUDView(AdminRequiredMixin, View):
    """
    CRUD operations for Floor.
    """
    
    def get(self, request, floor_id=None):
        """Get single floor."""
        if floor_id:
            try:
                floor = Floor.objects.select_related('building__compound__camp').get(id=floor_id)
                return JsonResponse({
                    'id': str(floor.id),
                    'name': floor.name,
                    'level': floor.level,
                    'building_id': str(floor.building.id),
                    'building_name': floor.building.name,
                    'compound_name': floor.building.compound.name,
                    'camp_name': floor.building.compound.camp.name,
                    'is_active': floor.is_active,
                    'description': floor.description,
                    'created_at': floor.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': floor.updated_at.strftime('%Y-%m-%d %H:%M'),
                })
            except Floor.DoesNotExist:
                return JsonResponse({'error': 'Floor not found'}, status=404)
        else:
            return JsonResponse({'error': 'Floor ID required'}, status=400)
    
    def post(self, request):
        """Create new floor."""
        try:
            data = json.loads(request.body)
            
            building = get_object_or_404(Building, id=data.get('building_id'))
            
            floor = Floor.objects.create(
                name=data.get('name'),
                level=data.get('level'),
                building=building,
                is_active=data.get('is_active', True),
                description=data.get('description', ''),
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Floor created successfully',
                'floor': {
                    'id': str(floor.id),
                    'name': floor.name,
                    'level': floor.level,
                    'building_id': str(floor.building.id),
                    'building_name': floor.building.name,
                    'is_active': floor.is_active,
                    'description': floor.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def put(self, request, floor_id):
        """Update floor."""
        try:
            floor = get_object_or_404(Floor, id=floor_id)
            data = json.loads(request.body)
            
            floor.name = data.get('name', floor.name)
            floor.level = data.get('level', floor.level)
            floor.is_active = data.get('is_active', floor.is_active)
            floor.description = data.get('description', floor.description)
            
            if 'building_id' in data:
                building = get_object_or_404(Building, id=data['building_id'])
                floor.building = building
            
            floor.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Floor updated successfully',
                'floor': {
                    'id': str(floor.id),
                    'name': floor.name,
                    'level': floor.level,
                    'building_id': str(floor.building.id),
                    'building_name': floor.building.name,
                    'is_active': floor.is_active,
                    'description': floor.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def delete(self, request, floor_id):
        """Delete floor."""
        try:
            floor = get_object_or_404(Floor, id=floor_id)
            
            # Check if floor has rooms
            if floor.rooms.exists():
                return JsonResponse({
                    'error': 'Cannot delete floor with existing rooms. Please delete rooms first.'
                }, status=400)
            
            floor.delete()
            return JsonResponse({
                'success': True,
                'message': 'Floor deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class RoomListView(AdminRequiredMixin, View):
    """
    API endpoint for listing rooms with pagination and search.
    """
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        floor_id = request.GET.get('floor_id', '')
        per_page = int(request.GET.get('per_page', 25))
        
        rooms = Room.objects.select_related('floor__building__compound__camp').filter(is_active=True).order_by('floor__building__compound__camp__name', 'floor__building__compound__name', 'floor__building__name', 'floor__code', 'name')
        
        if search:
            rooms = rooms.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(floor__name__icontains=search) |
                Q(floor__building__name__icontains=search) |
                Q(floor__building__compound__name__icontains=search) |
                Q(floor__building__compound__camp__name__icontains=search)
            )
        
        if floor_id:
            rooms = rooms.filter(floor_id=floor_id)
        
        paginator = Paginator(rooms, per_page)
        page_obj = paginator.get_page(page)
        
        rooms_data = []
        for room in rooms:
            rooms_data.append({
                'id': str(room.id),
                'name': room.name,
                'code': room.code,
                'sqm': float(room.sqm),
                'floor_name': room.floor.name,
                'floor_id': str(room.floor.id),
                'building_name': room.floor.building.name,
                'compound_name': room.floor.building.compound.name,
                'camp_name': room.floor.building.compound.camp.name,
                'is_active': room.is_active,
                'frequency_per_day': room.frequency_per_day,
                'frequency_per_week': room.frequency_per_week,
                'barcode_data': room.barcode_data,
                'created_at': room.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': room.updated_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({
            'rooms': rooms_data,
            'total': paginator.count,
            'pages': paginator.num_pages,
            'current_page': page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })


@method_decorator(login_required, name='dispatch')
class RoomCRUDView(AdminRequiredMixin, View):
    """
    CRUD operations for Room.
    """
    
    def get(self, request, room_id=None):
        """Get single room."""
        if room_id:
            try:
                room = Room.objects.select_related('floor__building__compound__camp').get(id=room_id)
                return JsonResponse({
                    'id': str(room.id),
                    'name': room.name,
                    'code': room.code,
                    'sqm': float(room.sqm),
                    'floor_id': str(room.floor.id),
                    'floor_name': room.floor.name,
                    'building_name': room.floor.building.name,
                    'compound_name': room.floor.building.compound.name,
                    'camp_name': room.floor.building.compound.camp.name,
                    'is_active': room.is_active,
                    'frequency_per_day': room.frequency_per_day,
                    'frequency_per_week': room.frequency_per_week,
                    'barcode_data': room.barcode_data,
                    'description': room.description,
                    'created_at': room.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': room.updated_at.strftime('%Y-%m-%d %H:%M'),
                })
            except Room.DoesNotExist:
                return JsonResponse({'error': 'Room not found'}, status=404)
        else:
            return JsonResponse({'error': 'Room ID required'}, status=400)
    
    def post(self, request):
        """Create new room."""
        try:
            data = json.loads(request.body)
            
            floor = get_object_or_404(Floor, id=data.get('floor_id'))
            
            room = Room.objects.create(
                name=data.get('name'),
                code=data.get('code'),
                sqm=data.get('sqm', 0),
                floor=floor,
                is_active=data.get('is_active', True),
                frequency_per_day=data.get('frequency_per_day', 1),
                frequency_per_week=data.get('frequency_per_week', 7),
                description=data.get('description', ''),
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Room created successfully',
                'room': {
                    'id': str(room.id),
                    'name': room.name,
                    'code': room.code,
                    'sqm': float(room.sqm),
                    'floor_id': str(room.floor.id),
                    'floor_name': room.floor.name,
                    'is_active': room.is_active,
                    'frequency_per_day': room.frequency_per_day,
                    'frequency_per_week': room.frequency_per_week,
                    'description': room.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def put(self, request, room_id):
        """Update room."""
        try:
            room = get_object_or_404(Room, id=room_id)
            data = json.loads(request.body)
            
            room.name = data.get('name', room.name)
            room.code = data.get('code', room.code)
            room.sqm = data.get('sqm', room.sqm)
            room.is_active = data.get('is_active', room.is_active)
            room.frequency_per_day = data.get('frequency_per_day', room.frequency_per_day)
            room.frequency_per_week = data.get('frequency_per_week', room.frequency_per_week)
            room.description = data.get('description', room.description)
            
            if 'floor_id' in data:
                floor = get_object_or_404(Floor, id=data['floor_id'])
                room.floor = floor
            
            room.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Room updated successfully',
                'room': {
                    'id': str(room.id),
                    'name': room.name,
                    'code': room.code,
                    'sqm': float(room.sqm),
                    'floor_id': str(room.floor.id),
                    'floor_name': room.floor.name,
                    'is_active': room.is_active,
                    'frequency_per_day': room.frequency_per_day,
                    'frequency_per_week': room.frequency_per_week,
                    'description': room.description,
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def delete(self, request, room_id):
        """Soft delete room (set is_active=False)."""
        try:
            room = get_object_or_404(Room, id=room_id)
            
            # Soft delete - set is_active to False
            room.is_active = False
            room.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Room deactivated successfully'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(login_required, name='dispatch')
class LocationHierarchyView(AdminRequiredMixin, View):
    """
    Get hierarchical data for dropdowns and navigation.
    """
    
    def get(self, request):
        """Get hierarchical data for all locations."""
        try:
            # Get all camps
            camps = Camp.objects.all().values('id', 'name', 'code')
            
            # Get all compounds with their camps
            compounds = Compound.objects.select_related('camp').all().values(
                'id', 'name', 'code', 'camp_id', 'camp__name', 'camp__code'
            )
            
            # Get all buildings with their compounds and camps
            buildings = Building.objects.select_related('compound__camp').all().values(
                'id', 'name', 'code', 'compound_id', 'compound__name', 'compound__code',
                'compound__camp_id', 'compound__camp__name', 'compound__camp__code'
            )
            
            # Get all floors with their buildings, compounds and camps
            floors = Floor.objects.select_related('building__compound__camp').all().values(
                'id', 'name', 'code', 'building_id', 'building__name', 'building__code',
                'building__compound_id', 'building__compound__name', 'building__compound__code',
                'building__compound__camp_id', 'building__compound__camp__name', 'building__compound__camp__code'
            )
            
            return JsonResponse({
                'camps': list(camps),
                'compounds': list(compounds),
                'buildings': list(buildings),
                'floors': list(floors),
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
