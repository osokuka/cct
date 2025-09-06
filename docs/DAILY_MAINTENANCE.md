# Daily Task Maintenance

This document explains how to set up automated daily task maintenance for the ARCOM cleaning management system.

## Overview

The system includes a management command that automatically processes tasks at the end of each day:
- Marks past due tasks as "missed"
- Provides detailed reporting
- Can be run manually or scheduled

## Commands Available

### 1. Mark Missed Tasks Only
```bash
python manage.py mark_missed_tasks [options]
```

**Options:**
- `--dry-run`: Show what would be updated without making changes
- `--days-back N`: Check N days back for missed tasks (default: 1)

**Examples:**
```bash
# Dry run to see what would be updated
python manage.py mark_missed_tasks --dry-run

# Mark tasks from yesterday as missed
python manage.py mark_missed_tasks --days-back 1

# Mark tasks from the last 3 days as missed
python manage.py mark_missed_tasks --days-back 3
```

### 2. Daily Maintenance (Recommended)
```bash
python manage.py daily_task_maintenance [options]
```

**Options:**
- `--dry-run`: Show what would be updated without making changes
- `--mark-missed`: Mark past due tasks as missed (default: True)
- `--days-back N`: Check N days back for missed tasks (default: 1)

**Examples:**
```bash
# Full daily maintenance (recommended)
python manage.py daily_task_maintenance

# Dry run to see what would happen
python manage.py daily_task_maintenance --dry-run
```

## Scheduling the Command

### Option 1: Windows Task Scheduler (Recommended for Windows)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to "Daily" at desired time (e.g., 11:59 PM)
4. Set action to "Start a program"
5. Program: `python`
6. Arguments: `manage.py daily_task_maintenance`
7. Start in: `C:\apps\ARCOM`

### Option 2: Linux/Mac Cron Job

Add to crontab (`crontab -e`):
```bash
# Run daily at 11:59 PM
59 23 * * * cd /path/to/ARCOM && python manage.py daily_task_maintenance
```

### Option 3: Manual Execution

Run the command manually each day:
```bash
cd C:\apps\ARCOM
python manage.py daily_task_maintenance
```

## What the Command Does

### 1. Identifies Missed Tasks
- Finds tasks with `state='planned'`
- Checks if `task_date` is on or before the cutoff date
- Excludes tasks already marked as `done` or `missed`

### 2. Updates Task States
- Changes `state` from `'planned'` to `'missed'`
- Updates all matching tasks in a single database operation
- Provides detailed reporting

### 3. Reports Results
- Shows count of tasks updated by date
- Provides summary by compound
- Logs the action for audit purposes

## Example Output

```
Daily Task Maintenance - 2025-09-06
==================================================

1. Marking missed tasks (before 2025-09-05)
   Found 61 tasks to mark as missed:
     2025-09-05: 61 tasks
   ✓ Successfully marked 61 tasks as missed.
   Summary by compound:
     Albanian Compound: 15 tasks
     Austrian Compound: 12 tasks
     Croatian Compound: 18 tasks
     Danish Compound: 8 tasks
     German Compound: 8 tasks

Daily maintenance completed successfully!
```

## Best Practices

1. **Run Daily**: Schedule the command to run once per day, preferably in the evening
2. **Test First**: Always run with `--dry-run` first to verify what will be updated
3. **Monitor Logs**: Check the application logs for any errors
4. **Backup**: Ensure database backups are in place before running
5. **Timing**: Run after the last shift of the day to avoid marking tasks as missed too early

## Troubleshooting

### Command Not Found
- Ensure you're in the correct directory (`C:\apps\ARCOM`)
- Check that the virtual environment is activated
- Verify Django is properly installed

### Permission Errors
- Ensure the user running the command has database write permissions
- Check file system permissions for the project directory

### No Tasks Found
- Verify the `--days-back` parameter is correct
- Check that tasks exist in the database
- Use `--dry-run` to see what the command would find

## Integration with Dashboard

After running the command, the dashboard will automatically show:
- Updated missed task counts
- Correct task states in the UI
- Accurate compound performance metrics
- Proper urgent request listings

The dashboard logic already handles both actual `missed` state tasks and past due `planned` tasks, so the transition is seamless.
