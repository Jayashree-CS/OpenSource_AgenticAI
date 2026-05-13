import React, { useState } from 'react';
import { employeeAPI } from '../api/employee';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';
import { formatAssetStatus } from '../utils/assetStatus';

export default function MyAssets() {
  const { toast } = useToast();
  const list = useApi(() => employeeAPI.listAssets(), []);
  const [form, setForm] = useState({ asset_type: 'laptop', reason: '' });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await employeeAPI.createAsset(form);
      toast('Asset request submitted', { type: 'success' });
      setForm({ asset_type: 'laptop', reason: '' });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to submit asset request', { type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="My Assets" subtitle="Request and track company assets" />

      <section style={{ marginBottom: 24 }}>
        <h3>Request New Asset</h3>
        <form
          onSubmit={submit}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}
        >
          <label>
            <div>Asset type</div>
            <select
              value={form.asset_type}
              onChange={(e) => setForm({ ...form, asset_type: e.target.value })}
              style={inputStyle}
            >
              <option value="laptop">Laptop</option>
              <option value="monitor">Monitor</option>
              <option value="keyboard">Keyboard</option>
              <option value="mouse">Mouse</option>
              <option value="headset">Headset</option>
            </select>
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            <div>Reason</div>
            <input
              type="text"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Why do you need this asset?"
              style={inputStyle}
            />
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" disabled={submitting} style={primaryBtn}>
              {submitting ? 'Submitting…' : 'Request Asset'}
            </button>
          </div>
        </form>
      </section>

      <section>
        <h3>My Asset Requests</h3>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
        {!list.loading && !list.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'asset_type', label: 'Asset' },
              {
                key: 'status',
                label: 'Status',
                render: (row) => formatAssetStatus(row),
              },
              { key: 'reason', label: 'Reason' },
              { key: 'created_at', label: 'Created' },
            ]}
            rows={list.data || []}
            emptyMessage="No asset requests yet"
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
