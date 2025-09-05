"""
Management command to add more diverse room data with various SLA and frequency patterns.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from decimal import Decimal

from locations.models import Camp, Compound, Building, Floor, Room


class Command(BaseCommand):
    help = 'Add diverse room data with various SLA and frequency patterns'

    def handle(self, *args, **options):
        self.stdout.write('Adding diverse room data...')
        
        # Get the first compound (Albanian)
        compound = Compound.objects.first()
        if not compound:
            self.stdout.write(self.style.ERROR('No compounds found. Run setup_test_data first.'))
            return
        
        # Get Building 10A
        building = Building.objects.filter(compound=compound, code='10A').first()
        if not building:
            self.stdout.write(self.style.ERROR('Building 10A not found.'))
            return
        
        # Get floors
        floor1 = Floor.objects.filter(building=building, code='F1').first()
        floor2 = Floor.objects.filter(building=building, code='F2').first()
        
        if not floor1 or not floor2:
            self.stdout.write(self.style.ERROR('Floors not found.'))
            return
        
        # Add diverse room data based on CSV sample
        diverse_rooms = [
            # High frequency, high SQM rooms
            {
                'room_code': '301',
                'room_description': 'High Traffic Office (3 times a week)',
                'space_type': 'office',
                'square_meters': Decimal('50.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('50.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('3'),
                'max_frequency_per_month': 15,
                'weekly_required_sqm': Decimal('150.00'),
                'monthly_cap_sqm': Decimal('750.00'),
                'floor': floor1
            },
            # Low frequency, low SQM rooms
            {
                'room_code': '302',
                'room_description': 'Storage Room (0.5 times a week)',
                'space_type': 'other',
                'square_meters': Decimal('8.50'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('8.50'),
                'frequency_per_day': Decimal('0.5'),
                'frequency_per_week': Decimal('0.5'),
                'max_frequency_per_month': 2,
                'weekly_required_sqm': Decimal('4.25'),
                'monthly_cap_sqm': Decimal('17.00'),
                'floor': floor1
            },
            # Daily cleaning room
            {
                'room_code': '303',
                'room_description': 'Main Corridor (daily cleaning)',
                'space_type': 'corridor',
                'square_meters': Decimal('35.75'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('35.75'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('7'),
                'max_frequency_per_month': 31,
                'weekly_required_sqm': Decimal('250.25'),
                'monthly_cap_sqm': Decimal('1109.25'),
                'floor': floor2
            },
            # Meeting room with specific requirements
            {
                'room_code': '304',
                'room_description': 'Conference Room (2 times a week)',
                'space_type': 'meeting_room',
                'square_meters': Decimal('30.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('30.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('2'),
                'max_frequency_per_month': 10,
                'weekly_required_sqm': Decimal('60.00'),
                'monthly_cap_sqm': Decimal('300.00'),
                'floor': floor2
            },
            # Toilet with specific cleaning requirements
            {
                'room_code': '305',
                'room_description': 'Toilet Facility (3 times a week)',
                'space_type': 'toilet',
                'square_meters': Decimal('12.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('12.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('3'),
                'max_frequency_per_month': 15,
                'weekly_required_sqm': Decimal('36.00'),
                'monthly_cap_sqm': Decimal('180.00'),
                'floor': floor1
            },
            # Garage with different requirements
            {
                'room_code': '306',
                'room_description': 'Vehicle Garage (1 time a week)',
                'space_type': 'garage',
                'square_meters': Decimal('80.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('80.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('1'),
                'max_frequency_per_month': 5,
                'weekly_required_sqm': Decimal('80.00'),
                'monthly_cap_sqm': Decimal('400.00'),
                'floor': floor2
            },
            # MWA facility (from CSV sample)
            {
                'room_code': '307',
                'room_description': 'MWA Facility (0.5 times a week)',
                'space_type': 'mwa',
                'square_meters': Decimal('38.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('38.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('0.5'),
                'max_frequency_per_month': 3,
                'weekly_required_sqm': Decimal('19.00'),
                'monthly_cap_sqm': Decimal('114.00'),
                'floor': floor1
            },
            # Urgent cleaning room (from CSV sample)
            {
                'room_code': '308',
                'room_description': 'Urgent Cleaning Area (1 time total)',
                'space_type': 'other',
                'square_meters': Decimal('500.00'),
                'quantity_of_rooms': 1,
                'actual_sqm': Decimal('500.00'),
                'frequency_per_day': Decimal('1'),
                'frequency_per_week': Decimal('1'),
                'max_frequency_per_month': 1,
                'weekly_required_sqm': Decimal('500.00'),
                'monthly_cap_sqm': Decimal('500.00'),
                'floor': floor2
            }
        ]
        
        for room_data in diverse_rooms:
            floor = room_data.pop('floor')
            room, created = Room.objects.get_or_create(
                camp=compound.camp,
                compound=compound,
                building=building,
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
                self.stdout.write(f'  SQM: {room.square_meters}, Actual: {room.actual_sqm}')
                self.stdout.write(f'  Freq/Day: {room.frequency_per_day}, Freq/Week: {room.frequency_per_week}')
                self.stdout.write(f'  Max/Month: {room.max_frequency_per_month}')
                self.stdout.write(f'  Weekly Required: {room.weekly_required_sqm}, Monthly Cap: {room.monthly_cap_sqm}')
            else:
                self.stdout.write(f'Room already exists: {room.room_code}')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully added diverse room data!')
        )
