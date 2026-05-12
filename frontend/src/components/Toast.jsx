import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

const ToastCtx = createContext({ toast: () => {} });

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);

  const remove = useCallback((id) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message, opts = {}) => {
      const id = Math.random().toString(36).slice(2);
      const item = {
        id,
        message,
        type: opts.type || 'info', // info | success | error
        duration: opts.duration ?? 3500,
      };
      setItems((prev) => [...prev, item]);
      if (item.duration > 0) {
        setTimeout(() => remove(id), item.duration);
      }
      return id;
    },
    [remove]
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div
        style={{
          position: 'fixed',
          top: 16,
          right: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 9999,
          maxWidth: 360,
        }}
      >
        {items.map((t) => (
          <div
            key={t.id}
            onClick={() => remove(t.id)}
            style={{
              padding: '10px 14px',
              borderRadius: 10,
              color: '#fff',
              background:
                t.type === 'success'
                  ? '#16a34a'
                  : t.type === 'error'
                  ? '#dc2626'
                  : '#2563eb',
              boxShadow: '0 6px 18px rgba(0,0,0,0.18)',
              cursor: 'pointer',
              fontSize: 14,
            }}
            role="status"
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

export default ToastProvider;
