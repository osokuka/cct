"""
AJAX endpoints for barcode generator dynamic filtering
"""

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from locations.models import Camp, Compound, Building, Floor


@login_required
@staff_member_required
def get_compounds_for_camp(request, camp_id):
    """
    AJAX endpoint to get compounds for a specific camp
    """
    try:
        camp = get_object_or_404(Camp, id=camp_id, is_active=True)
        compounds = Compound.objects.filter(camp=camp, is_active=True).order_by('name')
        
        data = [{'id': str(compound.id), 'name': compound.name} for compound in compounds]
        return JsonResponse({'compounds': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@staff_member_required
def get_buildings_for_compound(request, compound_id):
    """
    AJAX endpoint to get buildings for a specific compound
    """
    try:
        compound = get_object_or_404(Compound, id=compound_id, is_active=True)
        buildings = Building.objects.filter(compound=compound, is_active=True).order_by('name')
        
        data = [{'id': str(building.id), 'name': building.name} for building in buildings]
        return JsonResponse({'buildings': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@staff_member_required
def get_floors_for_building(request, building_id):
    """
    AJAX endpoint to get floors for a specific building
    """
    try:
        building = get_object_or_404(Building, id=building_id, is_active=True)
        floors = Floor.objects.filter(building=building, is_active=True).order_by('name')
        
        data = [{'id': str(floor.id), 'name': floor.name} for floor in floors]
        return JsonResponse({'floors': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
