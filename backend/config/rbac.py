"""
rbac.py

Centralized Role-Based Access Control (RBAC) configuration.

Final role model:
- employee
- manager  
- it_team
- admin

REMOVED: hr_team (completely removed)
"""

from typing import Dict, List, Set
from enum import Enum


class Role(Enum):
    """Final role enumeration."""
    EMPLOYEE = "employee"
    MANAGER = "manager"
    IT_TEAM = "it_team"
    ADMIN = "admin"


class Permission(Enum):
    """Permission enumeration for fine-grained access control."""
    
    # Dashboard permissions
    VIEW_LEAVE_DASHBOARD = "view_leave_dashboard"
    VIEW_TICKET_DASHBOARD = "view_ticket_dashboard"
    VIEW_ASSET_DASHBOARD = "view_asset_dashboard"
    VIEW_ADMIN_CONSOLE = "view_admin_console"
    VIEW_SYSTEM_LOGS = "view_system_logs"
    
    # Action permissions
    APPROVE_LEAVE = "approve_leave"
    REJECT_LEAVE = "reject_leave"
    APPROVE_TICKET = "approve_ticket"
    REJECT_TICKET = "reject_ticket"
    APPROVE_ASSET = "approve_asset"
    REJECT_ASSET = "reject_asset"
    
    # View permissions
    VIEW_PENDING_APPROVALS = "view_pending_approvals"
    VIEW_TEAM_DATA = "view_team_data"
    VIEW_ALL_DATA = "view_all_data"
    
    # System permissions
    ACCESS_ALL_PAGES = "access_all_pages"
    ACCESS_ALL_COMPONENTS = "access_all_components"


# Role-based permission matrix
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.EMPLOYEE: {
        # Employees can only view their own data
        Permission.VIEW_LEAVE_DASHBOARD,  # For personal leave status
        # No dashboard access, no approval permissions
    },
    
    Role.MANAGER: {
        # Dashboard access
        Permission.VIEW_LEAVE_DASHBOARD,
        Permission.VIEW_TICKET_DASHBOARD,
        Permission.VIEW_ASSET_DASHBOARD,
        Permission.VIEW_PENDING_APPROVALS,
        Permission.VIEW_TEAM_DATA,
        
        # Approval permissions
        Permission.APPROVE_LEAVE,
        Permission.REJECT_LEAVE,
        Permission.APPROVE_TICKET,
        Permission.REJECT_TICKET,
        Permission.APPROVE_ASSET,
        Permission.REJECT_ASSET,
    },
    
    Role.IT_TEAM: {
        # Limited dashboard access
        Permission.VIEW_TICKET_DASHBOARD,
        Permission.VIEW_PENDING_APPROVALS,
        
        # IT-specific approval permissions
        Permission.APPROVE_TICKET,
        Permission.REJECT_TICKET,
        Permission.APPROVE_ASSET,
        Permission.REJECT_ASSET,
    },
    
    Role.ADMIN: {
        # Admin has ALL permissions (superuser)
        Permission.ACCESS_ALL_PAGES,
        Permission.ACCESS_ALL_COMPONENTS,
        Permission.VIEW_LEAVE_DASHBOARD,
        Permission.VIEW_TICKET_DASHBOARD,
        Permission.VIEW_ASSET_DASHBOARD,
        Permission.VIEW_ADMIN_CONSOLE,
        Permission.VIEW_SYSTEM_LOGS,
        Permission.VIEW_PENDING_APPROVALS,
        Permission.VIEW_TEAM_DATA,
        Permission.VIEW_ALL_DATA,
        Permission.APPROVE_LEAVE,
        Permission.REJECT_LEAVE,
        Permission.APPROVE_TICKET,
        Permission.REJECT_TICKET,
        Permission.APPROVE_ASSET,
        Permission.REJECT_ASSET,
    }
}


