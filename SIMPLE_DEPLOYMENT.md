# Simple ARCOM Deployment Guide

## Quick Start

### **1. Environment Setup**
The `.env` file is already created with simple passwords:

```bash
# Current passwords (change for production)
DB_PASSWORD=password1          # Database password
EMAIL_HOST_PASSWORD=password2  # Gmail SMTP password
SECRET_KEY=django-insecure-*&v#&okfzv%-wgvm#q=&qgif1l)vr5gg11i_^fh%bw#+3pu7&!
DEBUG=1                       # Set to 0 for production
```

### **2. Development Deployment**
```bash
# Start with default passwords
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs web
```

### **3. Production Deployment**
```bash
# Set your secure passwords
export DB_PASSWORD="your-secure-db-password"
export EMAIL_HOST_PASSWORD="your-gmail-app-password"
export SECRET_KEY="your-secure-secret-key"
export DEBUG=0

# Deploy
docker-compose up -d
```

## Password Reference

| Password | Purpose | Default | Change To |
|----------|---------|---------|-----------|
| `password1` | Database (PostgreSQL) | `password1` | Your secure DB password |
| `password2` | Email SMTP (Gmail) | `password2` | Your Gmail app password |
| `password3` | Reserved | - | Future use |

## Services

- **web**: Django application (port 8232)
- **db**: PostgreSQL database (port 8231)
- **cron**: Daily maintenance tasks

## Access Points

- **Application**: http://localhost:8223
- **Admin Panel**: http://localhost:8232/admin
- **Barcode Scanner**: http://localhost:8232/accounts/scan/

## Default Login

- **Username**: admin
- **Password**: admin123

## Troubleshooting

### **Database Connection Issues**
```bash
# Check database logs
docker-compose logs db

# Restart database
docker-compose restart db
```

### **Application Not Starting**
```bash
# Check application logs
docker-compose logs web

# Restart application
docker-compose restart web
```

### **Cache Issues**
```bash
# Set up database cache
docker-compose exec web python manage.py setup_cache
```

## Production Checklist

- [ ] Change `password1` to secure database password
- [ ] Change `password2` to Gmail app password
- [ ] Change `SECRET_KEY` to secure random key
- [ ] Set `DEBUG=0`
- [ ] Update `ALLOWED_HOSTS` with your domain
- [ ] Set up SSL certificates
- [ ] Configure backup strategy
- [ ] Set up monitoring

## Security Notes

- Never commit `.env` file to version control
- Use strong, unique passwords
- Rotate passwords regularly
- Keep this reference updated
