/**
 * Shared UI State Components
 *
 * Consistent loading, empty, and error states across all pages.
 * These replace ad-hoc inline implementations.
 */

import { ReactNode, useEffect, useState } from 'react';
import { Loader2, Package, AlertCircle, RefreshCw, WifiOff, Search } from 'lucide-react';
import { Button } from './Button';
import { Card } from './Card';
import { Link } from 'react-router-dom';

// ===== Loading State =====

interface LoadingProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
  fullScreen?: boolean;
}

export function Loading({ size = 'md', text = 'Loading...', fullScreen = false }: LoadingProps) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  };

  const containerClasses = fullScreen
    ? 'min-h-screen flex items-center justify-center bg-cream'
    : 'flex flex-col items-center justify-center py-12';

  return (
    <div className={containerClasses}>
      <Loader2 className={`${sizeClasses[size]} animate-spin text-plum`} aria-hidden="true" />
      {text && <p className="mt-3 text-sm text-ink/60">{text}</p>}
    </div>
  );
}

interface SkeletonProps {
  variant?: 'card' | 'text' | 'avatar' | 'button';
  className?: string;
}

export function Skeleton({ variant = 'text', className = '' }: SkeletonProps) {
  const baseClass = 'animate-pulse bg-ink/10 rounded';

  const variantClasses = {
    card: 'h-24 w-full',
    text: 'h-4 w-3/4',
    avatar: 'h-10 w-10 rounded-full',
    button: 'h-10 w-24 rounded-full',
  };

  return <div className={`${baseClass} ${variantClasses[variant]} ${className}`} />;
}

// ===== Empty State =====

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
    variant?: 'primary' | 'secondary';
  };
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = ''
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 text-center ${className}`}>
      {icon && (
        <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-ink/5 flex items-center justify-center text-ink/40">
          {icon}
        </div>
      )}
      <h3 className="text-lg font-medium text-ink">{title}</h3>
      {description && <p className="mt-2 text-sm text-ink/60 max-w-xs">{description}</p>}
      {action && (
        <div className="mt-4">
          {action.href ? (
            <Link to={action.href}>
              <Button variant={action.variant ?? 'primary'} className="w-full sm:w-auto">
                {action.label}
              </Button>
            </Link>
          ) : (
            <Button variant={action.variant ?? 'primary'} onClick={action.onClick} className="w-full sm:w-auto">
              {action.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// ===== Error State =====

export type ErrorType = 'network' | 'unauthorized' | 'forbidden' | 'notfound' | 'validation' | 'server' | 'unknown';

interface ErrorStateProps {
  type: ErrorType;
  title?: string;
  message: string;
  details?: string;
  onRetry?: () => void;
  onAction?: { label: string; onClick: () => void };
  className?: string;
}

const errorConfigs: Record<ErrorType, { icon: ReactNode; defaultTitle: string; color: string }> = {
  network: {
    icon: <WifiOff size={24} />,
    defaultTitle: 'Connection Problem',
    color: 'text-amber-600'
  },
  unauthorized: {
    icon: <AlertCircle size={24} />,
    defaultTitle: 'Please Sign In',
    color: 'text-rose-600'
  },
  forbidden: {
    icon: <AlertCircle size={24} />,
    defaultTitle: 'Access Denied',
    color: 'text-rose-600'
  },
  notfound: {
    icon: <Search size={24} />,
    defaultTitle: 'Not Found',
    color: 'text-ink/60'
  },
  validation: {
    icon: <AlertCircle size={24} />,
    defaultTitle: 'Invalid Input',
    color: 'text-amber-600'
  },
  server: {
    icon: <AlertCircle size={24} />,
    defaultTitle: 'Server Error',
    color: 'text-rose-600'
  },
  unknown: {
    icon: <AlertCircle size={24} />,
    defaultTitle: 'Something Went Wrong',
    color: 'text-rose-600'
  },
};

export function ErrorState({
  type,
  title,
  message,
  details,
  onRetry,
  onAction,
  className = ''
}: ErrorStateProps) {
  const config = errorConfigs[type];

  return (
    <div className={`flex flex-col items-center justify-center py-12 text-center ${className}`}>
      <div className={`mx-auto mb-4 h-12 w-12 rounded-full bg-ink/5 flex items-center justify-center ${config.color}`}>
        {config.icon}
      </div>
      <h3 className="text-lg font-medium text-ink">{title ?? config.defaultTitle}</h3>
      <p className="mt-2 text-sm text-ink/60 max-w-xs">{message}</p>
      {details && (
        <details className="mt-3 text-left text-xs text-ink/50 max-w-xs">
          <summary className="cursor-pointer mb-1">Details</summary>
          <pre className="bg-ink/5 rounded p-2 overflow-auto max-h-24">{details}</pre>
        </details>
      )}
      <div className="mt-4 flex flex-col sm:flex-row gap-2">
        {onRetry && (
          <Button onClick={onRetry} variant="primary" className="w-full sm:w-auto">
            <RefreshCw className="mr-2 h-4 w-4" />
            Try Again
          </Button>
        )}
        {onAction && (
          <Button onClick={onAction.onClick} variant="secondary" className="w-full sm:w-auto">
            {onAction.label}
          </Button>
        )}
      </div>
    </div>
  );
}

// ===== Page Wrapper with States =====

interface PageWrapperProps {
  children?: ReactNode;
  isLoading?: boolean;
  loadingText?: string;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: EmptyStateProps['action'];
  error?: { type: ErrorType; message: string; details?: string } | null;
  onRetry?: () => void;
  className?: string;
}

export function PageWrapper({
  children,
  isLoading,
  loadingText,
  isEmpty,
  emptyTitle,
  emptyDescription,
  emptyAction,
  error,
  onRetry,
  className = '',
}: PageWrapperProps) {
  // Show loading first
  if (isLoading) {
    return (
      <div className={className}>
        <Loading text={loadingText} />
      </div>
    );
  }

  // Show error if present
  if (error) {
    return (
      <div className={className}>
        <ErrorState
          type={error.type}
          message={error.message}
          details={error.details}
          onRetry={onRetry}
        />
      </div>
    );
  }

  // Show empty state if applicable
  if (isEmpty) {
    return (
      <div className={className}>
        <EmptyState
          title={emptyTitle ?? 'No data'}
          description={emptyDescription}
          action={emptyAction}
          icon={<Package size={24} />}
        />
      </div>
    );
  }

  // Show content
  return <div className={className}>{children}</div>;
}