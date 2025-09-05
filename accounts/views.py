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
from django.utils import timezone
import time

from .models import UserProfile, Team, Shift, Route, CompoundAssignment
from .forms import (
    UserCreateForm, UserUpdateForm, TeamCreateForm, TeamUpdateForm,
    ShiftCreateForm, ShiftUpdateForm, RouteCreateForm, RouteUpdateForm, CompoundAssignmentForm
)
from locations.models import Camp, Compound
from audit.models import AuditLog


# Authentication Views
def login_view(request):
    """User login view."""
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')
    
    # Create a simple form for the template
    from django import forms
    
    class LoginForm(forms.Form):
        username = forms.CharField(
            max_length=150,
            widget=forms.TextInput(attrs={
                'class': 'w-full pl-12 pr-4 py-3 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter your username',
                'autocomplete': 'username'
            })
        )
        password = forms.CharField(
            widget=forms.PasswordInput(attrs={
                'class': 'w-full pl-12 pr-4 py-3 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter your password',
                'autocomplete': 'current-password'
            })
        )
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            from django.contrib.auth import authenticate, login
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                
                # Log audit event
                log_audit_event(
                    request, 
                    'USER_LOGIN', 
                    object_ref=f'User:{user.id}',
                    details={
                        'username': user.username,
                        'role': user.profile.role if hasattr(user, 'profile') else None
                    }
                )
                
                # Get user role for redirect
                user_role = user.profile.role if hasattr(user, 'profile') else None
                
                # Redirect based on user role
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                elif user_role == 'admin':
                    return redirect('/admin/')
                else:
                    return redirect('dashboard:dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """User logout view."""
    if request.user.is_authenticated:
        # Log audit event before logout
        log_audit_event(
            request, 
            'USER_LOGOUT', 
            object_ref=f'User:{request.user.id}',
            details={
                'username': request.user.username,
                'role': request.user.profile.role if hasattr(request.user, 'profile') else None
            }
        )
        
        from django.contrib.auth import logout
        logout(request)
        messages.info(request, 'You have been logged out successfully.')
    
    return redirect('accounts:login')


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


def get_authority_compound_ids(user):
    """Get compound IDs that an Authority user can access."""
    if not hasattr(user, 'profile') or user.profile.role != 'authority':
        return []
    return list(CompoundAssignment.objects.filter(
        user=user, 
        is_active=True
    ).values_list('compound_id', flat=True))


def log_audit_event(request, action, object_ref=None, details=None, status_code=200):
    """Log an audit event for user actions."""
    try:
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Calculate latency (simplified - in production, use middleware)
        latency_ms = 0  # This would be calculated by middleware
        
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            ip_address=ip,
            method=request.method,
            path=request.path,
            status_code=status_code,
            latency_ms=latency_ms,
            object_ref=object_ref,
            action=action,
            details=details or {}
        )
    except Exception as e:
        # Don't let audit logging break the main functionality
        pass


# User Management Views
@login_required
def user_list(request):
    """List all users with role-based filtering and RBAC enforcement."""
    # Admin, Supervisor, and Manager can view users
    if not check_permission(request, ['admin', 'supervisor', 'manager']):
        return redirect('accounts:login')
    
    # Get all users for statistics (before filtering)
    all_users = User.objects.select_related('profile').all()
    
    # Calculate statistics
    total_users = all_users.count()
    active_users = all_users.filter(is_active=True, profile__is_active=True).count()
    
    # Get last user created
    last_user_created = all_users.order_by('-date_joined').first()
    last_user_created_info = {
        'username': last_user_created.username if last_user_created else 'N/A',
        'date': last_user_created.date_joined.strftime('%Y-%m-%d %H:%M') if last_user_created else 'Never'
    }
    
    # Count users who logged in today
    from datetime import datetime, timedelta
    today = timezone.now().date()
    online_today = all_users.filter(last_login__date=today).count()
    
    # Get last password change from audit logs
    from audit.models import AuditLog
    last_password_change_log = AuditLog.objects.filter(
        action='PASSWORD_RESET'
    ).order_by('-timestamp').first()
    
    last_password_change = {
        'user': last_password_change_log.details.get('username', 'N/A') if last_password_change_log else 'N/A',
        'date': last_password_change_log.timestamp.strftime('%Y-%m-%d %H:%M') if last_password_change_log else 'Never'
    }
    
    # Apply filters for the actual user list
    users = all_users.order_by('username')
    
    # Filter by role if specified
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(profile__role=role_filter)
    
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
        'stats': {
            'total_users': total_users,
            'active_users': active_users,
            'last_user_created': last_user_created_info,
            'online_today': online_today,
            'last_password_change': last_password_change,
        }
    }
    return render(request, 'accounts/user_list.html', context)


