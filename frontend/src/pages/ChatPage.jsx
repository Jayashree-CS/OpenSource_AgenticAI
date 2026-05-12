import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import chatService from '../utils/chatService';
import { sendChatMessage } from '../api/chat';
import MessageBubble from '../components/MessageBubble';
import QuickActions from '../components/QuickActions';
import ApprovalWidget from '../components/ApprovalWidget';
import AdminConsole from '../components/AdminConsole';
import './ChatPage.css';

const WELCOME_MESSAGES = {
  employee: "Hello! I'm your AI Copilot. I can help you with HR queries, leave requests, IT support tickets, and more. What would you like to do today?",
  manager: "Welcome back! I can help you manage your team's requests, approve leaves, and handle IT needs. You also have pending approvals to review.",
  it_team: "IT Support active. I can help with ticket management, asset tracking, and technical troubleshooting.",
  admin: "Admin mode active. Full system access enabled. Use the Admin Console tab for logs and configuration.",
};

export default function ChatPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [activePanel, setActivePanel] = useState(null); // 'admin' | null
  const [detectedAgent, setDetectedAgent] = useState(null); // 'hr' | 'it' | null
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const messagesRef = useRef([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages, activeSession]);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    if (!user) return;
    
    try {
      const data = await chatService.getChatSessions(user);
      setSessions(data);
      if (data.length > 0) {
        loadSession(data[0].id);
      } else {
        await startNewSession();
      }
    } catch (error) {
      console.error('Failed to load sessions:', error);
      // If sessions fail, start fresh with welcome message
      addWelcome();
    }
  };

  const loadSession = async (sessionId) => {
    if (!user) return;
    
    try {
      const data = await chatService.getChatSession(user, sessionId);
      setActiveSession(sessionId);
      setMessages(data.messages || []);
    } catch (error) {
      console.error('Failed to load session:', error);
      addWelcome();
    }
  };

  const startNewSession = async () => {
    if (!user) return;
    
    try {
      const data = await chatService.createChatSession(user);
      setActiveSession(data.id);
      setSessions(prev => [data, ...prev]);
      setMessages([]);
      // Add welcome message
      const welcomeMsg = { role: 'assistant', content: WELCOME_MESSAGES[user.role] || WELCOME_MESSAGES.employee };
      setMessages([welcomeMsg]);
    } catch (error) {
      console.error('Failed to create new session:', error);
      // If even new session fails, add welcome manually
      addWelcome();
    }
  };

  const addWelcome = (sessionId) => {
    const welcomeMsg = {
      id: `welcome_${Date.now()}`,
      role: 'assistant',
      content: WELCOME_MESSAGES[user?.role] || WELCOME_MESSAGES.employee,
      agent: null,
      timestamp: new Date().toISOString(),
    };
    setMessages([welcomeMsg]);
  };

  const sendMessage = useCallback(async (text) => {
    if (!user) {
      console.error('Cannot send message: user not authenticated');
      return;
    }

    const content = (text || input).trim();
    if (!content || sending) return;
    
    let currentSessionId = activeSession;

    if (!activeSession) {
      // Create new session
      const newSession = await chatService.createChatSession(user, content);
      currentSessionId = newSession.id;
      setActiveSession(currentSessionId);
      setSessions(prev => [newSession, ...prev]);
      setMessages([{
        id: `welcome_${Date.now()}`,
        role: 'assistant',
        content: WELCOME_MESSAGES[user.role] || WELCOME_MESSAGES.employee,
        timestamp: new Date().toISOString(),
      }]);
    } else {
      // Add message to existing session
      try {
        const newMessage = await chatService.addMessageToSession(user, activeSession, content);
        setMessages(prev => [...prev, newMessage]);
      } catch (error) {
        console.error('Failed to add message:', error);
        setMessages(prev => [...prev, {
          id: `err_${Date.now()}`,
          role: 'assistant',
          content: 'Failed to send message. Please try again.',
          isError: true,
          timestamp: new Date().toISOString(),
        }]);
        return; // Exit early if message addition failed
      }
    }
    
    setInput('');
    setSending(true);

    // Typing indicator
    const typingId = `typing_${Date.now()}`;
    setMessages(prev => [...prev, { id: typingId, role: 'assistant', typing: true }]);

    try {
      const history = (messagesRef.current || []).slice(-10).map(m => ({
        role: m.role,
        content: m.content,
      }));
      
      // Send message to backend
      const data = await sendChatMessage({ message: content });

      // Update session with AI response
      const aiMessage = {
        id: `ai_${Date.now()}`,
        role: 'assistant',
        content: data.reply,
        agent: data.agent || null,
        sources: data.sources || null,
        timestamp: new Date().toISOString(),
      };

      await chatService.updateChatSession(user, currentSessionId, {
        messages: [...messagesRef.current, aiMessage]
      });

      setMessages(prev => {
      const filtered = prev.filter(m => m.id !== typingId);
      return [...filtered, aiMessage];
    });

      if (data.agent) setDetectedAgent(data.agent);
    } catch (err) {
      setMessages(prev => {
        const filtered = prev.filter(m => m.id !== typingId);
        const errorMessage = {
          id: `err_${Date.now()}`,
          role: 'assistant',
          content: err?.message || 'Sorry, I encountered an error. Please try again.',
          isError: true,
          timestamp: new Date().toISOString(),
        };
        return [...filtered, errorMessage];
      });
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [input, sending, messages, activeSession, user]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const agentLabel = detectedAgent === 'hr'
    ? 'HR Agent Active'
    : detectedAgent === 'it'
    ? 'IT Support Active'
    : 'AI Copilot';

  const canAccessAdmin = ['admin'].includes(user?.role);

  return (
    <div className="chat-root" style={{ flex: 1, height: '100vh' }}>
      <div className="chat-main">
        {/* Header */}
        <header className="chat-header">
          <button
            className="chat-header-toggle"
            onClick={startNewSession}
            aria-label="New chat"
            title="New chat"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>

          <div className="chat-header-agent">
            <div className={`chat-agent-dot ${detectedAgent || 'idle'}`} />
            <span className="chat-agent-name">{agentLabel}</span>
          </div>

          <div className="chat-header-user">
            <div className="chat-header-role-badge" data-role={user?.role}>
              {formatRole(user?.role)}
            </div>
            <div className="chat-header-avatar">
              {(user?.full_name || user?.name || user?.email || 'U')?.charAt(0)?.toUpperCase() || 'U'}
            </div>
          </div>
        </header>

        {/* Panel overlays */}
        {activePanel === 'admin' && canAccessAdmin && (
          <AdminConsole onClose={() => setActivePanel(null)} />
        )}

        {/* Messages */}
        {!activePanel && (
          <>
            <div className="chat-messages" role="log" aria-live="polite">
              {/* Approvals widget — manager sees leaves + manager-stage assets;
                  IT team sees pending IT tickets + IT-stage assets */}
              {(user?.role === 'manager' || user?.role === 'it_team') && messages.length <= 1 && (
                <ApprovalWidget role={user.role} />
              )}

              {messages.map(msg => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  userInitial={(user?.full_name || user?.name || user?.email || 'U')?.charAt(0)?.toUpperCase() || 'U'}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick actions + Input */}
            <div className="chat-input-area">
              <QuickActions
                role={user?.role}
                detectedAgent={detectedAgent}
                onAction={sendMessage}
                onNavigate={(path) => navigate(path)}
              />
              <div className="chat-input-row">
                <textarea
                  ref={inputRef}
                  className="chat-input"
                  placeholder="Ask about HR policies, leave, IT support, assets..."
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  disabled={sending}
                />
                <button
                  className={`chat-send-btn ${sending ? 'sending' : ''}`}
                  onClick={() => sendMessage()}
                  disabled={sending || !input.trim()}
                  aria-label="Send message"
                >
                  {sending ? (
                    <span className="chat-send-spinner" />
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              </div>
              <p className="chat-input-hint">
                Press <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for new line
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function formatRole(role) {
  const map = {
    employee: 'Employee',
    manager: 'Manager',
    it_team: 'IT Team',
    admin: 'Admin',
  };
  return map[role] || role;
}
