import React from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AppSidebar from '../components/AppSidebar';

export default function EmployeeLayout() {
  const { user, logout } = useAuth();

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-page)' }}>
      <AppSidebar user={user} onLogout={logout} />
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>
    </div>
  );
}
