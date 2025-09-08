"""
Debug views for troubleshooting camera issues.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


@login_required
def camera_debug(request):
    """Camera debug tool for troubleshooting."""
    return render(request, 'accounts/camera_debug.html')


@login_required
def simple_scanner(request):
    """Simple camera scanner for testing."""
    return render(request, 'accounts/simple_scanner.html')
