"""
Forms for location management in the NATO Camp Cleaning Tracker.
"""

from django import forms
from django.db.models import Q
from decimal import Decimal
from .models import Camp, Compound, Building, Floor, Room


class CampCreateForm(forms.ModelForm):
    """Form for creating camps."""
    
    class Meta:
        model = Camp
        fields = [
            'code', 'name', 'timezone', 'week_cutoff_day', 'week_cutoff_hour',
            'month_cutoff_day', 'month_cutoff_hour', 'skip_holidays', 'is_active'
        ]
        widgets = {
            'week_cutoff_hour': forms.TimeInput(attrs={'type': 'time'}),
            'month_cutoff_hour': forms.TimeInput(attrs={'type': 'time'}),
        }


class CampEditForm(forms.ModelForm):
    """Form for editing camps."""
    
    class Meta:
        model = Camp
        fields = [
            'code', 'name', 'timezone', 'week_cutoff_day', 'week_cutoff_hour',
            'month_cutoff_day', 'month_cutoff_hour', 'skip_holidays', 'is_active'
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'}),
            'name': forms.TextInput(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'}),
            'timezone': forms.TextInput(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'}),
            'week_cutoff_day': forms.HiddenInput(),
            'week_cutoff_hour': forms.HiddenInput(),
            'month_cutoff_day': forms.HiddenInput(),
            'month_cutoff_hour': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add custom fields to the form
        self.fields['week_cutoff_day_choice'] = forms.ChoiceField(
            choices=[
                (0, 'Monday'),
                (1, 'Tuesday'),
                (2, 'Wednesday'),
                (3, 'Thursday'),
                (4, 'Friday'),
                (5, 'Saturday'),
                (6, 'Sunday'),
            ],
            widget=forms.Select(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'})
        )
        
        self.fields['week_cutoff_hour_choice'] = forms.ChoiceField(
            choices=[(i, f"{i:02d}:00") for i in range(24)],
            widget=forms.Select(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'})
        )
        
        self.fields['month_cutoff_type'] = forms.ChoiceField(
            choices=[
                ('eom', 'End of Month (EoM)'),
                ('specific', 'Specific Date'),
            ],
            widget=forms.RadioSelect(attrs={'class': 'mr-2'})
        )
        
        self.fields['month_cutoff_day_choice'] = forms.ChoiceField(
            choices=[(i, f"Day {i}") for i in range(1, 32)],
            required=False,
            widget=forms.Select(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'})
        )
        
        self.fields['month_cutoff_hour_choice'] = forms.ChoiceField(
            choices=[(i, f"{i:02d}:00") for i in range(24)],
            widget=forms.Select(attrs={'class': 'w-full border border-industrial-gray rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel-blue'})
        )
        
        if self.instance and self.instance.pk:
            # Set initial values for custom fields
            self.fields['week_cutoff_day_choice'].initial = self.instance.week_cutoff_day
            self.fields['week_cutoff_hour_choice'].initial = self.instance.week_cutoff_hour
            self.fields['month_cutoff_hour_choice'].initial = self.instance.month_cutoff_hour
            
            # Set month cutoff type based on current value
            if self.instance.month_cutoff_day == 0:  # 0 means EoM
                self.fields['month_cutoff_type'].initial = 'eom'
            else:
                self.fields['month_cutoff_type'].initial = 'specific'
                self.fields['month_cutoff_day_choice'].initial = self.instance.month_cutoff_day
    
    def full_clean(self):
        """Override full_clean to populate hidden fields before validation."""
        # Get the raw data first
        if hasattr(self, 'data'):
            # Populate hidden fields from custom fields before validation
            week_day_choice = self.data.get('week_cutoff_day_choice')
            if week_day_choice is not None:
                self.data = self.data.copy()
                self.data['week_cutoff_day'] = int(week_day_choice)
            
            week_hour_choice = self.data.get('week_cutoff_hour_choice')
            if week_hour_choice is not None:
                self.data = self.data.copy()
                self.data['week_cutoff_hour'] = int(week_hour_choice)
            
            month_cutoff_type = self.data.get('month_cutoff_type')
            if month_cutoff_type == 'eom':
                self.data = self.data.copy()
                self.data['month_cutoff_day'] = 0  # 0 represents End of Month
            else:
                month_day_choice = self.data.get('month_cutoff_day_choice')
                if month_day_choice is not None and month_day_choice != '':
                    self.data = self.data.copy()
                    self.data['month_cutoff_day'] = int(month_day_choice)
                else:
                    # If no specific day is selected, default to 31
                    self.data = self.data.copy()
                    self.data['month_cutoff_day'] = 31
            
            month_hour_choice = self.data.get('month_cutoff_hour_choice')
            if month_hour_choice is not None:
                self.data = self.data.copy()
                self.data['month_cutoff_hour'] = int(month_hour_choice)
        
        # Now call the parent full_clean
        super().full_clean()
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Handle week cutoff
        week_day_choice = cleaned_data.get('week_cutoff_day_choice')
        if week_day_choice is not None:
            cleaned_data['week_cutoff_day'] = int(week_day_choice)
        
        week_hour_choice = cleaned_data.get('week_cutoff_hour_choice')
        if week_hour_choice is not None:
            cleaned_data['week_cutoff_hour'] = int(week_hour_choice)
        
        # Handle month cutoff
        month_cutoff_type = cleaned_data.get('month_cutoff_type')
        if month_cutoff_type == 'eom':
            cleaned_data['month_cutoff_day'] = 0  # 0 means End of Month
        else:
            month_day_choice = cleaned_data.get('month_cutoff_day_choice')
            if month_day_choice is not None and month_day_choice != '':
                cleaned_data['month_cutoff_day'] = int(month_day_choice)
            else:
                # If no specific day is selected, default to 31
                cleaned_data['month_cutoff_day'] = 31
        
        month_hour_choice = cleaned_data.get('month_cutoff_hour_choice')
        if month_hour_choice is not None:
            cleaned_data['month_cutoff_hour'] = int(month_hour_choice)
        
        return cleaned_data
    
    def save(self, commit=True):
        """Override save to ensure hidden fields are populated."""
        instance = super().save(commit=False)
        
        # Ensure the hidden fields are populated from cleaned_data
        if 'week_cutoff_day' in self.cleaned_data:
            instance.week_cutoff_day = self.cleaned_data['week_cutoff_day']
        if 'week_cutoff_hour' in self.cleaned_data:
            instance.week_cutoff_hour = self.cleaned_data['week_cutoff_hour']
        if 'month_cutoff_day' in self.cleaned_data:
            instance.month_cutoff_day = self.cleaned_data['month_cutoff_day']
        if 'month_cutoff_hour' in self.cleaned_data:
            instance.month_cutoff_hour = self.cleaned_data['month_cutoff_hour']
        
        if commit:
            instance.save()
        return instance


class CompoundEditForm(forms.ModelForm):
    """Form for editing compound details with project definition styling."""
    
    class Meta:
        model = Compound
        fields = ['code', 'name', 'camp', 'is_active', 'monthly_urgent_sqm_quota', 'weekly_urgent_sqm_quota']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter compound code'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter compound name'
            }),
            'camp': forms.Select(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-steel-blue bg-gray-100 border-gray-300 rounded focus:ring-steel-blue focus:ring-2'
            }),
            'monthly_urgent_sqm_quota': forms.NumberInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter monthly urgent SQM quota',
                'step': '0.01',
                'min': '0'
            }),
            'weekly_urgent_sqm_quota': forms.NumberInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter weekly urgent SQM quota',
                'step': '0.01',
                'min': '0'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Style the form fields
        self.fields['code'].label = 'Compound Code'
        self.fields['name'].label = 'Compound Name'
        self.fields['camp'].label = 'Camp'
        self.fields['is_active'].label = 'Active Status'
        self.fields['monthly_urgent_sqm_quota'].label = 'Monthly Urgent SQM Quota'
        self.fields['weekly_urgent_sqm_quota'].label = 'Weekly Urgent SQM Quota'
        
        # Add help text
        self.fields['code'].help_text = 'Unique identifier for the compound'
        self.fields['name'].help_text = 'Full name of the compound'
        self.fields['camp'].help_text = 'Select the camp this compound belongs to'
        self.fields['is_active'].help_text = 'Whether this compound is currently active'
        self.fields['monthly_urgent_sqm_quota'].help_text = 'Monthly SQM quota for urgent cleaning requests (optional)'
        self.fields['weekly_urgent_sqm_quota'].help_text = 'Weekly SQM quota for urgent cleaning requests (optional)'


class BuildingEditForm(forms.ModelForm):
    """Form for editing building details with project definition styling."""
    
    class Meta:
        model = Building
        fields = ['code', 'name', 'compound', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter building code'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter building name'
            }),
            'compound': forms.Select(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-steel-blue bg-gray-100 border-gray-300 rounded focus:ring-steel-blue focus:ring-2'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Style the form fields
        self.fields['code'].label = 'Building Code'
        self.fields['name'].label = 'Building Name'
        self.fields['compound'].label = 'Compound'
        self.fields['is_active'].label = 'Active Status'
        
        # Add help text
        self.fields['code'].help_text = 'Unique identifier for the building'
        self.fields['name'].help_text = 'Full name of the building'
        self.fields['compound'].help_text = 'Select the compound this building belongs to'
        self.fields['is_active'].help_text = 'Whether this building is currently active'


class FloorEditForm(forms.ModelForm):
    """Form for editing floor details with project definition styling."""
    
    class Meta:
        model = Floor
        fields = ['code', 'name', 'building', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter floor code'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200',
                'placeholder': 'Enter floor name'
            }),
            'building': forms.Select(attrs={
                'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-steel-blue bg-gray-100 border-gray-300 rounded focus:ring-steel-blue focus:ring-2'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Style the form fields
        self.fields['code'].label = 'Floor Code'
        self.fields['name'].label = 'Floor Name'
        self.fields['building'].label = 'Building'
        self.fields['is_active'].label = 'Active Status'
        
        # Add help text
        self.fields['code'].help_text = 'Unique identifier for the floor'
        self.fields['name'].help_text = 'Full name of the floor'
        self.fields['building'].help_text = 'Select the building this floor belongs to'
        self.fields['is_active'].help_text = 'Whether this floor is currently active'


class CompoundCreateForm(forms.ModelForm):
    """Form for creating compounds."""
    
    class Meta:
        model = Compound
        fields = ['camp', 'code', 'name', 'is_active', 'monthly_urgent_sqm_quota', 'weekly_urgent_sqm_quota']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id, is_active=True)
                else:
                    self.fields['camp'].queryset = Camp.objects.none()
            else:
                self.fields['camp'].queryset = Camp.objects.filter(is_active=True)


class BuildingCreateForm(forms.ModelForm):
    """Form for creating buildings."""
    
    class Meta:
        model = Building
        fields = ['compound', 'code', 'name', 'is_active']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['compound'].queryset = Compound.objects.filter(camp=camp, is_active=True)
                else:
                    self.fields['compound'].queryset = Compound.objects.none()
            else:
                self.fields['compound'].queryset = Compound.objects.filter(is_active=True)


class FloorCreateForm(forms.ModelForm):
    """Form for creating floors."""
    
    class Meta:
        model = Floor
        fields = ['building', 'code', 'name', 'is_active']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['building'].queryset = Building.objects.filter(compound__camp=camp, is_active=True)
                else:
                    self.fields['building'].queryset = Building.objects.none()
            else:
                self.fields['building'].queryset = Building.objects.filter(is_active=True)


class RoomCreateForm(forms.ModelForm):
    """Form for creating rooms with all required fields."""
    
    class Meta:
        model = Room
        fields = [
            'camp', 'compound', 'building', 'floor', 'room_code', 'room_description', 
            'space_type', 'dumpster_type', 'building_code', 'square_meters', 'quantity_of_rooms', 
            'actual_sqm', 'frequency_per_day', 'frequency_per_week', 
            'max_frequency_per_month', 'weekly_required_sqm', 'monthly_cap_sqm',
            'service_start_date', 'service_end_date', 'weeks_of_service',
            'custom_field_name', 'custom_field_value', 'is_active'
        ]
        widgets = {
            'service_start_date': forms.DateInput(attrs={'type': 'date'}),
            'service_end_date': forms.DateInput(attrs={'type': 'date'}),
            'room_description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Make all fields required except room_description
        for field_name, field in self.fields.items():
            if field_name != 'room_description':
                field.required = True
        
        if self.request and hasattr(self.request.user, 'profile'):
            # Filter by user's camp if not admin
            if self.request.user.profile.role != 'admin':
                camp = self.request.user.profile.camp
                if camp:
                    self.fields['camp'].queryset = Camp.objects.filter(id=camp.id, is_active=True)
                    self.fields['compound'].queryset = Compound.objects.filter(camp=camp, is_active=True)
                    self.fields['building'].queryset = Building.objects.filter(compound__camp=camp, is_active=True)
                    self.fields['floor'].queryset = Floor.objects.filter(building__compound__camp=camp, is_active=True)
                else:
                    self.fields['camp'].queryset = Camp.objects.none()
                    self.fields['compound'].queryset = Compound.objects.none()
                    self.fields['building'].queryset = Building.objects.none()
                    self.fields['floor'].queryset = Floor.objects.none()
            else:
                self.fields['camp'].queryset = Camp.objects.filter(is_active=True)
                self.fields['compound'].queryset = Compound.objects.filter(is_active=True)
                self.fields['building'].queryset = Building.objects.filter(is_active=True)
                self.fields['floor'].queryset = Floor.objects.filter(is_active=True)
        
        # Add data attributes for JavaScript filtering
        self.fields['compound'].widget.attrs['data-camp'] = ''
        self.fields['building'].widget.attrs['data-compound'] = ''
        self.fields['floor'].widget.attrs['data-building'] = ''
        
        # Add onchange events
        self.fields['camp'].widget.attrs['onchange'] = 'updateCompounds()'
        self.fields['compound'].widget.attrs['onchange'] = 'updateBuildings()'
        self.fields['building'].widget.attrs['onchange'] = 'updateFloors()'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Business logic validation
        if cleaned_data.get('service_start_date') and cleaned_data.get('service_end_date'):
            if cleaned_data['service_start_date'] > cleaned_data['service_end_date']:
                raise forms.ValidationError("Start Date must be before or equal to End Date")
        
        if cleaned_data.get('actual_sqm') and cleaned_data.get('square_meters'):
            if cleaned_data['actual_sqm'] > cleaned_data['square_meters']:
                raise forms.ValidationError("Actual Sqm cannot exceed Square Meters")
        
        # Validate that frequency doesn't exceed contract caps
        actual_sqm = cleaned_data.get('actual_sqm')
        frequency_per_week = cleaned_data.get('frequency_per_week')
        weekly_required_sqm = cleaned_data.get('weekly_required_sqm')
        max_frequency_per_month = cleaned_data.get('max_frequency_per_month')
        monthly_cap_sqm = cleaned_data.get('monthly_cap_sqm')
        
        # Validate weekly frequency against contract cap
        if actual_sqm and frequency_per_week and weekly_required_sqm:
            calculated_weekly_sqm = actual_sqm * frequency_per_week
            if calculated_weekly_sqm > weekly_required_sqm:
                raise forms.ValidationError(
                    f"Weekly cleaning SQM ({calculated_weekly_sqm}) exceeds contract cap "
                    f"({weekly_required_sqm}). Reduce frequency or increase contract cap."
                )
        
        # Validate monthly frequency against contract cap
        if actual_sqm and max_frequency_per_month and monthly_cap_sqm:
            calculated_monthly_sqm = actual_sqm * max_frequency_per_month
            if calculated_monthly_sqm > monthly_cap_sqm:
                raise forms.ValidationError(
                    f"Monthly cleaning SQM ({calculated_monthly_sqm}) exceeds contract cap "
                    f"({monthly_cap_sqm}). Reduce frequency or increase contract cap."
                )
        
        # Validate frequency consistency
        if frequency_per_week and max_frequency_per_month:
            if frequency_per_week > max_frequency_per_month:
                raise forms.ValidationError(
                    f"Frequency per week ({frequency_per_week}) cannot exceed "
                    f"Max frequency per month ({max_frequency_per_month})"
                )
        
        return cleaned_data


class RoomEditForm(forms.ModelForm):
    """Form for editing rooms with all required fields."""
    
    class Meta:
        model = Room
        fields = [
            'room_code', 'room_description', 'space_type', 'dumpster_type', 'building_code', 
            'square_meters', 'quantity_of_rooms', 'actual_sqm', 'frequency_per_day', 
            'frequency_per_week', 'max_frequency_per_month', 'weekly_required_sqm', 
            'monthly_cap_sqm', 'service_start_date', 'service_end_date', 
            'weeks_of_service', 'custom_field_name', 'custom_field_value', 'is_active'
        ]
        widgets = {
            'service_start_date': forms.DateInput(attrs={'type': 'date'}),
            'service_end_date': forms.DateInput(attrs={'type': 'date'}),
            'room_description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Style the form fields
        for field_name, field in self.fields.items():
            if field_name in ['service_start_date', 'service_end_date']:
                field.widget.attrs.update({
                    'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
                })
            elif field_name == 'room_description':
                field.widget.attrs.update({
                    'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
                })
            elif field_name == 'is_active':
                field.widget.attrs.update({
                    'class': 'w-5 h-5 text-steel-blue bg-gray-100 border-gray-300 rounded focus:ring-steel-blue focus:ring-2'
                })
            else:
                field.widget.attrs.update({
                    'class': 'form-control w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-steel-blue focus:border-transparent transition-all duration-200'
                })
        
        # Ensure initial values are properly set for editing
        if self.instance.pk:
            # Set initial values for all fields
            for field_name, field in self.fields.items():
                if hasattr(self.instance, field_name):
                    field.initial = getattr(self.instance, field_name)
        
        # Add help text for contract caps
        self.fields['weekly_required_sqm'].help_text = 'Contract cap for weekly cleaning SQM (set by contracting authority)'
        self.fields['monthly_cap_sqm'].help_text = 'Contract cap for monthly cleaning SQM (set by contracting authority)'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Business logic validation
        if cleaned_data.get('service_start_date') and cleaned_data.get('service_end_date'):
            if cleaned_data['service_start_date'] > cleaned_data['service_end_date']:
                raise forms.ValidationError("Start Date must be before or equal to End Date")
        
        if cleaned_data.get('actual_sqm') and cleaned_data.get('square_meters'):
            if cleaned_data['actual_sqm'] > cleaned_data['square_meters']:
                raise forms.ValidationError("Actual Sqm cannot exceed Square Meters")
        
        # Validate that frequency doesn't exceed contract caps
        actual_sqm = cleaned_data.get('actual_sqm')
        frequency_per_week = cleaned_data.get('frequency_per_week')
        weekly_required_sqm = cleaned_data.get('weekly_required_sqm')
        max_frequency_per_month = cleaned_data.get('max_frequency_per_month')
        monthly_cap_sqm = cleaned_data.get('monthly_cap_sqm')
        
        # Validate weekly frequency against contract cap
        if actual_sqm and frequency_per_week and weekly_required_sqm:
            calculated_weekly_sqm = actual_sqm * frequency_per_week
            if calculated_weekly_sqm > weekly_required_sqm:
                raise forms.ValidationError(
                    f"Weekly cleaning SQM ({calculated_weekly_sqm}) exceeds contract cap "
                    f"({weekly_required_sqm}). Reduce frequency or increase contract cap."
                )
        
        # Validate monthly frequency against contract cap
        if actual_sqm and max_frequency_per_month and monthly_cap_sqm:
            calculated_monthly_sqm = actual_sqm * max_frequency_per_month
            if calculated_monthly_sqm > monthly_cap_sqm:
                raise forms.ValidationError(
                    f"Monthly cleaning SQM ({calculated_monthly_sqm}) exceeds contract cap "
                    f"({monthly_cap_sqm}). Reduce frequency or increase contract cap."
                )
        
        # Validate frequency consistency
        if frequency_per_week and max_frequency_per_month:
            if frequency_per_week > max_frequency_per_month:
                raise forms.ValidationError(
                    f"Frequency per week ({frequency_per_week}) cannot exceed "
                    f"Max frequency per month ({max_frequency_per_month})"
                )
        
        return cleaned_data
