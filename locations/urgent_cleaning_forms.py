"""
Forms for urgent cleaning request functionality.
"""

from django import forms
from .models import UrgentCleaningRequest, Compound, Room


class UrgentCleaningRequestForm(forms.ModelForm):
    """
    Form for creating urgent cleaning requests.
    """
    room = forms.ModelChoiceField(
        queryset=Room.objects.none(),
        required=False,
        empty_label="Select a room...",
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
            'id': 'id_room'
        })
    )
    
    class Meta:
        model = UrgentCleaningRequest
        fields = [
            'compound', 'room', 'title', 'description', 'priority', 
            'requested_sqm', 'estimated_duration', 'preferred_start_time', 'notes'
        ]
        widgets = {
            'compound': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent'
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'placeholder': 'Brief title for the urgent cleaning request'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'rows': 4,
                'placeholder': 'Detailed description of the cleaning requirements'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent'
            }),
            'requested_sqm': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'step': '0.01',
                'min': '0.01'
            }),
            'estimated_duration': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'min': '1',
                'max': '24'
            }),
            'preferred_start_time': forms.DateTimeInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
                'rows': 3,
                'placeholder': 'Additional notes or comments (optional)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter compounds based on user role
        if user:
            if user.profile.role == 'authority':
                # Authority users can only request for their assigned compounds
                self.fields['compound'].queryset = Compound.objects.filter(
                    assignments__user=user
                ).distinct()
            else:
                # Admin and manager can request for all compounds
                self.fields['compound'].queryset = Compound.objects.filter(is_active=True)
        
        # Set default values
        if not self.instance.pk:
            self.fields['priority'].initial = 'medium'
            self.fields['estimated_duration'].initial = 2
            
        # Add JavaScript for room filtering and SQM calculation
        self.fields['compound'].widget.attrs.update({
            'onchange': 'filterRooms()',
            'id': 'id_compound'
        })
        self.fields['room'].widget.attrs.update({
            'onchange': 'calculateSQM()',
            'id': 'id_room'
        })
        self.fields['requested_sqm'].widget.attrs.update({
            'readonly': 'readonly',
            'id': 'id_requested_sqm'
        })
        
        # If compound is pre-selected, populate rooms
        if 'compound' in self.data:
            try:
                compound_id = self.data.get('compound')
                if compound_id:
                    self.fields['room'].queryset = Room.objects.filter(
                        floor__building__compound_id=compound_id,
                        is_active=True
                    ).select_related('floor', 'floor__building').order_by('room_code')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, 'compound') and self.instance.compound:
            self.fields['room'].queryset = Room.objects.filter(
                floor__building__compound=self.instance.compound,
                is_active=True
            ).select_related('floor', 'floor__building').order_by('room_code')
        
        # Handle pre-selected compound from URL parameters
        if hasattr(self, 'initial') and 'compound' in self.initial:
            compound = self.initial['compound']
            if compound:
                self.fields['room'].queryset = Room.objects.filter(
                    floor__building__compound=compound,
                    is_active=True
                ).select_related('floor', 'floor__building').order_by('room_code')
    
    def clean_requested_sqm(self):
        sqm = self.cleaned_data.get('requested_sqm')
        if sqm and sqm <= 0:
            raise forms.ValidationError("Requested SQM must be greater than 0.")
        return sqm
    
    def clean_room(self):
        room = self.cleaned_data.get('room')
        compound = self.cleaned_data.get('compound')
        
        if room and compound:
            # Verify that the selected room belongs to the selected compound
            if room.floor.building.compound != compound:
                raise forms.ValidationError("Selected room does not belong to the selected compound.")
        
        return room
    
    def clean_estimated_duration(self):
        duration = self.cleaned_data.get('estimated_duration')
        if duration and (duration < 1 or duration > 24):
            raise forms.ValidationError("Estimated duration must be between 1 and 24 hours.")
        return duration


class UrgentCleaningRequestQuickForm(forms.Form):
    """
    Quick form for creating urgent cleaning requests from the dashboard.
    """
    compound_id = forms.UUIDField(widget=forms.HiddenInput())
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
            'placeholder': 'Brief title for the urgent cleaning request'
        })
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
            'rows': 3,
            'placeholder': 'Detailed description of the cleaning requirements'
        })
    )
    priority = forms.ChoiceField(
        choices=UrgentCleaningRequest.PRIORITY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent'
        })
    )
    requested_sqm = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
            'step': '0.01',
            'min': '0.01'
        })
    )
    estimated_duration = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-steel-blue focus:border-transparent',
            'min': '1',
            'max': '24'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['priority'].initial = 'medium'
        self.fields['estimated_duration'].initial = 2
        self.fields['requested_sqm'].initial = 10.0
