#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cct.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile

def change_user_role(username, new_role):
    """Change a user's role"""
    try:
        user = User.objects.get(username=username)
        if hasattr(user, 'profile'):
            old_role = user.profile.role
            user.profile.role = new_role
            user.profile.save()
            print(f"✅ Changed {username}'s role from '{old_role}' to '{new_role}'")
        else:
            print(f"❌ User {username} doesn't have a profile")
    except User.DoesNotExist:
        print(f"❌ User {username} not found")

# Available users and their current roles
print("=== AVAILABLE USERS ===")
users = User.objects.all()
for user in users:
    role = user.profile.role if hasattr(user, 'profile') else 'No profile'
    print(f"- {user.username} (current role: {role})")

print("\n=== CHANGING ROLES ===")

# Change cleaner1 to manager so you can test
change_user_role('cleaner1', 'manager')

print("\n=== UPDATED USERS ===")
for user in users:
    role = user.profile.role if hasattr(user, 'profile') else 'No profile'
    print(f"- {user.username} (current role: {role})")
