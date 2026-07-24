"""
Forms for location management in the NATO Camp Cleaning Tracker.
"""

import json

from django import forms
from django.db.models import Q
from decimal import Decimal
from .models import Camp, Compound, Building, Floor, Room
from accounts.scoping import is_platform_user, user_camp, scoped_camps, filter_by_camp


# Shared light-theme input styling used by the rebuilt Site/Zone CRUD forms.
INPUT_CLS = (
    "w-full px-4 py-3 border border-gray-300 rounded-lg bg-white text-gray-800 "
    "focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent "
    "transition-all duration-200"
)
CHECKBOX_CLS = "w-5 h-5 text-steel-blue bg-gray-100 border-gray-300 rounded focus:ring-steel-blue focus:ring-2"


class SiteForm(forms.ModelForm):
    """Create/edit a Site (city). Cutoff fields keep their model defaults."""

    class Meta:
        model = Camp
        fields = ['code', 'name', 'timezone', 'center_lat', 'center_lng', 'default_zoom', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'e.g. GJ'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'e.g. Komuna e Gjakovës'}),
            'timezone': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'e.g. Europe/Belgrade'}),
            'center_lat': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': 'any', 'placeholder': '42.370929'}),
            'center_lng': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': 'any', 'placeholder': '20.435395'}),
            'default_zoom': forms.NumberInput(attrs={'class': INPUT_CLS, 'min': 1, 'max': 20}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLS}),
        }
        labels = {
            'code': 'Site code', 'name': 'Site name', 'timezone': 'Timezone',
            'center_lat': 'Map center latitude', 'center_lng': 'Map center longitude',
            'default_zoom': 'Default zoom', 'is_active': 'Active',
        }
        help_texts = {
            'center_lat': 'Used to center the boundary-drawing map (optional).',
            'center_lng': 'Used to center the boundary-drawing map (optional).',
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        qs = Camp.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A site with this code already exists.")
        return code


class ZoneForm(forms.ModelForm):
    """Create/edit a Zone (city zone) with a map-drawn boundary polygon."""

    class Meta:
        model = Compound
        fields = ['camp', 'code', 'name', 'zone_type', 'assigned_team', 'collection_weekday', 'geo_polygon', 'is_active']
        widgets = {
            'camp': forms.Select(attrs={'class': INPUT_CLS}),
            'code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'e.g. Z1'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'e.g. Zona 1 — Qendra'}),
            'zone_type': forms.Select(attrs={'class': INPUT_CLS}),
            'assigned_team': forms.Select(attrs={'class': INPUT_CLS}),
            'geo_polygon': forms.HiddenInput(),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLS}),
        }
        labels = {
            'camp': 'Site', 'code': 'Zone code', 'name': 'Zone name',
            'zone_type': 'Zone type',
            'assigned_team': 'Assigned team', 'collection_weekday': 'Collection day',
            'is_active': 'Active',
        }
        help_texts = {
            'zone_type': 'Collection zone (serviced per dumpster) or public area (serviced by measured m²).',
            'assigned_team': 'Team responsible for this zone.',
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['camp'].queryset = Camp.objects.filter(is_active=True).order_by('name')
        self.fields['geo_polygon'].required = False

        # Collection day (optional). The shift/time is assigned by the field manager.
        self.fields['collection_weekday'] = forms.TypedChoiceField(
            choices=[('', '— unscheduled —')] + WEEKDAY_CHOICES,
            coerce=int, empty_value=None, required=False,
            label='Collection day',
            help_text='New dumpsters added to this zone inherit this day. The shift/time is set by the field manager.',
            widget=forms.Select(attrs={'class': INPUT_CLS}),
        )

        # Responsible team (optional). Filter to the zone's site when known.
        from accounts.models import Team
        team_qs = Team.objects.select_related('team_leader').order_by('name')
        if self.instance and self.instance.pk and self.instance.camp_id:
            team_qs = team_qs.filter(camp_id=self.instance.camp_id)
        self.fields['assigned_team'].queryset = team_qs
        self.fields['assigned_team'].required = False
        self.fields['assigned_team'].empty_label = "— unassigned —"

        if self.request and self.request.user.is_authenticated and not is_platform_user(self.request.user):
            camp = user_camp(self.request.user)
            if camp:
                self.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
                self.fields['camp'].initial = camp
                self.fields['assigned_team'].queryset = Team.objects.filter(
                    camp=camp).select_related('team_leader').order_by('name')
            else:
                self.fields['camp'].queryset = Camp.objects.none()
                self.fields['assigned_team'].queryset = Team.objects.none()

    def clean_geo_polygon(self):
        raw = (self.cleaned_data.get('geo_polygon') or '').strip()
        if not raw:
            return ''
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            raise forms.ValidationError("Boundary is not valid JSON. Redraw the zone on the map.")

        geom = data.get('geometry', data) if isinstance(data, dict) else data
        if not isinstance(geom, dict) or geom.get('type') != 'Polygon':
            raise forms.ValidationError("Boundary must be a GeoJSON Polygon.")
        coords = geom.get('coordinates') or []
        if not coords or len(coords[0]) < 4:
            raise forms.ValidationError("Draw a boundary with at least 3 points.")
        # Store a normalized bare Polygon geometry.
        return json.dumps({'type': 'Polygon', 'coordinates': coords})

    def clean(self):
        cleaned = super().clean()
        camp = cleaned.get('camp')
        code = (cleaned.get('code') or '').strip()
        if camp and code:
            qs = Compound.objects.filter(camp=camp, code__iexact=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', "A zone with this code already exists for this site.")
        return cleaned


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
        self.request = kwargs.pop('request', None)
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

        if self.request and self.request.user.is_authenticated:
            self.fields['compound'].queryset = filter_by_camp(
                Compound.objects.all(), self.request.user
            )


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
        self.request = kwargs.pop('request', None)
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

        if self.request and self.request.user.is_authenticated:
            self.fields['building'].queryset = filter_by_camp(
                Building.objects.all(), self.request.user, camp_lookup='compound__camp'
            )


class CompoundCreateForm(forms.ModelForm):
    """Form for creating compounds."""
    
    class Meta:
        model = Compound
        fields = ['camp', 'code', 'name', 'is_active', 'monthly_urgent_sqm_quota', 'weekly_urgent_sqm_quota']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and self.request.user.is_authenticated:
            self.fields['camp'].queryset = scoped_camps(self.request.user)


class BuildingCreateForm(forms.ModelForm):
    """Form for creating buildings."""
    
    class Meta:
        model = Building
        fields = ['compound', 'code', 'name', 'is_active']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and self.request.user.is_authenticated:
            self.fields['compound'].queryset = filter_by_camp(
                Compound.objects.filter(is_active=True), self.request.user
            )


class FloorCreateForm(forms.ModelForm):
    """Form for creating floors."""
    
    class Meta:
        model = Floor
        fields = ['building', 'code', 'name', 'is_active']
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request and self.request.user.is_authenticated:
            self.fields['building'].queryset = filter_by_camp(
                Building.objects.filter(is_active=True), self.request.user, camp_lookup='compound__camp'
            )


WEEKDAY_CHOICES = [
    (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
    (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
]


class DumpsterForm(forms.ModelForm):
    """Add a single dumpster by GPS. Zone + street are auto-detected in the view."""

    class Meta:
        model = Room
        fields = [
            'latitude', 'longitude', 'dumpster_type', 'room_code',
            'room_description', 'client', 'is_active',
        ]
        widgets = {
            'latitude': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': 'any', 'placeholder': '42.370929', 'id': 'id_latitude'}),
            'longitude': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': 'any', 'placeholder': '20.435395', 'id': 'id_longitude'}),
            'dumpster_type': forms.Select(attrs={'class': INPUT_CLS}),
            'room_code': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'Auto-generated if left blank'}),
            'room_description': forms.TextInput(attrs={'class': INPUT_CLS, 'placeholder': 'Optional note'}),
            'client': forms.Select(attrs={'class': INPUT_CLS}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLS}),
        }
        labels = {
            'latitude': 'Latitude', 'longitude': 'Longitude', 'dumpster_type': 'Dumpster type',
            'room_code': 'Dumpster ID', 'room_description': 'Description',
            'client': 'Billing client', 'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['latitude'].required = True
        self.fields['longitude'].required = True
        self.fields['room_code'].required = False
        self.fields['room_description'].required = False
        self.fields['client'].required = False
        self.fields['client'].queryset = self.fields['client'].queryset.filter(is_active=True)
        self.fields['client'].empty_label = "— none —"


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
        
        if self.request and self.request.user.is_authenticated:
            self.fields['camp'].queryset = scoped_camps(self.request.user)
            self.fields['compound'].queryset = filter_by_camp(
                Compound.objects.filter(is_active=True), self.request.user
            )
            self.fields['building'].queryset = filter_by_camp(
                Building.objects.filter(is_active=True), self.request.user, camp_lookup='compound__camp'
            )
            self.fields['floor'].queryset = filter_by_camp(
                Floor.objects.filter(is_active=True), self.request.user, camp_lookup='building__compound__camp'
            )
        
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
