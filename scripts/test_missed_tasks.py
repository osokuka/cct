#!/usr/bin/env python
"""
Test script for missed tasks functionality.
This script can be used to test the missed tasks logic without affecting production data.
"""

import os
import sys
import django
from datetime import timedelta

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cct.settings')
django.setup()

from accounts.task_generation import DailyCleaningTask
from django.utils import timezone
from django.db.models import Q


def test_missed_tasks_logic():
    """Test the missed tasks logic"""
    today = timezone.now().date()
    cutoff_date = today - timedelta(days=1)
    
    print(f"Testing Missed Tasks Logic")
    print(f"Today: {today}")
    print(f"Cutoff date: {cutoff_date}")
    print("=" * 50)
    
    # Get all tasks
    all_tasks = DailyCleaningTask.objects.all()
    print(f"Total tasks in database: {all_tasks.count()}")
    
    # Check current states
    states = all_tasks.values_list('state', flat=True).distinct()
    print(f"Current task states: {list(states)}")
    
    for state in states:
        count = all_tasks.filter(state=state).count()
        print(f"  {state}: {count}")
    
    print("\nTasks by date:")
    for days_ago in range(0, 5):
        date = today - timedelta(days=days_ago)
        tasks_on_date = all_tasks.filter(task_date=date)
        if tasks_on_date.exists():
            planned = tasks_on_date.filter(state='planned')
            done = tasks_on_date.filter(state='done')
            missed = tasks_on_date.filter(state='missed')
            print(f"  {date}: Total={tasks_on_date.count()}, Planned={planned.count()}, Done={done.count()}, Missed={missed.count()}")
    
    # Test the missed tasks query
    print(f"\nMissed tasks query (planned + past due):")
    missed_tasks = all_tasks.filter(
        Q(state='missed') | 
        (Q(state='planned') & Q(task_date__lt=today))
    )
    print(f"  Total missed tasks: {missed_tasks.count()}")
    
    # Test the command query
    print(f"\nCommand query (planned + on/before cutoff):")
    command_tasks = all_tasks.filter(
        state='planned',
        task_date__lte=cutoff_date
    ).exclude(
        state__in=['done', 'missed']
    )
    print(f"  Tasks that would be marked as missed: {command_tasks.count()}")
    
    if command_tasks.exists():
        print("  Tasks by compound:")
        compound_summary = {}
        for task in command_tasks:
            compound_name = task.room.compound.name
            if compound_name not in compound_summary:
                compound_summary[compound_name] = 0
            compound_summary[compound_name] += 1
        
        for compound_name, count in sorted(compound_summary.items()):
            print(f"    {compound_name}: {count}")


if __name__ == "__main__":
    test_missed_tasks_logic()