@login_required
def user_create(request):
    """Create a new user with RBAC enforcement."""
    # Only Admin can create users
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    print(f"DEBUG: User create view called. Method: {request.method}")
    
    if request.method == 'POST':
        print(f"DEBUG: POST data: {request.POST}")
        form = UserCreateForm(request.POST, request=request)
        print(f"DEBUG: Form is valid: {form.is_valid()}")
        
        if not form.is_valid():
            print(f"DEBUG: Form errors: {form.errors}")
            messages.error(request, f'Please correct the errors below: {form.errors}')
        else:
            try:
                user = form.save()
                print(f"DEBUG: User created successfully: {user.username} (ID: {user.id})")
                messages.success(request, f'User {user.username} created successfully.')
                
                # Log audit event
                log_audit_event(
                    request, 
                    'USER_CREATED', 
                    object_ref=f'User:{user.id}',
                    details={
                        'username': user.username,
                        'role': user.profile.role if hasattr(user, 'profile') else None,
                        'email': user.email
                    }
                )
                
                return redirect('accounts:user_list')
            except Exception as e:
                print(f"DEBUG: Error creating user: {str(e)}")
                messages.error(request, f'Error creating user: {str(e)}')
    else:
        form = UserCreateForm(request=request)
        print(f"DEBUG: Form created for GET request")
    
    context = {'form': form}
    return render(request, 'accounts/user_create.html', context)


@login_required
def user_update(request, profile_uuid):
    """Update an existing user with RBAC enforcement."""
    # Only Admin can update users
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=user, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, f'User {user.username} updated successfully.')
            
            # Log audit event
            log_audit_event(
                request, 
                'USER_UPDATED', 
                object_ref=f'User:{user.id}',
                details={
                    'username': user.username,
                    'role': user.profile.role if hasattr(user, 'profile') else None,
                    'email': user.email
                }
            )
            
            return redirect('accounts:user_list')
    else:
        form = UserUpdateForm(instance=user, request=request)
    
    context = {'form': form, 'user': user}
    return render(request, 'accounts/user_update.html', context)


