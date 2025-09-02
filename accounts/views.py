"""
Authentication and user management views for the NATO Camp Cleaning Tracker.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView

from cct.mixins import AdminRequiredMixin, ScopedQuerysetMixin
from cct.utils import get_user_scope
from .models import UserProfile, CompoundAssignment
from .forms import UserProfileForm, CompoundAssignmentForm, UserCreationFormWithProfile
from locations.models import Compound


class CustomLoginView(LoginView):
    """Custom login view with NATO styling."""
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        """Redirect based on user role."""
        user = self.request.user
        try:
            profile = user.profile
            if profile.role == 'admin':
                return reverse_lazy('dashboard:dashboard')
            elif profile.role == 'supervisor':
                return reverse_lazy('dashboard:dashboard')
            elif profile.role == 'authority':
                return reverse_lazy('authority:dashboard')
            elif profile.role == 'cleaner':
                return reverse_lazy('scans:dashboard')
        except UserProfile.DoesNotExist:
            pass
        
        return reverse_lazy('dashboard:dashboard')
    
    def form_valid(self, form):
        """Add success message and audit logging."""
        response = super().form_valid(form)
        messages.success(self.request, f'Welcome back, {self.request.user.get_full_name()}!')
        
        # Set audit reference for login
        self.request.audit_ref = f"User {self.request.user.username} logged in"
        
        return response


class CustomLogoutView(LogoutView):
    """Custom logout view."""
    next_page = 'accounts:login'
    
    def dispatch(self, request, *args, **kwargs):
        # Set audit reference for logout
        if request.user.is_authenticated:
            request.audit_ref = f"User {request.user.username} logged out"
        return super().dispatch(request, *args, **kwargs)


class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view."""
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


@method_decorator(login_required, name='dispatch')
class UserListView(AdminRequiredMixin, ScopedQuerysetMixin, ListView):
    """List all users with role-based filtering."""
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 20
    
    def get_queryset(self):
        """Filter users based on search and role."""
        queryset = super().get_queryset().select_related('profile').prefetch_related('compound_assignments__compound')
        
        # Search functionality
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        
        # Role filtering
        role = self.request.GET.get('role', '')
        if role:
            queryset = queryset.filter(profile__role=role)
        
        # Status filtering
        status = self.request.GET.get('status', '')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        return queryset.order_by('-date_joined')
    
    def get_context_data(self, **kwargs):
        """Add context data for filtering and pagination."""
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['role'] = self.request.GET.get('role', '')
        context['status'] = self.request.GET.get('status', '')
        context['role_choices'] = UserProfile.ROLE_CHOICES
        context['user_scope'] = get_user_scope(self.request)
        return context


@method_decorator(login_required, name='dispatch')
class UserCreateView(AdminRequiredMixin, CreateView):
    """Create new user with profile."""
    model = User
    form_class = UserCreationFormWithProfile
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def form_valid(self, form):
        """Create user profile and compound assignments."""
        response = super().form_valid(form)
        
        # Create user profile
        profile = UserProfile.objects.create(
            user=self.object,
            role=form.cleaned_data['role'],
            phone_number=form.cleaned_data.get('phone_number', ''),
            employee_id=form.cleaned_data.get('employee_id', ''),
        )
        
        # Create compound assignments
        compounds = form.cleaned_data.get('compounds', [])
        for compound in compounds:
            CompoundAssignment.objects.create(
                user=self.object,
                compound=compound,
                created_by=self.request.user
            )
        
        messages.success(self.request, f'User {self.object.username} created successfully.')
        self.request.audit_ref = f"Created user {self.object.username} with role {profile.role}"
        
        return response
    
    def get_context_data(self, **kwargs):
        """Add context data for form."""
        context = super().get_context_data(**kwargs)
        context['compounds'] = Compound.objects.all()
        context['user_scope'] = get_user_scope(self.request)
        return context


@method_decorator(login_required, name='dispatch')
class UserUpdateView(AdminRequiredMixin, UpdateView):
    """Update user and profile."""
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def get_object(self):
        """Get user object."""
        return get_object_or_404(User, pk=self.kwargs['pk'])
    
    def get_form_kwargs(self):
        """Pass user instance to form."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.get_object()
        return kwargs
    
    def form_valid(self, form):
        """Update user profile and compound assignments."""
        response = super().form_valid(form)
        
        # Update user profile
        profile, created = UserProfile.objects.get_or_create(user=self.object)
        profile.role = form.cleaned_data['role']
        profile.phone_number = form.cleaned_data.get('phone_number', '')
        profile.employee_id = form.cleaned_data.get('employee_id', '')
        profile.is_active = form.cleaned_data.get('is_active', True)
        profile.save()
        
        # Update compound assignments
        compounds = form.cleaned_data.get('compounds', [])
        # Remove existing assignments
        CompoundAssignment.objects.filter(user=self.object).delete()
        # Create new assignments
        for compound in compounds:
            CompoundAssignment.objects.create(
                user=self.object,
                compound=compound,
                created_by=self.request.user
            )
        
        messages.success(self.request, f'User {self.object.username} updated successfully.')
        self.request.audit_ref = f"Updated user {self.object.username}"
        
        return response
    
    def get_context_data(self, **kwargs):
        """Add context data for form."""
        context = super().get_context_data(**kwargs)
        context['compounds'] = Compound.objects.all()
        context['user_scope'] = get_user_scope(self.request)
        
        # Get current compound assignments
        current_assignments = list(
            CompoundAssignment.objects
            .filter(user=self.object)
            .values_list('compound_id', flat=True)
        )
        context['current_compounds'] = current_assignments
        
        return context


@method_decorator(login_required, name='dispatch')
class UserDeleteView(AdminRequiredMixin, DeleteView):
    """Delete user (deactivate instead of delete)."""
    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('accounts:user_list')
    
    def delete(self, request, *args, **kwargs):
        """Deactivate user instead of deleting."""
        self.object = self.get_object()
        self.object.is_active = False
        self.object.save()
        
        messages.success(request, f'User {self.object.username} has been deactivated.')
        request.audit_ref = f"Deactivated user {self.object.username}"
        
        return redirect(self.success_url)


@login_required
def user_detail(request, pk):
    """User detail view."""
    user = get_object_or_404(User, pk=pk)
    profile = getattr(user, 'profile', None)
    compound_assignments = CompoundAssignment.objects.filter(user=user).select_related('compound')
    
    context = {
        'user_obj': user,
        'profile': profile,
        'compound_assignments': compound_assignments,
        'user_scope': get_user_scope(request),
    }
    
    return render(request, 'accounts/user_detail.html', context)


@login_required
@require_http_methods(["POST"])
def toggle_user_status(request, pk):
    """Toggle user active status."""
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save()
    
    status = "activated" if user.is_active else "deactivated"
    messages.success(request, f'User {user.username} has been {status}.')
    request.audit_ref = f"{status.title()} user {user.username}"
    
    return JsonResponse({
        'success': True,
        'is_active': user.is_active,
        'message': f'User {status} successfully.'
    })


@login_required
@require_http_methods(["POST"])
def reset_user_password(request, pk):
    """Reset user password."""
    user = get_object_or_404(User, pk=pk)
    new_password = User.objects.make_random_password()
    user.set_password(new_password)
    user.save()
    
    messages.success(request, f'Password reset for {user.username}. New password: {new_password}')
    request.audit_ref = f"Reset password for user {user.username}"
    
    return JsonResponse({
        'success': True,
        'new_password': new_password,
        'message': 'Password reset successfully.'
    })