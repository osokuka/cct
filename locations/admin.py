from django.contrib import admin
from .models import Camp, Compound, Building, Floor, Room


@admin.register(Camp)
class CampAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'timezone', 'is_active', 'created_at']
    list_filter = ['is_active', 'timezone', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'code', 'timezone', 'is_active')
        }),
        ('Policy Settings', {
            'fields': ('week_cutoff_day', 'week_cutoff_hour', 'month_cutoff_day', 'month_cutoff_hour', 'skip_holidays')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Compound)
class CompoundAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'camp', 'is_active', 'created_at']
    list_filter = ['is_active', 'camp', 'created_at']
    search_fields = ['name', 'code', 'camp__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'camp', 'name', 'code', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'compound', 'is_active', 'created_at']
    list_filter = ['is_active', 'compound__camp', 'compound', 'created_at']
    search_fields = ['name', 'code', 'compound__name', 'compound__camp__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'compound', 'name', 'code', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'building', 'is_active', 'created_at']
    list_filter = ['is_active', 'building__compound__camp', 'building__compound', 'building', 'created_at']
    search_fields = ['name', 'code', 'building__name', 'building__compound__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'building', 'name', 'code', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = [
        'room_code', 'room_description', 'space_type', 'building_code', 
        'square_meters', 'actual_sqm', 'frequency_per_day', 'frequency_per_week', 
        'max_frequency_per_month', 'weekly_required_sqm', 'monthly_cap_sqm', 'is_active'
    ]
    list_filter = [
        'space_type', 'dumpster_type', 'is_active', 'camp', 'compound', 'building', 'floor',
        'service_start_date', 'service_end_date', 'created_at'
    ]
    search_fields = [
        'room_code', 'room_description', 'building_code', 
        'camp__name', 'compound__name', 'building__name', 'floor__name'
    ]
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Location Hierarchy', {
            'fields': ('id', 'camp', 'compound', 'building', 'floor')
        }),
        ('Basic Information', {
            'fields': ('room_code', 'room_description', 'space_type', 'dumpster_type', 'building_code')
        }),
        ('Physical Properties', {
            'fields': ('square_meters', 'quantity_of_rooms', 'actual_sqm')
        }),
        ('Cleaning Schedule', {
            'fields': ('frequency_per_day', 'frequency_per_week', 'max_frequency_per_month')
        }),
        ('SLA Calculations', {
            'fields': ('weekly_required_sqm', 'monthly_cap_sqm')
        }),
        ('Service Period', {
            'fields': ('service_start_date', 'service_end_date', 'weeks_of_service')
        }),
        ('Custom Fields', {
            'fields': ('custom_field_name', 'custom_field_value'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queries with select_related."""
        return super().get_queryset(request).select_related(
            'camp', 'compound', 'building', 'floor'
        )