@login_required
def user_view(request, profile_uuid):
    """View user details with RBAC enforcement."""
    # Admin, Supervisor, and Manager can view user details
    if not check_permission(request, ['admin', 'supervisor', 'manager']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    # Log audit event
    log_audit_event(
        request, 
        'USER_VIEWED', 
        object_ref=f'User:{user.id}',
        details={
            'username': user.username,
            'role': user.profile.role if hasattr(user, 'profile') else None
        }
    )
    
    context = {'viewed_user': user}
    return render(request, 'accounts/user_view.html', context)


@login_required
def user_disable(request, profile_uuid):
    """Disable a user (set is_active=False)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    # Prevent disabling admin users
    if user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'admin'):
        messages.error(request, 'Cannot disable admin users.')
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        # Disable both user and profile
        if hasattr(user, 'profile'):
            user.profile.is_active = False
            user.profile.save()
        user.is_active = False
        user.save()
        
        messages.success(request, f'User {user.username} has been disabled successfully.')
        
        # Log audit event
        log_audit_event(
            request, 
            'USER_DISABLED', 
            object_ref=f'User:{user.id}',
            details={
                'username': user.username,
                'role': user.profile.role if hasattr(user, 'profile') else None,
                'disabled_by': request.user.username
            }
        )
        
        return redirect('accounts:user_list')
    
    context = {'user': user, 'action': 'disable'}
    return render(request, 'accounts/user_confirm_disable.html', context)


@login_required
def user_enable(request, profile_uuid):
    """Enable a user (set is_active=True)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        # Enable both user and profile
        if hasattr(user, 'profile'):
            user.profile.is_active = True
            user.profile.save()
        user.is_active = True
        user.save()
        
        messages.success(request, f'User {user.username} has been enabled successfully.')
        
        # Log audit event
        log_audit_event(
            request, 
            'USER_ENABLED', 
            object_ref=f'User:{user.id}',
            details={
                'username': user.username,
                'role': user.profile.role if hasattr(user, 'profile') else None,
                'enabled_by': request.user.username
            }
        )
        
        return redirect('accounts:user_list')
    
    context = {'user': user, 'action': 'enable'}
    return render(request, 'accounts/user_confirm_disable.html', context)


@login_required
def user_delete(request, profile_uuid):
    """Permanently delete a user (complete removal from database)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    # Prevent deleting admin users
    if user.is_superuser or (hasattr(user, 'profile') and user.profile.role == 'admin'):
        messages.error(request, 'Cannot delete admin users.')
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        username = user.username
        user_id = user.id
        
        # Delete the user (this will cascade to profile due to CASCADE relationship)
        user.delete()
        
        messages.success(request, f'User {username} has been permanently deleted.')
        
        # Log audit event
        log_audit_event(
            request, 
            'USER_DELETED', 
            object_ref=f'User:{user_id}',
            details={
                'username': username,
                'deleted_by': request.user.username
            }
        )
        
        return redirect('accounts:user_list')
    
    context = {'user': user, 'action': 'delete'}
    return render(request, 'accounts/user_confirm_delete.html', context)


@login_required
def password_reset(request, profile_uuid):
    """Admin-only password reset functionality."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    try:
        profile = UserProfile.objects.get(uuid=profile_uuid)
        user = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('accounts:user_list')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not new_password or not confirm_password:
            messages.error(request, 'Both password fields are required.')
        elif new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        elif len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, f'Password for {user.username} has been reset successfully.')
            
            # Log audit event
            log_audit_event(
                request, 
                'PASSWORD_RESET', 
                object_ref=f'User:{user.id}',
                details={
                    'username': user.username,
                    'reset_by': request.user.username
                }
            )
            
            return redirect('accounts:user_list')
    
    context = {'user': user}
    return render(request, 'accounts/password_reset.html', context)


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
    
    # Filter by camp if specified
    camp_filter = request.GET.get('camp')
    if camp_filter:
        teams = teams.filter(camp_id=camp_filter)
    
    # Pagination
    paginator = Paginator(teams, 20)
    page_number = request.GET.get('page')
    teams = paginator.get_page(page_number)
    
    # Calculate statistics
    all_teams = Team.objects.all()
    total_teams = all_teams.count()
    active_teams = all_teams.filter(is_active=True).count()
    total_members = sum(team.members.count() for team in all_teams)
    avg_team_size = total_members / total_teams if total_teams > 0 else 0
    
    # Get available camps for filter
    from locations.models import Camp
    camps = Camp.objects.filter(is_active=True)
    
    context = {
        'teams': teams,
        'search_query': search_query,
        'current_camp': camp_filter,
        'camps': camps,
        'stats': {
            'total_teams': total_teams,
            'active_teams': active_teams,
            'total_members': total_members,
            'avg_team_size': avg_team_size,
        }
    }
    return render(request, 'accounts/team_list.html', context)


