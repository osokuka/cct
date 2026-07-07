from django.urls import path
from . import views
from . import urgent_cleaning_views

app_name = 'locations'

urlpatterns = [
    # Main location management page (simplified room-centric view)
    path('', views.location_list, name='location_list'),
    
    # Sites (cities)
    path('camps/', views.camp_list, name='camp_list'),
    path('camps/add/', views.site_create, name='site_create'),
    path('camps/<uuid:camp_id>/edit/', views.camp_edit, name='camp_edit'),
    path('camps/<uuid:camp_id>/delete/', views.site_delete, name='site_delete'),
    path('camps/<uuid:camp_id>/breakdown/', views.camp_breakdown, name='camp_breakdown'),

    # Zones (city zones)
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/add/', views.zone_create, name='zone_create'),
    path('compounds/<uuid:compound_id>/', views.compound_view, name='compound_view'),
    path('compounds/<uuid:compound_id>/edit/', views.compound_edit, name='compound_edit'),
    path('compounds/<uuid:compound_id>/delete/', views.zone_delete, name='zone_delete'),
    path('compounds/<uuid:compound_id>/populate/', views.zone_populate, name='zone_populate'),
    path('compounds/<uuid:compound_id>/populate/status/', views.zone_populate_status, name='zone_populate_status'),
    path('compounds/<uuid:compound_id>/measure-area/', views.zone_measure_area, name='zone_measure_area'),
    path('compounds/<uuid:compound_id>/breakdown/', views.compound_breakdown, name='compound_breakdown'),

    # Streets / segments (auto-populated from OSM; edit kept for manual tweaks)
    path('buildings/<uuid:building_id>/edit/', views.building_edit, name='building_edit'),
    path('floors/<uuid:floor_id>/edit/', views.floor_edit, name='floor_edit'),
    path('buildings/<uuid:building_id>/', views.building_view, name='building_view'),
    path('floors/<uuid:floor_id>/', views.floor_view, name='floor_view'),

    # Modal form submissions (rooms/service points management page)
    path('compounds/create/', views.compound_create, name='compound_create'),
    path('buildings/create/', views.building_create, name='building_create'),
    path('floors/create/', views.floor_create, name='floor_create'),
    
    # Dumpsters (GPS-placed, auto-assigned to zone + nearest street)
    path('dumpsters/add/', views.dumpster_create, name='dumpster_create'),
    path('dumpsters/detect-zone/', views.detect_zone, name='detect_zone'),

    # Room management (keep for full form)
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<uuid:room_id>/', views.room_view, name='room_view'),
    path('rooms/<uuid:room_id>/update/', views.room_update, name='room_update'),
    path('rooms/<uuid:room_id>/delete/', views.room_delete, name='room_delete'),
    
    # AJAX endpoints for cascading dropdowns
    path('ajax/load-compounds/', views.ajax_load_compounds, name='ajax_load_compounds'),
    path('ajax/load-buildings/', views.ajax_load_buildings, name='ajax_load_buildings'),
    path('ajax/load-floors/', views.ajax_load_floors, name='ajax_load_floors'),
    
    # Urgent Cleaning Request URLs
    path('urgent-test/', urgent_cleaning_views.test_urgent_cleaning, name='urgent_cleaning_test'),
    path('urgent-test-detail/<uuid:request_id>/', urgent_cleaning_views.test_urgent_detail, name='urgent_cleaning_test_detail'),
    path('urgent-cleaning/', urgent_cleaning_views.urgent_cleaning_request_list, name='urgent_cleaning_request_list'),
    path('urgent-cleaning/create/', urgent_cleaning_views.urgent_cleaning_request_create, name='urgent_cleaning_request_create'),
    path('urgent-cleaning/<uuid:request_id>/', urgent_cleaning_views.urgent_cleaning_request_detail, name='urgent_cleaning_request_detail'),
    path('urgent-cleaning/<uuid:request_id>/approve/', urgent_cleaning_views.urgent_cleaning_request_approve, name='urgent_cleaning_request_approve'),
    path('urgent-cleaning/<uuid:request_id>/reject/', urgent_cleaning_views.urgent_cleaning_request_reject, name='urgent_cleaning_request_reject'),
    path('urgent-cleaning/<uuid:request_id>/complete/', urgent_cleaning_views.urgent_cleaning_request_complete, name='urgent_cleaning_request_complete'),
    path('urgent-cleaning/<uuid:request_id>/cancel/', urgent_cleaning_views.urgent_cleaning_request_cancel, name='urgent_cleaning_request_cancel'),
    path('urgent-cleaning/ajax/', urgent_cleaning_views.urgent_cleaning_request_ajax, name='urgent_cleaning_request_ajax'),
    
    # AJAX endpoints for urgent cleaning
    path('ajax/load-rooms/', urgent_cleaning_views.ajax_load_rooms, name='ajax_load_rooms_urgent'),
    path('ajax/urgent-quota-info/', urgent_cleaning_views.ajax_urgent_quota_info, name='ajax_urgent_quota_info'),
    path('ajax/urgent-requests-for-cleaners/', urgent_cleaning_views.urgent_requests_for_cleaners, name='urgent_requests_for_cleaners'),
]
