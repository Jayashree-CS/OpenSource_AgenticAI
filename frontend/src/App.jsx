import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { isValidRole, ROLES } from './utils/rbac';
import { ROUTES, getDefaultRouteForRole } from './config/routesConfig';

import { ToastProvider } from './components/Toast';
import CommonLayout from './layouts/CommonLayout';
import EmployeeLayout from './layouts/EmployeeLayout';
import ManagerLayout from './layouts/ManagerLayout';
import ITLayout from './layouts/ITLayout';
import AdminLayout from './layouts/AdminLayout';

import './index.css';

function RequireAuth({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const role = ((user.role || ROLES.EMPLOYEE) + '').toLowerCase();
  const normalized = isValidRole(role) ? role : ROLES.EMPLOYEE;

  if (roles && !roles.includes(normalized)) {
    return <Navigate to={getDefaultRouteForRole(normalized)} replace />;
  }
  return children;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) {
    const role = ((user.role || ROLES.EMPLOYEE) + '').toLowerCase();
    return <Navigate to={getDefaultRouteForRole(role)} replace />;
  }
  return children;
}

function renderRoutes(routeList) {
  return (routeList || []).map((r) => {
    const Element = r.element;
    return (
      <Route
        key={r.path}
        path={r.path}
        element={
          <RequireAuth roles={r.roles}>
            <Element />
          </RequireAuth>
        }
      />
    );
  });
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            {(ROUTES.public || []).map((r) => {
              const Element = r.element;
              return (
                <Route
                  key={r.path}
                  path={r.path}
                  element={
                    <PublicRoute>
                      <Element />
                    </PublicRoute>
                  }
                />
              );
            })}

            <Route element={<RequireAuth><CommonLayout /></RequireAuth>}>
              {renderRoutes(ROUTES.common)}
            </Route>

            <Route
              element={
                <RequireAuth roles={[ROLES.EMPLOYEE, ROLES.ADMIN]}>
                  <EmployeeLayout />
                </RequireAuth>
              }
            >
              {renderRoutes(ROUTES.employee)}
            </Route>

            <Route
              element={
                <RequireAuth roles={[ROLES.MANAGER, ROLES.ADMIN]}>
                  <ManagerLayout />
                </RequireAuth>
              }
            >
              {renderRoutes(ROUTES.manager)}
            </Route>

            <Route
              element={
                <RequireAuth roles={[ROLES.IT_TEAM, ROLES.ADMIN]}>
                  <ITLayout />
                </RequireAuth>
              }
            >
              {renderRoutes(ROUTES.it)}
            </Route>

            <Route
              element={
                <RequireAuth roles={[ROLES.ADMIN]}>
                  <AdminLayout />
                </RequireAuth>
              }
            >
              {renderRoutes(ROUTES.admin)}
            </Route>

            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
