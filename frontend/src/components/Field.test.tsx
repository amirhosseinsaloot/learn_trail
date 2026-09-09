import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Field } from './Field';

describe('Field', () => {
  it('binds the label and hint to the input', () => {
    render(<Field id="email" label="Email" hint="We never share it." type="email" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAccessibleDescription('We never share it.');
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('marks the input invalid and describes the error', () => {
    render(<Field id="password" label="Password" error="Use at least 12 characters." />);
    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Use at least 12 characters.');
    expect(input).toHaveClass('input--invalid');
  });
});
