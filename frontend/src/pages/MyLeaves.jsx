import React, { useState } from 'react';
import { employeeAPI } from '../api/employee';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

export default function MyLeaves() {
  const { toast } = useToast();
  const history = useApi(() => employeeAPI.leaveHistory(), []);
  const balance = useApi(() => employeeAPI.leaveBalance(), []);

  const [form, setForm] = useState({ start_date: '', end_date: '', reason: '', leave_type: 'casual' });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.start_date || !form.end_date) {
      toast('Please select start and end dates', { type: 'error' });
      return;
    }
    setSubmitting(true);
    try {
      await employeeAPI.applyLeave(form);
      toast('Leave applied successfully', { type: 'success' });
      setForm({ start_date: '', end_date: '', reason: '', leave_type: 'casual' });
      history.refetch();
      balance.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to apply leave', { type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="My Leaves" subtitle="Apply for leave and review your history" />

      <section style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>Leave Balance</h3>
        {balance.loading && <Loading />}
        {balance.error && <ErrorState message={balance.error} onRetry={balance.refetch} />}
        {!balance.loading && !balance.error && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {Object.entries(balance.data || {}).map(([k, v]) => {
              // Backend returns { sick: { total, used, remaining }, ... }
              const isObj = v && typeof v === 'object';
              const remaining = isObj ? (v.remaining ?? 0) : v;
              const total = isObj ? (v.total ?? null) : null;
              const used = isObj ? (v.used ?? null) : null;
              return (
                <div
                  key={k}
                  style={{
                    padding: 14,
                    borderRadius: 12,
                    border: '1px solid var(--border,#e5e7eb)',
                    minWidth: 180,
                  }}
                >
                  <div style={{ textTransform: 'capitalize', color: 'var(--text-muted)', fontSize: 13 }}>
                    {k} leave
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>
                    {String(remaining)}
                    {total != null && <span style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 500 }}> / {total}</span>}
                  </div>
                  {used != null && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      Used: {used}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section style={{ marginBottom: 24 }}>
        <h3>Apply for Leave</h3>
        <form
          onSubmit={submit}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}
        >
          <label>
            <div>Start date</div>
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
              style={inputStyle}
            />
          </label>
          <label>
            <div>End date</div>
            <input
              type="date"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
              style={inputStyle}
            />
          </label>
          <label>
            <div>Type</div>
            <select
              value={form.leave_type}
              onChange={(e) => setForm({ ...form, leave_type: e.target.value })}
              style={inputStyle}
            >
              <option value="casual">Casual</option>
              <option value="sick">Sick</option>
              <option value="earned">Earned</option>
            </select>
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            <div>Reason</div>
            <input
              type="text"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Optional reason"
              style={inputStyle}
            />
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" disabled={submitting} style={primaryBtn}>
              {submitting ? 'Submitting…' : 'Apply Leave'}
            </button>
          </div>
        </form>
      </section>

      <section>
        <h3>History</h3>
        {history.loading && <Loading />}
        {history.error && <ErrorState message={history.error} onRetry={history.refetch} />}
        {!history.loading && !history.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID', render: (r) => `#${r.id ?? '—'}` },
              {
                key: 'leave_type',
                label: 'Type',
                render: (r) =>
                  typeof r.leave_type === 'string'
                    ? r.leave_type.charAt(0).toUpperCase() + r.leave_type.slice(1)
                    : '—',
              },
              { key: 'start_date', label: 'From', render: (r) => formatDate(r.start_date) },
              { key: 'end_date', label: 'To', render: (r) => formatDate(r.end_date) },
              {
                key: 'status',
                label: 'Status',
                render: (r) => <StatusPill value={r.status} />,
              },
              {
                key: 'reason',
                label: 'Reason',
                render: (r) => (typeof r.reason === 'string' && r.reason.trim()) ? r.reason : '—',
              },
            ]}
            rows={history.data || []}
            emptyMessage="No leave records yet"
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

function formatDate(value) {
  if (!value) return '—';
  if (typeof value !== 'string' && !(value instanceof Date)) return '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toISOString().slice(0, 10);
}

function StatusPill({ value }) {
  const status = String(value || '').toLowerCase();
  const palette = {
    pending_manager: { bg: '#fef3c7', fg: '#92400e', label: 'Pending Manager' },
    approved:        { bg: '#dcfce7', fg: '#166534', label: 'Approved' },
    rejected:        { bg: '#fee2e2', fg: '#991b1b', label: 'Rejected' },
    cancelled:       { bg: '#f3f4f6', fg: '#374151', label: 'Cancelled' },
    open:            { bg: '#dbeafe', fg: '#1e40af', label: 'Open' },
    in_progress:     { bg: '#fef3c7', fg: '#92400e', label: 'In Progress' },
    closed:          { bg: '#dcfce7', fg: '#166534', label: 'Closed' },
  };
  const p = palette[status] || { bg: '#f3f4f6', fg: '#374151', label: status || '—' };
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 999,
      background: p.bg,
      color: p.fg,
      fontSize: 12,
      fontWeight: 600,
    }}>
      {p.label}
    </span>
  );
}
