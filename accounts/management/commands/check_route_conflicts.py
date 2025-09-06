"""
Management command to check for route conflicts and provide recommendations.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from accounts.models import Route, Team, Shift
from accounts.route_utils import get_route_assignments_summary


class Command(BaseCommand):
    help = 'Check for route conflicts and provide recommendations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--camp',
            type=str,
            help='Camp name to check (optional)',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix conflicts automatically',
        )

    def handle(self, *args, **options):
        camp_name = options.get('camp')
        fix_conflicts = options.get('fix')
        
        self.stdout.write(self.style.SUCCESS('Checking for route conflicts...\n'))
        
        # Get route assignments summary
        summary = get_route_assignments_summary()
        
        conflicts_found = 0
        recommendations = []
        
        # Check for conflicts
        for key, routes in summary.items():
            if len(routes) > 1:
                conflicts_found += 1
                compound, shift = key.split('_', 1)
                
                self.stdout.write(
                    self.style.ERROR(f'CONFLICT: {compound} during {shift} shift')
                )
                
                for route in routes:
                    self.stdout.write(f'  - Team: {route["team"]} (Priority: {route["priority"]})')
                
                # Generate recommendations
                priorities = [r['priority'] for r in routes]
                max_priority = max(priorities)
                min_priority = min(priorities)
                
                if max_priority - min_priority > 2:
                    recommendations.append(
                        f"Consider adjusting priorities for {compound} during {shift} shift. "
                        f"Current range: {min_priority} to {max_priority}"
                    )
                else:
                    recommendations.append(
                        f"Consider reassigning one team from {compound} during {shift} shift"
                    )
                
                self.stdout.write('')
        
        if conflicts_found == 0:
            self.stdout.write(self.style.SUCCESS('No route conflicts found!'))
        else:
            self.stdout.write(
                self.style.WARNING(f'Found {conflicts_found} route conflicts')
            )
            
            if recommendations:
                self.stdout.write(self.style.SUCCESS('\nRecommendations:'))
                for i, rec in enumerate(recommendations, 1):
                    self.stdout.write(f'{i}. {rec}')
        
        # Show current route assignments
        self.stdout.write(self.style.SUCCESS('\nCurrent Route Assignments:'))
        self.stdout.write('=' * 50)
        
        routes = Route.objects.filter(is_active=True).select_related('team', 'team__shift')
        if camp_name:
            routes = routes.filter(team__camp__name__icontains=camp_name)
        
        for route in routes:
            compounds = ', '.join([c.name for c in route.compounds.all()])
            shift_name = route.team.shift.name if route.team.shift else 'No Shift'
            self.stdout.write(f'{route.team.name} → {compounds} ({shift_name}) [Priority: {route.priority}]')
        
        if fix_conflicts and conflicts_found > 0:
            self.stdout.write(self.style.WARNING('\nAuto-fix functionality not implemented yet.'))
            self.stdout.write('Please resolve conflicts manually using the admin interface.')
