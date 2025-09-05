from django.urls import path
from . import views

app_name = 'locations'

urlpatterns = [
    # Main location management page (simplified room-centric view)
    path('', views.location_list, name='location_list'),
    
    # Camp and Compound list views
    path('camps/', views.camp_list, name='camp_list'),
    path('camps/<uuid:camp_id>/edit/', views.camp_edit, name='camp_edit'),
    path('camps/<uuid:camp_id>/breakdown/', views.camp_breakdown, name='camp_breakdown'),
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<uuid:compound_id>/', views.compound_view, name='compound_view'),
    path('compounds/<uuid:compound_id>/edit/', views.compound_edit, name='compound_edit'),
    path('buildings/<uuid:building_id>/edit/', views.building_edit, name='building_edit'),
    path('floors/<uuid:floor_id>/edit/', views.floor_edit, name='floor_edit'),
    path('compounds/<uuid:compound_id>/breakdown/', views.compound_breakdown, name='compound_breakdown'),
    path('buildings/<uuid:building_id>/', views.building_view, name='building_view'),
    path('floors/<uuid:floor_id>/', views.floor_view, name='floor_view'),
    
    # Modal form submissions
    path('camps/create/', views.camp_create, name='camp_create'),
    path('compounds/create/', views.compound_create, name='compound_create'),
    path('buildings/create/', views.building_create, name='building_create'),
    path('floors/create/', views.floor_create, name='floor_create'),
    
    # Room management (keep for full form)
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<uuid:room_id>/', views.room_view, name='room_view'),
    path('rooms/<uuid:room_id>/update/', views.room_update, name='room_update'),
    path('rooms/<uuid:room_id>/delete/', views.room_delete, name='room_delete'),
    
    # AJAX endpoints for cascading dropdowns
    path('ajax/load-compounds/', views.ajax_load_compounds, name='ajax_load_compounds'),
    path('ajax/load-buildings/', views.ajax_load_buildings, name='ajax_load_buildings'),
    path('ajax/load-floors/', views.ajax_load_floors, name='ajax_load_floors'),
]
