import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './AuthPage.css';

const ROLES = [
  { value: 'employee', label: 'Employee' },
  { value: 'manager', label: 'Manager' },
  { value: 'it_team', label: 'IT Team' },
  { value: 'admin', label: 'Admin' },
];

export default function AuthPage() {
  const navigate = useNavigate();
  const { login, register } = useAuth();

  const [mode, setMode] = useState('login');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    username: '', // treated as email for backend compatibility
    password: '',
    role: 'employee',
  });

  const update = (k, v) =>
    setForm((f) => ({
      ...f,
      [k]: v,
    }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'login') {
        await login({
          username: form.username,
          password: form.password,
        });
        navigate('/chat');
      } else {
        await register({
          username: form.username,
          password: form.password,
          role: form.role,
        });
      

      // after successful register:
      setMode('login');

      setError(
        'Account created successfully. Please sign in.'
      );

      setForm({
        username: '',
        password: '',
        role: 'employee',
      });
    }
    } catch (err) {
      setError(
        err?.message ||
          err?.response?.data?.detail ||
          err?.response?.data?.message ||
          'Authentication failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-root">
      {/* LEFT PANEL */}
      <div className="auth-left">
        <div className="auth-left-content">
          <div className="auth-logo">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect
                width="48"
                height="48"
                rx="14"
                fill="rgba(255,255,255,0.15)"
              />
              <path
                d="M24 10L36 17V31L24 38L12 31V17L24 10Z"
                stroke="white"
                strokeWidth="2"
                strokeLinejoin="round"
                fill="none"
              />
              <circle cx="24" cy="24" r="5" fill="white" />
            </svg>

            <span className="auth-logo-text">CopilotAI</span>
          </div>

          <div className="auth-hero">
            <h1 className="auth-hero-title">
              Enterprise
              <br />
              Multi-Agent
              <br />
              AI Copilot
            </h1>

            <p className="auth-hero-sub">
              Intelligent automation for HR & IT powered by AI agents.
            </p>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="auth-right">
        <div className="auth-form-card">
          <div className="auth-tabs">
            <button
              type="button"
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => {
                setMode('login');
                setError('');
              }}
            >
              Sign In
            </button>

            <button
              type="button"
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => {
                setMode('register');
                setError('');
              }}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            {/* USERNAME */}
            <div className="auth-field-group">
              <label className="auth-label">Email</label>

              <input
                className="auth-input"
                type="email"
                placeholder="Enter email"
                value={form.username}
                onChange={(e) => update('username', e.target.value)}
                required
              />
            </div>

            {/* PASSWORD */}
            <div className="auth-field-group">
              <label className="auth-label">Password</label>

              <input
                className="auth-input"
                type="password"
                placeholder="Enter password"
                value={form.password}
                onChange={(e) => update('password', e.target.value)}
                required
              />
            </div>

            {/* ROLE ONLY FOR REGISTER */}
            {mode === 'register' && (
              <div className="auth-field-group">
                <label className="auth-label">
                  Your Role
                </label>

                <div className="auth-select-wrap">
                  <select
                    className="auth-select"
                    value={form.role}
                    onChange={(e) => update('role', e.target.value)}
                  >
                    {ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>

                  <span className="auth-select-arrow">▾</span>
                </div>

                <div
                  className="auth-role-badge"
                  data-role={form.role}
                >
                  {getRoleDescription(form.role)}
                </div>
              </div>
            )}

            {/* ERROR */}
            {error && (
              <div className="auth-error">
                <span className="auth-error-icon">⚠</span>
                {error}
              </div>
            )}

            {/* SUBMIT */}
            <button
              type="submit"
              className={`auth-submit ${loading ? 'loading' : ''}`}
              disabled={loading}
            >
              {loading ? (
                <span className="auth-spinner" />
              ) : mode === 'login' ? (
                'Sign In'
              ) : (
                'Create Account'
              )}
            </button>
          </form>

          <div className="auth-demo-hint">
            <span>Demo:</span> employee@novigo.com / password123
          </div>
        </div>
      </div>
    </div>
  );
}

function getRoleDescription(role) {
  const map = {
    employee: '📋 Employee access',
    manager: '✅ Team management access',
    it_team: '🖥️ IT support access',
    admin: '🔐 Full system access',
  };

  return map[role] || '';
}