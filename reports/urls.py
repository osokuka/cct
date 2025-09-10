"""
URL patterns for reports app.
"""

from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('compound/<uuid:compound_id>/sla-report/', views.compound_sla_report, name='compound_sla_report'),
]
