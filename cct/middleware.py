"""
Custom middleware for the NATO Camp Cleaning Tracker.
Includes RBAC middleware for role enforcement and audit middleware for security logging.
"""

import time
import json
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from accounts.models import get_user_role, get_authority_compound_ids
from audit.models import AuditLog


class RBACMiddleware(MiddlewareMixin):
    """
    Role-Based Access Control middleware.
    Attaches user role and compound scope to request for use in views and templates.
    """
    
    def process_request(self, request):
        """Attach role and scope information to the request."""
        # Initialize request attributes
        request.role = None
        request.scope = type('Scope', (), {})()
        request.scope.compound_ids = []
        
        # Skip for anonymous users
        if isinstance(request.user, AnonymousUser) or not request.user.is_authenticated:
            return None
        
        # Get user role
        request.role = get_user_role(request.user)
        
        # Get compound scope for Authority users
        if request.role == 'authority':
            request.scope.compound_ids = get_authority_compound_ids(request.user)
        
        return None


class AuditMiddleware(MiddlewareMixin):
    """
    Audit middleware for comprehensive security logging.
    Captures all requests with user, IP, method, path, status, and latency.
    """
    
    def process_request(self, request):
        """Start timing the request."""
        request._audit_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log the request and response."""
        # Calculate latency
        if hasattr(request, '_audit_start_time'):
            latency_ms = int((time.time() - request._audit_start_time) * 1000)
        else:
            latency_ms = None
        
        # Extract request information
        user = getattr(request, 'user', None)
        if isinstance(user, AnonymousUser):
            user = None
        
        ip_address = self._get_client_ip(request)
        method = request.method
        path = request.path
        status_code = response.status_code
        
        # Determine action from path and method
        action = self._determine_action(request, response)
        
        # Extract object reference if available
        object_ref = getattr(request, 'audit_ref', None)
        
        # Clean request data
        request_data = self._clean_request_data(request)
        
        # Clean response data (only for errors or specific actions)
        response_data = None
        if status_code >= 400 or action in ['export_report', 'bulk_import']:
            response_data = self._clean_response_data(response)
        
        # Extract error message for failed requests
        error_message = None
        if status_code >= 400:
            error_message = self._extract_error_message(response)
        
        # Log the audit entry
        try:
            AuditLog.objects.create(
                user=user,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                method=method,
                path=path,
                status_code=status_code,
                latency_ms=latency_ms,
                action=action,
                object_ref=object_ref,
                request_data=request_data,
                response_data=response_data,
                error_message=error_message,
                session_key=request.session.session_key if hasattr(request, 'session') else None,
            )
        except Exception as e:
            # Don't let audit logging break the application
            # In production, you might want to log this to a separate error log
            pass
        
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions."""
        # Calculate latency
        if hasattr(request, '_audit_start_time'):
            latency_ms = int((time.time() - request._audit_start_time) * 1000)
        else:
            latency_ms = None
        
        # Extract request information
        user = getattr(request, 'user', None)
        if isinstance(user, AnonymousUser):
            user = None
        
        ip_address = self._get_client_ip(request)
        method = request.method
        path = request.path
        
        # Log the exception
        try:
            AuditLog.objects.create(
                user=user,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                method=method,
                path=path,
                status_code=500,
                latency_ms=latency_ms,
                action='exception',
                error_message=str(exception),
                session_key=request.session.session_key if hasattr(request, 'session') else None,
            )
        except Exception:
            # Don't let audit logging break the application
            pass
        
        return None
    
    def _get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _determine_action(self, request, response):
        """Determine the action being performed based on request path and method."""
        path = request.path.lower()
        method = request.method
        
        # Authentication actions
        if '/login/' in path:
            return 'login' if method == 'POST' else 'login_view'
        elif '/logout/' in path:
            return 'logout'
        elif '/password-reset/' in path:
            return 'password_reset'
        
        # Admin actions
        elif '/admin/' in path:
            if '/users/' in path:
                return 'user_management'
            elif '/reports/' in path:
                return 'report_generation'
            elif '/audit-logs/' in path:
                return 'audit_log_view'
            elif '/import/' in path:
                return 'bulk_import'
            elif '/roster-management/' in path:
                return 'roster_management'
            elif '/barcode-generator/' in path:
                return 'barcode_generation'
            else:
                return 'admin_access'
        
        # Authority actions
        elif '/authority/' in path:
            if '/reclean-requests/' in path:
                return 'reclean_request'
            elif '/urgent-cleaning-requests/' in path:
                return 'urgent_cleaning_request'
            else:
                return 'authority_access'
        
        # Scanning actions
        elif '/scan' in path or '/api/scans/' in path:
            return 'room_scan'
        
        # API actions
        elif '/api/' in path:
            if method == 'GET':
                return 'api_read'
            elif method == 'POST':
                return 'api_create'
            elif method == 'PUT' or method == 'PATCH':
                return 'api_update'
            elif method == 'DELETE':
                return 'api_delete'
            else:
                return 'api_access'
        
        # Export actions
        elif 'export' in path or 'download' in path:
            return 'export_data'
        
        # Default action
        return f'{method.lower()}_request'
    
    def _clean_request_data(self, request):
        """Clean request data to remove sensitive information."""
        sensitive_fields = ['password', 'token', 'secret', 'key', 'auth', 'csrf']
        
        if request.method == 'GET':
            data = dict(request.GET)
        else:
            try:
                data = dict(request.POST)
            except:
                data = {}
        
        # Remove sensitive fields
        cleaned_data = {}
        for key, value in data.items():
            if not any(sensitive in key.lower() for sensitive in sensitive_fields):
                cleaned_data[key] = value
        
        return cleaned_data if cleaned_data else None
    
    def _clean_response_data(self, response):
        """Clean response data for logging."""
        # Only log basic response info, not full content
        return {
            'content_type': response.get('Content-Type', ''),
            'status_code': response.status_code,
        }
    
    def _extract_error_message(self, response):
        """Extract error message from response."""
        if hasattr(response, 'content'):
            try:
                # Try to parse JSON error response
                content = response.content.decode('utf-8')
                if content.startswith('{'):
                    data = json.loads(content)
                    return data.get('error', data.get('message', 'Unknown error'))
            except:
                pass
        
        return f"HTTP {response.status_code} Error"


