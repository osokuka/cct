"""
Management command to show detailed room data with SLA and frequency information.
"""

from django.core.management.base import BaseCommand
from locations.models import Room


class Command(BaseCommand):
    help = 'Show detailed room data with SLA and frequency information'

    def handle(self, *args, **options):
        self.stdout.write('=== ROOM DETAILS WITH SLA & FREQUENCY DATA ===\n')
        
        rooms = Room.objects.all().order_by('compound__name', 'room_code')
        
        for room in rooms:
            self.stdout.write(f'🏢 {room.room_code} - {room.room_description}')
            self.stdout.write(f'   📍 {room.compound.name} - {room.building.name} - {room.floor.name}')
            self.stdout.write(f'   🏷️  Type: {room.get_space_type_display()}')
            self.stdout.write(f'   📐 Square Meters: {room.square_meters} m²')
            self.stdout.write(f'   📊 Actual SQM: {room.actual_sqm} m²')
            self.stdout.write(f'   🔄 Frequency/Day: {room.frequency_per_day}')
            self.stdout.write(f'   📅 Frequency/Week: {room.frequency_per_week}')
            self.stdout.write(f'   📆 Max Frequency/Month: {room.max_frequency_per_month}')
            self.stdout.write(f'   📈 Weekly Required SQM: {room.weekly_required_sqm} m²')
            self.stdout.write(f'   💰 Monthly Cap SQM: {room.monthly_cap_sqm} m²')
            self.stdout.write(f'   📅 Service Period: {room.service_start_date} to {room.service_end_date}')
            self.stdout.write(f'   ⏱️  Weeks of Service: {room.weeks_of_service}')
            self.stdout.write(f'   ✅ Active: {room.is_active}')
            if room.custom_field_name:
                self.stdout.write(f'   🔧 Custom Field ({room.custom_field_name}): {room.custom_field_value}')
            self.stdout.write('')
        
        # Summary statistics
        total_rooms = rooms.count()
        total_sqm = sum(room.actual_sqm for room in rooms)
        total_weekly_required = sum(room.weekly_required_sqm for room in rooms)
        total_monthly_cap = sum(room.monthly_cap_sqm for room in rooms)
        
        self.stdout.write('=== SUMMARY STATISTICS ===')
        self.stdout.write(f'Total Rooms: {total_rooms}')
        self.stdout.write(f'Total Actual SQM: {total_sqm} m²')
        self.stdout.write(f'Total Weekly Required SQM: {total_weekly_required} m²')
        self.stdout.write(f'Total Monthly Cap SQM: {total_monthly_cap} m²')
        
        # Frequency distribution
        freq_dist = {}
        for room in rooms:
            freq = str(room.frequency_per_week)
            freq_dist[freq] = freq_dist.get(freq, 0) + 1
        
        self.stdout.write('\n=== FREQUENCY DISTRIBUTION ===')
        for freq, count in sorted(freq_dist.items()):
            self.stdout.write(f'Frequency {freq}/week: {count} rooms')
        
        self.stdout.write('\n=== END DETAILS ===')
