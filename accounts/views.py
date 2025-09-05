"""
Authentication and user management views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import UserProfile, Team, Shift, Route, CompoundAssignment
from .forms import (
    UserCreateForm, UserUpdateForm, TeamCreateForm, TeamUpdateForm,
    ShiftCreateForm, RouteCreateForm, CompoundAssignmentForm
)
from locations.models import Camp, Compound


def get_user_role(request):
    """Helper function to get user role."""
    if hasattr(request.user, 'profile'):
        return request.user.profile.role
    return None


def check_permission(request, required_roles):
    """Check if user has required role."""
    user_role = get_user_role(request)
    if not user_role or user_role not in required_roles:
        messages.error(request, "You don't have permission to access this page.")
        return False
    return True


# User Management Views
@login_required
def user_list(request):
    """List all users with role-based filtering."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    users = User.objects.select_related('profile').all()
    
    # Filter by role if specified
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(profile__role=role_filter)
    
    # Filter by camp if manager
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            users = users.filter(profile__camp=camp)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)
    
    context = {
        'users': users,
        'role_choices': UserProfile.ROLE_CHOICES,
        'current_role': role_filter,
        'search_query': search_query,
    }
    return render(request, 'accounts/user_list.html', context)


@login_required
def user_create(request):
    """Create a new user."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = UserCreateForm(request.POST, request=request)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('accounts:user_list')
    else:
        form = UserCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/user_form.html', context)


@login_required
def user_update(request, user_id):
    """Update an existing user."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    user = get_object_or_404(User, id=user_id)
    
    # Check if manager can edit this user
    user_role = get_user_role(request)
    if user_role == 'manager':
        if hasattr(user, 'profile') and user.profile.role in ['admin']:
            messages.error(request, "You don't have permission to edit this user.")
            return redirect('accounts:user_list')
    
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User {user.username} updated successfully.')
            return redirect('accounts:user_list')
    else:
        form = UserUpdateForm(instance=user)
    
    context = {'form': form, 'user': user}
    return render(request, 'accounts/user_form.html', context)


@login_required
def user_delete(request, user_id):
    """Delete a user (deactivate)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        if hasattr(user, 'profile'):
            user.profile.is_active = False
            user.profile.save()
        user.is_active = False
        user.save()
        messages.success(request, f'User {user.username} deactivated successfully.')
        return redirect('accounts:user_list')
    
    context = {'user': user}
    return render(request, 'accounts/user_confirm_delete.html', context)


# Team Management Views
@login_required
def team_list(request):
    """List all teams."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    teams = Team.objects.select_related('camp', 'team_leader').prefetch_related('members').all()
    
    # Filter by camp if manager
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            teams = teams.filter(camp=camp)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        teams = teams.filter(
            Q(name__icontains=search_query) |
            Q(team_leader__username__icontains=search_query) |
            Q(camp__name__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(teams, 20)
    page_number = request.GET.get('page')
    teams = paginator.get_page(page_number)
    
    context = {
        'teams': teams,
        'search_query': search_query,
    }
    return render(request, 'accounts/team_list.html', context)


@login_required
def team_create(request):
    """Create a new team."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = TeamCreateForm(request.POST, request=request)
        if form.is_valid():
            team = form.save()
            messages.success(request, f'Team {team.name} created successfully.')
            return redirect('accounts:team_list')
    else:
        form = TeamCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/team_form.html', context)


@login_required
def team_update(request, team_id):
    """Update an existing team."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    team = get_object_or_404(Team, id=team_id)
    
    if request.method == 'POST':
        form = TeamUpdateForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, f'Team {team.name} updated successfully.')
            return redirect('accounts:team_list')
    else:
        form = TeamUpdateForm(instance=team)
    
    context = {'form': form, 'team': team}
    return render(request, 'accounts/team_form.html', context)


@login_required
def team_delete(request, team_id):
    """Delete a team (deactivate)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    team = get_object_or_404(Team, id=team_id)
    
    if request.method == 'POST':
        team.is_active = False
        team.save()
        messages.success(request, f'Team {team.name} deactivated successfully.')
        return redirect('accounts:team_list')
    
    context = {'team': team}
    return render(request, 'accounts/team_confirm_delete.html', context)


# Shift Management Views
@login_required
def shift_list(request):
    """List all shifts."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shifts = Shift.objects.select_related('camp').all()
    
    # Filter by camp if manager
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            shifts = shifts.filter(camp=camp)
    
    context = {'shifts': shifts}
    return render(request, 'accounts/shift_list.html', context)


@login_required
def shift_create(request):
    """Create a new shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = ShiftCreateForm(request.POST)
        if form.is_valid():
            shift = form.save()
            messages.success(request, f'Shift {shift.name} created successfully.')
            return redirect('accounts:shift_list')
    else:
        form = ShiftCreateForm()
    
    context = {'form': form}
    return render(request, 'accounts/shift_form.html', context)


# Route Management Views
@login_required
def route_list(request):
    """List all routes."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    routes = Route.objects.select_related('team', 'shift', 'compound').all()
    
    # Filter by camp if manager
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            routes = routes.filter(team__camp=camp)
    
    context = {'routes': routes}
    return render(request, 'accounts/route_list.html', context)


@login_required
def route_create(request):
    """Create a new route."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = RouteCreateForm(request.POST, request=request)
        if form.is_valid():
            route = form.save()
            messages.success(request, f'Route created successfully.')
            return redirect('accounts:route_list')
    else:
        form = RouteCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/route_form.html', context)


# Compound Assignment Views
@login_required
def compound_assignment_list(request):
    """List all compound assignments."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    assignments = CompoundAssignment.objects.select_related('user', 'compound', 'assigned_by').all()
    
    context = {'assignments': assignments}
    return render(request, 'accounts/compound_assignment_list.html', context)


@login_required
def compound_assignment_create(request):
    """Create a new compound assignment."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = CompoundAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.assigned_by = request.user
            assignment.save()
            messages.success(request, 'Compound assignment created successfully.')
            return redirect('accounts:compound_assignment_list')
    else:
        form = CompoundAssignmentForm()
    
    context = {'form': form}
    return render(request, 'accounts/compound_assignment_form.html', context)