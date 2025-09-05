"""
Management command to create test cleaner users for team assignment testing.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import UserProfile
from locations.models import Camp
import uuid


class Command(BaseCommand):
    help = 'Create test cleaner users (cleaner4-cleaner15) for team assignment testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--camp',
            type=str,
            help='Camp name to assign cleaners to (default: first available camp)',
        )

    def handle(self, *args, **options):
        # Get or create a camp for the cleaners
        camp_name = options.get('camp')
        if camp_name:
            try:
                camp = Camp.objects.get(name=camp_name)
            except Camp.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Camp "{camp_name}" not found. Available camps:')
                )
                for camp in Camp.objects.all():
                    self.stdout.write(f'  - {camp.name}')
                return
        else:
            camp = Camp.objects.first()
            if not camp:
                self.stdout.write(
                    self.style.ERROR('No camps found. Please create a camp first.')
                )
                return

        # Create cleaners 4-15
        created_count = 0
        for i in range(4, 16):
            username = f'cleaner{i}'
            
            # Check if user already exists
            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.WARNING(f'User {username} already exists, skipping...')
                )
                continue

            try:
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@test.com',
                    password='cleaner123',  # Simple password for testing
                    first_name=f'Cleaner',
                    last_name=f'{i}',
                    is_active=True
                )

                # Create user profile
                profile = UserProfile.objects.create(
                    user=user,
                    role='cleaner',
                    camp=camp,
                    is_team_leader=False,
                    phone_number=f'+123456789{i:02d}',
                    is_active=True
                )

                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created {username} (ID: {user.id}) assigned to {camp.name}')
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error creating {username}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully created {created_count} test cleaners assigned to {camp.name}')
        )
        
        # Show summary
        total_cleaners = User.objects.filter(profile__role='cleaner').count()
        self.stdout.write(f'Total cleaners in system: {total_cleaners}')
