import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as apiLogin, register as apiRegister } from '../api/auth';
import { api, readToken, clearAuthStorage, AUTH_FAILED_EVENT } from '../api/client';
import chatService from '../utils/chatService';
import { isValidRole } from '../utils/rbac';

const AuthContext = createContext(null);

function normalizeUser(u) {
  if (!u) return null;
  
  // Backend returns { name, email, role }
  const name = u.full_name || u.name || u.email || 'User';
  const backendRole = (u.role || 'employee').toLowerCase();
  
  // Validate role against expected roles
  const normalizedRole = isValidRole(backendRole) ? backendRole : 'employee';
  
  return {
    ...u,
    name,
    full_name: u.full_name || u.name || name,
    role: normalizedRole,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // Read the token defensively on first mount so we never start the app with
  // a literal "null"/"undefined" string in localStorage.
  const [token, setToken] = useState(() => readToken());
  // Only block on /me when we actually have a token to validate. With no
  // token there is nothing to load, so RequireAuth can immediately redirect
  // to /login instead of showing a blank screen.
  const [loading, setLoading] = useState(() => Boolean(readToken()));

  // Stable logout: reads the latest user from localStorage instead of closing
  // over the user state. Empty deps keep its identity stable across renders so
  // the restore effect below doesn't re-run on every user update (which was
  // the cause of the /me request spam).
  const logout = useCallback(() => {
    let cachedUser = null;
    try {
      const raw = localStorage.getItem('user');
      cachedUser = raw ? JSON.parse(raw) : null;
    } catch (_) {
      cachedUser = null;
    }

    setUser(null);
    setToken(null);
    clearAuthStorage();

    if (cachedUser) {
      try {
        chatService.clearUserSessions(cachedUser);
      } catch (error) {
        console.error('Failed to clear user sessions during logout:', error);
      }
    }
  }, []);

  // Listen for 401s from anywhere in the app (axios response interceptor
  // dispatches AUTH_FAILED_EVENT). The interceptor has already cleared
  // localStorage; we only need to flush React state so RequireAuth navigates
  // to /login through React Router (no hard reload, no race).
  useEffect(() => {
    const handler = () => {
      setUser(null);
      setToken(null);
    };
    window.addEventListener(AUTH_FAILED_EVENT, handler);
    return () => window.removeEventListener(AUTH_FAILED_EVENT, handler);
  }, []);

  // Track whether we have already validated the current token with /me so we
  // never refire the request on subsequent renders / layout swaps.
  const restoredTokenRef = React.useRef(null);

  useEffect(() => {
    // No token → nothing to validate. Make sure local state is clean and
    // RequireAuth can redirect immediately.
    if (!token) {
      setUser(null);
      setLoading(false);
      restoredTokenRef.current = null;
      return undefined;
    }

    // Only run when the token actually changed (avoids /me spam on rerenders).
    if (restoredTokenRef.current === token) {
      return undefined;
    }

    let cancelled = false;

    async function restore() {
      setLoading(true);

      // Prefer server-validated identity. This call should fire exactly once
      // per token (initial load / after login / after manual revalidation).
      try {
        const { data } = await api.get('/me');
        const nextUser = normalizeUser(data?.data || data);
        if (!cancelled) {
          setUser(nextUser);
          localStorage.setItem('user', JSON.stringify(nextUser));
        }
      } catch (error) {
        // Token is invalid or server is rejecting it. We MUST NOT fall back
        // to the cached user — that would leave React state authenticated
        // while every subsequent API call 401s, producing the auth loop.
        // The 401 interceptor has already cleared storage and dispatched
        // AUTH_FAILED_EVENT; just make sure local state is clean.
        console.warn('Failed to restore user from /me:', error?.message || error);
        if (!cancelled) {
          setUser(null);
          setToken(null);
          clearAuthStorage();
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          // Record the token we attempted so we don't retry it on the next
          // render. If the token was cleared above, `token` here is still the
          // closure value; the next effect run with token=null will reset it.
          restoredTokenRef.current = token;
        }
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
    // logout is stable (empty deps), so it does not need to be in the dep list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const login = async (credentials) => {
    try {
      console.log('Attempting login with:', { email: credentials.email || credentials.username });
      const resolvedEmail = (credentials.email || credentials.username || '').trim();
      const data = await apiLogin({ email: resolvedEmail, password: credentials.password });

      console.log('Login response:', data);

      setToken(data.token);
      const nextUser = normalizeUser(data.user);
      setUser(nextUser);
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(nextUser));
      
      console.log('Login successful, user:', nextUser);
      return nextUser;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  const register = async (payload) => {
    try {
      console.log('Attempting registration with:', { email: payload.email || payload.username, role: payload.role });
      const data = await apiRegister(payload);

      console.log('Registration response:', data);

      setToken(data.token);
      const nextUser = normalizeUser(data.user);
      setUser(nextUser);
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(nextUser));
      
      console.log('Registration successful, user:', nextUser);
      return nextUser;
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);