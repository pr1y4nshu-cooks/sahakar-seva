import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Home } from './pages/Home';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

function renderHome() {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe('Home', () => {
  it('renders main heading and CTA buttons', () => {
    renderHome();
    expect(screen.getByRole('heading', { name: /Trusted help/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Hire a Worker/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Find Work/i })).toBeInTheDocument();
  });

  it('renders the tagline', () => {
    renderHome();
    expect(screen.getByText('Local work. Shared prosperity.')).toBeInTheDocument();
  });

  it('renders three feature cards', () => {
    renderHome();
    expect(screen.getByText('People-first by design')).toBeInTheDocument();
    expect(screen.getByText('Hyperlocal by nature')).toBeInTheDocument();
    expect(screen.getByText('Built on trust')).toBeInTheDocument();
  });
});