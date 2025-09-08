# Password Reference Guide

## Password Naming Convention

All passwords in the ARCOM system use a simple numbering system for easy tracking:

### **password1** - Database Password
- **Purpose**: PostgreSQL database authentication
- **Used in**: 
  - `DB_PASSWORD` environment variable
  - `DATABASE_URL` connection string
  - Docker PostgreSQL container
- **Default**: `password1`
- **Change to**: Your secure database password

### **password2** - Email SMTP Password
- **Purpose**: Gmail SMTP authentication for notifications
- **Used in**: 
  - `EMAIL_HOST_PASSWORD` environment variable
  - Email sending functionality
- **Default**: `password2`
- **Change to**: Your Gmail app password

### **password3** - Reserved for Future Use
- **Purpose**: Reserved for future integrations
- **Potential uses**:
  - SSL certificate passwords
  - API keys
  - Third-party service authentication
  - Backup encryption keys

## Environment Variables

### **Current Configuration**
```bash
# Database
DB_PASSWORD=password1
DATABASE_URL=postgresql://arcom:password1@db:5432/arcom

# Email
EMAIL_HOST_PASSWORD=password2

# Security
SECRET_KEY=django-insecure-*&v#&okfzv%-wgvm#q=&qgif1l)vr5gg11i_^fh%bw#+3pu7&!
```

### **Production Changes Needed**
1. **Change password1** to a strong database password
2. **Change password2** to your Gmail app password
3. **Change SECRET_KEY** to a secure random key
4. **Set DEBUG=0** for production

## Quick Setup Commands

### **Development**
```bash
# Use default passwords (password1, password2)
docker-compose up -d
```

### **Production**
```bash
# Set your passwords
export DB_PASSWORD="your-secure-db-password"
export EMAIL_HOST_PASSWORD="your-gmail-app-password"
export SECRET_KEY="your-secure-secret-key"
export DEBUG=0

# Deploy
docker-compose up -d
```

## Security Notes

- **Never commit** the `.env` file to version control
- **Use strong passwords** for production
- **Rotate passwords** regularly
- **Use different passwords** for different environments
- **Keep this reference** updated when adding new passwords

## Password Strength Guidelines

- **Minimum 12 characters**
- **Mix of uppercase, lowercase, numbers, symbols**
- **No dictionary words**
- **Unique for each service**
- **Stored securely** (password manager recommended)
