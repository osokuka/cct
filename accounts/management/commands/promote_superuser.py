"""
Management command to promote superusers to admin role in the app.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from accounts.models import UserProfile


class Command(BaseCommand):
    help = 'Promote superusers to admin role in the app'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Specific username to promote (optional)',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        
        if username:
            # Promote specific user
            try:
                user = User.objects.get(username=username)
                self.promote_user(user)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User "{username}" not found.')
                )
        else:
            # Promote all superusers
            superusers = User.objects.filter(is_superuser=True)
            
            if not superusers.exists():
                self.stdout.write(
                    self.style.WARNING('No superusers found.')
                )
                return
            
            for user in superusers:
                self.promote_user(user)

    def promote_user(self, user):
        """Promote a user to admin role."""
        self.stdout.write(f'Promoting user: {user.username}')
        
        # Create or update user profile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': 'admin',
                'phone_number': '+1-555-0000',
                'employee_id': f'ADMIN-{user.username.upper()}',
                'is_active': True
            }
        )
        
        if not created:
            # Update existing profile to admin role
            profile.role = 'admin'
            profile.is_active = True
            profile.save()
            self.stdout.write(f'  Updated profile role to admin')
        else:
            self.stdout.write(f'  Created admin profile')
        
        # Add to Admin group
        admin_group, created = Group.objects.get_or_create(name='Admin')
        user.groups.add(admin_group)
        self.stdout.write(f'  Added to Admin group')
        
        # Ensure user is active and staff
        if not user.is_active:
            user.is_active = True
            user.save()
            self.stdout.write(f'  Activated user account')
        
        if not user.is_staff:
            user.is_staff = True
            user.save()
            self.stdout.write(f'  Made user staff')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully promoted {user.username} to admin role')
        )
