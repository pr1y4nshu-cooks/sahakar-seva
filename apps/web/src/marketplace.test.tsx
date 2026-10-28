import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { rupees } from './lib/marketplace';
import { Hire } from './pages/Hire';
import { AuthProvider } from './lib/auth';

describe('marketplace formatting', () => {
  it('formats integer paise as rupees', () => {
    expect(rupees(70000)).toBe('₹700');
    expect(rupees(63050)).toBe('₹630.50');
    expect(rupees(0)).toBe('₹0');
  });
});

describe('Hire page', () => {
  it('renders a real search form and no hardcoded marketplace metrics', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <BrowserRouter>
          <AuthProvider>
            <Hire />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole('button', { name: /Search workers/i })).toBeDisabled(); // needs service + location first
    expect(screen.getByRole('tab', { name: 'Post a job' })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/12 workers found|24 jobs posted|Verified Workers/);
  });
});