# Role hierarchy for inheritance
ROLE_HIERARCHY: Dict[Role, List[Role]] = {
    Role.EMPLOYEE: [],
    Role.MANAGER: [Role.EMPLOYEE],
    Role.IT_TEAM: [Role.EMPLOYEE],
    Role.ADMIN: [Role.MANAGER, Role.IT_TEAM, Role.EMPLOYEE],
}


# Frontend route access configuration
ROUTE_ACCESS: Dict[str, Set[Role]] = {
    "/": {Role.EMPLOYEE, Role.MANAGER, Role.IT_TEAM, Role.ADMIN},  # Chat page
    "/dashboard": {Role.MANAGER, Role.ADMIN},  # Main dashboard
    "/leave-dashboard": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "/ticket-dashboard": {Role.MANAGER, Role.IT_TEAM, Role.ADMIN},
    "/asset-dashboard": {Role.MANAGER, Role.ADMIN},
    "/admin": {Role.ADMIN},
    "/system-logs": {Role.ADMIN},
}


# Sidebar component visibility
SIDEBAR_VISIBILITY: Dict[str, Set[Role]] = {
    "chat": {Role.EMPLOYEE, Role.MANAGER, Role.IT_TEAM, Role.ADMIN},
    "dashboard": {Role.MANAGER, Role.ADMIN},
    "leave-dashboard": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "ticket-dashboard": {Role.MANAGER, Role.IT_TEAM, Role.ADMIN},
    "asset-dashboard": {Role.MANAGER, Role.ADMIN},
    "admin-console": {Role.ADMIN},
    "system-logs": {Role.ADMIN},
}


# API endpoint permissions
API_PERMISSIONS: Dict[str, Set[Permission]] = {
    # Leave endpoints
    "/api/leave/apply": {Permission.VIEW_LEAVE_DASHBOARD},
    "/api/leave/approve": {Permission.APPROVE_LEAVE},
    "/api/leave/reject": {Permission.REJECT_LEAVE},
    "/api/leave/pending": {Permission.VIEW_PENDING_APPROVALS},
    
    # Ticket endpoints
    "/api/ticket/create": {Permission.VIEW_TICKET_DASHBOARD},
    "/api/ticket/update": {Permission.APPROVE_TICKET},
    "/api/ticket/all": {Permission.VIEW_ALL_DATA},
    
    # Asset endpoints
    "/api/asset/request": {Permission.VIEW_ASSET_DASHBOARD},
    "/api/asset/approve": {Permission.APPROVE_ASSET},
    "/api/asset/reject": {Permission.REJECT_ASSET},
    
    # Admin endpoints
    "/api/admin/logs": {Permission.VIEW_SYSTEM_LOGS},
    "/api/admin/users": {Permission.VIEW_ALL_DATA},
}


_ROLE_ALIASES = {
    "it": "it_team",
    "itteam": "it_team",
    "it-team": "it_team",
    "it team": "it_team",
    "hr": "employee",
    "hr_team": "employee",
}


def _canonical_role(user_role: str | None) -> str:
    """Normalize raw DB role strings to canonical Role values.

    Legacy rows were seeded with ``role="it"``; the canonical value is
    ``it_team``. This helper keeps every ``can_*`` / ``is_*`` check below
    working even if a caller passes the raw DB value instead of the
    auth-dependency-normalized value.
    """
    r = (user_role or "").strip().lower()
    return _ROLE_ALIASES.get(r, r)


