"""
Management command to set up initial data for the NATO Camp Cleaning Tracker.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from accounts.models import UserProfile, CompoundAssignment
from locations.models import Camp, Compound, Building, Floor, Room, Shift


class Command(BaseCommand):
    help = 'Set up initial data for the NATO Camp Cleaning Tracker'

    def handle(self, *args, **options):
        self.stdout.write('Setting up initial data...')
        
        # Create user groups
        self.create_user_groups()
        
        # Create admin profile
        self.create_admin_profile()
        
        # Create sample camp data
        self.create_sample_camp_data()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully set up initial data!')
        )

    def create_user_groups(self):
        """Create user groups for role-based access control."""
        groups = ['Admin', 'Supervisor', 'Cleaner', 'Authority']
        
        for group_name in groups:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(f'Created group: {group_name}')
            else:
                self.stdout.write(f'Group already exists: {group_name}')

    def create_admin_profile(self):
        """Create admin user profile."""
        try:
            admin_user = User.objects.get(username='admin')
            profile, created = UserProfile.objects.get_or_create(
                user=admin_user,
                defaults={
                    'role': 'admin',
                    'phone_number': '+1-555-0123',
                    'employee_id': 'ADMIN001',
                    'is_active': True
                }
            )
            
            if created:
                self.stdout.write('Created admin profile')
            else:
                self.stdout.write('Admin profile already exists')
                
            # Add to Admin group
            admin_group = Group.objects.get(name='Admin')
            admin_user.groups.add(admin_group)
            
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('Admin user not found. Please create a superuser first.')
            )

    def create_sample_camp_data(self):
        """Create sample camp, compound, and room data."""
        # Create sample camp
        camp, created = Camp.objects.get_or_create(
            code='CAMP001',
            defaults={
                'name': 'NATO Training Camp Alpha',
                'timezone': 'UTC',
                'week_cutoff_day': 4,  # Thursday
                'week_cutoff_hour': 18,  # 6 PM
                'month_cutoff_day': 25,
                'month_cutoff_hour': 23,
                'skip_holidays': True
            }
        )
        
        if created:
            self.stdout.write('Created sample camp: NATO Training Camp Alpha')
        else:
            self.stdout.write('Sample camp already exists')
        
        # Create sample compounds
        compounds_data = [
            {'code': 'DANISH', 'name': 'Danish Contingent'},
            {'code': 'GERMAN', 'name': 'German Contingent'},
            {'code': 'US', 'name': 'US Contingent'},
            {'code': 'CNS', 'name': 'CNS/AUT Compound'},
        ]
        
        for compound_data in compounds_data:
            compound, created = Compound.objects.get_or_create(
                code=compound_data['code'],
                defaults={
                    'camp': camp,
                    'name': compound_data['name']
                }
            )
            
            if created:
                self.stdout.write(f'Created compound: {compound_data["name"]}')
            
            # Create sample building
            building, created = Building.objects.get_or_create(
                code=f'{compound_data["code"]}_BLDG1',
                defaults={
                    'compound': compound,
                    'name': f'{compound_data["name"]} Main Building'
                }
            )
            
            if created:
                self.stdout.write(f'Created building: {building.name}')
            
            # Create sample floor
            floor, created = Floor.objects.get_or_create(
                code='FLOOR1',
                defaults={
                    'building': building,
                    'name': 'Ground Floor'
                }
            )
            
            if created:
                self.stdout.write(f'Created floor: {floor.name}')
            
            # Create sample rooms
            if compound_data['code'] == 'CNS':
                # CNS/AUT Compound specific rooms
                rooms_data = [
                    {'code': 'BLDG87_TOILET', 'name': 'Bld. 87, 1 single container (toilet)', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 7},
                    {'code': 'BLDG87_F4', 'name': 'Bld. 87,1 single containers F4', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG87_F5', 'name': 'Bld. 87,1 single containers F5', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG87_F6', 'name': 'Bld. 87,1 single containers F6', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG87_KITCHEN', 'name': 'Bld. 87, 1 single container - Kitchen F2', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 6},
                    {'code': 'BLDG87_F7', 'name': 'Bld. 87, 1 double containers F7', 'sqm': 27.50, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG87_F9', 'name': 'Bld. 87, 1 double containers F9', 'sqm': 27.50, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG87_F3', 'name': 'Bld. 87, 1 double container F3 ,1 single container F3', 'sqm': 41.54, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG17_CORRIDOR_GF', 'name': 'Bld. 17 Corridor Ground Floor', 'sqm': 54.45, 'freq_day': 1, 'freq_week': 6},
                    {'code': 'BLDG17_CORRIDOR_FF', 'name': 'Bld. 17 Corridor First Floor', 'sqm': 14.75, 'freq_day': 1, 'freq_week': 6},
                    {'code': 'BLDG193_SANITARY', 'name': 'Bld. 193, 4 single containers (sanitary)', 'sqm': 52.64, 'freq_day': 1, 'freq_week': 7},
                    {'code': 'BLDG126_TOILET', 'name': 'Bld. 126, AUT Toilet next to garage Bld. 126 (single container)', 'sqm': 13.16, 'freq_day': 1, 'freq_week': 6},
                    {'code': 'BLDG103_MWA01', 'name': 'Bld. 103 MWA area 01', 'sqm': 56.83, 'freq_day': 1, 'freq_week': 7},
                    {'code': 'BLDG103_MWA02', 'name': 'Bld. 103 MWA area 02', 'sqm': 28.00, 'freq_day': 1, 'freq_week': 7},
                    {'code': 'BLDG139_101', 'name': 'Bld. 139, I-ZG Kanzei / 101 (Double Container)', 'sqm': 27.50, 'freq_day': 1, 'freq_week': 1},
                    {'code': 'BLDG139_102', 'name': 'Bld. 139, Auftenthaltsraum 102 (triple container)', 'sqm': 41.54, 'freq_day': 1, 'freq_week': 3},
                    {'code': 'BLDG126_FMWKST', 'name': 'Bld. 126, Fm-Wkst I04 and EtLG Kanzlei(2 double containers)', 'sqm': 55.00, 'freq_day': 1, 'freq_week': 1},
                    {'code': 'BLDG127_MECHUO', 'name': 'Bld. 127, MechUO Kanzlei I06', 'sqm': 14.76, 'freq_day': 1, 'freq_week': 1},
                ]
            else:
                # Standard rooms for other compounds
                rooms_data = [
                    {'code': 'ROOM101', 'name': 'Conference Room A', 'sqm': 25.0, 'freq_day': 1, 'freq_week': 5},
                    {'code': 'ROOM102', 'name': 'Office Space B', 'sqm': 25.0, 'freq_day': 1, 'freq_week': 5},
                    {'code': 'ROOM103', 'name': 'Storage Room C', 'sqm': 25.0, 'freq_day': 1, 'freq_week': 5},
                ]
            
            for room_data in rooms_data:
                room, created = Room.objects.get_or_create(
                    code=room_data['code'],
                    defaults={
                        'floor': floor,
                        'name': room_data['name'],
                        'sqm': room_data['sqm'],
                        'is_active': True,
                        'frequency_per_day': room_data['freq_day'],
                        'frequency_per_week': room_data['freq_week'],
                        'barcode_data': f'{camp.code}-{compound.code}-{building.code}-{floor.code}-{room_data["code"]}'
                    }
                )
                
                if created:
                    self.stdout.write(f'Created room: {room_data["name"]}')
        
        # Create sample shifts
        shifts_data = [
            {'name': 'Morning Shift', 'start_time': '08:00', 'end_time': '12:00'},
            {'name': 'Afternoon Shift', 'start_time': '13:00', 'end_time': '17:00'},
            {'name': 'Evening Shift', 'start_time': '18:00', 'end_time': '22:00'},
        ]
        
        for shift_data in shifts_data:
            shift, created = Shift.objects.get_or_create(
                camp=camp,
                name=shift_data['name'],
                defaults={
                    'start_time': shift_data['start_time'],
                    'end_time': shift_data['end_time']
                }
            )
            
            if created:
                self.stdout.write(f'Created shift: {shift_data["name"]}')
        
        self.stdout.write('Sample camp data created successfully!')
