# Nginx Proxy Manager Setup for ARCOM

This guide explains how to configure Nginx Proxy Manager to work with the ARCOM Cleaning Management System.

## Prerequisites

- Nginx Proxy Manager installed and running
- ARCOM application running on port 8000
- Domain name pointing to your server (optional)

## Configuration Steps

### 1. Access Nginx Proxy Manager

Open your browser and navigate to:
```
http://your-server-ip:81
```

Default login credentials:
- **Email**: admin@example.com
- **Password**: changeme

### 2. Create Proxy Host

1. **Click "Proxy Hosts"** in the main menu
2. **Click "Add Proxy Host"**
3. **Fill in the details**:

#### Details Tab
- **Domain Names**: `arcom.yourdomain.com` (or your preferred subdomain)
- **Scheme**: `http`
- **Forward Hostname/IP**: `arcom_web_1` (Docker container name) or your server IP
- **Forward Port**: `8000`
- **Cache Assets**: ✅ (recommended)
- **Block Common Exploits**: ✅ (recommended)
- **Websockets Support**: ✅ (if you plan to use real-time features)

#### SSL Tab
- **SSL Certificate**: Select "Request a new SSL Certificate"
- **Force SSL**: ✅ (recommended)
- **HTTP/2 Support**: ✅ (recommended)
- **HSTS Enabled**: ✅ (recommended)
- **HSTS Subdomains**: ✅ (if using subdomains)

#### Advanced Tab
```nginx
# Custom configuration for ARCOM
location / {
    proxy_pass http://arcom_web_1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect off;
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Buffer settings
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;
}

# Static files caching
location /static/ {
    proxy_pass http://arcom_web_1:8000;
    expires 1y;
    add_header Cache-Control "public, immutable";
}

# Media files
location /media/ {
    proxy_pass http://arcom_web_1:8000;
    expires 1y;
    add_header Cache-Control "public";
}
```

### 3. Save and Test

1. **Click "Save"**
2. **Test the configuration** by visiting your domain
3. **Check SSL certificate** is working properly

## Docker Network Configuration

If you're running NPM in Docker, make sure both containers are on the same network:

### Option 1: Use Docker Compose (Recommended)

Add NPM to your `docker-compose.yml`:

```yaml
services:
  # ... your existing services ...
  
  nginx-proxy-manager:
    image: jc21/nginx-proxy-manager:latest
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    volumes:
      - npm_data:/data
      - npm_letsencrypt:/etc/letsencrypt
    restart: unless-stopped

volumes:
  npm_data:
  npm_letsencrypt:
```

### Option 2: Connect to Existing Network

If NPM is already running, connect ARCOM to its network:

```bash
# Find NPM network
docker network ls

# Connect ARCOM to NPM network
docker network connect npm_default arcom_web_1
```

## Environment Variables

Update your `.env` file to include the domain:

```bash
ALLOWED_HOSTS=arcom.yourdomain.com,yourdomain.com,localhost,127.0.0.1
```

## Security Considerations

### 1. Rate Limiting

Add rate limiting in NPM Advanced tab:

```nginx
# Rate limiting for login
location /accounts/login/ {
    proxy_pass http://arcom_web_1:8000;
    limit_req zone=login burst=3 nodelay;
    limit_req_status 429;
}

# Rate limiting for API
location /api/ {
    proxy_pass http://arcom_web_1:8000;
    limit_req zone=api burst=20 nodelay;
    limit_req_status 429;
}
```

### 2. Security Headers

Add security headers in NPM Advanced tab:

```nginx
# Security headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
```

### 3. IP Whitelisting

If you want to restrict access:

1. Go to **Access Lists** in NPM
2. Create a new access list
3. Add allowed IP addresses
4. Assign the access list to your proxy host

## Monitoring

### Health Check

Create a health check endpoint in NPM:

```nginx
location /health/ {
    proxy_pass http://arcom_web_1:8000;
    access_log off;
    return 200 "healthy\n";
    add_header Content-Type text/plain;
}
```

### Logs

Monitor NPM logs:

```bash
# NPM logs
docker logs nginx-proxy-manager

# ARCOM logs
docker-compose logs web
```

## Troubleshooting

### Common Issues

#### 1. 502 Bad Gateway

**Cause**: ARCOM container not running or not accessible

**Solution**:
```bash
# Check if ARCOM is running
docker-compose ps

# Check ARCOM logs
docker-compose logs web

# Test direct connection
curl http://localhost:8000/
```

#### 2. SSL Certificate Issues

**Cause**: Domain not pointing to server or DNS issues

**Solution**:
1. Check DNS records
2. Ensure domain points to your server IP
3. Wait for DNS propagation (up to 24 hours)
4. Check Let's Encrypt logs in NPM

#### 3. Static Files Not Loading

**Cause**: Static files not being served correctly

**Solution**:
```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Check static files
curl -I http://arcom.yourdomain.com/static/admin/css/base.css
```

#### 4. WebSocket Issues

**Cause**: WebSocket support not enabled

**Solution**:
1. Enable "Websockets Support" in NPM proxy host
2. Add WebSocket configuration in Advanced tab:

```nginx
location /ws/ {
    proxy_pass http://arcom_web_1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Performance Optimization

### 1. Caching

Enable caching in NPM:
- **Cache Assets**: ✅
- **Cache Duration**: 1 year for static files

### 2. Compression

Enable gzip compression in Advanced tab:

```nginx
# Gzip compression
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/json
    application/javascript
    application/xml+rss
    application/atom+xml
    image/svg+xml;
```

### 3. HTTP/2

Enable HTTP/2 in SSL tab:
- **HTTP/2 Support**: ✅

## Backup

### NPM Configuration Backup

```bash
# Backup NPM data
docker run --rm -v npm_data:/data -v $(pwd):/backup alpine tar czf /backup/npm_backup.tar.gz -C /data .
```

### Restore NPM Configuration

```bash
# Restore NPM data
docker run --rm -v npm_data:/data -v $(pwd):/backup alpine tar xzf /backup/npm_backup.tar.gz -C /data
```

## Conclusion

With Nginx Proxy Manager properly configured, your ARCOM application will be:

- ✅ **Securely accessible** via HTTPS
- ✅ **Automatically managed** SSL certificates
- ✅ **Performance optimized** with caching and compression
- ✅ **Rate limited** to prevent abuse
- ✅ **Easy to monitor** and maintain

The setup provides a professional, production-ready environment for your ARCOM Cleaning Management System.
