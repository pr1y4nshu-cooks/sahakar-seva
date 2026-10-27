/**
 * Auth Context with API Adapter Integration
 *
 * Provides authentication state and token to the app.
 * Integrates with Supabase Auth when configured, or provides dev fixtures.
 * Sets up TanStack Query token provider for automatic auth in hooks.
 */

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { supabase } from '@/lib/supabase';
import { setTokenProvider } from '@/hooks/useApi';
import { api, authMode, request } from '@/lib/api-adapter';
import type { User } from '@/types/api';

type AuthState = {
  user: User | null;
  session: any | null;
  loading: boolean;
  isFixturesMode: boolean;
  signIn: (email: string, password: string) => Promise<{ error: any; user?: User }>;
  signUp: (email: string, password: string) => Promise<{ error: any; user?: User }>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

// ===== Local development identity (VITE_AUTH_MODE=dev) =====
// Tokens come from the API's /dev-auth/token endpoint, which exists only when the server runs with
// APP_ENV=development and DEV_AUTH_ENABLED=true. Every request is still verified server-side.
const DEV_SESSION_KEY = 'sahakar.devSession';

type DevSession = { access_token: string; expires_at: string; email: string };

function readDevSession(): DevSession | null {
  try {
    const raw = window.localStorage.getItem(DEV_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DevSession;
    if (!parsed.access_token || new Date(parsed.expires_at).getTime() <= Date.now()) {
      window.localStorage.removeItem(DEV_SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function fetchBackendUser(token: string): Promise<User> {
  return request<User>('/api/v1/users/me', {}, token);
}

function setGlobalToken(token: string | null) {
  (window as any).__SAHAKAR_AUTH_TOKEN__ = token;
}

// Token provider for TanStack Query hooks
async function getAuthToken(): Promise<string | null> {
  // This will be set by the AuthProvider
  return (window as any).__SAHAKAR_AUTH_TOKEN__ ?? null;
}

setTokenProvider(getAuthToken);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [isFixturesMode, setIsFixturesMode] = useState(false);

  // Check API mode on mount
  useEffect(() => {
    setIsFixturesMode(api.isFixturesMode());
  }, []);

  const refreshUser = useCallback(async () => {
    if (!session?.access_token) {
      setUser(null);
      return;
    }
    if (authMode === 'dev') {
      try {
        setUser(await fetchBackendUser(session.access_token));
      } catch (err: any) {
        if (err.status === 401) {
          window.localStorage.removeItem(DEV_SESSION_KEY);
          setUser(null);
          setGlobalToken(null);
        }
        throw err;
      }
      return;
    }

    try {
      const implementation = await api.getImplementation();
      const userData = await implementation.user.getCurrent(session.access_token);
      setUser(userData);
      // Store token globally for hooks
      (window as any).__SAHAKAR_AUTH_TOKEN__ = session.access_token;
    } catch (err: any) {
      if (err.status === 401) {
        setUser(null);
        (window as any).__SAHAKAR_AUTH_TOKEN__ = null;
      }
      throw err;
    }
  }, [session]);

  // Dev identity mode: restore the stored session and resolve the server-side user.
  useEffect(() => {
    if (authMode !== 'dev') return;
    let mounted = true;
    const stored = readDevSession();
    if (!stored) {
      setLoading(false);
      return;
    }
    setGlobalToken(stored.access_token);
    fetchBackendUser(stored.access_token)
      .then((u) => {
        if (!mounted) return;
        setSession({ access_token: stored.access_token, expires_at: stored.expires_at, user: { email: stored.email } });
        setUser(u);
      })
      .catch(() => {
        window.localStorage.removeItem(DEV_SESSION_KEY);
        setGlobalToken(null);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  const devSignIn = async (email: string, passcode: string) => {
    try {
      const res = await request<{ access_token: string; expires_at: string }>('/api/v1/dev-auth/token', {
        method: 'POST',
        body: JSON.stringify({ email, passcode }),
      });
      setGlobalToken(res.access_token);
      const backendUser = await fetchBackendUser(res.access_token);
      const devSession = { access_token: res.access_token, expires_at: res.expires_at, email };
      window.localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(devSession));
      setSession({ access_token: res.access_token, expires_at: res.expires_at, user: { email } });
      setUser(backendUser);
      return { error: null, user: backendUser };
    } catch (err: any) {
      setGlobalToken(null);
      return { error: { message: err?.message || 'Sign-in failed', code: err?.code } };
    }
  };

  useEffect(() => {
    if (authMode === 'dev') return;
    let mounted = true;

    const initAuth = async () => {
      try {
        // Initialize Supabase auth listener
        const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
          if (!mounted) return;

          setSession(session);
          setUser(session?.user ? {
            id: session.user.id,
            display_name: session.user.user_metadata?.display_name || session.user.email?.split('@')[0] || 'User',
            email: session.user.email || '',
            created_at: session.user.created_at,
            updated_at: session.user.updated_at || session.user.created_at,
          } : null);

          if (session?.access_token) {
            (window as any).__SAHAKAR_AUTH_TOKEN__ = session.access_token;
          } else {
            (window as any).__SAHAKAR_AUTH_TOKEN__ = null;
          }

          setLoading(false);
        });

        // Get initial session
        const { data: { session: initialSession } } = await supabase.auth.getSession();
        setSession(initialSession);

        if (initialSession?.user) {
          setUser({
            id: initialSession.user.id,
            display_name: initialSession.user.user_metadata?.display_name || initialSession.user.email?.split('@')[0] || 'User',
            email: initialSession.user.email || '',
            created_at: initialSession.user.created_at,
            updated_at: initialSession.user.updated_at || initialSession.user.created_at,
          });
          (window as any).__SAHAKAR_AUTH_TOKEN__ = initialSession.access_token;
        }

        setLoading(false);

        return () => subscription.unsubscribe();
      } catch {
        setLoading(false);
      }
    };

    initAuth();

    return () => { mounted = false; };
  }, []);

  const signIn = async (email: string, password: string) => {
    if (authMode === 'dev') return devSignIn(email, password);
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      return { error };
    }

    if (data.session?.access_token) {
      (window as any).__SAHAKAR_AUTH_TOKEN__ = data.session.access_token;
      await refreshUser();
    }

    return { error: null, user: data.user ? {
      id: data.user.id,
      display_name: data.user.user_metadata?.display_name || data.user.email?.split('@')[0] || 'User',
      email: data.user.email || '',
      created_at: data.user.created_at,
      updated_at: data.user.updated_at || data.user.created_at,
    } : undefined };
  };

  const signUp = async (email: string, password: string) => {
    // Dev identities are created on first verified request; there is no separate sign-up step.
    if (authMode === 'dev') return devSignIn(email, password);
    const { data, error } = await supabase.auth.signUp({ email, password });

    if (error) {
      return { error };
    }

    // If email confirmation is required, session might be null
    if (data.session?.access_token) {
      (window as any).__SAHAKAR_AUTH_TOKEN__ = data.session.access_token;
      await refreshUser();
      return { error: null, user: data.user ? {
        id: data.user.id,
        display_name: data.user.user_metadata?.display_name || data.user.email?.split('@')[0] || 'User',
        email: data.user.email || '',
        created_at: data.user.created_at,
        updated_at: data.user.updated_at || data.user.created_at,
      } : undefined };
    }

    // No active session - user needs to confirm email
    return {
      error: {
        message: 'Account created! Please check your email to confirm your address.',
        code: 'EMAIL_CONFIRMATION_REQUIRED'
      },
      user: data.user ? {
        id: data.user.id,
        display_name: data.user.user_metadata?.display_name || data.user.email?.split('@')[0] || 'User',
        email: data.user.email || '',
        created_at: data.user.created_at,
        updated_at: data.user.updated_at || data.user.created_at,
      } : undefined
    };
  };

  const signOut = async () => {
    if (authMode === 'dev') {
      window.localStorage.removeItem(DEV_SESSION_KEY);
    } else {
      await supabase.auth.signOut();
    }
    setUser(null);
    setSession(null);
    (window as any).__SAHAKAR_AUTH_TOKEN__ = null;
  };

  return (
    <AuthContext.Provider value={{
      user,
      session,
      loading,
      isFixturesMode,
      signIn,
      signUp,
      signOut,
      refreshUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}