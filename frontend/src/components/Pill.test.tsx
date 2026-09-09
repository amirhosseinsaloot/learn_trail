import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Pill } from './Pill';

describe('Pill', () => {
  it('renders a word next to a hidden glyph', () => {
    const { container } = render(<Pill tone="draft">Draft</Pill>);
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(container.firstChild).toHaveClass('pill--draft');
  });
});
