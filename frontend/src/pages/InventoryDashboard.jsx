import React, { useState } from 'react';
import { itAPI } from '../api/it';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

export default function InventoryDashboard() {
  const { toast } = useToast();
  const list = useApi(() => itAPI.inventory(), []);
  const [form, setForm] = useState({ asset_type: '', total_quantity: 0, available_quantity: 0 });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.asset_type.trim()) {
      toast('Asset type is required', { type: 'error' });
      return;
    }
    setSubmitting(true);
    try {
      await itAPI.upsertInventory({
        asset_type: form.asset_type.trim(),
        total_quantity: Number(form.total_quantity) || 0,
        available_quantity: Number(form.available_quantity) || 0,
      });
      toast('Inventory updated', { type: 'success' });
      setForm({ asset_type: '', total_quantity: 0, available_quantity: 0 });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Failed to save inventory', { type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Inventory" subtitle="Manage available hardware stock" />

      <section style={{ marginBottom: 24 }}>
        <h3>Add / Update Inventory</h3>
        <form
          onSubmit={submit}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}
        >
          <label>
            <div>Asset type</div>
            <input
              value={form.asset_type}
              onChange={(e) => setForm({ ...form, asset_type: e.target.value })}
              placeholder="e.g. laptop"
              style={inputStyle}
            />
          </label>
          <label>
            <div>Total quantity</div>
            <input
              type="number"
              min={0}
              value={form.total_quantity}
              onChange={(e) => setForm({ ...form, total_quantity: e.target.value })}
              style={inputStyle}
            />
          </label>
          <label>
            <div>Available quantity</div>
            <input
              type="number"
              min={0}
              value={form.available_quantity}
              onChange={(e) => setForm({ ...form, available_quantity: e.target.value })}
              style={inputStyle}
            />
          </label>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" disabled={submitting} style={primaryBtn}>
              {submitting ? 'Saving…' : 'Save Inventory'}
            </button>
          </div>
        </form>
      </section>

      <section>
        <h3>Inventory</h3>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
        {!list.loading && !list.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'asset_type', label: 'Asset' },
              { key: 'total_quantity', label: 'Total' },
              { key: 'available_quantity', label: 'Available' },
            ]}
            rows={list.data || []}
            emptyMessage="No inventory items"
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
