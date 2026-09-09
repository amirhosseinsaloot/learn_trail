import { act, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';

import { routes } from './router';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe('routes', () => {
  it.each([
    ['/login', 'Sign in'],
    ['/register', 'Create your account'],
    ['/', 'Conversations'],
    ['/c/new', 'New conversation'],
    ['/c/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f', 'Conversation'],
    ['/c/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f/summary', 'Review before saving'],
    ['/library', 'Library'],
    ['/library/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f', 'Saved summary'],
    ['/ask', 'Ask my knowledge'],
    ['/account', 'Account'],
  ])('%s renders one h1 named %s inside main', (path, heading) => {
    renderAt(path);
    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(heading);
    expect(screen.getByRole('main')).toContainElement(headings[0] ?? null);
  });

  it('shows the context list only for conversation and library sections', () => {
    renderAt('/library');
    expect(screen.getByRole('region', { name: 'Saved summaries' })).toBeInTheDocument();
  });

  it('shows no context list on the ask screen', () => {
    renderAt('/ask');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('renders Not found with a link home for unknown paths', () => {
    renderAt('/nowhere/at/all');
    expect(screen.getByRole('heading', { level: 1, name: 'Not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to your conversations' })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('moves focus to the new h1 after a route change', async () => {
    const router = renderAt('/');
    await act(() => router.navigate('/library'));
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Library' })).toHaveFocus();
    });
  });

  it('marks the active section in the navigation', () => {
    renderAt('/library/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f');
    const links = screen.getAllByRole('link', { name: 'Library', current: 'page' });
    expect(links.length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: 'Ask', current: 'page' })).not.toBeInTheDocument();
  });
});
