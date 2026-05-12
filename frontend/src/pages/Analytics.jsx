import React from 'react';
import { adminApi } from '../api/admin';
import useApi from '../hooks/useApi';
import { ErrorState, Loading, PageHeader } from '../components/PageState';

export default function Analytics() {
  const analytics = useApi(() => adminApi.analytics(), []);
  const inventory = useApi(() => adminApi.inventory(), []);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Analytics" subtitle="System-wide metrics" />

      {(analytics.loading || inventory.loading) && <Loading />}
      {(analytics.error || inventory.error) && (
        <ErrorState message={analytics.error || inventory.error} onRetry={() => { analytics.refetch(); inventory.refetch(); }} />
      )}

      {!analytics.loading && !analytics.error && (
        <section style={{ marginBottom: 24 }}>
          <h3>Counts</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            {Object.entries(analytics.data || {}).map(([k, v]) => (
              <div key={k} style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: 13, textTransform: 'capitalize' }}>
                  {k.replace(/_/g, ' ')}
                </div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>{String(v)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {!inventory.loading && !inventory.error && (
        <section>
          <h3>Inventory Stock Levels</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {(inventory.data || []).map((row) => {
              const total = Number(row.total_quantity) || 0;
              const available = Number(row.available_quantity) || 0;
              const used = Math.max(total - available, 0);
              const pct = total > 0 ? Math.round((available / total) * 100) : 0;
              return (
                <div key={row.id} style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{row.asset_type}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
                    {available} available / {used} in use / {total} total
                  </div>
                  <div style={{ height: 8, borderRadius: 999, background: '#e5e7eb', overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: '#2563eb' }} />
                  </div>
                </div>
              );
            })}
            {(inventory.data || []).length === 0 && (
              <div style={{ color: 'var(--text-muted)' }}>No inventory items</div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
