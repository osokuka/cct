"""
URL configuration for dashboard app.
"""

from django.urls import path
from . import views, authority_views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('authority/', authority_views.authority_dashboard, name='authority_dashboard'),
    path('authority/compound/<uuid:compound_id>/', authority_views.authority_compound_detail, name='authority_compound_detail'),
]