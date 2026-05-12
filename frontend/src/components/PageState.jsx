import React from 'react';

export function Loading({ label = 'Loading...' }) {
  return (
    <div style={{ padding: 20, color: 'var(--text-muted)' }}>{label}</div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div
      style={{
        padding: 16,
        borderRadius: 10,
        border: '1px solid #f3c2c2',
        background: '#fdecec',
        color: '#7a1f1f',
        display: 'flex',
        gap: 12,
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <div>{message || 'Something went wrong.'}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '6px 10px',
            borderRadius: 8,
            border: '1px solid #b3393940',
            background: '#fff',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title = 'Nothing here yet', description, action }) {
  return (
    <div
      style={{
        padding: 28,
        borderRadius: 12,
        border: '1px dashed var(--border, #ddd)',
        textAlign: 'center',
        color: 'var(--text-muted)',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>{title}</div>
      {description && <div style={{ fontSize: 14, marginBottom: 12 }}>{description}</div>}
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        marginBottom: 16,
        gap: 12,
        flexWrap: 'wrap',
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: '1.4rem' }}>{title}</h1>
        {subtitle && (
          <div style={{ color: 'var(--text-muted)', marginTop: 4, fontSize: 14 }}>{subtitle}</div>
        )}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8 }}>{actions}</div>}
    </div>
  );
}

export function DataTable({ columns, rows, emptyMessage = 'No records found.' }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title={emptyMessage} />;
  }
  return (
    <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ background: 'rgba(0,0,0,0.04)', textAlign: 'left' }}>
            {columns.map((c) => (
              <th key={c.key} style={{ padding: '10px 12px', fontWeight: 600 }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.id ?? i} style={{ borderTop: '1px solid var(--border,#e5e7eb)' }}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: '10px 12px' }}>
                  {c.render ? c.render(row) : row[c.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default {};
