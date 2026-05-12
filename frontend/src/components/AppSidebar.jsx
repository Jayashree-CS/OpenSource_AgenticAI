import React from 'react';
import { NavLink } from 'react-router-dom';
import { getSidebarItemsForRole } from '../config/sidebarConfig';

export default function AppSidebar({ user, onLogout }) {
  const items = getSidebarItemsForRole(user?.role);

  return (
    <aside style={{
      width: 260,
      borderRight: '1px solid var(--border)',
      background: 'var(--bg-card)',
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      padding: 16,
      gap: 12,
    }}>
      <div>
        <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>CopilotAI</div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{(user?.role || '').toUpperCase()}</div>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map((item) => (
          <NavLink
            key={item.key}
            to={item.path}
            style={({ isActive }) => ({
              padding: '10px 10px',
              borderRadius: 10,
              textDecoration: 'none',
              color: 'var(--text-primary)',
              background: isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
              border: '1px solid ' + (isActive ? 'rgba(255,255,255,0.10)' : 'transparent'),
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div style={{ flex: 1 }} />

      <div style={{
        borderTop: '1px solid var(--border)',
        paddingTop: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{user?.email || ''}</div>
        <button
          onClick={onLogout}
          style={{
            width: '100%',
            padding: '10px 12px',
            borderRadius: 10,
            border: '1px solid var(--border)',
            background: 'rgba(255,255,255,0.06)',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
