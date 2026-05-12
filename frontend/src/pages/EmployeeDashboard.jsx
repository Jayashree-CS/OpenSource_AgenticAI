import React from 'react';
import { Link } from 'react-router-dom';
import { employeeAPI } from '../api/employee';
import useApi from '../hooks/useApi';
import { ErrorState, Loading, PageHeader } from '../components/PageState';

export default function EmployeeDashboard() {
  const balance = useApi(() => employeeAPI.leaveBalance(), []);
  const tickets = useApi(() => employeeAPI.listTickets(), []);
  const assets = useApi(() => employeeAPI.listAssets(), []);
  const leaves = useApi(() => employeeAPI.leaveHistory(), []);

  const loading = balance.loading || tickets.loading || assets.loading || leaves.loading;
  const error = balance.error || tickets.error || assets.error || leaves.error;

  const openTickets = (tickets.data || []).filter(
    (t) => (t.status || '').toLowerCase() !== 'closed' && (t.status || '').toLowerCase() !== 'resolved'
  ).length;
  const pendingAssets = (assets.data || []).filter(
    (a) => (a.status || '').toLowerCase().includes('pending')
  ).length;
  const pendingLeaves = (leaves.data || []).filter(
    (l) => (l.status || '').toLowerCase().includes('pending')
  ).length;

  // Backend returns { sick: { total, used, remaining }, casual: {...}, earned: {...} }.
  // Sum the .remaining field across all leave types so the dashboard reflects
  // the live, DB-computed balance after every approval/cancellation.
  const totalBalance = Object.values(balance.data || {}).reduce((acc, v) => {
    if (typeof v === 'number') return acc + v;
    if (v && typeof v === 'object' && typeof v.remaining === 'number') return acc + v.remaining;
    return acc;
  }, 0);
  const totalUsed = Object.values(balance.data || {}).reduce((acc, v) => {
    if (v && typeof v === 'object' && typeof v.used === 'number') return acc + v.used;
    return acc;
  }, 0);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Employee Dashboard" subtitle="Your workspace at a glance" />

      {loading && <Loading />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 24,
            }}
          >
            <Stat label="Leave balance (remaining)" value={totalBalance} />
            <Stat label="Leaves used" value={totalUsed} />
            <Stat label="Pending leaves" value={pendingLeaves} />
            <Stat label="Open tickets" value={openTickets} />
            <Stat label="Pending assets" value={pendingAssets} />
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link to="/employee/leaves" style={linkBtn}>Apply Leave →</Link>
            <Link to="/employee/tickets" style={linkBtn}>Raise Ticket →</Link>
            <Link to="/employee/assets" style={linkBtn}>Request Asset →</Link>
            <Link to="/chat" style={linkBtn}>Ask AI Copilot →</Link>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

const linkBtn = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid var(--border,#e5e7eb)',
  background: 'rgba(0,0,0,0.04)',
  color: 'inherit',
  textDecoration: 'none',
  fontWeight: 600,
};
