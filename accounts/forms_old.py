"""
Forms for user management in the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from .models import UserProfile, Team, Shift, Route, CompoundAssignment
from locations.models import Camp, Compound


class UserCreateForm(UserCreationForm):
    """Form for creating new users with profile information and compound assignment."""
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('supervisor', 'Supervisor'),
        ('cleaner', 'Cleaner'),
        ('authority', 'Authority'),
    ]
    
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=False)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select compounds for Authority users (only applies to Authority role)"
    )
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        print(f"DEBUG FORM INIT: Request user: {self.request.user if self.request else None}")
        
        # Only Admin can create users
        if self.request and not self.request.user.is_superuser:
            if hasattr(self.request.user, 'profile'):
                if self.request.user.profile.role != 'admin':
                    raise PermissionError("Only Admin users can create new users")
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Only Admin can create users
        if self.request and not self.request.user.is_superuser:
            if hasattr(self.request.user, 'profile'):
                if self.request.user.profile.role != 'admin':
                    raise PermissionError("Only Admin users can create new users")
    
    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        compounds = cleaned_data.get('compounds')
        
        # Authority users must have at least one compound assignment
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
        
        # Non-authority users should not have compound assignments
        if role != 'authority' and compounds:
            cleaned_data['compounds'] = []
            
        return cleaned_data
    
    def save(self, commit=True):
        print(f"DEBUG FORM SAVE: Starting save with commit={commit}")
        print(f"DEBUG FORM SAVE: cleaned_data: {self.cleaned_data}")
        
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        print(f"DEBUG FORM SAVE: User object created: {user.username}")
        
        if commit:
            try:
                user.save()
                print(f"DEBUG FORM SAVE: User saved to database with ID: {user.id}")
                
                # Create user profile
                profile = UserProfile.objects.create(
                    user=user,
                    role=self.cleaned_data['role'],
                    camp=self.cleaned_data.get('camp'),
                    is_team_leader=self.cleaned_data.get('is_team_leader', False),
                    phone_number=self.cleaned_data.get('phone_number', ''),
                    is_active=True
                )
                print(f"DEBUG FORM SAVE: Profile created: {profile}")
                
                # Create compound assignments for Authority users
                if self.cleaned_data['role'] == 'authority' and self.cleaned_data.get('compounds'):
                    print(f"DEBUG FORM SAVE: Creating compound assignments for Authority user")
                    for compound in self.cleaned_data['compounds']:
                        assignment = CompoundAssignment.objects.create(
                            user=user,
                            compound=compound,
                            assigned_by=self.request.user if self.request else None
                        )
                        print(f"DEBUG FORM SAVE: Created assignment: {assignment}")
            except Exception as e:
                print(f"DEBUG FORM SAVE: Error during save: {str(e)}")
                raise e
        return user


class UserUpdateForm(forms.ModelForm):
    """Form for updating user information with compound assignment."""
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('supervisor', 'Supervisor'),
        ('cleaner', 'Cleaner'),
        ('authority', 'Authority'),
    ]
    
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=False)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    is_active = forms.BooleanField(required=False)
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select compounds for Authority users (only applies to Authority role)"
    )
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            try:
                profile = self.instance.profile
                self.fields['role'].initial = profile.role
                self.fields['camp'].initial = profile.camp
                self.fields['is_team_leader'].initial = profile.is_team_leader
                self.fields['phone_number'].initial = profile.phone_number
                self.fields['is_active'].initial = profile.is_active
                
                # Set initial compound assignments for Authority users
                if profile.role == 'authority':
                    self.fields['compounds'].initial = CompoundAssignment.objects.filter(
                        user=self.instance, 
                        is_active=True
                    ).values_list('compound_id', flat=True)
            except UserProfile.DoesNotExist:
                pass
    
    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        compounds = cleaned_data.get('compounds')
        
        # Authority users must have at least one compound assignment
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
        
        # Non-authority users should not have compound assignments
        if role != 'authority' and compounds:
            cleaned_data['compounds'] = []
            
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.camp = self.cleaned_data.get('camp')
            profile.is_team_leader = self.cleaned_data.get('is_team_leader', False)
            profile.phone_number = self.cleaned_data.get('phone_number', '')
            profile.is_active = self.cleaned_data.get('is_active', True)
            profile.save()
            
            # Update compound assignments for Authority users
            if self.cleaned_data['role'] == 'authority':
                # Remove existing assignments
                CompoundAssignment.objects.filter(user=user).delete()
                
                # Create new assignments
                if self.cleaned_data.get('compounds'):
                    for compound in self.cleaned_data['compounds']:
                        CompoundAssignment.objects.create(
                            user=user,
                            compound=compound,
                            assigned_by=self.request.user if self.request else None
                        )
            else:
                # Remove all compound assignments for non-authority users
                CompoundAssignment.objects.filter(user=user).delete()
        return user


class TeamCreateForm(forms.ModelForm):
    """Form for creating teams."""
    
    class Meta:
        model = Team
        fields = ['name', 'camp', 'shift', 'team_leader', 'members', 'is_active']
        widgets = {
            'members': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Filter team leaders to only managers and admins
        if self.request:
            self.fields['team_leader'].queryset = User.objects.filter(
                profile__role__in=['admin', 'manager', 'cleaner'],
                profile__is_active=True
            )
            
            # Filter members to only cleaners who are not already assigned to any team
            self.fields['members'].queryset = User.objects.filter(
                profile__role='cleaner',
                profile__is_active=True
            ).exclude(teams__is_active=True)
            
            # Filter shifts by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['shift'].queryset = Shift.objects.filter(camp=camp, is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        camp = cleaned_data.get('camp')
        shift = cleaned_data.get('shift')
        
        # Validate shift belongs to the selected camp
        if camp and shift and shift.camp != camp:
            raise forms.ValidationError(
                f"Shift '{shift.name}' does not belong to camp '{camp.name}'"
            )
        
        return cleaned_data


class TeamUpdateForm(forms.ModelForm):
    """Form for updating teams."""
    
    class Meta:
        model = Team
        fields = ['name', 'camp', 'shift', 'team_leader', 'members', 'is_active']
        widgets = {
            'members': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Filter team leaders to only managers and admins
        self.fields['team_leader'].queryset = User.objects.filter(
            profile__role__in=['admin', 'manager', 'cleaner'],
            profile__is_active=True
        )
        
        # Filter shifts by user's camp if not admin
        if self.request and self.request.user.profile.role != 'admin':
            camp = self.request.user.profile.camp
            if camp:
                self.fields['shift'].queryset = Shift.objects.filter(camp=camp, is_active=True)
        
        # Filter members to only cleaners who are not already assigned to any team
        # But include current team members so they can be removed if needed
        current_team_members = []
        if self.instance and self.instance.pk:
            current_team_members = list(self.instance.members.values_list('id', flat=True))
        
        self.fields['members'].queryset = User.objects.filter(
            profile__role='cleaner',
            profile__is_active=True
        ).filter(
            models.Q(teams__isnull=True) |  # No teams assigned
            models.Q(teams__is_active=False) |  # Only inactive teams
            models.Q(id__in=current_team_members)  # Current team members
        ).distinct()
    
    def clean(self):
        cleaned_data = super().clean()
        camp = cleaned_data.get('camp')
        shift = cleaned_data.get('shift')
        
        # Validate shift belongs to the selected camp
        if camp and shift and shift.camp != camp:
            raise forms.ValidationError(
                f"Shift '{shift.name}' does not belong to camp '{camp.name}'"
            )
        
        return cleaned_data


class ShiftCreateForm(forms.ModelForm):
    """Form for creating shifts."""
    
    class Meta:
        model = Shift
        fields = ['name', 'camp', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
                    self.fields['camp'].initial = camp


class ShiftUpdateForm(forms.ModelForm):
    """Form for updating shifts."""
    
    class Meta:
        model = Shift
        fields = ['name', 'camp', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)


class RouteCreateForm(forms.ModelForm):
    """Form for creating routes with conflict checking."""
    
    class Meta:
        model = Route
        fields = ['team', 'compounds', 'priority', 'is_active']
        widgets = {
            'compounds': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['team'].queryset = Team.objects.filter(camp=camp, is_active=True)
                    self.fields['shift'].queryset = Shift.objects.filter(camp=camp, is_active=True)
                    self.fields['compounds'].queryset = Compound.objects.filter(camp=camp, is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        shift = cleaned_data.get('shift')
        compounds = cleaned_data.get('compounds')
        
        if team and shift and compounds:
            from .route_utils import check_route_conflicts
            
            # Check for conflicts
            conflict_result = check_route_conflicts(team, shift, compounds)
            
            if conflict_result['has_conflicts']:
                conflict_messages = []
                for conflict in conflict_result['conflicts']:
                    conflict_messages.append(
                        f"Team '{conflict['conflicting_team']}' is already assigned to "
                        f"{conflict['compound']} during {conflict['shift']} shift."
                    )
                
                # Add suggestions
                if conflict_result['suggestions']:
                    conflict_messages.append("\nSuggestions:")
                    conflict_messages.extend(conflict_result['suggestions'])
                
                raise forms.ValidationError('\n'.join(conflict_messages))
        
        return cleaned_data


class RouteUpdateForm(forms.ModelForm):
    """Form for updating routes with conflict checking."""
    
    class Meta:
        model = Route
        fields = ['team', 'shift', 'compounds', 'priority', 'is_active']
        widgets = {
            'compounds': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['team'].queryset = Team.objects.filter(camp=camp, is_active=True)
                    self.fields['shift'].queryset = Shift.objects.filter(camp=camp, is_active=True)
                    self.fields['compounds'].queryset = Compound.objects.filter(camp=camp, is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        shift = cleaned_data.get('shift')
        compounds = cleaned_data.get('compounds')
        
        if team and shift and compounds:
            from .route_utils import check_route_conflicts
            
            # Check for conflicts, excluding current route
            conflict_result = check_route_conflicts(team, shift, compounds, exclude_route=self.instance)
            
            if conflict_result['has_conflicts']:
                conflict_messages = []
                for conflict in conflict_result['conflicts']:
                    conflict_messages.append(
                        f"Team '{conflict['conflicting_team']}' is already assigned to "
                        f"{conflict['compound']} during {conflict['shift']} shift."
                    )
                
                # Add suggestions
                if conflict_result['suggestions']:
                    conflict_messages.append("\nSuggestions:")
                    conflict_messages.extend(conflict_result['suggestions'])
                
                raise forms.ValidationError('\n'.join(conflict_messages))
        
        return cleaned_data


class CompoundAssignmentForm(forms.ModelForm):
    """Form for assigning compounds to authority users."""
    
    class Meta:
        model = CompoundAssignment
        fields = ['user', 'compound', 'is_active']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Only show authority users
        self.fields['user'].queryset = User.objects.filter(
            profile__role='authority',
            profile__is_active=True
        )
        
        # Only show active compounds
        self.fields['compound'].queryset = Compound.objects.filter(is_active=True)