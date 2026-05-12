import React from 'react';
import './QuickActions.css';

// Exactly two role-relevant chips per role. Dashboard chips navigate to
// the role's primary dashboard route; the others fire a chat prompt.
const ACTION_SETS = {
  employee: [
    { label: 'Apply Leave', prompt: 'I want to apply for leave', icon: '📅', agent: 'hr' },
    { label: 'Raise IT Ticket', prompt: 'I need to raise an IT support ticket', icon: '🎫', agent: 'it' },
  ],
  manager: [
    { label: 'Pending Approvals', prompt: 'Show all pending approvals', icon: '✅', agent: 'hr' },
    { label: 'Dashboard', icon: '�', agent: null, navigateTo: '/manager' },
  ],
  it_team: [
    {
      label: 'Pending Requests',
      // Shows both pending IT tickets AND pending asset approvals for
      // the IT team (capability dispatcher / IT agent handles this).
      prompt: 'Show pending IT tickets and pending asset approvals',
      icon: '�',
      agent: 'it',
    },
    { label: 'Dashboard', icon: '�', agent: null, navigateTo: '/it' },
  ],
  admin: [
    { label: 'System Logs', prompt: 'Show system activity logs', icon: '🗃️', agent: null },
    { label: 'Inventory', prompt: 'Show inventory', icon: '📦', agent: 'it' },
  ],
};

export default function QuickActions({ role, detectedAgent, onAction, onNavigate }) {
  const actions = ACTION_SETS[role] || ACTION_SETS.employee;

  // Each role gets exactly two relevant chips. Agent-filtering is no
  // longer useful with the trimmed set, so we always render both.
  const displayed = actions;

  const handleClick = (action) => {
    if (action.navigateTo && typeof onNavigate === 'function') {
      onNavigate(action.navigateTo);
      return;
    }
    if (action.prompt && typeof onAction === 'function') {
      onAction(action.prompt);
    }
  };

  return (
    <div className="quick-actions" role="group" aria-label="Quick actions">
      {displayed.map((action, i) => (
        <button
          key={i}
          className={`quick-chip ${action.agent ? `chip-${action.agent}` : ''}`}
          onClick={() => handleClick(action)}
          type="button"
        >
          <span className="quick-chip-icon">{action.icon}</span>
          {action.label}
        </button>
      ))}
    </div>
  );
}
