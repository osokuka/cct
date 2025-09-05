from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, CompoundAssignment, Team, Shift, Route


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('role', 'camp', 'is_team_leader', 'phone_number', 'is_active')


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_active')
    list_filter = ('profile__role', 'profile__is_active', 'is_staff', 'is_superuser')
    
    def get_role(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.get_role_display()
        return 'No Role'
    get_role.short_description = 'Role'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'camp', 'is_team_leader', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'camp', 'is_team_leader', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'role', 'camp', 'is_team_leader', 'phone_number')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CompoundAssignment)
class CompoundAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'compound', 'assigned_by', 'assigned_at', 'is_active']
    list_filter = ['is_active', 'compound__camp', 'assigned_at']
    search_fields = ['user__username', 'compound__name', 'assigned_by__username']
    readonly_fields = ['id', 'assigned_at']
    fieldsets = (
        ('Assignment', {
            'fields': ('id', 'user', 'compound', 'assigned_by', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('assigned_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'camp', 'team_leader', 'member_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'camp', 'created_at']
    search_fields = ['name', 'camp__name', 'team_leader__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = ['members']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'camp', 'team_leader', 'is_active')
        }),
        ('Team Members', {
            'fields': ('members',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['name', 'camp', 'start_time', 'end_time', 'is_active', 'created_at']
    list_filter = ['is_active', 'camp', 'created_at']
    search_fields = ['name', 'camp__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'camp', 'start_time', 'end_time', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ['team', 'compound', 'shift', 'priority', 'is_active', 'created_at']
    list_filter = ['is_active', 'team__camp', 'compound', 'shift', 'created_at']
    search_fields = ['team__name', 'compound__name', 'shift__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Route Information', {
            'fields': ('id', 'team', 'shift', 'compound', 'priority', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
