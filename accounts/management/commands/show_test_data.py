"""
Management command to show summary of test data.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from locations.models import Camp, Compound, Building, Floor, Room
from accounts.models import UserProfile, Team, Shift, Route


class Command(BaseCommand):
    help = 'Show summary of test data'

    def handle(self, *args, **options):
        self.stdout.write('=== TEST DATA SUMMARY ===\n')
        
        # Show Camps
        camps = Camp.objects.all()
        self.stdout.write(f'Camps: {camps.count()}')
        for camp in camps:
            self.stdout.write(f'  - {camp.name} ({camp.code})')
        
        # Show Compounds
        compounds = Compound.objects.all()
        self.stdout.write(f'\nCompounds: {compounds.count()}')
        for compound in compounds:
            self.stdout.write(f'  - {compound.name} ({compound.code}) - {compound.camp.name}')
        
        # Show Buildings
        buildings = Building.objects.all()
        self.stdout.write(f'\nBuildings: {buildings.count()}')
        for building in buildings:
            self.stdout.write(f'  - {building.name} - {building.compound.name}')
        
        # Show Floors
        floors = Floor.objects.all()
        self.stdout.write(f'\nFloors: {floors.count()}')
        for floor in floors:
            self.stdout.write(f'  - {floor.name} - {floor.building.name}')
        
        # Show Rooms
        rooms = Room.objects.all()
        self.stdout.write(f'\nRooms: {rooms.count()}')
        for room in rooms:
            self.stdout.write(f'  - {room.room_code} ({room.space_type}) - {room.room_description} - {room.compound.name}')
        
        # Show Users
        users = User.objects.all()
        self.stdout.write(f'\nUsers: {users.count()}')
        for user in users:
            if hasattr(user, 'profile'):
                self.stdout.write(f'  - {user.username} ({user.profile.get_role_display()}) - {user.get_full_name()}')
            else:
                self.stdout.write(f'  - {user.username} (No Profile) - {user.get_full_name()}')
        
        # Show Teams
        teams = Team.objects.all()
        self.stdout.write(f'\nTeams: {teams.count()}')
        for team in teams:
            member_count = team.members.count()
            self.stdout.write(f'  - {team.name} (Leader: {team.team_leader.username}, Members: {member_count})')
        
        # Show Shifts
        shifts = Shift.objects.all()
        self.stdout.write(f'\nShifts: {shifts.count()}')
        for shift in shifts:
            self.stdout.write(f'  - {shift.name} ({shift.start_time} - {shift.end_time})')
        
        # Show Routes
        routes = Route.objects.all()
        self.stdout.write(f'\nRoutes: {routes.count()}')
        for route in routes:
            self.stdout.write(f'  - {route.team.name} → {route.compound.name} ({route.shift.name})')
        
        self.stdout.write('\n=== END SUMMARY ===')
