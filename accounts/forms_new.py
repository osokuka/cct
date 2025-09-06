"""
Account forms for the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from .models import UserProfile, Team, Shift, Route, CompoundAssignment
from locations.models import Camp, Compound


class UserCreateForm(UserCreationForm):
    """Form for creating users with profile information."""
    
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=False)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Filter camps by user's access if not admin
        if self.request and hasattr(self.request.user, 'profile'):
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
    
    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                camp=self.cleaned_data['camp'],
                is_team_leader=self.cleaned_data['is_team_leader'],
                phone_number=self.cleaned_data['phone_number']
            )
            
            # Handle compound assignments for authority users
            if self.cleaned_data['role'] == 'authority' and self.cleaned_data.get('compounds'):
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
                    self.fields['compounds'].queryset = Compound.objects.filter(camp=camp, is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        compounds = cleaned_data.get('compounds')
        
        if team and compounds:
            from .route_utils import check_route_conflicts
            
            # Check for conflicts (no shift parameter needed)
            conflict_result = check_route_conflicts(team, None, compounds)
            
            if conflict_result['has_conflicts']:
                conflict_messages = []
                for conflict in conflict_result['conflicts']:
                    conflict_messages.append(
                        f"Team '{conflict['conflicting_team']}' is already assigned to "
                        f"{conflict['compound']}."
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
                    self.fields['compounds'].queryset = Compound.objects.filter(camp=camp, is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        compounds = cleaned_data.get('compounds')
        
        if team and compounds:
            from .route_utils import check_route_conflicts
            
            # Check for conflicts, excluding current route
            conflict_result = check_route_conflicts(team, None, compounds, exclude_route=self.instance)
            
            if conflict_result['has_conflicts']:
                conflict_messages = []
                for conflict in conflict_result['conflicts']:
                    conflict_messages.append(
                        f"Team '{conflict['conflicting_team']}' is already assigned to "
                        f"{conflict['compound']}."
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
        fields = ['compound']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['compound'].queryset = Compound.objects.filter(camp=camp, is_active=True)
