"""
Location models for the NATO Camp Cleaning Tracker.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
import uuid


class OperationsConfig(models.Model):
    """
    Global, site-wide operations settings (singleton, pk=1).

    This platform is an operations-management tool, not a payment tracker. The
    payment integration is optional: when ``payment_tracking_enabled`` is off,
    payment status is ignored entirely — every point is collected and clients are
    simply billed at the end of the month.
    """
    _CACHE_KEY = "operations_config_payment_tracking"

    id = models.AutoField(primary_key=True)
    payment_tracking_enabled = models.BooleanField(
        default=True,
        help_text="When on, unpaid clients are flagged and skipped on the map. "
                  "When off, everyone is collected and billed monthly.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operations Settings"
        verbose_name_plural = "Operations Settings"

    def __str__(self):
        return "Operations Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)
        try:
            cache.set(self._CACHE_KEY, self.payment_tracking_enabled, 300)
        except Exception:
            pass  # cache backend may be unavailable; DB remains source of truth

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def payment_tracking_on(cls):
        """Cached read of the payment-tracking flag.

        Resilient to a missing cache table (fresh DB) and to reads before the
        model's own migration has run — defaults to True in those cases.
        """
        try:
            val = cache.get(cls._CACHE_KEY)
        except Exception:
            val = None
        if val is None:
            try:
                val = cls.get_solo().payment_tracking_enabled
            except Exception:
                return True
            try:
                cache.set(cls._CACHE_KEY, val, 300)
            except Exception:
                pass
        return val


class Camp(models.Model):
    """
    Top-level camp entity with timezone and policy settings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, help_text="Unique camp code")
    name = models.CharField(max_length=200, help_text="Camp name")
    timezone = models.CharField(max_length=50, default='Europe/Berlin', help_text="Camp timezone")
    week_cutoff_day = models.IntegerField(
        default=6, 
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Week cutoff day (0=Monday, 6=Sunday)"
    )
    week_cutoff_hour = models.IntegerField(
        default=23,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Week cutoff hour (0-23)"
    )
    month_cutoff_day = models.IntegerField(
        default=31,
        validators=[MinValueValidator(0), MaxValueValidator(31)],
        help_text="Month cutoff day (0=End of Month, 1-31=specific day)"
    )
    month_cutoff_hour = models.IntegerField(
        default=23,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Month cutoff hour (0-23)"
    )
    skip_holidays = models.BooleanField(default=True, help_text="Skip holidays in scheduling")

    # Map center for this site (used to center the boundary-drawing map and views).
    # Kept per-site so no coordinates are hardcoded in the app.
    center_lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Map center latitude for this site (WGS84)"
    )
    center_lng = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Map center longitude for this site (WGS84)"
    )
    default_zoom = models.IntegerField(
        default=13,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Default map zoom level for this site"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Site"
        verbose_name_plural = "Sites"

    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this camp."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)

    @property
    def map_center(self):
        """Best-effort map center: explicit site center, else settings default."""
        from django.conf import settings
        if self.center_lat is not None and self.center_lng is not None:
            return {"lat": float(self.center_lat), "lng": float(self.center_lng), "zoom": self.default_zoom}
        c = getattr(settings, "MAP_DEFAULT_CENTER", None) or {}
        return {
            "lat": float(c.get("lat", 0.0)),
            "lng": float(c.get("lng", 0.0)),
            "zoom": int(c.get("zoom", self.default_zoom or 13)),
        }


class Compound(models.Model):
    """
    Compound within a camp.
    """
    # OSM street-population job status (async, persisted so the UI can poll).
    OSM_STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    COLLECTION_WEEKDAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    ZONE_TYPE_CHOICES = [
        ('collection', 'Collection zone (dumpsters)'),
        ('public_area', 'Public area (SQM)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='compounds')
    code = models.CharField(max_length=50, help_text="Compound code")
    name = models.CharField(max_length=200, help_text="Compound name")
    is_active = models.BooleanField(default=True)

    # A zone is either a garbage-collection zone (serviced per dumpster) or an
    # independent public area (serviced by surface area, measured in m²).
    zone_type = models.CharField(
        max_length=20, choices=ZONE_TYPE_CHOICES, default='collection',
        help_text="Collection zone (dumpsters) or public area (SQM)"
    )

    # Collection day for the whole zone. New dumpsters added to this zone inherit
    # this day automatically. The shift/time is assigned separately by the field
    # manager (at the team/route level), not on the zone.
    collection_weekday = models.IntegerField(
        null=True, blank=True, choices=COLLECTION_WEEKDAY_CHOICES,
        help_text="Weekday this zone is collected (0=Mon..6=Sun). New dumpsters inherit this."
    )
    assigned_team = models.ForeignKey(
        'accounts.Team', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_zones',
        help_text="Team responsible for collecting this zone."
    )

    # Zone boundary drawn on a map (GeoJSON Polygon, WGS84). Streets are
    # auto-populated from OpenStreetMap within this boundary.
    geo_polygon = models.TextField(
        blank=True, null=True,
        help_text="GeoJSON Polygon of the zone boundary (drawn on the map)"
    )

    # Async OSM street-population tracking.
    osm_status = models.CharField(
        max_length=20, choices=OSM_STATUS_CHOICES, default='idle',
        help_text="Status of the last OpenStreetMap street-population job"
    )
    osm_message = models.TextField(
        blank=True, null=True, help_text="Result/error message from the last OSM job"
    )
    osm_last_synced_at = models.DateTimeField(
        null=True, blank=True, help_text="When streets were last populated from OSM"
    )
    osm_street_count = models.IntegerField(
        default=0, help_text="Streets created on the last OSM population run"
    )

    # Cleanable surface area (m²) measured from the drawn boundary polygon.
    area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Surface area (m²) computed from the zone boundary"
    )

    # Additional SQM quota for urgent cleaning requests
    monthly_urgent_sqm_quota = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monthly SQM quota for urgent cleaning requests (optional)"
    )
    weekly_urgent_sqm_quota = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Weekly SQM quota for urgent cleaning requests (optional)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['camp', 'code']
        verbose_name = "Zone"
        verbose_name_plural = "Zones"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.camp.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this compound."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)

    @property
    def collection_schedule_display(self) -> str:
        """Human-readable collection day for this zone (time is set by the field manager)."""
        if self.collection_weekday is None:
            return "Unscheduled"
        return dict(self.COLLECTION_WEEKDAY_CHOICES).get(self.collection_weekday, "Unscheduled")

    @property
    def has_boundary(self) -> bool:
        return bool(self.geo_polygon)

    @property
    def boundary_ring(self):
        """Return the outer ring of the boundary as a list of [lng, lat] pairs.

        Accepts a GeoJSON Polygon, a Feature wrapping a Polygon, or a bare
        coordinate ring. Returns None when no valid boundary is stored.
        """
        import json as _json
        if not self.geo_polygon:
            return None
        try:
            data = _json.loads(self.geo_polygon)
        except (ValueError, TypeError):
            return None
        if isinstance(data, dict):
            if data.get("type") == "Feature":
                data = data.get("geometry") or {}
            if data.get("type") == "Polygon":
                coords = data.get("coordinates") or []
                return coords[0] if coords else None
            return None
        if isinstance(data, list) and data and isinstance(data[0], (list, tuple)):
            return data
        return None

    @property
    def boundary_center(self):
        """Centroid (lat/lng) of the boundary ring, or the site center as fallback."""
        ring = self.boundary_ring
        if ring:
            lngs = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if lats and lngs:
                return {"lat": sum(lats) / len(lats), "lng": sum(lngs) / len(lngs),
                        "zoom": self.camp.default_zoom or 14}
        return self.camp.map_center

    @property
    def street_count(self) -> int:
        return self.buildings.filter(is_active=True).count()

    def compute_area_sqm(self):
        """Geodesic-approx area (m²) of the drawn boundary, or None if no boundary."""
        from . import geo
        from decimal import Decimal
        ring = self.boundary_ring
        if not ring:
            return None
        value = geo.polygon_area_sqm(ring)
        return Decimal(str(round(value, 2)))

    @property
    def area_hectares(self):
        if self.area_sqm:
            return round(float(self.area_sqm) / 10000.0, 2)
        return None

    @property
    def is_public_area(self) -> bool:
        return self.zone_type == 'public_area'

    def ensure_area_room(self):
        """For a public-area zone, get/maintain the single representative Service
        Point that carries its cleaning task and surface area (m²). Returns the
        Room, or None for collection zones."""
        if self.zone_type != 'public_area':
            return None
        from datetime import date, timedelta
        from decimal import Decimal as _D

        area = self.area_sqm or self.compute_area_sqm() or _D('1.00')
        center = self.boundary_center or {}
        lat = center.get('lat')
        lng = center.get('lng')

        building, _ = Building.objects.get_or_create(
            compound=self, code='AREA',
            defaults={'name': self.name[:200]},
        )
        floor, _ = Floor.objects.get_or_create(
            building=building, code='A', defaults={'name': 'Area'},
        )
        today = date.today()
        defaults = {
            'camp': self.camp,
            'building': building,
            'floor': floor,
            'room_description': f'Public area — {self.name}',
            'space_type': 'public_area',
            'building_code': 'AREA',
            'square_meters': area,
            'quantity_of_rooms': 1,
            'actual_sqm': area,
            'frequency_per_day': _D('0'),
            'frequency_per_week': _D('1'),
            'max_frequency_per_month': 4,
            'weekly_required_sqm': area,
            'monthly_cap_sqm': area * 4,
            'service_start_date': today,
            'service_end_date': today + timedelta(days=365),
            'weeks_of_service': 52,
            'latitude': _D(str(round(lat, 6))) if lat is not None else None,
            'longitude': _D(str(round(lng, 6))) if lng is not None else None,
            'collection_weekday': self.collection_weekday,
            'is_active': True,
        }
        room, created = Room.objects.get_or_create(
            compound=self, room_code=f'{self.code}-AREA', defaults=defaults,
        )
        if not created:
            room.space_type = 'public_area'
            room.actual_sqm = area
            room.square_meters = area
            room.weekly_required_sqm = area
            room.monthly_cap_sqm = area * 4
            if lat is not None and lng is not None:
                room.latitude = _D(str(round(lat, 6)))
                room.longitude = _D(str(round(lng, 6)))
            room.collection_weekday = self.collection_weekday
            room.is_active = True
            room.save()
        return room
    
    @property
    def has_urgent_sqm_quota(self):
        """Check if compound has any urgent SQM quota allocated."""
        return self.monthly_urgent_sqm_quota is not None or self.weekly_urgent_sqm_quota is not None
    
    @property
    def urgent_sqm_quota_display(self):
        """Get formatted urgent SQM quota display string."""
        if not self.has_urgent_sqm_quota:
            return "No urgent SQM quota allocated"
        
        parts = []
        if self.monthly_urgent_sqm_quota:
            parts.append(f"Monthly: {self.monthly_urgent_sqm_quota:,.2f} m²")
        if self.weekly_urgent_sqm_quota:
            parts.append(f"Weekly: {self.weekly_urgent_sqm_quota:,.2f} m²")
        
        return " | ".join(parts)
    
    def get_urgent_sqm_quota_for_period(self, period_type='monthly'):
        """Get urgent SQM quota amount for specific period type."""
        if period_type == 'monthly':
            return self.monthly_urgent_sqm_quota
        elif period_type == 'weekly':
            return self.weekly_urgent_sqm_quota
        return None
    
    def get_remaining_urgent_sqm_quota(self, period_type='monthly', used_sqm=0):
        """Calculate remaining urgent SQM quota after usage."""
        quota = self.get_urgent_sqm_quota_for_period(period_type)
        if not quota:
            return None
        
        remaining = quota - used_sqm
        return max(remaining, 0)  # Don't go below 0
    
    def can_allocate_urgent_sqm(self, requested_sqm, period_type='monthly', used_sqm=0):
        """Check if compound can allocate requested urgent SQM."""
        remaining_quota = self.get_remaining_urgent_sqm_quota(period_type, used_sqm)
        if remaining_quota is None:
            return False
        
        return requested_sqm <= remaining_quota


class Building(models.Model):
    """
    Building within a compound.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='buildings')
    code = models.CharField(max_length=50, help_text="Building code")
    name = models.CharField(max_length=200, help_text="Building name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Street geometry (GeoJSON) so collection routes follow the real road layout
    # instead of straight lines that cut across properties without streets.
    geo_polyline = models.TextField(
        blank=True, null=True,
        help_text="GeoJSON MultiLineString of the street's road segments"
    )

    class Meta:
        ordering = ['name']
        unique_together = ['compound', 'code']
        verbose_name = "Street"
        verbose_name_plural = "Streets"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.compound.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms in this building."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Floor(models.Model):
    """
    Floor within a building.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    code = models.CharField(max_length=50, help_text="Floor code")
    name = models.CharField(max_length=200, help_text="Floor name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['building', 'code']
        verbose_name = "Street Segment"
        verbose_name_plural = "Street Segments"

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.building.name}"
    
    @property
    def total_sqm(self):
        """Calculate total SQM for all rooms on this floor."""
        return sum(room.actual_sqm for room in self.rooms.filter(is_active=True) if room.actual_sqm)


class Room(models.Model):
    """
    Room/Area within a floor - the smallest unit for cleaning tasks.
    """
    SPACE_TYPE_CHOICES = [
        ('room', 'Room'),
        ('office', 'Office'),
        ('meeting_room', 'Meeting Room'),
        ('corridor', 'Corridor'),
        ('laundry_room', 'Laundry Room'),
        ('toilet', 'Toilet'),
        ('balcony', 'Balcony'),
        ('front_yard', 'Front Yard'),
        ('garage', 'Garage'),
        ('container', 'Container'),
        ('mwa', 'MWA'),
        ('dumpster', 'Dumpster (Garbage Collection)'),
        ('public_area', 'Public Area (SQM)'),
        ('park', 'Park / Green Space'),
        ('city_center', 'City Center / Public Plaza'),
        ('school_yard', 'School Yard'),
        ('other', 'Other'),
    ]

    # Space types treated as public-area cleaning sites (SQM/SLA) on the map.
    PUBLIC_AREA_TYPES = ['public_area', 'park', 'city_center', 'school_yard', 'front_yard']

    # For dumpsters only: whether the bin serves a single household or is a
    # shared communal bin for a whole block.
    DUMPSTER_TYPE_CHOICES = [
        ('household', 'Household (single family)'),
        ('communal', 'Communal (shared block)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Location hierarchy
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='rooms')
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='rooms')
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='rooms')
    
    # Basic information
    room_code = models.CharField(max_length=100, help_text="Room code/identifier")
    room_description = models.TextField(blank=True, null=True, help_text="Room description")
    space_type = models.CharField(max_length=50, choices=SPACE_TYPE_CHOICES, help_text="Type of space")
    building_code = models.CharField(max_length=20, help_text="Building code reference")
    
    # Physical properties
    square_meters = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Square meters (m²)"
    )
    quantity_of_rooms = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantity of rooms"
    )
    actual_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Actual Sqm (m2) for SLA calculations"
    )
    
    # Cleaning schedule
    frequency_per_day = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Frequency Per Day"
    )
    frequency_per_week = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Frequency Per Week"
    )
    max_frequency_per_month = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Max Frequency Per Month"
    )
    
    # SLA calculations
    weekly_required_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total m² Week"
    )
    monthly_cap_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="EoM Invoicing max. Sqm (m2)"
    )
    
    # Service period
    service_start_date = models.DateField(help_text="Start Date")
    service_end_date = models.DateField(help_text="End Date")
    weeks_of_service = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="# Weeks of service"
    )
    
    # Custom field (named by Admin/Manager)
    custom_field_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Custom field name (set by Admin/Manager)"
    )
    custom_field_value = models.TextField(
        blank=True, 
        null=True,
        help_text="Custom field value"
    )
    
    # Geolocation (for the operations map)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Latitude for map placement (WGS84)"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Longitude for map placement (WGS84)"
    )
    geo_polygon = models.TextField(
        blank=True, null=True,
        help_text="Optional GeoJSON geometry outlining a public area (Polygon)"
    )

    # Billing client for a collection point (dumpster). Anonymized on the map.
    client = models.ForeignKey(
        'CollectionClient', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dumpsters',
        help_text="Billing client for this dumpster/collection point"
    )

    # For dumpsters: household (single family) vs communal (shared block bin).
    dumpster_type = models.CharField(
        max_length=20, choices=DUMPSTER_TYPE_CHOICES, default='household', blank=True,
        help_text="For dumpsters: single-family household bin or shared communal block bin"
    )

    # Weekly collection plan: which weekday (0=Mon..6=Sun) this point is serviced,
    # so each team collects <= a daily cap and the week covers the whole area.
    collection_weekday = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Scheduled collection weekday (0=Mon..6=Sun)"
    )
    last_collected_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp of the most recent successful collection"
    )

    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room_code']
        unique_together = ['floor', 'room_code']
        verbose_name = "Service Point"
        verbose_name_plural = "Service Points"

    def __str__(self):
        return f"{self.room_code} - {self.room_description or 'No description'}"

    def clean(self):
        """
        Business logic validation.
        """
        from django.core.exceptions import ValidationError
        
        # If space_type is dumpster, auto-fill defaults to bypass physical sqm requirements
        if self.space_type == 'dumpster':
            self.square_meters = Decimal('1.00')
            self.actual_sqm = Decimal('1.00')
            self.quantity_of_rooms = 1
            if self.frequency_per_week:
                self.weekly_required_sqm = self.frequency_per_week
            if self.max_frequency_per_month:
                self.monthly_cap_sqm = Decimal(str(self.max_frequency_per_month))

        # Date validation
        if self.service_start_date and self.service_end_date:
            if self.service_start_date > self.service_end_date:
                raise ValidationError("Start Date must be before or equal to End Date")
        
        # Frequency validation
        if self.frequency_per_week and self.max_frequency_per_month:
            if self.frequency_per_week > self.max_frequency_per_month:
                raise ValidationError("Frequency per week cannot exceed max frequency per month")
        
        # Area validation (run only for non-dumpster spaces)
        if self.space_type != 'dumpster':
            if self.actual_sqm and self.square_meters:
                if self.actual_sqm > self.square_meters:
                    raise ValidationError("Actual Sqm cannot exceed Square Meters")
            
            # SLA validation (with tolerance)
            if self.actual_sqm and self.frequency_per_week and self.weekly_required_sqm:
                expected_weekly_sqm = self.actual_sqm * self.frequency_per_week
                tolerance = expected_weekly_sqm * Decimal('0.02')  # 2% tolerance
                if abs(self.weekly_required_sqm - expected_weekly_sqm) > tolerance:
                    raise ValidationError(
                        f"Weekly required Sqm ({self.weekly_required_sqm}) should be approximately "
                        f"Actual Sqm × Frequency Per Week ({expected_weekly_sqm})"
                    )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def generate_barcode_data(self) -> str:
        """
        Generate barcode data string for this room
        Format: C1-D-B87-R101 (max 16 characters)
        """
        from accounts.barcode_service import BarcodeService
        return BarcodeService.generate_barcode_data(self)
    
    def generate_barcode_image(self, width: int = 600, height: int = 240) -> bytes:
        """
        Generate barcode image as bytes
        """
        from accounts.barcode_service import BarcodeService
        barcode_data = self.generate_barcode_data()
        return BarcodeService.generate_barcode_with_text(barcode_data, width, height)
    
    @property
    def barcode_display(self) -> str:
        """
        Get barcode data for display
        """
        return self.generate_barcode_data()

    @property
    def is_dumpster(self) -> bool:
        return self.space_type == 'dumpster'

    @property
    def is_communal_dumpster(self) -> bool:
        return self.is_dumpster and self.dumpster_type == 'communal'

    @property
    def dumpster_type_label(self) -> str:
        return self.get_dumpster_type_display() if self.is_dumpster else ''

    @property
    def is_public_area(self) -> bool:
        return self.space_type in self.PUBLIC_AREA_TYPES

    @property
    def can_collect(self) -> bool:
        """
        Whether a collection team may service this dumpster right now, based on the
        billing client's payment status. Dumpsters without a client default to
        blocked (must be confirmed before collecting).
        """
        if not self.is_dumpster:
            return True
        # Payment integration is optional. When disabled, everyone is collected
        # (billed monthly) — this is an operations tool, not a payment tracker.
        if not OperationsConfig.payment_tracking_on():
            return True
        return bool(self.client and self.client.can_collect)


