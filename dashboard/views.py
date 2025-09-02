"""
Admin dashboard views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import csv
import io
from accounts.models import UserProfile
from locations.models import Camp, Compound, Room, Building, Floor
from scans.models import ScanEvent, DailyCleaningTask
from authority.models import RecleanRequest, UrgentCleaningRequest


@method_decorator(login_required, name='dispatch')
class AdminDashboardView(TemplateView):
    """
    Admin dashboard with comprehensive KPIs, roster status, and SLA metrics.
    """
    template_name = 'admin/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get user profile
        try:
            profile = self.request.user.profile
            context['user_profile'] = profile
        except UserProfile.DoesNotExist:
            profile = None
            context['user_profile'] = None
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Basic Infrastructure KPIs
        context['total_camps'] = Camp.objects.count()
        context['total_compounds'] = Compound.objects.count()
        context['total_buildings'] = Building.objects.count()
        context['total_rooms'] = Room.objects.filter(is_active=True).count()
        context['total_users'] = UserProfile.objects.count()
        
        # Add camps for roster tasks dropdown
        context['camps'] = Camp.objects.all().order_by('name')
        context['today'] = today
        
        # Today's Activity KPIs
        context['rooms_cleaned_today'] = ScanEvent.objects.filter(
            timestamp__date=today,
            scan_type='CLEANED'
        ).count()
        
        context['active_users'] = UserProfile.objects.filter(
            user__is_active=True
        ).count()
        
        # Roster Status KPIs (aligned to camp cut-offs)
        context['roster_status'] = self.get_roster_status(today)
        
        # SLA Metrics (based on camp cut-offs, not calendar periods)
        context['sla_metrics'] = self.get_sla_metrics(today)
        
        # Request Status
        context['pending_recleans'] = RecleanRequest.objects.filter(status='OPEN').count()
        context['urgent_requests'] = UrgentCleaningRequest.objects.filter(
            status__in=['URGENT_REQUESTED', 'IN_PROGRESS']
        ).count()
        
        # Top buildings by scans today
        context['top_buildings'] = Room.objects.filter(
            scan_events__timestamp__date=today
        ).values(
            'floor__building__name',
            'floor__building__compound__name'
        ).annotate(
            scan_count=Count('scan_events')
        ).order_by('-scan_count')[:5]
        
        # Recent activity (last 7 days)
        context['recent_scans'] = ScanEvent.objects.filter(
            timestamp__date__gte=week_ago
        ).count()
        
        # User activity breakdown
        context['user_activity'] = UserProfile.objects.filter(
            user__is_active=True
        ).values('role').annotate(
            count=Count('user')
        ).order_by('role')
        
        context['today'] = today
        
        return context
    
    def get_roster_status(self, today):
        """Get roster status aligned to camp cut-offs."""
        camps = Camp.objects.all()
        roster_data = []
        
        for camp in camps:
            # Calculate operational period based on camp's cut-off rules
            operational_period = self.get_operational_period(camp, today)
            
            # Get tasks for this operational period
            tasks = DailyCleaningTask.objects.filter(
                room__floor__building__compound__camp=camp,
                date__range=operational_period
            )
            
            planned = tasks.filter(state='PLANNED').count()
            done = tasks.filter(state='DONE').count()
            missed = tasks.filter(state='MISSED').count()
            in_progress = tasks.filter(state='IN_PROGRESS').count()
            re_clean_required = tasks.filter(state='RE_CLEAN_REQUIRED').count()
            
            total = planned + done + missed + in_progress + re_clean_required
            completion_rate = (done / total * 100) if total > 0 else 0
            
            roster_data.append({
                'camp': camp,
                'planned': planned,
                'done': done,
                'missed': missed,
                'in_progress': in_progress,
                're_clean_required': re_clean_required,
                'total': total,
                'completion_rate': round(completion_rate, 1),
                'operational_period': operational_period,
            })
        
        return roster_data
    
    def get_sla_metrics(self, today):
        """Calculate SLA metrics based on camp cut-offs."""
        camps = Camp.objects.all()
        sla_data = []
        
        for camp in camps:
            operational_period = self.get_operational_period(camp, today)
            
            # Calculate SLA based on camp's cut-off rules
            tasks = DailyCleaningTask.objects.filter(
                room__floor__building__compound__camp=camp,
                date__range=operational_period
            )
            
            total_tasks = tasks.count()
            completed_on_time = tasks.filter(
                state='DONE',
                completed_at__isnull=False
            ).count()
            
            # Calculate average completion time (simplified)
            # Note: SQLite doesn't support Avg on datetime fields, so we'll skip this for now
            avg_completion_time = None
            
            sla_percentage = (completed_on_time / total_tasks * 100) if total_tasks > 0 else 0
            
            sla_data.append({
                'camp': camp,
                'total_tasks': total_tasks,
                'completed_on_time': completed_on_time,
                'sla_percentage': round(sla_percentage, 1),
                'avg_completion_time': avg_completion_time,
            })
        
        return sla_data
    
    def get_operational_period(self, camp, today):
        """Get operational period based on camp's cut-off rules."""
        # This is a simplified version - in reality, you'd implement
        # the complex logic for week/month cut-offs and holidays
        if camp.week_cutoff_day and camp.week_cutoff_hour:
            # Calculate based on week cut-off
            days_since_cutoff = (today.weekday() + 1) % 7  # Monday = 0
            start_date = today - timedelta(days=days_since_cutoff)
            end_date = start_date + timedelta(days=6)
        else:
            # Default to current week
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        
        return [start_date, end_date]


