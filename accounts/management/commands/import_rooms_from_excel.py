
"""
Django management command to import rooms from Excel file.
"""
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from datetime import datetime
from locations.models import Camp, Compound, Building, Floor, Room


class Command(BaseCommand):
    help = 'Import rooms from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to Excel file')
        parser.add_argument('--camp-code', type=str, default='CNS', help='Camp code (default: CNS)')
        parser.add_argument('--camp-name', type=str, default='Camp Novo Selo', help='Camp name (default: Camp Novo Selo)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be created without actually creating')

    def handle(self, *args, **options):
        excel_file = options['excel_file']
        camp_code = options['camp_code']
        camp_name = options['camp_name']
        dry_run = options['dry_run']

        try:
            # Read Excel file
            df = pd.read_excel(excel_file)
            self.stdout.write(f"Read {len(df)} rows from Excel file")

            # Get or create camp
            camp, created = Camp.objects.get_or_create(
                code=camp_code,
                defaults={
                    'name': camp_name,
                    'timezone': 'Europe/Berlin',
                    'week_cutoff_day': 6,
                    'week_cutoff_hour': 23,
                    'month_cutoff_day': 31,
                    'month_cutoff_hour': 23,
                    'skip_holidays': True,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(f"Created camp: {camp.name}")
            else:
                self.stdout.write(f"Using existing camp: {camp.name}")

            if dry_run:
                self.stdout.write("\n=== DRY RUN - What would be created ===")
                self.show_dry_run(df, camp)
                return

            # Process each row
            created_count = 0
            updated_count = 0
            errors = []

            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        result = self.process_row(row, camp, index + 2)  # +2 for header and 0-based index
                        if result['action'] == 'created':
                            created_count += 1
                        elif result['action'] == 'updated':
                            updated_count += 1
                    except Exception as e:
                        error_msg = f"Row {index + 2}: {str(e)}"
                        errors.append(error_msg)
                        self.stdout.write(self.style.ERROR(error_msg))

            # Summary
            self.stdout.write(f"\n=== IMPORT SUMMARY ===")
            self.stdout.write(f"Created: {created_count} rooms")
            self.stdout.write(f"Updated: {updated_count} rooms")
            if errors:
                self.stdout.write(f"Errors: {len(errors)}")
                for error in errors:
                    self.stdout.write(self.style.ERROR(error))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading Excel file: {str(e)}"))

    def show_dry_run(self, df, camp):
        """Show what would be created in dry run mode."""
        compounds = set()
        buildings = set()
        floors = set()
        rooms = []

        for index, row in df.iterrows():
            try:
                # Parse row data
                compound_code = str(row.get('Compound Code', '')).strip()
                compound_name = str(row.get('Compound Name', '')).strip()
                building_code = str(row.get('BLD Code', '')).strip()
                building_name = str(row.get('BLG Name', '')).strip()
                description = str(row.get('Description', '')).strip()
                sqm = self.safe_float(row.get('m²', 0))
                qty_rooms = self.safe_int(row.get('Qty of rooms', 1))
                actual_sqm = self.safe_float(row.get('Actual Sqm (m2)', sqm))
                freq_per_day = self.safe_float(row.get('Frequency Per Day', 1))
                freq_per_week = self.safe_float(row.get('Frequency Per Week', 5))
                max_freq_per_month = self.safe_int(row.get('Max Frexuency Per Month', 20))
                total_sqm_week = self.safe_float(row.get('Total m² Week', actual_sqm * freq_per_week))
                eom_invoicing_max = self.safe_float(row.get('EoM Invoicing max. Sqm (m2)', total_sqm_week * 4))
                weeks_of_service = self.safe_int(row.get('# Weeks of service', 52))
                start_date = self.parse_date(row.get('Start Date'))
                end_date = self.parse_date(row.get('End Date'))

                if compound_code and compound_name:
                    compounds.add((compound_code, compound_name))
                if building_code and building_name:
                    buildings.add((building_code, building_name))
                floors.add('Ground Floor')  # Default floor
                
                rooms.append({
                    'compound_code': compound_code,
                    'compound_name': compound_name,
                    'building_code': building_code,
                    'building_name': building_name,
                    'description': description,
                    'sqm': sqm,
                    'qty_rooms': qty_rooms,
                    'actual_sqm': actual_sqm
                })

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Row {index + 2}: Error parsing - {str(e)}"))

        self.stdout.write(f"\nWould create/update:")
        self.stdout.write(f"- {len(compounds)} compounds")
        self.stdout.write(f"- {len(buildings)} buildings") 
        self.stdout.write(f"- {len(floors)} floors")
        self.stdout.write(f"- {len(rooms)} rooms")

    def process_row(self, row, camp, row_num):
        """Process a single row from the Excel file."""
        # Parse row data
        compound_code = str(row.get('Compound Code', '')).strip()
        compound_name = str(row.get('Compound Name', '')).strip()
        building_code = str(row.get('BLD Code', '')).strip()
        building_name = str(row.get('BLG Name', '')).strip()
        description = str(row.get('Description', '')).strip()
        sqm = self.safe_float(row.get('m²', 0))
        qty_rooms = self.safe_int(row.get('Qty of rooms', 1))
        actual_sqm = self.safe_float(row.get('Actual Sqm (m2)', sqm))
        freq_per_day = self.safe_float(row.get('Frequency Per Day', 1))
        freq_per_week = self.safe_float(row.get('Frequency Per Week', 5))
        max_freq_per_month = self.safe_int(row.get('Max Frexuency Per Month', 20))
        total_sqm_week = self.safe_float(row.get('Total m² Week', actual_sqm * freq_per_week))
        eom_invoicing_max = self.safe_float(row.get('EoM Invoicing max. Sqm (m2)', total_sqm_week * 4))
        weeks_of_service = self.safe_int(row.get('# Weeks of service', 52))
        start_date = self.parse_date(row.get('Start Date'))
        end_date = self.parse_date(row.get('End Date'))

        # Validate required fields
        if not compound_code or not compound_name:
            raise Exception("Missing compound code or name")
        if not building_code or not building_name:
            raise Exception("Missing building code or name")
        if sqm <= 0:
            raise Exception("Invalid square meters")

        # Get or create compound
        compound, created = Compound.objects.get_or_create(
            camp=camp,
            code=compound_code,
            defaults={
                'name': compound_name,
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f"Created compound: {compound.name}")

        # Get or create building
        building, created = Building.objects.get_or_create(
            compound=compound,
            code=building_code,
            defaults={
                'name': building_name,
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f"Created building: {building.name}")

        # Get or create floor (default to Ground Floor)
        floor, created = Floor.objects.get_or_create(
            building=building,
            code='GF',
            defaults={
                'name': 'Ground Floor',
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f"Created floor: {floor.name}")

        # Create room code from building and description
        room_code = f"{building_code}-{description[:10]}" if description else f"{building_code}-ROOM"
        room_code = room_code.replace(' ', '-').upper()

        # Get or create room
        room, created = Room.objects.get_or_create(
            floor=floor,
            room_code=room_code,
            defaults={
                'camp': camp,
                'compound': compound,
                'building': building,
                'room_description': description,
                'space_type': 'room',
                'building_code': building_code,
                'square_meters': Decimal(str(sqm)),
                'quantity_of_rooms': qty_rooms,
                'actual_sqm': Decimal(str(actual_sqm)),
                'frequency_per_day': Decimal(str(freq_per_day)),
                'frequency_per_week': Decimal(str(freq_per_week)),
                'max_frequency_per_month': max_freq_per_month,
                'weekly_required_sqm': Decimal(str(total_sqm_week)),
                'monthly_cap_sqm': Decimal(str(eom_invoicing_max)),
                'service_start_date': start_date or datetime.now().date(),
                'service_end_date': end_date or datetime.now().date() + pd.Timedelta(days=365),
                'weeks_of_service': weeks_of_service,
                'is_active': True
            }
        )

        if created:
            self.stdout.write(f"Created room: {room.room_code} - {room.room_description}")
            return {'action': 'created', 'room': room}
        else:
            self.stdout.write(f"Room already exists: {room.room_code}")
            return {'action': 'updated', 'room': room}

    def safe_float(self, value, default=0):
        """Safely convert value to float."""
        if pd.isna(value) or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def safe_int(self, value, default=1):
        """Safely convert value to int."""
        if pd.isna(value) or value == '':
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

    def parse_date(self, value):
        """Parse date from various formats."""
        if pd.isna(value) or value == '':
            return None
        try:
            if isinstance(value, str):
                # Try different date formats
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(value.strip(), fmt).date()
                    except ValueError:
                        continue
            return pd.to_datetime(value).date()
        except:
            return None
