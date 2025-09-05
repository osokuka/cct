"""
Management command to set up initial data for the NATO Camp Cleaning Tracker.
"""

from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Set up initial data for the NATO Camp Cleaning Tracker'

    def handle(self, *args, **options):
        self.stdout.write('Command will be implemented as needed')