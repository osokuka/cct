"""
Dashboard views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from accounts.models import User, UserProfile, Team
from locations.models import Camp, Compound, Room


@login_required
def dashboard(request):
    """Main dashboard view with role-based content."""
    context = {}
    
    # Get user role
    user_role = None
    if hasattr(request.user, 'profile'):
        user_role = request.user.profile.role
    
    # Basic statistics
    context.update({
        'total_users': User.objects.filter(is_active=True).count(),
        'total_camps': Camp.objects.filter(is_active=True).count(),
        'total_compounds': Compound.objects.filter(is_active=True).count(),
        'total_rooms': Room.objects.filter(is_active=True).count(),
        'total_teams': Team.objects.filter(is_active=True).count(),
    })
    
    # Role-specific data
    if user_role == 'admin':
        # Admin sees all data
        context.update({
            'recent_users': User.objects.select_related('profile').filter(is_active=True).order_by('-date_joined')[:5],
            'recent_rooms': Room.objects.select_related('compound', 'building', 'floor').filter(is_active=True).order_by('-created_at')[:5],
        })
    elif user_role == 'manager':
        # Manager sees camp-specific data
        if hasattr(request.user, 'profile') and request.user.profile.camp:
            camp = request.user.profile.camp
            context.update({
                'camp': camp,
                'camp_compounds': Compound.objects.filter(camp=camp, is_active=True).count(),
                'camp_rooms': Room.objects.filter(camp=camp, is_active=True).count(),
                'camp_teams': Team.objects.filter(camp=camp, is_active=True).count(),
                'recent_rooms': Room.objects.select_related('compound', 'building', 'floor').filter(
                    camp=camp, is_active=True
                ).order_by('-created_at')[:5],
            })
    elif user_role == 'cleaner':
        # Cleaner sees team-specific data
        if hasattr(request.user, 'profile'):
            user_teams = Team.objects.filter(members=request.user, is_active=True)
            context.update({
                'user_teams': user_teams,
                'team_count': user_teams.count(),
            })
    
    return render(request, 'dashboard/dashboard.html', context)