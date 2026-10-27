/**
 * Auth Guard Component
 *
 * Wraps protected routes with proper loading, auth state handling,
 * and session expiry detection.
 */

import { ReactNode, useEffect, useState } from 'react';
import { Navigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import { PageWrapper, Skeleton } from '@/components/ui/States';
import { Card } from '@/components/ui/Card';
import { Loader2, AlertCircle, Lock } from 'lucide-react';

interface AuthGuardProps {
  children?: ReactNode;
  fallback?: ReactNode;
}

export function AuthGuard({ children, fallback }: AuthGuardProps) {
  const { user, session, loading: authLoading, isFixturesMode, refreshUser } = useAuth();
  const location = useLocation();
  const [showSessionExpired, setShowSessionExpired] = useState(false);

  // Detect session expiry by attempting to refresh
  useEffect(() => {
    if (!authLoading && session?.access_token && user) {
      // Session exists, check if it's still valid
      const checkSession = async () => {
        try {
          await refreshUser();
          setShowSessionExpired(false);
        } catch (err: any) {
          if (err.status === 401) {
            setShowSessionExpired(true);
          }
        }
      };

      checkSession();
    }
  }, [authLoading, session, user, refreshUser]);

  // Show loading skeleton during auth check
  if (authLoading) {
    return (
      <PageWrapper isLoading loadingText="Restoring session...">
        <div className="min-h-screen flex items-center justify-center bg-cream px-4">
          <Card className="p-8 text-center">
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-plum" />
            <p className="mt-3 text-sm text-ink/60">Restoring your session...</p>
          </Card>
        </div>
      </PageWrapper>
    );
  }

  // Show session expired modal
  if (showSessionExpired) {
    return (
      <PageWrapper className="min-h-screen flex items-center justify-center bg-cream px-4 py-12">
        <Card className="w-full max-w-md text-center">
          <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-amber-50 flex items-center justify-center">
            <AlertCircle className="h-6 w-6 text-amber-500" />
          </div>
          <h2 className="text-xl font-bold text-ink">Session Expired</h2>
          <p className="mt-2 text-sm text-ink/60">
            Your session has expired. Please sign in again to continue.
          </p>
          <div className="mt-6">
            <button
              onClick={() => setShowSessionExpired(false)}
              className="text-plum font-medium hover:underline"
            >
              Sign in again
            </button>
          </div>
        </Card>
      </PageWrapper>
    );
  }

  // Not authenticated - redirect to login with return path
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Authenticated - render children
  return children ? <>{children}</> : <Outlet />;
}

/**
 * Public Only Guard
 * Redirects authenticated users away from login/signup pages
 */
export function PublicOnlyGuard({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <PageWrapper isLoading loadingText="Checking session...">
        <div className="min-h-screen flex items-center justify-center bg-cream px-4">
          <Card className="p-8 text-center">
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-plum" />
            <p className="mt-3 text-sm text-ink/60">Checking session...</p>
          </Card>
        </div>
      </PageWrapper>
    );
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

/**
 * Email Confirmation Required Screen
 * Shown when signup returns no session (email verification required)
 */
export function EmailConfirmationRequired({
  email,
  onResend,
  onBackToLogin
}: {
  email: string;
  onResend?: () => Promise<void>;
  onBackToLogin?: () => void;
}) {
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  const handleResend = async () => {
    if (!onResend) return;
    setResending(true);
    try {
      await onResend();
      setResent(true);
    } finally {
      setResending(false);
    }
  };

  return (
    <PageWrapper className="min-h-screen flex items-center justify-center bg-cream px-4 py-12">
      <Card className="w-full max-w-md text-center">
        <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-blue-50 flex items-center justify-center">
          <Lock className="h-6 w-6 text-blue-500" />
        </div>
        <h1 className="text-2xl font-bold text-ink">Confirm Your Email</h1>
        <p className="mt-3 text-sm text-ink/60">
          We've sent a confirmation link to <strong>{email}</strong>.
          Please check your inbox (and spam folder) and click the link to verify your account.
        </p>

        <div className="mt-6 space-y-3">
          <button
            onClick={handleResend}
            disabled={resending || resent}
            className="w-full text-plum font-medium hover:underline disabled:opacity-50"
          >
            {resending ? 'Sending...' : resent ? 'Email sent!' : "Didn't receive it? Resend confirmation"}
          </button>

          <button
            onClick={onBackToLogin}
            className="w-full text-ink/60 font-medium hover:underline"
          >
            Back to sign in
          </button>
        </div>
      </Card>
    </PageWrapper>
  );
}