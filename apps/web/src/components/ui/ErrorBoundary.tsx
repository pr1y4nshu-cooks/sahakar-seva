/**
 * Error Boundary Component
 *
 * Catches render errors in component tree and shows fallback UI.
 * Does not catch event handler errors (use try/catch there).
 */

import { Component, ReactNode, ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from './Button';
import { Card } from './Card';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-cream px-4 py-12">
          <Card className="w-full max-w-md text-center">
            <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-rose-50 flex items-center justify-center">
              <AlertTriangle className="h-6 w-6 text-rose-500" />
            </div>
            <h2 className="text-xl font-bold text-ink">Something went wrong</h2>
            <p className="mt-2 text-sm text-ink/60">
              We encountered an unexpected error. The team has been notified.
            </p>
            {this.state.error && (
              <details className="mt-4 text-left text-xs text-ink/50">
                <summary className="cursor-pointer mb-1">Error details</summary>
                <pre className="bg-ink/5 rounded p-2 overflow-auto max-h-32">
                  {this.state.error.message}
                  {this.state.error.stack && '\n' + this.state.error.stack}
                </pre>
              </details>
            )}
            <div className="mt-6 flex gap-3">
              <Button onClick={() => window.location.reload()} className="flex-1">
                <RefreshCw className="mr-2 h-4 w-4" />
                Reload Page
              </Button>
              <Link to="/" className="flex-1">
                <Button variant="outline" className="flex-1">
                  <Home className="mr-2 h-4 w-4" />
                  Go Home
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Hook for catching async errors in event handlers
 * Usage: const handleClick = useErrorHandler(async () => { ... }, onError);
 */
export function useErrorHandler() {
  // This is a placeholder - in real app, integrate with error reporting service
  return (error: Error) => {
    console.error('[ErrorHandler]', error);
  };
}