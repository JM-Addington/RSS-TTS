# User Management Commands

This document describes the management commands available for user administration in the RSS-TTS application.

## Overview

The RSS-TTS application includes several Django management commands for user administration via the command line. These commands are particularly useful for:

- Initial setup and creating the first admin user
- Bulk user operations
- Automated scripts and deployment workflows
- Server administration without web interface access

## Available Commands

### 1. `createuser` - Create New Users

Create new regular user accounts.

```bash
# Interactive mode (prompts for details)
python manage.py createuser

# Non-interactive mode with all details
python manage.py createuser --username=newuser --email=user@example.com --password=securepass123 --noinput

# Create user that's already approved
python manage.py createuser --username=approveduser --password=securepass123 --approved --noinput
```

**Options:**
- `--username` - Username for the new user
- `--email` - Email address (optional)
- `--password` - Password (will prompt if not provided)
- `--approved` - Create user as already approved
- `--noinput` - Don't prompt for input (requires username and password)

**Behavior:**
- First user created automatically becomes super admin
- Subsequent users require admin approval (unless `--approved` is used)
- Password validation is enforced

### 2. `approveuser` - Approve/Revoke User Access

Manage user approval status.

```bash
# Approve a pending user
python manage.py approveuser username

# Revoke approval from a user
python manage.py approveuser username --revoke

# List all users pending approval
python manage.py approveuser dummy --list-pending
```

**Options:**
- `--revoke` - Revoke approval instead of granting it
- `--list-pending` - Show all users waiting for approval

**Notes:**
- Cannot revoke approval from super admin users
- Useful for bulk approval operations

### 3. `promoteuser` - Manage Super Admin Status

Promote users to super admin or demote them.

```bash
# Promote user to super admin
python manage.py promoteuser username

# Demote user from super admin
python manage.py promoteuser username --demote

# List all super admin users
python manage.py promoteuser dummy --list-admins

# Force operation even if user is already in target state
python manage.py promoteuser username --force
```

**Options:**
- `--demote` - Remove super admin privileges
- `--list-admins` - Show all super admin users
- `--force` - Force operation regardless of current state

**Protection:**
- Cannot demote the last super admin (safety measure)
- Promoted users are automatically approved
- Demoted users retain their approval status

### 4. `listusers` - Display User Information

List users with various filtering and formatting options.

```bash
# Show all users in table format
python manage.py listusers

# Show only pending users
python manage.py listusers --pending-only

# Show only super admins
python manage.py listusers --admins-only

# Show only approved users
python manage.py listusers --approved-only

# Output in JSON format
python manage.py listusers --format=json

# Output in CSV format
python manage.py listusers --format=csv

# Include inactive users
python manage.py listusers --include-inactive
```

**Options:**
- `--pending-only` - Show only users awaiting approval
- `--admins-only` - Show only super admin users
- `--approved-only` - Show only approved users
- `--format` - Output format: `table` (default), `json`, or `csv`
- `--include-inactive` - Include deactivated users

**Features:**
- Color-coded output in table format
- Summary statistics when showing all users
- Machine-readable formats for automation

### 5. `make_superadmin` - Legacy Super Admin Creation

Make a user super admin (legacy command, use `promoteuser` instead).

```bash
# Make first user super admin
python manage.py make_superadmin

# Make specific user super admin
python manage.py make_superadmin --username=username

# Force operation
python manage.py make_superadmin --username=username --force
```

## Common Workflows

### Initial Setup

```bash
# Create first admin user
python manage.py createuser --username=admin --email=admin@company.com --password=secure123 --noinput

# The first user automatically becomes super admin
```

### Daily Administration

```bash
# Check for pending users
python manage.py listusers --pending-only

# Approve a user
python manage.py approveuser newuser

# Create pre-approved user
python manage.py createuser --username=employee --approved --noinput
```

### Bulk Operations

```bash
# Export user list for reporting
python manage.py listusers --format=csv > users.csv

# Get user data for scripts
python manage.py listusers --format=json | jq '.[] | select(.is_approved == false)'
```

### Emergency Administration

```bash
# List all admins to verify access
python manage.py promoteuser dummy --list-admins

# Promote user to admin if locked out
python manage.py promoteuser username

# Check system status
python manage.py listusers
```

## Security Considerations

1. **First User Protection**: The first user automatically becomes super admin
2. **Last Admin Protection**: Cannot demote the last super admin
3. **Password Validation**: All passwords must meet Django's validation requirements
4. **Approval Workflow**: New users (except first) require explicit approval
5. **Audit Trail**: All operations are logged to Django's logging system

## Integration with Web Interface

- CLI operations are immediately reflected in the web interface
- Web interface and CLI commands use the same underlying models
- No synchronization required between CLI and web operations

## Error Handling

All commands include comprehensive error handling:
- Duplicate username detection
- Invalid user references
- Safety checks for critical operations
- Clear error messages with suggested fixes

## Examples for Automation

### Shell Script for User Creation
```bash
#!/bin/bash
# create_user.sh
python manage.py createuser \
    --username="$1" \
    --email="$2" \
    --password="$3" \
    --approved \
    --noinput
```

### Backup Script
```bash
#!/bin/bash
# backup_users.sh
python manage.py listusers --format=json > "users_backup_$(date +%Y%m%d).json"
```

### Monitoring Script
```bash
#!/bin/bash
# check_pending.sh
PENDING=$(python manage.py listusers --pending-only --format=json | jq length)
if [ "$PENDING" -gt 0 ]; then
    echo "Warning: $PENDING users pending approval"
    python manage.py approveuser dummy --list-pending
fi
```