@login_required
def admin_dashboard(request):
    """
    Function-based admin dashboard view.
    """
    view = AdminDashboardView()
    view.request = request
    return view.get(request)


@login_required
def bulk_import_view(request):
    """
    Bulk import view for CSV data.
    """
    return render(request, 'dashboard/bulk_import.html')


@login_required
@require_http_methods(["POST"])
def process_import(request):
    """
    Process CSV import - either dry run or apply.
    """
    try:
        csv_file = request.FILES.get('csv_file')
        action = request.POST.get('action', 'dry_run')
        
        if not csv_file:
            return JsonResponse({'success': False, 'error': 'No CSV file provided'})
        
        # Read CSV content
        csv_content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        if action == 'dry_run':
            result = process_csv_dry_run(csv_reader)
        else:
            result = process_csv_apply(csv_reader)
        
        return JsonResponse({'success': True, 'result': result})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def process_csv_dry_run(csv_reader):
    """
    Process CSV for dry run - analyze what would be created.
    """
    would_create = []
    conflicts = []
    summary = {
        'camps': 0,
        'compounds': 0,
        'buildings': 0,
        'floors': 0,
        'rooms': 0
    }
    
    # Track what we've seen
    seen_camps = set()
    seen_compounds = set()
    seen_buildings = set()
    seen_floors = set()
    seen_rooms = set()
    
    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
        try:
            # Extract data
            camp_name = row.get('Camp_Name', '').strip()
            compound_name = row.get('Compound_Name', '').strip()
            bldg_location = row.get('BLDG_Location', '').strip()
            
            if not all([camp_name, compound_name, bldg_location]):
                conflicts.append({
                    'row_num': row_num,
                    'error': 'Missing required fields (Camp_Name, Compound_Name, BLDG_Location)'
                })
                continue
            
            # Parse building location
            building_info = parse_building_location(bldg_location)
            if not building_info:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Could not parse building location: {bldg_location}'
                })
                continue
            
            building_name = building_info['building_name']
            floor_name = building_info['floor_name']
            room_name = building_info['room_name']
            
            # Check for conflicts
            if camp_name in seen_camps:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Camp {camp_name} already exists'
                })
            else:
                seen_camps.add(camp_name)
                would_create.append({
                    'type': 'camp',
                    'name': camp_name,
                    'code': camp_name
                })
                summary['camps'] += 1
            
            compound_key = f"{camp_name}_{compound_name}"
            if compound_key in seen_compounds:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Compound {compound_name} in camp {camp_name} already exists'
                })
            else:
                seen_compounds.add(compound_key)
                would_create.append({
                    'type': 'compound',
                    'name': compound_name,
                    'code': compound_name
                })
                summary['compounds'] += 1
            
            building_key = f"{camp_name}_{compound_name}_{building_name}"
            if building_key in seen_buildings:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Building {building_name} in compound {compound_name} already exists'
                })
            else:
                seen_buildings.add(building_key)
                would_create.append({
                    'type': 'building',
                    'name': building_name,
                    'code': building_name
                })
                summary['buildings'] += 1
            
            floor_key = f"{camp_name}_{compound_name}_{building_name}_{floor_name}"
            if floor_key in seen_floors:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Floor {floor_name} in building {building_name} already exists'
                })
            else:
                seen_floors.add(floor_key)
                would_create.append({
                    'type': 'floor',
                    'name': floor_name,
                    'code': floor_name
                })
                summary['floors'] += 1
            
            room_key = f"{camp_name}_{compound_name}_{building_name}_{floor_name}_{room_name}"
            if room_key in seen_rooms:
                conflicts.append({
                    'row_num': row_num,
                    'error': f'Room {room_name} in floor {floor_name} already exists'
                })
            else:
                seen_rooms.add(room_key)
                would_create.append({
                    'type': 'room',
                    'name': room_name,
                    'code': room_name
                })
                summary['rooms'] += 1
                
        except Exception as e:
            conflicts.append({
                'row_num': row_num,
                'error': f'Error processing row: {str(e)}'
            })
    
    return {
        'would_create': would_create,
        'conflicts': conflicts,
        'summary': summary
    }


