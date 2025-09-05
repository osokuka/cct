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
    ShiftCreateForm, RouteCreateForm, CompoundAssignmentForm
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