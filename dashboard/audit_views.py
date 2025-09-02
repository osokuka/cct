"""
Audit logs views for the admin interface.
"""

from django.shortcuts import render, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse
import csv
from cct.mixins import AdminRequiredMixin
from audit.models import AuditLog
from accounts.models import UserProfile


@method_decorator(login_required, name='dispatch')
class AuditLogsView(AdminRequiredMixin, TemplateView):
    """
    Audit logs viewer with filters and pagination.
    """
    template_name = 'dashboard/audit_logs.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters
        user_filter = self.request.GET.get('user', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')
        status_filter = self.request.GET.get('status', '')
        action_filter = self.request.GET.get('action', '')
        
        # Build queryset
        queryset = AuditLog.objects.all().select_related('user').order_by('-timestamp')
        
        # Apply filters
        if user_filter:
            queryset = queryset.filter(
                Q(user__username__icontains=user_filter) |
                Q(user__first_name__icontains=user_filter) |
                Q(user__last_name__icontains=user_filter)
            )
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=date_to)
            except ValueError:
                pass
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if action_filter:
            queryset = queryset.filter(object_ref__icontains=action_filter)
        
        # Pagination
        from django.core.paginator import Paginator
        paginator = Paginator(queryset, 50)  # 50 logs per page
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Get unique users for filter dropdown
        users = UserProfile.objects.filter(user__is_active=True).select_related('user')
        
        context.update({
            'page_obj': page_obj,
            'users': users,
            'user_filter': user_filter,
            'date_from': date_from,
            'date_to': date_to,
            'status_filter': status_filter,
            'action_filter': action_filter,
        })
        
        return context


@method_decorator(login_required, name='dispatch')
class ExportAuditLogsView(AdminRequiredMixin, View):
    """
    Export audit logs to CSV format.
    """
    
    def post(self, request):
        # Get filter parameters
        user_filter = request.POST.get('user', '')
        date_from = request.POST.get('date_from', '')
        date_to = request.POST.get('date_to', '')
        status_filter = request.POST.get('status', '')
        action_filter = request.POST.get('action', '')
        
        # Build queryset (same logic as AuditLogsView)
        queryset = AuditLog.objects.all().select_related('user').order_by('-timestamp')
        
        if user_filter:
            queryset = queryset.filter(
                Q(user__username__icontains=user_filter) |
                Q(user__first_name__icontains=user_filter) |
                Q(user__last_name__icontains=user_filter)
            )
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=date_to)
            except ValueError:
                pass
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if action_filter:
            queryset = queryset.filter(object_ref__icontains=action_filter)
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Timestamp',
            'User',
            'IP Address',
            'Method',
            'Path',
            'Status',
            'Latency (ms)',
            'Object Reference',
            'Action'
        ])
        
        # Write data (with PII minimization)
        for log in queryset:
            # Minimize PII - don't include sensitive data
            user_info = ''
            if log.user:
                user_info = f"{log.user.username} ({log.user.get_full_name() or 'No Name'})"
            
            # Clean object reference to remove sensitive data
            object_ref = log.object_ref or ''
            if 'password' in object_ref.lower():
                object_ref = '[REDACTED - Contains Password]'
            elif 'token' in object_ref.lower():
                object_ref = '[REDACTED - Contains Token]'
            
            writer.writerow([
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                user_info,
                log.ip,
                log.method,
                log.path,
                log.status,
                log.latency_ms,
                object_ref,
                self.get_action_description(log)
            ])
        
        return response
    
    def get_action_description(self, log):
        """Get human-readable action description from audit log."""
        if not log.object_ref:
            return f"{log.method} {log.path}"
        
        # Try to extract meaningful action from object reference
        if 'create' in log.object_ref.lower():
            return 'Create'
        elif 'update' in log.object_ref.lower():
            return 'Update'
        elif 'delete' in log.object_ref.lower():
            return 'Delete'
        elif 'login' in log.object_ref.lower():
            return 'Login'
        elif 'logout' in log.object_ref.lower():
            return 'Logout'
        elif 'scan' in log.object_ref.lower():
            return 'Room Scan'
        else:
            return f"{log.method} {log.path}"
