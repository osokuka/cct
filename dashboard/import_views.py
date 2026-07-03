"""
Bulk import views for locations and rooms.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
import csv
import io
import re
from datetime import datetime
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Floor, Room
from accounts.models import Shift
from cct.utils import generate_barcode_data


@method_decorator(login_required, name='dispatch')
class BulkImportView(AdminRequiredMixin, TemplateView):
    """
    Bulk import interface for locations and rooms.
    """
    template_name = 'dashboard/bulk_import.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get existing data for reference
        context['camps'] = Camp.objects.all()
        context['compounds'] = Compound.objects.all()
        context['buildings'] = Building.objects.all()
        context['shifts'] = Shift.objects.all()
        
        return context


@method_decorator(login_required, name='dispatch')
class ProcessImportView(AdminRequiredMixin, View):
    """
    Process CSV import with dry-run and apply functionality.
    """
    
    def post(self, request):
        action = request.POST.get('action')  # 'dry_run' or 'apply'
        csv_file = request.FILES.get('csv_file')
        
        if not csv_file:
            return JsonResponse({'error': 'No CSV file provided'}, status=400)
        
        try:
            # Read and parse CSV
            csv_data = self.parse_csv(csv_file)
            
            if action == 'dry_run':
                # Perform dry run - show what would be created/updated
                result = self.dry_run_import(csv_data)
                return JsonResponse({
                    'success': True,
                    'action': 'dry_run',
                    'result': result
                })
            
            elif action == 'apply':
                # Apply the import
                result = self.apply_import(csv_data)
                return JsonResponse({
                    'success': True,
                    'action': 'apply',
                    'result': result
                })
            
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def parse_csv(self, csv_file):
        """Parse CSV file and return structured data."""
        # Read CSV content
        content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        data = []
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
            try:
                # Parse and validate row data
                parsed_row = self.parse_row(row, row_num)
                data.append(parsed_row)
            except Exception as e:
                raise Exception(f"Error parsing row {row_num}: {str(e)}")
        
        return data
    
    def parse_row(self, row, row_num):
        """Parse a single CSV row."""
        # Required fields
        camp_name = row.get('Camp_Name', '').strip()
        compound_name = row.get('Compound_Name', '').strip()
        bldg_location = row.get('BLDG_Location', '').strip()
        sqm = row.get('m²', '').strip()
        qty_rooms = row.get('Qty_of_rooms', '').strip()
        actual_sqm = row.get('Actual_Sqm_m2', '').strip()
        
        if not all([camp_name, compound_name, bldg_location, sqm]):
            raise Exception("Missing required fields: Camp_Name, Compound_Name, BLDG_Location, m²")
        
        # Parse numeric fields
        try:
            sqm = float(sqm)
            qty_rooms = int(qty_rooms) if qty_rooms else 1
            actual_sqm = float(actual_sqm) if actual_sqm else sqm
        except ValueError as e:
            raise Exception(f"Invalid numeric value: {str(e)}")
        
        # Parse cleaning schedule
        frequency_per_day = int(row.get('Frequency_Per_Day', 1))
        frequency_per_week = int(row.get('Frequency_Per_Week', 7))
        max_frequency_per_month = int(row.get('Max_Frequency_Per_Month', 31))
        
        # Parse dates
        start_date = self.parse_date(row.get('Start_Date', ''))
        end_date = self.parse_date(row.get('End_Date', ''))
        
        # Parse shift and time window
        shift_code = row.get('Shift_Code', '').strip()
        time_window_start = row.get('Time_Window_Start', '').strip()
        time_window_end = row.get('Time_Window_End', '').strip()
        
        # Parse building location to extract hierarchy
        building_info = self.parse_building_location(bldg_location)
        
        return {
            'row_num': row_num,
            'camp_name': camp_name,
            'compound_name': compound_name,
            'building_info': building_info,
            'sqm': sqm,
            'qty_rooms': qty_rooms,
            'actual_sqm': actual_sqm,
            'frequency_per_day': frequency_per_day,
            'frequency_per_week': frequency_per_week,
            'max_frequency_per_month': max_frequency_per_month,
            'start_date': start_date,
            'end_date': end_date,
            'shift_code': shift_code,
            'time_window_start': time_window_start,
            'time_window_end': time_window_end,
        }
    
    def parse_date(self, date_str):
        """Parse date string in DD-MMM-YY format."""
        if not date_str:
            return None
        
        try:
            # Handle format like "1-Oct-25" or "31-Dec-25"
            return datetime.strptime(date_str.strip(), '%d-%b-%y').date()
        except ValueError:
            try:
                # Try alternative format
                return datetime.strptime(date_str.strip(), '%d-%m-%y').date()
            except ValueError:
                return None
    
    def parse_building_location(self, bldg_location):
        """Parse building location string to extract hierarchy."""
        # Example: "Bld. 87, 1 single container (toilet)"
        # Extract building number
        building_match = re.search(r'Bld\.?\s*(\d+)', bldg_location, re.IGNORECASE)
        building_number = building_match.group(1) if building_match else '001'
        
        # Extract floor/container info
        floor_info = 'Ground'
        if 'F4' in bldg_location:
            floor_info = 'F4'
        elif 'F5' in bldg_location:
            floor_info = 'F5'
        elif 'container' in bldg_location.lower():
            floor_info = 'Container'
        
        # Extract room type
        room_type = 'Room'
        if 'toilet' in bldg_location.lower():
            room_type = 'Toilet'
        elif 'container' in bldg_location.lower():
            room_type = 'Container'
        
        return {
            'building_number': building_number,
            'floor_info': floor_info,
            'room_type': room_type,
            'description': bldg_location
        }
    
    def dry_run_import(self, csv_data):
        """Perform dry run to show what would be created/updated."""
        result = {
            'would_create': [],
            'would_update': [],
            'conflicts': [],
            'summary': {
                'camps': 0,
                'compounds': 0,
                'buildings': 0,
                'floors': 0,
                'rooms': 0,
            }
        }
        
        for row in csv_data:
            try:
                # Check what would be created/updated
                changes = self.analyze_row_changes(row)
                result['would_create'].extend(changes['create'])
                result['would_update'].extend(changes['update'])
                result['conflicts'].extend(changes['conflicts'])
                
                # Update summary counts
                for item in changes['create']:
                    result['summary'][item['type']] += 1
                
            except Exception as e:
                result['conflicts'].append({
                    'row_num': row['row_num'],
                    'error': str(e)
                })
        
        return result
    
    def analyze_row_changes(self, row):
        """Analyze what changes would be made for a single row."""
        changes = {
            'create': [],
            'update': [],
            'conflicts': []
        }
        
        # Check camp
        camp, created = Camp.objects.get_or_create(
            name=row['camp_name'],
            defaults={'code': row['camp_name'].upper().replace(' ', '')}
        )
        if created:
            changes['create'].append({
                'type': 'camps',
                'name': camp.name,
                'code': camp.code
            })
        
        # Check compound
        compound, created = Compound.objects.get_or_create(
            camp=camp,
            name=row['compound_name'],
            defaults={'code': row['compound_name'].upper().replace(' ', '')}
        )
        if created:
            changes['create'].append({
                'type': 'compounds',
                'name': compound.name,
                'code': compound.code,
                'camp': camp.name
            })
        
        # Check building
        building_info = row['building_info']
        building, created = Building.objects.get_or_create(
            compound=compound,
            code=building_info['building_number'],
            defaults={'name': f"Building {building_info['building_number']}"}
        )
        if created:
            changes['create'].append({
                'type': 'buildings',
                'name': building.name,
                'code': building.code,
                'compound': compound.name
            })
        
        # Check floor
        floor, created = Floor.objects.get_or_create(
            building=building,
            code=building_info['floor_info'],
            defaults={'name': f"Floor {building_info['floor_info']}"}
        )
        if created:
            changes['create'].append({
                'type': 'floors',
                'name': floor.name,
                'code': floor.code,
                'building': building.name
            })
        
        # Check rooms (based on qty_rooms)
        for i in range(row['qty_rooms']):
            room_code = f"RM{i+1:03d}"
            room, created = Room.objects.get_or_create(
                floor=floor,
                code=room_code,
                defaults={
                    'name': f"{building_info['room_type']} {i+1}",
                    'sqm': row['sqm'],
                    'is_active': True,
                    'frequency_per_day': row['frequency_per_day'],
                    'frequency_per_week': row['frequency_per_week'],
                }
            )
            if created:
                # Generate barcode
                barcode_data = generate_barcode_data(
                    camp.code, compound.code, building.code, floor.code, room.code
                )
                room.barcode_data = barcode_data
                room.save()
                
                changes['create'].append({
                    'type': 'rooms',
                    'name': room.name,
                    'code': room.code,
                    'sqm': room.sqm,
                    'barcode': barcode_data,
                    'floor': floor.name
                })
            else:
                # Check if update is needed
                if (room.sqm != row['sqm'] or 
                    room.frequency_per_day != row['frequency_per_day'] or
                    room.frequency_per_week != row['frequency_per_week']):
                    changes['update'].append({
                        'type': 'rooms',
                        'name': room.name,
                        'code': room.code,
                        'changes': {
                            'sqm': f"{room.sqm} → {row['sqm']}",
                            'frequency_per_day': f"{room.frequency_per_day} → {row['frequency_per_day']}",
                            'frequency_per_week': f"{room.frequency_per_week} → {row['frequency_per_week']}",
                        }
                    })
        
        return changes
    
    def apply_import(self, csv_data):
        """Apply the import with atomic transaction."""
        result = {
            'created': [],
            'updated': [],
            'errors': [],
            'summary': {
                'camps': 0,
                'compounds': 0,
                'buildings': 0,
                'floors': 0,
                'rooms': 0,
            }
        }
        
        with transaction.atomic():
            for row in csv_data:
                try:
                    # Apply changes for this row
                    changes = self.apply_row_changes(row)
                    result['created'].extend(changes['created'])
                    result['updated'].extend(changes['updated'])
                    
                    # Update summary counts
                    for item in changes['created']:
                        result['summary'][item['type']] += 1
                
                except Exception as e:
                    result['errors'].append({
                        'row_num': row['row_num'],
                        'error': str(e)
                    })
                    # Re-raise to trigger rollback
                    raise
        
        return result
    
    def apply_row_changes(self, row):
        """Apply changes for a single row."""
        changes = {
            'created': [],
            'updated': []
        }
        
        # Create/update camp
        camp, created = Camp.objects.get_or_create(
            name=row['camp_name'],
            defaults={'code': row['camp_name'].upper().replace(' ', '')}
        )
        if created:
            changes['created'].append({
                'type': 'camps',
                'name': camp.name,
                'code': camp.code
            })
        
        # Create/update compound
        compound, created = Compound.objects.get_or_create(
            camp=camp,
            name=row['compound_name'],
            defaults={'code': row['compound_name'].upper().replace(' ', '')}
        )
        if created:
            changes['created'].append({
                'type': 'compounds',
                'name': compound.name,
                'code': compound.code,
                'camp': camp.name
            })
        
        # Create/update building
        building_info = row['building_info']
        building, created = Building.objects.get_or_create(
            compound=compound,
            code=building_info['building_number'],
            defaults={'name': f"Building {building_info['building_number']}"}
        )
        if created:
            changes['created'].append({
                'type': 'buildings',
                'name': building.name,
                'code': building.code,
                'compound': compound.name
            })
        
        # Create/update floor
        floor, created = Floor.objects.get_or_create(
            building=building,
            code=building_info['floor_info'],
            defaults={'name': f"Floor {building_info['floor_info']}"}
        )
        if created:
            changes['created'].append({
                'type': 'floors',
                'name': floor.name,
                'code': floor.code,
                'building': building.name
            })
        
        # Create/update rooms
        for i in range(row['qty_rooms']):
            room_code = f"RM{i+1:03d}"
            room, created = Room.objects.get_or_create(
                floor=floor,
                code=room_code,
                defaults={
                    'name': f"{building_info['room_type']} {i+1}",
                    'sqm': row['sqm'],
                    'is_active': True,
                    'frequency_per_day': row['frequency_per_day'],
                    'frequency_per_week': row['frequency_per_week'],
                }
            )
            
            if created:
                # Generate barcode
                barcode_data = generate_barcode_data(
                    camp.code, compound.code, building.code, floor.code, room.code
                )
                room.barcode_data = barcode_data
                room.save()
                
                changes['created'].append({
                    'type': 'rooms',
                    'name': room.name,
                    'code': room.code,
                    'sqm': room.sqm,
                    'barcode': barcode_data,
                    'floor': floor.name
                })
            else:
                # Update existing room
                updated = False
                if room.sqm != row['sqm']:
                    room.sqm = row['sqm']
                    updated = True
                if room.frequency_per_day != row['frequency_per_day']:
                    room.frequency_per_day = row['frequency_per_day']
                    updated = True
                if room.frequency_per_week != row['frequency_per_week']:
                    room.frequency_per_week = row['frequency_per_week']
                    updated = True
                
                if updated:
                    room.save()
                    changes['updated'].append({
                        'type': 'rooms',
                        'name': room.name,
                        'code': room.code,
                        'changes': {
                            'sqm': row['sqm'],
                            'frequency_per_day': row['frequency_per_day'],
                            'frequency_per_week': row['frequency_per_week'],
                        }
                    })
        
        return changes
