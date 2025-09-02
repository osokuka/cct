"""
Views for the scans app - barcode scanning interface for cleaners.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.utils import timezone
from cct.mixins import CleanerRequiredMixin
from .models import ScanEvent, DailyCleaningTask
from locations.models import Room
from authority.models import RecleanRequest, UrgentCleaningRequest


@method_decorator(login_required, name='dispatch')
class CleanerDashboardView(CleanerRequiredMixin, TemplateView):
    """Cleaner dashboard with today's tasks and outstanding requests."""
    template_name = 'scans/cleaner_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        user = self.request.user
        
        # Get today's assigned tasks for the cleaner
        today_tasks = DailyCleaningTask.objects.filter(
            assigned_to=user,
            date=today,
            state__in=['PLANNED', 'IN_PROGRESS']
        ).select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        # Get outstanding reclean requests for rooms the cleaner is assigned to
        reclean_requests = RecleanRequest.objects.filter(
            status='OPEN',
            room__in=[task.room for task in today_tasks]
        ).select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        # Get urgent cleaning requests for rooms the cleaner is assigned to
        urgent_requests = UrgentCleaningRequest.objects.filter(
            status__in=['URGENT_REQUESTED', 'IN_PROGRESS'],
            room__in=[task.room for task in today_tasks]
        ).select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        # Get missed tasks from previous shifts (last 3 days)
        missed_tasks = DailyCleaningTask.objects.filter(
            assigned_to=user,
            date__gte=today - timezone.timedelta(days=3),
            date__lt=today,
            state='MISSED'
        ).select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        # Get recent scans (last 5)
        recent_scans = ScanEvent.objects.filter(
            user=user
        ).order_by('-timestamp')[:5].select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        context.update({
            'today_tasks': today_tasks,
            'reclean_requests': reclean_requests,
            'urgent_requests': urgent_requests,
            'missed_tasks': missed_tasks,
            'recent_scans': recent_scans,
            'today': today,
        })
        
        return context


@method_decorator(login_required, name='dispatch')
class ScanView(CleanerRequiredMixin, TemplateView):
    """Main scanning interface for cleaners."""
    template_name = 'scans/scan.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        user = self.request.user
        
        # Get today's assigned tasks for the cleaner
        today_tasks = DailyCleaningTask.objects.filter(
            assigned_to=user,
            date=today,
            state__in=['PLANNED', 'IN_PROGRESS']
        ).select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        # Get user's recent scans (last 10)
        recent_scans = ScanEvent.objects.filter(
            user=user
        ).order_by('-timestamp')[:10].select_related('room', 'room__floor', 'room__floor__building', 'room__floor__building__compound')
        
        context.update({
            'today_tasks': today_tasks,
            'recent_scans': recent_scans,
            'today': today,
        })
        
        return context


@method_decorator(login_required, name='dispatch')
class ScanHistoryView(CleanerRequiredMixin, TemplateView):
    """Scan history view for cleaners."""
    template_name = 'scans/scan_history.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get user's scan history
        scan_history = ScanEvent.objects.filter(
            user=self.request.user
        ).order_by('-timestamp')[:50]
        
        context.update({
            'scan_history': scan_history,
        })
        
        return context