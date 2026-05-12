/**
 * chatService.js
 * 
 * Secure chat service with user isolation and proper session management
 * Prevents chat leakage between users
 */

import { api } from '../api/client';

// Session storage keys with user isolation
const SESSION_KEY_PREFIX = 'chat_sessions_v2:';
const USER_SESSIONS_KEY = 'user_chat_sessions';

// Chat title generation based on intent
const TITLE_PATTERNS = {
  leave_request: [
    /apply.*leave/i,
    /leave.*request/i,
    /need.*leave/i,
    /sick.*leave/i,
    /casual.*leave/i,
    /earned.*leave/i
  ],
  it_support: [
    /reset.*laptop/i,
    /laptop.*issue/i,
    /computer.*problem/i,
    /software.*install/i,
    /hardware.*request/i,
    /it.*support/i,
    /technical.*issue/i
  ],
  payroll: [
    /salary.*slip/i,
    /pay.*stub/i,
    /payslip/i,
    /salary.*statement/i,
    /earnings/i,
    /wage/i
  ],
  policy: [
    /policy/i,
    /rule/i,
    /guideline/i,
    /procedure/i,
    /what.*is/i,
    /how.*to/i,
    /company/i
  ]
};

// Get user-specific session key
function getUserSessionKey(user) {
  if (!user || !user.email) {
    throw new Error('User not authenticated for chat session');
  }
  return `${SESSION_KEY_PREFIX}${user.email.toLowerCase()}`;
}

// Get user sessions from localStorage
function getUserSessions(user) {
  try {
    const key = getUserSessionKey(user);
    const sessions = JSON.parse(localStorage.getItem(key) || '[]');
    return sessions.filter(session => session.user_id === user.id);
  } catch (error) {
    console.error('Failed to get user sessions:', error);
    return [];
  }
}

// Save user sessions to localStorage
function saveUserSessions(user, sessions) {
  try {
    const key = getUserSessionKey(user);
    const userSessions = sessions.filter(session => session.user_id === user.id);
    localStorage.setItem(key, JSON.stringify(userSessions));
  } catch (error) {
    console.error('Failed to save user sessions:', error);
  }
}

// Generate chat title based on intent
function generateChatTitle(firstMessage) {
  if (!firstMessage || typeof firstMessage !== 'string') {
    return 'New Chat';
  }

  const message = firstMessage.toLowerCase().trim();
  
  // Check against patterns
  for (const [category, patterns] of Object.entries(TITLE_PATTERNS)) {
    for (const pattern of patterns) {
      if (pattern.test(message)) {
        switch (category) {
          case 'leave_request':
            return 'Leave Request';
          case 'it_support':
            return 'IT Support Request';
          case 'payroll':
            return 'Payroll Assistance';
          case 'policy':
            return 'Policy Inquiry';
          default:
            return 'General Inquiry';
        }
      }
    }
  }

  // Fallback to generic title
  if (message.length > 50) {
    return `${message.substring(0, 47)}...`;
  }
  
  return message || 'New Chat';
}

