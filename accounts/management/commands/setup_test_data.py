"""
Management command to create test data for the NATO Camp Cleaning Tracker.
Creates camps, compounds, buildings, rooms, and users for testing.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import uuid

from locations.models import Camp, Compound, Building, Floor, Room
from accounts.models import UserProfile, Team, Shift, Route


class Command(BaseCommand):
    help = 'Create test data for the NATO Camp Cleaning Tracker'

    def handle(self, *args, **options):
        self.stdout.write('Creating test data...')
        
        # Create Camp Novo Selo
        camp = self.create_camp()
        
        # Create compounds for different nations
        compounds = self.create_compounds(camp)
        
        # Create buildings and rooms for each compound
        for compound in compounds:
            self.create_buildings_and_rooms(compound)
        
        # Create users
        self.create_users(camp)
        
        # Create teams and shifts
        self.create_teams_and_shifts(camp, compounds)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created test data!')
        )

    def create_camp(self):
        """Create Camp Novo Selo (CNS)"""
        camp, created = Camp.objects.get_or_create(
            code='CNS',
            defaults={
                'name': 'Camp Novo Selo',
                'timezone': 'Europe/Belgrade',
                'week_cutoff_day': 6,  # Sunday
                'week_cutoff_hour': 23,
                'month_cutoff_day': 31,
                'month_cutoff_hour': 23,
                'skip_holidays': True,
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write(f'Created camp: {camp.name}')
        else:
            self.stdout.write(f'Camp already exists: {camp.name}')
        
        return camp

    def create_compounds(self, camp):
        """Create compounds for different nations"""
        compounds_data = [
            {'code': 'ALB', 'name': 'Albanian Compound'},
            {'code': 'AUT', 'name': 'Austrian Compound'},
            {'code': 'BUL', 'name': 'Bulgarian Compound'},
            {'code': 'CRO', 'name': 'Croatian Compound'},
            {'code': 'DEN', 'name': 'Danish Compound'},
            {'code': 'GER', 'name': 'German Compound'},
            {'code': 'ITA', 'name': 'Italian Compound'},
            {'code': 'NOR', 'name': 'Norwegian Compound'},
        ]
        
        compounds = []
        for data in compounds_data:
            compound, created = Compound.objects.get_or_create(
                camp=camp,
                code=data['code'],
                defaults={
                    'name': data['name'],
                    'is_active': True
                }
            )
            compounds.append(compound)
            if created:
                self.stdout.write(f'Created compound: {compound.name}')
        
        return compounds

    def create_buildings_and_rooms(self, compound):
        """Create buildings and rooms for a compound based on sample CSV data"""
        
        # Create Building 10A
        building_10a, created = Building.objects.get_or_create(
            compound=compound,
            code='10A',
            defaults={
                'name': f'Building 10A - {compound.name}',
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created building: {building_10a.name}')
        
        # Create floors for Building 10A
        floors_data = [
            {'code': 'F1', 'name': 'Floor 1'},
            {'code': 'F2', 'name': 'Floor 2'},
        ]
        
        floors = []
        for floor_data in floors_data:
            floor, created = Floor.objects.get_or_create(
                building=building_10a,
                code=floor_data['code'],
                defaults={
                    'name': floor_data['name'],
                    'is_active': True
                }
            )
            floors.append(floor)
            if created:
                self.stdout.write(f'Created floor: {floor.name}')
        
        # Create rooms based on sample CSV data
        rooms_data = [
            # Floor 1 rooms
            {
                'room_code': '101',
                'room_description': 'Office Nr 09A - 11 (2 times a week)',
                'space_type': 'office',
                'square_meters': Decimal('45.15'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('45.15'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('2'),
                'max_frequency_per_month': 10,
                'weekly_required_sqm': Decimal('90.3'),
                'monthly_cap_sqm': Decimal('451.5'),
                'floor': floors[0]  # Floor 1
            },
            {
                'room_code': '102',
                'room_description': 'Office Nr 5 (2 times a week)',
                'space_type': 'office',
                'square_meters': Decimal('22.48'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('22.48'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('2'),
                'max_frequency_per_month': 10,
                'weekly_required_sqm': Decimal('44.96'),
                'monthly_cap_sqm': Decimal('224.8'),
                'floor': floors[0]  # Floor 1
            },
            # Floor 2 rooms
            {
                'room_code': '201',
                'room_description': 'Meeting room (1 time a week)',
                'space_type': 'meeting_room',
                'square_meters': Decimal('25.20'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('25.20'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('1'),
                'max_frequency_per_month': 5,
                'weekly_required_sqm': Decimal('25.2'),
                'monthly_cap_sqm': Decimal('126'),
                'floor': floors[1]  # Floor 2
            },
            {
                'room_code': '203',
                'room_description': 'Corridor NSPA (7 times a week)',
                'space_type': 'corridor',
                'square_meters': Decimal('22.52'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('22.52'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('7'),
                'max_frequency_per_month': 31,
                'weekly_required_sqm': Decimal('157.64'),
                'monthly_cap_sqm': Decimal('698.12'),
                'floor': floors[1]  # Floor 2
            },
        ]
        
        # Add some additional rooms for variety
        additional_rooms = [
            {
                'room_code': '103',
                'room_description': 'Office Nr 7 (2 times a week)',
                'space_type': 'office',
                'square_meters': Decimal('19.11'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('19.11'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('2'),
                'max_frequency_per_month': 10,
                'weekly_required_sqm': Decimal('38.22'),
                'monthly_cap_sqm': Decimal('191.1'),
                'floor': floors[0]  # Floor 1
            },
            {
                'room_code': '104',
                'room_description': 'Office Nr 09',
                'space_type': 'office',
                'square_meters': Decimal('4.62'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('4.62'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('1'),
                'max_frequency_per_month': 5,
                'weekly_required_sqm': Decimal('4.62'),
                'monthly_cap_sqm': Decimal('23.1'),
                'floor': floors[0]  # Floor 1
            },
            {
                'room_code': '202',
                'room_description': 'Laundry Room',
                'space_type': 'laundry_room',
                'square_meters': Decimal('14.10'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('14.10'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('0.5'),
                'max_frequency_per_month': 3,
                'weekly_required_sqm': Decimal('7.05'),
                'monthly_cap_sqm': Decimal('42.3'),
                'floor': floors[1]  # Floor 2
            },
        ]
        
        all_rooms = rooms_data + additional_rooms
        
        for room_data in all_rooms:
            floor = room_data.pop('floor')
            room, created = Room.objects.get_or_create(
                camp=compound.camp,
                compound=compound,
                building=building_10a,
                floor=floor,
                room_code=room_data['room_code'],
                defaults={
                    **room_data,
                    'building_code': '10A',
                    'service_start_date': date(2025, 10, 1),
                    'service_end_date': date(2025, 12, 31),
                    'weeks_of_service': 14,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(f'Created room: {room.room_code} - {room.room_description}')

    def create_users(self, camp):
        """Create test users: 3 cleaners, 2 managers, 1 admin"""
        
        # Create Admin (already exists, but create profile if needed)
        admin_user = User.objects.get(username='admin')
        admin_profile, created = UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'role': 'admin',
                'camp': camp,
                'is_team_leader': True,
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'Created admin profile: {admin_user.username}')
        
        # Create 2 Managers
        managers_data = [
            {'username': 'manager1', 'email': 'manager1@example.com', 'first_name': 'John', 'last_name': 'Manager'},
            {'username': 'manager2', 'email': 'manager2@example.com', 'first_name': 'Jane', 'last_name': 'Supervisor'},
        ]
        
        for manager_data in managers_data:
            user, created = User.objects.get_or_create(
                username=manager_data['username'],
                defaults={
                    'email': manager_data['email'],
                    'first_name': manager_data['first_name'],
                    'last_name': manager_data['last_name'],
                    'is_staff': True,
                    'is_active': True
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(f'Created manager user: {user.username}')
            
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'manager',
                    'camp': camp,
                    'is_team_leader': True,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(f'Created manager profile: {user.username}')
        
        # Create 3 Cleaners
        cleaners_data = [
            {'username': 'cleaner1', 'email': 'cleaner1@example.com', 'first_name': 'Mike', 'last_name': 'Cleaner'},
            {'username': 'cleaner2', 'email': 'cleaner2@example.com', 'first_name': 'Sarah', 'last_name': 'Worker'},
            {'username': 'cleaner3', 'email': 'cleaner3@example.com', 'first_name': 'Tom', 'last_name': 'Staff'},
        ]
        
        for cleaner_data in cleaners_data:
            user, created = User.objects.get_or_create(
                username=cleaner_data['username'],
                defaults={
                    'email': cleaner_data['email'],
                    'first_name': cleaner_data['first_name'],
                    'last_name': cleaner_data['last_name'],
                    'is_staff': False,
                    'is_active': True
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(f'Created cleaner user: {user.username}')
            
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'cleaner',
                    'camp': camp,
                    'is_team_leader': False,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(f'Created cleaner profile: {user.username}')

    def create_teams_and_shifts(self, camp, compounds):
        """Create teams and shifts for the camp"""
        
        # Create shifts
        shifts_data = [
            {'name': 'Morning Shift', 'start_time': '06:00', 'end_time': '14:00'},
            {'name': 'Afternoon Shift', 'start_time': '14:00', 'end_time': '22:00'},
            {'name': 'Night Shift', 'start_time': '22:00', 'end_time': '23:59'},
        ]
        
        shifts = []
        for shift_data in shifts_data:
            shift, created = Shift.objects.get_or_create(
                camp=camp,
                name=shift_data['name'],
                defaults={
                    'start_time': shift_data['start_time'],
                    'end_time': shift_data['end_time'],
                    'is_active': True
                }
            )
            shifts.append(shift)
            if created:
                self.stdout.write(f'Created shift: {shift.name}')
        
        # Create teams
        teams_data = [
            {'name': 'Alpha Team', 'team_leader_username': 'manager1'},
            {'name': 'Beta Team', 'team_leader_username': 'manager2'},
        ]
        
        teams = []
        for team_data in teams_data:
            team_leader = User.objects.get(username=team_data['team_leader_username'])
            team, created = Team.objects.get_or_create(
                camp=camp,
                name=team_data['name'],
                defaults={
                    'team_leader': team_leader,
                    'is_active': True
                }
            )
            teams.append(team)
            if created:
                self.stdout.write(f'Created team: {team.name}')
        
        # Add cleaners to teams
        cleaner1 = User.objects.get(username='cleaner1')
        cleaner2 = User.objects.get(username='cleaner2')
        cleaner3 = User.objects.get(username='cleaner3')
        
        teams[0].members.add(cleaner1, cleaner2)
        teams[1].members.add(cleaner3)
        
        # Create routes (assign teams to compounds for specific shifts)
        # Alpha Team - Morning Shift - Albanian Compound
        Route.objects.get_or_create(
            team=teams[0],
            shift=shifts[0],  # Morning Shift
            compound=compounds[0],  # Albanian Compound
            defaults={
                'priority': 1,
                'is_active': True
            }
        )
        
        # Beta Team - Afternoon Shift - Albanian Compound
        Route.objects.get_or_create(
            team=teams[1],
            shift=shifts[1],  # Afternoon Shift
            compound=compounds[0],  # Albanian Compound
            defaults={
                'priority': 2,
                'is_active': True
            }
        )
        
        self.stdout.write('Created teams, shifts, and routes')
