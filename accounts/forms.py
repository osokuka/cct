"""
Account forms for the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from .models import UserProfile, Team, Shift, Route, RouteStreet, CompoundAssignment, PlanGenerationConfig
from locations.models import Camp, Compound, Building


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


class UserUpdateForm(forms.ModelForm):
    """Form for updating users with profile information."""
    
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=False)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select compounds for Authority users to supervise"
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Filter camps by user's access if not admin
        if self.request and hasattr(self.request.user, 'profile'):
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
        
        # Set initial values for all profile fields
        if self.instance.pk and not self.is_bound:
            try:
                profile = self.instance.profile
                # Set initial values for profile fields
                self.fields['role'].initial = profile.role
                self.fields['camp'].initial = profile.camp
                self.fields['is_team_leader'].initial = profile.is_team_leader
                self.fields['phone_number'].initial = profile.phone_number
                
                # Set initial compound assignments for Authority users
                if profile.role == 'authority':
                    compound_ids = CompoundAssignment.objects.filter(
                        user=self.instance, 
                        is_active=True
                    ).values_list('compound_id', flat=True)
                    self.fields['compounds'].initial = compound_ids
            except UserProfile.DoesNotExist:
                pass
        
        # Add camp ID to compound choices for JavaScript filtering
        if 'compounds' in self.fields:
            self.fields['compounds'].queryset = self.fields['compounds'].queryset.select_related('camp')
            
        # Ensure compounds are filtered by the user's camp if not admin
        if self.request and hasattr(self.request.user, 'profile'):
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['compounds'].queryset = self.fields['compounds'].queryset.filter(camp=camp)
    
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
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            profile.role = self.cleaned_data['role']
            profile.camp = self.cleaned_data['camp']
            profile.is_team_leader = self.cleaned_data['is_team_leader']
            profile.phone_number = self.cleaned_data['phone_number']
            profile.save()
            
            # Handle compound assignments for authority users
            if self.cleaned_data['role'] == 'authority':
                # Remove existing assignments first
                CompoundAssignment.objects.filter(user=user).delete()
                
                # Add new assignments
                compounds = self.cleaned_data.get('compounds', [])
                for compound in compounds:
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
    """Create a team: leader, headcount, vehicle and equipment.

    Shifts are simplified to a single standard 08:00-17:00 shift and assigned
    automatically, so they are not part of this form.
    """

    class Meta:
        model = Team
        fields = ['name', 'camp', 'team_type', 'team_leader',
                  'employee_count', 'vehicle', 'equipment', 'is_active']
        widgets = {
            'equipment': forms.Textarea(attrs={'rows': 3,
                'placeholder': 'e.g. 2× bins lift, brooms, high-vis vests, pressure washer'}),
            'vehicle': forms.TextInput(attrs={'placeholder': 'e.g. Garbage Truck GJ-123-AB'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        self.fields['team_leader'].queryset = User.objects.filter(
            profile__role__in=['admin', 'manager', 'cleaner'],
            profile__is_active=True,
        )
        # Non-admins can only create teams in their own site.
        if self.request and hasattr(self.request.user, 'profile') \
                and self.request.user.profile.role != 'admin':
            camp = self.request.user.profile.camp
            if camp:
                self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
                self.fields['camp'].initial = camp


class TeamUpdateForm(TeamCreateForm):
    """Same builder, used for editing an existing team."""
    pass


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
    """Build a team's daily route: Team + weekday + ordered streets."""

    streets = forms.ModelMultipleChoiceField(
        queryset=Building.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 14, "class": "route-streets"}),
        help_text="Streets serviced on this route (order = selection order)",
    )

    class Meta:
        model = Route
        fields = ['team', 'weekday', 'priority', 'is_active']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        team_qs = Team.objects.filter(is_active=True)
        street_qs = Building.objects.select_related('compound').all()
        if self.request and hasattr(self.request.user, 'profile'):
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    team_qs = team_qs.filter(camp=camp)
                    street_qs = street_qs.filter(compound__camp=camp)
        self.fields['team'].queryset = team_qs
        self.fields['streets'].queryset = street_qs.order_by('compound__name', 'name')

        if self.instance and self.instance.pk:
            self.fields['streets'].initial = self.instance.streets.all()

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get('team')
        weekday = cleaned.get('weekday')
        if team is not None and weekday is not None:
            qs = Route.objects.filter(team=team, weekday=weekday)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "This team already has a route for that weekday. Edit the existing one instead."
                )
        return cleaned

    def save(self, commit=True):
        route = super().save(commit=commit)
        if commit:
            self._save_streets(route)
        return route

    def _save_streets(self, route):
        buildings = list(self.cleaned_data.get('streets') or [])
        RouteStreet.objects.filter(route=route).delete()
        for i, b in enumerate(buildings):
            RouteStreet.objects.create(route=route, building=b, order=i)
        route.compounds.set({b.compound_id for b in buildings})


class RouteUpdateForm(RouteCreateForm):
    """Same builder, used for editing an existing route."""
    pass


class PlanGenerationConfigForm(forms.ModelForm):
    """Management setting for automatic route-task generation cadence."""

    class Meta:
        model = PlanGenerationConfig
        fields = ['cadence', 'anchor_date', 'is_active']
        widgets = {
            'anchor_date': forms.DateInput(attrs={'type': 'date'}),
        }


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
