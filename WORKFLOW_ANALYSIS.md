# NATO Camp Cleaning Tracker - Workflow Analysis

## Current Workflow Overview

### Entity Relationships
```
Cleaners (Users) ←→ Teams (Many-to-Many)
Teams ←→ Routes (One-to-Many)
Shifts ←→ Routes (One-to-Many)
Compounds ←→ Routes (Many-to-Many)
Routes → Tasks (via compound assignment logic)
```

### Workflow Steps

#### 1. **Team Management**
- **Admin/Manager** creates teams with team leaders
- **Team Leaders** can be Admin, Manager, or Cleaner roles
- **Team Members** are Cleaners assigned to teams
- **Business Rule**: One user can only lead one team per camp
- **Business Rule**: One user can only be a member of one team per camp

#### 2. **Shift Management**
- **Admin** creates shifts (8-hour periods) for each camp
- Shifts have start/end times and unique names per camp
- Examples: Morning (06:00-14:00), Afternoon (14:00-22:00), Night (22:00-06:00)

#### 3. **Route Assignment**
- **Admin/Manager** assigns teams to compounds during specific shifts
- **Business Rule**: No overlapping teams in the same compound-shift combination
- Routes have priority levels for conflict resolution
- One team can handle multiple compounds per shift

#### 4. **Task Generation & Assignment**
- **Admin** generates tasks based on room cleaning frequencies
- Tasks are assigned to teams via route logic:
  - Find route for room's compound and shift
  - Assign task to the team in that route
- Tasks start as 'planned' and remain open until completed

#### 5. **Task Execution**
- **Team Leaders** see all tasks for their team's assigned compounds
- **Team Leaders** can mark tasks as completed (representing team completion)
- **Cleaners** can scan barcodes to complete individual tasks
- Tasks can be: planned, in_progress, done, missed, requested

## Business Logic Implementation

### 1. **Team Assignment Rules**
```python
# In Team.clean() method
- Team leader must be Admin, Manager, or Cleaner
- One user can only lead one team per camp
- One user can only be a member of one team per camp
```

### 2. **Route Assignment Rules**
```python
# In Route.clean() method
- No overlapping teams in same compound-shift combination
- Priority-based conflict resolution
- Automatic validation on save
```

### 3. **Conflict Detection**
```python
# In route_utils.py
- check_route_conflicts(): Detects overlapping assignments
- get_available_compounds_for_team(): Shows available compounds
- validate_team_capacity(): Checks team capacity for compounds
```

### 4. **Form Validation**
```python
# In RouteCreateForm and RouteUpdateForm
- Real-time conflict checking
- Detailed error messages with suggestions
- Prevents saving conflicting routes
```

## Current Workflow Issues & Solutions

### Issues Identified:
1. **No overlap prevention**: Multiple teams could be assigned to same compound-shift
2. **No business logic validation**: Teams could be assigned without checking conflicts
3. **No route priority handling**: No clear resolution when conflicts occurred

### Solutions Implemented:
1. **Model-level validation**: Added `clean()` methods to Team and Route models
2. **Form-level validation**: Added conflict checking in RouteCreateForm and RouteUpdateForm
3. **Utility functions**: Created `route_utils.py` for conflict detection and resolution
4. **Management command**: Added `check_route_conflicts.py` for system analysis

## Workflow Benefits

### 1. **Clear Responsibility**
- Each compound-shift combination has exactly one team
- No confusion about who should handle which tasks
- Clear escalation path through team leaders

### 2. **Scalable Structure**
- Teams can handle multiple compounds
- Multiple teams can work different shifts on same compound
- Easy to add/remove teams and routes

### 3. **Conflict Prevention**
- Automatic validation prevents overlapping assignments
- Clear error messages help resolve conflicts
- Priority-based system for complex scenarios

### 4. **Audit Trail**
- All assignments are tracked with timestamps
- Clear ownership of tasks and responsibilities
- Easy to identify and resolve issues

## Usage Examples

### Creating a Team
```python
# Admin creates team with conflict checking
team = Team.objects.create(
    name="Alpha Team",
    camp=camp,
    team_leader=user,  # Must be Admin/Manager/Cleaner
    is_active=True
)
# Automatically validates no existing leadership in same camp
```

### Creating a Route
```python
# Admin creates route with conflict checking
route = Route.objects.create(
    team=team,
    shift=shift,
    compounds=[compound1, compound2],  # Multiple compounds OK
    priority=5,
    is_active=True
)
# Automatically validates no overlapping teams in same compound-shift
```

### Checking for Conflicts
```python
# Check if assignment would create conflicts
from accounts.route_utils import check_route_conflicts

result = check_route_conflicts(team, shift, compounds)
if result['has_conflicts']:
    print("Conflicts found:", result['conflicts'])
    print("Suggestions:", result['suggestions'])
```

## Management Commands

### Check Route Conflicts
```bash
python manage.py check_route_conflicts
python manage.py check_route_conflicts --camp "Camp Name"
python manage.py check_route_conflicts --fix
```

This provides a comprehensive analysis of the workflow and the business logic implemented to prevent overlapping teams in the same route.
