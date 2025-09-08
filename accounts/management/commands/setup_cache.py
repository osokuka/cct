"""
Django management command to set up database cache table.
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key


class Command(BaseCommand):
    help = 'Set up database cache table for lean deployment'

    def handle(self, *args, **options):
        self.stdout.write("Setting up database cache...")
        
        # Create cache table
        from django.core.management import call_command
        call_command('createcachetable')
        
        # Test cache
        cache.set('test_key', 'test_value', 30)
        if cache.get('test_key') == 'test_value':
            self.stdout.write(
                self.style.SUCCESS('Database cache setup successful!')
            )
        else:
            self.stdout.write(
                self.style.ERROR('Database cache setup failed!')
            )
