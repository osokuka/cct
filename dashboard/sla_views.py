"""
SLA calculation and management views.
Implements per-sqm credit system and SLA reporting.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q, F
from datetime import datetime, date, timedelta
from decimal import Decimal
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Room, MonthlyRollup
from scans.models import DailyCleaningTask


@method_decorator(login_required, name='dispatch')
class SLAManagementView(AdminRequiredMixin, TemplateView):
    """
    SLA management interface with calculations and reporting.
    """
    template_name = 'dashboard/sla_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get camps for filtering
        context['camps'] = Camp.objects.all()
        
        # Get current date for default filtering
        context['current_date'] = timezone.now().date()
        
        return context


@method_decorator(login_required, name='dispatch')
class SLACalculationAPIView(AdminRequiredMixin, View):
    """
    API for SLA calculations and rollup generation.
    """
    
    def post(self, request):
        action = request.POST.get('action')
        
        if action == 'calculate_weekly':
            return self.calculate_weekly_sla(request)
        elif action == 'calculate_monthly':
            return self.calculate_monthly_sla(request)
        elif action == 'generate_rollup':
            return self.generate_monthly_rollup(request)
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
    
    def calculate_weekly_sla(self, request):
        """Calculate weekly SLA for a specific camp and date range."""
        try:
            camp_id = request.POST.get('camp_id')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            if not all([camp_id, start_date, end_date]):
                return JsonResponse({'error': 'Missing required parameters'}, status=400)
            
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            camp = Camp.objects.get(id=camp_id)
            
            # Get all rooms in the camp
            rooms = Room.objects.filter(
                floor__building__compound__camp=camp,
                service_start__lte=end_date,
                service_end__gte=start_date
            )
            
            sla_data = []
            total_required_sqm = Decimal('0')
            total_achieved_sqm = Decimal('0')
            
            for room in rooms:
                # Calculate required sqm for the period
                required_sqm = self.calculate_required_sqm(room, start_date, end_date)
                
                # Calculate achieved sqm for the period
                achieved_sqm = self.calculate_achieved_sqm(room, start_date, end_date)
                
                # Calculate SLA percentage
                sla_percent = (achieved_sqm / required_sqm * 100) if required_sqm > 0 else 0
                
                sla_data.append({
                    'room': room.name,
                    'compound': room.floor.building.compound.name,
                    'building': room.floor.building.name,
                    'required_sqm': float(required_sqm),
                    'achieved_sqm': float(achieved_sqm),
                    'sla_percent': float(sla_percent),
                    'actual_sqm': float(room.actual_sqm or room.sqm),
                    'weekly_required_sqm': float(room.weekly_required_sqm or 0)
                })
                
                total_required_sqm += required_sqm
                total_achieved_sqm += achieved_sqm
            
            # Calculate overall SLA
            overall_sla = (total_achieved_sqm / total_required_sqm * 100) if total_required_sqm > 0 else 0
            
            return JsonResponse({
                'success': True,
                'sla_data': sla_data,
                'summary': {
                    'total_required_sqm': float(total_required_sqm),
                    'total_achieved_sqm': float(total_achieved_sqm),
                    'overall_sla_percent': float(overall_sla)
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def calculate_monthly_sla(self, request):
        """Calculate monthly SLA with capping for invoicing."""
        try:
            camp_id = request.POST.get('camp_id')
            month = request.POST.get('month')  # YYYY-MM format
            
            if not all([camp_id, month]):
                return JsonResponse({'error': 'Missing required parameters'}, status=400)
            
            year, month_num = month.split('-')
            start_date = date(int(year), int(month_num), 1)
            
            # Calculate end date (last day of month)
            if month_num == '12':
                end_date = date(int(year) + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(int(year), int(month_num) + 1, 1) - timedelta(days=1)
            
            camp = Camp.objects.get(id=camp_id)
            
            # Get all rooms in the camp
            rooms = Room.objects.filter(
                floor__building__compound__camp=camp,
                service_start__lte=end_date,
                service_end__gte=start_date
            )
            
            sla_data = []
            total_required_sqm = Decimal('0')
            total_achieved_sqm = Decimal('0')
            total_capped_sqm = Decimal('0')
            total_overage = Decimal('0')
            
            for room in rooms:
                # Calculate required sqm for the month
                required_sqm = self.calculate_required_sqm(room, start_date, end_date)
                
                # Calculate achieved sqm for the month
                achieved_sqm = self.calculate_achieved_sqm(room, start_date, end_date)
                
                # Apply monthly cap
                monthly_cap = room.monthly_cap_sqm or Decimal('999999')
                capped_sqm = min(achieved_sqm, monthly_cap)
                overage = max(achieved_sqm - monthly_cap, Decimal('0'))
                
                # Calculate SLA percentage (using capped value for compliance)
                sla_percent = (capped_sqm / monthly_cap * 100) if monthly_cap > 0 else 0
                
                sla_data.append({
                    'room': room.name,
                    'compound': room.floor.building.compound.name,
                    'building': room.floor.building.name,
                    'required_sqm': float(required_sqm),
                    'achieved_sqm': float(achieved_sqm),
                    'capped_sqm': float(capped_sqm),
                    'overage': float(overage),
                    'sla_percent': float(sla_percent),
                    'monthly_cap': float(monthly_cap)
                })
                
                total_required_sqm += required_sqm
                total_achieved_sqm += achieved_sqm
                total_capped_sqm += capped_sqm
                total_overage += overage
            
            # Calculate overall SLA
            total_monthly_cap = sum(float(room.monthly_cap_sqm or 0) for room in rooms)
            overall_sla = (total_capped_sqm / total_monthly_cap * 100) if total_monthly_cap > 0 else 0
            
            return JsonResponse({
                'success': True,
                'sla_data': sla_data,
                'summary': {
                    'total_required_sqm': float(total_required_sqm),
                    'total_achieved_sqm': float(total_achieved_sqm),
                    'total_capped_sqm': float(total_capped_sqm),
                    'total_overage': float(total_overage),
                    'overall_sla_percent': float(overall_sla)
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def generate_monthly_rollup(self, request):
        """Generate monthly rollup data for reporting."""
        try:
            camp_id = request.POST.get('camp_id')
            month = request.POST.get('month')  # YYYY-MM format
            
            if not all([camp_id, month]):
                return JsonResponse({'error': 'Missing required parameters'}, status=400)
            
            year, month_num = month.split('-')
            start_date = date(int(year), int(month_num), 1)
            
            # Calculate end date (last day of month)
            if month_num == '12':
                end_date = date(int(year) + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(int(year), int(month_num) + 1, 1) - timedelta(days=1)
            
            camp = Camp.objects.get(id=camp_id)
            
            with transaction.atomic():
                # Delete existing rollups for this period
                MonthlyRollup.objects.filter(
                    camp=camp,
                    period_start=start_date,
                    period_end=end_date
                ).delete()
                
                # Get all rooms in the camp
                rooms = Room.objects.filter(
                    floor__building__compound__camp=camp,
                    service_start__lte=end_date,
                    service_end__gte=start_date
                )
                
                created_count = 0
                
                for room in rooms:
                    # Calculate required sqm for the period
                    required_sqm = self.calculate_required_sqm(room, start_date, end_date)
                    
                    # Calculate achieved sqm for the period
                    achieved_sqm = self.calculate_achieved_sqm(room, start_date, end_date)
                    
                    # Apply monthly cap
                    monthly_cap = room.monthly_cap_sqm or Decimal('999999')
                    capped_sqm = min(achieved_sqm, monthly_cap)
                    
                    # Create rollup record
                    rollup = MonthlyRollup.objects.create(
                        room=room,
                        building=room.floor.building,
                        compound=room.floor.building.compound,
                        camp=camp,
                        period_start=start_date,
                        period_end=end_date,
                        required_weekly_sqm=required_sqm,
                        achieved_weekly_sqm=achieved_sqm,
                        achieved_monthly_sqm=achieved_sqm,
                        capped_monthly_sqm=capped_sqm
                    )
                    
                    created_count += 1
                
                return JsonResponse({
                    'success': True,
                    'created_count': created_count,
                    'period': f"{start_date} to {end_date}"
                })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def calculate_required_sqm(self, room, start_date, end_date):
        """Calculate required sqm for a room in a given period."""
        # Get the effective sqm for SLA calculations
        actual_sqm = room.actual_sqm or room.sqm
        
        # Calculate operational days in the period
        operational_days = 0
        current_date = start_date
        
        while current_date <= end_date:
            # Check if room is in service window
            if (not room.service_start or current_date >= room.service_start) and \
               (not room.service_end or current_date <= room.service_end):
                operational_days += 1
            current_date += timedelta(days=1)
        
        # Calculate required sqm based on frequency
        if room.frequency_per_day > 0:
            # Use daily frequency
            required_cleans = operational_days * room.frequency_per_day
        else:
            # Use weekly frequency (distribute across operational days)
            weeks_in_period = operational_days / 7
            required_cleans = weeks_in_period * room.frequency_per_week
        
        return actual_sqm * required_cleans
    
    def calculate_achieved_sqm(self, room, start_date, end_date):
        """Calculate achieved sqm for a room in a given period."""
        # Get completed tasks in the period
        completed_tasks = DailyCleaningTask.objects.filter(
            room=room,
            date__gte=start_date,
            date__lte=end_date,
            state='done'
        )
        
        # Sum up SLA credits
        total_credit = completed_tasks.aggregate(
            total=Sum('sla_credit_sqm')
        )['total'] or Decimal('0')
        
        return total_credit
