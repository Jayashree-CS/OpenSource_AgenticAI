import { ROLES } from '../utils/rbac';

import ChatPage from '../pages/ChatPage';
import AuthPage from '../pages/AuthPage';

import EmployeeDashboard from '../pages/EmployeeDashboard';
import ManagerDashboard from '../pages/ManagerDashboard';
import ITDashboard from '../pages/ITDashboard';
import AdminDashboard from '../pages/AdminDashboard';

import MyLeaves from '../pages/MyLeaves';
import MyTickets from '../pages/MyTickets';
import MyAssets from '../pages/MyAssets';

import InventoryDashboard from '../pages/InventoryDashboard';
import ApprovalHistory from '../pages/ApprovalHistory';
import TicketResolution from '../pages/TicketResolution';

import SystemLogs from '../pages/SystemLogs';
import UserManagement from '../pages/UserManagement';
import Analytics from '../pages/Analytics';

export const ROUTES = {
  public: [{ path: '/login', element: AuthPage }],

  common: [{ path: '/chat', element: ChatPage, roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.IT_TEAM, ROLES.ADMIN] }],

  employee: [
    { path: '/employee', element: EmployeeDashboard, roles: [ROLES.EMPLOYEE, ROLES.ADMIN] },
    { path: '/employee/leaves', element: MyLeaves, roles: [ROLES.EMPLOYEE, ROLES.ADMIN] },
    { path: '/employee/tickets', element: MyTickets, roles: [ROLES.EMPLOYEE, ROLES.ADMIN] },
    { path: '/employee/assets', element: MyAssets, roles: [ROLES.EMPLOYEE, ROLES.ADMIN] },
  ],

  manager: [
    { path: '/manager', element: ManagerDashboard, roles: [ROLES.MANAGER, ROLES.ADMIN] },
    { path: '/manager/approvals', element: ApprovalHistory, roles: [ROLES.MANAGER, ROLES.ADMIN] },
  ],

  it: [
    { path: '/it', element: ITDashboard, roles: [ROLES.IT_TEAM, ROLES.ADMIN] },
    { path: '/it/inventory', element: InventoryDashboard, roles: [ROLES.IT_TEAM, ROLES.ADMIN] },
    { path: '/it/tickets', element: TicketResolution, roles: [ROLES.IT_TEAM, ROLES.ADMIN] },
  ],

  admin: [
    { path: '/admin', element: AdminDashboard, roles: [ROLES.ADMIN] },
    { path: '/admin/system-logs', element: SystemLogs, roles: [ROLES.ADMIN] },
    { path: '/admin/users', element: UserManagement, roles: [ROLES.ADMIN] },
    { path: '/admin/analytics', element: Analytics, roles: [ROLES.ADMIN] },
  ],
};

export function getDefaultRouteForRole(role) {
  switch (role) {
    case ROLES.EMPLOYEE:
      return '/employee';
    case ROLES.MANAGER:
      return '/manager';
    case ROLES.IT_TEAM:
      return '/it';
    case ROLES.ADMIN:
      return '/admin';
    default:
      return '/chat';
  }
}