@login_required
def team_view(request, team_id):
    """View team details."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    try:
        team = Team.objects.select_related('camp', 'team_leader').prefetch_related('members', 'routes__compounds', 'routes__shift').get(id=team_id)
    except Team.DoesNotExist:
        messages.error(request, 'Team not found.')
        return redirect('accounts:team_list')
    
    # Log audit event
    log_audit_event(
        request, 
        'TEAM_VIEWED', 
        object_ref=f'Team:{team.id}',
        details={
            'team_name': team.name,
            'camp': team.camp.name if team.camp else None,
            'team_leader': team.team_leader.username
        }
    )
    
    # Calculate active members count
    active_members_count = team.members.filter(is_active=True, profile__is_active=True).count()
    
    context = {
        'team': team,
        'active_members_count': active_members_count
    }
    return render(request, 'accounts/team_view.html', context)


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
            
            # Log audit event
            log_audit_event(
                request, 
                'TEAM_CREATED', 
                object_ref=f'Team:{team.id}',
                details={
                    'team_name': team.name,
                    'camp': team.camp.name if team.camp else None,
                    'team_leader': team.team_leader.username,
                    'member_count': team.members.count()
                }
            )
            
            return redirect('accounts:team_list')
    else:
        form = TeamCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/team_create.html', context)


@login_required
def team_update(request, team_id):
    """Update an existing team."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    team = get_object_or_404(Team, id=team_id)
    
    if request.method == 'POST':
        form = TeamUpdateForm(request.POST, instance=team, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, f'Team {team.name} updated successfully.')
            
            # Log audit event
            log_audit_event(
                request, 
                'TEAM_UPDATED', 
                object_ref=f'Team:{team.id}',
                details={
                    'team_name': team.name,
                    'camp': team.camp.name if team.camp else None,
                    'team_leader': team.team_leader.username,
                    'member_count': team.members.count()
                }
            )
            
            return redirect('accounts:team_list')
    else:
        form = TeamUpdateForm(instance=team, request=request)
    
    # Get current member IDs for template
    current_member_ids = list(team.members.values_list('id', flat=True))
    
    context = {
        'form': form, 
        'team': team,
        'current_member_ids': current_member_ids
    }
    return render(request, 'accounts/team_update.html', context)


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
        
        # Log audit event
        log_audit_event(
            request, 
            'TEAM_DEACTIVATED', 
            object_ref=f'Team:{team.id}',
            details={
                'team_name': team.name,
                'camp': team.camp.name if team.camp else None,
                'team_leader': team.team_leader.username,
                'member_count': team.members.count(),
                'route_count': team.routes.count()
            }
        )
        
        return redirect('accounts:team_list')
    
    context = {'team': team}
    return render(request, 'accounts/team_confirm_delete.html', context)


@login_required
def team_activate(request, team_id):
    """Activate a team (reactivate)."""
    if not check_permission(request, ['admin']):
        return redirect('accounts:login')
    
    team = get_object_or_404(Team, id=team_id)
    
    if request.method == 'POST':
        team.is_active = True
        team.save()
        messages.success(request, f'Team {team.name} activated successfully.')
        
        # Log audit event
        log_audit_event(
            request, 
            'TEAM_ACTIVATED', 
            object_ref=f'Team:{team.id}',
            details={
                'team_name': team.name,
                'camp': team.camp.name if team.camp else None,
                'team_leader': team.team_leader.username,
                'member_count': team.members.count()
            }
        )
        
        return redirect('accounts:team_list')
    
    context = {'team': team, 'action': 'activate'}
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
    
    routes = Route.objects.select_related('team', 'shift', 'team__camp', 'shift__camp').prefetch_related('compounds__camp').all()
    
    # Filter by camp if manager
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp:
            routes = routes.filter(team__camp=camp)
    
    # Calculate statistics
    active_routes_count = routes.filter(is_active=True).count()
    teams_with_routes_count = routes.filter(is_active=True).values('team').distinct().count()
    # Count unique compounds across all active routes
    active_routes = routes.filter(is_active=True)
    compound_ids = set()
    for route in active_routes:
        compound_ids.update(route.compounds.values_list('id', flat=True))
    compounds_covered_count = len(compound_ids)
    
    context = {
        'routes': routes,
        'active_routes_count': active_routes_count,
        'teams_with_routes_count': teams_with_routes_count,
        'compounds_covered_count': compounds_covered_count
    }
    return render(request, 'accounts/route_list.html', context)


