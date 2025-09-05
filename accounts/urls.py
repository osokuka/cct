"""
URL configuration for accounts app.
"""

from django.urls import path
from . import views, task_views, task_assignment_views

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
]