"""
URL configuration for scans app.
"""

from django.urls import path
from . import views

app_name = 'scans'

urlpatterns = [
    path('', views.CleanerDashboardView.as_view(), name='dashboard'),
    path('scan/', views.ScanView.as_view(), name='scan'),
    path('scan/history/', views.ScanHistoryView.as_view(), name='scan_history'),
]
