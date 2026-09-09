import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Alert } from './Alert';

describe('Alert', () => {
  it('uses role alert for errors', () => {
    render(<Alert tone="error">The model is unavailable.</Alert>);
    expect(screen.getByRole('alert')).toHaveTextContent('The model is unavailable.');
  });

  it.each(['info', 'success'] as const)('uses role status for %s', (tone) => {
    render(<Alert tone={tone}>Saved to your library.</Alert>);
    expect(screen.getByRole('status')).toHaveTextContent('Saved to your library.');
  });
});
