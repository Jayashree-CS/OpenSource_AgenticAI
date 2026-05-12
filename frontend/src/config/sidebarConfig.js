import { ROLES } from '../utils/rbac';

// Sidebar items are scoped strictly to the role they belong to. Admins get
// only admin/operational tools — no personal employee pages such as "My
// Leaves" / "My Tickets" / "My Assets" / "Employee Dashboard".
export const SIDEBAR_ITEMS = [
  { key: 'chat', label: 'Chat', path: '/chat', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.IT_TEAM, ROLES.ADMIN] },

  { key: 'emp_home', label: 'Employee Dashboard', path: '/employee', roles: [ROLES.EMPLOYEE] },
  { key: 'emp_leaves', label: 'My Leaves', path: '/employee/leaves', roles: [ROLES.EMPLOYEE] },
  { key: 'emp_tickets', label: 'My Tickets', path: '/employee/tickets', roles: [ROLES.EMPLOYEE] },
  { key: 'emp_assets', label: 'My Assets', path: '/employee/assets', roles: [ROLES.EMPLOYEE] },

  { key: 'mgr_home', label: 'Manager Dashboard', path: '/manager', roles: [ROLES.MANAGER] },
  { key: 'mgr_approvals', label: 'Approval History', path: '/manager/approvals', roles: [ROLES.MANAGER] },

  { key: 'it_home', label: 'IT Dashboard', path: '/it', roles: [ROLES.IT_TEAM] },
  { key: 'it_tickets', label: 'Ticket Resolution', path: '/it/tickets', roles: [ROLES.IT_TEAM, ROLES.ADMIN] },
  { key: 'it_inventory', label: 'Inventory', path: '/it/inventory', roles: [ROLES.IT_TEAM, ROLES.ADMIN] },

  { key: 'admin_home', label: 'Admin Dashboard', path: '/admin', roles: [ROLES.ADMIN] },
  { key: 'admin_users', label: 'User Management', path: '/admin/users', roles: [ROLES.ADMIN] },
  { key: 'admin_logs', label: 'System Logs', path: '/admin/system-logs', roles: [ROLES.ADMIN] },
  { key: 'admin_analytics', label: 'Analytics', path: '/admin/analytics', roles: [ROLES.ADMIN] },
  { key: 'admin_approvals', label: 'Approvals', path: '/manager/approvals', roles: [ROLES.ADMIN] },
];

export function getSidebarItemsForRole(role) {
  const r = (role || '').toLowerCase();
  return SIDEBAR_ITEMS.filter((i) => i.roles.includes(r));
}
