"""
logging_config.py

Centralized logging configuration for the enterprise AI copilot system.

Provides structured logging with:
- User context tracking
- Audit trail for sensitive operations
- Performance monitoring
- Error tracking with context
- Security event logging
"""

import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from functools import wraps
from contextvars import ContextVar

# Context variables for user tracking
current_user: ContextVar[Optional[Dict[str, Any]]] ContextVar('current_user', default=None)
request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record):
        # Get user context from context variables
        user = current_user.get()
        request_id_val = request_id.get()
        
        # Base log structure
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add user context if available
        if user:
            log_data['user_id'] = user.get('id')
            log_data['user_email'] = user.get('email')
            log_data['user_role'] = user.get('role')
        
        # Add request context if available
        if request_id_val:
            log_data['request_id'] = request_id_val
        
        # Add extra fields if provided
        if hasattr(record, 'extra') and record.extra:
            log_data.update(record.extra)
        
        # Add exception details if available
        if record.exc_info:
            log_data['exception'] = {
                'type': type(record.exc_info[1]).__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_data, default=str)


class AuditLogger:
    """Specialized logger for audit events."""
    
    def __init__(self, name: str = 'audit'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Create handler with structured formatter
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        self.logger.propagate = False
    
    def log_user_action(self, action: str, details: Dict[str, Any] = None, 
                     resource_id: str = None, result: str = None):
        """Log user action for audit trail."""
        extra_data = {
            'event_type': 'user_action',
            'action': action,
            'resource_id': resource_id,
            'result': result,
        }
        
        if details:
            extra_data.update(details)
        
        self.logger.info(f"User action: {action}", extra=extra_data)
    
    def log_auth_event(self, event_type: str, email: str, role: str = None, 
                   success: bool = True, reason: str = None):
        """Log authentication events."""
        extra_data = {
            'event_type': 'auth',
            'auth_event': event_type,
            'email': email,
            'role': role,
            'success': success,
        }
        
        if reason:
            extra_data['reason'] = reason
        
        self.logger.info(f"Auth event: {event_type}", extra=extra_data)
    
    def log_permission_check(self, resource: str, user_role: str, 
                       permission: str, granted: bool, reason: str = None):
        """Log RBAC permission checks."""
        extra_data = {
            'event_type': 'permission_check',
            'resource': resource,
            'user_role': user_role,
            'permission': permission,
            'granted': granted,
        }
        
        if reason:
            extra_data['reason'] = reason
        
        self.logger.info(f"Permission check: {permission} for {resource}", extra=extra_data)
    
    def log_api_access(self, endpoint: str, method: str, user_id: int = None,
                    status_code: int = None, response_time: float = None):
        """Log API access patterns."""
        extra_data = {
            'event_type': 'api_access',
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code,
            'response_time_ms': response_time * 1000 if response_time else None,
        }
        
        if user_id:
            extra_data['user_id'] = user_id
        
        self.logger.info(f"API access: {method} {endpoint}", extra=extra_data)
    
    def log_security_event(self, event_type: str, details: Dict[str, Any] = None):
        """Log security-related events."""
        extra_data = {
            'event_type': 'security',
            'security_event': event_type,
        }
        
        if details:
            extra_data.update(details)
        
        self.logger.warning(f"Security event: {event_type}", extra=extra_data)


class PerformanceLogger:
    """Specialized logger for performance monitoring."""
    
    def __init__(self, name: str = 'performance'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Create handler with structured formatter
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        self.logger.propagate = False
    
    def log_query_performance(self, agent: str, query: str, 
                           response_time: float, token_count: int = None):
        """Log LLM query performance."""
        extra_data = {
            'event_type': 'query_performance',
            'agent': agent,
            'query_length': len(query),
            'response_time_ms': response_time * 1000,
        }
        
        if token_count is not None:
            extra_data['token_count'] = token_count
        
        self.logger.info(f"Query performance: {agent}", extra=extra_data)
    
    def log_webhook_performance(self, webhook_type: str, url: str, 
                              response_time: float, success: bool = None):
        """Log webhook performance."""
        extra_data = {
            'event_type': 'webhook_performance',
            'webhook_type': webhook_type,
            'url': url,
            'response_time_ms': response_time * 1000,
            'success': success,
        }
        
        self.logger.info(f"Webhook performance: {webhook_type}", extra=extra_data)


class SecurityLogger:
    """Specialized logger for security events."""
    
    def __init__(self, name: str = 'security'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.WARNING)
        
        # Create handler with structured formatter
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        self.logger.propagate = False
    
    def log_failed_login(self, email: str, reason: str = None, ip_address: str = None):
        """Log failed login attempts."""
        extra_data = {
            'event_type': 'failed_login',
            'email': email,
        }
        
        if reason:
            extra_data['reason'] = reason
        
        if ip_address:
            extra_data['ip_address'] = ip_address
        
        self.logger.warning(f"Failed login attempt for {email}", extra=extra_data)
    
    def log_suspicious_activity(self, activity: str, details: Dict[str, Any] = None):
        """Log suspicious activities."""
        extra_data = {
            'event_type': 'suspicious_activity',
            'activity': activity,
        }
        
        if details:
            extra_data.update(details)
        
        self.logger.warning(f"Suspicious activity: {activity}", extra=extra_data)


def setup_logging():
    """Configure root logger with structured formatting."""
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add structured handler
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)
    
    # Set specific loggers to appropriate levels
    logging.getLogger('audit').setLevel(logging.INFO)
    logging.getLogger('performance').setLevel(logging.INFO)
    logging.getLogger('security').setLevel(logging.WARNING)
    logging.getLogger('power_automate').setLevel(logging.INFO)


# Convenience functions for common logging patterns
def get_audit_logger() -> AuditLogger:
    return AuditLogger()


def get_performance_logger() -> PerformanceLogger:
    return PerformanceLogger()


def get_security_logger() -> SecurityLogger:
    return SecurityLogger()


def set_user_context(user_data: Dict[str, Any]):
    """Set user context for current request."""
    current_user.set(user_data)


def set_request_context(request_id_val: str):
    """Set request context for current request."""
    request_id.set(request_id_val)


def clear_context():
    """Clear user and request context."""
    current_user.set(None)
    request_id.set(None)
