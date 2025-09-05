"""
Barcode generator views for the admin interface.
"""

from django.shortcuts import render, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import zipfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Floor, Room
from cct.utils import generate_barcode_data


@method_decorator(login_required, name='dispatch')
class BarcodeGeneratorView(AdminRequiredMixin, TemplateView):
    """
    Barcode generator interface with room selection and bulk generation.
    """
    template_name = 'dashboard/barcode_generator.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter options
        context['camps'] = Camp.objects.all()
        context['compounds'] = Compound.objects.all()
        context['buildings'] = Building.objects.all()
        context['floors'] = Floor.objects.all()
        
        # Get rooms with barcode status
        rooms = Room.objects.filter(is_active=True).select_related(
            'floor__building__compound__camp'
        ).order_by('floor__building__compound__camp__name', 'floor__building__compound__name', 'floor__building__name', 'floor__name', 'name')
        
        context['rooms'] = rooms
        
        return context


@method_decorator(login_required, name='dispatch')
class GenerateBarcodesView(AdminRequiredMixin, View):
    """
    Generate barcodes for selected rooms.
    """
    
    def get(self, request):
        """Handle GET requests for individual room downloads."""
        room_id = request.GET.get('room_id')
        format_type = request.GET.get('format', 'png')
        size = request.GET.get('size', 'medium')
        include_text = request.GET.get('include_text', 'true').lower() == 'true'
        
        if not room_id:
            return JsonResponse({'error': 'Room ID required'}, status=400)
        
        try:
            room = Room.objects.get(
                id=room_id,
                is_active=True
            )
            
            # Generate or regenerate barcode data
            barcode_data = self.ensure_barcode_data(room)
            
            if format_type == 'png':
                return self.generate_png_barcode(barcode_data, room, size, include_text)
            elif format_type == 'pdf':
                return self.generate_pdf_barcode(barcode_data, room, size, include_text)
            else:
                return JsonResponse({'error': 'Invalid format'}, status=400)
                
        except Room.DoesNotExist:
            return JsonResponse({'error': 'Room not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def post(self, request):
        action = request.POST.get('action')  # 'preview', 'generate_individual', 'generate_bulk'
        room_ids = request.POST.getlist('room_ids')
        format_type = request.POST.get('format', 'png')  # 'png' or 'pdf'
        
        if not room_ids:
            return JsonResponse({'error': 'No rooms selected'}, status=400)
        
        try:
            rooms = Room.objects.filter(
                id__in=room_ids,
                is_active=True
            ).select_related('floor__building__compound__camp')
            
            if action == 'preview':
                # Preview mode - show what would be generated
                result = self.preview_barcode_generation(rooms)
                return JsonResponse({
                    'success': True,
                    'action': 'preview',
                    'result': result
                })
            
            elif action == 'generate_individual':
                # Generate individual barcode images
                return self.generate_individual_barcodes(rooms, format_type)
            
            elif action == 'generate_bulk':
                # Generate bulk download (ZIP file)
                return self.generate_bulk_barcodes(rooms, format_type)
            
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def preview_barcode_generation(self, rooms):
        """Preview what barcodes would be generated."""
        result = {
            'total_rooms': rooms.count(),
            'rooms_with_barcodes': 0,
            'rooms_without_barcodes': 0,
            'rooms_needing_regeneration': 0,
            'room_details': []
        }
        
        for room in rooms:
            has_barcode = bool(room.barcode_data)
            needs_regeneration = False
            
            # Check if barcode needs regeneration (simplified logic)
            if has_barcode:
                # Verify barcode format
                expected_barcode = generate_barcode_data(room)
                needs_regeneration = room.barcode_data != expected_barcode
            
            if has_barcode and not needs_regeneration:
                result['rooms_with_barcodes'] += 1
            elif needs_regeneration:
                result['rooms_needing_regeneration'] += 1
            else:
                result['rooms_without_barcodes'] += 1
            
            result['room_details'].append({
                'id': room.id,
                'name': room.name,
                'code': room.code,
                'location': f"{room.floor.building.compound.camp.name} - {room.floor.building.compound.name} - {room.floor.building.name} - {room.floor.name}",
                'has_barcode': has_barcode,
                'needs_regeneration': needs_regeneration,
                'barcode_data': room.barcode_data or 'Not Generated'
            })
        
        return result
    
    def generate_individual_barcodes(self, rooms, format_type):
        """Generate individual barcode for a single room."""
        if len(rooms) != 1:
            return JsonResponse({'error': 'Individual generation requires exactly one room'}, status=400)
        
        room = rooms[0]
        
        # Generate or regenerate barcode data
        barcode_data = self.ensure_barcode_data(room)
        
        if format_type == 'png':
            return self.generate_png_barcode(barcode_data, room)
        elif format_type == 'pdf':
            return self.generate_pdf_barcode(barcode_data, room)
        else:
            return JsonResponse({'error': 'Invalid format'}, status=400)
    
    def generate_bulk_barcodes(self, rooms, format_type):
        """Generate bulk barcodes as ZIP file."""
        # Create ZIP file in memory
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for room in rooms:
                # Generate or regenerate barcode data
                barcode_data = self.ensure_barcode_data(room)
                
                if format_type == 'png':
                    # Generate PNG barcode
                    png_data = self.create_png_barcode(barcode_data, room)
                    filename = f"{room.floor.building.compound.camp.code}_{room.floor.building.compound.code}_{room.floor.building.code}_{room.floor.code}_{room.code}.png"
                    zip_file.writestr(filename, png_data)
                
                elif format_type == 'pdf':
                    # Generate PDF barcode
                    pdf_data = self.create_pdf_barcode(barcode_data, room)
                    filename = f"{room.floor.building.compound.camp.code}_{room.floor.building.compound.code}_{room.floor.building.code}_{room.floor.code}_{room.code}.pdf"
                    zip_file.writestr(filename, pdf_data)
        
        zip_buffer.seek(0)
        
        response = HttpResponse(
            zip_buffer.read(),
            content_type='application/zip'
        )
        response['Content-Disposition'] = 'attachment; filename="room_barcodes.zip"'
        return response
    
    def ensure_barcode_data(self, room):
        """Ensure room has valid barcode data, generate if needed."""
        if not room.barcode_data:
            # Generate new barcode data
            barcode_data = generate_barcode_data(room)
            room.barcode_data = barcode_data
            room.save()
            return barcode_data
        
        # Verify existing barcode data
        expected_barcode = generate_barcode_data(room)
        
        if room.barcode_data != expected_barcode:
            # Regenerate barcode data
            room.barcode_data = expected_barcode
            room.save()
            return expected_barcode
        
        return room.barcode_data
    
    def generate_png_barcode(self, barcode_data, room, size='medium', include_text=True):
        """Generate PNG barcode for download."""
        png_data = self.create_png_barcode(barcode_data, room, size, include_text)
        
        response = HttpResponse(png_data, content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{room.code}_barcode.png"'
        return response

    def generate_pdf_barcode(self, barcode_data, room, size='medium', include_text=True):
        """Generate PDF barcode for download."""
        pdf_data = self.create_pdf_barcode(barcode_data, room, size, include_text)
        
        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{room.code}_barcode.pdf"'
        return response
    
    def create_png_barcode(self, barcode_data, room, size='medium', include_text=True):
        """Create PNG barcode image with real-world size constraints."""
        # Size configurations in mm (converted to appropriate module widths)
        # Target: 7cm width (70mm), 4cm height (40mm)
        size_configs = {
            'small': {
                'module_width': 0.12,  # Smaller bars for more compact
                'module_height': 8.0,  # 8mm height
                'font_size': 6,
                'max_width_mm': 50,    # 5cm max width
                'max_height_mm': 30    # 3cm max height
            },
            'medium': {
                'module_width': 0.15,  # Standard bars
                'module_height': 10.0, # 10mm height
                'font_size': 8,
                'max_width_mm': 70,    # 7cm max width
                'max_height_mm': 40    # 4cm max height
            },
            'large': {
                'module_width': 0.18,  # Larger bars
                'module_height': 12.0, # 12mm height
                'font_size': 10,
                'max_width_mm': 70,    # 7cm max width
                'max_height_mm': 40    # 4cm max height
            }
        }
        
        config = size_configs.get(size, size_configs['medium'])
        
        # Generate Code128 barcode
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(barcode_data, writer=ImageWriter())
        
        # Create image
        buffer = BytesIO()
        barcode_instance.write(buffer, options={
            'module_width': config['module_width'],
            'module_height': config['module_height'],
            'quiet_zone': 4.0,  # Reduced quiet zone for better fit
            'font_size': config['font_size'],
            'text_distance': 3.0,
            'background': 'white',
            'foreground': 'black',
            'write_text': include_text,
            'text': f"{room.code}" if include_text else "",  # Shorter text for better fit
            'center_text': True
        })
        
        return buffer.getvalue()
    
    def create_pdf_barcode(self, barcode_data, room, size='medium', include_text=True):
        """Create PDF with barcode and room information."""
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Title
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, f"Room Barcode: {room.name}")
        
        # Room information
        p.setFont("Helvetica", 12)
        y_position = height - 100
        
        info_lines = [
            f"Room Code: {room.code}",
            f"Location: {room.floor.building.compound.camp.name} - {room.floor.building.compound.name}",
            f"Building: {room.floor.building.name}",
            f"Floor: {room.floor.name}",
            f"Area: {room.sqm} m²",
            f"Barcode Data: {barcode_data}",
        ]
        
        for line in info_lines:
            p.drawString(50, y_position, line)
            y_position -= 20
        
        # Generate barcode image
        png_data = self.create_png_barcode(barcode_data, room, size, include_text)
        
        # Save barcode image to PDF with real-world size constraints
        # 7cm = 198.425 points (1cm = 28.35 points)
        # 4cm = 113.4 points
        barcode_width = 198.425  # 7cm in points
        barcode_height = 113.4   # 4cm in points
        
        barcode_buffer = BytesIO(png_data)
        p.drawImage(barcode_buffer, 50, y_position - 200, width=barcode_width, height=barcode_height)
        
        # Footer
        p.setFont("Helvetica", 8)
        p.drawString(50, 50, f"Generated on: {room.floor.building.compound.camp.name} - {barcode_data}")
        
        p.showPage()
        p.save()
        
        return buffer.getvalue()


@method_decorator(login_required, name='dispatch')
class RegenerateBarcodesView(AdminRequiredMixin, View):
    """
    Regenerate barcodes for selected rooms.
    """
    
    def post(self, request):
        room_ids = request.POST.getlist('room_ids')
        
        if not room_ids:
            return JsonResponse({'error': 'No rooms selected'}, status=400)
        
        try:
            rooms = Room.objects.filter(
                id__in=room_ids,
                is_active=True
            ).select_related('floor__building__compound__camp')
            
            regenerated_count = 0
            
            for room in rooms:
                # Generate new barcode data
                barcode_data = generate_barcode_data(room)
                
                room.barcode_data = barcode_data
                room.save()
                regenerated_count += 1
            
            return JsonResponse({
                'success': True,
                'regenerated_count': regenerated_count,
                'message': f'Successfully regenerated barcodes for {regenerated_count} rooms'
            })
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class BarcodeAPIView(AdminRequiredMixin, View):
    """
    API endpoints for barcode generator.
    """
    
    def get(self, request):
        """Get rooms, compounds, or buildings for filtering."""
        # Determine endpoint based on URL path
        if 'rooms' in request.path:
            return self.get_rooms(request)
        elif 'compounds' in request.path:
            return self.get_compounds(request)
        elif 'buildings' in request.path:
            return self.get_buildings(request)
        else:
            return JsonResponse({'error': 'Invalid endpoint'}, status=400)
    
    def get_rooms(self, request):
        """Get rooms with filtering options."""
        try:
            camp_id = request.GET.get('camp_id')
            compound_id = request.GET.get('compound_id')
            building_id = request.GET.get('building_id')
            search = request.GET.get('search', '')
            
            # Build queryset
            rooms = Room.objects.filter(is_active=True).select_related(
                'floor__building__compound__camp'
            )
            
            # Apply filters
            if camp_id:
                rooms = rooms.filter(floor__building__compound__camp_id=camp_id)
            if compound_id:
                rooms = rooms.filter(floor__building__compound_id=compound_id)
            if building_id:
                rooms = rooms.filter(floor__building_id=building_id)
            if search:
                rooms = rooms.filter(
                    Q(name__icontains=search) | 
                    Q(code__icontains=search)
                )
            
            # Format response
            room_data = []
            for room in rooms:
                room_data.append({
                    'id': room.id,
                    'name': room.name,
                    'code': room.code,
                    'sqm': room.sqm,
                    'barcode_data': room.barcode_data,
                    'hierarchy_path': f"{room.floor.building.compound.camp.name} - {room.floor.building.compound.name} - {room.floor.building.name} - {room.floor.name}",
                })
            
            return JsonResponse({
                'success': True,
                'rooms': room_data
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def get_compounds(self, request):
        """Get compounds for a camp."""
        try:
            camp_id = request.GET.get('camp_id')
            if not camp_id:
                return JsonResponse({'error': 'Camp ID required'}, status=400)
            
            compounds = Compound.objects.filter(camp_id=camp_id).values(
                'id', 'name', 'code'
            )
            
            return JsonResponse({
                'success': True,
                'compounds': list(compounds)
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def get_buildings(self, request):
        """Get buildings for a compound."""
        try:
            compound_id = request.GET.get('compound_id')
            if not compound_id:
                return JsonResponse({'error': 'Compound ID required'}, status=400)
            
            buildings = Building.objects.filter(compound_id=compound_id).values(
                'id', 'name', 'code'
            )
            
            return JsonResponse({
                'success': True,
                'buildings': list(buildings)
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def post(self, request):
        """Handle barcode generation operations."""
        import json
        data = json.loads(request.body)
        
        # Determine action based on URL path
        if 'preview' in request.path:
            return self.preview_barcode(data)
        elif 'generate' in request.path:
            return self.generate_barcodes(data)
        elif 'regenerate' in request.path:
            return self.regenerate_barcodes(data)
        else:
            return JsonResponse({'error': 'Invalid endpoint'}, status=400)
    
    def preview_barcode(self, data):
        """Preview a single barcode."""
        try:
            room_id = data.get('room_id')
            room_code = data.get('room_code')
            format_type = data.get('format', 'code128')
            size = data.get('size', 'medium')
            include_text = data.get('include_text', True)
            
            if not room_id:
                return JsonResponse({'error': 'Room ID required'}, status=400)
            
            room = Room.objects.get(id=room_id)
            
            # Ensure barcode data exists
            if not room.barcode_data:
                room.generate_barcode_data()
                room.save()
            
            # Generate barcode image
            barcode_data = room.barcode_data
            png_data = self.create_png_barcode(barcode_data, room, size, include_text)
            
            # Convert to base64 for preview
            import base64
            barcode_base64 = base64.b64encode(png_data).decode('utf-8')
            
            return JsonResponse({
                'success': True,
                'barcode_data': barcode_base64
            })
        except Room.DoesNotExist:
            return JsonResponse({'error': 'Room not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def generate_barcodes(self, data):
        """Generate barcodes for multiple rooms."""
        try:
            room_ids = data.get('room_ids', [])
            format_type = data.get('format', 'code128')
            output_format = data.get('output_format', 'png')
            size = data.get('size', 'medium')
            include_text = data.get('include_text', True)
            
            if not room_ids:
                return JsonResponse({'error': 'Room IDs required'}, status=400)
            
            rooms = Room.objects.filter(id__in=room_ids, is_active=True)
            
            generated = 0
            skipped = 0
            errors = []
            
            for room in rooms:
                try:
                    # Ensure barcode data exists
                    if not room.barcode_data:
                        room.generate_barcode_data()
                        room.save()
                        generated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append({
                        'room_code': room.code,
                        'error': str(e)
                    })
            
            result = {
                'generated': generated,
                'skipped': skipped,
                'errors': len(errors),
                'error_details': errors
            }
            
            return JsonResponse({
                'success': True,
                'result': result
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def regenerate_barcodes(self, data):
        """Regenerate barcodes for multiple rooms."""
        try:
            room_ids = data.get('room_ids', [])
            format_type = data.get('format', 'code128')
            output_format = data.get('output_format', 'png')
            size = data.get('size', 'medium')
            include_text = data.get('include_text', True)
            
            if not room_ids:
                return JsonResponse({'error': 'Room IDs required'}, status=400)
            
            rooms = Room.objects.filter(id__in=room_ids, is_active=True)
            
            regenerated = 0
            errors = []
            
            for room in rooms:
                try:
                    # Regenerate barcode data
                    room.generate_barcode_data()
                    room.save()
                    regenerated += 1
                except Exception as e:
                    errors.append({
                        'room_code': room.code,
                        'error': str(e)
                    })
            
            result = {
                'generated': regenerated,
                'skipped': 0,
                'errors': len(errors),
                'error_details': errors
            }
            
            return JsonResponse({
                'success': True,
                'result': result
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def create_png_barcode(self, barcode_data, room, size='medium', include_text=True):
        """Create PNG barcode image."""
        # Size mapping
        size_map = {
            'small': {'module_width': 0.3, 'module_height': 10.0, 'font_size': 8},
            'medium': {'module_width': 0.4, 'module_height': 15.0, 'font_size': 10},
            'large': {'module_width': 0.6, 'module_height': 20.0, 'font_size': 12}
        }
        
        options = size_map.get(size, size_map['medium'])
        options.update({
            'quiet_zone': 6.5,
            'text_distance': 5.0,
            'background': 'white',
            'foreground': 'black',
        })
        
        if not include_text:
            options['write_text'] = False
        
        # Generate Code128 barcode
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(barcode_data, writer=ImageWriter())
        
        # Create image
        buffer = BytesIO()
        barcode_instance.write(buffer, options=options)
        
        return buffer.getvalue()
