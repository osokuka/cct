"""
Management command to generate SLA reports for all compounds.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import datetime, timedelta, date
from decimal import Decimal
import os

from locations.models import Compound
from reports.views import generate_compound_sla_excel, generate_all_compounds_sla_excel


class Command(BaseCommand):
    help = 'Generate SLA reports for all compounds and save them to files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='reports_output',
            help='Directory to save the generated reports (default: reports_output)'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for the report (YYYY-MM-DD format)'
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date for the report (YYYY-MM-DD format)'
        )
        parser.add_argument(
            '--compound-id',
            type=str,
            help='Generate report for specific compound only'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        start_date_str = options['start_date']
        end_date_str = options['end_date']
        compound_id = options['compound_id']
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Parse dates
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = timezone.now().date().replace(day=1)  # First day of current month
        
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()  # Today
        
        self.stdout.write(f"Generating SLA reports for period: {start_date} to {end_date}")
        self.stdout.write(f"Output directory: {output_dir}")
        
        if compound_id:
            # Generate report for specific compound
            try:
                compound = Compound.objects.get(id=compound_id)
                self.generate_compound_report(compound, start_date, end_date, output_dir)
            except Compound.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Compound with ID {compound_id} not found"))
                return
        else:
            # Generate reports for all compounds
            compounds = Compound.objects.filter(is_active=True).order_by('name')
            
            # Generate individual compound reports
            for compound in compounds:
                self.generate_compound_report(compound, start_date, end_date, output_dir)
            
            # Generate all compounds summary report
            self.generate_all_compounds_report(compounds, start_date, end_date, output_dir)
        
        self.stdout.write(self.style.SUCCESS("SLA reports generated successfully!"))

    def generate_compound_report(self, compound, start_date, end_date, output_dir):
        """Generate individual compound report"""
        try:
            workbook = generate_compound_sla_excel(compound, start_date, end_date)
            filename = f"SLA_Report_{compound.name}_{start_date}_{end_date}.xlsx"
            filepath = os.path.join(output_dir, filename)
            workbook.save(filepath)
            self.stdout.write(f"  ✓ Generated: {filename}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error generating report for {compound.name}: {str(e)}"))

    def generate_all_compounds_report(self, compounds, start_date, end_date, output_dir):
        """Generate all compounds summary report"""
        try:
            workbook = generate_all_compounds_sla_excel(compounds, start_date, end_date)
            filename = f"All_Compounds_SLA_Report_{start_date}_{end_date}.xlsx"
            filepath = os.path.join(output_dir, filename)
            workbook.save(filepath)
            self.stdout.write(f"  ✓ Generated: {filename}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error generating all compounds report: {str(e)}"))
