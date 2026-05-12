import React, { useState } from 'react';
import { adminApi } from '../api/admin';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';
import { useAuth } from '../context/AuthContext';
import { ALL_ROLES } from '../utils/rbac';

export default function UserManagement() {
  const { toast } = useToast();
  const { user: currentUser } = useAuth();
  const list = useApi(() => adminApi.users(), []);
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    role: 'employee',
  });
  const [submitting, setSubmitting] = useState(false);
  const [busy, setBusy] = useState({});

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email || !form.password) {
      toast('Email and password are required', { type: 'error' });
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.createUser(form);
      toast('User created', { type: 'success' });
      setForm({ name: '', email: '', password: '', role: 'employee' });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to create user', { type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const deleteUser = async (row) => {
    if (currentUser?.id === row.id) {
      toast('You cannot delete your own account.', { type: 'error' });
      return;
    }
    // eslint-disable-next-line no-alert
    const ok = window.confirm(
      `Delete user "${row.name || row.email}"?\n\n` +
      'This will remove their account and their leave/ticket/asset history. ' +
      'This action cannot be undone.'
    );
    if (!ok) return;
    setBusy((b) => ({ ...b, [row.id]: true }));
    try {
      await adminApi.deleteUser(row.id);
      toast('User deleted', { type: 'success' });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to delete user', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [row.id]: false }));
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="User Management" subtitle="Create and manage employees" />

      <section style={{ marginBottom: 24 }}>
        <h3>Create User</h3>
        <form
          onSubmit={submit}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}
        >
          <label>
            <div>Name</div>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
          </label>
          <label>
            <div>Email</div>
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={inputStyle} />
          </label>
          <label>
            <div>Password</div>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              style={inputStyle}
            />
          </label>
          <label>
            <div>Role</div>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} style={inputStyle}>
              {ALL_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" disabled={submitting} style={primaryBtn}>
              {submitting ? 'Creating…' : 'Create User'}
            </button>
          </div>
        </form>
      </section>

      <section>
        <h3>All Users</h3>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
        {!list.loading && !list.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID', render: (r) => `#${r.id}` },
              { key: 'name', label: 'Name', render: (r) => r.name || '—' },
              { key: 'email', label: 'Email', render: (r) => r.email || '—' },
              {
                key: 'role',
                label: 'Role',
                render: (r) => (
                  <span style={{
                    display: 'inline-block',
                    padding: '2px 10px',
                    borderRadius: 999,
                    background: 'rgba(37, 99, 235, 0.1)',
                    color: '#1e40af',
                    fontWeight: 600,
                    fontSize: 12,
                    textTransform: 'capitalize',
                  }}>
                    {r.role}
                  </span>
                ),
              },
              {
                key: '_act',
                label: 'Actions',
                render: (r) => (
                  <button
                    onClick={() => deleteUser(r)}
                    disabled={busy[r.id] || currentUser?.id === r.id}
                    style={{
                      padding: '6px 10px',
                      borderRadius: 8,
                      border: '1px solid #fecaca',
                      background: currentUser?.id === r.id ? '#f3f4f6' : '#fef2f2',
                      color: currentUser?.id === r.id ? '#9ca3af' : '#b91c1c',
                      fontWeight: 600,
                      cursor: currentUser?.id === r.id ? 'not-allowed' : 'pointer',
                    }}
                    title={currentUser?.id === r.id ? 'You cannot delete yourself' : 'Delete user'}
                  >
                    {busy[r.id] ? 'Deleting…' : 'Delete'}
                  </button>
                ),
              },
            ]}
            rows={list.data || []}
            emptyMessage="No users"
          />
        )}
      </section>
    </div>
  );
}

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 8,
  border: '1px solid var(--border,#d1d5db)',
  background: 'transparent',
  color: 'inherit',
};
const primaryBtn = {
  padding: '10px 16px',
  borderRadius: 10,
  border: 'none',
  background: '#2563eb',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
};