@login_required
def route_view(request, route_id):
    """View route details."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    try:
        route = Route.objects.select_related('team', 'shift', 'team__camp', 'shift__camp').prefetch_related('team__members', 'compounds__camp').get(id=route_id)
    except Route.DoesNotExist:
        messages.error(request, 'Route not found.')
        return redirect('accounts:route_list')
    
    # Check camp access for managers
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp and route.team.camp != camp:
            messages.error(request, 'You do not have permission to view this route.')
            return redirect('accounts:route_list')
    
    # Log audit event
    compound_names = ", ".join([c.name for c in route.compounds.all()])
    log_audit_event(
        request, 
        'ROUTE_VIEWED', 
        object_ref=f'Route:{route.id}',
        details={
            'team_name': route.team.name,
            'shift_name': route.shift.name,
            'compound_names': compound_names,
            'priority': route.priority
        }
    )
    
    context = {'route': route}
    return render(request, 'accounts/route_view.html', context)


@login_required
def route_create(request):
    """Create a new route."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = RouteCreateForm(request.POST, request=request)
        if form.is_valid():
            route = form.save()
            
            # Log audit event
            compound_names = ", ".join([c.name for c in route.compounds.all()])
            log_audit_event(
                request, 
                'ROUTE_CREATED', 
                object_ref=f'Route:{route.id}',
                details={
                    'team_name': route.team.name,
                    'shift_name': route.shift.name,
                    'compound_names': compound_names,
                    'priority': route.priority
                }
            )
            
            messages.success(request, f'Route created successfully.')
            return redirect('accounts:route_view', route_id=route.id)
    else:
        form = RouteCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/route_form.html', context)


@login_required
def route_update(request, route_id):
    """Update a route."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        messages.error(request, 'Route not found.')
        return redirect('accounts:route_list')
    
    # Check camp access for managers
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp and route.team.camp != camp:
            messages.error(request, 'You do not have permission to edit this route.')
            return redirect('accounts:route_list')
    
    if request.method == 'POST':
        form = RouteUpdateForm(request.POST, instance=route, request=request)
        if form.is_valid():
            route = form.save()
            
            # Log audit event
            compound_names = ", ".join([c.name for c in route.compounds.all()])
            log_audit_event(
                request, 
                'ROUTE_UPDATED', 
                object_ref=f'Route:{route.id}',
                details={
                    'team_name': route.team.name,
                    'shift_name': route.shift.name,
                    'compound_names': compound_names,
                    'priority': route.priority
                }
            )
            
            messages.success(request, f'Route updated successfully.')
            return redirect('accounts:route_view', route_id=route.id)
    else:
        form = RouteUpdateForm(instance=route, request=request)
    
    context = {'form': form, 'route': route}
    return render(request, 'accounts/route_form.html', context)


@login_required
def route_deactivate(request, route_id):
    """Deactivate a route."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        messages.error(request, 'Route not found.')
        return redirect('accounts:route_list')
    
    # Check camp access for managers
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp and route.team.camp != camp:
            messages.error(request, 'You do not have permission to modify this route.')
            return redirect('accounts:route_list')
    
    if request.method == 'POST':
        route.is_active = False
        route.save()
        
        # Log audit event
        compound_names = ", ".join([c.name for c in route.compounds.all()])
        log_audit_event(
            request, 
            'ROUTE_DEACTIVATED', 
            object_ref=f'Route:{route.id}',
            details={
                'team_name': route.team.name,
                'shift_name': route.shift.name,
                'compound_names': compound_names
            }
        )
        
        messages.success(request, f'Route deactivated successfully.')
        return redirect('accounts:route_view', route_id=route.id)
    
    context = {'route': route, 'action': 'deactivate'}
    return render(request, 'accounts/route_confirm_delete.html', context)


