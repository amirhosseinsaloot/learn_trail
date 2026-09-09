import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('renders the shell landmarks and the conversations screen', () => {
    render(<App />);
    // Desktop rail header and mobile top bar both exist in the DOM; CSS shows one.
    expect(screen.getAllByRole('banner').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('navigation', { name: 'Main' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Conversations' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute(
      'href',
      '#main',
    );
  });
});
