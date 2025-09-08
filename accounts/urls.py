"""
URL configuration for accounts app.
"""

from django.urls import path
from . import views, task_views, task_assignment_views, barcode_views, barcode_ajax_views, scan_views, debug_views

app_name = 'accounts'

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # User Management URLs
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<uuid:profile_uuid>/', views.user_view, name='user_view'),
    path('users/<uuid:profile_uuid>/update/', views.user_update, name='user_update'),
    path('users/<uuid:profile_uuid>/disable/', views.user_disable, name='user_disable'),
    path('users/<uuid:profile_uuid>/enable/', views.user_enable, name='user_enable'),
    path('users/<uuid:profile_uuid>/delete/', views.user_delete, name='user_delete'),
    path('users/<uuid:profile_uuid>/password-reset/', views.password_reset, name='password_reset'),
    
    # Team Management URLs
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.team_create, name='team_create'),
    path('teams/<uuid:team_id>/', views.team_view, name='team_view'),
    path('teams/<uuid:team_id>/update/', views.team_update, name='team_update'),
    path('teams/<uuid:team_id>/delete/', views.team_delete, name='team_delete'),
    path('teams/<uuid:team_id>/activate/', views.team_activate, name='team_activate'),
    
    # Shift Management URLs
    path('shifts/', views.shift_list, name='shift_list'),
    path('shifts/create/', views.shift_create, name='shift_create'),
    path('shifts/<uuid:shift_id>/', views.shift_view, name='shift_view'),
    path('shifts/<uuid:shift_id>/update/', views.shift_update, name='shift_update'),
    path('shifts/<uuid:shift_id>/deactivate/', views.shift_deactivate, name='shift_deactivate'),
    path('shifts/<uuid:shift_id>/activate/', views.shift_activate, name='shift_activate'),
    
    # Route Management URLs
    path('routes/', views.route_list, name='route_list'),
    path('routes/create/', views.route_create, name='route_create'),
    path('routes/<uuid:route_id>/', views.route_view, name='route_view'),
    path('routes/<uuid:route_id>/update/', views.route_update, name='route_update'),
    path('routes/<uuid:route_id>/deactivate/', views.route_deactivate, name='route_deactivate'),
    path('routes/<uuid:route_id>/activate/', views.route_activate, name='route_activate'),
    
    # Task Generation URLs
    path('task-generation/', task_views.task_generation_dashboard, name='task_generation_dashboard'),
    path('task-generation/preview/', task_views.task_generation_preview, name='task_generation_preview'),
    path('task-generation/execute/', task_views.task_generation_execute, name='task_generation_execute'),
    path('tasks/', task_views.task_list, name='task_list'),
    path('tasks/<uuid:task_id>/', task_views.task_detail, name='task_detail'),
    path('tasks/<uuid:task_id>/mark-done/', task_views.task_mark_done, name='task_mark_done'),
    path('tasks/<uuid:task_id>/assign-team/', task_views.task_assign_team, name='task_assign_team'),
    
    # Task Assignment URLs
    path('task-assignment/', task_assignment_views.task_assignment_dashboard, name='task_assignment_dashboard'),
    path('task-assignment/assign-to-route/', task_assignment_views.assign_tasks_to_route, name='assign_tasks_to_route'),
    path('task-assignment/bulk-assign/', task_assignment_views.bulk_task_assignment, name='bulk_task_assignment'),
    
    # Barcode Generator URLs
    path('barcode-generator/', barcode_views.barcode_generator, name='barcode_generator'),
    path('barcode-generator/room/<uuid:room_id>/', barcode_views.generate_single_barcode, name='generate_single_barcode'),
    path('barcode-generator/bulk/', barcode_views.generate_bulk_barcodes, name='generate_bulk_barcodes'),
    path('barcode-generator/camp/<uuid:camp_id>/', barcode_views.generate_camp_barcodes, name='generate_camp_barcodes'),
    path('barcode-generator/compound/<uuid:compound_id>/', barcode_views.generate_compound_barcodes, name='generate_compound_barcodes'),
    path('barcode-generator/building/<uuid:building_id>/', barcode_views.generate_building_barcodes, name='generate_building_barcodes'),
    
    # Cleaner historical tasks
    path('cleaner/historical-tasks/', views.cleaner_historical_tasks, name='cleaner_historical_tasks'),
    path('cleaner/tasks/<uuid:task_id>/', views.cleaner_task_detail, name='cleaner_task_detail'),
    
    # Scan functionality
    path('scan/', scan_views.barcode_scanner, name='barcode_scanner'),
    path('scan/lookup/<str:barcode>/', scan_views.barcode_lookup, name='barcode_lookup'),
    path('scan/task/<uuid:task_id>/', scan_views.scan_task, name='scan_task'),
    path('scan/task/<uuid:task_id>/mark-completed/', scan_views.mark_task_scanned, name='mark_task_scanned'),
    
    # Debug URLs
    path('debug/camera/', debug_views.camera_debug, name='camera_debug'),
    path('debug/simple-scanner/', debug_views.simple_scanner, name='simple_scanner'),
    
    # AJAX endpoints for dynamic filtering
    path('barcode-generator/ajax/camp/<uuid:camp_id>/compounds/', barcode_ajax_views.get_compounds_for_camp, name='get_compounds_for_camp'),
    path('barcode-generator/ajax/compound/<uuid:compound_id>/buildings/', barcode_ajax_views.get_buildings_for_compound, name='get_buildings_for_compound'),
    path('barcode-generator/ajax/building/<uuid:building_id>/floors/', barcode_ajax_views.get_floors_for_building, name='get_floors_for_building'),
]