@login_required
def route_activate(request, route_id):
    """Activate a route."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        messages.error(request, 'Route not found.')
        return redirect('accounts:route_list')
    
    # Check camp access for managers
    user_role = get_user_role(request)
    if user_role == 'manager' and hasattr(request.user, 'profile'):
        camp = request.user.profile.camp
        if camp and route.team.camp != camp:
            messages.error(request, 'You do not have permission to modify this route.')
            return redirect('accounts:route_list')
    
    if request.method == 'POST':
        route.is_active = True
        route.save()
        
        # Log audit event
        compound_names = ", ".join([c.name for c in route.compounds.all()])
        log_audit_event(
            request, 
            'ROUTE_ACTIVATED', 
            object_ref=f'Route:{route.id}',
            details={
                'team_name': route.team.name,
                'shift_name': route.shift.name,
                'compound_names': compound_names
            }
        )
        
        messages.success(request, f'Route activated successfully.')
        return redirect('accounts:route_view', route_id=route.id)
    
    context = {'route': route, 'action': 'activate'}
    return render(request, 'accounts/route_confirm_delete.html', context)


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


# Shift Management Views

@login_required
def shift_list(request):
    """List all shifts with filtering and search."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shifts = Shift.objects.select_related('camp').all()
    
    # Filter by camp for managers
    if request.user.profile.role == 'manager':
        camp = request.user.profile.camp
        if camp:
            shifts = shifts.filter(camp=camp)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        shifts = shifts.filter(
            Q(name__icontains=search_query) |
            Q(camp__name__icontains=search_query)
        )
    
    # Filter by active status
    active_filter = request.GET.get('active', '')
    if active_filter == 'true':
        shifts = shifts.filter(is_active=True)
    elif active_filter == 'false':
        shifts = shifts.filter(is_active=False)
    
    # Add duration calculation to each shift
    for shift in shifts:
        if shift.start_time and shift.end_time:
            if shift.end_time > shift.start_time:
                # Regular shift (same day)
                start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
                end_minutes = shift.end_time.hour * 60 + shift.end_time.minute
                duration_minutes = end_minutes - start_minutes
                duration_hours = duration_minutes / 60
                shift.duration_display = f"{duration_hours:.1f} hours"
            else:
                # Overnight shift
                shift.duration_display = "Overnight Shift"
        else:
            shift.duration_display = None
    
    # Pagination
    paginator = Paginator(shifts, 20)
    page_number = request.GET.get('page')
    shifts = paginator.get_page(page_number)
    
    # Statistics
    total_shifts = Shift.objects.count()
    active_shifts = Shift.objects.filter(is_active=True).count()
    
    context = {
        'shifts': shifts,
        'search_query': search_query,
        'active_filter': active_filter,
        'total_shifts': total_shifts,
        'active_shifts': active_shifts,
    }
    return render(request, 'accounts/shift_list.html', context)


@login_required
def shift_view(request, shift_id):
    """View detailed information about a specific shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shift = get_object_or_404(Shift, id=shift_id)
    
    # Check camp access for managers
    if request.user.profile.role == 'manager':
        camp = request.user.profile.camp
        if camp and shift.camp != camp:
            messages.error(request, 'You do not have permission to view this shift.')
            return redirect('accounts:shift_list')
    
    # Calculate duration for display
    if shift.start_time and shift.end_time:
        if shift.end_time > shift.start_time:
            # Regular shift (same day)
            start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
            end_minutes = shift.end_time.hour * 60 + shift.end_time.minute
            duration_minutes = end_minutes - start_minutes
            duration_hours = duration_minutes / 60
            shift.duration_display = f"{duration_hours:.1f} hours"
        else:
            # Overnight shift
            shift.duration_display = "Overnight Shift"
    else:
        shift.duration_display = None
    
    # Get routes using this shift
    routes = shift.routes.select_related('team').prefetch_related('compounds__camp').all()
    
    # Log audit event
    log_audit_event(
        request,
        'SHIFT_VIEWED',
        object_ref=f'shift:{shift.id}',
        details=f'Viewed shift: {shift.name}'
    )
    
    context = {
        'shift': shift,
        'routes': routes,
        'routes_count': routes.count(),
    }
    return render(request, 'accounts/shift_view.html', context)


@login_required
def shift_create(request):
    """Create a new shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = ShiftCreateForm(request.POST, request=request)
        if form.is_valid():
            shift = form.save()
            
            # Log audit event
            log_audit_event(
                request,
                'SHIFT_CREATED',
                object_ref=f'shift:{shift.id}',
                details=f'Created shift: {shift.name}'
            )
            
            messages.success(request, f'Shift "{shift.name}" created successfully.')
            return redirect('accounts:shift_view', shift_id=shift.id)
    else:
        form = ShiftCreateForm(request=request)
    
    context = {'form': form}
    return render(request, 'accounts/shift_form.html', context)