class CollectionClient(models.Model):
    """
    Anonymized billing client for a garbage-collection point (dumpster).

    Deliberately holds NO personal name so it can be safely exposed on the
    operations map. Only an opaque `client_code` and the payment state are shown to
    teams; any human-readable notes stay in `internal_note` (never serialized to the
    map API).
    """
    PAYMENT_STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
        ('overdue', 'Overdue'),
        ('exempt', 'Exempt (public)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_code = models.CharField(
        max_length=50, unique=True,
        help_text="Anonymized client identifier shown on the map (no name)"
    )
    compound = models.ForeignKey(
        Compound, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='clients', help_text="Neighbourhood this client belongs to"
    )
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid'
    )
    paid_until = models.DateField(
        null=True, blank=True, help_text="Service paid through this date (optional)"
    )
    internal_note = models.TextField(
        blank=True, null=True,
        help_text="Internal only — never exposed on the public map"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client_code']
        verbose_name = "Collection Client"
        verbose_name_plural = "Collection Clients"

    def __str__(self):
        return f"{self.client_code} ({self.get_payment_status_display()})"

    @property
    def can_collect(self) -> bool:
        """Collection allowed when paid/exempt and not past the paid-until date."""
        if self.payment_status not in ('paid', 'exempt'):
            return False
        if self.paid_until and self.paid_until < timezone.localdate():
            return False
        return True


class UrgentCleaningRequest(models.Model):
    """
    Model for urgent cleaning requests made by admin, manager, or authority users.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='urgent_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='urgent_requests')
    title = models.CharField(max_length=200, help_text="Brief title for the urgent cleaning request")
    description = models.TextField(help_text="Detailed description of the cleaning requirements")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_sqm = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="SQM area that needs urgent cleaning"
    )
    estimated_duration = models.IntegerField(
        help_text="Estimated duration in hours",
        validators=[MinValueValidator(1), MaxValueValidator(24)]
    )
    requested_date = models.DateTimeField(default=timezone.now)
    preferred_start_time = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Preferred start time for the cleaning"
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_urgent_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Additional notes or comments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Urgent Cleaning Request"
        verbose_name_plural = "Urgent Cleaning Requests"
    
    def __str__(self):
        return f"Urgent Request: {self.title} - {self.compound.name} ({self.get_status_display()})"
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def can_be_approved(self):
        return self.status == 'pending'
    
    @property
    def can_be_completed(self):
        return self.status in ['approved', 'in_progress']


class MonthlyRollup(models.Model):
    """
    Materialized rollup model for fast reporting and compliance calculations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='monthly_rollups')
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='monthly_rollups')
    compound = models.ForeignKey(Compound, on_delete=models.CASCADE, related_name='monthly_rollups')
    camp = models.ForeignKey(Camp, on_delete=models.CASCADE, related_name='monthly_rollups')
    period_start = models.DateField(help_text="Start of the rollup period")
    period_end = models.DateField(help_text="End of the rollup period")
    required_weekly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    achieved_weekly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    achieved_monthly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    capped_monthly_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    sla_weekly_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    sla_monthly_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start', 'room__room_code']
        unique_together = ['room', 'period_start', 'period_end']
        verbose_name = "Monthly Rollup"
        verbose_name_plural = "Monthly Rollups"

    def __str__(self):
        return f"Rollup: {self.room.room_code} ({self.period_start} to {self.period_end})"