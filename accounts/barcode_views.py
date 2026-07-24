"""
Barcode Generator Views
"""

from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from locations.models import Room, Camp, Compound, Building
from accounts.barcode_service import BarcodeService
import json


@login_required
@staff_member_required
def generate_single_barcode(request, room_id):
    """
    Generate barcode for a single room
    """
    room = get_object_or_404(Room, id=room_id, is_active=True)
    
    try:
        barcode_data = room.generate_barcode_data()
        barcode_bytes = room.generate_barcode_image()
        
        if barcode_bytes:
            response = HttpResponse(barcode_bytes, content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="barcode_{room.room_code}.png"'
            return response
        else:
            raise Http404("Could not generate barcode")
            
    except Exception as e:
        raise Http404(f"Error generating barcode: {str(e)}")


@login_required
@staff_member_required
@require_http_methods(["POST"])
def generate_bulk_barcodes(request):
    """
    Generate barcodes for multiple rooms
    """
    try:
        data = json.loads(request.body)
        room_ids = data.get('room_ids', [])
        
        if not room_ids:
            return HttpResponse(json.dumps({'error': 'No rooms selected'}), 
                              content_type='application/json', status=400)
        
        # Get rooms
        rooms = Room.objects.filter(id__in=room_ids, is_active=True)
        
        if not rooms.exists():
            return HttpResponse(json.dumps({'error': 'No valid rooms found'}), 
                              content_type='application/json', status=400)
        
        # Generate PDF
        pdf_bytes = BarcodeService.generate_barcode_pdf(rooms)
        
        if pdf_bytes:
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="room_barcodes.pdf"'
            return response
        else:
            return HttpResponse(json.dumps({'error': 'Could not generate PDF'}), 
                              content_type='application/json', status=500)
            
    except Exception as e:
        return HttpResponse(json.dumps({'error': str(e)}), 
                          content_type='application/json', status=500)


@login_required
@staff_member_required
def generate_camp_barcodes(request, camp_id):
    """
    Generate barcodes for all rooms in a camp
    """
    camp = get_object_or_404(Camp, id=camp_id, is_active=True)
    rooms = Room.objects.filter(
        floor__building__compound__camp=camp,
        is_active=True
    ).select_related('floor__building__compound__camp')
    
    if not rooms.exists():
        raise Http404("No rooms found for this camp")
    
    try:
        pdf_bytes = BarcodeService.generate_barcode_pdf(rooms)
        
        if pdf_bytes:
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="barcodes_{camp.code}.pdf"'
            return response
        else:
            raise Http404("Could not generate PDF")
            
    except Exception as e:
        raise Http404(f"Error generating PDF: {str(e)}")


@login_required
@staff_member_required
def generate_compound_barcodes(request, compound_id):
    """
    Generate barcodes for all rooms in a compound
    """
    compound = get_object_or_404(Compound, id=compound_id, is_active=True)
    rooms = Room.objects.filter(
        floor__building__compound=compound,
        is_active=True
    ).select_related('floor__building__compound__camp')
    
    if not rooms.exists():
        raise Http404("No rooms found for this compound")
    
    try:
        pdf_bytes = BarcodeService.generate_barcode_pdf(rooms)
        
        if pdf_bytes:
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="barcodes_{compound.code}.pdf"'
            return response
        else:
            raise Http404("Could not generate PDF")
            
    except Exception as e:
        raise Http404(f"Error generating PDF: {str(e)}")


@login_required
@staff_member_required
def generate_building_barcodes(request, building_id):
    """
    Generate barcodes for all rooms in a building
    """
    building = get_object_or_404(Building, id=building_id, is_active=True)
    rooms = Room.objects.filter(
        floor__building=building,
        is_active=True
    ).select_related('floor__building__compound__camp')
    
    if not rooms.exists():
        raise Http404("No rooms found for this building")
    
    try:
        pdf_bytes = BarcodeService.generate_barcode_pdf(rooms)
        
        if pdf_bytes:
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="barcodes_{building.code}.pdf"'
            return response
        else:
            raise Http404("Could not generate PDF")
            
    except Exception as e:
        raise Http404(f"Error generating PDF: {str(e)}")