class RBACService:
    """Centralized RBAC service for permission checking."""
    
    @staticmethod
    def has_permission(user_role: str, permission: Permission) -> bool:
        """
        Check if user role has specific permission.
        
        Args:
            user_role: User role string
            permission: Permission to check
            
        Returns:
            True if user has permission
        """
        try:
            role = Role(_canonical_role(user_role))
            return permission in ROLE_PERMISSIONS.get(role, set())
        except ValueError:
            return False
    
    @staticmethod
    def has_route_access(user_role: str, route: str) -> bool:
        """
        Check if user role can access specific route.
        
        Args:
            user_role: User role string
            route: Route path
            
        Returns:
            True if user can access route
        """
        try:
            role = Role(user_role)
            return role in ROUTE_ACCESS.get(route, set())
        except ValueError:
            return False
    
    @staticmethod
    def can_view_sidebar_component(user_role: str, component: str) -> bool:
        """
        Check if user role can view sidebar component.
        
        Args:
            user_role: User role string
            component: Component identifier
            
        Returns:
            True if user can view component
        """
        try:
            role = Role(user_role)
            return role in SIDEBAR_VISIBILITY.get(component, set())
        except ValueError:
            return False
    
    @staticmethod
    def has_api_permission(user_role: str, endpoint: str) -> bool:
        """
        Check if user role can access API endpoint.
        
        Args:
            user_role: User role string
            endpoint: API endpoint path
            
        Returns:
            True if user can access endpoint
        """
        try:
            role = Role(user_role)
            required_permissions = API_PERMISSIONS.get(endpoint, set())
            return any(
                permission in ROLE_PERMISSIONS.get(role, set())
                for permission in required_permissions
            )
        except ValueError:
            return False
    
    @staticmethod
    def get_user_permissions(user_role: str) -> Set[Permission]:
        """
        Get all permissions for a user role.
        
        Args:
            user_role: User role string
            
        Returns:
            Set of permissions
        """
        try:
            role = Role(user_role)
            return ROLE_PERMISSIONS.get(role, set())
        except ValueError:
            return set()
    
    @staticmethod
    def get_accessible_routes(user_role: str) -> List[str]:
        """
        Get all routes accessible to user role.
        
        Args:
            user_role: User role string
            
        Returns:
            List of accessible routes
        """
        try:
            role = Role(user_role)
            return [
                route for route, roles in ROUTE_ACCESS.items()
                if role in roles
            ]
        except ValueError:
            return []
    
    @staticmethod
    def get_visible_sidebar_components(user_role: str) -> List[str]:
        """
        Get all visible sidebar components for user role.
        
        Args:
            user_role: User role string
            
        Returns:
            List of visible components
        """
        try:
            role = Role(user_role)
            return [
                component for component, roles in SIDEBAR_VISIBILITY.items()
                if role in roles
            ]
        except ValueError:
            return []
    
    @staticmethod
    def is_valid_role(role: str) -> bool:
        """
        Check if role is valid in the current system.
        
        Args:
            role: Role string to validate
            
        Returns:
            True if role is valid
        """
        return role in [r.value for r in Role]
    
    @staticmethod
    def get_all_roles() -> List[str]:
        """
        Get all valid roles in the system.
        
        Returns:
            List of role strings
        """
        return [role.value for role in Role]


# Global RBAC service instance
rbac_action = RBACService()


# Helper functions for common checks
def can_approve_leave(user_role: str) -> bool:
    """Check if user can approve leave requests."""
    return rbac_action.has_permission(user_role, Permission.APPROVE_LEAVE)


def can_approve_ticket(user_role: str) -> bool:
    """Check if user can approve IT tickets."""
    return rbac_action.has_permission(user_role, Permission.APPROVE_TICKET)


def can_approve_asset(user_role: str) -> bool:
    """Check if user can approve asset requests."""
    return rbac_action.has_permission(user_role, Permission.APPROVE_ASSET)


def can_view_system_logs(user_role: str) -> bool:
    """Check if user can view system logs."""
    return rbac_action.has_permission(user_role, Permission.VIEW_SYSTEM_LOGS)


def is_admin(user_role: str) -> bool:
    """Check if user is admin."""
    return _canonical_role(user_role) == Role.ADMIN.value


def is_manager(user_role: str) -> bool:
    """Check if user is manager."""
    return _canonical_role(user_role) == Role.MANAGER.value


def is_it_team(user_role: str) -> bool:
    """Check if user is IT team."""
    return _canonical_role(user_role) == Role.IT_TEAM.value


def is_employee(user_role: str) -> bool:
    """Check if user is employee."""
    return _canonical_role(user_role) == Role.EMPLOYEE.value
