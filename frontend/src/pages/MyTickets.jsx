import React, { useState } from 'react';
import { employeeAPI } from '../api/employee';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

export default function MyTickets() {
  const { toast } = useToast();
  const list = useApi(() => employeeAPI.listTickets(), []);
  const [form, setForm] = useState({ issue_type: 'general', description: '', priority: 'medium' });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.description.trim()) {
      toast('Please describe the issue', { type: 'error' });
      return;
    }
    setSubmitting(true);
    try {
      const res = await employeeAPI.createTicket(form);
      if (res?.duplicate_ticket) {
        toast('A similar open ticket already exists.', { type: 'info' });
      } else {
        toast('Ticket created', { type: 'success' });
      }
      setForm({ issue_type: 'general', description: '', priority: 'medium' });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to create ticket', { type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="My Tickets" subtitle="Raise IT support tickets and track status" />

      <section style={{ marginBottom: 24 }}>
        <h3>Raise New Ticket</h3>
        <form
          onSubmit={submit}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}
        >
          <label>
            <div>Issue type</div>
            <select
              value={form.issue_type}
              onChange={(e) => setForm({ ...form, issue_type: e.target.value })}
              style={inputStyle}
            >
              <option value="general">General</option>
              <option value="vpn">VPN</option>
              <option value="hardware">Hardware</option>
              <option value="software">Software</option>
              <option value="access">Access</option>
            </select>
          </label>
          <label>
            <div>Priority</div>
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              style={inputStyle}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            <div>Description</div>
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Describe the issue"
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" disabled={submitting} style={primaryBtn}>
              {submitting ? 'Submitting…' : 'Create Ticket'}
            </button>
          </div>
        </form>
      </section>

      <section>
        <h3>My Tickets</h3>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
        {!list.loading && !list.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'issue_type', label: 'Type' },
              { key: 'priority', label: 'Priority' },
              { key: 'status', label: 'Status' },
              { key: 'description', label: 'Description' },
              { key: 'created_at', label: 'Created' },
            ]}
            rows={list.data || []}
            emptyMessage="No tickets yet"
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
