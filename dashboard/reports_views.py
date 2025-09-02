"""
Reports views for the admin interface.
"""

from django.shortcuts import render, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse
import xlsxwriter
import io
from cct.mixins import AdminRequiredMixin
from locations.models import Camp, Compound, Building, Room
from scans.models import ScanEvent, DailyCleaningTask
from accounts.models import UserProfile
from authority.models import RecleanRequest, UrgentCleaningRequest


@method_decorator(login_required, name='dispatch')
class ReportsView(AdminRequiredMixin, TemplateView):
    """
    Reports dashboard with filters and export options.
    """
    template_name = 'dashboard/reports.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter options
        context['camps'] = Camp.objects.all()
        context['compounds'] = Compound.objects.all()
        context['buildings'] = Building.objects.all()
        context['users'] = UserProfile.objects.filter(user__is_active=True)
        
        # Default date range (last 30 days)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        return context


@method_decorator(login_required, name='dispatch')
class ExportReportView(AdminRequiredMixin, View):
    """
    Export reports in XLSX or PDF format.
    """
    
    def post(self, request):
        report_type = request.POST.get('report_type')
        format_type = request.POST.get('format', 'xlsx')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        camp_id = request.POST.get('camp_id')
        compound_id = request.POST.get('compound_id')
        building_id = request.POST.get('building_id')
        user_id = request.POST.get('user_id')
        
        # Parse dates
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
        
        # Build filters
        filters = {}
        if start_date:
            filters['timestamp__date__gte'] = start_date
        if end_date:
            filters['timestamp__date__lte'] = end_date
        if camp_id:
            filters['room__floor__building__compound__camp_id'] = camp_id
        if compound_id:
            filters['room__floor__building__compound_id'] = compound_id
        if building_id:
            filters['room__floor__building_id'] = building_id
        if user_id:
            filters['user_id'] = user_id
        
        if format_type == 'xlsx':
            return self.export_xlsx(report_type, filters)
        elif format_type == 'pdf':
            return self.export_pdf(report_type, filters)
        else:
            return JsonResponse({'error': 'Invalid format'}, status=400)
    
    def export_xlsx(self, report_type, filters):
        """Export data to XLSX format."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Report')
        
        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3F5876',
            'font_color': 'white',
            'border': 1
        })
        
        data_format = workbook.add_format({
            'border': 1
        })
        
        if report_type == 'scan_events':
            data = self.get_scan_events_data(filters)
            headers = ['Date', 'Time', 'Room', 'Building', 'Compound', 'Camp', 'User', 'Scan Type', 'Device ID']
            
            # Write headers
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
            
            # Write data
            for row, record in enumerate(data, 1):
                worksheet.write(row, 0, record['date'], data_format)
                worksheet.write(row, 1, record['time'], data_format)
                worksheet.write(row, 2, record['room'], data_format)
                worksheet.write(row, 3, record['building'], data_format)
                worksheet.write(row, 4, record['compound'], data_format)
                worksheet.write(row, 5, record['camp'], data_format)
                worksheet.write(row, 6, record['user'], data_format)
                worksheet.write(row, 7, record['scan_type'], data_format)
                worksheet.write(row, 8, record['device_id'], data_format)
        
        elif report_type == 'cleaning_tasks':
            data = self.get_cleaning_tasks_data(filters)
            headers = ['Date', 'Room', 'Building', 'Compound', 'Camp', 'Assigned To', 'State', 'Completed At']
            
            # Write headers
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
            
            # Write data
            for row, record in enumerate(data, 1):
                worksheet.write(row, 0, record['date'], data_format)
                worksheet.write(row, 1, record['room'], data_format)
                worksheet.write(row, 2, record['building'], data_format)
                worksheet.write(row, 3, record['compound'], data_format)
                worksheet.write(row, 4, record['camp'], data_format)
                worksheet.write(row, 5, record['assigned_to'], data_format)
                worksheet.write(row, 6, record['state'], data_format)
                worksheet.write(row, 7, record['completed_at'], data_format)
        
        elif report_type == 'reclean_requests':
            data = self.get_reclean_requests_data(filters)
            headers = ['Date', 'Room', 'Building', 'Compound', 'Camp', 'Requested By', 'Reason', 'Status', 'Resolved At']
            
            # Write headers
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
            
            # Write data
            for row, record in enumerate(data, 1):
                worksheet.write(row, 0, record['date'], data_format)
                worksheet.write(row, 1, record['room'], data_format)
                worksheet.write(row, 2, record['building'], data_format)
                worksheet.write(row, 3, record['compound'], data_format)
                worksheet.write(row, 4, record['camp'], data_format)
                worksheet.write(row, 5, record['requested_by'], data_format)
                worksheet.write(row, 6, record['reason'], data_format)
                worksheet.write(row, 7, record['status'], data_format)
                worksheet.write(row, 8, record['resolved_at'], data_format)
        
        workbook.close()
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report.xlsx"'
        return response
    
    def export_pdf(self, report_type, filters):
        """Export data to PDF format."""
        # This would use WeasyPrint or similar for PDF generation
        # For now, return a placeholder
        return HttpResponse("PDF export not yet implemented", content_type='text/plain')
    
    def get_scan_events_data(self, filters):
        """Get scan events data for export."""
        events = ScanEvent.objects.filter(**filters).select_related(
            'room__floor__building__compound__camp',
            'user'
        ).order_by('-timestamp')
        
        data = []
        for event in events:
            data.append({
                'date': event.timestamp.date(),
                'time': event.timestamp.time(),
                'room': event.room.name,
                'building': event.room.floor.building.name,
                'compound': event.room.floor.building.compound.name,
                'camp': event.room.floor.building.compound.camp.name,
                'user': event.user.get_full_name() or event.user.username,
                'scan_type': event.get_scan_type_display(),
                'device_id': event.device_id or '',
            })
        
        return data
    
    def get_cleaning_tasks_data(self, filters):
        """Get cleaning tasks data for export."""
        # Convert scan event filters to task filters
        task_filters = {}
        if 'timestamp__date__gte' in filters:
            task_filters['date__gte'] = filters['timestamp__date__gte']
        if 'timestamp__date__lte' in filters:
            task_filters['date__lte'] = filters['timestamp__date__lte']
        if 'room__floor__building__compound__camp_id' in filters:
            task_filters['room__floor__building__compound__camp_id'] = filters['room__floor__building__compound__camp_id']
        if 'room__floor__building__compound_id' in filters:
            task_filters['room__floor__building__compound_id'] = filters['room__floor__building__compound_id']
        if 'room__floor__building_id' in filters:
            task_filters['room__floor__building_id'] = filters['room__floor__building_id']
        if 'user_id' in filters:
            task_filters['assigned_to_id'] = filters['user_id']
        
        tasks = DailyCleaningTask.objects.filter(**task_filters).select_related(
            'room__floor__building__compound__camp',
            'assigned_to'
        ).order_by('-date')
        
        data = []
        for task in tasks:
            data.append({
                'date': task.date,
                'room': task.room.name,
                'building': task.room.floor.building.name,
                'compound': task.room.floor.building.compound.name,
                'camp': task.room.floor.building.compound.camp.name,
                'assigned_to': task.assigned_to.get_full_name() if task.assigned_to else '',
                'state': task.get_state_display(),
                'completed_at': task.completed_at or '',
            })
        
        return data
    
    def get_reclean_requests_data(self, filters):
        """Get reclean requests data for export."""
        # Convert scan event filters to request filters
        request_filters = {}
        if 'timestamp__date__gte' in filters:
            request_filters['created_at__date__gte'] = filters['timestamp__date__gte']
        if 'timestamp__date__lte' in filters:
            request_filters['created_at__date__lte'] = filters['timestamp__date__lte']
        if 'room__floor__building__compound__camp_id' in filters:
            request_filters['room__floor__building__compound__camp_id'] = filters['room__floor__building__compound__camp_id']
        if 'room__floor__building__compound_id' in filters:
            request_filters['room__floor__building__compound_id'] = filters['room__floor__building__compound_id']
        if 'room__floor__building_id' in filters:
            request_filters['room__floor__building_id'] = filters['room__floor__building_id']
        if 'user_id' in filters:
            request_filters['requested_by_id'] = filters['user_id']
        
        requests = RecleanRequest.objects.filter(**request_filters).select_related(
            'room__floor__building__compound__camp',
            'requested_by'
        ).order_by('-created_at')
        
        data = []
        for req in requests:
            data.append({
                'date': req.created_at.date(),
                'room': req.room.name,
                'building': req.room.floor.building.name,
                'compound': req.room.floor.building.compound.name,
                'camp': req.room.floor.building.compound.camp.name,
                'requested_by': req.requested_by.get_full_name() if req.requested_by else '',
                'reason': req.reason,
                'status': req.get_status_display(),
                'resolved_at': req.resolved_at or '',
            })
        
        return data
