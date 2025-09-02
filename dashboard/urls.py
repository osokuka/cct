"""
URL configuration for admin app.
"""

from django.urls import path
from . import views
from . import reports_views
from . import audit_views
from . import import_views
from . import roster_views
from . import barcode_views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard
    path('dashboard/', views.admin_dashboard, name='dashboard'),
    
    # Reports
    path('reports/', reports_views.ReportsView.as_view(), name='reports'),
    path('reports/export/', reports_views.ExportReportView.as_view(), name='export_report'),
    
    # Audit logs
    path('audit-logs/', audit_views.AuditLogsView.as_view(), name='audit_logs'),
    path('audit-logs/export/', audit_views.ExportAuditLogsView.as_view(), name='export_audit_logs'),
    
    # Bulk import
    path('import/locations/', views.bulk_import_view, name='bulk_import'),
    path('import/process/', views.process_import, name='process_import'),
    
    # Roster management
    path('roster-management/', roster_views.RosterManagementView.as_view(), name='roster_management'),
    path('roster/generate/', roster_views.GenerateRosterView.as_view(), name='generate_roster'),
    path('roster/day-closing/', roster_views.DayClosingView.as_view(), name='day_closing'),
    
    # Roster API endpoints
    path('roster/shifts/', roster_views.RosterAPIView.as_view(), name='roster_shifts'),
    path('roster/save-policy/', roster_views.RosterAPIView.as_view(), name='roster_save_policy'),
    path('roster/add-shift/', roster_views.RosterAPIView.as_view(), name='roster_add_shift'),
    path('roster/delete-shift/', roster_views.RosterAPIView.as_view(), name='roster_delete_shift'),
    path('roster/generate/', roster_views.RosterAPIView.as_view(), name='roster_generate'),
    path('roster/current-tasks/', roster_views.RosterAPIView.as_view(), name='roster_current_tasks'),
    
    # Barcode generator
    path('barcode-generator/', barcode_views.BarcodeGeneratorView.as_view(), name='barcode_generator'),
    path('barcode/generate/', barcode_views.GenerateBarcodesView.as_view(), name='generate_barcodes'),
    path('barcode/regenerate/', barcode_views.RegenerateBarcodesView.as_view(), name='regenerate_barcodes'),
    
    # Barcode API endpoints
    path('barcode/rooms/', barcode_views.BarcodeAPIView.as_view(), name='barcode_rooms'),
    path('barcode/compounds/', barcode_views.BarcodeAPIView.as_view(), name='barcode_compounds'),
    path('barcode/buildings/', barcode_views.BarcodeAPIView.as_view(), name='barcode_buildings'),
    path('barcode/preview/', barcode_views.BarcodeAPIView.as_view(), name='barcode_preview'),
]
