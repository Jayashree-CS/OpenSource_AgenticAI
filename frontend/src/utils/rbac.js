/**
 * rbac.js
 *
 * Canonical RBAC configuration for the frontend, fully synchronized with the
 * backend `/api/{employee,manager,it,admin}` namespaces. Legacy routes have
 * been removed; only the canonical role-scoped routes are recognized.
 */

export const ROLES = {
  EMPLOYEE: 'employee',
  MANAGER: 'manager',
  IT_TEAM: 'it_team',
  ADMIN: 'admin',
};

export const ALL_ROLES = [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.IT_TEAM, ROLES.ADMIN];

// Role inheritance: admin sees everything, others are siloed by role.
export const ROLE_HIERARCHY = {
  [ROLES.EMPLOYEE]: [ROLES.EMPLOYEE],
  [ROLES.MANAGER]: [ROLES.MANAGER],
  [ROLES.IT_TEAM]: [ROLES.IT_TEAM],
  [ROLES.ADMIN]: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.IT_TEAM, ROLES.ADMIN],
};

// Canonical route prefixes per role (anything starting with these is allowed).
export const ROLE_ROUTE_PREFIXES = {
  [ROLES.EMPLOYEE]: ['/chat', '/employee'],
  [ROLES.MANAGER]: ['/chat', '/manager'],
  [ROLES.IT_TEAM]: ['/chat', '/it'],
  [ROLES.ADMIN]: ['/chat', '/employee', '/manager', '/it', '/admin'],
};

// Explicit canonical route list per role (used for menu rendering and access checks).
export const ROUTE_ACCESS = {
  [ROLES.EMPLOYEE]: [
    '/chat',
    '/employee',
    '/employee/leaves',
    '/employee/tickets',
    '/employee/assets',
  ],
  [ROLES.MANAGER]: [
    '/chat',
    '/manager',
    '/manager/approvals',
  ],
  [ROLES.IT_TEAM]: [
    '/chat',
    '/it',
    '/it/tickets',
    '/it/inventory',
  ],
  [ROLES.ADMIN]: [
    '/chat',
    '/employee', '/employee/leaves', '/employee/tickets', '/employee/assets',
    '/manager', '/manager/approvals',
    '/it', '/it/tickets', '/it/inventory',
    '/admin', '/admin/users', '/admin/system-logs', '/admin/analytics',
  ],
};

// Component visibility map keyed by canonical component identifiers.
export const COMPONENT_VISIBILITY = {
  chat: ALL_ROLES,
  'employee-dashboard': [ROLES.EMPLOYEE, ROLES.ADMIN],
  'my-leaves': [ROLES.EMPLOYEE, ROLES.ADMIN],
  'my-tickets': [ROLES.EMPLOYEE, ROLES.ADMIN],
  'my-assets': [ROLES.EMPLOYEE, ROLES.ADMIN],
  'manager-dashboard': [ROLES.MANAGER, ROLES.ADMIN],
  'approval-history': [ROLES.MANAGER, ROLES.ADMIN],
  'it-dashboard': [ROLES.IT_TEAM, ROLES.ADMIN],
  'ticket-resolution': [ROLES.IT_TEAM, ROLES.ADMIN],
  'inventory-dashboard': [ROLES.IT_TEAM, ROLES.ADMIN],
  'admin-dashboard': [ROLES.ADMIN],
  'user-management': [ROLES.ADMIN],
  'system-logs': [ROLES.ADMIN],
  'analytics': [ROLES.ADMIN],
};

export const isValidRole = (role) => ALL_ROLES.includes(role);

export const normalizeRole = (role) => {
  const r = (role || '').toLowerCase();
  return isValidRole(r) ? r : ROLES.EMPLOYEE;
};

export const canAccessRoute = (userRole, route) => {
  const role = normalizeRole(userRole);
  const list = ROUTE_ACCESS[role] || [];
  if (list.includes(route)) return true;
  // Prefix-based fallback for nested routes under a canonical namespace.
  return (ROLE_ROUTE_PREFIXES[role] || []).some((p) => route === p || route.startsWith(p + '/'));
};

export const canViewComponent = (userRole, component) => {
  const role = normalizeRole(userRole);
  return (COMPONENT_VISIBILITY[component] || []).includes(role);
};

export const hasRoleOrHigher = (userRole, minimumRole) => {
  const role = normalizeRole(userRole);
  if (role === ROLES.ADMIN) return true;
  return role === minimumRole;
};

export const getRoleDisplayName = (role) => {
  const map = {
    [ROLES.EMPLOYEE]: 'Employee',
    [ROLES.MANAGER]: 'Manager',
    [ROLES.IT_TEAM]: 'IT Team',
    [ROLES.ADMIN]: 'Administrator',
  };
  return map[normalizeRole(role)] || 'Unknown';
};

export default {
  ROLES,
  ALL_ROLES,
  ROLE_HIERARCHY,
  ROLE_ROUTE_PREFIXES,
  ROUTE_ACCESS,
  COMPONENT_VISIBILITY,
  isValidRole,
  normalizeRole,
  canAccessRoute,
  canViewComponent,
  hasRoleOrHigher,
  getRoleDisplayName,
};
