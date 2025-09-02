"""
Roster management views for the admin interface.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta, date
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Room, Shift
from scans.models import DailyCleaningTask
from accounts.models import UserProfile


@method_decorator(login_required, name='dispatch')
class RosterManagementView(AdminRequiredMixin, TemplateView):
    """
    Roster management interface with camp policy configuration and task generation.
    """
    template_name = 'dashboard/roster_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get camps and their policies
        camps = Camp.objects.all()
        context['camps'] = camps
        
        # Get shifts
        context['shifts'] = Shift.objects.all()
        
        # Get recent roster generation info
        context['recent_tasks'] = DailyCleaningTask.objects.filter(
            date__gte=timezone.now().date() - timedelta(days=7)
        ).count()
        
        return context


@method_decorator(login_required, name='dispatch')
class GenerateRosterView(AdminRequiredMixin, View):
    """
    Generate daily cleaning tasks for a rolling horizon.
    """
    
    def post(self, request):
        action = request.POST.get('action')  # 'preview' or 'generate'
        camp_id = request.POST.get('camp_id')
        days_ahead = int(request.POST.get('days_ahead', 7))
        start_date = request.POST.get('start_date')
        
        if not camp_id:
            return JsonResponse({'error': 'Camp is required'}, status=400)
        
        try:
            camp = Camp.objects.get(id=camp_id)
            
            if start_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                start_date = timezone.now().date()
            
            if action == 'preview':
                # Preview mode - show what would be generated
                result = self.preview_roster_generation(camp, start_date, days_ahead)
                return JsonResponse({
                    'success': True,
                    'action': 'preview',
                    'result': result
                })
            
            elif action == 'generate':
                # Generate roster
                result = self.generate_roster(camp, start_date, days_ahead)
                return JsonResponse({
                    'success': True,
                    'action': 'generate',
                    'result': result
                })
            
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
                
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def preview_roster_generation(self, camp, start_date, days_ahead):
        """Preview what tasks would be generated."""
        result = {
            'camp': camp.name,
            'start_date': start_date,
            'end_date': start_date + timedelta(days=days_ahead - 1),
            'total_tasks': 0,
            'tasks_by_date': {},
            'tasks_by_room': {},
            'conflicts': []
        }
        
        # Get all active rooms in this camp
        rooms = Room.objects.filter(
            floor__building__compound__camp=camp,
            is_active=True
        ).select_related('floor__building__compound')
        
        # Get shifts for this camp
        shifts = Shift.objects.filter(camp=camp)
        
        current_date = start_date
        for day_offset in range(days_ahead):
            date = start_date + timedelta(days=day_offset)
            
            # Check if this is a holiday (simplified)
            if self.is_holiday(date, camp):
                continue
            
            tasks_for_date = []
            
            for room in rooms:
                # Calculate how many tasks this room needs today
                tasks_needed = self.calculate_daily_tasks(room, date, camp)
                
                for task_index in range(tasks_needed):
                    # Check if task already exists
                    existing_task = DailyCleaningTask.objects.filter(
                        room=room,
                        date=date,
                        index_in_day=task_index
                    ).first()
                    
                    if existing_task:
                        result['conflicts'].append({
                            'date': date,
                            'room': room.name,
                            'index': task_index,
                            'existing_state': existing_task.state
                        })
                    else:
                        # Determine shift for this task
                        shift = self.get_shift_for_task(room, task_index, shifts)
                        
                        task_info = {
                            'date': date,
                            'room': room.name,
                            'room_code': room.code,
                            'compound': room.floor.building.compound.name,
                            'building': room.floor.building.name,
                            'floor': room.floor.name,
                            'index_in_day': task_index,
                            'shift': shift.name if shift else 'No Shift',
                            'frequency_per_day': room.frequency_per_day,
                            'frequency_per_week': room.frequency_per_week,
                        }
                        
                        tasks_for_date.append(task_info)
                        result['total_tasks'] += 1
                        
                        # Add to room summary
                        room_key = f"{room.floor.building.compound.name} - {room.name}"
                        if room_key not in result['tasks_by_room']:
                            result['tasks_by_room'][room_key] = 0
                        result['tasks_by_room'][room_key] += 1
            
            result['tasks_by_date'][date.strftime('%Y-%m-%d')] = {
                'date': date,
                'task_count': len(tasks_for_date),
                'tasks': tasks_for_date
            }
        
        return result
    
    def generate_roster(self, camp, start_date, days_ahead):
        """Generate the actual roster with atomic transaction."""
        result = {
            'camp': camp.name,
            'start_date': start_date,
            'end_date': start_date + timedelta(days=days_ahead - 1),
            'created_tasks': 0,
            'skipped_tasks': 0,
            'errors': []
        }
        
        with transaction.atomic():
            # Get all active rooms in this camp
            rooms = Room.objects.filter(
                floor__building__compound__camp=camp,
                is_active=True
            ).select_related('floor__building__compound')
            
            # Get shifts for this camp
            shifts = Shift.objects.filter(camp=camp)
            
            for day_offset in range(days_ahead):
                date = start_date + timedelta(days=day_offset)
                
                # Check if this is a holiday
                if self.is_holiday(date, camp):
                    continue
                
                for room in rooms:
                    try:
                        # Calculate how many tasks this room needs today
                        tasks_needed = self.calculate_daily_tasks(room, date, camp)
                        
                        for task_index in range(tasks_needed):
                            # Check if task already exists (idempotent)
                            existing_task = DailyCleaningTask.objects.filter(
                                room=room,
                                date=date,
                                index_in_day=task_index
                            ).first()
                            
                            if existing_task:
                                result['skipped_tasks'] += 1
                                continue
                            
                            # Determine shift for this task
                            shift = self.get_shift_for_task(room, task_index, shifts)
                            
                            # Create the task
                            task = DailyCleaningTask.objects.create(
                                room=room,
                                date=date,
                                index_in_day=task_index,
                                shift=shift,
                                state='PLANNED'
                            )
                            
                            result['created_tasks'] += 1
                    
                    except Exception as e:
                        result['errors'].append({
                            'date': date,
                            'room': room.name,
                            'error': str(e)
                        })
        
        return result
    
    def calculate_daily_tasks(self, room, date, camp):
        """Calculate how many cleaning tasks a room needs on a specific date."""
        # This is a simplified calculation
        # In reality, you'd implement complex logic based on:
        # - Room frequency settings
        # - Camp cut-off rules
        # - Holiday policies
        # - Shift assignments
        
        # For now, use the room's frequency_per_day
        return room.frequency_per_day
    
    def get_shift_for_task(self, room, task_index, shifts):
        """Determine which shift should handle this task."""
        # This is a simplified assignment
        # In reality, you'd implement logic based on:
        # - Room's shift binding
        # - Time windows
        # - Load balancing
        
        if not shifts.exists():
            return None
        
        # Simple round-robin assignment
        return shifts[task_index % shifts.count()]
    
    def is_holiday(self, date, camp):
        """Check if a date is a holiday based on camp policy."""
        # This is a simplified implementation
        # In reality, you'd check against a holidays table or external API
        
        if not camp.skip_holidays:
            return False
        
        # Simple weekend check (Saturday = 5, Sunday = 6)
        if date.weekday() >= 5:
            return True
        
        # Add more holiday logic here
        return False


@method_decorator(login_required, name='dispatch')
class DayClosingView(AdminRequiredMixin, View):
    """
    Perform day closing operations - mark remaining tasks as missed.
    """
    
    def post(self, request):
        camp_id = request.POST.get('camp_id')
        closing_date = request.POST.get('closing_date')
        
        if not camp_id:
            return JsonResponse({'error': 'Camp is required'}, status=400)
        
        try:
            camp = Camp.objects.get(id=camp_id)
            
            if closing_date:
                closing_date = datetime.strptime(closing_date, '%Y-%m-%d').date()
            else:
                closing_date = timezone.now().date()
            
            result = self.perform_day_closing(camp, closing_date)
            
            return JsonResponse({
                'success': True,
                'result': result
            })
                
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def perform_day_closing(self, camp, closing_date):
        """Perform day closing operations."""
        result = {
            'camp': camp.name,
            'closing_date': closing_date,
            'tasks_marked_missed': 0,
            'sla_metrics': {}
        }
        
        with transaction.atomic():
            # Mark remaining PLANNED tasks as MISSED
            planned_tasks = DailyCleaningTask.objects.filter(
                room__floor__building__compound__camp=camp,
                date=closing_date,
                state='PLANNED'
            )
            
            result['tasks_marked_missed'] = planned_tasks.count()
            planned_tasks.update(state='MISSED')
            
            # Calculate SLA metrics for this operational period
            operational_period = self.get_operational_period(camp, closing_date)
            
            all_tasks = DailyCleaningTask.objects.filter(
                room__floor__building__compound__camp=camp,
                date__range=operational_period
            )
            
            total_tasks = all_tasks.count()
            completed_tasks = all_tasks.filter(state='DONE').count()
            missed_tasks = all_tasks.filter(state='MISSED').count()
            
            result['sla_metrics'] = {
                'operational_period': operational_period,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'missed_tasks': missed_tasks,
                'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
                'miss_rate': (missed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            }
        
        return result
    
    def get_operational_period(self, camp, date):
        """Get operational period based on camp's cut-off rules."""
        # This is a simplified version
        if camp.week_cutoff_day and camp.week_cutoff_hour:
            # Calculate based on week cut-off
            days_since_cutoff = (date.weekday() + 1) % 7
            start_date = date - timedelta(days=days_since_cutoff)
            end_date = start_date + timedelta(days=6)
        else:
            # Default to current week
            start_date = date - timedelta(days=date.weekday())
            end_date = start_date + timedelta(days=6)
        
        return [start_date, end_date]


