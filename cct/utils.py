"""
Utility functions for the NATO Camp Cleaning Tracker.
Includes helper functions for role management, compound scoping, and audit logging.
"""

from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from accounts.models import get_user_role, get_authority_compound_ids


def get_user_scope(request):
    """
    Get user scope information including role and compound assignments.
    Returns a dictionary with role and compound_ids.
    """
    if not request.user or not request.user.is_authenticated:
        return {
            'role': None,
            'compound_ids': [],
            'is_admin': False,
            'is_supervisor': False,
            'is_cleaner': False,
            'is_authority': False,
        }
    
    role = get_user_role(request.user)
    compound_ids = get_authority_compound_ids(request.user) if role == 'authority' else []
    
    return {
        'role': role,
        'compound_ids': compound_ids,
        'is_admin': role == 'admin',
        'is_supervisor': role == 'supervisor',
        'is_cleaner': role == 'cleaner',
        'is_authority': role == 'authority',
    }


def can_access_compound(user, compound_id):
    """
    Check if user can access a specific compound.
    """
    if not user or not user.is_authenticated:
        return False
    
    role = get_user_role(user)
    
    # Admins and supervisors can access all compounds
    if role in ['admin', 'supervisor']:
        return True
    
    # Authority users can only access their assigned compounds
    if role == 'authority':
        user_compound_ids = get_authority_compound_ids(user)
        return compound_id in user_compound_ids
    
    return False


def can_access_room(user, room):
    """
    Check if user can access a specific room.
    """
    if not user or not user.is_authenticated:
        return False
    
    role = get_user_role(user)
    
    # Admins and supervisors can access all rooms
    if role in ['admin', 'supervisor']:
        return True
    
    # Authority users can only access rooms in their assigned compounds
    if role == 'authority':
        compound_id = room.floor.building.compound_id
        return can_access_compound(user, compound_id)
    
    # Cleaners can access all active rooms
    if role == 'cleaner':
        return room.is_active
    
    return False


def get_accessible_rooms(user):
    """
    Get all rooms accessible to the user based on their role and compound assignments.
    """
    from locations.models import Room
    
    if not user or not user.is_authenticated:
        return Room.objects.none()
    
    role = get_user_role(user)
    
    # Admins and supervisors can access all rooms
    if role in ['admin', 'supervisor']:
        return Room.objects.all()
    
    # Authority users can only access rooms in their assigned compounds
    if role == 'authority':
        compound_ids = get_authority_compound_ids(user)
        if not compound_ids:
            return Room.objects.none()
        return Room.objects.filter(floor__building__compound_id__in=compound_ids)
    
    # Cleaners can access all active rooms
    if role == 'cleaner':
        return Room.objects.filter(is_active=True)
    
    return Room.objects.none()


def get_accessible_compounds(user):
    """
    Get all compounds accessible to the user based on their role.
    """
    from locations.models import Compound
    
    if not user or not user.is_authenticated:
        return Compound.objects.none()
    
    role = get_user_role(user)
    
    # Admins and supervisors can access all compounds
    if role in ['admin', 'supervisor']:
        return Compound.objects.all()
    
    # Authority users can only access their assigned compounds
    if role == 'authority':
        compound_ids = get_authority_compound_ids(user)
        if not compound_ids:
            return Compound.objects.none()
        return Compound.objects.filter(id__in=compound_ids)
    
    return Compound.objects.none()


def log_user_action(user, action, object_type=None, object_id=None, object_ref=None, **kwargs):
    """
    Log a user action to the audit log.
    """
    from audit.models import AuditLog
    
    return AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_ref=object_ref,
        **kwargs
    )


def get_camp_cutoff_datetime(camp, date, cutoff_type='week'):
    """
    Get the cutoff datetime for a camp on a specific date.
    """
    if cutoff_type == 'week':
        cutoff_day = camp.week_cutoff_day
        cutoff_hour = camp.week_cutoff_hour
    elif cutoff_type == 'month':
        cutoff_day = camp.month_cutoff_day
        cutoff_hour = camp.month_cutoff_hour
    else:
        raise ValueError("cutoff_type must be 'week' or 'month'")
    
    # Create datetime for the cutoff
    cutoff_datetime = datetime.combine(date, datetime.min.time().replace(hour=cutoff_hour))
    
    # Adjust for week cutoff day
    if cutoff_type == 'week':
        # Find the cutoff day in the week containing the date
        days_ahead = cutoff_day - date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        cutoff_date = date + timedelta(days=days_ahead)
        cutoff_datetime = datetime.combine(cutoff_date, datetime.min.time().replace(hour=cutoff_hour))
    
    return cutoff_datetime


def is_past_cutoff(camp, date, cutoff_type='week'):
    """
    Check if a date is past the camp's cutoff time.
    """
    cutoff_datetime = get_camp_cutoff_datetime(camp, date, cutoff_type)
    return timezone.now() > cutoff_datetime


def get_operational_period(camp, date, period_type='week'):
    """
    Get the operational period (week/month) for a given date based on camp cutoffs.
    """
    if period_type == 'week':
        cutoff_day = camp.week_cutoff_day
        cutoff_hour = camp.week_cutoff_hour
        
        # Find the start of the operational week
        days_back = date.weekday() - cutoff_day
        if days_back < 0:
            days_back += 7
        
        start_date = date - timedelta(days=days_back)
        end_date = start_date + timedelta(days=6)
        
    elif period_type == 'month':
        cutoff_day = camp.month_cutoff_day
        cutoff_hour = camp.month_cutoff_hour
        
        # Find the start of the operational month
        if date.day >= cutoff_day:
            # Current operational month
            start_date = date.replace(day=cutoff_day)
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1) - timedelta(days=1)
        else:
            # Previous operational month
            if date.month == 1:
                start_date = date.replace(year=date.year - 1, month=12, day=cutoff_day)
            else:
                start_date = date.replace(month=date.month - 1, day=cutoff_day)
            end_date = date.replace(day=cutoff_day) - timedelta(days=1)
    
    else:
        raise ValueError("period_type must be 'week' or 'month'")
    
    return start_date, end_date


def generate_barcode_data(room):
    """
    Generate barcode data for a room.
    """
    return room.full_hierarchy_path


def validate_barcode_data(barcode_data):
    """
    Validate barcode data format and extract room information.
    """
    if not barcode_data:
        return False, "Empty barcode data"
    
    # Expected format: CAMP-COMPOUND-BUILDING-FLOOR-ROOM
    parts = barcode_data.split('-')
    if len(parts) != 5:
        return False, f"Invalid barcode format. Expected 5 parts, got {len(parts)}"
    
    camp_code, compound_code, building_code, floor_code, room_code = parts
    
    # Validate that the room exists
    from locations.models import Room
    try:
        room = Room.objects.get(
            code=room_code,
            floor__code=floor_code,
            floor__building__code=building_code,
            floor__building__compound__code=compound_code,
            floor__building__compound__camp__code=camp_code
        )
        return True, room
    except Room.DoesNotExist:
        return False, "Room not found"
    except Room.MultipleObjectsReturned:
        return False, "Multiple rooms found with same barcode"


def get_room_by_barcode(barcode_data):
    """
    Get room by barcode data.
    """
    is_valid, result = validate_barcode_data(barcode_data)
    if is_valid and isinstance(result, Room):
        return result
    return None


def format_audit_message(user, action, object_ref=None):
    """
    Format a standardized audit message.
    """
    user_str = user.get_full_name() if user else "Anonymous"
    message = f"{user_str} performed {action}"
    if object_ref:
        message += f" on {object_ref}"
    return message