def process_csv_apply(csv_reader):
    """
    Process CSV and actually create the data.
    """
    created_tasks = 0
    skipped_tasks = 0
    errors = []
    
    # Track what we've created
    created_camps = {}
    created_compounds = {}
    created_buildings = {}
    created_floors = {}
    created_rooms = {}
    
    for row_num, row in enumerate(csv_reader, start=2):
        try:
            # Extract data
            camp_name = row.get('Camp_Name', '').strip()
            compound_name = row.get('Compound_Name', '').strip()
            bldg_location = row.get('BLDG_Location', '').strip()
            
            if not all([camp_name, compound_name, bldg_location]):
                errors.append({
                    'row_num': row_num,
                    'error': 'Missing required fields'
                })
                continue
            
            # Parse building location
            building_info = parse_building_location(bldg_location)
            if not building_info:
                errors.append({
                    'row_num': row_num,
                    'error': f'Could not parse building location: {bldg_location}'
                })
                continue
            
            building_name = building_info['building_name']
            floor_name = building_info['floor_name']
            room_name = building_info['room_name']
            
            # Create or get camp
            if camp_name not in created_camps:
                camp, created = Camp.objects.get_or_create(
                    name=camp_name,
                    defaults={'code': camp_name}
                )
                created_camps[camp_name] = camp
            
            # Create or get compound
            compound_key = f"{camp_name}_{compound_name}"
            if compound_key not in created_compounds:
                compound, created = Compound.objects.get_or_create(
                    name=compound_name,
                    camp=created_camps[camp_name],
                    defaults={'code': compound_name}
                )
                created_compounds[compound_key] = compound
            
            # Create or get building
            building_key = f"{camp_name}_{compound_name}_{building_name}"
            if building_key not in created_buildings:
                building, created = Building.objects.get_or_create(
                    name=building_name,
                    compound=created_compounds[compound_key],
                    defaults={'code': building_name}
                )
                created_buildings[building_key] = building
            
            # Create or get floor
            floor_key = f"{camp_name}_{compound_name}_{building_name}_{floor_name}"
            if floor_key not in created_floors:
                floor, created = Floor.objects.get_or_create(
                    name=floor_name,
                    building=created_buildings[building_key],
                    defaults={'code': floor_name}
                )
                created_floors[floor_key] = floor
            
            # Create or get room
            room_key = f"{camp_name}_{compound_name}_{building_name}_{floor_name}_{room_name}"
            if room_key not in created_rooms:
                room, created = Room.objects.get_or_create(
                    name=room_name,
                    floor=created_floors[floor_key],
                    defaults={'code': room_name}
                )
                created_rooms[room_key] = room
            
            # Create cleaning task
            task_data = extract_task_data(row)
            if task_data:
                task, created = DailyCleaningTask.objects.get_or_create(
                    room=created_rooms[room_key],
                    date=task_data['date'],
                    shift_code=task_data['shift_code'],
                    defaults=task_data
                )
                if created:
                    created_tasks += 1
                else:
                    skipped_tasks += 1
            
        except Exception as e:
            errors.append({
                'row_num': row_num,
                'error': f'Error processing row: {str(e)}'
            })
    
    return {
        'created_tasks': created_tasks,
        'skipped_tasks': skipped_tasks,
        'errors': errors
    }


def parse_building_location(bldg_location):
    """
    Parse building location string to extract building, floor, and room info.
    """
    try:
        # Example: "Bld. 87, 1 single container (toilet)"
        # Extract building number
        if 'Bld.' in bldg_location:
            building_part = bldg_location.split('Bld.')[1].split(',')[0].strip()
            building_name = f"Building {building_part}"
        else:
            return None
        
        # Extract room description
        room_desc = bldg_location.split(',')[1].strip() if ',' in bldg_location else bldg_location
        
        # For now, assume ground floor
        floor_name = "Ground Floor"
        
        return {
            'building_name': building_name,
            'floor_name': floor_name,
            'room_name': room_desc
        }
    except:
        return None


def extract_task_data(row):
    """
    Extract task data from CSV row.
    """
    try:
        # Parse dates
        start_date_str = row.get('Start_Date', '').strip()
        end_date_str = row.get('End_Date', '').strip()
        
        if not start_date_str or not end_date_str:
            return None
        
        # Parse date format: "1-Oct-25"
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        if not start_date or not end_date:
            return None
        
        # Extract other data
        frequency_per_day = int(row.get('Frequency_Per_Day', 1))
        frequency_per_week = int(row.get('Frequency_Per_Week', 1))
        max_frequency_per_month = int(row.get('Max_Frequency_Per_Month', 1))
        shift_code = row.get('Shift_Code', 'MORNING').strip()
        time_window_start = row.get('Time_Window_Start', '08:00').strip()
        time_window_end = row.get('Time_Window_End', '17:00').strip()
        
        return {
            'date': start_date,
            'frequency_per_day': frequency_per_day,
            'frequency_per_week': frequency_per_week,
            'max_frequency_per_month': max_frequency_per_month,
            'shift_code': shift_code,
            'time_window_start': time_window_start,
            'time_window_end': time_window_end,
            'state': 'PLANNED'
        }
    except:
        return None


def parse_date(date_str):
    """
    Parse date string in format "1-Oct-25" to date object.
    """
    try:
        # Map month abbreviations
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        parts = date_str.split('-')
        if len(parts) != 3:
            return None
        
        day = int(parts[0])
        month_str = parts[1]
        year = int('20' + parts[2])  # Convert "25" to "2025"
        
        if month_str not in month_map:
            return None
        
        month = month_map[month_str]
        
        from datetime import date
        return date(year, month, day)
    except:
        return None
