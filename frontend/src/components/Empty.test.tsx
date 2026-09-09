import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from './Button';
import { Empty } from './Empty';

describe('Empty', () => {
  it('renders a heading, one sentence, and the action', () => {
    render(
      <Empty
        title="No conversations yet"
        description="Start one and Nuroli keeps what you work out."
        action={<Button variant="primary">New conversation</Button>}
      />,
    );
    expect(screen.getByRole('heading', { level: 2, name: 'No conversations yet' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'New conversation' })).toBeInTheDocument();
  });
});
