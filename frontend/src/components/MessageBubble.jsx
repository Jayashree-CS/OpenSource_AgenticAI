import React from 'react';
import './MessageBubble.css';

const AGENT_CONFIG = {
  hr: {
    name: 'HR Assistant',
    icon: '👥',
    color: 'hr',
  },
  it: {
    name: 'IT Support Pro',
    icon: '🖥️',
    color: 'it',
  },
  router: {
    name: 'AI Copilot',
    icon: '✦',
    color: 'router',
  },
};

export default function MessageBubble({ message, userInitial }) {
  if (message.typing) {
    return (
      <div className="bubble-row assistant">
        <div className="bubble-avatar assistant-avatar router">✦</div>
        <div className="bubble-content">
          <div className="bubble assistant typing-bubble">
            <span className="typing-dot" style={{ animationDelay: '0s' }} />
            <span className="typing-dot" style={{ animationDelay: '0.2s' }} />
            <span className="typing-dot" style={{ animationDelay: '0.4s' }} />
          </div>
        </div>
      </div>
    );
  }

  if (message.role === 'user') {
    return (
      <div className="bubble-row user">
        <div className="bubble-content user-content">
          <div className="bubble user-bubble">
            <p className="bubble-text">{message.content}</p>
          </div>
          <span className="bubble-time">{formatTime(message.timestamp)}</span>
        </div>
        <div className="bubble-avatar user-avatar">{userInitial}</div>
      </div>
    );
  }

  // Assistant message
  const agentKey = message.agent || 'router';
  const agent = AGENT_CONFIG[agentKey] || AGENT_CONFIG.router;

  return (
    <div className={`bubble-row assistant ${message.isError ? 'error-row' : ''}`} style={{ animationDuration: '0.3s' }}>
      <div className={`bubble-avatar assistant-avatar ${agent.color}`}>
        {agent.icon}
      </div>
      <div className="bubble-content">
        <div className="bubble-agent-name">{agent.name}</div>
        <div className={`bubble assistant-bubble ${message.isError ? 'error-bubble' : ''}`}>
          <div className="bubble-text assistant-text">
            {formatContent(message.content)}
          </div>
          {message.sources && message.sources.length > 0 && (
            <div className="bubble-sources">
              {message.sources.map((src, i) => (
                <span key={i} className="bubble-source-chip">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  {src}
                </span>
              ))}
            </div>
          )}
          {message.requires_approval && (
            <div className="bubble-approval-notice">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              This request requires manager approval
            </div>
          )}
        </div>
        <span className="bubble-time">{formatTime(message.timestamp)}</span>
      </div>
    </div>
  );
}

function formatTime(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

function formatContent(content) {
  if (!content) return null;
  // Convert **bold** and line breaks
  const lines = content.split('\n');
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return (
      <React.Fragment key={i}>
        {i > 0 && <br />}
        {parts.map((part, j) =>
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong>
            : part
        )}
      </React.Fragment>
    );
  });
}
