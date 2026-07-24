"""
Account forms for the CCT Cleaning Tracker.
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Team, Shift, Route, RouteStreet, CompoundAssignment, PlanGenerationConfig
from locations.models import Camp, Compound, Building
from .scoping import is_platform_user, user_camp, scoped_camps, filter_by_camp


def _restrict_camp_field(form, request):
    """Limit camp queryset to the actor's scope; lock to their site for non-platform."""
    if not request or not request.user.is_authenticated:
        return
    form.fields['camp'].queryset = scoped_camps(request.user)
    if not is_platform_user(request.user):
        camp = user_camp(request.user)
        if camp:
            form.fields['camp'].queryset = Camp.objects.filter(id=camp.id)
            form.fields['camp'].initial = camp
            # Single choice — no need to disable (disabled fields omit POST values)


class UserCreateForm(UserCreationForm):
    """Form for creating users with profile information."""

    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=True)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select compounds for Authority users to supervise",
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        _restrict_camp_field(self, self.request)
        if self.request and not is_platform_user(self.request.user):
            camp = user_camp(self.request.user)
            if camp:
                self.fields['compounds'].queryset = Compound.objects.filter(
                    camp=camp, is_active=True
                )
        self.fields['compounds'].queryset = self.fields['compounds'].queryset.select_related('camp')

    def clean_camp(self):
        camp = self.cleaned_data.get('camp')
        if self.request and not is_platform_user(self.request.user):
            actor_camp = user_camp(self.request.user)
            if not actor_camp:
                raise forms.ValidationError("You must be assigned to a site to create users.")
            # Disabled field may be missing from cleaned_data
            camp = camp or actor_camp
            if camp.id != actor_camp.id:
                raise forms.ValidationError("You can only create users for your assigned site.")
        if not camp:
            raise forms.ValidationError("Site assignment is required.")
        return camp

    def clean(self):
        cleaned_data = super().clean()
        if self.request and not is_platform_user(self.request.user):
            actor_camp = user_camp(self.request.user)
            if actor_camp and not cleaned_data.get('camp'):
                cleaned_data['camp'] = actor_camp
        role = cleaned_data.get('role')
        compounds = cleaned_data.get('compounds')
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
        if role != 'authority' and compounds:
            cleaned_data['compounds'] = []
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                camp=self.cleaned_data['camp'],
                is_team_leader=self.cleaned_data['is_team_leader'],
                phone_number=self.cleaned_data['phone_number'],
            )
            if self.cleaned_data['role'] == 'authority' and self.cleaned_data.get('compounds'):
                for compound in self.cleaned_data['compounds']:
                    CompoundAssignment.objects.create(
                        user=user,
                        compound=compound,
                        assigned_by=self.request.user if self.request else None,
                    )
        return user


class UserUpdateForm(forms.ModelForm):
    """Form for updating users with profile information."""

    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    camp = forms.ModelChoiceField(queryset=Camp.objects.filter(is_active=True), required=True)
    is_team_leader = forms.BooleanField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    compounds = forms.ModelMultipleChoiceField(
        queryset=Compound.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select compounds for Authority users to supervise",
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        _restrict_camp_field(self, self.request)

        if self.instance.pk and not self.is_bound:
            try:
                profile = self.instance.profile
                self.fields['role'].initial = profile.role
                self.fields['camp'].initial = profile.camp
                self.fields['is_team_leader'].initial = profile.is_team_leader
                self.fields['phone_number'].initial = profile.phone_number
                if profile.role == 'authority':
                    compound_ids = CompoundAssignment.objects.filter(
                        user=self.instance,
                        is_active=True,
                    ).values_list('compound_id', flat=True)
                    self.fields['compounds'].initial = compound_ids
            except UserProfile.DoesNotExist:
                pass

        self.fields['compounds'].queryset = self.fields['compounds'].queryset.select_related('camp')
        if self.request and not is_platform_user(self.request.user):
            camp = user_camp(self.request.user)
            if camp:
                self.fields['compounds'].queryset = self.fields['compounds'].queryset.filter(camp=camp)
            # Non-platform cannot move users between sites (queryset already single-site)

    def clean_camp(self):
        camp = self.cleaned_data.get('camp')
        if self.request and not is_platform_user(self.request.user):
            actor_camp = user_camp(self.request.user)
            if not actor_camp:
                raise forms.ValidationError("You must be assigned to a site.")
            # Preserve existing / actor camp when field disabled
            try:
                camp = camp or self.instance.profile.camp or actor_camp
            except UserProfile.DoesNotExist:
                camp = actor_camp
            if camp.id != actor_camp.id:
                raise forms.ValidationError("You cannot move users to another site.")
        if not camp:
            raise forms.ValidationError("Site assignment is required.")
        return camp

    def clean(self):
        cleaned_data = super().clean()
        if self.request and not is_platform_user(self.request.user):
            actor_camp = user_camp(self.request.user)
            if actor_camp and not cleaned_data.get('camp'):
                try:
                    cleaned_data['camp'] = self.instance.profile.camp or actor_camp
                except UserProfile.DoesNotExist:
                    cleaned_data['camp'] = actor_camp

        role = cleaned_data.get('role')
        compounds = cleaned_data.get('compounds')
        if role == 'authority' and not compounds:
            raise forms.ValidationError("Authority users must be assigned to at least one compound.")
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

            if self.cleaned_data['role'] == 'authority':
                CompoundAssignment.objects.filter(user=user).delete()
                for compound in self.cleaned_data.get('compounds', []):
                    CompoundAssignment.objects.create(
                        user=user,
                        compound=compound,
                        assigned_by=self.request.user if self.request else None,
                    )
            else:
                CompoundAssignment.objects.filter(user=user).delete()
        return user


class TeamCreateForm(forms.ModelForm):
    """Create a team: leader, headcount, vehicle and equipment."""

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
        leader_qs = User.objects.filter(
            profile__role__in=['admin', 'manager', 'cleaner'],
            profile__is_active=True,
        )
        if self.request and self.request.user.is_authenticated:
            _restrict_camp_field(self, self.request)
            if not is_platform_user(self.request.user):
                camp = user_camp(self.request.user)
                if camp:
                    leader_qs = leader_qs.filter(profile__camp=camp)
        self.fields['team_leader'].queryset = leader_qs


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
        if self.request:
            _restrict_camp_field(self, self.request)


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
        if self.request:
            _restrict_camp_field(self, self.request)


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
        if self.request and self.request.user.is_authenticated:
            if not is_platform_user(self.request.user):
                camp = user_camp(self.request.user)
                if camp:
                    team_qs = team_qs.filter(camp=camp)
                    street_qs = street_qs.filter(compound__camp=camp)
            else:
                team_qs = filter_by_camp(team_qs, self.request.user)
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
        if self.request and self.request.user.is_authenticated:
            self.fields['compound'].queryset = filter_by_camp(
                Compound.objects.filter(is_active=True),
                self.request.user,
            )