// Create new chat session
export async function createChatSession(user, initialMessage = 'New Conversation') {
  if (!user) throw new Error('User required to create chat session');
  const sessions = getUserSessions(user);

  // Auto-generate a friendly title from the first message.
  let title = initialMessage.length > 30
    ? initialMessage.substring(0, 30) + '...'
    : initialMessage;

  const lower = (initialMessage || '').toLowerCase();
  if (lower.includes('leave')) title = 'Leave Request';
  else if (lower.includes('ticket')) title = 'IT Ticket';
  else if (lower.includes('asset')) title = 'Asset Request';

  const newSession = {
    id: `session_${Date.now()}`,
    user_id: user.id,
    title,
    messages: [],
    metadata: { message_count: 0 },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  saveUserSessions(user, [newSession, ...sessions]);

  return {
    id: newSession.id,
    title: newSession.title,
    created_at: newSession.created_at,
    messages: [],
  };
}

// Get user's chat sessions
export async function getChatSessions(user) {
  try {
    const sessions = getUserSessions(user);
    return sessions.map(session => ({
      id: session.id,
      title: session.title,
      created_at: session.created_at,
      updated_at: session.updated_at,
      message_count: session.metadata?.message_count || 0,
      last_activity: session.metadata?.last_activity
    }));
  } catch (error) {
    console.error('Failed to get chat sessions:', error);
    return [];
  }
}

// Get specific chat session
export async function getChatSession(user, sessionId) {
  try {
    const sessions = getUserSessions(user);
    const session = sessions.find(s => s.id === sessionId && s.user_id === user.id);
    
    if (!session) {
      throw new Error(`Chat session ${sessionId} not found or access denied`);
    }
    
    return {
      ...session,
      messages: session.messages || []
    };
  } catch (error) {
    console.error('Failed to get chat session:', error);
    throw error;
  }
}

// Update chat session
export async function updateChatSession(user, sessionId, updates) {
  try {
    const sessions = getUserSessions(user);
    const sessionIndex = sessions.findIndex(s => s.id === sessionId && s.user_id === user.id);
    
    if (sessionIndex === -1) {
      throw new Error(`Chat session ${sessionId} not found or access denied`);
    }
    
    sessions[sessionIndex] = {
      ...sessions[sessionIndex],
      ...updates,
      updated_at: new Date().toISOString(),
      metadata: {
        ...sessions[sessionIndex].metadata,
        last_activity: new Date().toISOString()
      }
    };
    
    saveUserSessions(user, sessions);
    return sessions[sessionIndex];
  } catch (error) {
    console.error('Failed to update chat session:', error);
    throw error;
  }
}

// Add message to chat session
export async function addMessageToSession(user, sessionId, message) {
  try {
    const sessions = getUserSessions(user);
    const sessionIndex = sessions.findIndex(s => s.id === sessionId && s.user_id === user.id);
    
    if (sessionIndex === -1) {
      throw new Error(`Chat session ${sessionId} not found or access denied`);
    }
    
    const newMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    };
    
    sessions[sessionIndex].messages = [...(sessions[sessionIndex].messages || []), newMessage];
    sessions[sessionIndex].metadata = {
      ...sessions[sessionIndex].metadata,
      message_count: (sessions[sessionIndex].metadata?.message_count || 0) + 1,
      last_activity: new Date().toISOString()
    };
    
    // Generate title if this is the first message
    if (sessions[sessionIndex].metadata.message_count === 0) {
      sessions[sessionIndex].title = generateChatTitle(message);
    }
    
    sessions[sessionIndex].updated_at = new Date().toISOString();
    saveUserSessions(user, sessions);
    
    return newMessage;
  } catch (error) {
    console.error('Failed to add message to session:', error);
    throw error;
  }
}

// Delete chat session
export async function deleteChatSession(user, sessionId) {
  try {
    const sessions = getUserSessions(user);
    const filteredSessions = sessions.filter(s => !(s.id === sessionId && s.user_id === user.id));
    saveUserSessions(user, filteredSessions);
    return true;
  } catch (error) {
    console.error('Failed to delete chat session:', error);
    throw error;
  }
}

// Clear all user sessions (for logout)
export async function clearUserSessions(user) {
  try {
    const key = getUserSessionKey(user);
    localStorage.removeItem(key);
    return true;
  } catch (error) {
    console.error('Failed to clear user sessions:', error);
    throw error;
  }
}

// Validate session ownership
export function validateSessionOwnership(user, sessionId) {
  try {
    const sessions = getUserSessions(user);
    const session = sessions.find(s => s.id === sessionId);
    return session && session.user_id === user.id;
  } catch (error) {
    console.error('Failed to validate session ownership:', error);
    return false;
  }
}

// Cleanup old sessions (older than 30 days)
export async function cleanupOldSessions(user) {
  try {
    const sessions = getUserSessions(user);
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    
    const activeSessions = sessions.filter(session => {
      const sessionDate = new Date(session.updated_at || session.created_at);
      return sessionDate > thirtyDaysAgo;
    });
    
    saveUserSessions(user, activeSessions);
    return activeSessions.length;
  } catch (error) {
    console.error('Failed to cleanup old sessions:', error);
    return 0;
  }
}

export default {
  createChatSession,
  getChatSessions,
  getChatSession,
  updateChatSession,
  addMessageToSession,
  deleteChatSession,
  clearUserSessions,
  validateSessionOwnership,
  cleanupOldSessions,
  generateChatTitle
};