@method_decorator(login_required, name='dispatch')
class RosterAPIView(AdminRequiredMixin, View):
    """
    API endpoints for roster management.
    """
    
    def get(self, request):
        """Get shifts for a camp."""
        camp_id = request.GET.get('camp_id')
        if not camp_id:
            return JsonResponse({'error': 'Camp ID required'}, status=400)
        
        try:
            shifts = Shift.objects.filter(camp_id=camp_id).values(
                'id', 'name', 'start_time', 'end_time'
            )
            return JsonResponse({
                'success': True,
                'shifts': list(shifts)
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def post(self, request):
        """Handle various roster operations based on URL path."""
        import json
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON: {str(e)}'}, status=400)
        
        # Determine action based on URL path
        if 'save-policy' in request.path:
            return self.save_camp_policy(data)
        elif 'add-shift' in request.path:
            return self.add_shift(data)
        elif 'delete-shift' in request.path:
            return self.delete_shift(data)
        elif 'generate' in request.path:
            return self.generate_roster_api(data)
        elif 'current-tasks' in request.path:
            return self.get_current_tasks_api(data)
        else:
            return JsonResponse({'error': f'Invalid endpoint: {request.path}'}, status=400)
    
    def save_camp_policy(self, data):
        """Save camp policy configuration."""
        try:
            from datetime import time
            
            camp_id = data.get('camp_id')
            camp = Camp.objects.get(id=camp_id)
            
            camp.timezone = data.get('timezone', camp.timezone)
            camp.week_cutoff_day = int(data.get('week_cutoff_day', camp.week_cutoff_day))
            
            # Parse time strings to extract hour
            week_cutoff_hour_str = data.get('week_cutoff_hour', '23:59')
            if ':' in week_cutoff_hour_str:
                week_cutoff_hour = int(week_cutoff_hour_str.split(':')[0])
            else:
                week_cutoff_hour = int(week_cutoff_hour_str)
            camp.week_cutoff_hour = week_cutoff_hour
            
            camp.month_cutoff_day = int(data.get('month_cutoff_day', camp.month_cutoff_day))
            
            # Parse time strings to extract hour
            month_cutoff_hour_str = data.get('month_cutoff_hour', '23:59')
            if ':' in month_cutoff_hour_str:
                month_cutoff_hour = int(month_cutoff_hour_str.split(':')[0])
            else:
                month_cutoff_hour = int(month_cutoff_hour_str)
            camp.month_cutoff_hour = month_cutoff_hour
            
            camp.skip_holidays = data.get('skip_holidays', camp.skip_holidays)
            
            camp.save()
            
            return JsonResponse({'success': True})
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid data format: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def add_shift(self, data):
        """Add a new shift to a camp."""
        try:
            from datetime import time
            
            camp_id = data.get('camp_id')
            name = data.get('name')
            start_time_str = data.get('start_time')
            end_time_str = data.get('end_time')
            
            # Parse time strings to time objects
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)
            
            camp = Camp.objects.get(id=camp_id)
            
            shift = Shift.objects.create(
                camp=camp,
                name=name,
                start_time=start_time,
                end_time=end_time
            )
            
            return JsonResponse({
                'success': True,
                'shift_id': shift.id
            })
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid time format: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def delete_shift(self, data):
        """Delete a shift."""
        try:
            shift_id = data.get('shift_id')
            shift = Shift.objects.get(id=shift_id)
            shift.delete()
            
            return JsonResponse({'success': True})
        except Shift.DoesNotExist:
            return JsonResponse({'error': 'Shift not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def generate_roster_api(self, data):
        """Generate roster via API."""
        try:
            camp_id = data.get('camp_id')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            days = data.get('days', 7)
            action = data.get('action', 'preview')
            

            if not camp_id:
                return JsonResponse({'error': 'Camp ID is required'}, status=400)
            
            camp = Camp.objects.get(id=camp_id)
            
            if start_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                start_date = timezone.now().date()
            
            # Calculate days based on end_date if provided, otherwise use days parameter
            if end_date:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                days = (end_date - start_date).days + 1
            else:
                days = int(days)
            
            if days <= 0:
                return JsonResponse({'error': 'Invalid date range'}, status=400)
            
            # Use the existing roster generation logic
            roster_view = GenerateRosterView()
            
            if action == 'preview':
                result = roster_view.preview_roster_generation(camp, start_date, days)
                return JsonResponse({
                    'success': True,
                    'result': result
                })
            else:
                result = roster_view.generate_roster(camp, start_date, days)
                return JsonResponse({
                    'success': True,
                    'result': result
                })
                
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid date format: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def get_current_tasks_api(self, data):
        """Get current roster tasks grouped by teams/shifts."""
        try:
            from django.contrib.auth.models import User
            
            camp_id = data.get('camp_id')
            date_filter = data.get('date', timezone.now().date().isoformat())
            
            
            if not camp_id:
                return JsonResponse({'error': 'Camp ID is required'}, status=400)
            
            camp = Camp.objects.get(id=camp_id)
            
            # Parse date filter
            if isinstance(date_filter, str):
                date_filter = datetime.strptime(date_filter, '%Y-%m-%d').date()
            
            # Get all tasks for the camp on the specified date
            tasks = DailyCleaningTask.objects.filter(
                room__floor__building__compound__camp=camp,
                date=date_filter
            ).select_related(
                'room__floor__building__compound',
                'shift',
                'assigned_to'
            ).order_by('shift__start_time', 'room__name')
            
            # Group tasks by shift (team)
            teams_data = {}
            unassigned_tasks = []
            
            for task in tasks:
                if task.shift:
                    shift_name = task.shift.name
                    if shift_name not in teams_data:
                        teams_data[shift_name] = {
                            'shift': {
                                'name': task.shift.name,
                                'start_time': task.shift.start_time.strftime('%H:%M'),
                                'end_time': task.shift.end_time.strftime('%H:%M')
                            },
                            'tasks': [],
                            'stats': {
                                'total': 0,
                                'planned': 0,
                                'in_progress': 0,
                                'done': 0,
                                'missed': 0,
                                're_clean_required': 0
                            }
                        }
                    
                    # Add task to team
                    task_data = {
                        'id': str(task.id),
                        'room': {
                            'name': task.room.name,
                            'code': task.room.code,
                            'compound': task.room.floor.building.compound.name,
                            'building': task.room.floor.building.name,
                            'floor': task.room.floor.name
                        },
                        'state': task.state.lower(),
                        'assigned_to': {
                            'id': task.assigned_to.id if task.assigned_to else None,
                            'username': task.assigned_to.username if task.assigned_to else None,
                            'full_name': f"{task.assigned_to.first_name} {task.assigned_to.last_name}".strip() if task.assigned_to else None
                        } if task.assigned_to else None,
                        'index_in_day': task.index_in_day,
                        'created_at': task.created_at.isoformat(),
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None
                    }
                    
                    teams_data[shift_name]['tasks'].append(task_data)
                    teams_data[shift_name]['stats']['total'] += 1
                    teams_data[shift_name]['stats'][task.state.lower()] += 1
                else:
                    # Unassigned tasks
                    unassigned_tasks.append({
                        'id': str(task.id),
                        'room': {
                            'name': task.room.name,
                            'code': task.room.code,
                            'compound': task.room.floor.building.compound.name,
                            'building': task.room.floor.building.name,
                            'floor': task.room.floor.name
                        },
                        'state': task.state.lower(),
                        'assigned_to': None,
                        'index_in_day': task.index_in_day,
                        'created_at': task.created_at.isoformat(),
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None
                    })
            
            # Convert to list format for easier frontend handling
            teams_list = []
            for shift_name, team_data in teams_data.items():
                teams_list.append(team_data)
            
            # Sort teams by shift start time
            teams_list.sort(key=lambda x: x['shift']['start_time'])
            
            return JsonResponse({
                'success': True,
                'date': date_filter.isoformat(),
                'camp': {
                    'id': str(camp.id),
                    'name': camp.name,
                    'code': camp.code
                },
                'teams': teams_list,
                'unassigned_tasks': unassigned_tasks,
                'summary': {
                    'total_tasks': tasks.count(),
                    'total_teams': len(teams_list),
                    'unassigned_count': len(unassigned_tasks)
                }
            })
            
        except Camp.DoesNotExist:
            return JsonResponse({'error': 'Camp not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid date format: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
