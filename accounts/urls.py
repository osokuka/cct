"""
URL configuration for accounts app.
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # User Management URLs
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/update/', views.user_update, name='user_update'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    
    # Team Management URLs
    path('teams/', views.team_list, name='team_list'),
    path('teams/create/', views.team_create, name='team_create'),
    path('teams/<int:team_id>/update/', views.team_update, name='team_update'),
    path('teams/<int:team_id>/delete/', views.team_delete, name='team_delete'),
    
    # Shift Management URLs
    path('shifts/', views.shift_list, name='shift_list'),
    path('shifts/create/', views.shift_create, name='shift_create'),
    
    # Route Management URLs
    path('routes/', views.route_list, name='route_list'),
    path('routes/create/', views.route_create, name='route_create'),
    
    # Compound Assignment URLs
    path('compound-assignments/', views.compound_assignment_list, name='compound_assignment_list'),
    path('compound-assignments/create/', views.compound_assignment_create, name='compound_assignment_create'),
]