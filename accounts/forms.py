"""
Forms for user management in the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, CompoundAssignment
from locations.models import Compound


class UserCreationFormWithProfile(UserCreationForm):
    """User creation form with profile fields."""
    
    # Profile fields
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'})
    )
    employee_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employee ID'})
    )
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text="Select compounds for Authority users"
    )
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add CSS classes to password fields
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
    
    def clean_email(self):
        """Validate email uniqueness."""
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
    
    def clean_compounds(self):
        """Validate compound assignments."""
        compounds = self.cleaned_data.get('compounds')
        role = self.cleaned_data.get('role')
        
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
        
        return compounds


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile."""
    
    # User fields
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # Profile fields
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    employee_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text="Select compounds for Authority users"
    )
    
    class Meta:
        model = UserProfile
        fields = ('role', 'phone_number', 'employee_id')
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Populate user fields
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email
            self.fields['is_active'].initial = self.user.is_active
            
            # Populate profile fields - handle case where profile doesn't exist
            try:
                profile = self.user.profile
                self.fields['role'].initial = profile.role
                self.fields['phone_number'].initial = profile.phone_number
                self.fields['employee_id'].initial = profile.employee_id
            except UserProfile.DoesNotExist:
                # Set default values if no profile exists
                self.fields['role'].initial = 'cleaner'
                self.fields['phone_number'].initial = ''
                self.fields['employee_id'].initial = ''
            
            # Populate compound assignments
            compound_ids = list(
                CompoundAssignment.objects
                .filter(user=self.user)
                .values_list('compound_id', flat=True)
            )
            self.fields['compounds'].initial = compound_ids
    
    def clean_email(self):
        """Validate email uniqueness."""
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
    
    def clean_compounds(self):
        """Validate compound assignments."""
        compounds = self.cleaned_data.get('compounds')
        role = self.cleaned_data.get('role')
        
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
        
        return compounds
    
    def save(self, commit=True):
        """Save user and profile data."""
        # Update user fields
        self.user.first_name = self.cleaned_data['first_name']
        self.user.last_name = self.cleaned_data['last_name']
        self.user.email = self.cleaned_data['email']
        self.user.is_active = self.cleaned_data['is_active']
        
        if commit:
            self.user.save()
        
        # Update profile
        profile = super().save(commit=False)
        profile.user = self.user
        if commit:
            profile.save()
        
        return profile


class CompoundAssignmentForm(forms.ModelForm):
    """Form for managing compound assignments."""
    
    class Meta:
        model = CompoundAssignment
        fields = ('compound',)
        widgets = {
            'compound': forms.Select(attrs={'class': 'form-control'})
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Filter compounds based on user role
            from accounts.models import get_user_role
            role = get_user_role(self.user)
            
            if role == 'authority':
                # Authority users can only be assigned to compounds they don't already have
                existing_compound_ids = list(
                    CompoundAssignment.objects
                    .filter(user=self.user)
                    .values_list('compound_id', flat=True)
                )
                self.fields['compound'].queryset = Compound.objects.exclude(
                    id__in=existing_compound_ids
                )
            else:
                # Other roles can be assigned to any compound
                self.fields['compound'].queryset = Compound.objects.all()


class UserSearchForm(forms.Form):
    """Form for searching users."""
    
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by username, name, or email...'
        })
    )
    role = forms.ChoiceField(
        choices=[('', 'All Roles')] + list(UserProfile.ROLE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        choices=[
            ('', 'All Status'),
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
