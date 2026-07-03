"""
Client acceptance list CSV import views.
Updated to match the exact format provided by the client.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Floor, Room
from accounts.models import Shift, Team, Route
from accounts.task_generation import DailyCleaningTask
from cct.utils import generate_barcode_data


@method_decorator(login_required, name='dispatch')
class ClientBulkImportView(AdminRequiredMixin, TemplateView):
    """
    Client acceptance list bulk import interface.
    """
    template_name = 'dashboard/client_bulk_import.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get existing data for reference
        context['camps'] = Camp.objects.all()
        context['compounds'] = Compound.objects.all()
        context['shifts'] = Shift.objects.all()
        
        return context


@method_decorator(login_required, name='dispatch')
class ProcessClientImportView(AdminRequiredMixin, View):
    """
    Process client acceptance list CSV import with dry-run and apply functionality.
    """
    
    def post(self, request):
        action = request.POST.get('action')  # 'dry_run' or 'apply'
        csv_file = request.FILES.get('csv_file')
        camp_id = request.POST.get('camp_id')
        compound_id = request.POST.get('compound_id')
        
        if not csv_file:
            return JsonResponse({'error': 'No CSV file provided'}, status=400)
        
        if not camp_id or not compound_id:
            return JsonResponse({'error': 'Please select both camp and compound'}, status=400)
        
        try:
            # Get camp and compound
            camp = Camp.objects.get(id=camp_id)
            compound = Compound.objects.get(id=compound_id, camp=camp)
            
            # Read and parse CSV
            csv_data = self.parse_csv(csv_file)
            
            if action == 'dry_run':
                # Perform dry run - show what would be created/updated
                result = self.dry_run_import(csv_data, camp, compound)
                return JsonResponse({
                    'success': True,
                    'action': 'dry_run',
                    'result': result
                })
            
            elif action == 'apply':
                # Apply the import
                result = self.apply_import(csv_data, camp, compound)
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
        """Parse a single CSV row using client acceptance list format."""
        # Required fields from client acceptance list
        bldg_location = row.get('BLDG Location', '').strip()
        sqm = row.get('m²', '').strip()
        qty_rooms = row.get('Qty of rooms', '').strip()
        actual_sqm = row.get('Actual Sqm (m2)', '').strip()
        freq_per_day = row.get('Frequency Per Day', '').strip()
        freq_per_week = row.get('Frequency Per Week', '').strip()
        max_freq_per_month = row.get('Max Frequency Per Month', '').strip()
        total_sqm_week = row.get('Total m² Week', '').strip()
        eom_invoicing_max = row.get('EoM Invoicing max. Sqm (m2)', '').strip()
        weeks_of_service = row.get('# Weeks of service', '').strip()
        start_date = row.get('Start Date', '').strip()
        end_date = row.get('End Date', '').strip()
        
        if not all([bldg_location, sqm]):
            raise Exception("Missing required fields: BLDG Location, m²")
        
        # Parse numeric fields
        try:
            sqm_val = float(sqm)
            qty_rooms_val = int(qty_rooms) if qty_rooms else 1
            actual_sqm_val = float(actual_sqm) if actual_sqm else sqm_val
            freq_per_day_val = int(freq_per_day) if freq_per_day else 1
            freq_per_week_val = int(freq_per_week) if freq_per_week else 7
            max_freq_per_month_val = int(max_freq_per_month) if max_freq_per_month else 31
            total_sqm_week_val = float(total_sqm_week) if total_sqm_week else 0
            eom_invoicing_max_val = float(eom_invoicing_max) if eom_invoicing_max else 0
            weeks_of_service_val = int(weeks_of_service) if weeks_of_service else 0
        except ValueError as e:
            raise Exception(f"Invalid numeric value: {str(e)}")
        
        # Parse dates (DD-MMM-YY format)
        start_date_val = self.parse_date(start_date) if start_date else None
        end_date_val = self.parse_date(end_date) if end_date else None
        
        # Parse building location to extract hierarchy
        building_info = self.parse_building_location(bldg_location)
        if not building_info:
            raise Exception(f"Could not parse building location: {bldg_location}")
        
        # Validate SLA calculations (±2% tolerance)
        validation_warnings = []
        
        # Check weekly calculation
        expected_weekly = actual_sqm_val * freq_per_week_val
        if total_sqm_week_val > 0 and abs(total_sqm_week_val - expected_weekly) / expected_weekly > 0.02:
            validation_warnings.append(
                f"Total m² Week ({total_sqm_week_val}) differs from calculated ({expected_weekly:.2f}) by >2%"
            )
        
        # Check monthly calculation
        expected_monthly = actual_sqm_val * max_freq_per_month_val
        if eom_invoicing_max_val > 0 and abs(eom_invoicing_max_val - expected_monthly) / expected_monthly > 0.02:
            validation_warnings.append(
                f"EoM Invoicing max. Sqm ({eom_invoicing_max_val}) differs from calculated ({expected_monthly:.2f}) by >2%"
            )
        
        # Check frequency coherence
        if freq_per_day_val > 0 and freq_per_week_val > 0:
            expected_weekly_from_daily = actual_sqm_val * freq_per_day_val * 5  # Assume 5 operational days
            if abs(total_sqm_week_val - expected_weekly_from_daily) / total_sqm_week_val > 0.1:
                validation_warnings.append(
                    f"Frequency Per Day ({freq_per_day_val}) and Frequency Per Week ({freq_per_week_val}) may be inconsistent"
                )
        
        return {
            'row_num': row_num,
            'bldg_location': bldg_location,
            'sqm': sqm_val,
            'qty_rooms': qty_rooms_val,
            'actual_sqm': actual_sqm_val,
            'freq_per_day': freq_per_day_val,
            'freq_per_week': freq_per_week_val,
            'max_freq_per_month': max_freq_per_month_val,
            'total_sqm_week': total_sqm_week_val,
            'eom_invoicing_max': eom_invoicing_max_val,
            'weeks_of_service': weeks_of_service_val,
            'start_date': start_date_val,
            'end_date': end_date_val,
            'building_info': building_info,
            'validation_warnings': validation_warnings
        }
    
    def parse_date(self, date_str):
        """Parse date in DD-MMM-YY format."""
        if not date_str:
            return None
        
        try:
            # Handle DD-MMM-YY format (e.g., "1-Oct-25")
            return datetime.strptime(date_str, '%d-%b-%y').date()
        except ValueError:
            try:
                # Try alternative format
                return datetime.strptime(date_str, '%d-%m-%y').date()
            except ValueError:
                raise Exception(f"Invalid date format: {date_str}. Expected DD-MMM-YY")
    
    def parse_building_location(self, bldg_location):
        """Parse building location to extract hierarchy."""
        # Extract building number from "Bld. XX" pattern
        building_match = re.search(r'Bld\.\s*(\d+)', bldg_location)
        if not building_match:
            return None
        
        building_num = building_match.group(1)
        
        # Extract floor and room info
        floor_name = "Ground"  # Default floor
        room_name = f"Room {building_num}"  # Default room name
        
        # Look for specific patterns in the description
        if "toilet" in bldg_location.lower():
            room_name = f"Toilet {building_num}"
        elif "container" in bldg_location.lower():
            room_name = f"Container {building_num}"
        
        return {
            'building_name': f"Building {building_num}",
            'floor_name': floor_name,
            'room_name': room_name
        }
    
    def dry_run_import(self, csv_data, camp, compound):
        """Perform dry run - analyze what would be created/updated."""
        would_create = []
        conflicts = []
        validation_warnings = []
        
        summary = {
            'camp': camp.name,
            'compound': compound.name,
            'buildings': 0,
            'floors': 0,
            'rooms': 0,
            'total_rows': len(csv_data)
        }
        
        # Track what we've seen
        seen_buildings = set()
        seen_floors = set()
        seen_rooms = set()
        
        for row_data in csv_data:
            try:
                building_info = row_data['building_info']
                building_name = building_info['building_name']
                floor_name = building_info['floor_name']
                room_name = building_info['room_name']
                
                # Track hierarchy creation (camp and compound already exist)
                building_key = f"{compound.name}_{building_name}"
                if building_key not in seen_buildings:
                    seen_buildings.add(building_key)
                    summary['buildings'] += 1
                    would_create.append({
                        'type': 'Building',
                        'name': building_name,
                        'action': 'create'
                    })
                
                floor_key = f"{compound.name}_{building_name}_{floor_name}"
                if floor_key not in seen_floors:
                    seen_floors.add(floor_key)
                    summary['floors'] += 1
                    would_create.append({
                        'type': 'Floor',
                        'name': floor_name,
                        'action': 'create'
                    })
                
                room_key = f"{compound.name}_{building_name}_{floor_name}_{room_name}"
                if room_key not in seen_rooms:
                    seen_rooms.add(room_key)
                    summary['rooms'] += 1
                    would_create.append({
                        'type': 'Room',
                        'name': room_name,
                        'action': 'create',
                        'data': {
                            'sqm': row_data['sqm'],
                            'actual_sqm': row_data['actual_sqm'],
                            'freq_per_day': row_data['freq_per_day'],
                            'freq_per_week': row_data['freq_per_week'],
                            'total_sqm_week': row_data['total_sqm_week'],
                            'eom_invoicing_max': row_data['eom_invoicing_max']
                        }
                    })
                
                # Collect validation warnings
                validation_warnings.extend([
                    {
                        'row_num': row_data['row_num'],
                        'warning': warning
                    } for warning in row_data['validation_warnings']
                ])
                
            except Exception as e:
                conflicts.append({
                    'row_num': row_data['row_num'],
                    'error': str(e)
                })
        
        return {
            'would_create': would_create,
            'conflicts': conflicts,
            'validation_warnings': validation_warnings,
            'summary': summary
        }
    
    def apply_import(self, csv_data, camp, compound):
        """Apply the import - actually create the data."""
        created_count = 0
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for row_data in csv_data:
                try:
                    building_info = row_data['building_info']
                    building_name = building_info['building_name']
                    floor_name = building_info['floor_name']
                    room_name = building_info['room_name']
                    
                    # Create or get building
                    building, building_created = Building.objects.get_or_create(
                        compound=compound,
                        name=building_name,
                        defaults={'code': building_name}
                    )
                    
                    # Create or get floor
                    floor, floor_created = Floor.objects.get_or_create(
                        building=building,
                        name=floor_name,
                        defaults={'code': floor_name}
                    )
                    
                    # Determine space type based on room name
                    space_type = 'room'
                    if 'toilet' in room_name.lower():
                        space_type = 'toilet'
                    elif 'container' in room_name.lower():
                        space_type = 'container'

                    # Create or update room with SLA fields
                    room, room_created = Room.objects.get_or_create(
                        floor=floor,
                        room_code=room_name,
                        defaults={
                            'camp': camp,
                            'compound': compound,
                            'building': building,
                            'room_description': room_name,
                            'space_type': space_type,
                            'building_code': building.code,
                            'square_meters': Decimal(str(row_data['sqm'])),
                            'actual_sqm': Decimal(str(row_data['actual_sqm'])),
                            'quantity_of_rooms': row_data['qty_rooms'],
                            'frequency_per_day': Decimal(str(row_data['freq_per_day'])),
                            'frequency_per_week': Decimal(str(row_data['freq_per_week'])),
                            'max_frequency_per_month': row_data['max_freq_per_month'],
                            'weekly_required_sqm': Decimal(str(row_data['total_sqm_week'])),
                            'monthly_cap_sqm': Decimal(str(row_data['eom_invoicing_max'])),
                            'service_start_date': row_data['start_date'],
                            'service_end_date': row_data['end_date'],
                            'weeks_of_service': row_data['weeks_of_service'],
                            'is_active': True
                        }
                    )
                    
                    if not room_created:
                        # Update existing room with new SLA data
                        room.actual_sqm = Decimal(str(row_data['actual_sqm']))
                        room.quantity_of_rooms = row_data['qty_rooms']
                        room.frequency_per_day = Decimal(str(row_data['freq_per_day']))
                        room.frequency_per_week = Decimal(str(row_data['freq_per_week']))
                        room.max_frequency_per_month = row_data['max_freq_per_month']
                        room.weekly_required_sqm = Decimal(str(row_data['total_sqm_week']))
                        room.monthly_cap_sqm = Decimal(str(row_data['eom_invoicing_max']))
                        room.service_start_date = row_data['start_date']
                        room.service_end_date = row_data['end_date']
                        room.weeks_of_service = row_data['weeks_of_service']
                        room.save()
                        updated_count += 1
                    else:
                        created_count += 1
                    
                except Exception as e:
                    errors.append({
                        'row_num': row_data['row_num'],
                        'error': str(e)
                    })
        
        return {
            'created_count': created_count,
            'updated_count': updated_count,
            'errors': errors,
            'camp': camp.name,
            'compound': compound.name
        }
