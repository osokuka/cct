"""
URL configuration for dashboard app.
"""

from django.urls import path
from . import views, authority_views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('authority/', authority_views.authority_dashboard, name='authority_dashboard'),
    path('authority/tasks/', authority_views.authority_all_tasks, name='authority_all_tasks'),
    path('authority/tasks/<str:date_str>/', authority_views.authority_tasks_by_date, name='authority_tasks_by_date'),
    path('authority/compound/<uuid:compound_id>/', authority_views.authority_compound_detail, name='authority_compound_detail'),
    path('authority/daily-tasks/<int:compound_id>/', authority_views.authority_daily_tasks, name='authority_daily_tasks'),
]