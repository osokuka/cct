"""
Utility functions for route management and conflict detection.
"""

from django.core.exceptions import ValidationError
from .models import Route, Team, Shift


def check_route_conflicts(team, shift, compounds, exclude_route=None):
    """
    Check if assigning a team to compounds would create conflicts.
    
    Args:
        team: Team instance
        shift: Shift instance (not used in simplified workflow)
        compounds: QuerySet or list of Compound instances
        exclude_route: Route instance to exclude from conflict check (for updates)
    
    Returns:
        dict: {
            'has_conflicts': bool,
            'conflicts': list of conflict details,
            'suggestions': list of suggestions
        }
    """
    conflicts = []
    suggestions = []
    
    # Check for each compound
    for compound in compounds:
        # Find existing routes for this compound
        existing_routes = Route.objects.filter(
            compounds=compound,
            is_active=True
        )
        
        if exclude_route:
            existing_routes = existing_routes.exclude(pk=exclude_route.pk)
        
        if existing_routes.exists():
            for route in existing_routes:
                conflict = {
                    'compound': compound.name,
                    'conflicting_team': route.team.name,
                    'conflicting_route_id': route.id,
                    'priority': route.priority
                }
                conflicts.append(conflict)
                
                # Generate suggestions
                if route.priority < 5:  # Lower priority route
                    suggestions.append(
                        f"Consider increasing priority of {team.name} or decreasing priority of {route.team.name}"
                    )
                else:
                    suggestions.append(
                        f"Consider reassigning {route.team.name} to different compounds"
                    )
    
    return {
        'has_conflicts': len(conflicts) > 0,
        'conflicts': conflicts,
        'suggestions': suggestions
    }


def get_available_compounds_for_team(team, shift=None):
    """
    Get compounds that are available for assignment to a team.
    
    Args:
        team: Team instance
        shift: Shift instance (not used in simplified workflow)
    
    Returns:
        QuerySet: Available compounds
    """
    from locations.models import Compound
    
    # Get compounds already assigned to other teams
    assigned_compounds = Route.objects.filter(
        is_active=True
    ).exclude(team=team).values_list('compounds', flat=True)
    
    # Return compounds not assigned to other teams
    return Compound.objects.filter(
        camp=team.camp,
        is_active=True
    ).exclude(id__in=assigned_compounds)


def get_route_assignments_summary(camp=None):
    """
    Get a summary of all route assignments for conflict analysis.
    
    Args:
        camp: Camp instance to filter by (optional)
    
    Returns:
        dict: Summary of route assignments
    """
    routes = Route.objects.filter(is_active=True)
    if camp:
        routes = routes.filter(team__camp=camp)
    
    summary = {}
    
    for route in routes:
        for compound in route.compounds.all():
            key = f"{compound.name}"
            if key not in summary:
                summary[key] = []
            
            summary[key].append({
                'team': route.team.name,
                'shift': route.team.shift.name if route.team.shift else 'No Shift',
                'priority': route.priority,
                'route_id': route.id
            })
    
    return summary


def validate_team_capacity(team, compounds, shift=None):
    """
    Validate if a team has sufficient capacity for the assigned compounds.
    
    Args:
        team: Team instance
        compounds: QuerySet or list of Compound instances
        shift: Shift instance (not used in simplified workflow)
    
    Returns:
        dict: Validation result with capacity analysis
    """
    # Get team member count
    member_count = team.members.count()
    
    # Calculate total area for assigned compounds
    total_area = sum(compound.total_area for compound in compounds if hasattr(compound, 'total_area'))
    
    # Basic capacity check (can be enhanced with more sophisticated logic)
    capacity_per_member = 1000  # sqm per member (configurable)
    required_members = max(1, total_area // capacity_per_member) if total_area > 0 else 1
    
    return {
        'team_members': member_count,
        'total_area': total_area,
        'required_members': required_members,
        'has_sufficient_capacity': member_count >= required_members,
        'capacity_ratio': member_count / required_members if required_members > 0 else 1
    }
