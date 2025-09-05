"""
Forms for user management in the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
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