/**
 * Tests for UI State Components
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import {
  Loading,
  Skeleton,
  EmptyState,
  ErrorState,
  PageWrapper
} from '@/components/ui/States';
import { DevBadge } from '@/components/ui/DevBadge';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Button } from '@/components/ui/Button';

// Mock the api adapter for DevBadge
vi.mock('@/lib/api-adapter', () => ({
  getApiModeBadge: () => ({ text: 'Dev fixtures active', variant: 'dev' }),
}));

// Wrapper with router for components that use Link
const renderWithRouter = (ui: React.ReactElement) => {
  return render(
    <BrowserRouter>
      {ui}
    </BrowserRouter>
  );
};

describe('UI State Components', () => {
  describe('Loading', () => {
    it('renders spinner with text', () => {
      render(<Loading text="Loading data..." />);
      expect(screen.getByText('Loading data...')).toBeInTheDocument();
    });

    it('renders full screen when requested', () => {
      render(<Loading fullScreen />);
      const container = screen.getByText('Loading...').parentElement;
      expect(container).toHaveClass('min-h-screen');
    });
  });

  describe('Skeleton', () => {
    it('renders with correct variant classes', () => {
      const { container } = render(<Skeleton variant="card" />);
      const skeleton = container.querySelector('div');
      expect(skeleton).toHaveClass('animate-pulse');
    });
  });

  describe('EmptyState', () => {
    it('renders title and description', () => {
      renderWithRouter(<EmptyState title="No data" description="Nothing to show" />);
      expect(screen.getByText('No data')).toBeInTheDocument();
      expect(screen.getByText('Nothing to show')).toBeInTheDocument();
    });

    it('renders action button', () => {
      renderWithRouter(<EmptyState title="No data" action={{ label: 'Create', onClick: vi.fn() }} />);
      expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
    });

    it('renders action link', () => {
      renderWithRouter(<EmptyState title="No data" action={{ label: 'Go', href: '/test' }} />);
      expect(screen.getByRole('link', { name: 'Go' })).toBeInTheDocument();
    });
  });

  describe('ErrorState', () => {
    it('renders network error correctly', () => {
      render(<ErrorState type="network" message="Cannot connect" onRetry={vi.fn()} />);
      expect(screen.getByText('Connection Problem')).toBeInTheDocument();
      expect(screen.getByText('Cannot connect')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument();
    });

    it('renders unauthorized error correctly', () => {
      render(<ErrorState type="unauthorized" message="Please sign in" />);
      expect(screen.getByText('Please Sign In')).toBeInTheDocument();
      expect(screen.getByText('Please sign in')).toBeInTheDocument();
    });

    it('renders details when provided', () => {
      render(<ErrorState type="unknown" message="Error" details="Stack trace here" />);
      expect(screen.getByText('Error')).toBeInTheDocument();
      // Details are in a details element
      const details = screen.getByText('Stack trace here');
      expect(details).toBeInTheDocument();
    });
  });

  describe('PageWrapper', () => {
    it('shows loading when isLoading', () => {
      render(<PageWrapper isLoading loadingText="Loading..." />);
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('shows error when error prop', () => {
      render(<PageWrapper error={{ type: 'network', message: 'Failed' }} />);
      expect(screen.getByText('Connection Problem')).toBeInTheDocument();
    });

    it('shows empty when isEmpty', () => {
      render(<PageWrapper isEmpty emptyTitle="Nothing here" />);
      expect(screen.getByText('Nothing here')).toBeInTheDocument();
    });

    it('shows children when no special state', () => {
      render(<PageWrapper><div data-testid="content">Content</div></PageWrapper>);
      expect(screen.getByTestId('content')).toBeInTheDocument();
    });
  });
});

describe('DevBadge', () => {
  it('renders dev badge in fixtures mode', () => {
    render(<DevBadge />);
    expect(screen.getByText('Dev fixtures active')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('opens details on click', () => {
    render(<DevBadge />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('Development Mode')).toBeInTheDocument();
  });
});

describe('ErrorBoundary', () => {
  it('catches render errors', () => {
    const ThrowError = () => {
      throw new Error('Test error');
    };

    renderWithRouter(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload Page' })).toBeInTheDocument();
  });
});

describe('Button', () => {
  it('renders with primary variant by default', () => {
    render(<Button>Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toHaveClass('bg-plum');
    expect(button).toHaveClass('text-white');
  });

  it('renders with secondary variant', () => {
    render(<Button variant="secondary">Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toHaveClass('bg-ink/10');
    expect(button).toHaveClass('text-ink');
  });

  it('renders with outline variant', () => {
    render(<Button variant="outline">Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toHaveClass('border');
    expect(button).toHaveClass('bg-white');
  });

  it('renders with ghost variant', () => {
    render(<Button variant="ghost">Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toHaveClass('bg-transparent');
    expect(button).toHaveClass('text-ink');
  });

  it('applies disabled state', () => {
    render(<Button disabled>Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button).toBeDisabled();
  });
});