class ScopedQuerysetMixin:
    """
    Mixin for views to automatically filter querysets based on user role and compound scope.
    Authority users only see data from their assigned compounds.
    """
    
    def get_queryset(self):
        """Filter queryset based on user role and compound scope."""
        queryset = super().get_queryset()
        
        # Get user role and scope from request
        user_role = getattr(self.request, 'role', None)
        scope = getattr(self.request, 'scope', None)
        compound_ids = getattr(scope, 'compound_ids', []) if scope else []
        
        # Apply compound scoping for Authority users
        if user_role == 'authority' and compound_ids:
            # Filter by compound_id through the hierarchy
            if hasattr(queryset.model, 'compound'):
                # Direct compound relationship
                queryset = queryset.filter(compound_id__in=compound_ids)
            elif hasattr(queryset.model, 'floor'):
                # Through floor -> building -> compound
                queryset = queryset.filter(floor__building__compound_id__in=compound_ids)
            elif hasattr(queryset.model, 'building'):
                # Through building -> compound
                queryset = queryset.filter(building__compound_id__in=compound_ids)
            elif hasattr(queryset.model, 'room'):
                # Through room -> floor -> building -> compound
                queryset = queryset.filter(room__floor__building__compound_id__in=compound_ids)
            elif hasattr(queryset.model, 'requested_by'):
                # For requests, filter by the user's compound assignments
                from accounts.models import CompoundAssignment
                user_compound_ids = list(
                    CompoundAssignment.objects
                    .filter(user=self.request.user)
                    .values_list('compound_id', flat=True)
                )
                if hasattr(queryset.model, 'room'):
                    queryset = queryset.filter(room__floor__building__compound_id__in=user_compound_ids)
        
        return queryset


class RoleRequiredMixin:
    """
    Mixin to require specific roles for view access.
    """
    required_roles = []
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has required role."""
        user_role = getattr(request, 'role', None)
        
        if not user_role or user_role not in self.required_roles:
            if request.user.is_authenticated:
                return JsonResponse(
                    {'error': 'Insufficient permissions'}, 
                    status=403
                )
            else:
                return JsonResponse(
                    {'error': 'Authentication required'}, 
                    status=401
                )
        
        return super().dispatch(request, *args, **kwargs)
