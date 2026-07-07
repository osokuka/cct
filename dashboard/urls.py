"""
URL configuration for dashboard app.
"""

from django.urls import path
from . import (
    views, authority_views, industrial_views, client_import_views,
    map_views, operations_views,
)

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Operations map (Gjakova)
    path('map/', map_views.collection_map, name='collection_map'),
    path('map/data/', map_views.collection_map_data, name='collection_map_data'),

    # Operations Manager dashboard + TV wall
    path('operations/', operations_views.operations_dashboard, name='operations_dashboard'),
    path('operations/tv/', operations_views.operations_tv, name='operations_tv'),
    path('operations/data/', operations_views.operations_data, name='operations_data'),
    path('authority/', authority_views.authority_dashboard, name='authority_dashboard'),
    path('authority/tasks/', authority_views.authority_all_tasks, name='authority_all_tasks'),
    path('authority/tasks/<str:date_str>/', authority_views.authority_tasks_by_date, name='authority_tasks_by_date'),
    path('authority/compound/<uuid:compound_id>/', authority_views.authority_compound_detail, name='authority_compound_detail'),
    path('authority/daily-tasks/<int:compound_id>/', authority_views.authority_daily_tasks, name='authority_daily_tasks'),
    
    # Industrial Tables
    path('rooms/', industrial_views.rooms_table, name='rooms_table'),
    path('tasks/', industrial_views.tasks_table, name='tasks_table'),
    path('tasks/completed/', industrial_views.completed_tasks_table, name='completed_tasks_table'),
    
    # Client Bulk Import
    path('admin/import/locations/', client_import_views.ClientBulkImportView.as_view(), name='bulk_import'),
    path('admin/import/locations/process/', client_import_views.ProcessClientImportView.as_view(), name='client_import_process'),
]