@login_required
def shift_update(request, shift_id):
    """Update an existing shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shift = get_object_or_404(Shift, id=shift_id)
    
    # Check camp access for managers
    if request.user.profile.role == 'manager':
        camp = request.user.profile.camp
        if camp and shift.camp != camp:
            messages.error(request, 'You do not have permission to edit this shift.')
            return redirect('accounts:shift_list')
    
    if request.method == 'POST':
        form = ShiftUpdateForm(request.POST, instance=shift, request=request)
        if form.is_valid():
            shift = form.save()
            
            # Log audit event
            log_audit_event(
                request,
                'SHIFT_UPDATED',
                object_ref=f'shift:{shift.id}',
                details=f'Updated shift: {shift.name}'
            )
            
            messages.success(request, f'Shift "{shift.name}" updated successfully.')
            return redirect('accounts:shift_view', shift_id=shift.id)
    else:
        form = ShiftUpdateForm(instance=shift, request=request)
    
    context = {'form': form, 'shift': shift}
    return render(request, 'accounts/shift_form.html', context)


@login_required
def shift_deactivate(request, shift_id):
    """Deactivate a shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shift = get_object_or_404(Shift, id=shift_id)
    
    # Check camp access for managers
    if request.user.profile.role == 'manager':
        camp = request.user.profile.camp
        if camp and shift.camp != camp:
            messages.error(request, 'You do not have permission to deactivate this shift.')
            return redirect('accounts:shift_list')
    
    if request.method == 'POST':
        shift.is_active = False
        shift.save()
        
        # Log audit event
        log_audit_event(
            request,
            'SHIFT_DEACTIVATED',
            object_ref=f'shift:{shift.id}',
            details=f'Deactivated shift: {shift.name}'
        )
        
        messages.success(request, f'Shift "{shift.name}" has been deactivated.')
        return redirect('accounts:shift_view', shift_id=shift.id)
    
    context = {'shift': shift}
    return render(request, 'accounts/shift_confirm_deactivate.html', context)


@login_required
def shift_activate(request, shift_id):
    """Activate a shift."""
    if not check_permission(request, ['admin', 'manager']):
        return redirect('accounts:login')
    
    shift = get_object_or_404(Shift, id=shift_id)
    
    # Check camp access for managers
    if request.user.profile.role == 'manager':
        camp = request.user.profile.camp
        if camp and shift.camp != camp:
            messages.error(request, 'You do not have permission to activate this shift.')
            return redirect('accounts:shift_list')
    
    if request.method == 'POST':
        shift.is_active = True
        shift.save()
        
        # Log audit event
        log_audit_event(
            request,
            'SHIFT_ACTIVATED',
            object_ref=f'shift:{shift.id}',
            details=f'Activated shift: {shift.name}'
        )
        
        messages.success(request, f'Shift "{shift.name}" has been activated.')
        return redirect('accounts:shift_view', shift_id=shift.id)
    
    context = {'shift': shift}
    return render(request, 'accounts/shift_confirm_activate.html', context)