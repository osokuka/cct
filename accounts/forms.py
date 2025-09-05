"""
Forms for user management in the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Team, Shift, Route, CompoundAssignment
from locations.models import Camp, Compound


class UserCreateForm(UserCreationForm):
    """Form for creating new users with profile information."""
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
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
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # If user is not admin, limit role choices
        if self.request and not self.request.user.is_superuser:
            if hasattr(self.request.user, 'profile'):
                if self.request.user.profile.role == 'manager':
                    self.fields['role'].choices = [
                        ('cleaner', 'Cleaner'),
                        ('authority', 'Authority'),
                    ]
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                camp=self.cleaned_data.get('camp'),
                is_team_leader=self.cleaned_data.get('is_team_leader', False),
                phone_number=self.cleaned_data.get('phone_number', ''),
                is_active=True
            )
        return user


class UserUpdateForm(forms.ModelForm):
    """Form for updating user information."""
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('cleaner', 'Cleaner'),
        ('authority', 'Authority'),
    ]
    
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=False)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    is_active = forms.BooleanField(required=False)
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            try:
                profile = self.instance.profile
                self.fields['role'].initial = profile.role
                self.fields['camp'].initial = profile.camp
                self.fields['is_team_leader'].initial = profile.is_team_leader
                self.fields['phone_number'].initial = profile.phone_number
                self.fields['is_active'].initial = profile.is_active
            except UserProfile.DoesNotExist:
                pass
    
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
        return user


class TeamCreateForm(forms.ModelForm):
    """Form for creating teams."""
    
    class Meta:
        model = Team
        fields = ['name', 'camp', 'team_leader', 'members', 'is_active']
        widgets = {
            'members': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Filter team leaders to only managers and admins
        if self.request:
            self.fields['team_leader'].queryset = User.objects.filter(
                profile__role__in=['admin', 'manager'],
                profile__is_active=True
            )
            
            # Filter members to only cleaners
            self.fields['members'].queryset = User.objects.filter(
                profile__role='cleaner',
                profile__is_active=True
            )


class TeamUpdateForm(forms.ModelForm):
    """Form for updating teams."""
    
    class Meta:
        model = Team
        fields = ['name', 'camp', 'team_leader', 'members', 'is_active']
        widgets = {
            'members': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter team leaders to only managers and admins
        self.fields['team_leader'].queryset = User.objects.filter(
            profile__role__in=['admin', 'manager'],
            profile__is_active=True
        )
        
        # Filter members to only cleaners
        self.fields['members'].queryset = User.objects.filter(
            profile__role='cleaner',
            profile__is_active=True
        )


class ShiftCreateForm(forms.ModelForm):
    """Form for creating shifts."""
    
    class Meta:
        model = Shift
        fields = ['name', 'camp', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class RouteCreateForm(forms.ModelForm):
    """Form for creating routes."""
    
    class Meta:
        model = Route
        fields = ['team', 'shift', 'compound', 'priority', 'is_active']
    
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
                    self.fields['compound'].queryset = Compound.objects.filter(camp=camp, is_active=True)


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